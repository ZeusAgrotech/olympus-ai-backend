# Design: Apollo Intelligence — Rebranding e Nova Arquitetura

**Data:** 2026-05-14
**Status:** Aprovado

---

## Contexto

O sistema atual consiste em dois serviços:

- `olympus-ai-backend` — servidor Flask OpenAI-compatível com agentes LLM (LangChain, RAG, MCP)
- `olympus-ai-frontend` — LibreChat apontando diretamente para o backend

O objetivo é introduzir uma camada intermediária (`app-apollo-server`) entre o frontend e o backend central de agentes, permitir controle de modelos por ambiente, e renomear os serviços para refletir a nova identidade de produto (Apollo Intelligence).

---

## Arquitetura Geral

```
app-apollo-frontend  (LibreChat, renomeado)
        │
        │  GET  /v1/models
        │  POST /v1/chat/completions
        ▼
app-apollo-server    (novo — Python/Flask, OpenAI-compatible)
        │  filtra modelos por ALLOWED_MODELS
        │  valida modelo no body antes de repassar
        │  repassa payload ao olympus sem modificação
        ▼
olympus-ai-server    (renomeado de olympus-ai-backend)
        │  agentes: Athena, Saori, OneDrive, WebSearch, Chatwoot...
        ▼
   LLMs / Tools / RAG / MCP
```

### Filtragem por ambiente

| Ambiente | `ALLOWED_MODELS` no apollo-server | Modelos visíveis no frontend |
|----------|----------------------------------|------------------------------|
| prod     | `OneDrive,WebSearch`             | Apenas OneDrive e WebSearch  |
| accept   | `*`                              | Todos os agentes do olympus  |
| local    | `*`                              | Todos                        |

---

## Componente 1 — `app-apollo-server` (novo)

### Estrutura de arquivos

```
app-apollo-server/
├── main.py                        # entrypoint local (igual ao olympus)
├── wsgi.py                        # entrypoint gunicorn (igual ao olympus)
├── server/
│   ├── __init__.py
│   └── server.py                  # Flask singleton — mesmo padrão do olympus
├── proxy/
│   ├── __init__.py
│   └── olympus.py                 # cliente HTTP para olympus-ai-server
├── tools/
│   ├── __init__.py
│   └── env_bootstrap.py           # mesmo padrão do olympus
├── requirements.txt
├── Dockerfile
├── cloudbuild.yaml
├── ci/
│   ├── cloudbuild-trigger-accept.yaml
│   └── cloudbuild-trigger-prod.yaml
├── .env.example
├── run.sh
├── stop.sh
└── install.sh
```

### Variáveis de ambiente

| Variável               | Prod                   | Accept | Local                   |
|------------------------|------------------------|--------|-------------------------|
| `OLYMPUS_SERVER_URL`   | URL Cloud Run prod     | URL Cloud Run accept | `http://localhost:6001` |
| `OLYMPUS_SERVER_AUTH_KEY` | secret              | secret | valor local             |
| `AUTH_API_KEY`         | secret                 | secret | valor local             |
| `ALLOWED_MODELS`       | `OneDrive,WebSearch`   | `*`    | `*`                     |
| `ENVIRONMENT`          | `prod`                 | `accept` | `local`               |
| `PORT`                 | `8080`                 | `8080` | `6002`                  |

### Comportamento dos endpoints

**`GET /v1/models`**
1. Chama `olympus-ai-server GET /v1/models`
2. Se `ALLOWED_MODELS == *`, devolve lista completa
3. Caso contrário, filtra mantendo apenas os modelos cujo `id` está em `ALLOWED_MODELS`
4. Retorna no formato OpenAI (`{"object": "list", "data": [...]}`)

**`POST /v1/chat/completions`**
1. Extrai campo `model` do body JSON
2. Valida que `model` está em `ALLOWED_MODELS` (ou que `ALLOWED_MODELS == *`)
3. Se inválido → retorna 400 no padrão OpenAI (`model_not_allowed`)
4. Se válido → repassa payload inteiro para `olympus-ai-server POST /v1/chat/completions`
5. Suporta streaming (SSE) — repassa chunks diretamente sem buffer

**`GET /health`**
Resposta padrão de health check (mesmo padrão do olympus).

### Padrões herdados do olympus

- Bearer auth via `AUTH_API_KEY` (mesma lógica de `_validate_api_key`)
- Flask singleton (`Server.get_instance()`)
- `strip_secret_env_vars` no boot
- Gunicorn + Dockerfile multi-stage (mesma base)
- `cloudbuild.yaml` com triggers separados por ambiente

### Expansibilidade

A camada `proxy/olympus.py` pode crescer para outros endpoints futuros (ex: `/v1/embeddings`, endpoints customizados). O padrão é: nova rota no `server.py` → novo método no `proxy/olympus.py`.

---

## Componente 2 — `olympus-ai-server` (renomeado)

Zero mudança de comportamento. Apenas renomeação:

