# tools/ — Utilitários

Funções puras (stateless) de uso transversal. Nenhum módulo aqui depende de outro dentro de `tools/` — são utilidades independentes importadas onde necessário.

---

## Módulos

| Arquivo | Descrição |
|---------|-----------|
| `parsing.py` | Extração de IDs de estruturas aninhadas |
| `dates.py` | Normalização de formatos de data |
| `messages.py` | Normalização de mensagens OpenAI |
| `toon.py` | Codificação no formato TOON |
| `grouping.py` | Agrupamento recursivo de DataFrames |
| `env_bootstrap.py` | Limpeza de variáveis de ambiente |

---

## `parsing.py`

### `extract_pic_ids(data)`

Percorre recursivamente uma estrutura (dict, list, aninhamentos) e retorna todos os valores encontrados nas chaves `pic_id` ou `pic_id_list`.

```python
from tools.parsing import extract_pic_ids

resposta = {
    "parques": [
        {"pic_id": 1001, "status": "offline"},
        {"pic_id_list": [1002, 1003], "tipo": "lora"},
    ]
}

extract_pic_ids(resposta)  # → [1001, 1002, 1003]
```

### `safe_int(value)`

Conversão segura para `int` — retorna `None` em caso de falha, sem lançar exceção.

| Entrada | Saída |
|---------|-------|
| `"42"` | `42` |
| `"abc"` | `None` |
| `None` | `None` |

---

## `dates.py`

### `normalize_reference_date(reference_date)`

| Entrada | Saída |
|---------|-------|
| `"2025-01-15"` | `"2025-01-15T00:00:00Z"` |
| `datetime(2025, 1, 15, 10, 0)` | `"2025-01-15T10:00:00Z"` |
| `date(2025, 1, 15)` | `"2025-01-15T00:00:00Z"` |
| `None` | `None` |

---

## `messages.py`

### `normalize_message_content(content)`

Converte qualquer formato de `content` OpenAI para string simples.

| Entrada | Saída |
|---------|-------|
| `"Olá"` | `"Olá"` |
| `[{"type": "text", "text": "Analise:"}, {"type": "image_url", ...}]` | `"Analise:"` |

### `extract_last_user_message(messages)`

Retorna o conteúdo do último `role: "user"` na lista de mensagens.

```python
messages = [
    {"role": "system",    "content": "Você é um assistente"},
    {"role": "user",      "content": "Olá"},
    {"role": "assistant", "content": "Oi!"},
    {"role": "user",      "content": "Me ajude com X"},
]

extract_last_user_message(messages)  # → "Me ajude com X"
```

Usada pelo `Server` e `Agent` para extrair o input atual antes de passar ao LangChain.

---

## `toon.py`

### `encode_toon(df, name, datetimes, columns_agrupation)`

Converte um `pandas.DataFrame` para string no formato TOON — texto estruturado otimizado para leitura por LLMs.

```python
from tools.toon import encode_toon
import pandas as pd

df = pd.DataFrame([
    {"pic_id": 1001, "status": "offline", "cliente": "Acme"},
    {"pic_id": 1002, "status": "online",  "cliente": "Acme"},
])

texto = encode_toon(df, name="PICs Diagnóstico")
```

Usado pelo `MCPDiagnosisService` para formatar respostas antes de passá-las ao LLM.

---

## `grouping.py`

### `recursive_grouping(df, cols)`

Agrupa um DataFrame recursivamente pelas colunas especificadas, retornando dict aninhado.

```python
from tools.grouping import recursive_grouping
import pandas as pd

df = pd.DataFrame([
    {"cliente": "Acme", "status": "offline", "pic_id": 1001},
    {"cliente": "Acme", "status": "online",  "pic_id": 1002},
    {"cliente": "Beta", "status": "offline", "pic_id": 2001},
])

recursive_grouping(df, cols=["cliente", "status"])
# → {
#     "Acme": {"offline": [...], "online": [...]},
#     "Beta": {"offline": [...]}
#   }
```

---

## `env_bootstrap.py`

### `strip_secret_env_vars()`

