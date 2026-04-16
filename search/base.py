from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_core.tools import StructuredTool

from rag.base import RAG


class WebSearch(ABC):
    """
    Interface base para fontes de busca na web.

    Separada da hierarquia RAG por ser uma fonte de dados, não um banco vetorial.
    Pode ser composta com um RAG para persistir e reutilizar resultados.

    Subclasses devem definir:
      - description: str
      - name: str (opcional)

    Opcionais:
      - storage: Optional[RAG] = None  — backend de armazenamento/cache
      - max_web_results: int = 5
    """

    name: str = ""
    description: str = ""
    storage: Optional[RAG] = None
    max_web_results: int = 5

    def __init__(self):
        """
        Resolve `storage` automaticamente se for uma referência de classe.

        Permite declarar o storage de forma completamente declarativa:
            class Research(TavilySearch):
                storage = _ResearchStore  # classe, não instância

        Subclasses que sobrescrevem __init__ devem chamar super().__init__().
        """
        storage = type(self).__dict__.get("storage") or getattr(self, "storage", None)
        if isinstance(storage, type):
            self.storage = storage()

    @abstractmethod
    def fetch(self, query: str) -> List[Document]:
        """
        Busca informações na web para a query.

        Se `storage` estiver configurado, persiste os resultados automaticamente.
        Retorna os documentos encontrados.
        """
        ...

    def as_tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> List[StructuredTool]:
        """
        Retorna uma lista de LangChain tools:
          1. <name>_WebSearch  — busca na web (sempre presente)
          2. <name>_ReadCache  — leitura do storage/cache (só se storage estiver configurado)

        O padrão recomendado de uso pelo agente:
          1. Consulte o cache primeiro (economiza créditos)
          2. Se não encontrar, busque na web
        """
        base_name = name or self.name or self.__class__.__name__
        tools: List[StructuredTool] = []

        web_tool = StructuredTool.from_function(
            func=self.fetch,
            name=f"{base_name}_WebSearch",
            description=(
                description
                or f"Busca na web sobre um tópico e salva no cache. "
                   f"Use para informações novas ou atualizadas. (Custo: créditos da API)"
            ),
        )
        tools.append(web_tool)

        if self.storage:
            storage_ref = self.storage

            def _read_cache(query: str) -> str:
                docs = storage_ref.search(query)
                if not docs:
                    return "Nenhum resultado encontrado no cache local."
                lines = []
                for doc in docs:
                    title = doc.metadata.get("title", "Sem título")
                    url = doc.metadata.get("url", "")
                    preview = doc.page_content[:200].replace("\n", " ")
                    line = f"- [{title}]({url}): {preview}..." if url else f"- {title}: {preview}..."
                    lines.append(line)
                return "Cache local:\n" + "\n".join(lines)

            cache_tool = StructuredTool.from_function(
                func=_read_cache,
                name=f"{base_name}_ReadCache",
                description=(
                    "Busca apenas no cache local de pesquisas anteriores. "
                    "Use ANTES de buscar na web para economizar créditos."
                ),
            )
            tools.append(cache_tool)

        return tools
