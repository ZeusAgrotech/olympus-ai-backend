from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document

from .base import RAG, TypeAccess


class RagieRAG(RAG):
    """
    Implementação RAG usando Ragie como backend gerenciado.

    O Ragie cuida de chunking, embeddings e indexação automaticamente —
    não é necessário configurar embeddings ou vector store localmente.

    Subclasses devem definir:
      - description: str
      - partition: str   — nome da partição no Ragie (equivalente a uma coleção)

    Opcionais:
      - api_key: str          — chave da API (fallback: env RAGIE_API_KEY)
      - type_access: TypeAccess = TypeAccess.READ
      - max_query_results: int = 5
      - rerank: bool = False  — ativa reranking nativo do Ragie na retrieval

    Exemplo de uso:
        class KnowledgeBase(RagieRAG):
            description = "Base de conhecimento técnico."
            partition = "knowledge-base"
    """

    partition: str = ""
    api_key: str = ""
    type_access: TypeAccess = TypeAccess.READ
    max_query_results: int = 5
    rerank: bool = False

    def __init__(self, *, name: Optional[str] = None, k: Optional[int] = None):
        try:
            from ragie import Ragie
        except ImportError:
            raise ImportError(
                "Instale o pacote Ragie: pip install ragie"
            )

        if not getattr(self, "description", None):
            raise ValueError(f"description não definida em {self.__class__.__name__}")
        if not getattr(self, "partition", None):
            raise ValueError(f"partition não definida em {self.__class__.__name__}")

        resolved_key = getattr(self, "api_key", None) or os.getenv("RAGIE_API_KEY")
        if not resolved_key:
            raise ValueError(
                f"api_key não definida em {self.__class__.__name__} e RAGIE_API_KEY não encontrada no ambiente"
            )

        if k is not None:
            self.max_query_results = k
        if name is not None:
            self.name = name
        if not getattr(self, "name", None):
            self.name = self.__class__.__name__

        self._client = Ragie(auth=resolved_key)

    # ------------------------------------------------------------------
    # Interface RAG
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        k: Optional[int] = None,
    ) -> List[Document]:
        """Retrieval semântico via Ragie."""
        top_k = k or self.max_query_results

        request: Dict[str, Any] = {
            "query": query,
            "top_k": top_k,
            "partition": self.partition,
        }
        if self.rerank:
            request["rerank"] = True

        response = self._client.retrievals.retrieve(request=request)

        docs = []
        for chunk in response.scored_chunks:
            chunk_metadata = getattr(chunk, "metadata", None) or {}
            metadata = {
                "document_id": chunk.document_id,
                "document_name": getattr(chunk, "document_name", None),
                "score": chunk.score,
                "start_page": chunk_metadata.get("start_page"),
                "end_page": chunk_metadata.get("end_page"),
                "start_time": chunk_metadata.get("start_time"),
                "end_time": chunk_metadata.get("end_time"),
                **(chunk.document_metadata or {}),
                **chunk_metadata,
            }
            docs.append(Document(page_content=chunk.text, metadata=metadata))

        return docs

    def write(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        source_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Ingere textos no Ragie como documentos raw.

        O Ragie realiza chunking e indexação automaticamente.
        Se `source_ids` for fornecido, é usado como `external_id` para deduplicação.
        """
        if metadatas is None:
            metadatas = [{} for _ in texts]

        ids = []
        for i, (text, meta) in enumerate(zip(texts, metadatas)):
            params: Dict[str, Any] = {
                "content": text,
                "partition": self.partition,
                "metadata": meta,
            }
            if source_ids and i < len(source_ids):
                params["external_id"] = source_ids[i]

            doc = self._client.documents.create_raw(request=params)
            ids.append(doc.id)

        return ids

    def as_tool(self, name=None, description=None, k=None):
        return super().as_tool(
            name=name,
            description=description,
            k=k,
            type_access=getattr(self, "type_access", TypeAccess.READ),
        )
