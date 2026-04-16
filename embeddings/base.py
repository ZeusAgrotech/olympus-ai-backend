from __future__ import annotations

from abc import abstractmethod
from typing import List

from langchain_core.embeddings import Embeddings


class Embedding(Embeddings):
    """
    Interface base para provedores de embedding.

    Estende langchain_core.embeddings.Embeddings para ser compatível com
    qualquer componente LangChain (WeaviateVectorStore, retrievers, etc.).

    Implementações concretas devem criar o cliente do provedor de forma lazy
    — apenas quando embed_query/embed_documents for chamado pela primeira vez,
    nunca no import ou na definição da classe.

    Implementações disponíveis:
      - embeddings.openai.OpenAIEmbedding
    """

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> List[float]: ...
