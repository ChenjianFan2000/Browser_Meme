import os
import re
from dotenv import load_dotenv

import openai
import requests
import time
import random
import json
from typing import Dict, List, Union, Any
from retry import retry
import base64
from openai import OpenAI
from PIL import Image
from io import BytesIO

load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")
OPENAI_API_TYPE = os.environ.get("OPENAI_API_TYPE", "openai")

# 你可以按你项目的习惯放到配置文件里
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_WS_ID = os.getenv("DEEPSEEK_WS_ID", "")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
)

@retry(tries=3, backoff=3, max_delay=60)
def call_llm(
    text,
    system_prompt=(
        "You are a helpful and knowledgeable AI assistant. Provide accurate, "
        "concise, and relevant responses based on the user's instructions. "
        "Maintain a polite and neutral tone, and do not add any information "
        "beyond what is asked."
    ),
    model="deepseek-chat",   # ✅ 官方推荐：非思考
    # model="deepseek-reasoner",  # ✅ 官方推荐：思考版（你可以按需切换）
    max_tokens=120,
    temperature=0.3,
):
    """
    Call DeepSeek OpenAI-compatible API.

    Args:
        text (str): The input text to process
        system_prompt (str): The system prompt to use
        model (str): DeepSeek model name, e.g. "deepseek-chat" or "deepseek-reasoner"
        max_tokens (int): Maximum tokens in the response
        temperature (float): Temperature for response generation
        api_key (str, optional): If None, uses DEEPSEEK_API_KEY env var
        base_url (str, optional): If None, uses DEEPSEEK_BASE_URL env var/default
        timeout (int/float): requests timeout

    Returns:
        str: The model's response text
    """
    llm_client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
    )
    try:
        response = llm_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"API Call Error: {e}")
        return None


def encode_image_to_base64(image_data: Image.Image) -> str:
    """
    Encodes a PIL Image object to a Base64 string.
    """
    try:
        buffered = BytesIO()
        # You need to specify the format when saving to BytesIO.
        # JPEG is generally a good choice for vision models due to compression.
        # You might want to infer format from original source or choose based on quality needs.
        image_data.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Error encoding image to Base64: {e}")

@retry(tries=3, backoff=3, max_delay=60)
def image_llm(
    user_prompt: str,
    image: Image.Image,
    system_prompt: str = "You are a helpful AI assistant with vision. Provide concise, accurate answers based on the image(s) and the user’s question.",
    model: str = "gpt-4o",  # Changed to gpt-4o as gpt-4o-vision-preview is often just 'gpt-4o' now or specific versions.
    max_tokens: int = 120,
    temperature: float = 0.3
) -> str:
    """
    Sends a user prompt and image(s) to OpenAI's vision-enabled model for analysis.

    Args:
        user_prompt (str): The text prompt from the user.
        image_paths (List[str]): A list of local file paths to the images.
        system_prompt (str): The system prompt to guide the AI's behavior.
        model (str): The OpenAI model to use (e.g., "gpt-4o").
        max_tokens (int): The maximum number of tokens for the AI's response.
        temperature (float): Controls the randomness of the output.

    Returns:
        str: The AI's response.

    Raises:
        FileNotFoundError: If any of the image files are not found.
        IOError: If there's an error reading or encoding an image.
        openai.OpenAIError: For API-related errors from OpenAI.
    """
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    messages_content: List[Dict[str, Any]] = []

    # Add system prompt
    messages_content.append({"type": "text", "text": system_prompt})

    # Add user prompt
    user_message_content: List[Dict[str, str]] = []
    user_message_content.append({"type": "text", "text": user_prompt})

    # Add images by encoding them to Base64
    base64_image = encode_image_to_base64(image)
    user_message_content.append({
        "type": "image_url",
        "image_url": {
            "url": f"data:image/jpeg;base64,{base64_image}"
        },
    })

    messages = [
        {"role": "user", "content": user_message_content},
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content
    except openai.APIError as e:
        print(f"OpenAI API error: {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise

@retry(openai.APIConnectionError, tries=3, backoff=3, max_delay=60)
def call_embedding(
    inputs: Union[str, List[str]],
    model: str = "openai/text-embedding-3-large",
) -> List[List[float]]:
    if isinstance(inputs, str):
        payload = [inputs]
    else:
        payload = inputs

    try:
        response = client.embeddings.create(
            model=model,
            input=payload,
        )
        return [item.embedding for item in response.data]

    except Exception:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {"model": model, "input": payload}
        resp = requests.post(
            f"{OPENROUTER_BASE_URL}/embeddings",
            headers=headers,
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data.get("data", [])]

@retry(openai.APIConnectionError, tries=3, backoff=3, max_delay=60)
def call_llm_dp(
    text: str,
    system_prompt: str = "Summarize the following in 2 short sentences:",
    model: str = "DeepSeekV3-0324-SGL-nj",
    max_tokens: int = 16384,
    temperature: float = 0.3,
) -> str:
    """
    Call DeepSeek / HunYuan chat-completion endpoint (OpenAI-compatible).
    Args:
        text (str): The input text to process
        system_prompt (str): The system prompt to use
        model (str): The model to use
        max_tokens (int): Maximum tokens in the response
        temperature (float): Temperature for response generation
       
    Returns:
        The assistant's reply extracted from the JSON response.
    """
    if not DEEPSEEK_API_KEY or not DEEPSEEK_WS_ID:
        raise ValueError("Missing DEEPSEEK_API_KEY or DEEPSEEK_WS_ID")
    url = (
        "http://stream-server-offline-10274.turbotke.production.polaris:81"
        "/openapi/chat/completions"
    )

    # Mandatory headers for authentication + workspace ID
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Wsid": DEEPSEEK_WS_ID,
    }

    # Unique query ID helps the backend with tracking / debugging
    query_id = f"{int(time.time() * 1000)}{random.randint(0, 9999)}"

    payload: Dict = {
        "query_id": query_id,
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": text},
        ],
        "model_type": "hunyuan",
        "temperature": temperature,
        "top_p": 1,
        "top_k": 40,
        "output_seq_len": max_tokens,
        "max_input_seq_len": max_tokens,    
        "repetition_penalty": 1,
        "debug_level": 0,
        "stream": False,
        "random_seed": 5610,
        "debug_flag": 0,
        "compatible_with_openai": True,
        "stop": ["</answer>", "</function_call>"],
    }

    raw_resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp_content_dict = json.loads(raw_resp.text)

    return resp_content_dict["choices"][0]["message"]["content"]

def extract_code(markdown: str) -> str:
    """
    Extract the contents of all fenced code blocks (```…```) in the input.
    If multiple code blocks are present, they are concatenated with two newlines.
    If no fences are found, returns the original text plus a trailing newline.
    """
    # Matches ```<optional-lang>\n ... ``` (non-greedy)
    pattern = r"```[^\n]*\n(.*?)(?=\n```)"  
    blocks = re.findall(pattern, markdown, re.DOTALL)
    if blocks:
        # strip leading/trailing whitespace on each block and join them
        return "\n\n".join(block.strip() for block in blocks) + "\n"
    # fallback: return whole text
    return markdown.strip() + "\n"
