from llm.llm import BaseLLM


class Gpt54NanoLLM(BaseLLM):
    model_name = "gpt-5.4-nano"
    provider = "openai"
    env_key = "OPENAI_API_KEY"
    passthrough = True
