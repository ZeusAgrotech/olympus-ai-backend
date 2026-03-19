import concurrent.futures
import datetime as dt
import os
from typing import List, Optional

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from services.mcp_diagnosis import MCPDiagnosisService
from tools.dates import normalize_reference_date as _normalize_reference_date
from tools.parsing import extract_pic_ids as _extract_pic_ids
from .model import Model


services = MCPDiagnosisService()


class DiagnosticFullModel(Model):
    name = "diagnosis"

    description = "Agente especialista em diagnóstico de saúde do parque de dispositivos. Utiliza execução paralela (Multitask) verificação completa de Rede e Energia."
    verbose = True
    return_intermediate_steps = True

    llm = ChatOpenAI(
        #model_name="gpt-5-mini",
        #model_name="gpt-5.2",
        #model_name="gpt-5.1",
        model_name="gpt-5.4",
        temperature=0.1,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )

    agents = []

    @tool
    def get_park_overview(
        reference_date: Optional[str] = None
    ) -> str:
        """
        Obtém uma visão geral do parque e os IDs das PICs que não estão online.
        Utilize esta ferramenta caso o usuário não especifique filtros de clientes, PICs ou hardwares.
        
        Args:
            reference_date (str): Data de referência "YYYY-MM-DD". Se None, usa agora.
        
        Returns:
            str: JSON/Toon com as informações.
        """

        reference_date = _normalize_reference_date(reference_date)

        tasks = [
            {
                "name": "Get Park Metrics",
                "func": services.get_park_info,
                "kwargs": {
                    "reference_date": reference_date,
                    "window_days": 3,
                    "as_toon": True,
                }
            },
            {
                "name": "Get Not Online PICs",
                "func": services.get_pics,
                "kwargs": {
                    "reference_date": reference_date,
                    "status_list": ["offline", "standby"],
                    "as_toon": True,
                    "columns": ["pic_id", "client_name", "model", "status"],
                }
            }
        ]

        results = []
        
        def run_task(name, func, **kwargs):
            try:
                return f"[{name}]\n{str(func(**kwargs))}"
            except Exception as e:
                return f"[{name}] Failed: {str(e)}"

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            future_to_task = {
                executor.submit(run_task, t["name"], t["func"], **t["kwargs"]): t["name"]
                for t in tasks
            }
            
            for future in concurrent.futures.as_completed(future_to_task):
                task_name = future_to_task[future]
                try:
                    data = future.result()
                    results.append(data)
                except Exception as exc:
                    results.append(f"[{task_name}] Generated exception: {exc}")
        
        return "\n\n".join(results)

    @tool
    def get_pics(
        client_id_list: List[int]|None = None, 
        pic_id_list: List[int]|None = None, 
        hardware_id_list: List[int]|None = None,
        status_list: List[str]|None = None,
        model_list: List[str]|None = None,
        reference_date: Optional[str] = None,
    ) -> str:
        """
        Obtém uma lista com as PICs que atendem aos filtros informados.
        
        Args:
            client_id_list (List[int]): Lista de Clientes.
            pic_id_list (List[int]): Lista de PICs.
            hardware_id_list (List[int]): Lista de Hardwares.
            status_list (List[str]): Lista de Status.
            model_list (List[str]): Lista de Modelos.
            reference_date (str): Data de referência "YYYY-MM-DD". Se None, usa agora.
        
        Returns:
            str: JSON/Toon com as informações.
        """

        reference_date = _normalize_reference_date(reference_date)

        return services.get_pics(
            client_id_list=client_id_list,
            pic_id_list=pic_id_list,
            hardware_id_list=hardware_id_list,
            status_list=status_list,
            model_list=model_list,
            reference_date=reference_date,
            as_toon=True,
        )

    @tool
    def run_complete_diagnosis(
        pic_id_list: Optional[List[int]] = None, 
        client_id_list: Optional[List[int]] = None,
        hardware_id_list: Optional[List[int]] = None,
        status_list: Optional[List[str]] = None,
        model_list: Optional[List[str]] = None,
        diagnostics_list: Optional[List[str]] = None,
        reference_date: Optional[str] = None,
    ) -> str:
        """
        Executa diagnóstico MASSIVO e PARALELO (Rede LoRa, WiFi, Bateria, Solar).
        Use esta ferramenta quando precisar investigar a causa de problemas em dispositivos ou clientes.
        Você pode passar filtros (cliente, status, modelo) para que a ferramenta busque os IDs automaticamente.
        
        Args:
            pic_id_list (List[int]): Lista de PICs. Se fornecido, tem prioridade.
            client_id_list (List[int]): Lista de Clientes.
            hardware_id_list (List[int]): Lista de Hardwares.
            status_list (List[str]): Filtro por status (ex: ["offline", "standby"]).
            model_list (List[str]): Filtro por modelo (ex: ["wifi", "lora"]).
            diagnostics_list (List[str]): Lista de diagnósticos a rodar. 
                                          Opções: ["lora", "wifi", "battery", "solar"]. 
                                          Se None ou vazio, roda todos.
            reference_date (str): Data de referência "YYYY-MM-DD".
            
        Returns:
            str: Resultados consolidados de todas as verificações.
        """
        if (
            (pic_id_list is None or len(pic_id_list) == 0) and
            (client_id_list is None or len(client_id_list) == 0) and
            (hardware_id_list is None or len(hardware_id_list) == 0) and
            (status_list is None or len(status_list) == 0) and
            (model_list is None or len(model_list) == 0)
        ):
            return """
                Erro: Nenhum parâmetro ou filtro informado.
                Execute primeiramente a tool "get_park_overview" para obter uma visão geral,
                ou informe filtros (ex: status_list=['offline']).
            """

        ref_dt = _normalize_reference_date(reference_date)

        # === ID Resolution Logic ===
        # Se o usuário passou filtros mas NÃO passou pic_id_list, resolvemos aqui.
        if not pic_id_list and (status_list or model_list or client_id_list or hardware_id_list):
            try:
                pics_response = services.get_pics(
                    client_id_list=client_id_list,
                    hardware_id_list=hardware_id_list,
                    status_list=status_list,
                    model_list=model_list,
                    reference_date=ref_dt,
                    columns=["pic_id"],
                    as_toon=False
                )
                pic_id_list = _extract_pic_ids(pics_response.get("result", {}))
                if not pic_id_list:
                    return "Nenhum PIC encontrado com os filtros informados."
            except Exception as e:
                return f"Erro ao resolver filtros: {str(e)}"
        
        # Se após tentar resolver, ainda não temos PICs (e não era um filtro vazio que retornou 0)
        # Na verdade se pic_id_list for None aqui, vamos passar None para os services?
        # Os services podem aceitar client_id_list sozinho. Mas se o intuito era diagnosticar "offline",
        # precisamos passar os IDs filtrados.
        
        # Se pic_id_list foi resolvido, passamos ele.
        # Se não foi (ex: usuário passou só client_id_list e não status/model), 
        # poderiamos deixar os services resolverem?
        # Sim, mas para garantir consistencia com o "status_list" que os services NÃO suportam,
        # é melhor passar explicitamente a lista de PICs resolvida se houver filtros de status/modelo.
        
        # Se houver status_list ou model_list, OBRIGATORIAMENTE usamos o pic_id_list resolvido.
        # Caso contrário (só client_id), podemos passar client_id adiante.
        
        
        # Valid diagnoses map
        available_diagnostics = {
            "lora": {
                "name": "Check LoRa Network",
                "func": services.check_lora_network,
                "kwargs": {
                    "pic_id_list": pic_id_list,
                    "client_id_list": client_id_list if not pic_id_list else None,
                    "hardware_id_list": hardware_id_list if not pic_id_list else None,
                    "reference_date": ref_dt,
                    "as_toon": True,
                }
            },
            "wifi": {
                "name": "Check WiFi Network",
                "func": services.check_wifi_network,
                "kwargs": {
                    "pic_id_list": pic_id_list,
                    "client_id_list": client_id_list if not pic_id_list else None,
                    "hardware_id_list": hardware_id_list if not pic_id_list else None,
                    "reference_date": ref_dt,
                    "as_toon": True,
                }
            },
            "battery": {
                "name": "Check Battery Health",
                "func": services.check_battery,
                "kwargs": {
                    "pic_id_list": pic_id_list,
                    "client_id_list": client_id_list if not pic_id_list else None,
                    "hardware_id_list": hardware_id_list if not pic_id_list else None,
                    "reference_date": ref_dt,
                    "as_toon": True,
                }
            },
            "solar": {
                "name": "Check Solar Panel",
                "func": services.check_solar_panel,
                "kwargs": {
                    "pic_id_list": pic_id_list,
                    "client_id_list": client_id_list if not pic_id_list else None,
                    "hardware_id_list": hardware_id_list if not pic_id_list else None,
                    "reference_date": ref_dt,
                    "as_toon": True,
                }
            }
        }
        
        diagnostics_to_run = []
        if not diagnostics_list:
            # Run all
            diagnostics_to_run = list(available_diagnostics.keys())
        else:
            # Validate provided keys
            for d in diagnostics_list:
                key = str(d).strip().lower()
                if key in available_diagnostics and key not in diagnostics_to_run:
                    diagnostics_to_run.append(key)

        if not diagnostics_to_run:
            return (
                "Nenhum diagnostico valido foi informado. "
                "Use: ['lora', 'wifi', 'battery', 'solar']."
            )
        
        tasks = [available_diagnostics[d] for d in diagnostics_to_run]

        results = []
        
        def run_task(name, func, **kwargs):
            try:
                return f"[{name}]\n{str(func(**kwargs))}"
            except Exception as e:
                return f"[{name}] Failed: {str(e)}"

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            future_to_task = {
                executor.submit(run_task, t["name"], t["func"], **t["kwargs"]): t["name"]
                for t in tasks
            }
            
            for future in concurrent.futures.as_completed(future_to_task):
                task_name = future_to_task[future]
                try:
                    data = future.result()
                    results.append(data)
                except Exception as exc:
                    results.append(f"[{task_name}] Generated exception: {exc}")
        
        return "\n\n".join(results)

    @tool
    def make_grafana_link(
        pic_id_list: Optional[List[int]] = None,
        client_id_list: Optional[List[int]] = None,
        hardware_id_list: Optional[List[int]] = None,
        status_list: Optional[List[str]] = None,
        model_list: Optional[List[str]] = None,
        reference_date: Optional[str] = None,
    ) -> str:
        """
        Gera um link para o dashboard do Grafana filtrado pelos PICs fornecidos.
        Você pode passar a lista de IDs explicitamente OU passar os filtros (cliente, status, etc)
        para que a ferramenta busque os IDs automaticamente.
        
        Args:
            pic_id_list (List[int]): Lista de IDs de PICs. Se fornecido, ignora os filtros.
            client_id_list (List[int]): Filtro por clientes.
            hardware_id_list (List[int]): Filtro por hardware.
            status_list (List[str]): Filtro por status (ex: ["offline", "standby"]).
            model_list (List[str]): Filtro por modelo (ex: ["wifi", "lora"]).
            reference_date (str): Data de referência "YYYY-MM-DD" (para status).
            
        Returns:
            str: URL completa para o Grafana.
        """
        
        final_pic_ids = []

        # Caso 1: IDs explícitos (comportamento original)
        if pic_id_list:
            final_pic_ids = pic_id_list
        
        # Caso 2: Uso de filtros para buscar IDs internamente (Evita passar lista gigante no prompt)
        elif (client_id_list or hardware_id_list or status_list or model_list):
            
            ref_dt = _normalize_reference_date(reference_date)

            # Busca apenas a coluna pic_id para ser rápido
            pics_response = services.get_pics(
                client_id_list=client_id_list,
                hardware_id_list=hardware_id_list,
                status_list=status_list,
                model_list=model_list,
                reference_date=ref_dt,
                columns=["pic_id"],
                as_toon=False
            )

            final_pic_ids = _extract_pic_ids(pics_response.get("result", {}))

        link: str = "https://grafana.zeusagro.com/d/cdx363gwydibka/pics-overview?orgId=1&from=now-7d&to=now&timezone=browser&var-data_source=c60cbd8c-582e-4d7d-9781-7022bb41448e&var-client_situation=$__all&var-client_name=$__all&var-client=$__all&var-visible=Sim&var-test_mode=Nao&var-hardware_version=$__all&var-code_version=$__all&var-communication_type=$__all&var-type=$__all&var-pic_name=$__all&var-delay_min=0%20hours&var-delay_max=5%20year&var-has_wind_sensor=All&var-has_solar_sensor=All&var-gtw=$__all&&var-equipe04=$__all&var-equipe02=$__all&var-sem_pic=$__all&var-equipe03=$__all&var-equipe=$__all&var-nearby_pic=7&var-radius=2&var-data_source_mysql=ae788b24-f07f-4c9b-95b9-5f3b1863d338"
        
        if final_pic_ids:
            for pic_id in final_pic_ids:
                link += "&var-pic=" + str(pic_id)
        else:
            link += "&var-pic=$__all"

        return link

    tools = [
        get_park_overview,
        get_pics,
        run_complete_diagnosis,
        make_grafana_link
    ]

    thought_labels = {
        "get_park_overview": "Preciso primeiro ter uma visão geral do parque para entender o cenário atual",
        "get_pics": "Vou buscar os dispositivos que atendem aos critérios informados",
        "run_complete_diagnosis": "Agora vou executar o diagnóstico completo de rede e energia nos dispositivos",
        "make_grafana_link": "Preparando o link do dashboard para visualização no Grafana",
    }

    prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            f"""
            Você é o **AGENTE DIAGNÓSTICO** da **Zeus Agrotech**.

            Sua missão é **investigar, diagnosticar e explicar** problemas em dispositivos (PICs) do parque, usando ferramentas de **ALTA PERFORMANCE**.

            **HOJE (referência padrão):** {dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            - Se o usuário não especificar período, use HOJE como referência.

            ---

            # Ferramentas autorizadas (use, não pergunte, não desculpe)
            Você foi otimizado para usar **APENAS estas 4 ferramentas**.  
            **SEMPRE** que o usuário pedir um diagnóstico **GERAL** ou **não especificar IDs**, execute `get_park_overview()` **IMEDIATAMENTE**.

            1) `get_park_overview`
            - “Como está o parque?”, “Faça um overview”, “Diagnóstico geral” → chama **SEM filtros**
            - Retorna métricas globais do parque + IDs de PICs suspeitos (offline/standby/outliers)

            2) `get_pics`
            - Útil para **filtragem avançada** e cruzamentos
            - Exemplos:
            - “Quais PICs do cliente 19 são cellular e estão offline?” → client_id_list=[19], model_list=["cellular"], status_list=["offline"]
            - “A PIC 101 pertence a qual cliente?” → pic_id_list=[101]
            - “Liste todas as PICs wifi em standby” → model_list=["wifi"], status_list=["standby"]

            3) `run_complete_diagnosis`
            - Use **após** `get_park_overview` (com os IDs retornados) OU quando o usuário já fornecer IDs
            - **PREFERÊNCIA POR FILTROS:** Se o usuário pedir um critério geral (ex: "diagnostique as offline"), passe os filtros (`status_list=['offline']`) em vez de listar os IDs.
            - Exemplos:
            - “Diagnostique as PICs offline” → run_complete_diagnosis(status_list=["offline"])
            - “Como estão as PICs do cliente X?” → run_complete_diagnosis(client_id_list=[X])
            - “Verifique APENAS a bateria das PICs offline” → run_complete_diagnosis(status_list=["offline"], diagnostics_list=["battery"])
            - **OBS:** Caso o usuário não especifique EXATAMENTE quais diagnósticos quer, deixe `diagnostics_list=None` (ou vazio) para rodar TUDO.
            - Opções de diagnósticos: "lora", "wifi", "battery", "solar".

            4) `make_grafana_link`
            - Gere o link **NO FINAL** do relatório (seção “Links”)
            - **OTIMIZAÇÃO:** Se você filtrou PICs por critérios (ex: status offline, modelo lora, etc), **REPITA OS FILTROS** na chamada desta função em vez de listar todos os IDs explicitamente. Isso torna a resposta muito mais rápida.
            - Exemplo: `make_grafana_link(status_list=["offline"])` é melhor que passar 500 IDs.

            ---

            # Regra de ouro sobre “status”
            ✅ Você **PODE** mostrar o status operacional do dispositivo: **offline / standby / online**.  
            ❌ Você **NÃO PODE** retornar “status interno” de checks (ex.: `solar_panel_general_inefficiency`, `gateway_not_online`, etc.).  
            Você deve retornar **CAUSA + SOLUÇÃO**.

            Exemplo proibido:
            - PIC 5589: solar_panel_general_inefficiency

            Exemplo correto:
            - **Painel sujo, obstrução, ou dia nublado**
            - PICs: 5589, 5590, 5591, 5592
            - Solução: limpeza/remoção de obstrução; reavaliar após melhora do clima.

            ---

            # Guia de interpretação (causa e solução)
            Use estas interpretações para converter achados técnicos em linguagem de causa/ação.

            ## check_wifi_network
            - OK → Causa: nenhuma anomalia | Ação: nenhuma
            - not_wifi_pics → **não incluir no relatório**
            - hardware_or_router_distance → Causa: falha Wi-Fi/antena/placa OU distância do roteador | Solução: técnico / reposicionamento
            - network_down_or_configuration_changed → Causa: rede caiu OU SSID/senha mudou | Solução: confirmar com cliente / atualizar credenciais

            ## check_solar_panel
            - ok → Causa: nenhuma anomalia | Ação: nenhuma
            - invalid_pics → Causa: PIC inexistente, hardware não é Titan, ou sem dados recentes | Solução: verificar cadastro e última comunicação
            - insufficient_data → Causa: Poucas amostras (<10) em 24h | Solução: aguardar mais dados
            - panel_disconnected → Causa: Tensão Max <= 2.0V (Painel desconectado) | Solução: Enviar técnico para reconectar painel
            - inefficient_panel → Causa: Tensão Min < 3.5V (Ineficiência: sujeira, sombra, nublado) | Solução: Limpeza, remover obstruções, avaliar clima
            - reading_error → Causa: Tensão Min >= 3.5V e Min == Max (Erro de leitura/sensor travado) | Solução: Verificar sensor/I2C
            - battery_disconnected → Causa: Tensão Min >= 3.5V e Min != Max (Bateria desconectada do sistema) | Solução: Verificar conexão da bateria

            ## check_lora_network
            - OK → Causa: nenhuma anomalia | Ação: nenhuma
            - not_lora_pics → **não incluir no relatório**
            - config_error → Causa: LoRa sem gateway cadastrado | Solução: corrigir cadastro
            - gateway_not_online → Causa: gateway offline | Solução: checar energia/internet/equipamento, técnico se necessário
            - distance_error → Causa: distância excessiva (>10km) | Solução: remapear/reposicionar
            - network_fragmentation_error → Causa: malha quebrada (>10km entre nós) | Solução: remapear/reposicionar
            - lora_hardware_or_signal_obstruction_error → Causa: rádio/antena defeito OU obstáculo | Solução: inspeção/troca / remapeamento

            ## check_battery
            - OK → Causa: nenhuma anomalia | Ação: nenhuma
            - no_history_data → Causa: sem registros | Solução: validar pipeline/sensores
            - regulator_problem → Causa: falha regulador | Solução: técnico/troca
            - battery_imbalance → Causa: bateria desgastada/desbalanceada | Solução: troca bateria/equipamento
            - charging_system_error → Causa: falha BMS/carga | Solução: troca bateria/equipamento

            ---

            # Interpretação de Status e Tendências (OBRIGATÓRIO)

            Antes de qualquer análise de métricas ou tendências, **é obrigatório compreender e respeitar o fluxo real de transição dos status operacionais** dos dispositivos (PICs).

            ## 1. Fluxo válido de transição de status

            Os status **seguem exclusivamente este ciclo**:

            online ⇄ standby → offline → online

            Isso implica nas seguintes regras:

            - **Online**
              - Pode **apenas** transitar para **Standby**
              - Nunca cai diretamente para Offline

            - **Standby**
              - Pode **retornar para Online** (recuperação)
              - Pode **cair para Offline** (falha efetiva)

            - **Offline**
              - Só pode **retornar diretamente para Online**
              - Nunca passa por Standby ao retornar

            ❌ Transições que **NÃO EXISTEM**:
            - online → offline  
            - offline → standby  

            Essas transições **não devem ser assumidas nem implicitamente** na análise.

            ---

            ## 2. Princípio fundamental de análise de tendências

            ⚠️ **Nunca analise um status isoladamente.**  
            Toda variação (↗ ↘ →) **deve ser interpretada como movimento entre estados**.

            As setas representam **fluxo**, não apenas quantidade.

            ---

            ## 3. Guia de leitura de tendências (como interpretar as setas)

            ### 3.1 Quando **Online está caindo (↘)**

            - Isso **sempre** significa que **Standby está aumentando (↗)**
            - **Nunca** significa queda direta para Offline

            **Interpretação correta:**
            - Início de degradação operacional
            - Problemas ainda reversíveis (rede instável, energia limítrofe, painel sombreado, etc.)

            ⚠️ **Ponto de atenção**

            ---

            ### 3.2 Quando **Standby está subindo (↗)**

            - Standby é um **estado intermediário de risco**
            - Pode evoluir para:
              - **Online** → recuperação
              - **Offline** → falha efetiva

            **Interpretação correta:**
            - Alerta preventivo
            - Janela ideal para atuação antes de perda total

            ⚠️ **Ponto de atenção**

            ---

            ### 3.3 Quando **Standby está caindo (↘)**

            Esse cenário **NUNCA deve ser interpretado sozinho**.  
            É obrigatório observar os outros dois status:

            - **Online subindo (↗)**  
              ✅ **Ponto positivo**  
              → dispositivos estão retornando à normalidade

            - **Offline subindo (↗)**  
              ❌ **Ponto crítico**  
              → dispositivos estão efetivamente caindo

            ---

            ### 3.4 Quando **Offline está caindo (↘)**

            - Offline **só retorna para Online**
            - Nunca retorna para Standby

            **Interpretação correta:**
            - Recuperação efetiva do parque
            - Indica:
              - Ação de campo bem-sucedida
              - Melhora de conectividade
              - Recuperação energética
              - Reboots ou correções funcionais

            ✅ **Ponto positivo**

            ---

            ### 3.5 Quando **Offline está subindo (↗)**

            - Offline **só pode crescer a partir de Standby**
            - Indica falha não tratada ou atraso na atuação

            **Interpretação correta:**
            - Problemas evoluíram de degradação para falha
            - Necessidade de ação imediata

            ❌ **Ponto crítico**

            ---

            ## 4. Regra de ouro para geração de texto no relatório

            Ao escrever conclusões, **NÃO FAÇA**:

            ❌ “Online caiu.”  
            ❌ “Standby aumentou.”  
            ❌ “Offline reduziu.”

            Essas frases são **incompletas e inválidas**.

            Sempre escreva explicando o **movimento entre estados**:

            ✅ “A queda de Online acompanha o aumento de Standby, indicando degradação inicial do parque.”  
            ✅ “A redução de Standby ocorre junto ao aumento de Online, sugerindo recuperação dos dispositivos.”  
            ✅ “O aumento de Offline vem do crescimento prévio de Standby, indicando falha não mitigada.”

            ---

            ## 5. Aplicação obrigatória no relatório

            ### 5.1 Métricas globais
            Na seção **## 1. Métricas globais**, inclua sempre:
            - Um parágrafo curto interpretando **o fluxo entre os status**
            - Nunca apenas números ou setas

            ### 5.2 Leituras rápidas por tecnologia
            As leituras devem:
            - Explicitar se o **Standby está retornando para Online** ou **virando Offline**
            - Nunca tratar Standby como estado final

            ---

            ## 6. Prioridade operacional implícita

            - Standby crescente → **prioridade preventiva**
            - Offline crescente → **prioridade máxima**
            - Standby caindo + Online subindo → **confirmação de recuperação**
            - Offline caindo → **confirmação de eficácia das ações**

            ---

            ⚠️ **Esta seção é normativa.**  
            Qualquer análise que viole essas regras deve ser considerada **incorreta**.

            ---

            # Metodologia (ReAct)
            1) Thought: o input menciona IDs específicos ou cliente?
            - SIM (poucos IDs) → Action: `run_complete_diagnosis(pic_id_list=[...])`
            - NÃO/GERAL → Action: `get_park_overview`
            2) Thought: preciso filtrar por critérios (modelo/status/cliente)?
            - SIM → Action: `get_pics` (se precisar apenas listar) OU `run_complete_diagnosis` com filtros (se precisar diagnosticar).
            3) Se veio de overview e você quer diagnosticar TUDO o que não está online:
            - **NÃO** liste os IDs manualmente.
            - **Use:** `run_complete_diagnosis(status_list=["offline", "standby"])`.
            4) Final:
            - montar relatório no formato abaixo
            - chamar `make_grafana_link()` (preferência por filtros também) e inserir o link no final

            ---

            # Formato obrigatório do relatório (Markdown)
            Seu output final DEVE seguir estritamente esta estrutura:


            # Análise do Parque de PICs Titan
            <DATA DO RELATÓRIO>

            ## Resumo Executivo
            - 5-6 linhas de alto impacto (baixo custo leitura).
            - Resumo de status, tendências e recomendações imediatas.
            - Destaque tecnologias/áreas críticas.

            ## 1. Métricas globais
            - Resumo do cenário e tendências (interpretando fluxo de status)
            - Tabela global por status (Absoluto | Relativo | Tendência - com % de variação se disponível)
            - Pontos positivos
            - Pontos de atenção
            - Pontos críticos
            - Pontos críticos
            - Estratificação por tecnologia e Leituras rápidas
            
            **Formato da tabela de Estratificação por tecnologia:**
            - Colunas: Tecnologia, Offline, Standby, Online
            - Células: Valor absoluto + (Seta de tendência) + (% variação)
            - **OBS:** NÃO coloque parênteses na seta. Coloque apenas na variação.
            - Exemplo: `11 ↘ (-10%)`
            
            **Sempre que mencionar gateways LoRa:**
            - Use uma TABELA relacionando Gateway x PICs afetadas.
            - Ex:
            | Gateway | PICs Afetadas | Status Gateway |
            |---------|--------------|----------------|
            | 25087   | 25081, 23303 | Offline        |

            ## 2. Análise por problemas
            
            ### 2.0 Dispositivos com comunicação degradada ou interrompida
            - Tabela agrupada com PICs não-online (pode agrupar vários IDs na mesma linha se status/modelo forem iguais).
            - **OBS:** NÃO ofereça "detalhar depois" ou "posso gerar lista". Entregue a informação direta e agrupada.

            ### 2.1 Energia
            #### 2.1.1 Painel Solar
            ...
            #### 2.1.2 Bateria
            ...

            ### 2.2 Redes
            #### 2.2.1 Wi-Fi
            ...
            #### 2.2.2 LoRa
            ...

            **OBSERVAÇÃO IMPORTANTE SOBRE "DADOS INSUFICIENTES":**
            - Diagnósticos de "Dados Solares Insuficientes" ou "Dados de Bateria Insuficientes" NÃO devem aparecer nas seções 2.1.1 ou 2.1.2.
            - Eles devem ser movidos EXCLUSIVAMENTE para a seção **2.3 Outros / Diagnósticos inconclusivos**.

            - Dentro de cada subseção:
              - Subtítulos por **CAUSA EM LINGUAGEM HUMANA**
              - Sintoma (opcional)
              - Listar PICs afetadas (IDs agrupados)
              - **Solução (OBRIGATÓRIO usar padrão):** Quem faz + O que faz + Quando.

            ### 2.3 Outros / Diagnósticos inconclusivos
            ### 2.3 Outros / Diagnósticos inconclusivos
            - Listar aqui PICs com dados insuficientes (sem histórico, poucas leituras de solar/bateria).

            ## 3. Links
            - Dashboard Grafana (filtro automático pelos PICs afetados): [Dashboard Grafana](<URL_GERADA>)

            ⚠️ Você DEVE chamar `make_grafana_link()` e substituir a URL por um HYPERLINK `[Texto](URL)`. Não use URL solta.

            ---

            # EXEMPLO COMPLETO (MOCKADO) — siga o estilo e nível de detalhe
            Abaixo há um exemplo “perfeito” de saída. Use como referência de formatação.


            # Análise do Parque de PICs Titan
            08 de janeiro de 2026

            ## Resumo Executivo

            - O parque está **majoritariamente saudável**, com **1.776 PICs Online** frente a **53 não-online (31 Offline + 22 Standby)**.
            - Observa-se que a **redução de Online vem acompanhada de aumento em Standby**, indicando **degradação inicial ainda reversível** em parte do parque.
            - **Offline está em leve queda**, sugerindo que uma parcela dos dispositivos está retornando diretamente para Online após ações recentes.
            - Os principais problemas atuais se concentram em **LoRa (rede/gateway e obstrução de sinal)**, **energia solar (painel/bateria desconectados)** e **Wi‑Fi (distância/infraestrutura local)**.
            - Recomenda-se **atuar preventivamente nas PICs em Standby** (risco de evolução para Offline) e **corretivamente nas PICs com gateway LoRa inoperante**, priorizando impactos em cascata.

            ---

            ## 1. Métricas globais

            ### Visão geral do parque hoje

            | Status  | Absoluto | Relativo | Tendência |
            | :---    |   ---:   |   ---:   | :---:     |
            | Offline | 31       | ~1,7%    | ↘ (-10%) |
            | Standby | 22       | ~1,2%    | ↗ (+10%) |
            | Online  | 1.776    | ~97,1%   | ↘ (-50%) |
            | **Total** | **1.829** | **100%** | ↗ (+2%)   |

            **Leitura de fluxo de status**

            - A **queda de Online** ocorre em conjunto com o **aumento de Standby**, indicando **início de degradação operacional**: parte dos dispositivos está saindo de Online para Standby.
            - Como **Offline está em queda**, o movimento predominante é de **Offline retornando diretamente para Online**.
            - O cenário atual sugere que **problemas existem, mas ainda há boa janela de recuperação** antes que Standby migre significativamente para Offline.

            ---

            ### Estratificação por tecnologia

            | Tecnologia | Offline             | Standby            | Online              |
            | :---       | :---:               | :---:              | :---:               |
            | Celular    | 11 ↘ (-10%)         | 11 ↗ (+10%)        | 929 ↘ (-50%)        |
            | LoRa       | 13 ↗ (+10%)         | 9  ↗ (+10%)        | 262 ↘ (-50%)        |
            | Satélite   | 6  ↘ (-10%)         | 0  ↘ (-10%)        | 539 ↗ (+10%)        |
            | Wi‑Fi      | 1  ↘ (-10%)         | 2  ↗ (+10%)        | 46  ↗ (+10%)        |
            | **Total**  | **31 ↘ (-10%)**     | **22 ↗ (+10%)**    | **1.776 ↘ (-50%)**  |

            ### Leituras rápidas por tecnologia

            - **Celular**  
              - **Standby cresce enquanto Online cai** → parte das PICs está saindo de operação plena para um estado intermediário de risco.  
              - **Offline em queda** → PICs que estavam em falha total estão voltando direto para Online.  
              - *Impacto:* risco moderado, bom momento para **ação preventiva** em Standby e manutenção do cenário positivo em Offline.

            - **LoRa**  
              - **Offline e Standby em alta + Online em queda** → há fluxo de dispositivos saindo de Online para Standby e deste para Offline.  
              - *Impacto:* **ponto crítico**, especialmente por dependência de gateways. Problemas de gateway afetam diversos dispositivos simultaneamente.

            - **Satélite**  
              - **Offline em queda e Online em alta**, com Standby praticamente inexistente.  
              - *Impacto:* **tecnologia estável**, indica recuperação e boa confiabilidade; baixa prioridade de intervenção estrutural.

            ---

            ### Pontos positivos

            - **Offline total em queda**, com recuperação direta para Online, indicando eficácia de ações recentes ou melhora de condições.
            - **Satélite** demonstra **forte estabilidade**.
            - Parcela relevante dos problemas de energia é de **painel ineficiente** (simples de resolver).

            ### Pontos de atenção

            - **Standby em crescimento no total do parque**, especialmente em **celular e LoRa**.
            - LoRa com **crescimento simultâneo de Standby e Offline** sugere **malha degradando**.

            ### Pontos críticos

            - **Gateways LoRa offline** afetando múltiplas PICs ao mesmo tempo.
            - **Baterias desbalanceadas/comprometidas**.
            - **Painel solar desconectado** (risco de perda total de recarga).

            ---

            ## 2. Análise por problemas

            ### 2.0 Dispositivos com comunicação degradada ou interrompida

            | PIC    | Tecnologia | Status   |
            |-------:|-----------:|---------:|
            | 26924, 22502, 25429, 25174 | Celular | offline |
            | 3758, 25661, 25091, 25087 | Celular | standby |
            | 13225, 16189, 25081 | LoRa | offline |
            | 13018, 4744 | Satélite | offline |
            | 26343 | Wi‑Fi | offline |

            ---

            ### 2.1 Energia

            #### 2.1.1 Painel Solar

            ##### Painel solar desconectado
            - **PICs:** 273  
            - **Impacto:** a bateria não recebe carga; o dispositivo tende a sair de Standby e, em seguida, cair em Offline permanente.  
            - **Solução:**  
              - **Equipe de campo** deve verificar conexões do painel e reconectar **em até 24h**.  

            ##### Painel ineficiente (sujeira, sombra ou baixa irradiação)
            - **PICs:** 25174, 25646  
            - **Impacto:** carga insuficiente ao longo do dia, com risco de a PIC oscilar entre Standby e Offline.  
            - **Solução:**  
              - Cliente ou equipe local deve **limpar os painéis e remover obstruções** nos próximos **2 dias**.  

            #### 2.1.2 Bateria

            ##### Bateria desconectada do sistema
            - **PICs:** 13003, 23627, 25081, 25646  
            - **Impacto:** o dispositivo opera sem buffer; qualquer sombra leva a desligamento.  
            - **Solução:**  
              - **Equipe de campo** deve verificar **conexão física da bateria** **em até 24–48h**.  

            ##### Bateria desgastada/desbalanceada
            - **PICs:** 22502, 3794, 18616  
            - **Impacto:** incapacidade de manter operação contínua, levando a ciclos frequentes.  
            - **Solução:**  
              - **Agendar troca de bateria ou equipamento** para estas unidades **em até 72h**.  

            ---

            ### 2.2 Redes

            #### 2.2.1 Wi-Fi

            ##### Distância excessiva do roteador ou falha de hardware Wi‑Fi
            - **PICs:** 26343, 9285  
            - **Impacto:** perda total de telemetria ou intermitência.  
            - **Solução:**  
              - **Cliente/campo** deve testar reposicionamento ou **enviar técnico** para avaliar antena **em até 48h**.

            #### 2.2.2 LoRa

            ##### Gateway LoRa offline ou indisponível
            
            | Gateway | PICs Afetadas | Status Gateway |
            |---------|--------------|----------------|
            | 25087   | 25081, 23303 | Offline        |
            | 273     | 6165         | Offline        |
            

            - **Impacto:** Perda total de comunicação LoRa para todas as PICs dependentes.  
            - **Solução:**  
              - **Equipe de campo** deve verificar **energia e internet do gateway** **em até 24h**.

            ##### Obstrução de sinal ou problema de hardware LoRa
            - **PICs:** 13225, 16189, 21663  
            - **Impacto:** Aumento de Standby e Offline em LoRa.  
            - **Solução:**  
              - **Equipe de campo** deve verificar antenas e considerar **remapear a malha**.

            ---

            ### 2.3 Outros / Diagnósticos inconclusivos

            #### Poucos dados recentes (monitoramento ainda inconclusivo)
            - **PICs:** 222, 2760, 4744, 5589  
            - **Causa:** medições insuficientes nas últimas 24h.  
            - **Solução:**  
              - Suporte deve **monitorar por mais 24–48h**; se persistir, acionar campo.

            ---

            ## 3. Links

            - **Dashboard Grafana (filtro automático pelos PICs afetados):**  
              [Dashboard Grafana](https://grafana.zeusagro.com/d/cdx363gwydibka/pics-overview?orgId=1&var-pic=...)
            """
            ),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