| Item                        | De                        | Para                   |
|-----------------------------|---------------------------|------------------------|
| Repo GitHub                 | `olympus-ai-backend`      | `olympus-ai-server`    |
| `_SERVICE_NAME` cloudbuild  | `olympus-ai-backend`      | `olympus-ai-server`    |
| `_ARTIFACT_REPO` cloudbuild | `olympus-ai-backend`      | `olympus-ai-server`    |
| Secret auth (env var)       | `AUTH_API_KEY=OLYMPUS_AUTH_API_KEY` | `AUTH_API_KEY=OLYMPUS_SERVER_AUTH_KEY` |
| Cloud Run service           | `olympus-ai-backend`      | `olympus-ai-server`    |

---

## Componente 3 — `app-apollo-frontend` (renomeado)

| Item                        | De                              | Para                        |
|-----------------------------|---------------------------------|-----------------------------|
| Repo GitHub                 | `olympus-ai-frontend`           | `app-apollo-frontend`       |
| `_SERVICE_NAME` cloudbuild  | `olympus-ai-frontend`           | `app-apollo-frontend`       |
| `APP_TITLE` (env var)       | `Olympus`                       | `Apollo`                    |
| `OLYMPUS_BASE_URL` (env var)| URL do olympus-backend          | URL do apollo-server        |
| `OLYMPUS_AUTH_API_KEY` (secret) | chave do olympus            | `APOLLO_AUTH_API_KEY`       |
| `_AGENTS_LIST` cloudbuild   | `"OneDrive,WebSearch"`          | **removido**                |
| `fetch` no `librechat.yaml` | `false`                         | `true` (apollo-server é leve, sem cold start) |
| Cloud Run service           | `olympus-ai-frontend`           | `app-apollo-frontend`       |

**Motivo do `fetch: true`:** O problema de cold start era causado pelo `olympus-ai-backend` (pesado: LangChain, Weaviate). O `app-apollo-server` é um proxy leve (Flask + httpx) que sobe em segundos, eliminando o problema. A filtragem de modelos passa a ser responsabilidade do apollo-server via `ALLOWED_MODELS`.

---

## Componente 4 — `chronos-diagnosis` (Cloud Run Job)

O job chama o olympus diretamente (sem passar pelo apollo-server). Apenas os **valores** dos secrets precisam ser atualizados — a configuração do job em si não muda.

| Secret Manager         | Projeto      | Ação                                    |
|------------------------|--------------|-----------------------------------------|
| `OLYMPUS_BASE_URL`     | zeus-prod    | Atualizar valor → URL do `olympus-ai-server` prod |
| `OLYMPUS_BASE_URL`     | zeus-accept  | Atualizar valor → URL do `olympus-ai-server` accept |
| `OLYMPUS_AUTH_KEY`     | zeus-prod    | Atualizar valor → nova chave do olympus-server |
| `OLYMPUS_AUTH_KEY`     | zeus-accept  | Atualizar valor → nova chave do olympus-server |

---

## Fases de Execução

### Fase 1 — Local

1. Renomear repo `olympus-ai-backend` → `olympus-ai-server` (GitHub + clone local)
2. Atualizar `cloudbuild.yaml` do olympus-ai-server (service name + artifact repo)
3. Implementar `app-apollo-server` (repo já existe vazio)
4. Renomear repo `olympus-ai-frontend` → `app-apollo-frontend` (GitHub + clone local)
5. Atualizar frontend: `APP_TITLE`, URL do backend, `fetch: true`, remover `_AGENTS_LIST`
6. Testar localmente:
   - `olympus-ai-server` em `:6001`
   - `app-apollo-server` em `:6002`
   - `app-apollo-frontend` em `:3000`

### Fase 2 — Cloud Run (blue/green)

1. Criar Artifact Registry repos: `olympus-ai-server`, `app-apollo-server`, `app-apollo-frontend`
2. Criar secrets no Secret Manager: `OLYMPUS_SERVER_AUTH_KEY`, `APOLLO_AUTH_API_KEY`
3. Deploy `olympus-ai-server` (prod + accept)
4. Deploy `app-apollo-server` (prod + accept)
5. Deploy `app-apollo-frontend` (prod + accept)
6. Reconfigurar URL customizada do frontend para o novo serviço
7. Smoke test nos novos serviços
8. Atualizar valores de `OLYMPUS_BASE_URL` e `OLYMPUS_AUTH_KEY` no Secret Manager (prod + accept) para o `chronos-diagnosis`
9. Deletar serviços antigos: `olympus-ai-backend`, `olympus-ai-frontend`
10. Deletar Artifact Registry repos antigos

### Fase 3 — CI/CD

1. Criar Cloud Build triggers para `olympus-ai-server` (prod + accept)
2. Criar Cloud Build triggers para `app-apollo-server` (prod + accept)
3. Criar Cloud Build triggers para `app-apollo-frontend` (prod + accept)
4. Deletar triggers antigos

> **Schedulers (`chronos-diagnosis-daily`, `athena-etl-orbcomm`):** apontam para Cloud Run Jobs independentes — não afetados, exceto pela atualização de secrets descrita acima.

---

## Portas locais

| Serviço              | Porta |
|----------------------|-------|
| olympus-ai-server    | 6001  |
| app-apollo-server    | 6002  |
| app-apollo-frontend  | 3000  |
