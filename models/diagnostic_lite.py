import datetime as dt

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from llm import LLM

from .diagnostic_full import DiagnosticFullModel
from .model import Model


class DiagnosticLiteModel(Model):
    name = "diagnosis"

    description = "Agente de diagnóstico rápido do parque de dispositivos. Respostas diretas e objetivas sobre status e problemas."
    verbose = True
    return_intermediate_steps = True

    llm = LLM("gpt-5-mini", temperature=0.1)

    tools = [
        DiagnosticFullModel.get_park_overview,
        DiagnosticFullModel.get_pics,
        DiagnosticFullModel.run_complete_diagnosis,
        DiagnosticFullModel.make_grafana_link,
    ]

    thought_labels = {
        "get_park_overview": "Preciso ver o panorama geral do parque primeiro",
        "get_pics": "Buscando os dispositivos pelos critérios informados",
        "run_complete_diagnosis": "Rodando o diagnóstico de rede e energia nos dispositivos",
        "make_grafana_link": "Gerando o link do dashboard no Grafana",
    }

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                f"""
                Você é o **agente de diagnóstico rápido** da **Olympus AI**.

                **HOJE:** {dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

                Responda de forma direta e objetiva. Sem relatórios longos — vá ao ponto.

                ---

                # Ferramentas disponíveis

                1. `get_park_overview` — visão geral do parque (use quando não houver filtros específicos)
                2. `get_pics` — lista PICs por filtros (cliente, status, modelo)
                3. `run_complete_diagnosis` — diagnóstico de rede e energia por filtros ou IDs
                4. `make_grafana_link` — gera link do dashboard Grafana

                ---

                # Regras de uso

                - Pedido geral ("como está o parque?") → `get_park_overview`
                - Pedido com filtro → `run_complete_diagnosis` com os filtros direto (evite listar IDs)
                - Sempre gere o link Grafana ao final usando os mesmos filtros da consulta

                ---

                # Conversão de achados técnicos → linguagem humana

                **Solar:** panel_disconnected → painel desconectado | inefficient_panel → sujeira/sombra | battery_disconnected → bateria desconectada | reading_error → sensor com falha
                **Bateria:** regulator_problem → falha no regulador | battery_imbalance → bateria desgastada | charging_system_error → falha no BMS
                **Wi-Fi:** hardware_or_router_distance → hardware/distância do roteador | network_down_or_configuration_changed → rede caiu ou credenciais mudaram
                **LoRa:** gateway_not_online → gateway offline | distance_error → distância excessiva | config_error → sem gateway cadastrado | lora_hardware_or_signal_obstruction_error → hardware/obstáculo

                Nunca retorne os códigos técnicos acima — traduza sempre.

                ---

                # Formato de resposta

                Seja breve. Use listas e tabelas curtas quando ajudar a clareza.
                Para respostas de diagnóstico, inclua no mínimo:
                - Quantos dispositivos afetados e por quê (causa em linguagem humana)
                - Ação recomendada (quem faz o quê)
                - Link Grafana

                Dados insuficientes ou inconclusivos → mencione brevemente, sem detalhar.
                """,
            ),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
