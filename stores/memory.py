from embeddings.openai import OpenAIEmbedding
from rag.base import TypeAccess
from rag.weaviate import WeaviateRAG


class Memory(WeaviateRAG):
    description = """
        Memória de longo prazo das conversas dos usuários do ZeusAI.
        Uma linha = um trecho/mensagem que você decidiu salvar como importante.
    """

    collection_name = "ZEUSAI_Memory"
    text_key = "content"
    type_access = TypeAccess.ALL
    max_query_results = 5

    metadata_fields = [
        "user_id",
        "chat_id",
        "role",
        "importance",
        "timestamp",
        "tags",
    ]

    embedding = OpenAIEmbedding("text-embedding-3-small")

    skip_init_checks = True
    port = 8080
