# olympus-ai-backend

Servidor Flask que expõe agentes de IA via API OpenAI-compatível (`/v1/chat/completions`, `/v1/models`).

## Arquitetura

### Agentes (`agents/`)
Cada arquivo em `agents/` define um agente declarativo que herda de `Agent`. O `agents/__init__.py` faz auto-discovery — basta criar o arquivo e o agente é registrado automaticamente no servidor.

Agente mínimo:
```python
from .agent import Agent
from models.meu_model import MeuModel

class MeuAgent(Agent):
    model    = MeuModel
    hidden   = False   # aparece no GET /v1/models
    owned_by = "Zeus"
```

### Models (`models/`)
Cada `Model` define o comportamento do agente: prompt, LLM, tools. Herda de `Model` (LangChain + AgentExecutor). O `models/__init__.py` também faz auto-discovery.

### LLMs (`llm/`)
`BaseLLM` define os modelos disponíveis para uso interno pelos agents LangChain (via factory `LLM("model-name")`).

Modelos com `passthrough=True` são adicionalmente expostos como endpoints diretos no servidor (sem lógica de agente — repassam mensagens direto ao provider). Esses modelos aparecem no `GET /v1/models` por padrão.

LLM passthrough com todas as opções:
```python
from llm.llm import BaseLLM

class MeuModeloLLM(BaseLLM):
    model_name    = "nome-do-modelo"
    provider      = "openai"          # "openai" | "google" | "anthropic"
    env_key       = "OPENAI_API_KEY"
    passthrough   = True              # expõe em /v1/chat/completions
    hidden        = False             # aparece no GET /v1/models (default: False)
    model_aliases = ["alias-1"]       # nomes alternativos aceitos no campo "model"
```

### Servidor (`server/server.py`)
Singleton Flask. Endpoints padrão:
- `GET /v1/models` — lista todos os modelos não-hidden (agents + passthroughs)
- `POST /v1/chat/completions` — chat OpenAI-compatível, roteia pelo campo `model`
- `GET /health`

O campo `model` na requisição é resolvido por nome exato ou por alias. Se só há um modelo registrado, o campo é opcional.

### Adapters (`llm/adapters/`)
Adaptam a interface de cada provider (OpenAI, Anthropic, Google) para o `PassthroughProxy`. Para adicionar um novo provider, crie um arquivo com uma classe decorada com `@register_adapter("nome")` herdando de `BaseAdapter`.

## Decisões relevantes

### `GET /passthrough` foi removido
Havia um endpoint separado `GET /passthrough` que listava apenas os modelos passthrough. Foi removido. Agora todos os modelos (agents e passthroughs) aparecem no mesmo `GET /v1/models`, controlados pelo atributo `hidden`. Motivação: manter a API 100% compatível com clientes OpenAI sem endpoints não-padrão.

### Visibilidade e aliases por modelo passthrough
`PassthroughProxy` agora lê `hidden` e `model_aliases` diretamente do `BaseLLM`, permitindo configuração por modelo sem alterar o proxy.