Remove espaços em branco e `\n` de variáveis de ambiente críticas. O GCP Secret Manager injeta newlines no final dos valores — sem esta limpeza, autenticação e chaves de API falham silenciosamente.

Variáveis limpas: `OPENAI_API_KEY`, `TAVILY_API_KEY`, `RAGIE_API_KEY`, `MCP_DIAGNOSIS_AUTH_TOKEN`, `AUTH_API_KEY`, etc.

Chamada em `main.py` e `wsgi.py` imediatamente após `load_dotenv()`, antes de qualquer importação de serviços.

---

## Exemplo Completo de Uso

Cenário: processar a resposta do MCP Diagnosis Service — extrair IDs, normalizar datas, formatar para o LLM e agrupar resultados para análise.

### 1. `parsing.py` — extrair IDs de resposta aninhada

```python
from tools.parsing import extract_pic_ids, safe_int

# Resposta típica do MCP Diagnosis (estrutura aninhada)
resposta_mcp = {
    "parques": [
        {
            "nome": "Parque Solar Alpha",
            "clientes": [
                {
                    "cliente_id": 42,
                    "pics_offline": [
                        {"pic_id": 1001, "status": "offline"},
                        {"pic_id": 1002, "status": "offline"},
                    ],
                },
                {
                    "cliente_id": 55,
                    "pic_id_list": [2001, 2002, 2003],
                },
            ],
        },
        {
            "nome": "Parque Solar Beta",
            "pic_id": 3001,   # único na raiz
        },
    ]
}

ids = extract_pic_ids(resposta_mcp)
print(f"IDs encontrados: {ids}")
# → [1001, 1002, 2001, 2002, 2003, 3001]

# safe_int — converter parâmetros de entrada HTTP sem risco de exceção
params = {"pic_id": "1001", "limite": "abc", "cliente": None}
pic_id  = safe_int(params["pic_id"])   # → 1001
limite  = safe_int(params["limite"])  # → None  (sem exceção)
cliente = safe_int(params["cliente"]) # → None
```

### 2. `dates.py` — normalizar datas de entrada

```python
from tools.dates import normalize_reference_date
from datetime import datetime, date

# Formatos aceitos pelo sistema
print(normalize_reference_date("2025-04-09"))
# → "2025-04-09T00:00:00Z"

print(normalize_reference_date(datetime(2025, 4, 9, 14, 30, 0)))
# → "2025-04-09T14:30:00Z"

print(normalize_reference_date(date(2025, 4, 9)))
# → "2025-04-09T00:00:00Z"

print(normalize_reference_date(None))
# → None  (MCP usa data atual como padrão)

# Uso prático: normalizar datas vindas da API antes de enviar ao MCP
def processar_request(reference_date_raw):
    ref_normalizado = normalize_reference_date(reference_date_raw)
    return mcp.get_park_info(reference_date=ref_normalizado)
```

### 3. `messages.py` — normalizar mensagens OpenAI

```python
from tools.messages import normalize_message_content, extract_last_user_message

# Conteúdo multimodal (texto + imagem) → extrai apenas texto
content_multimodal = [
    {"type": "text",      "text": "Analise a imagem do PIC abaixo:"},
    {"type": "image_url", "image_url": {"url": "https://..."}},
]
texto = normalize_message_content(content_multimodal)
print(texto)  # → "Analise a imagem do PIC abaixo:"

# Conteúdo simples — retorna direto
texto_simples = normalize_message_content("Qual o status do parque Alpha?")
print(texto_simples)  # → "Qual o status do parque Alpha?"

# Extrair a última mensagem do usuário (input para o LLM)
historico = [
    {"role": "system",    "content": "Você é Athena, assistente de diagnóstico."},
    {"role": "user",      "content": "Quais PICs estão offline?"},
    {"role": "assistant", "content": "Há 3 PICs offline no parque Alpha..."},
    {"role": "user",      "content": "E no parque Beta?"},
]
ultimo_input = extract_last_user_message(historico)
print(ultimo_input)  # → "E no parque Beta?"
```

### 4. `toon.py` — formatar DataFrame para o LLM

