"""
Classe base para definição declarativa de LLMs na plataforma Olympus AI.

Cada subclasse representa um modelo disponível. O simples ato de criá-la
a registra automaticamente no REGISTRY global e, se passthrough=True e
hide=False, também a expõe como endpoint direto no servidor.

Uso:
    class Gpt54LLM(BaseLLM):
        model_name  = "gpt-5.4"
        provider    = "openai"
        env_key     = "OPENAI_API_KEY"
        passthrough = True   # expõe como endpoint /v1/chat/completions
        hide        = False  # visível via passthrough (True = só uso interno)
"""

import os
import time
from functools import lru_cache
from typing import Any, Dict, Iterator, List, Optional, Type

import tiktoken
from langchain_core.language_models.chat_models import BaseChatModel


# ---------------------------------------------------------------------------
# Registry global: model_name → BaseLLM class
# ---------------------------------------------------------------------------

REGISTRY: Dict[str, Type["BaseLLM"]] = {}


# ---------------------------------------------------------------------------
# Parâmetros de geração repassados ao provider no modo passthrough
# ---------------------------------------------------------------------------

_PASSTHROUGH_PARAMS = (
    "temperature",
    "top_p",
    "max_tokens",
    "frequency_penalty",
    "presence_penalty",
    "stop",
    "seed",
    "logprobs",
    "top_logprobs",
    "n",
    "user",
)


@lru_cache(maxsize=32)
def _get_tiktoken_encoding(model_name: str):
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


# ---------------------------------------------------------------------------
# BaseLLM
# ---------------------------------------------------------------------------

class BaseLLM:
    """
    Classe base declarativa para LLMs.

    Atributos obrigatórios:
        model_name  (str)  — nome exato do modelo no provider
        provider    (str)  — "openai" | "google" | "anthropic"
        env_key     (str)  — variável de ambiente com a API key

    Atributos opcionais:
        passthrough (bool) — se True, expõe como endpoint direto
        hide        (bool) — se True, bloqueia o registro passthrough
                             mesmo que passthrough=True (uso interno apenas)
    """

    model_name: str = ""
    provider: str = ""
    env_key: str = ""
    passthrough: bool = False
    hide: bool = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        if not getattr(cls, "model_name", ""):
            raise TypeError(f"{cls.__name__}: 'model_name' é obrigatório")
        if not getattr(cls, "provider", ""):
            raise TypeError(f"{cls.__name__}: 'provider' é obrigatório")
        if not getattr(cls, "env_key", ""):
            raise TypeError(f"{cls.__name__}: 'env_key' é obrigatório")

        REGISTRY[cls.model_name] = cls

    @classmethod
    def build(cls, **kwargs: Any) -> BaseChatModel:
        """
        Instancia o LangChain model correspondente ao provider declarado.
        Usado pelos agents LangChain (Athena, Saori, etc).
        """
        api_key = os.getenv(cls.env_key)

        if cls.provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model_name=cls.model_name, openai_api_key=api_key, **kwargs)

        if cls.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=cls.model_name, google_api_key=api_key, **kwargs)

        if cls.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=cls.model_name, anthropic_api_key=api_key, **kwargs)

        raise ValueError(
            f"{cls.__name__}: provider '{cls.provider}' não suportado. "
            "Use: 'openai', 'google' ou 'anthropic'."
        )


# ---------------------------------------------------------------------------
# PassthroughProxy
# ---------------------------------------------------------------------------

class PassthroughProxy:
    """
    Proxy direto para um provider de LLM via SDK oficial (sem LangChain).

    Criado automaticamente pelo llm/__init__.py para cada BaseLLM com
    passthrough=True e hide=False. Registrado no servidor como hidden=True
    (acessível via /v1/chat/completions mas invisível no GET /v1/models).

    Suporta todos os parâmetros padrão OpenAI: temperature, top_p,
    max_tokens, frequency_penalty, presence_penalty, stop, seed, etc.
    """

    def __init__(self, llm_cls: Type[BaseLLM]) -> None:
        self._llm_cls = llm_cls
        self.name = llm_cls.model_name
        self.hidden = True          # nunca aparece em GET /v1/models
        self.model_aliases: List[str] = []
        self.owned_by: str = "zeus"
        self.created: int = int(time.time())

        # self-ref para Server._resolve_model_token_counter
        # que espera agent.model._count_tokens
        self.model = self

        from openai import OpenAI
        self._client = OpenAI(api_key=os.getenv(llm_cls.env_key))

    # ------------------------------------------------------------------
    # Extração de parâmetros de geração
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_params(request_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not request_data:
            return {}
        return {
            key: request_data[key]
            for key in _PASSTHROUGH_PARAMS
            if key in request_data and request_data[key] is not None
        }

    # ------------------------------------------------------------------
    # Chat (não-streaming)
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        params = self._extract_params(request_data)
        response = self._client.chat.completions.create(
            model=self.name,
            messages=messages,
            **params,
        )
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Chat (streaming)
    # ------------------------------------------------------------------

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
    ) -> Iterator[str]:
        params = self._extract_params(request_data)
        stream = self._client.chat.completions.create(
            model=self.name,
            messages=messages,
            stream=True,
            **params,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    # ------------------------------------------------------------------
    # Contagem de tokens (tiktoken)
    # ------------------------------------------------------------------

    def _count_tokens(self, text: str) -> int:
        if not text:
            return 0
        encoding = _get_tiktoken_encoding(self.name)
        return len(encoding.encode(text, disallowed_special=()))
