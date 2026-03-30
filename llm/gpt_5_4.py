from llm.llm import BaseLLM


class Gpt54LLM(BaseLLM):
    model_name = "gpt-5.4"
    provider = "openai"
    env_key = "OPENAI_API_KEY"
    passthrough = True
    hide = False
