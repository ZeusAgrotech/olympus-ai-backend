from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import weaviate
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.tools import StructuredTool
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_weaviate import WeaviateVectorStore

try:
    from flashrank import Ranker, RerankRequest
except ImportError:
    Ranker = None

from .base import RAG, TypeAccess


class WeaviateRAG(RAG):
    """
    Implementação RAG usando Weaviate como backend vetorial.

    Subclasses devem definir (antes de chamar super().__init__()):
      - description: str
      - collection_name: str
      - embedding: Embeddings

    Opcionais:
      - text_key: str = "content"
      - type_access: TypeAccess = TypeAccess.READ
      - metadata_fields: List[str] = []
      - max_query_results: int = 5
      - chunk_size: int = 1000
      - chunk_overlap: int = 200
      - skip_init_checks: bool = True
      - port: int = 8080
    """

    def __init__(
        self,
        *,
        default_filter: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        k: Optional[int] = None,
    ):
        if not getattr(self, "description", None):
            raise ValueError(f"description não definida em {self.__class__.__name__}")
        if not getattr(self, "collection_name", None):
            raise ValueError(f"collection_name não definida em {self.__class__.__name__}")
        if not getattr(self, "embedding", None):
            raise ValueError(f"embedding não definida em {self.__class__.__name__}")

        if not getattr(self, "text_key", None):
            self.text_key = "content"
        if not getattr(self, "metadata_fields", None):
            self.metadata_fields: List[str] = []
        if not getattr(self, "max_query_results", None):
            self.max_query_results = 5
        if not getattr(self, "default_filter", None):
            self.default_filter: Optional[Dict[str, Any]] = None
        if not getattr(self, "type_access", None):
            self.type_access = TypeAccess.READ
        if getattr(self, "chunk_size", None) is None:
            self.chunk_size = 1000
        if getattr(self, "chunk_overlap", None) is None:
            self.chunk_overlap = 200

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

        if default_filter is not None:
            self.default_filter = default_filter
        if k is not None:
            self.max_query_results = k
        if name is not None:
            self.name = name
        if not getattr(self, "name", None):
            self.name = self.__class__.__name__

        if not getattr(self, "client", None):
            self.client = weaviate.connect_to_local(
                port=getattr(self, "port", 8080),
                skip_init_checks=getattr(self, "skip_init_checks", True),
            )

        self.vectorstore = WeaviateVectorStore(
            client=self.client,
            index_name=self.collection_name,
            text_key=self.text_key,
            embedding=self.embedding,
            attributes=self.metadata_fields,
        )

        self.retriever = self.vectorstore.as_retriever(
            search_kwargs=self._build_search_kwargs()
        )

        self.ranker = Ranker() if Ranker else None

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _build_search_kwargs(
        self,
        *,
        k: Optional[int] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"k": k or self.max_query_results}

        if self.default_filter and where:
            final_filter = {"operator": "And", "operands": [self.default_filter, where]}
        elif where:
            final_filter = where
        elif self.default_filter:
            final_filter = self.default_filter
        else:
            final_filter = None

        if final_filter is not None:
            kwargs["where"] = final_filter

        return kwargs

    # ------------------------------------------------------------------
    # Interface RAG
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        k: Optional[int] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        search_kwargs = self._build_search_kwargs(k=k, where=where)
        return self.vectorstore.similarity_search(query, **search_kwargs)

    def smart_search(
        self,
        query: str,
        search_depth: str = "basic",
        max_k: int = 25,
    ) -> List[Document]:
        """
        Busca adaptativa:
          - basic: busca padrão (k definido no init)
          - deep:  busca ampla + reranking FlashRank → top 10
        """
        if search_depth == "deep":
            fetch_k, final_k, use_rerank = max_k, 10, True
        else:
            fetch_k, final_k, use_rerank = self.max_query_results, self.max_query_results, False

        docs = self.vectorstore.similarity_search(
            query, **self._build_search_kwargs(k=fetch_k)
        )

        if not docs:
            return []

        if use_rerank and self.ranker:
            passages = [
                {"id": getattr(d, "id", str(uuid.uuid4())), "text": d.page_content, "meta": d.metadata}
                for d in docs
            ]
            results = self.ranker.rerank(RerankRequest(query=query, passages=passages))
            final_docs = []
            for res in results[:final_k]:
                d = Document(page_content=res["text"], metadata=res["meta"])
                d.metadata["_rerank_score"] = res["score"]
                final_docs.append(d)
            return final_docs

        return docs[:final_k]

    def write(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        source_ids: Optional[List[str]] = None,
    ) -> List[str]:
        if metadatas is None:
            metadatas = [{} for _ in texts]

        all_texts, all_metadatas, all_ids = [], [], []

        for i, (text, meta) in enumerate(zip(texts, metadatas)):
            chunks = self.text_splitter.create_documents([text], [meta])
            source_id = source_ids[i] if source_ids and i < len(source_ids) else None

            for chunk_index, chunk in enumerate(chunks):
                all_texts.append(chunk.page_content)
                all_metadatas.append(chunk.metadata)

                if source_id:
                    try:
                        namespace = uuid.UUID(source_id)
                    except ValueError:
                        namespace = uuid.uuid5(uuid.NAMESPACE_DNS, source_id)
                    all_ids.append(str(uuid.uuid5(namespace, str(chunk_index))))
                else:
                    all_ids.append(None)

        final_ids = all_ids if any(all_ids) else None
        if final_ids:
            return self.vectorstore.add_texts(texts=all_texts, metadatas=all_metadatas, ids=final_ids)
        return self.vectorstore.add_texts(texts=all_texts, metadatas=all_metadatas)

    def as_retriever(self, *, k: Optional[int] = None, where: Optional[Dict[str, Any]] = None):
        """Retorna o retriever nativo do LangChain/Weaviate."""
        return self.vectorstore.as_retriever(search_kwargs=self._build_search_kwargs(k=k, where=where))

    def as_tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        k: Optional[int] = None,
    ) -> StructuredTool:
        """Sobrescreve para expor o parâmetro search_depth (basic/deep)."""
        can_read = self.type_access in (TypeAccess.READ, TypeAccess.ALL)
        can_write = self.type_access in (TypeAccess.WRITE, TypeAccess.ALL)
        rag_instance = self

        def _wrapper(
            query: Optional[str] = None,
            text_to_save: Optional[str] = None,
            search_depth: str = "basic",
            metadata: Optional[Dict[str, Any]] = None,
        ):
            if can_write and text_to_save:
                rag_instance.write(texts=[text_to_save], metadatas=[metadata or {}])
                return f"Informação salva com sucesso: '{text_to_save}'"
            if text_to_save and not can_write:
                return "Erro: Esta ferramenta não tem permissão de escrita."

            if can_read and query:
                docs = rag_instance.smart_search(query, search_depth=search_depth)
                return [{"page_content": d.page_content, "metadata": d.metadata} for d in docs]
            if query and not can_read:
                return "Erro: Esta ferramenta não tem permissão de leitura."

            hints = []
            if can_read:
                hints.append("`query` para buscar (search_depth='deep' para busca profunda)")
            if can_write:
                hints.append("`text_to_save` para salvar")
            return f"Erro: Forneça {' ou '.join(hints)}." if hints else "Erro: sem operações configuradas."

        return StructuredTool.from_function(
            func=_wrapper,
            name=name or self.name or self.__class__.__name__,
            description=description or self.description,
        )

    def close(self):
        if getattr(self, "client", None):
            self.client.close()
