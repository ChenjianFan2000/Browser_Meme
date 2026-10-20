import os
import json
from openai import AsyncOpenAI

from .formatter import DoNothingFormatter, LLaMaChatFormatter, OpenAIChatFormatter
from .openai import OpenAI_LLM, prompt_openai_single, prompt_openai_chat_single


model_list = [
    'gpt-3.5',
    'gpt-4',
    'o1',
    'claude',
    'gemini',
    'llama'
]


def get_formatter(model_name, **formatter_kwargs):
    # if model_name.split('/')[-1].startswith('meta-llama') and model_name.endswith('chat-hf'):
    #     return LLaMaChatFormatter(**formatter_kwargs)
    if sum([model_name.split('/')[-1].startswith(model) for model in model_list]):
        return OpenAIChatFormatter(**formatter_kwargs)
    else:
        return OpenAIChatFormatter(**formatter_kwargs)


def create_llm(model_name, **formatter_kwargs):
    formatter = get_formatter(model_name, **formatter_kwargs)
    # if 'davinci' in model_name:
    #     return OpenAI_LLM(model_name, prompt_openai_single, formatter)
    # elif model_name.split('/')[-1].startswith('meta-llama'):
    #     from .hf import HF_LLM, LLaMA_model
    #     return HF_LLM(model_name, LLaMA_model(model_name), formatter)
    if sum([model_name.split('/')[-1].startswith(model) for model in model_list]):
        return OpenAI_LLM(model_name, prompt_openai_chat_single, formatter)
    else:
        print('WARNING -- this model has not been tested', flush=True)
        return OpenAI_LLM(model_name, prompt_openai_chat_single, formatter)