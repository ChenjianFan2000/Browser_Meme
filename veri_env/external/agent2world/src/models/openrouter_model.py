from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Type, Union

from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel

from src.messages import OpenAIMessage
from src.models.base import BaseModelBackend
from src.configs.models import ChatGPTConfig
from src.types import ModelType
from src.utils.token_counter import BaseTokenCounter, OpenAITokenCounter


class OpenRouterModel(BaseModelBackend):
    r"""OpenRouter API in a unified BaseModelBackend interface.
    
    OpenRouter is compatible with OpenAI API but uses different authentication
    and base URL.

    Args:
        model_type (Union[ModelType, str]): Model for which a backend is
            created.
        model_config_dict (Optional[Dict[str, Any]], optional): A dictionary
            that will be fed into the chat completion API. If :obj:`None`, 
            :obj:`ChatGPTConfig().as_dict()` will be used. (default: :obj:`None`)
        api_key (Optional[str], optional): The API key for authenticating
            with the OpenRouter service. (default: :obj:`None`)
        url (Optional[str], optional): The url to the OpenRouter service.
            (default: :obj:`None`)
        token_counter (Optional[BaseTokenCounter], optional): Token counter to
            use for the model. If not provided, :obj:`OpenAITokenCounter` will
            be used. (default: :obj:`None`)
        timeout (Optional[float], optional): The timeout value in seconds for
            API calls. (default: :obj:`None`)
    """

    def __init__(
        self,
        model_type: Union[ModelType, str],
        model_config_dict: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        token_counter: Optional[BaseTokenCounter] = None,
        timeout: Optional[float] = None,
    ) -> None:
        if model_config_dict is None:
            model_config_dict = ChatGPTConfig().as_dict()
        
        # OpenRouter specific environment variables
        api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        url = url or os.environ.get("OPENROUTER_API_BASE_URL")
        timeout = timeout or float(os.environ.get("MODEL_TIMEOUT", 180))

        super().__init__(
            model_type, model_config_dict, api_key, url, token_counter, timeout
        )

        self._client = OpenAI(
            timeout=self._timeout,
            max_retries=3,
            base_url=self._url,
            api_key=self._api_key,
        )
        self._async_client = AsyncOpenAI(
            timeout=self._timeout,
            max_retries=3,
            base_url=self._url,
            api_key=self._api_key,
        )

    @property
    def token_counter(self) -> BaseTokenCounter:
        r"""Initialize the token counter for the model backend.

        Returns:
            BaseTokenCounter: The token counter following the model's
                tokenization style.
        """
        if not self._token_counter:
            self._token_counter = OpenAITokenCounter(self.model_type)
        return self._token_counter

    def _run(
        self,
        messages: List[OpenAIMessage],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[Any]:
        r"""Runs inference of OpenRouter chat completion.

        Args:
            messages (List[OpenAIMessage]): Message list with the chat history
                in OpenAI API format.
            response_format (Optional[Type[BaseModel]]): The format of the
                response.
            tools (Optional[List[Dict[str, Any]]]): The schema of the tools to
                use for the request.

        Returns:
            Union[ChatCompletion, Stream[ChatCompletionChunk]]:
                `ChatCompletion` in the non-stream mode, or
                `Stream[ChatCompletionChunk]` in the stream mode.
        """
        response_format = response_format or self.model_config_dict.get(
            "response_format", None
        )
        if response_format:
            return self._request_parse(messages, response_format, tools)
        else:
            return self._request_chat_completion(messages, tools)

    async def _arun(
        self,
        messages: List[OpenAIMessage],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[Any]:
        r"""Runs inference of OpenRouter chat completion in async mode.

        Args:
            messages (List[OpenAIMessage]): Message list with the chat history
                in OpenAI API format.
            response_format (Optional[Type[BaseModel]]): The format of the
                response.
            tools (Optional[List[Dict[str, Any]]]): The schema of the tools to
                use for the request.

        Returns:
            Union[ChatCompletion, AsyncStream[ChatCompletionChunk]]:
                `ChatCompletion` in the non-stream mode, or
                `AsyncStream[ChatCompletionChunk]` in the stream mode.
        """
        response_format = response_format or self.model_config_dict.get(
            "response_format", None
        )
        if response_format:
            return await self._arequest_parse(messages, response_format, tools)
        else:
            return await self._arequest_chat_completion(messages, tools)

    def _request_chat_completion(
        self,
        messages: List[OpenAIMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[Any]:
        import copy

        request_config = copy.deepcopy(self.model_config_dict)

        if tools:
            request_config["tools"] = tools

        return self._client.chat.completions.create(
            messages=messages,
            model=self.model_type,
            **request_config,
        )

    async def _arequest_chat_completion(
        self,
        messages: List[OpenAIMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[Any]:
        import copy

        request_config = copy.deepcopy(self.model_config_dict)

        if tools:
            request_config["tools"] = tools

        return await self._async_client.chat.completions.create(
            messages=messages,
            model=self.model_type,
            **request_config,
        )

    def _request_parse(
        self,
        messages: List[OpenAIMessage],
        response_format: Type[BaseModel],
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        import copy

        request_config = copy.deepcopy(self.model_config_dict)

        # OpenRouter doesn't support the parse method, so we use regular completion
        # with response_format and then manually parse the result
        schema = response_format.model_json_schema()
        props = schema.get("properties", {})
        schema["type"] = schema.get("type", "object")
        schema["required"] = list(props.keys())
        request_config["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": response_format.__name__,
                "schema": schema,
                "strict": True
            }
        }

        request_config.pop("stream", None)
        
        # 只有当 tools 不为 None 且不为空时才传递
        if tools:
            request_config["tools"] = tools

        # Use regular completions.create instead of parse
        try:
            response = self._client.chat.completions.create(
                messages=messages,
                model=self.model_type,
                **request_config,
            )
        except Exception:
            rf = request_config.pop("response_format", None)
            response = self._client.chat.completions.create(
                messages=messages,
                model=self.model_type,
                **request_config,
            )
        
        # Manually parse the response content
        if response.choices and response.choices[0].message.content:
            try:
                import json
                parsed_content = json.loads(response.choices[0].message.content)
                parsed_obj = response_format(**parsed_content)
                
                # Add the parsed object to the response
                response.choices[0].message.parsed = parsed_obj
            except (json.JSONDecodeError, ValueError) as e:
                # If parsing fails, leave parsed as None
                response.choices[0].message.parsed = None
        
        return response

    async def _arequest_parse(
        self,
        messages: List[OpenAIMessage],
        response_format: Type[BaseModel],
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        import copy

        request_config = copy.deepcopy(self.model_config_dict)

        # OpenRouter doesn't support the parse method, so we use regular completion
        # with response_format and then manually parse the result
        schema = response_format.model_json_schema()
        props = schema.get("properties", {})
        schema["type"] = schema.get("type", "object")
        schema["required"] = list(props.keys())
        request_config["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": response_format.__name__,
                "schema": schema,
                "strict": True
            }
        }

        # Remove stream from request config since structured response
        # may not support streaming
        request_config.pop("stream", None)
        
        # 只有当 tools 不为 None 且不为空时才传递
        if tools:
            request_config["tools"] = tools

        # Use regular completions.create instead of parse
        try:
            response = await self._async_client.chat.completions.create(
                messages=messages,
                model=self.model_type,
                **request_config,
            )
        except Exception:
            rf = request_config.pop("response_format", None)
            response = await self._async_client.chat.completions.create(
                messages=messages,
                model=self.model_type,
                **request_config,
            )
        
        # Manually parse the response content
        if response.choices and response.choices[0].message.content:
            try:
                import json
                parsed_content = json.loads(response.choices[0].message.content)
                parsed_obj = response_format(**parsed_content)
                
                # Add the parsed object to the response
                response.choices[0].message.parsed = parsed_obj
            except (json.JSONDecodeError, ValueError) as e:
                # If parsing fails, leave parsed as None
                response.choices[0].message.parsed = None
        
        return response

    def check_model_config(self):
        r"""Check whether the model configuration contains any
        unexpected arguments to OpenRouter API.
        
        Note: OpenRouter is generally compatible with OpenAI API parameters.
        """
        # OpenRouter is generally compatible with OpenAI API
        # We can use the same parameter validation as OpenAI
        from src.configs.models import OPENAI_API_PARAMS
        
        for param in self.model_config_dict:
            if param not in OPENAI_API_PARAMS:
                raise ValueError(
                    f"Unexpected argument `{param}` is "
                    "input into OpenRouter model backend."
                )

    @property
    def stream(self) -> bool:
        r"""Returns whether the model is in stream mode, which sends partial
        results each time.

        Returns:
            bool: Whether the model is in stream mode.
        """
        return self.model_config_dict.get('stream', False)