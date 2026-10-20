from setuptools import setup

setup(name='openai-hf-interface',
      version='0.0.1',
      author='Top Piriyakulkij',
      packages=['openai_hf_interface'],
      description="A simple interface implementation that aligns Huggingface's Transformers interface with OpenAI's API.",
      license='MIT',
      install_requires=[
        'openai>=1.0',
        'sqlalchemy',
        'tiktoken',
        'numpy'
      ],
)