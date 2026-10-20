import os
import sys
import time
from functools import lru_cache
from httpx import ReadError, RemoteProtocolError
from requests.exceptions import ChunkedEncodingError

import openai
import tiktoken

from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
# OPENAI_API_KEY = 'REDACTED'


# # client = openai.AzureOpenAI() if openai.api_type == "azure" else openai.OpenAI()
# client = openai.Client(
#     api_key=OPENAI_API_KEY
# )
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
if not OPENROUTER_API_KEY:
    raise ValueError("请设置 OPENROUTER_API_KEY 环境变量")

# 配置 OpenRouter 客户端
client = openai.OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

if sys.version_info >= (3, 12):
    from itertools import batched
else:
    def batched(iterable, n: int):
        """ Yield batches of n elements. """
        batch = []
        for item in iterable:
            batch.append(item)
            if len(batch) == n:
                yield batch
                batch = []

        if batch:
            yield batch


@lru_cache()
def get_tokenizer(model):
    model_mapping = {
        "openai/gpt-4o": "gpt-4o",
        "openai/gpt-4": "gpt-4",
        "openai/gpt-4-turbo": "gpt-4-turbo",
        "openai/gpt-3.5-turbo": "gpt-3.5-turbo",
        "anthropic/claude-3-sonnet": "gpt-4",
        "anthropic/claude-3-haiku": "gpt-4",
        "anthropic/claude-3-opus": "gpt-4",
    }
    try:
        m = (model or "").lower() if isinstance(model, str) else ""
        if ("llama" in m) or ("meta-llama" in m):
            return tiktoken.get_encoding("cl100k_base")
        tiktoken_model = model_mapping.get(model, model)
        return tiktoken.encoding_for_model(tiktoken_model)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text, model=None):
    """ Get the number of tokens for a string, measured using tiktoken. """

    try:
        model = model or "gpt-4o"
        if isinstance(model, str):
            tokenizer = get_tokenizer(model)
        else:
            # Assume model is a namedtuple (model_name, tokenizer)
            tokenizer = model.tokenizer
    except:
        model = "gpt-4o"
        if isinstance(model, str):
            tokenizer = get_tokenizer(model)
        else:
            # Assume model is a namedtuple (model_name, tokenizer)
            tokenizer = model.tokenizer
        

    return len(tokenizer.encode(text))

@retry(
    reraise=True,
    stop=stop_after_attempt(1000),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=(
        retry_if_exception_type(openai.APIError)
        | retry_if_exception_type(openai.APIConnectionError)
        | retry_if_exception_type(openai.RateLimitError)
    ),
)
def call_gpt(model, **kwargs):
    kwargs["temperature"] = 0.0
    kwargs["top_p"] = 1
    kwargs["frequency_penalty"] = 0.0
    kwargs["presence_penalty"] = 0.0
    kwargs["timeout"] = 4*10*60  # 40 minutes
    kwargs["model"] = model

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as e:
        print(e)
        raise e

    return response


# @retry(
#     reraise=True,
#     stop=stop_after_attempt(1000),
#     wait=wait_exponential(multiplier=1, min=4, max=10),
#     retry=(
#         retry_if_exception_type(openai.Timeout)
#     ),
# )
# def llm_gpt(prompt, model="gpt-3.5-turbo", n=1, **kwargs):
#     response = call_gpt(model=model, messages=[{"role": "user", "content": prompt}], n=n, **kwargs)

#     if n == 1:
#         choice = response.choices[0]
#         output = choice.message.content.strip()
#     else:
#         output = []
#         for choice in response.choices:
#             output.append(choice.message.content.strip())

#     return output


@retry(
    reraise=True,
    stop=stop_after_attempt(1000),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=(
        retry_if_exception_type(openai.Timeout)
    ),
)
def llm_gpt(prompt, model="meta-llama/llama-3.1-8b-instruct", n=1, pbar=None, **kwargs):
    # 如果有进度条，更新状态
    if pbar:
        pbar.set_postfix_str("Calling OpenRouter...")
    
    response = call_gpt(model=model, messages=[{"role": "user", "content": prompt}], n=n, **kwargs)

    if n == 1:
        choice = response.choices[0]
        output = choice.message.content.strip()
    else:
        output = []
        for choice in response.choices:
            output.append(choice.message.content.strip())

    # 如果有进度条，清除状态
    if pbar:
        pbar.set_postfix_str("")

    return output

def stream_llm_gpt(prompt, model="meta-llama/llama-3.1-8b-instruct", **kwargs):
    messages = [{"role": "user", "content": prompt}]

    response = ""
    while True:
        try:

            stream = call_gpt(stream=True, model=model, messages=messages, **kwargs)
            pbar = tqdm(stream, unit="token", total=kwargs.get("max_tokens", 8*1024), leave=False)
            for chunk in pbar:
                time.sleep(0.01)  # Should help with Errno 104: Connection reset by peer https://stackoverflow.com/questions/383738/104-connection-reset-by-peer-socket-error-or-when-does-closing-a-socket-resu
                chunk_content = chunk.choices[0].delta.content

                if chunk_content:
                    response += chunk_content
                    pbar.set_postfix_str(f"...{response[-70:]!r}")

                    nb_tokens = count_tokens(chunk_content)
                    pbar.update(nb_tokens)
            else:
                pbar.close()
                break

        except (openai.APITimeoutError, openai.APIError, ChunkedEncodingError, ReadError, RemoteProtocolError) as e:
            if isinstance(e, openai.APIError):
                print("*****", e.type)
                if "An error occurred during streaming" not in e.message:
                    raise e

            # Append the response we received so far to messages.
            if len(messages) == 1:
                messages.append({"role": "assistant", "content": response})

            messages[-1] = {"role": "assistant", "content": response}
            print(e)

    return response


def load_program(filename):
    with open(filename, 'r') as f:
        program = f.read()

    return program


def extract_python_code(raw_response):
    # Postprocess response, keep only the code chunks between "```" and "```"
    # Iterate over all code chunks and return the biggest.
    code = ""
    code_chunks = raw_response.split("```")
    for i in range(1, len(code_chunks), 2):
        code_chunk = code_chunks[i]
        if code_chunk.startswith("python\n"):
            code_chunk = code_chunk[7:]

        if len(code_chunk) > len(code):
            code = code_chunk

    return code


def get_empty_metrics():
    return {
        "validity": {
            "TextGame": False,
            "runnable": False,
            "winnable": False,
            "getTaskDescription": False,
            "generatePossibleActions": False,
            "step": False, # has the member function step
            "calculateScore": False,
            "num_valid_actions": 0,
            "error_msg": '',
        },
        "compliance": {
            "fold": "",
            "experiment": "",
            "passed": False,
            "response_msg": ''
        },
        "winnability": {
            "gpt_done": False,
            "gpt_bug": False,
            "num_actions": 0,
            "score": 0,
            "game_won": False,
            "done": False,
            "step": 0,
            "max_steps": 0,
            "history": [],
            "transcript": "",
            "init_prompt": "",
        },
        "alignment": {
            "score": 0,
            "error_msg": "",
            "evaluations": [],
        },
    }
