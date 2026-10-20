import asyncio
import json
from openai import AsyncOpenAI
import os
import time
import numpy as np

from .base import LLMBase

# Set openai_api_key if there's secrets.json file
try:
    dir_path = os.path.dirname(os.path.realpath(__file__))
    with open(os.path.join(dir_path, '..', 'secrets.json')) as f:
        data = json.load(f)
        aclient = AsyncOpenAI(api_key=data['openai_api_key'])
        client_provider = 'openai'
except Exception as e:
    try:
        dir_path = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(dir_path, '..', 'secrets.json')) as f:
            data = json.load(f)
            aclient = AsyncOpenAI(api_key=data['openrouter_api_key'], base_url='https://openrouter.ai/api/v1')
            client_provider = 'openrouter'
    except:
        aclient = AsyncOpenAI()


def choose_provider(provider):
    global aclient
    global client_provider
    if provider == 'openrouter':
        try:
            dir_path = os.path.dirname(os.path.realpath(__file__))
            with open(os.path.join(dir_path, '..', 'secrets.json')) as f:
                data = json.load(f)
                aclient = AsyncOpenAI(api_key=data['openrouter_api_key'], base_url='https://openrouter.ai/api/v1')
                client_provider = 'openrouter'
        except:
            aclient = AsyncOpenAI(base_url='https://openrouter.ai/api/v1')
    else:
        try:
            dir_path = os.path.dirname(os.path.realpath(__file__))
            with open(os.path.join(dir_path, '..', 'secrets.json')) as f:
                data = json.load(f)
                aclient = AsyncOpenAI(api_key=data['openai_api_key'])
                client_provider = 'openai'
        except:
            aclient = AsyncOpenAI()


async def prompt_openai_single(model, prompt, n, **kwargs):
    global client_provider
    ct = 0
    n_retries = 30
    while ct <= n_retries:
        try:
            if client_provider == 'openrouter':
                responses = await asyncio.gather(*[aclient.completions.create(model=model, prompt=prompt, **kwargs) for _ in range(n)])
                return [x.text for response in responses for x in response.choices]
            else:
                response = await aclient.completions.create(model=model, prompt=prompt, n=n, **kwargs)
                return [x.text for x in response.choices]
        except Exception as e:
            ct += 1
            print(f'Exception occured: {e}')
            print(f'Waiting for {10 * ct} seconds')
            time.sleep(5 * ct)


async def prompt_openai_chat_single(model, messages, n, **kwargs):
    global client_provider
    ct = 0
    n_retries = 10
    while ct <= n_retries:
        try:
            if client_provider == 'openrouter':
                responses = await asyncio.gather(*[aclient.chat.completions.create(model=model, messages=messages, **kwargs) for _ in range(n)])
                return [x.message.content for response in responses for x in response.choices]
            else:
                response = await aclient.chat.completions.create(model=model, messages=messages, n=n, **kwargs)
                return [x.message.content for x in response.choices]
        except Exception as e: 
            ct += 1
            print(f'Exception occured: {e}')
            print(f'Waiting for {10 * ct} seconds')
            await asyncio.sleep(10 * ct)


