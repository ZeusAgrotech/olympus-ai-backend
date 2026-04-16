import os

from embeddings.openai import OpenAIEmbedding
from rag.base import TypeAccess
from rag.weaviate import WeaviateRAG
from search.tavily import TavilySearch


class _ResearchStore(WeaviateRAG):
    """Cache Weaviate para resultados de pesquisa web."""

    description = "Cache interno de pesquisas web do ZeusAI."
    collection_name = "ZEUSAI_Research"
    text_key = "content"
    type_access = TypeAccess.ALL
    max_query_results = 5
    embedding = OpenAIEmbedding("text-embedding-3-large")

    skip_init_checks = True
    port = 8080


class Research(TavilySearch):
    """
    Pesquisa web com cache semântico.

    Busca via Tavily e persiste resultados no Weaviate para reutilização futura.
    Para trocar o backend de cache, basta substituir `storage`:
        storage = MyRagieRAG  # ex: usa Ragie como cache
    """

    description = """
        Agente de Pesquisa (Research).
        Realiza buscas na web (via Tavily) para encontrar informações atualizadas
        e as armazena na base de conhecimento (RAG) para uso futuro.
    """

    tavily_api_key = os.getenv("TAVILY_API_KEY")
    max_web_results = 5
    storage = _ResearchStore
