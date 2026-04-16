# rag/rag.py — shim de compatibilidade retroativa
#
# A lógica foi migrada para módulos dedicados:
#   - rag/base.py          → RAG (interface), TypeAccess
#   - rag/weaviate.py  → WeaviateRAG
#   - rag/ragie.py         → RagieRAG
#   - search/tavily.py     → TavilySearch  (substituiu WebRAG)
#   - collections/         → Library, Memory, Research

from enum import Enum

from .base import RAG, TypeAccess
from .weaviate import WeaviateRAG
from search.tavily import TavilySearch as WebRAG


class Backend(Enum):
    WEAVIATE = "weaviate"
    RAGIE = "ragie"


__all__ = ["Backend", "RAG", "TypeAccess", "WeaviateRAG", "WebRAG"]
