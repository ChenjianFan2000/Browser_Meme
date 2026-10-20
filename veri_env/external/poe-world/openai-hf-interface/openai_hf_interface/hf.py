import torch
from abc import ABC, abstractmethod
from transformers import LlamaTokenizer, LlamaForCausalLM, DataCollatorForLanguageModeling
from torch.nn.functional import log_softmax

from .base import LLMBase


# Decorator
class HF_LLM(LLMBase):
    def __init__(self, model_name, hf_model, formatter):
        self.hf_model = hf_model
        self.device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
        super().__init__(model_name, formatter)

    def handle_kwargs(self, kwargs):
        if 'temperature' not in kwargs:
            kwargs['temperature'] = 0

        if kwargs['temperature'] == 0:
            kwargs['do_sample'] = False
            kwargs.pop('temperature')

        if 'max_tokens' not in kwargs:
            kwargs['max_length'] = 1000
        else:
            kwargs['max_length'] = kwargs['max_tokens']
            kwargs.pop('max_tokens')

        if 'timeout' in kwargs:
            kwargs.pop('timeout')
        if 'request_timeout' in kwargs:
            kwargs.pop('request_timeout')

        kwargs = {**kwargs, **self.default_kwargs}

        return kwargs

    def prompt(self, prompts, **kwargs):
        kwargs = self.handle_kwargs(kwargs)

        prompts = [self.formatter.format_prompt(prompt) for prompt in prompts]

        if self.lookup_cache(prompts[0], **kwargs) is not None: # TODO: Do this better
            outputs = [self.lookup_cache(prompt, **kwargs) for prompt in prompts]
        else:
            data = self.hf_model.data_collator([self.hf_model.tokenizer(prompt) for prompt in prompts])

            gen_tokens = self.hf_model.model.generate(data.input_ids.to(self.device), 
                                            attention_mask=data.attention_mask.to(self.device),
                                            **kwargs)
            
            res = self.hf_model.tokenizer.batch_decode(gen_tokens[:, data.input_ids.shape[1]:])
            outputs = [x.split(self.hf_model.tokenizer.eos_token)[0].split('<unk>')[0] for x in res]

            for prompt, output in zip(prompts, outputs):
                self.update_cache(prompt, output, **kwargs)

        outputs = [self.formatter.format_output(output) for output in outputs]
        return outputs

class HF_model(ABC):
    def __init__(self, model, tokenizer, data_collator):
        self.model = model
        self.tokenizer = tokenizer
        self.data_collator = data_collator


class LLaMA_model(HF_model):
    def __init__(self, model_name):
        tokenizer = LlamaTokenizer.from_pretrained(model_name)
        tokenizer.pad_token = tokenizer.eos_token
        model = LlamaForCausalLM.from_pretrained(
            model_name, torch_dtype=torch.float16, device_map='auto',
        )
        data_collator = DataCollatorForLanguageModeling(tokenizer, mlm=False)

        super().__init__(model, tokenizer, data_collator)