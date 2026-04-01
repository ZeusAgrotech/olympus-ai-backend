from llm.llm import BaseLLM


class Gpt5MiniLLM(BaseLLM):
    model_name = "gpt-5-mini"
    provider = "openai"
    env_key = "OPENAI_API_KEY"
    passthrough = False  # uso interno apenas
