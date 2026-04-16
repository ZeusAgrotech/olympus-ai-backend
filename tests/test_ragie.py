"""
Teste manual do RagieRAG.

Pergunta: "Em nome de funções eu uso snake-case ou camel-case?"
Partition: test
"""

from dotenv import load_dotenv
load_dotenv()

from rag.ragie import RagieRAG
from rag.base import TypeAccess


class TestKB(RagieRAG):
    description = "Base de conhecimento de teste."
    partition = "test"
    type_access = TypeAccess.READ


kb = TestKB()

query = "Em nome de funções eu uso snake-case ou camel-case?"
print(f"Query: {query}\n")

docs = kb.search(query)

if not docs:
    print("Nenhum resultado encontrado.")
else:
    for i, doc in enumerate(docs, 1):
        print(f"--- Resultado {i} (score: {doc.metadata.get('score', '?'):.3f}) ---")
        print(doc.page_content)
        print()
