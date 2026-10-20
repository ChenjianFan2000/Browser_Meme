import requests
from retry import retry
from openai import OpenAI

client = OpenAI(
    api_key="REDACTED",
    base_url="https://openrouter.ai/api/v1",
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
    model="openai/gpt-4.1-mini",
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
    try:
        response = client.chat.completions.create(
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
