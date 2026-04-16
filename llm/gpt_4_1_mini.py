from llm.llm import BaseLLM


class Gpt41MiniLLM(BaseLLM):
    model_name = "gpt-4.1-mini"
    provider = "openai"
    env_key = "OPENAI_API_KEY"
    passthrough = True  # uso interno apenas