```python
import pandas as pd
from tools.toon import encode_toon

# DataFrame de resultado do diagnóstico
df_diagnostico = pd.DataFrame([
    {"pic_id": 1001, "status": "offline", "cliente": "Acme",  "ultimo_sinal": "2025-04-07 10:22", "bateria_%": 12},
    {"pic_id": 1002, "status": "offline", "cliente": "Acme",  "ultimo_sinal": "2025-04-06 08:15", "bateria_%": 8},
    {"pic_id": 2001, "status": "standby", "cliente": "Beta",  "ultimo_sinal": "2025-04-09 06:00", "bateria_%": 95},
    {"pic_id": 3001, "status": "online",  "cliente": "Gamma", "ultimo_sinal": "2025-04-09 14:30", "bateria_%": 78},
])

# Formatar para contexto do LLM (compacto, estruturado)
toon = encode_toon(
    df_diagnostico,
    name="Diagnóstico de PICs",
    datetimes=["ultimo_sinal"],
    columns_agrupation=["cliente", "status"],
)
print(toon)
# → Diagnóstico de PICs
#     Acme
#       offline
#         [1001] bateria_% = 12 | ultimo_sinal = 2025-04-07 10:22
#         [1002] bateria_% =  8 | ultimo_sinal = 2025-04-06 08:15
#     Beta
#       standby
#         [2001] bateria_% = 95 | ...
#     Gamma
#       online
#         [3001] bateria_% = 78 | ...
```

### 5. `grouping.py` — agrupar dados para análise

```python
import pandas as pd
from tools.grouping import recursive_grouping

df = pd.DataFrame([
    {"regiao": "Norte", "cliente": "Acme",  "status": "offline", "pic_id": 1001},
    {"regiao": "Norte", "cliente": "Acme",  "status": "offline", "pic_id": 1002},
    {"regiao": "Norte", "cliente": "Beta",  "status": "online",  "pic_id": 2001},
    {"regiao": "Sul",   "cliente": "Gamma", "status": "offline", "pic_id": 3001},
    {"regiao": "Sul",   "cliente": "Gamma", "status": "standby", "pic_id": 3002},
])

hierarquia = recursive_grouping(df, cols=["regiao", "cliente", "status"])
print(hierarquia)
# {
#   "Norte": {
#     "Acme":  {"offline": [{"pic_id": 1001, ...}, {"pic_id": 1002, ...}]},
#     "Beta":  {"online":  [{"pic_id": 2001, ...}]},
#   },
#   "Sul": {
#     "Gamma": {
#       "offline": [{"pic_id": 3001, ...}],
#       "standby": [{"pic_id": 3002, ...}],
#     }
#   }
# }

# Contar offline por região
for regiao, clientes in hierarquia.items():
    total_offline = sum(
        len(statuses.get("offline", []))
        for statuses in clientes.values()
    )
    print(f"{regiao}: {total_offline} offline")
# Norte: 2 offline
# Sul:   1 offline
```

### 6. `env_bootstrap.py` — limpar variáveis de ambiente no startup

```python
# main.py / wsgi.py — chamada obrigatória antes de qualquer import de serviços
from dotenv import load_dotenv
load_dotenv()

from tools.env_bootstrap import strip_secret_env_vars
strip_secret_env_vars()
# Remove \n e espaços do final de: OPENAI_API_KEY, RAGIE_API_KEY, etc.
# Necessário porque o GCP Secret Manager injeta newlines ao final dos valores

# Só então importar os módulos que usam as variáveis
import agents  # noqa — dispara o auto-registro de todos os agentes
```

---

## Como Adicionar um Novo Utilitário

1. Crie `tools/meu_utilitario.py`
2. Implemente funções puras com type hints
3. Não importe nada de `agents/`, `models/`, `server/`, `services/`

```python
# tools/meu_utilitario.py
from typing import Any, List


def minha_funcao(dados: List[Any]) -> dict:
    """
    Descrição do que faz.

    Args:
        dados: Lista de entradas.

    Returns:
        Dicionário processado.
    """
    if not dados:
        return {}
    return {str(item): True for item in dados}
```
