from abc import ABC
import datetime as dt
import queue as _queue
import threading
from typing import Any, Dict, List

from flask import jsonify, request
from langchain_core.messages import AIMessage, HumanMessage

from server.exceptions import ServerBaseException, ValidationError
from tools.messages import normalize_message_content, extract_last_user_message


class Agent(ABC):
    """
    Classe base declarativa para agentes.

    Um agente pode registrar:
    1. Rotas de ferramenta (tool endpoints), declarando `urls` (ou `url`),
       `method` e `callback`.
     2. Um modelo de chat OpenAI-compatível, declarando `model`
         (obrigatório, como classe ou instância de models.model.Model).
    """

    hidden: bool = False

    _normalize_message_content = staticmethod(normalize_message_content)
    _extract_last_user_message = staticmethod(extract_last_user_message)

    @staticmethod
    def _extract_chat_output(response: Any) -> str:
        if isinstance(response, dict):
            return str(response.get("output", ""))
        return str(response)

    def _format_intermediate_steps(self, intermediate_steps: Any) -> str:
        formatter = getattr(self.model, "_format_intermediate_steps", None)
        if callable(formatter):
            try:
                return str(formatter(intermediate_steps) or "")
            except Exception:
                pass

        if intermediate_steps is None:
            return ""
        return str(intermediate_steps)

    def _action_to_human_label(self, action) -> str:
        tool_name = getattr(action, "tool", None) or ""
        thought_labels = getattr(self.model, "thought_labels", {}) or {}
        if tool_name in thought_labels:
            return thought_labels[tool_name]
        return f"Consultando {tool_name}..." if tool_name else ""

    @classmethod
    def _to_langchain_history(cls, messages: List[Dict[str, Any]]):
        previous_messages = messages[:-1] if messages and messages[-1].get("role") == "user" else messages

        chat_history = []
        for message in previous_messages:
            role = message.get("role")
            content = cls._normalize_message_content(message.get("content", ""))

            if role == "user":
                chat_history.append(HumanMessage(content=content))
            elif role == "assistant":
                chat_history.append(AIMessage(content=content))

        return chat_history

    @staticmethod
    def _float_or_none(value):
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _int_or_none(value):
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    @classmethod
    def _build_generation_params(cls, request_data: Dict[str, Any] | None = None) -> Dict[str, Any]:
        request_data = request_data or {}
        params: Dict[str, Any] = {}

        for key in ("temperature", "top_p", "frequency_penalty", "presence_penalty"):
            value = cls._float_or_none(request_data.get(key))
            if value is not None:
                params[key] = value

        for key in ("max_tokens",):
            value = cls._int_or_none(request_data.get(key))
            if value is not None:
                params[key] = value

        return params

    def _resolve_model(self):
        from models.model import Model

        declared_model = getattr(self, "model", None)
        if declared_model is None:
            raise ValueError(
                f"{self.__class__.__name__}: model is required and must be a Model subclass or Model instance"
            )

        model_init_kwargs = dict(getattr(self, "model_init_kwargs", {}) or {})

        if isinstance(declared_model, type):
            if not issubclass(declared_model, Model):
                raise TypeError(
                    f"{self.__class__.__name__}: model class must inherit from Model"
                )
            try:
                self.model = declared_model(**model_init_kwargs)
            except Exception as exc:
                raise ValueError(
                    f"{self.__class__.__name__}: failed to instantiate model {declared_model.__name__}: {exc}"
                )
        else:
            self.model = declared_model

        if not isinstance(self.model, Model):
            raise TypeError(
                f"{self.__class__.__name__}: model must be an instance of Model"
            )

    def _tool_callback(self, **kwargs):
        """Processa chamadas em rotas de ferramentas declaradas no agente."""
        callback = getattr(self, "callback", None)
        if callback is None:
            raise ValueError("callback is not defined")

        try:
            data = request.get_json() or {}

            parameters = {}
            valid_params = self.agent_definition.get("parameters", {}).get("properties", {})

            for key, value in data.items():
                if key not in valid_params:
                    raise ValidationError(f"Invalid parameter: {key}")
                parameters[key] = value

            for key, value in parameters.items():
                if isinstance(value, str) and key == "reference_date":
                    try:
                        dt_parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                        parameters[key] = dt_parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
                    except ValueError:
                        raise ValidationError(f"Invalid date format for reference_date: {value}")

            result = callback(**parameters)
            return jsonify(
                {
                    "tool": self.agent_definition["name"],
                    "result": result,
                    "success": True,
                }
            )
        except ServerBaseException as e:
            return jsonify(
                {
                    "error": e.message,
                    "tool": self.agent_definition["name"],
                    "success": False,
                    "error_type": e.__class__.__name__,
                }
            ), e.status_code
        except Exception as e:
            return jsonify(
                {
                    "error": str(e),
                    "tool": self.agent_definition["name"],
                    "success": False,
                    "error_type": "InternalServerError",
                }
            ), 500

    def chat(self, messages, model, request_data=None):
        """Implementação genérica para chat declarativo baseado em `model`."""

        if hasattr(self.model, "invoke"):
            request_data = request_data or {}
            user_input = request_data.get("_last_user_message") or self._extract_last_user_message(messages)
            chat_history = self._to_langchain_history(messages)

            response = self.model.invoke(
                {
                    "input": user_input,
                    "chat_history": chat_history,
                }
            )

            if isinstance(response, dict):
                output = str(response.get("output", ""))
                thought = response.get("thought", "")
                return {
                    "output": output,
                    "thought": str(thought),
                }
            return str(response)

        if hasattr(self.model, "chat"):
            params = self._build_generation_params(request_data)
            return self.model.chat(messages=messages, **params)

        raise NotImplementedError(f"{self.__class__.__name__} model does not support chat()")

    def chat_stream(self, messages, model, request_data=None):
        """Implementação genérica de stream para modelos declarativos."""
        if hasattr(self.model, "stream"):
            request_data = request_data or {}
            user_input = request_data.get("_last_user_message") or self._extract_last_user_message(messages)
            chat_history = self._to_langchain_history(messages)

            thought_queue = _queue.Queue()
            chunk_queue = _queue.Queue()

            def _run_stream():
                try:
                    for chunk in self.model.stream(
                        {"input": user_input, "chat_history": chat_history},
                        thought_queue=thought_queue,
                    ):
                        chunk_queue.put(("chunk", chunk))
                    chunk_queue.put(("done", None))
                except Exception as exc:
                    chunk_queue.put(("error", exc))

            threading.Thread(target=_run_stream, daemon=True).start()

            while True:
                # Drena pensamentos internos acumulados enquanto a ferramenta rodava
                while not thought_queue.empty():
                    yield {"thought": thought_queue.get_nowait()}

                try:
                    item_type, item = chunk_queue.get(timeout=30)
                except _queue.Empty:
                    # Timeout de 30s sem chunk → keepalive para manter conexão viva
                    yield {"keepalive": True}
                    continue

                if item_type == "done":
                    # Drena pensamentos restantes antes de encerrar
                    while not thought_queue.empty():
                        yield {"thought": thought_queue.get_nowait()}
                    break
                if item_type == "error":
                    raise item

                chunk = item
                if isinstance(chunk, dict):
                    if "actions" in chunk:
                        for action in chunk["actions"]:
                            label = self._action_to_human_label(action)
                            if label:
                                yield {"thought": label}

                    if "output" in chunk and chunk["output"]:
                        yield {"content": str(chunk["output"])}
                else:
                    if chunk:
                        yield str(chunk)
            return

        if hasattr(self.model, "chat_stream"):
            params = self._build_generation_params(request_data)
            yield from self.model.chat_stream(messages=messages, **params)
            return

        response = self.chat(messages=messages, model=model, request_data=request_data)
        if isinstance(response, dict):
            yield {"content": self._extract_chat_output(response)}
            if "thought" in response:
                yield {"thought": str(response.get("thought", ""))}
            return

        yield self._extract_chat_output(response)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Agent"):
            raise TypeError(
                f"Subclasses de Agent devem terminar com 'Agent' (encontrado: '{cls.__name__}'). "
                f"Renomeie para '{cls.__name__}Agent'."
            )
        cls()

    def __init__(self):
        """Inicializa e registra o agente no servidor singleton."""
        from server.server import Server

        self._resolve_model()
        model_source = self.model

        self.agent_definition = (
            getattr(self, "agent_definition", None)
            or getattr(self, "definition", None)
            or getattr(self, "mcp_definition", None)
        )

        self.name = getattr(model_source, "name", None) or model_source.__class__.__name__

        if not self.agent_definition and self.name:
            self.agent_definition = {
                "name": self.name,
                "description": getattr(self, "description", None) or getattr(model_source, "description", ""),
                "parameters": {},
                "returns": {},
            }

        if not self.agent_definition:
            raise ValueError(
                f"{self.__class__.__name__}: agent_definition (or definition/mcp_definition) is required"
            )

        self.definition = self.agent_definition
        self.mcp_definition = self.agent_definition

        self.name = self.name or self.agent_definition.get("name") or model_source.__class__.__name__
        if not self.agent_definition.get("name"):
            self.agent_definition["name"] = self.name

        # Compatibilidade retroativa para código legado que ainda lê model_id.
        self.model_id = self.name

        declared_aliases = getattr(self, "model_aliases", None)
        if declared_aliases is None:
            declared_aliases = getattr(model_source, "model_aliases", []) if model_source else []
        self.model_aliases = list(declared_aliases or [])

        self.owned_by = (
            getattr(self, "owned_by", None)
            or (getattr(model_source, "owned_by", None) if model_source else None)
            or "zeus"
        )
        self.created = int(getattr(self, "created", dt.datetime.now(dt.timezone.utc).timestamp()))

        declared_urls = getattr(self, "urls", None)
        declared_url = getattr(self, "url", None)
        if declared_urls is None:
            self.urls = [declared_url] if declared_url else []
        else:
            if not isinstance(declared_urls, (list, tuple)) or len(declared_urls) == 0:
                raise ValueError(f"{self.__class__.__name__}: urls must be a non-empty list/tuple")

            self.urls = []
            for route in declared_urls:
                if not isinstance(route, str) or not route.strip():
                    raise ValueError(f"{self.__class__.__name__}: each url in urls must be a non-empty string")
                self.urls.append(route)

        self.url = self.urls[0] if self.urls else None

        server = Server.get_instance()

        if self.urls:
            self.method = getattr(self, "method", None)
            if not self.method:
                raise ValueError(f"{self.__class__.__name__}: method is required for tool routes")

            if not getattr(self, "callback", None):
                raise ValueError(f"{self.__class__.__name__}: callback is required for tool routes")

            for idx, route in enumerate(self.urls):
                endpoint_name = self.agent_definition["name"] if idx == 0 else f"{self.agent_definition['name']}__{idx}"
                server.app.add_url_rule(
                    route,
                    endpoint_name,
                    self._tool_callback,
                    methods=[self.method],
                )

            server.register_url_handler(self)

        server.register_chat_agent(self)



