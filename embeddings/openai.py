from __future__ import annotations

import os
from typing import List, Optional

from .base import Embedding


class OpenAIEmbedding(Embedding):
    """
    Embedding via OpenAI, inicializado de forma lazy.

    O cliente OpenAIEmbeddings só é criado quando embed_query/embed_documents
    é chamado pela primeira vez — nunca no import ou na definição da classe.

    Args:
        model:       Nome do modelo (ex: "text-embedding-3-large").
        api_key_env: Variável de ambiente com a chave (default: "OPENAI_API_KEY").

    Exemplo:
        class Library(WeaviateRAG):
            embedding = OpenAIEmbedding("text-embedding-3-large")
    """

    def __init__(self, model: str, api_key_env: str = "OPENAI_API_KEY"):
        self.model = model
        self.api_key_env = api_key_env
        self._client: Optional[object] = None

    def _get_client(self):
        if self._client is None:
            from langchain_openai import OpenAIEmbeddings
            self._client = OpenAIEmbeddings(
                model=self.model,
                openai_api_key=os.getenv(self.api_key_env),
            )
        return self._client

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._get_client().embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._get_client().embed_query(text)

    def __repr__(self) -> str:
        return f"OpenAIEmbedding(model={self.model!r})"
