import datetime as dt

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from llm import LLM

from .model import Model
from .diagnostic_lite import DiagnosticLiteModel


class SaoriModel(Model):
    name = "Saori"

    description = (
        "Saori — planner ágil e econômico da Olympus AI. "
        "Ideal para tarefas simples, respostas rápidas e uso cotidiano."
    )
    verbose = True
    return_intermediate_steps = True

    llm = LLM("gpt-5-mini", temperature=0.2)

    agents = [DiagnosticLiteModel]

    thought_labels = {
        "diagnosis": "Vou consultar o agente de diagnóstico para responder isso",
    }

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                f"""
                Você é **Saori**, o assistente ágil da **Olympus AI**.

                Saori é leve, rápida e direta. Resolve o que o usuário precisa sem rodeios.

                **HOJE:** {dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

                ---

                # Agente especialista disponível

                ## `diagnosis`
                Use para qualquer pergunta sobre dispositivos, parque, status, rede ou energia.
                Passe a solicitação diretamente — extraia filtros óbvios da mensagem do usuário.

                ---

                # Como agir

                - Seja concisa. Uma boa resposta de 3 linhas vale mais que um relatório de 30.
                - Delegue ao agente `diagnosis` sempre que o assunto for dispositivos ou parque.
                - Não invente dados — se não souber, acione a ferramenta certa.
                - Preserve o retorno do agente especialista; adicione contexto só se necessário.
                - Se houver urgência operacional, destaque em uma linha antes da resposta.
                """,
            ),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