class OpenAI_LLM(LLMBase):
    def __init__(self, model, prompt_single_func, formatter):
        self.full_model = model
        self.model = model.split('/')[-1]
        self.prompt_single_func = prompt_single_func
        self.info = {
            'input_tokens': 0,
            'output_tokens': 0,
            'calls': 0,
            'actual_input_tokens': 0,
            'actual_output_tokens': 0,
            'actual_calls': 0,
        }
        self.rng = np.random.default_rng(0)
        super().__init__(self.model, formatter)

    def handle_kwargs(self, kwargs):
        if 'temperature' not in kwargs:
            kwargs['temperature'] = 0
        if 'max_tokens' not in kwargs:
            if not self.model.startswith('gpt-4'):
                kwargs['max_tokens'] = 1000
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 180 if self.model.startswith('gpt-4') else 30
        # if 'request_timeout' not in kwargs:
        #     kwargs['request_timeout'] = 180 if self.model.startswith('gpt-4') else 30

        kwargs = {**kwargs, **self.default_kwargs}

        return kwargs

    def prompt(self, prompts, **kwargs):
        kwargs = self.handle_kwargs(kwargs)

        prompts = [self.formatter.format_prompt(prompt) for prompt in prompts]
        outputs = asyncio.run(self._prompt_batcher(prompts, **kwargs))
        outputs, input_tokens, calls, output_tokens = list(zip(*outputs)) 
        # Note that this is quite risky: https://stackoverflow.com/questions/61647815/do-coroutines-require-locks-when-reading-writing-a-shared-resource
        # Without lock, we need to ensure that operations on self.info are always atomic
        self.info['input_tokens'] += self.formatter.tiklen_formatted_prompts(prompts)
        self.info['calls'] += len(prompts)
        self.info['output_tokens'] += self.formatter.tiklen_outputs(outputs)
        self.info['actual_input_tokens'] += sum(input_tokens)
        self.info['actual_calls'] += sum(calls)
        self.info['actual_output_tokens'] += sum(output_tokens)

        return [self.formatter.format_output(output) for output in outputs]

    async def aprompt(self, prompts, **kwargs):
        kwargs = self.handle_kwargs(kwargs)

        prompts = [self.formatter.format_prompt(prompt) for prompt in prompts]
        outputs = await self._prompt_batcher(prompts, **kwargs)
        outputs, input_tokens, calls, output_tokens = list(zip(*outputs)) 
        # Note that this is quite risky: https://stackoverflow.com/questions/61647815/do-coroutines-require-locks-when-reading-writing-a-shared-resource
        # Without lock, we need to ensure that operations on self.info are always atomic
        self.info['input_tokens'] += self.formatter.tiklen_formatted_prompts(prompts)
        self.info['calls'] += len(prompts)
        self.info['output_tokens'] += self.formatter.tiklen_outputs(outputs)
        self.info['actual_input_tokens'] += sum(input_tokens)
        self.info['actual_calls'] += sum(calls)
        self.info['actual_output_tokens'] += sum(output_tokens)

        return [self.formatter.format_output(output) for output in outputs]

    def override_formatter(self, formatter):
        self.formatter = formatter

    async def _prompt_batcher(self, prompts, **kwargs):
        all_res = []
        for ind in range(0, len(prompts), 1000): # Batch 1000 requests
            res = await asyncio.gather(*[self._get_prompt_res(prompt, **kwargs) for prompt in prompts[ind:ind+1000]])
            all_res += res
        return all_res

    async def _get_prompt_res(self, prompt, **kwargs):
        if 'n' in kwargs:
            n = kwargs['n']
        else:
            n = 1
        cache_res = self.lookup_cache(prompt, **kwargs)
        if cache_res is not None and cache_res[0] is not None and len(cache_res) >= n and len(cache_res[0]) > 0:
            if 'n' in kwargs:
                if len(cache_res) == n:
                    return cache_res, 0, 0, 0
                else:
                    return self.rng.choice(cache_res, n), 0, 0, 0
            else:
                return cache_res[0], 0, 0, 0
        
        if 'n' in kwargs:
            if cache_res is not None and cache_res[0] is not None and len(cache_res[0]) > 0:
                n_existing = len(cache_res)
            else:
                n_existing = 0
        else:
            n_existing = 0

        n_to_prompt = n - n_existing
        
        new_kwargs = kwargs.copy()
        if 'n' in kwargs:
            del new_kwargs['n']
        res = await self.prompt_single_func(self.full_model, prompt, n_to_prompt, **new_kwargs)
        self.update_cache(prompt, n_existing, res, **new_kwargs)
        
        if n_existing > 0:
            res = cache_res + res
        
        return (res if 'n' in kwargs else res[0]), self.formatter.tiklen_formatted_prompts([prompt]), 1, self.formatter.tiklen_outputs(res)

    def get_info(self, cost_per_token=None):
        cost_per_token_dict = {
            'gpt-4-1106-preview': (0.010, 0.030),
            'gpt-4-turbo': (0.010, 0.030),
            'gpt-3.5-turbo': (0.003, 0.006),
            'gpt-4': (0.030, 0.060),
            'gpt-4o': (0.005, 0.015),
            'gpt-4o-2024-08-06': (0.0025, 0.010),
            'gpt-4o-2024-05-13': (0.005, 0.015),
            'gpt-4o-mini': (0.00015, 0.0006),
            'gpt-4o-mini-2024-07-18': (0.00015, 0.0006),
            'o1-preview': (0.015, 0.060),
            'o1-preview-2024-09-12': (0.015, 0.060),
            'o1-mini': (0.003, 0.012),
            'o1-mini-2024-09-12': (0.003, 0.012),
        }
        if cost_per_token is not None:
            self.info['cost_per_token'] = cost_per_token
        else:
            if self.model in cost_per_token_dict:
                self.info['cost_per_token'] = cost_per_token_dict[self.model]
            else:
                self.info['cost_per_token'] = (0, 0)
        self.info['cost'] = self.info['cost_per_token'][0] / 1000 * self.info['input_tokens'] + self.info['cost_per_token'][1] / 1000 * self.info['output_tokens']
        self.info['actual_cost'] = self.info['cost_per_token'][0] / 1000 * self.info['actual_input_tokens'] + self.info['cost_per_token'][1] / 1000 * self.info['actual_output_tokens']
        return self.info