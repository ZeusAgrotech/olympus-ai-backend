from abc import ABC
from functools import lru_cache
import queue
import threading

from langchain_classic.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.callbacks.base import BaseCallbackHandler
import tiktoken


# Thread-local para passar o thought_queue aos modelos internos (via as_tool)
_thought_queue_local = threading.local()


class _ThoughtQueueCallback(BaseCallbackHandler):
    """Callback que captura ações de agentes aninhados e empurra labels para a fila."""

    def __init__(self, thought_labels: dict, thought_queue: queue.Queue):
        super().__init__()
        self.thought_labels = thought_labels or {}
        self.thought_queue = thought_queue

    def on_agent_action(self, action, **kwargs):
        tool_name = getattr(action, "tool", "") or ""
        label = self.thought_labels.get(tool_name)
        if label is None and tool_name:
            label = f"Consultando {tool_name}..."
        if label:
            self.thought_queue.put(label)


@lru_cache(maxsize=32)
def _get_tiktoken_encoding(model_name: str):
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


class Model(ABC):
    """
    Classe base abstrata para padronizar agentes.
    As classes filhas devem definir:
      - self.description
      - self.llm
      - self.prompt
      - opcionalmente: self.tools, self.agents, self.use_history, self.max_history_messages
    antes de chamar super().__init__().
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Model"):
            raise TypeError(
                f"Subclasses de Model devem terminar com 'Model' (encontrado: '{cls.__name__}'). "
                f"Renomeie para '{cls.__name__}Model'."
            )

    # =========================
    # Inicialização
    # =========================

    def __init__(self):
        # 1. Validações de atributos obrigatórios
        if not getattr(self, "description", None):
            raise ValueError(
                f"Description is not initialized in {self.__class__.__name__}"
            )

        if not getattr(self, "llm", None):
            raise ValueError(f"LLM is not initialized in {self.__class__.__name__}")

        if not getattr(self, "prompt", None):
            raise ValueError(f"Prompt is not initialized in {self.__class__.__name__}")

        # Garante que tools existe, mesmo que vazio
        if not getattr(self, "tools", None):
            self.tools = []

        # Caso não tenha nome, usar o nome da classe
        if not getattr(self, "name", None):
            self.name = self.__class__.__name__

        # 2. Adiciona agentes filhos como tools (se definido)
        if getattr(self, "agents", None):
            self.instantiated_agents = []
            for agent_item in self.agents:
                if isinstance(agent_item, type):
                    self.instantiated_agents.append(agent_item())
                else:
                    self.instantiated_agents.append(agent_item)

            for agent in self.instantiated_agents:
                tools_or_tool = agent.as_tool()
                if isinstance(tools_or_tool, list):
                    self.tools.extend(tools_or_tool)
                else:
                    self.tools.append(tools_or_tool)

        if not getattr(self, "verbose", None):
            self.verbose = False

        if not getattr(self, "return_intermediate_steps", None):
            self.return_intermediate_steps = False

        # 3. Inicialização do Core do Agente (LangChain)
        try:
            self.agent_core = create_tool_calling_agent(
                llm=self.llm,
                tools=self.tools,
                prompt=self.prompt,
            )

            max_execution_time = getattr(self, "max_execution_time", 600)
            max_iterations = getattr(self, "max_iterations", 15)

            self.agent_executor = AgentExecutor(
                agent=self.agent_core,
                tools=self.tools,
                verbose=self.verbose,
                return_intermediate_steps=self.return_intermediate_steps,
                max_execution_time=max_execution_time,
                max_iterations=max_iterations,
            )
        except Exception as e:
            raise ValueError(
                f"Failed to initialize agent {self.__class__.__name__}: {e}"
            )

    # =========================
    # Métodos principais
    # =========================

    @staticmethod
    def _format_intermediate_steps(intermediate_steps) -> str:
        if not intermediate_steps:
            return ""

        formatted_steps = []
        for index, step in enumerate(intermediate_steps, start=1):
            action = None
            observation = None

            if isinstance(step, (list, tuple)):
                if len(step) > 0:
                    action = step[0]
                if len(step) > 1:
                    observation = step[1]
            else:
                formatted_steps.append(f"Passo {index}: {str(step)}")
                continue

            action_log = getattr(action, "log", None)
            tool_name = getattr(action, "tool", None)
            tool_input = getattr(action, "tool_input", None)

            if action_log:
                action_text = str(action_log).strip()
            else:
                action_parts = []
                if tool_name:
                    action_parts.append(f"Tool: {tool_name}")
                if tool_input is not None:
                    action_parts.append(f"Input: {tool_input}")
                action_text = " | ".join(action_parts) if action_parts else str(action)

            step_lines = [f"Passo {index}", f"Acao: {action_text}"]
            if observation is not None:
                step_lines.append(f"Observacao: {str(observation)}")

            formatted_steps.append("\n".join(step_lines))

        return "\n\n".join(formatted_steps).strip()

    def invoke(self, input_data: dict, *args, **kwargs):
        # Garante que input_data tenha um campo chat_history se não tiver
        if isinstance(input_data, dict):
            if "chat_history" not in input_data:
                input_data["chat_history"] = []

        # Callback para pensamentos de modelos aninhados
        tq = getattr(_thought_queue_local, "queue", None)
        config = {}
        if tq is not None:
            thought_labels = getattr(self, "thought_labels", {}) or {}
            config = {"callbacks": [_ThoughtQueueCallback(thought_labels, tq)]}

        response = self.agent_executor.invoke(input_data, config, *args, **kwargs)

        if isinstance(response, dict):
            thought = self._format_intermediate_steps(response.get("intermediate_steps"))
            response["thought"] = thought

        return response

    def stream(self, input_data: dict, thought_queue: "queue.Queue | None" = None, *args, **kwargs):
        # Garante que input_data tenha um campo chat_history se não tiver
        if isinstance(input_data, dict):
            if "chat_history" not in input_data:
                input_data["chat_history"] = []

        # Disponibiliza o thought_queue para modelos aninhados via thread-local
        if thought_queue is not None:
            _thought_queue_local.queue = thought_queue

        try:
            for chunk in self.agent_executor.stream(input_data, *args, **kwargs):
                yield chunk
        finally:
            if thought_queue is not None:
                _thought_queue_local.queue = None

    def _count_tokens(self, text: str) -> int:
        """Conta tokens usando tiktoken."""
        if not text:
            return 0

        model_name = (
            getattr(self, "model_name", None)
            or getattr(getattr(self, "llm", None), "model_name", None)
            or "cl100k_base"
        )

        encoding = _get_tiktoken_encoding(str(model_name))
        return len(encoding.encode(text, disallowed_special=()))

    def as_tool(self, name: str = None, description: str = None):
        from langchain_core.tools import StructuredTool

        def invoke_wrapper(input: str):
            # Repassa o thought_queue do thread corrente (via thread-local) para o invoke interno.
            # Isso permite que ações internas deste modelo apareçam como pensamentos no stream externo.
            result = self.invoke({"input": input, "chat_history": []})
            if isinstance(result, dict) and "output" in result:
                return result["output"]
            return str(result)

        return StructuredTool.from_function(
            func=invoke_wrapper,
            name=name or self.name,
            description=description or self.description,
        )

    def close(self):
        """
        Fecha conexões de agentes filhos instanciados.
        """
        if getattr(self, "instantiated_agents", None):
            for agent in self.instantiated_agents:
                if hasattr(agent, "close"):
                    try:
                        agent.close()
                    except Exception as e:
                        print(f"Erro ao fechar agente {agent}: {e}")
