from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List

from langchain_core.documents import Document

from .base import WebSearch

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None


class TavilySearch(WebSearch):
    """
    Implementação de WebSearch usando Tavily como fonte.

    Subclasses devem definir:
      - description: str
      - tavily_api_key: str  (fallback: env TAVILY_API_KEY)

    Opcionais:
      - max_web_results: int = 5
      - storage: Optional[RAG] = None  — se definido, persiste resultados automaticamente

    Exemplo básico (sem cache):
        class QuickSearch(TavilySearch):
            description = "Busca rápida na web."
            tavily_api_key = os.getenv("TAVILY_API_KEY")

    Exemplo com cache em Weaviate:
        class Research(TavilySearch):
            description = "Pesquisa com cache."
            tavily_api_key = os.getenv("TAVILY_API_KEY")
            storage = MyWeaviateRAG()

    Exemplo com cache em Ragie:
        class Research(TavilySearch):
            description = "Pesquisa com cache Ragie."
            tavily_api_key = os.getenv("TAVILY_API_KEY")
            storage = MyRagieRAG()
    """

    tavily_api_key: str = ""

    def __init__(self):
        if TavilyClient is None:
            raise ImportError(
                "Instale o pacote Tavily: pip install tavily-python"
            )

        resolved_key = getattr(self, "tavily_api_key", None) or os.getenv("TAVILY_API_KEY")
        if not resolved_key:
            raise ValueError(
                f"tavily_api_key não definida em {self.__class__.__name__} "
                f"e TAVILY_API_KEY não encontrada no ambiente"
            )

        self._client = TavilyClient(api_key=resolved_key)

        if not getattr(self, "name", None):
            self.name = self.__class__.__name__

        super().__init__()  # resolve self.storage se for classe

    def fetch(self, query: str) -> List[Document]:
        """
        Busca na web via Tavily.

        Se `storage` estiver configurado, persiste os resultados automaticamente
        usando IDs determinísticos por URL para evitar duplicatas.
        """
        max_results = getattr(self, "max_web_results", 5)

        response = self._client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=True,
        )

        results = response.get("results", [])
        answer = response.get("answer", "")

        docs: List[Document] = []
        texts_to_store: List[str] = []
        metas_to_store: List[Dict[str, Any]] = []
        ids_to_store: List[str] = []

        if answer:
            doc = Document(
                page_content=f"Resumo AI: {answer}",
                metadata={"source": "tavily_answer", "query": query},
            )
            docs.append(doc)
            texts_to_store.append(doc.page_content)
            metas_to_store.append(doc.metadata)
            ids_to_store.append(str(uuid.uuid5(uuid.NAMESPACE_URL, f"tavily_answer:{query}")))

        for res in results:
            content = res.get("content", "")
            url = res.get("url", "")
            title = res.get("title", "")
            if not content:
                continue

            doc = Document(
                page_content=f"Title: {title}\nURL: {url}\nContent: {content}",
                metadata={"source": "tavily", "url": url, "title": title, "query": query},
            )
            docs.append(doc)
            texts_to_store.append(doc.page_content)
            metas_to_store.append(doc.metadata)
            ids_to_store.append(
                str(uuid.uuid5(uuid.NAMESPACE_URL, url)) if url else str(uuid.uuid4())
            )

        if self.storage and texts_to_store:
            self.storage.write(
                texts=texts_to_store,
                metadatas=metas_to_store,
                source_ids=ids_to_store,
            )

        return docs
