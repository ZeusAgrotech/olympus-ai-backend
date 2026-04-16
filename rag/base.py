from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from langchain_core.documents import Document
from langchain_core.tools import StructuredTool


class TypeAccess(Enum):
    READ = "read"
    WRITE = "write"
    ALL = "all"


class RAG(ABC):
    """
    Interface base para backends de RAG (Retrieval-Augmented Generation).

    Toda implementação concreta deve definir:
      - description: str
      - name: str  (opcional — usa o nome da classe se omitido)

    E implementar os métodos abstratos:
      - search(query, *, k=None) -> List[Document]
      - write(texts, metadatas=None, source_ids=None) -> List[str]
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def search(
        self,
        query: str,
        *,
        k: Optional[int] = None,
    ) -> List[Document]:
        """Busca semântica na coleção. Retorna documentos relevantes."""
        ...

    @abstractmethod
    def write(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        source_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Indexa textos na coleção.

        Args:
            texts:      Lista de textos a salvar.
            metadatas:  Metadados por texto (opcional).
            source_ids: IDs de fonte para deduplicação (opcional).

        Returns:
            Lista de IDs gerados/usados.
        """
        ...

    def as_retriever(self, *, k: Optional[int] = None):
        """
        Retorna um callable compatível com LangChain retriever.
        Backends concretos podem sobrescrever para retornar o retriever nativo.
        """
        def _retrieve(query: str) -> List[Document]:
            return self.search(query, k=k)
        return _retrieve

    def as_tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        k: Optional[int] = None,
        type_access: TypeAccess = TypeAccess.READ,
    ) -> StructuredTool:
        """
        Expõe este backend como uma LangChain StructuredTool.

        O acesso (leitura/escrita/ambos) é controlado por `type_access`.
        Backends concretos podem sobrescrever para adicionar parâmetros extras (ex: search_depth).
        """
        can_read = type_access in (TypeAccess.READ, TypeAccess.ALL)
        can_write = type_access in (TypeAccess.WRITE, TypeAccess.ALL)
        rag_instance = self

        def _rag_wrapper(
            query: Optional[str] = None,
            text_to_save: Optional[str] = None,
            metadata: Optional[Dict[str, Any]] = None,
        ) -> Union[str, List[Dict[str, Any]]]:
            if can_write and text_to_save:
                rag_instance.write(texts=[text_to_save], metadatas=[metadata or {}])
                return f"Informação salva com sucesso: '{text_to_save}'"
            if text_to_save and not can_write:
                return "Erro: Esta ferramenta não tem permissão de escrita."

            if can_read and query:
                docs = rag_instance.search(query, k=k)
                return [{"page_content": d.page_content, "metadata": d.metadata} for d in docs]
            if query and not can_read:
                return "Erro: Esta ferramenta não tem permissão de leitura."

            hints = []
            if can_read:
                hints.append("`query` para buscar")
            if can_write:
                hints.append("`text_to_save` para salvar")
            return f"Erro: Forneça {' ou '.join(hints)}." if hints else "Erro: sem operações configuradas."

        return StructuredTool.from_function(
            func=_rag_wrapper,
            name=name or self.name or self.__class__.__name__,
            description=description or self.description,
        )
