from embeddings.openai import OpenAIEmbedding
from rag.base import TypeAccess
from rag.weaviate import WeaviateRAG


class Library(WeaviateRAG):
    description = """
        Biblioteca de conhecimento.
        Use esta ferramenta para buscar informações técnicas, manuais, documentações e procedimentos.
        Apenas busca é permitida.
    """

    collection_name = "VERBA_Embedding_text_embedding_3_large"
    text_key = "content"
    type_access = TypeAccess.READ
    max_query_results = 5
    embedding = OpenAIEmbedding("text-embedding-3-large")

    skip_init_checks = True
    port = 8080
