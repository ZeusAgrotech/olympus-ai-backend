from llm.llm import BaseLLM


class Gpt54MiniLLM(BaseLLM):
    model_name = "gpt-5.4-mini"
    provider = "openai"
    env_key = "OPENAI_API_KEY"
    passthrough = True
    hide = False
