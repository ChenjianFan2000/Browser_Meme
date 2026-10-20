# LLM API Prompting Toolkit

This package builds on top of OpenAI API. It provides an easy-to-use prompting interface that:
- performs asynchronous requests
- tracks costs (both hypothetical and actual)
- caches responses

(Originally, this package is supposed to be an interface that aligns Huggingface's Transformers interface with OpenAI's API, hence the name openai-hf-interface)

## Installation

To `import openai_hf_interface` in your project, go to the project's top-level directory and run the following script:

```
git clone https://github.com/topwasu/openai-hf-interface.git
cd openai-hf-interface
pip install -e .
```

## Usage

```
import os
os.environ['OPENAI_API_KEY'] = 'PUT-YOUR-KEY-HERE'
from openai_hf_interface import create_llm, choose_provider

choose_provider('openai') # or choose_provider('openrouter')
llm = create_llm('gpt-4o-2024-08-06')
llm.setup_cache('disk')
prompt1 = 'Who are you?'
prompt2 = ('what is this picture? explain in a single sentence', './example_img/fake_pikachu.jpg')
prompt3 = [('what is this picture? explain in a single setnece', './example_img/fake_pikachu.jpg'),
           'This image depicts a stylized, electrified version of Pikachu with glowing eyes and lightning bolts in the background.',
           'It does not look like Pikachu to me. What is your second guess?']
print(llm.prompt([prompt1, prompt2, prompt3], temperature=0, seed=0))

# Outputs you will get vvv
# Output 1 ==> 'I am an AI language model created by OpenAI, designed to assist with a wide range of questions and tasks by providing information and generating text based on the input I receive. How can I assist you today?', 
# Output 2 ==> 'This image depicts a stylized, electrified version of Pikachu with glowing eyes and lightning bolts in the background.', 
# Output 3 ==> 'This image features a cartoonish, electrified character with large, glowing eyes and lightning bolts, resembling a playful, energetic creature.'
# Note: These three requests were sent to Openai API asynchronously!
"""
```
We also provide asynchronous version of `prompt` as `aprompt`. They work exactly the same -- the latter can be used inside an `async` function.

## Cost tracking

The llm object has a method called `get_info` that will output a dictionary containing various information.
```
print(llm.get_info())
{'input_tokens': 99, 'output_tokens': 319, 'calls': 2, 'actual_input_tokens': 0, 'actual_output_tokens': 0, 'actual_calls': 0, 'cost_per_token': (0.0025, 0.01), 'cost': 0.0034375, 'actual_cost': 0.0}
```

## Caching

We also support in-memory and disk caching. You can can enable caching by calling
```
llm.setup_cache('in_memory')
```
or
```
llm.setup_cache('disk', database_path='path-to-your-database.db')
```
or 
```
llm.setup_cache('disk_to_memory', database_path='path-to-your-database.db')
```

Further explanation for `disk_to_memory`: it is supposed to be use when you have multiple programs accessing the database at the same time, or when your disk is very slow and you have RAM to spare. It keeps the number of reads and writes to disk to the minimum. How it works is it loads the entire database to memory and does further caching as more data comes in in memory. To save that save/update that database to disk, please call `llm.cache.dump_to_disk()` (code for this is optimized to run fast by directly using SQLite commands).


## Setting OpenAI's api key

For convenience, instead of setting the environment variable everytime you run, you can create `secrets.json` in the top-level directory. An example of it is:
```
{
    "openai_api_key": "put-your-key-here",
    "openrouter_api_key": "put-your-key-here"
}
```

## Prompt formatting

Feel free to write your own custom `PromptFormatter` and override the default `PromptFormatter` by calling the method `override_formatter`. Please look at the [formatter file](openai_hf_interface/formatter.py) for more information.

## Feedback

Feel free to open a Github issue for any questions/feedback/issues. Pull request is also welcome!

## License

MIT
