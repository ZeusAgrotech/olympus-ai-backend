from .agent import Agent
from models.chatwoot import ChatwootModel

# Mapeamento dos event_names do Chatwoot Captain para instrução legível pelo modelo
_EVENT_INSTRUCTIONS = {
    "reply_suggestion": "INSTRUÇÃO: sugira uma resposta para o atendente enviar ao cliente.",
    "summarize": "INSTRUÇÃO: faça um resumo da conversa com análise de sentimentos e qualidade do atendimento.",
    "summary": "INSTRUÇÃO: faça um resumo da conversa com análise de sentimentos e qualidade do atendimento.",
}


class ChatwootAgent(Agent):
    """Agente de atendimento especializado para o Chatwoot, com acesso ao OneDrive."""

    model = ChatwootModel
    model_aliases = ["gpt-4.1-mini"]
    owned_by = "Zeus"
    hidden = True

    def _inject_event(self, request_data: dict) -> dict:
        """Prepend a instrução do event_name ao input do modelo."""
        request_data = dict(request_data or {})
        event_name = (request_data.get("event_name") or "").strip().lower()
        instruction = _EVENT_INSTRUCTIONS.get(event_name, "")
        if instruction:
            existing = request_data.get("_last_user_message") or ""
            request_data["_last_user_message"] = f"{instruction}\n\n{existing}".strip()
        return request_data

    def chat(self, messages, model, request_data=None):
        return super().chat(messages, model, self._inject_event(request_data))

    def chat_stream(self, messages, model, request_data=None):
        yield from super().chat_stream(messages, model, self._inject_event(request_data))
