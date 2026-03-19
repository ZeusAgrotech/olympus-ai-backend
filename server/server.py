from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS
from typing import Any, Callable, Dict, List, Optional, Tuple
import datetime as dt
from enum import Enum
import json
import time
import uuid

from auth.api_keys import validate_api_key
from tools.messages import normalize_message_content, extract_last_user_message


class Server:
    """
    Singleton que gerencia a instância do Flask e o registro declarativo de agentes.

    Uso:
        Server.get_instance().start()
    """

    # Se houver necessidade de reutilizacao fora do Server, mover este enum para o escopo do modulo.
    class ThoughtStreamMode(str, Enum):
        """Controla como pensamentos são enviados em respostas com stream=true."""

        HIDDEN = "hidden"
        CUSTOM = "custom"
        CONTENT = "content"

    _instance: Optional["Server"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.app = Flask(__name__)
        CORS(self.app)

        # Handlers de rotas de ferramentas.
        self.url_handlers: List[Any] = []

        # Registro de agentes de chat OpenAI-compatíveis.
        self.chat_model_registry: Dict[str, Dict[str, Any]] = {}
        self.chat_alias_registry: Dict[str, str] = {}

        @self.app.before_request
        def check_auth():
            # Rotas públicas
            if request.endpoint in ("health_check", "list_models"):
                return

            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return (
                    jsonify(
                        {
                            "error": "Unauthorized",
                            "message": "Missing or invalid Authorization header. Use 'Bearer <API_KEY>'.",
                        }
                    ),
                    401,
                )

            api_key = auth_header.split(" ", 1)[1].strip()

            if not api_key or not validate_api_key(api_key):
                return (
                    jsonify(
                        {
                            "error": "Unauthorized",
                            "message": "Invalid or missing API Key",
                        }
                    ),
                    401,
                )

        self._setup_default_routes()
        self._initialized = True

    @staticmethod
    def _openai_error_payload(
        message: str,
        *,
        error_type: str = "invalid_request_error",
        param: Optional[str] = None,
        code: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "message": message,
            "type": error_type,
            "param": param,
            "code": code,
        }
        return payload

    _normalize_message_content = staticmethod(normalize_message_content)
    _extract_last_user_message = staticmethod(extract_last_user_message)

    @staticmethod
    def _resolve_model_token_counter(agent: Any) -> Callable[[str], int]:
        model_obj = getattr(agent, "model", None)
        model_counter = getattr(model_obj, "_count_tokens", None)
        if not callable(model_counter):
            raise ValueError("Registered chat agent model must implement _count_tokens")

        return model_counter

    @staticmethod
    def _count_text_tokens(model_counter: Callable[[str], int], text: str) -> int:
        return int(model_counter(text))

    @staticmethod
    def _parse_stream_include_usage(stream: bool, stream_options: Any) -> bool:
        if not stream:
            return False

        if not isinstance(stream_options, dict):
            return False

        return bool(stream_options.get("include_usage", False))

    def _build_usage_error_response(self, exc: Exception):
        return (
            jsonify(
                {
                    "error": self._openai_error_payload(
                        str(exc),
                        error_type="server_error",
                        code="usage_count_failed",
                    )
                }
            ),
            500,
        )

    def _build_usage_payload(
        self,
        *,
        agent: Any,
        messages: List[Dict[str, Any]],
        content_text: str,
        thought_text: Optional[str] = None,
    ) -> Dict[str, int]:
        model_counter = self._resolve_model_token_counter(agent)

        prompt_parts: List[str] = []
        for message in messages:
            role = str(message.get("role", "")).strip()
            content = self._normalize_message_content(message.get("content", ""))

            if role and content:
                prompt_parts.append(f"{role}: {content}")
            elif content:
                prompt_parts.append(content)

        prompt_text = "\n".join(prompt_parts)

        completion_parts = [content_text]
        if thought_text:
            completion_parts.append(thought_text)
        completion_text = "\n".join([part for part in completion_parts if part])

        prompt_tokens = self._count_text_tokens(model_counter, prompt_text)
        completion_tokens = self._count_text_tokens(model_counter, completion_text)

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    @staticmethod
    def _parse_thought_stream_mode(raw_value: Any) -> "Server.ThoughtStreamMode":
        if raw_value is None:
            return Server.ThoughtStreamMode.CONTENT

        raw_text = str(raw_value).strip().lower()
        if raw_text == "":
            return Server.ThoughtStreamMode.CONTENT

        try:
            return Server.ThoughtStreamMode(raw_text)
        except ValueError as exc:
            raise ValueError(
                "Invalid thought_stream_mode. Allowed values: hidden, custom, content"
            ) from exc

    def _resolve_chat_agent(
        self, requested_model: Optional[str]
    ) -> Tuple[Optional[str], Optional[Any], Optional[str]]:
        if not self.chat_model_registry:
            return None, None, "No chat models are registered"

        if requested_model:
            if requested_model in self.chat_model_registry:
                return (
                    requested_model,
                    self.chat_model_registry[requested_model]["agent"],
                    None,
                )

            alias_target = self.chat_alias_registry.get(requested_model)
            if alias_target:
                return (
                    alias_target,
                    self.chat_model_registry[alias_target]["agent"],
                    None,
                )

            return None, None, f"Model '{requested_model}' not found"

        if len(self.chat_model_registry) == 1:
            default_model = next(iter(self.chat_model_registry))
            return default_model, self.chat_model_registry[default_model]["agent"], None

        return None, None, "Model is required when multiple models are available"

    def _setup_default_routes(self):
        """Configura rotas padrão OpenAI-compatíveis e health-check."""

        @self.app.route("/models", methods=["GET"])
        @self.app.route("/v1/models", methods=["GET"])
        def list_models():
            models_data = []

            for model_id, meta in self.chat_model_registry.items():
                if meta.get("hidden"):
                    continue

                models_data.append(
                    {
                        "id": model_id,
                        "object": "model",
                        "created": meta["created"],
                        "owned_by": meta["owned_by"],
                    }
                )

                for alias in meta["aliases"]:
                    models_data.append(
                        {
                            "id": alias,
                            "object": "model",
                            "created": meta["created"],
                            "owned_by": meta["owned_by"],
                        }
                    )

            return jsonify({"object": "list", "data": models_data})

        @self.app.route("/chat/completions", methods=["POST"])
        @self.app.route("/v1/chat/completions", methods=["POST"])
        def chat_completions():
            data = request.get_json(silent=True) or {}
            messages = data.get("messages")
            stream = bool(data.get("stream", False))
            stream_include_usage = self._parse_stream_include_usage(stream, data.get("stream_options"))

            try:
                thought_stream_mode = self._parse_thought_stream_mode(data.get("thought_stream_mode"))
            except ValueError as e:
                return (
                    jsonify(
                        {
                            "error": self._openai_error_payload(
                                str(e),
                                param="thought_stream_mode",
                                code="invalid_thought_stream_mode",
                            )
                        }
                    ),
                    400,
                )

            if not isinstance(messages, list) or len(messages) == 0:
                return (
                    jsonify(
                        {
                            "error": self._openai_error_payload(
                                "No messages provided",
                                param="messages",
                                code="messages_required",
                            )
                        }
                    ),
                    400,
                )

            requested_model = data.get("model")
            resolved_model, agent, resolve_error = self._resolve_chat_agent(requested_model)
            if resolve_error:
                return (
                    jsonify(
                        {
                            "error": self._openai_error_payload(
                                resolve_error,
                                param="model",
                                code="model_not_found",
                            )
                        }
                    ),
                    400,
                )

            request_data = dict(data)
            request_data["_last_user_message"] = self._extract_last_user_message(messages)

            if stream:
                res_id = f"chatcmpl-{uuid.uuid4()}"
                created = int(time.time())

                def send_chunk(
                    content: Optional[str] = None,
                    finish_reason: Optional[str] = None,
                    delta: Optional[Dict[str, Any]] = None,
                ) -> str:
                    if delta is None:
                        delta = {} if content is None else {"content": content}

                    chunk_data = {
                        "id": res_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": resolved_model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": delta,
                                "finish_reason": finish_reason,
                            }
                        ],
                    }
                    return f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

                def send_usage_chunk(usage: Dict[str, int]) -> str:
                    chunk_data = {
                        "id": res_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": resolved_model,
                        "choices": [],
                        "usage": usage,
                    }
                    return f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

                def generate():
                    stream_content_parts: List[str] = []
                    stream_thought_parts: List[str] = []
                    thinking_open = False  # controla se um bloco <think> está aberto

                    def close_thinking():
                        nonlocal thinking_open
                        if thinking_open:
                            thinking_open = False
                            return send_chunk("\n</think>", None)
                        return None

                    try:
                        for chunk in agent.chat_stream(
                            messages=messages,
                            model=resolved_model,
                            request_data=request_data,
                        ):
                            if isinstance(chunk, dict):
                                if chunk.get("keepalive"):
                                    yield ": keepalive\n\n"
                                    continue

                                if "content" in chunk and chunk.get("content") is not None:
                                    content_piece = str(chunk.get("content"))
                                    if content_piece:
                                        # Fecha o bloco de pensamento antes de emitir conteúdo
                                        closing = close_thinking()
                                        if closing:
                                            yield closing
                                        stream_content_parts.append(content_piece)
                                        yield send_chunk(content_piece, None)

                                if "thought" in chunk:
                                    thought_piece = str(chunk.get("thought", ""))
                                    if thought_piece:
                                        stream_thought_parts.append(thought_piece)

                                    if thought_stream_mode == Server.ThoughtStreamMode.CUSTOM:
                                        yield send_chunk(None, None, delta={"reasoning": thought_piece})
                                    elif thought_stream_mode == Server.ThoughtStreamMode.CONTENT and thought_piece:
                                        thought_line = f"• {thought_piece}..."
                                        if not thinking_open:
                                            # Abre o bloco <think> uma única vez
                                            thinking_open = True
                                            yield send_chunk(f"<think>\n{thought_line}", None)
                                        else:
                                            # Adiciona ao bloco já aberto, separado por linha
                                            yield send_chunk(f"\n{thought_line}", None)

                                continue

                            if chunk:
                                chunk_text = str(chunk)
                                stream_content_parts.append(chunk_text)
                                yield send_chunk(chunk_text, None)

                        closing = close_thinking()
                        if closing:
                            yield closing

                        if stream_include_usage:
                            usage = self._build_usage_payload(
                                agent=agent,
                                messages=messages,
                                content_text="".join(stream_content_parts),
                                thought_text="\n".join(stream_thought_parts) or None,
                            )

                        yield send_chunk(None, "stop")
                        if stream_include_usage:
                            yield send_usage_chunk(usage)
                        yield "data: [DONE]\n\n"
                    except Exception as e:
                        error_data = {
                            "error": self._openai_error_payload(
                                str(e),
                                error_type="server_error",
                                code="internal_error",
                            )
                        }
                        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                        yield "data: [DONE]\n\n"

                return Response(stream_with_context(generate()), mimetype="text/event-stream")

            try:
                content = agent.chat(
                    messages=messages,
                    model=resolved_model,
                    request_data=request_data,
                )
            except Exception as e:
                return (
                    jsonify(
                        {
                            "error": self._openai_error_payload(
                                str(e),
                                error_type="server_error",
                                code="internal_error",
                            )
                        }
                    ),
                    500,
                )

            thought = None
            content_text = ""
            if isinstance(content, dict):
                content_text = str(content.get("output", ""))
                if "thought" in content:
                    thought = str(content.get("thought", ""))
            else:
                content_text = str(content)

            res_id = f"chatcmpl-{uuid.uuid4()}"
            created = int(time.time())
            response_payload = {
                "id": res_id,
                "object": "chat.completion",
                "created": created,
                "model": resolved_model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content_text},
                        "finish_reason": "stop",
                    }
                ],
            }

            try:
                response_payload["usage"] = self._build_usage_payload(
                    agent=agent,
                    messages=messages,
                    content_text=content_text,
                    thought_text=thought,
                )
            except Exception as e:
                return self._build_usage_error_response(e)

            if thought is not None:
                response_payload["thought"] = thought

            return jsonify(response_payload)

        @self.app.route("/health", methods=["GET"])
        def health_check():
            return jsonify(
                {
                    "status": "healthy",
                    "server": "Flask Agents Server",
                    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                }
            )

    def register_url_handler(self, handler):
        """Registra um handler de endpoint de ferramenta."""
        self.url_handlers.append(handler)

    def register_chat_agent(self, agent):
        """Registra um agente de chat para roteamento em /chat/completions."""
        model_name = getattr(agent, "name", None)
        if not model_name or not isinstance(model_name, str):
            raise ValueError(f"{agent.__class__.__name__}: name must be a non-empty string")

        if model_name in self.chat_model_registry or model_name in self.chat_alias_registry:
            raise ValueError(f"Duplicate model name registration: {model_name}")

        aliases = list(getattr(agent, "model_aliases", []) or [])
        normalized_aliases = []
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip():
                raise ValueError(f"{agent.__class__.__name__}: invalid model alias '{alias}'")
            if alias == model_name:
                continue
            if alias in self.chat_model_registry or alias in self.chat_alias_registry:
                raise ValueError(f"Duplicate model alias registration: {alias}")
            normalized_aliases.append(alias)
            self.chat_alias_registry[alias] = model_name

        self.chat_model_registry[model_name] = {
            "agent": agent,
            "created": int(getattr(agent, "created", time.time())),
            "owned_by": getattr(agent, "owned_by", "zeus"),
            "aliases": normalized_aliases,
            "hidden": bool(getattr(agent, "hidden", False)),
        }

    def start(self, host="0.0.0.0", port=5000, debug=True):
        """Inicia o servidor Flask."""
        print("Starting Flask Agents Server...")
        print("Available endpoints:")
        print("   - GET  /models              - OpenAI-compatible model listing")
        print("   - GET  /v1/models           - OpenAI-compatible model listing")
        print("   - POST /chat/completions    - OpenAI-compatible chat completions")
        print("   - POST /v1/chat/completions - OpenAI-compatible chat completions")
        print("   - GET  /health              - Health check")

        print("\nAvailable models:")
        if not self.chat_model_registry:
            print("   - (none)")
        else:
            for model_id, meta in self.chat_model_registry.items():
                print(f"   - {model_id}")
                for alias in meta["aliases"]:
                    print(f"     alias: {alias}")

        print("\nAvailable tool routes:")
        if not self.url_handlers:
            print("   - (none)")
        else:
            for handler in self.url_handlers:
                print(f"   - {handler.agent_definition.get('name')} -> {handler.url}")

        print("\n" + "=" * 50)
        self.app.run(host=host, port=port, debug=debug)

    @classmethod
    def get_instance(cls) -> "Server":
        return cls()