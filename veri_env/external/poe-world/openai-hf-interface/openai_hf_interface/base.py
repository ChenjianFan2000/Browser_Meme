from abc import ABC, abstractmethod

from .cache import InMemoryCache, SQLiteCache


class LLMBase(ABC):
    def __init__(self, model_name, formatter):
        self.model_name = model_name
        self.formatter = formatter
        self.cache_type = None
        self.cache = None
        self.default_kwargs = {}

    @abstractmethod
    def prompt(self, prompts):
        """
        Prompt the LLM

        :param prompts: list of (string or list of strings), the latter is for multi-turn conversation
        """
        pass

    def override_formatter(self, formatter):
        """
        Prompt the LLM

        :param prompts: list of strings only
        """
        self.formatter = formatter

    def setup_cache(self, cache_type, **kwargs):
        self.cache_type = cache_type
        if self.cache_type == 'in_memory':
            self.cache = InMemoryCache()
        elif self.cache_type == 'disk':
            self.cache = SQLiteCache(**kwargs)
        elif self.cache_type == 'disk_to_memory':
            self.cache = SQLiteCache(to_memory=True, **kwargs)
        else:
            raise NotImplementedError

    def lookup_cache(self, prompt, **kwargs):
        if self.cache is None:
            return None
        prompt_str = self.formatter.prompt_to_string(prompt)
        temp = kwargs['temperature'] if 'temperature' in kwargs else 0
        max_tokens = kwargs['max_tokens'] if 'max_tokens' in kwargs else kwargs['max_length'] if 'max_tokens' in kwargs else -1
        stop = kwargs['stop'] if 'stop' in kwargs else []
        seed = kwargs['seed'] if 'seed' in kwargs else -1
        return self.cache.lookup(prompt_str, self.model_name, temp, max_tokens, stop, seed)
    
    def update_cache(self, prompt, n, ret_val, **kwargs):
        if self.cache is None:
            return
        prompt_str = self.formatter.prompt_to_string(prompt)
        temp = kwargs['temperature'] if 'temperature' in kwargs else 0
        max_tokens = kwargs['max_tokens'] if 'max_tokens' in kwargs else kwargs['max_length'] if 'max_tokens' in kwargs else -1
        stop = kwargs['stop'] if 'stop' in kwargs else []
        seed = kwargs['seed'] if 'seed' in kwargs else -1
        self.cache.extend(prompt_str, n, self.model_name, ret_val, temp, max_tokens, stop, seed)

    def set_default_kwargs(self, kwargs):
        if not isinstance(kwargs, dict):
            raise Exception('kwargs must be a dictionary')
        self.default_kwargs = kwargs
