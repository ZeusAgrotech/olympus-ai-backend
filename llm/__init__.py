"""
Módulo LLM com auto-discovery e registro automático de passthroughs.

Ao importar este módulo:
  1. Todos os arquivos .py em llm/ são importados, disparando o auto-registro
     de cada classe BaseLLM no REGISTRY via __init_subclass__.
  2. Modelos com passthrough=True e hide=False são automaticamente registrados
     no servidor como endpoints /v1/chat/completions (hidden=True no /v1/models).

Para adicionar um novo modelo passthrough, basta criar um arquivo em llm/:

    # llm/gemini_2_flash.py
    from llm.llm import BaseLLM

    class Gemini2FlashLLM(BaseLLM):
        model_name  = "gemini-2.0-flash"
        provider    = "google"
        env_key     = "GOOGLE_API_KEY"
        passthrough = True
        hide        = False

Isso é tudo. O endpoint /v1/chat/completions estará disponível automaticamente.
"""

import importlib
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from llm.llm import BaseLLM, REGISTRY, PassthroughProxy

# ---------------------------------------------------------------------------
# 1. Auto-discovery: importa todos os módulos LLM para disparar o registro
# ---------------------------------------------------------------------------

_llm_dir = Path(__file__).parent

for _file in _llm_dir.glob("*.py"):
    if _file.stem in ("__init__", "llm"):
        continue
    try:
        importlib.import_module(f".{_file.stem}", package="llm")
    except Exception as _e:
        print(f"[llm] erro ao importar {_file.stem}: {_e}")

# ---------------------------------------------------------------------------
# 2. Auto-registro: BaseLLM com passthrough=True e hide=False → endpoint direto
# ---------------------------------------------------------------------------

from server.server import Server as _Server

_server = _Server.get_instance()

for _model_name, _cls in REGISTRY.items():
    if not _cls.passthrough or _cls.hide:
        continue
    try:
        _server.register_chat_agent(PassthroughProxy(_cls))
    except Exception as _e:
        print(f"[llm] erro ao registrar passthrough '{_model_name}': {_e}")


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def LLM(model_name: str, **kwargs: Any) -> BaseChatModel:
    """
    Factory que retorna a instância LangChain do modelo solicitado.
    Usado pelos models LangChain (Athena, Saori, etc).

    Args:
        model_name: Nome do modelo conforme declarado em cada classe LLM.
        **kwargs:   Parâmetros de geração (temperature, max_tokens, etc.)
    """
    cls = REGISTRY.get(model_name)
    if cls is None:
        raise ValueError(
            f"LLM '{model_name}' não encontrado. "
            f"Disponíveis: {list(REGISTRY.keys())}"
        )
    return cls.build(**kwargs)


__all__ = ["LLM", "REGISTRY", "BaseLLM", "PassthroughProxy"]
