# Apollo Intelligence — Rebranding e Nova Arquitetura — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduzir `app-apollo-server` como proxy OpenAI-compatible entre o frontend LibreChat e o `olympus-ai-server`, e renomear todos os serviços e repos para refletir a identidade Apollo Intelligence.

**Architecture:** O frontend (`app-apollo-frontend`) aponta para `app-apollo-server` (Flask, proxy puro — autenticação e repasse, sem filtragem de modelos). O apollo-server repassa payloads integralmente (incluindo streaming SSE) para `olympus-ai-server`. O olympus não muda de comportamento — apenas é renomeado.

**Separação por ambiente:** feita via dois arquivos `librechat.yaml`:
- `librechat.yaml` — acceptance: endpoints Apollo + Olympus, `fetch: true`, sem lista hardcoded
- `librechat.prod.yaml` — produção: apenas endpoint Apollo, `fetch: true`, sem lista hardcoded

O cloudbuild copia o arquivo correto antes de buildar a imagem. `ALLOWED_MODELS` foi removido — a visibilidade de modelos é controlada pelo atributo `hidden` no olympus (por agente), não por filtragem no proxy.

**Tech Stack:** Python 3.11, Flask, httpx, gunicorn, pytest, Docker, Cloud Run (GCP), Cloud Build, Secret Manager.

---

## Mapa de Arquivos

### Repo: `olympus-ai-backend` (a ser renomeado para `olympus-ai-server`)

| Arquivo | Ação | O que muda |
|---|---|---|
| `cloudbuild.yaml` | Modificar | `_SERVICE_NAME`, `_ARTIFACT_REPO`, secret `AUTH_API_KEY` |
| `ci/cloudbuild-trigger-accept.yaml` | Modificar | `name`, `github.name` |
| `ci/cloudbuild-trigger-prod.yaml` | Modificar | `name`, `github.name` |

### Repo: `app-apollo-server` (novo, repo vazio)

| Arquivo | Ação |
|---|---|
| `main.py` | Criar |
| `wsgi.py` | Criar |
| `tools/__init__.py` | Criar |
| `tools/env_bootstrap.py` | Criar |
| `proxy/__init__.py` | Criar |
| `proxy/olympus.py` | Criar |
| `server/__init__.py` | Criar |
| `server/server.py` | Criar |
| `tests/__init__.py` | Criar |
| `tests/test_proxy_olympus.py` | Criar |
| `tests/test_server.py` | Criar |
| `requirements.txt` | Criar |
| `pytest.ini` | Criar |
| `Dockerfile` | Criar |
| `docker-compose.yml` | Criar |
| `.env.example` | Criar |
| `cloudbuild.yaml` | Criar |
| `ci/cloudbuild-trigger-accept.yaml` | Criar |
| `ci/cloudbuild-trigger-prod.yaml` | Criar |
| `run.sh` | Criar |
| `stop.sh` | Criar |
| `install.sh` | Criar |
| `uninstall.sh` | Criar |

### Repo: `olympus-ai-frontend` (a ser renomeado para `app-apollo-frontend`)

| Arquivo | Ação | O que muda |
|---|---|---|
| `librechat.yaml` | Modificar | name, apiKey var, baseURL var, fetch: true, remover default list |
| `cloudbuild.yaml` | Modificar | service name, image name, env vars, remover sync-config step |
| `ci/cloudbuild-trigger-accept.yaml` | Modificar | name, github.name, _BACKEND_URL, _SERVICE_NAME, _AR_REPO |
| `ci/cloudbuild-trigger-prod.yaml` | Modificar | name, github.name, _BACKEND_URL, _SERVICE_NAME, _AR_REPO |

---

## Fase 1 — Local

---

### Task 1: Atualizar `olympus-ai-server` — cloudbuild e CI triggers

**Contexto:** Renomeia as referências internas nos arquivos de CI/CD do olympus. O comportamento do servidor em si não muda.

**Files:**
- Modify: `cloudbuild.yaml`
- Modify: `ci/cloudbuild-trigger-accept.yaml`
- Modify: `ci/cloudbuild-trigger-prod.yaml`

- [ ] **Step 1: Atualizar `cloudbuild.yaml`**

Substituir as três referências ao nome antigo:

```yaml
# cloudbuild.yaml — substitutions atualizadas
substitutions:
  _REGION: us-central1
  _SERVICE_NAME: olympus-ai-server          # era: olympus-ai-backend
  _ARTIFACT_REPO: olympus-ai-server         # era: olympus-ai-backend
  _IMAGE_TAG: latest
  _ENVIRONMENT: accept
  _MCP_DIAGNOSIS_BASE_URL: "MUST_BE_SET_BY_TRIGGER"
  _MCP_DIAGNOSIS_TIMEOUT_SECONDS: "300"
```

Nas steps de `docker build`, `docker push` e `gcloud run deploy`, trocar todas as ocorrências de `olympus-ai-backend` por `olympus-ai-server`.

Na step de deploy, atualizar o `--set-secrets`:
```yaml
      - "--set-secrets"
      - >-
        OPENAI_API_KEY=OPENAI_API_KEY:latest,TAVILY_API_KEY=TAVILY_API_KEY:latest,MCP_DIAGNOSIS_AUTH_TOKEN=MCP_DIAGNOSIS_AUTH_KEY:latest,AUTH_API_KEY=OLYMPUS_SERVER_AUTH_KEY:latest,RAGIE_API_KEY=RAGIE_API_KEY:latest
```
(mudança: `OLYMPUS_AUTH_API_KEY` → `OLYMPUS_SERVER_AUTH_KEY`)

- [ ] **Step 2: Atualizar `ci/cloudbuild-trigger-accept.yaml`**

```yaml
name: olympus-ai-server
description: "Olympus AI server - build and deploy to acceptance on push to acceptance"
github:
  owner: ZeusAgrotech
  name: olympus-ai-server
  push:
    branch: ^acceptance$
filename: cloudbuild.yaml
substitutions:
  _IMAGE_TAG: $SHORT_SHA
  _MCP_DIAGNOSIS_BASE_URL: https://mcp-diagnosis-server-ukneqvhpoa-uc.a.run.app
  _ENVIRONMENT: accept
```

- [ ] **Step 3: Atualizar `ci/cloudbuild-trigger-prod.yaml`**

```yaml
name: olympus-ai-server
description: "Olympus AI server - build and deploy to production on push to main"
github:
  owner: ZeusAgrotech
  name: olympus-ai-server
  push:
    branch: ^main$
filename: cloudbuild.yaml
substitutions:
  _IMAGE_TAG: $SHORT_SHA
  _MCP_DIAGNOSIS_BASE_URL: https://mcp-diagnosis-server-k56tkf3hxq-uc.a.run.app
  _ENVIRONMENT: production
```

- [ ] **Step 4: Commit**

```bash
git add cloudbuild.yaml ci/cloudbuild-trigger-accept.yaml ci/cloudbuild-trigger-prod.yaml
git commit -m "chore: rename service references to olympus-ai-server"
```

---

### Task 2: Bootstrap do `app-apollo-server` — arquivos de projeto

**Contexto:** Criar o esqueleto do novo serviço no repo `app-apollo-server` (já existe vazio no GitHub). Todos os scripts e configs seguem o mesmo padrão do olympus.

**Files:** Todos novos no repo `/Users/jorge/Documents/Git/app-apollo-server/`

- [ ] **Step 1: Criar `requirements.txt`**

```
flask
flask-cors
gunicorn
httpx
python-dotenv
pytest
pytest-cov
pytest-mock
```

- [ ] **Step 2: Criar `pytest.ini`**

```ini
[pytest]
testpaths = tests

python_files = test_*.py
python_classes = Test*
python_functions = test_*

addopts = 
    -v
    --tb=short
    --strict-markers
    --disable-warnings

markers =
    unit: marca teste como unitário
    integration: marca teste como de integração

[coverage:run]
source = .
omit = 
    tests/*
    .venv/*
    */__pycache__/*
```

- [ ] **Step 3: Criar `.env.example`**

```bash
# olympus-ai-server (backend central de agentes)
OLYMPUS_SERVER_URL=http://localhost:6001
OLYMPUS_SERVER_AUTH_KEY=sk_dev_olympus

# Auth: chave que o frontend usa para autenticar neste servidor
AUTH_API_KEY=sk_dev_apollo

ENVIRONMENT=local
```

> **Nota:** `ALLOWED_MODELS` foi removido. A visibilidade de modelos é controlada pelo atributo `hidden` em cada agente do olympus — o apollo é um proxy puro.

- [ ] **Step 4: Criar `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

ENV PYTHONPATH=/app
ENV ENVIRONMENT=production

CMD exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile - wsgi:app
```

- [ ] **Step 5: Criar `docker-compose.yml`**

```yaml
version: '3.8'

services:
  app:
    build: .
    container_name: apollo-server-container
    ports:
      - "6002:6002"
    volumes:
      - .:/app
    env_file:
      - .env
    environment:
      - PYTHONPATH=/app
      - PORT=6002
      - ENVIRONMENT=local
    restart: unless-stopped
```

- [ ] **Step 6: Criar `stop.sh`**

```bash
#!/bin/bash

echo "Checking for running instances..."

if lsof -i:6002 -t >/dev/null ; then
    PID=$(lsof -t -i:6002)
    echo "Found LOCAL process on port 6002 (PID $PID). Stopping..."
    kill $PID
    echo "Local process stopped."
else
    echo "No LOCAL process found on port 6002."
fi

if docker compose version >/dev/null 2>&1; then
    CMD="docker compose"
else
    CMD="docker-compose"
fi

if [ -n "$($CMD ps -q)" ]; then
    echo "Found RUNNING Docker containers. Stopping..."
    $CMD stop
    echo "Docker containers stopped."
else
    echo "No Docker containers running."
fi
```

```bash
chmod +x stop.sh
```

- [ ] **Step 7: Criar `install.sh`**

```bash
#!/bin/bash

require_cmd() {
    local cmd=$1 msg=$2
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: '$cmd' not found. $msg"
        exit 1
    fi
}

show_help() {
    echo "Usage: ./install.sh [OPTIONS]"
    echo "Options:"
    echo "  -l, --local   Install dependencies in a local .venv"
    echo "  -D, --docker  Build the Docker image"
    echo "  -f, --force   Force uninstallation before installing"
    exit 1
}

MODE=""
FORCE="false"

for arg in "$@"; do
    case $arg in
        -l|--local) MODE="local" ;;
        -D|--docker) MODE="docker" ;;
        -f|--force) FORCE="true" ;;
    esac
done

if [ -z "$MODE" ]; then show_help; fi

if [ "$FORCE" = "true" ]; then
    echo "Force mode. Uninstalling..."
    if [ "$MODE" = "local" ]; then ./uninstall.sh --local; else ./uninstall.sh --docker; fi
fi

if [ "$MODE" = "local" ]; then
    require_cmd python3 "Install Python 3"
    if [ -d ".venv" ]; then
        source .venv/bin/activate
        pip install -r requirements.txt
    else
        python3 -m venv .venv
        source .venv/bin/activate
        pip install -r requirements.txt
    fi
    echo "Local setup ready."
else
    require_cmd docker "Install Docker: https://docs.docker.com/get-docker/"
    if docker compose version >/dev/null 2>&1; then CMD="docker compose"; else CMD="docker-compose"; fi
    if [ -z "$($CMD images -q app)" ]; then
        $CMD build
    else
        echo "Docker image exists. Use --force to rebuild."
    fi
    echo "Docker setup ready."
fi
```

```bash
chmod +x install.sh
```

- [ ] **Step 8: Criar `uninstall.sh`**

```bash
#!/bin/bash

show_help() {
    echo "Usage: ./uninstall.sh [OPTIONS]"
    echo "  -l, --local   Remove .venv e caches"
    echo "  -D, --docker  Remove Docker resources"
    exit 1
}

MODE=""
for arg in "$@"; do
    case $arg in
        -l|--local) MODE="local" ;;
        -D|--docker) MODE="docker" ;;
    esac
done

if [ -z "$MODE" ]; then show_help; fi

if [ "$MODE" = "docker" ]; then
    if docker compose version >/dev/null 2>&1; then CMD="docker compose"; else CMD="docker-compose"; fi
    $CMD down --rmi all -v
elif [ "$MODE" = "local" ]; then
    rm -rf .venv
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
    echo "Cleanup complete."
fi
```

```bash
chmod +x uninstall.sh
```

- [ ] **Step 9: Criar `run.sh`**

```bash
#!/bin/bash

MODE=""
DEBUG="false"

show_help() {
    echo "Usage: ./run.sh [OPTIONS]"
    echo "  -l, --local   Run locally"
    echo "  -D, --docker  Run in Docker"
    echo "  -d, --debug   Enable debug mode"
    echo "  -s, --shell   Enter container shell (Docker only)"
    exit 1
}

for arg in "$@"; do
    case $arg in
        -l|--local) MODE="local" ;;
        -D|--docker) MODE="docker" ;;
        -d|--debug) DEBUG="true" ;;
        -s|--shell) SHELL_MODE="true" ;;
    esac
done

if [ -z "$MODE" ]; then show_help; fi

echo "Ensuring port 6002 is free..."
./stop.sh >/dev/null 2>&1

start_local() {
    echo "Starting in LOCAL mode..."
    ./install.sh --local
    source .venv/bin/activate
    if [ -f .env ]; then set -a; source .env; set +a; fi
    echo "Starting Apollo Server..."
    python main.py
}

start_docker() {
    echo "Starting in DOCKER mode..."
    if docker compose version >/dev/null 2>&1; then CMD="docker compose"; else CMD="docker-compose"; fi
    ./install.sh --docker
    if [ "$SHELL_MODE" = "true" ]; then
        $CMD run --rm --service-ports app /bin/bash
    elif [ "$DEBUG" = "true" ]; then
        $CMD up
    else
        $CMD up -d
        echo "Container started in background."
    fi
}

if [ "$MODE" = "local" ]; then start_local; else start_docker; fi
```

```bash
chmod +x run.sh
```

- [ ] **Step 10: Criar `__init__.py` dos pacotes**

```bash
mkdir -p tools proxy server tests
touch tools/__init__.py proxy/__init__.py server/__init__.py tests/__init__.py
```

- [ ] **Step 11: Commit**

```bash
git add .
git commit -m "chore: bootstrap app-apollo-server project structure"
```

---

### Task 3: Implementar `tools/env_bootstrap.py` com TDD

**Files:**
- Create: `tools/env_bootstrap.py`
- Test: `tests/test_env_bootstrap.py`

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_env_bootstrap.py
import os
import pytest


def test_get_environment_returns_local_by_default(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    from tools.env_bootstrap import get_environment
    assert get_environment() == "local"


def test_get_environment_returns_accept(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "accept")
    from tools.env_bootstrap import get_environment
    assert get_environment() == "accept"


def test_get_environment_returns_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    from tools.env_bootstrap import get_environment
    assert get_environment() == "production"


def test_strip_secret_env_vars_trims_whitespace(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "  sk_test  \n")
    monkeypatch.setenv("OLYMPUS_SERVER_AUTH_KEY", "  key123\n")
    from tools.env_bootstrap import strip_secret_env_vars
    strip_secret_env_vars()
    assert os.environ["AUTH_API_KEY"] == "sk_test"
    assert os.environ["OLYMPUS_SERVER_AUTH_KEY"] == "key123"
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
cd /Users/jorge/Documents/Git/app-apollo-server
source .venv/bin/activate
pytest tests/test_env_bootstrap.py -v
```

Expected: `ModuleNotFoundError: No module named 'tools.env_bootstrap'`

- [ ] **Step 3: Implementar `tools/env_bootstrap.py`**

```python
"""Normaliza variáveis de ambiente injetadas pelo Secret Manager (remove whitespace)."""

import os
from typing import Literal

_SECRET_ENV_NAMES = (
    "AUTH_API_KEY",
    "OLYMPUS_SERVER_AUTH_KEY",
)

Environment = Literal["local", "accept", "production"]


def get_environment() -> Environment:
    """Retorna o ambiente atual: 'local', 'accept' ou 'production'."""
    value = os.environ.get("ENVIRONMENT", "").strip().lower()
    if value == "production":
        return "production"
    if value == "accept":
        return "accept"
    return "local"


def strip_secret_env_vars() -> None:
    for name in _SECRET_ENV_NAMES:
        value = os.environ.get(name)
        if value is not None:
            os.environ[name] = value.strip()
```

- [ ] **Step 4: Rodar para confirmar aprovação**

```bash
pytest tests/test_env_bootstrap.py -v
```

Expected: todos os 4 testes passando.

- [ ] **Step 5: Commit**

```bash
git add tools/env_bootstrap.py tests/test_env_bootstrap.py
git commit -m "feat: add tools/env_bootstrap with tests"
```

---

### Task 4: Implementar `proxy/olympus.py` com TDD

**Contexto:** Esta é a peça central do apollo-server. Toda lógica de filtragem de modelos e forwarding para o olympus fica aqui.

**Files:**
- Create: `proxy/olympus.py`
- Test: `tests/test_proxy_olympus.py`

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_proxy_olympus.py
import pytest
from unittest.mock import MagicMock, patch


def test_list_models_returns_all(monkeypatch):
    monkeypatch.setenv("OLYMPUS_SERVER_URL", "http://test")
    monkeypatch.setenv("OLYMPUS_SERVER_AUTH_KEY", "key")

    olympus_data = {
        "object": "list",
        "data": [
            {"id": "OneDrive", "object": "model", "created": 1, "owned_by": "zeus"},
            {"id": "Athena", "object": "model", "created": 1, "owned_by": "zeus"},
        ]
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = olympus_data
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp

    with patch("proxy.olympus.httpx.Client", return_value=mock_client):
        from proxy.olympus import list_models
        result = list_models()

    assert result == olympus_data
```

> **Nota:** testes de `_allowed_models` e `is_model_allowed` foram removidos — `ALLOWED_MODELS` não existe mais. O apollo repassa todos os modelos do olympus sem filtrar.

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_proxy_olympus.py -v
```

Expected: `ModuleNotFoundError: No module named 'proxy.olympus'`

- [ ] **Step 3: Implementar `proxy/olympus.py`**

```python
"""Cliente HTTP para o olympus-ai-server. Toda comunicação com o olympus passa por aqui."""

import os
from typing import Generator

import httpx

_TIMEOUT = 300.0


def _olympus_url() -> str:
    return os.getenv("OLYMPUS_SERVER_URL", "http://localhost:6001")


def _olympus_headers() -> dict:
    key = os.getenv("OLYMPUS_SERVER_AUTH_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"}


def list_models() -> dict:
    """GET /v1/models do olympus — repassa todos os modelos sem filtrar."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.get(
            f"{_olympus_url()}/v1/models",
            headers=_olympus_headers(),
        )
        response.raise_for_status()
        return response.json()


def chat_completions(payload: dict) -> httpx.Response:
    """POST /v1/chat/completions ao olympus (não-streaming)."""
    return httpx.post(
        f"{_olympus_url()}/v1/chat/completions",
        json=payload,
        headers=_olympus_headers(),
        timeout=_TIMEOUT,
    )


def stream_chat_completions(payload: dict) -> Generator[bytes, None, None]:
    """POST /v1/chat/completions ao olympus com streaming SSE — repassa chunks diretamente."""
    with httpx.stream(
        "POST",
        f"{_olympus_url()}/v1/chat/completions",
        json=payload,
        headers=_olympus_headers(),
        timeout=_TIMEOUT,
    ) as response:
        for chunk in response.iter_raw():
            yield chunk
```

- [ ] **Step 4: Rodar para confirmar aprovação**

```bash
pytest tests/test_proxy_olympus.py -v
```

Expected: todos os 8 testes passando.

- [ ] **Step 5: Commit**

```bash
git add proxy/olympus.py tests/test_proxy_olympus.py
git commit -m "feat: add proxy/olympus with model filtering and streaming"
```

---

### Task 5: Implementar `server/server.py` com TDD

**Contexto:** Flask singleton com o mesmo padrão do olympus. Autentica requisições via `AUTH_API_KEY`, delega `/v1/models` e `/v1/chat/completions` ao `proxy/olympus.py`.

**Files:**
- Create: `server/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_server.py
import json
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def reset_server_singleton():
    """Reseta o singleton entre testes para evitar estado compartilhado."""
    from server import server as srv_module
    srv_module.Server._instance = None
    yield
    srv_module.Server._instance = None


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "test-key")
    from server.server import Server
    server = Server.get_instance()
    server.app.config["TESTING"] = True
    return server.app


@pytest.fixture
def client(app):
    return app.test_client()


def test_health_check_returns_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_list_models_does_not_require_auth(client):
    with patch("proxy.olympus.list_models", return_value={"object": "list", "data": []}):
        response = client.get("/v1/models")
    assert response.status_code == 200


def test_list_models_v1_and_non_v1_routes(client):
    with patch("proxy.olympus.list_models", return_value={"object": "list", "data": []}):
        assert client.get("/v1/models").status_code == 200
        assert client.get("/models").status_code == 200


def test_chat_completions_requires_auth(client):
    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 401


def test_chat_completions_rejects_invalid_key(client):
    response = client.post(
        "/v1/chat/completions",
        json={"model": "OneDrive", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert response.status_code == 401


def test_chat_completions_forwards_model(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"choices": [{"message": {"content": "hello"}}]}'
    mock_response.headers = {"content-type": "application/json"}

    with patch("proxy.olympus.chat_completions", return_value=mock_response):
        response = client.post(
            "/v1/chat/completions",
            json={"model": "OneDrive", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer test-key"},
        )
    assert response.status_code == 200


def test_health_check_no_auth_required(client):
    response = client.get("/health")
    assert response.status_code == 200
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_server.py -v
```

Expected: `ModuleNotFoundError: No module named 'server.server'`

- [ ] **Step 3: Implementar `server/server.py`**

```python
"""Servidor Flask singleton OpenAI-compatible. Delega ao proxy/olympus.py."""

import datetime as dt
import os
from typing import Optional

from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

from proxy import olympus as olympus_proxy


def _validate_api_key(raw_key: str) -> bool:
    env_keys = os.getenv("AUTH_API_KEY", "")
    return bool(raw_key) and raw_key in [k.strip() for k in env_keys.split(",") if k.strip()]


class Server:
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

        @self.app.before_request
        def check_auth():
            if not os.getenv("AUTH_API_KEY"):
                return
            if request.method == "OPTIONS":
                return
            if request.endpoint in ("health_check", "list_models"):
                return

            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return (
                    jsonify({"error": "Unauthorized", "message": "Missing or invalid Authorization header. Use 'Bearer <API_KEY>'."}),
                    401,
                )

            api_key = auth_header.split(" ", 1)[1].strip()
            if not _validate_api_key(api_key):
                return (
                    jsonify({"error": "Unauthorized", "message": "Invalid or missing API Key"}),
                    401,
                )

        self._setup_routes()
        self._initialized = True

    def _setup_routes(self):
        @self.app.route("/models", methods=["GET"])
        @self.app.route("/v1/models", methods=["GET"])
        def list_models():
            try:
                data = olympus_proxy.list_models()
                return jsonify(data)
            except Exception as e:
                return jsonify({"error": {"message": str(e), "type": "server_error"}}), 502

        @self.app.route("/chat/completions", methods=["POST"])
        @self.app.route("/v1/chat/completions", methods=["POST"])
        def chat_completions():
            payload = request.get_json(silent=True) or {}
            model = payload.get("model")

            if model and not olympus_proxy.is_model_allowed(model):
                return (
                    jsonify({
                        "error": {
                            "message": f"Model '{model}' is not available in this environment.",
                            "type": "invalid_request_error",
                            "param": "model",
                            "code": "model_not_allowed",
                        }
                    }),
                    400,
                )

            stream = bool(payload.get("stream", False))

            if stream:
                def generate():
                    for chunk in olympus_proxy.stream_chat_completions(payload):
                        yield chunk

                return Response(
                    stream_with_context(generate()),
                    mimetype="text/event-stream",
                )

            try:
                response = olympus_proxy.chat_completions(payload)
                return Response(
                    response.content,
                    status=response.status_code,
                    content_type=response.headers.get("content-type", "application/json"),
                )
            except Exception as e:
                return jsonify({"error": {"message": str(e), "type": "server_error"}}), 502

        @self.app.route("/health", methods=["GET"])
        def health_check():
            return jsonify({
                "status": "healthy",
                "server": "Apollo Server",
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            })

    def start(self, host="0.0.0.0", port=6002, debug=True):
        print("Starting Apollo Server...")
        print("Endpoints:")
        print("   GET  /v1/models")
        print("   POST /v1/chat/completions")
        print("   GET  /health")
        print("=" * 50)
        self.app.run(host=host, port=port, debug=debug)

    @classmethod
    def get_instance(cls) -> "Server":
        return cls()
```

- [ ] **Step 4: Rodar para confirmar aprovação**

```bash
pytest tests/test_server.py -v
```

Expected: todos os 9 testes passando.

- [ ] **Step 5: Rodar suite completa**

```bash
pytest -v
```

Expected: todos os testes passando (env_bootstrap + proxy + server).

- [ ] **Step 6: Commit**

```bash
git add server/server.py tests/test_server.py
git commit -m "feat: add server/server.py with auth and proxy delegation"
```

---

### Task 6: Criar entrypoints `main.py` e `wsgi.py`

**Files:**
- Create: `main.py`
- Create: `wsgi.py`

- [ ] **Step 1: Criar `main.py`**

```python
"""
Apollo Server — entrypoint local.
"""

import os

from dotenv import load_dotenv

from tools.env_bootstrap import get_environment, strip_secret_env_vars

load_dotenv()
strip_secret_env_vars()

from server.server import Server


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "6002"))
    environment = get_environment()
    debug = environment == "local"
    server = Server.get_instance()
    server.start(host="0.0.0.0", port=port, debug=debug)
```

- [ ] **Step 2: Criar `wsgi.py`**

```python
"""
WSGI entrypoint para produção (gunicorn no Cloud Run).
"""

from dotenv import load_dotenv

from tools.env_bootstrap import strip_secret_env_vars

load_dotenv()
strip_secret_env_vars()

from server.server import Server

server = Server.get_instance()
app = server.app
```

- [ ] **Step 3: Testar boot local**

Copiar `.env.example` para `.env`, ajustar valores:
```bash
cp .env.example .env
# Editar .env: OLYMPUS_SERVER_URL=http://localhost:6001 (ou onde olympus estiver rodando)
```

Rodar:
```bash
./run.sh --local
```

Expected: `Starting Apollo Server...` sem erros. `curl http://localhost:6002/health` retorna `{"status": "healthy", ...}`.

- [ ] **Step 4: Commit**

```bash
git add main.py wsgi.py .env.example
git commit -m "feat: add main.py and wsgi.py entrypoints"
```

---

### Task 7: CI/CD configs do `app-apollo-server`

**Files:**
- Create: `cloudbuild.yaml`
- Create: `ci/cloudbuild-trigger-accept.yaml`
- Create: `ci/cloudbuild-trigger-prod.yaml`

- [ ] **Step 1: Criar `cloudbuild.yaml`**

```yaml
# Cloud Build: build Docker image, push to Artifact Registry, deploy to Cloud Run.
# Deploy accept:  gcloud beta builds triggers import --source=ci/cloudbuild-trigger-accept.yaml --project=zeus-accept
# Deploy prod:    gcloud beta builds triggers import --source=ci/cloudbuild-trigger-prod.yaml --project=zeus-prod-335018

substitutions:
  _REGION: us-central1
  _AR_REPO: app-apollo-server
  _SERVICE_NAME: app-apollo-server
  _IMAGE_TAG: latest
  _ENVIRONMENT: accept
  _OLYMPUS_SERVER_URL: "MUST_BE_SET_BY_TRIGGER"

options:
  logging: CLOUD_LOGGING_ONLY

steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - "-t"
      - "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_AR_REPO}/app-apollo-server:${_IMAGE_TAG}"
      - .

  - name: gcr.io/cloud-builders/docker
    args:
      - push
      - "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_AR_REPO}/app-apollo-server:${_IMAGE_TAG}"

  - name: gcr.io/google.com/cloudsdktool/cloud-sdk
    entrypoint: gcloud
    args:
      - run
      - deploy
      - "${_SERVICE_NAME}"
      - "--image"
      - "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_AR_REPO}/app-apollo-server:${_IMAGE_TAG}"
      - "--region"
      - "${_REGION}"
      - "--platform"
      - managed
      - "--allow-unauthenticated"
      - "--set-env-vars"
      - >-
        ENVIRONMENT=${_ENVIRONMENT},OLYMPUS_SERVER_URL=${_OLYMPUS_SERVER_URL}
      - "--set-secrets"
      - >-
        AUTH_API_KEY=APOLLO_AUTH_API_KEY:latest,OLYMPUS_SERVER_AUTH_KEY=OLYMPUS_SERVER_AUTH_KEY:latest
```

- [ ] **Step 2: Criar `ci/` e `ci/cloudbuild-trigger-accept.yaml`**

```bash
mkdir -p ci
```

```yaml
# ci/cloudbuild-trigger-accept.yaml
name: app-apollo-server-accept
description: "Apollo Server - build and deploy to acceptance on push to acceptance branch"
github:
  owner: ZeusAgrotech
  name: app-apollo-server
  push:
    branch: ^acceptance$
filename: cloudbuild.yaml
substitutions:
  _IMAGE_TAG: $SHORT_SHA
  _OLYMPUS_SERVER_URL: https://olympus-ai-server-ukneqvhpoa-uc.a.run.app
  _ENVIRONMENT: accept
```

> **Nota:** A URL `olympus-ai-server-ukneqvhpoa-uc.a.run.app` é a URL do novo serviço após deploy na Task 11. Atualizar se a URL gerada for diferente.

- [ ] **Step 3: Criar `ci/cloudbuild-trigger-prod.yaml`**

```yaml
# ci/cloudbuild-trigger-prod.yaml
name: app-apollo-server-prod
description: "Apollo Server - build and deploy to production on push to main branch"
github:
  owner: ZeusAgrotech
  name: app-apollo-server
  push:
    branch: ^main$
filename: cloudbuild.yaml
substitutions:
  _IMAGE_TAG: $SHORT_SHA
  _OLYMPUS_SERVER_URL: https://olympus-ai-server-k56tkf3hxq-uc.a.run.app
  _ENVIRONMENT: production
```

> **Nota:** A URL `olympus-ai-server-k56tkf3hxq-uc.a.run.app` é a URL do novo serviço após deploy. Confirmar na Task 11.

- [ ] **Step 4: Commit**

```bash
git add cloudbuild.yaml ci/
git commit -m "chore: add CI/CD configs for app-apollo-server"
```

---

### Task 8: Atualizar `app-apollo-frontend` — `librechat.yaml` e `cloudbuild.yaml`

**Contexto:** O frontend passa a apontar pro apollo-server. Separação por ambiente via dois arquivos yaml: `librechat.yaml` (acceptance: Apollo + Olympus) e `librechat.prod.yaml` (prod: só Apollo). O cloudbuild copia o correto antes de buildar. Sem lista hardcoded de modelos — tudo via `fetch: true`.

**Status: Implementado.**

**Files (no repo `olympus-ai-frontend`):**
- Modify: `librechat.yaml` — Apollo + Olympus, `fetch: true`, sem `default`
- Create: `librechat.prod.yaml` — só Apollo, `fetch: true`, sem `default`
- Modify: `cloudbuild.yaml` — step sync-config copia yaml por `_ENVIRONMENT`, renomeia imagens para `app-apollo-frontend`, atualiza env vars e secrets
- Modify: `ci/cloudbuild-trigger-accept.yaml` — `_ENVIRONMENT: accept`, `_AR_REPO/SERVICE_NAME: app-apollo-frontend`
- Modify: `ci/cloudbuild-trigger-prod.yaml` — `_ENVIRONMENT: production`, idem

- [ ] **Step 3: Atualizar `ci/cloudbuild-trigger-accept.yaml`**

```yaml
name: app-apollo-frontend-accept
description: "Apollo frontend - build and deploy to acceptance on push to acceptance"
github:
  owner: ZeusAgrotech
  name: app-apollo-frontend
  push:
    branch: ^acceptance$
filename: cloudbuild.yaml
substitutions:
  _BACKEND_URL: https://app-apollo-server-ukneqvhpoa-uc.a.run.app
  _AR_REPO: app-apollo-frontend
  _SERVICE_NAME: app-apollo-frontend
  _ENVIRONMENT: accept
```

> **Nota:** URL do apollo-server em accept — confirmar após deploy na Task 12.

- [ ] **Step 4: Atualizar `ci/cloudbuild-trigger-prod.yaml`**

```yaml
name: app-apollo-frontend-prod
description: "Apollo frontend - build and deploy to production on push to main"
github:
  owner: ZeusAgrotech
  name: app-apollo-frontend
  push:
    branch: ^main$
filename: cloudbuild.yaml
substitutions:
  _BACKEND_URL: https://app-apollo-server-k56tkf3hxq-uc.a.run.app
  _AR_REPO: app-apollo-frontend
  _SERVICE_NAME: app-apollo-frontend
  _ENVIRONMENT: production
```

> **Nota:** URL do apollo-server em prod — confirmar após deploy na Task 12.

- [ ] **Step 5: Commit**

```bash
git add librechat.yaml librechat.prod.yaml cloudbuild.yaml ci/
git commit -m "chore: rename to app-apollo-frontend, two-env yaml, fetch:true, no hardcoded models"
```

---

### Task 8.1: Coldstart handling — simulação nos backends e polling no frontend

**Contexto:** O Cloud Run tem coldstart que pode demorar vários segundos. O LibreChat original caía num fallback hardcoded ao timeout. A solução foi: backends retornam 200 com lista vazia durante o warmup, e o frontend faz polling até preencher — sem fallback, com feedback visual (spinner).

**Status: Implementado.**

#### Backend — coldstart real do Cloud Run

O coldstart é inerente ao Cloud Run com `--min-instances=0`. O olympus já usa `--min-instances=1`, o que reduz (mas não elimina) o problema. Não há simulação de coldstart no código dos backends — o frontend lida com isso via polling.

#### Frontend — remoção de cache e polling automático

**Files modificados:**
- `librechat/api/server/controllers/ModelController.js`
- `librechat/client/src/hooks/Endpoint/useEndpoints.ts`
- `librechat/client/src/components/Chat/Menus/Endpoints/components/EndpointItem.tsx`

**ModelController.js:** cache removido completamente. Cada chamada ao `/api/models` vai diretamente aos backends — sem estado em memória. Isso garante que novos modelos aparecem sem reiniciar o servidor Node.js.

**useEndpoints.ts:** `useGetModelsQuery` recebe `refetchInterval` dinâmico:
```typescript
refetchInterval: (data) => {
  if (!data) return 10_000;
  const hasEmpty = Object.values(data).some(
    (models) => Array.isArray(models) && models.length === 0,
  );
  return hasEmpty ? 10_000 : 300_000;
},
```
- Endpoint vazio → poll a cada 10s até preencher
- Todos preenchidos → poll a cada 5min (verificação de novos modelos)

**EndpointItem.tsx — spinner:** `isLoadingModels` simplificado para mostrar spinner sempre que `!hasModels` (independente do estado do fetch). Antes, o spinner sumia entre os intervalos de poll.

```typescript
// Antes (bugado: spinner sumia entre polls)
const isLoadingModels = !hasModels && ... && (modelsQuery.isLoading || modelsQuery.isFetching || modelsQuery.isError);

// Depois (correto: spinner persiste enquanto lista estiver vazia)
const isLoadingModels = !hasModels && ep !== EModelEndpoint.agents && ep !== EModelEndpoint.assistants;
```

**Fluxo completo:**
1. Frontend abre → `useGetModelsQuery` chama `/api/models`
2. Node.js chama `/v1/models` em cada backend (parallel, sem cache)
3. Backend em coldstart → retorna 200 vazio
4. Frontend: endpoint sem modelos → mostra spinner
5. Poll a cada 10s → backend responde com modelos → spinner some, setinha aparece
6. Todos preenchidos → poll cai para 5min

---

### Task 9: Teste de integração local

**Contexto:** Validar que os três serviços funcionam juntos localmente antes de subir pro Cloud.

- [ ] **Step 1: Garantir olympus rodando em :6001**

```bash
cd /Users/jorge/Documents/Git/olympus-ai-backend
./run.sh --local
```

Verificar: `curl http://localhost:6001/health` retorna `{"status": "healthy"}`.

- [ ] **Step 2: Iniciar apollo-server em :6002**

Em outro terminal:
```bash
cd /Users/jorge/Documents/Git/app-apollo-server
./run.sh --local
```

Verificar: `curl http://localhost:6002/health` retorna `{"status": "healthy", "server": "Apollo Server"}`.

- [ ] **Step 3: Testar GET /v1/models com filtragem**

```bash
# Sem filtro (ALLOWED_MODELS=* no .env local)
curl http://localhost:6002/v1/models | python3 -m json.tool
```

Expected: lista com todos os modelos do olympus.

```bash
# Simular prod: setar ALLOWED_MODELS=OneDrive,WebSearch no .env e reiniciar apollo
curl http://localhost:6002/v1/models | python3 -m json.tool
```

Expected: apenas `OneDrive` e `WebSearch` na lista.

- [ ] **Step 4: Testar bloqueio de modelo não permitido**

```bash
# Com ALLOWED_MODELS=OneDrive,WebSearch
curl -X POST http://localhost:6002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(grep AUTH_API_KEY .env | cut -d= -f2)" \
  -d '{"model": "Athena", "messages": [{"role": "user", "content": "teste"}]}'
```

Expected: `{"error": {"code": "model_not_allowed", ...}}` com status 400.

- [ ] **Step 5: Testar forwarding de mensagem completa**

```bash
curl -X POST http://localhost:6002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(grep AUTH_API_KEY .env | cut -d= -f2)" \
  -d '{"model": "WebSearch", "messages": [{"role": "user", "content": "qual é a capital do Brasil?"}]}'
```

Expected: resposta completa do olympus repassada pelo apollo.

---

## Fase 2 — Cloud Run

---

### Task 10: GCP — Criar Artifact Registry repos e Secrets

- [ ] **Step 1: Criar Artifact Registry repos**

```bash
# olympus-ai-server (prod)
gcloud artifacts repositories create olympus-ai-server \
  --repository-format=docker \
  --location=us-central1 \
  --project=zeus-prod-335018

# olympus-ai-server (accept)
gcloud artifacts repositories create olympus-ai-server \
  --repository-format=docker \
  --location=us-central1 \
  --project=zeus-accept

# app-apollo-server (prod)
gcloud artifacts repositories create app-apollo-server \
  --repository-format=docker \
  --location=us-central1 \
  --project=zeus-prod-335018

# app-apollo-server (accept)
gcloud artifacts repositories create app-apollo-server \
  --repository-format=docker \
  --location=us-central1 \
  --project=zeus-accept

# app-apollo-frontend (prod)
gcloud artifacts repositories create app-apollo-frontend \
  --repository-format=docker \
  --location=us-central1 \
  --project=zeus-prod-335018

# app-apollo-frontend (accept)
gcloud artifacts repositories create app-apollo-frontend \
  --repository-format=docker \
  --location=us-central1 \
  --project=zeus-accept
```

- [ ] **Step 2: Criar secret `OLYMPUS_SERVER_AUTH_KEY` (mesma chave que `OLYMPUS_AUTH_API_KEY`, nova versão)**

```bash
# Buscar valor atual do secret
CURRENT_KEY=$(gcloud secrets versions access latest \
  --secret=OLYMPUS_AUTH_API_KEY \
  --project=zeus-prod-335018)

# Criar novo secret com novo nome (prod)
echo -n "$CURRENT_KEY" | gcloud secrets create OLYMPUS_SERVER_AUTH_KEY \
  --data-file=- \
  --project=zeus-prod-335018

# Criar novo secret com novo nome (accept)
CURRENT_KEY_ACCEPT=$(gcloud secrets versions access latest \
  --secret=OLYMPUS_AUTH_API_KEY \
  --project=zeus-accept)

echo -n "$CURRENT_KEY_ACCEPT" | gcloud secrets create OLYMPUS_SERVER_AUTH_KEY \
  --data-file=- \
  --project=zeus-accept
```

- [ ] **Step 3: Criar secret `APOLLO_AUTH_API_KEY`**

Gerar nova chave para o apollo-server (usada pelo frontend para autenticar):
```bash
# Gerar chave (pode ser qualquer string segura — usar o mesmo padrão do projeto)
NEW_APOLLO_KEY="sk_$(openssl rand -hex 32)"

echo -n "$NEW_APOLLO_KEY" | gcloud secrets create APOLLO_AUTH_API_KEY \
  --data-file=- \
  --project=zeus-prod-335018

echo -n "$NEW_APOLLO_KEY" | gcloud secrets create APOLLO_AUTH_API_KEY \
  --data-file=- \
  --project=zeus-accept

echo "Apollo Auth Key: $NEW_APOLLO_KEY"
# Guardar esse valor — será necessário configurar no frontend local (.env)
```

---

### Task 11: GCP — Deploy `olympus-ai-server`

- [ ] **Step 1: Trigger manual do build (prod)**

```bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  --project=zeus-prod-335018 \
  --substitutions=_SERVICE_NAME=olympus-ai-server,_ARTIFACT_REPO=olympus-ai-server,_IMAGE_TAG=latest,_ENVIRONMENT=production,_MCP_DIAGNOSIS_BASE_URL=https://mcp-diagnosis-server-k56tkf3hxq-uc.a.run.app \
  /Users/jorge/Documents/Git/olympus-ai-backend
```

- [ ] **Step 2: Verificar URL do novo serviço (prod)**

```bash
gcloud run services describe olympus-ai-server \
  --project=zeus-prod-335018 \
  --region=us-central1 \
  --format="value(status.url)"
```

Anotar a URL — formato esperado: `https://olympus-ai-server-k56tkf3hxq-uc.a.run.app`

- [ ] **Step 3: Trigger manual do build (accept)**

```bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  --project=zeus-accept \
  --substitutions=_SERVICE_NAME=olympus-ai-server,_ARTIFACT_REPO=olympus-ai-server,_IMAGE_TAG=latest,_ENVIRONMENT=accept,_MCP_DIAGNOSIS_BASE_URL=https://mcp-diagnosis-server-ukneqvhpoa-uc.a.run.app \
  /Users/jorge/Documents/Git/olympus-ai-backend
```

- [ ] **Step 4: Smoke test olympus-ai-server (prod)**

```bash
OLYMPUS_URL=$(gcloud run services describe olympus-ai-server \
  --project=zeus-prod-335018 --region=us-central1 --format="value(status.url)")
curl "$OLYMPUS_URL/health"
```

Expected: `{"status": "healthy"}`.

---

### Task 12: GCP — Deploy `app-apollo-server`

- [ ] **Step 1: Build e deploy em accept**

```bash
OLYMPUS_ACCEPT_URL=$(gcloud run services describe olympus-ai-server \
  --project=zeus-accept --region=us-central1 --format="value(status.url)")

gcloud builds submit \
  --config=cloudbuild.yaml \
  --project=zeus-accept \
  --substitutions=_SERVICE_NAME=app-apollo-server,_AR_REPO=app-apollo-server,_IMAGE_TAG=latest,_ENVIRONMENT=accept,_OLYMPUS_SERVER_URL=$OLYMPUS_ACCEPT_URL \
  /Users/jorge/Documents/Git/app-apollo-server
```

- [ ] **Step 2: Smoke test apollo-server (accept)**

```bash
APOLLO_ACCEPT_URL=$(gcloud run services describe app-apollo-server \
  --project=zeus-accept --region=us-central1 --format="value(status.url)")
curl "$APOLLO_ACCEPT_URL/health"
curl "$APOLLO_ACCEPT_URL/v1/models"
```

Expected: `{"status": "healthy"}` e lista de todos os modelos do olympus.

- [ ] **Step 3: Build e deploy em prod**

```bash
OLYMPUS_PROD_URL=$(gcloud run services describe olympus-ai-server \
  --project=zeus-prod-335018 --region=us-central1 --format="value(status.url)")

gcloud builds submit \
  --config=cloudbuild.yaml \
  --project=zeus-prod-335018 \
  --substitutions=_SERVICE_NAME=app-apollo-server,_AR_REPO=app-apollo-server,_IMAGE_TAG=latest,_ENVIRONMENT=production,_OLYMPUS_SERVER_URL=$OLYMPUS_PROD_URL \
  /Users/jorge/Documents/Git/app-apollo-server
```

- [ ] **Step 4: Smoke test apollo-server (prod)**

```bash
APOLLO_PROD_URL=$(gcloud run services describe app-apollo-server \
  --project=zeus-prod-335018 --region=us-central1 --format="value(status.url)")
curl "$APOLLO_PROD_URL/v1/models"
```

Expected: apenas `OneDrive` e `WebSearch` na lista.

- [ ] **Step 5: Atualizar URLs nos CI triggers do apollo-server**

Abrir `ci/cloudbuild-trigger-accept.yaml` e `ci/cloudbuild-trigger-prod.yaml` do `app-apollo-server` e confirmar/atualizar as URLs do olympus-ai-server com os valores reais obtidos nos steps acima.

---

### Task 13: GCP — Deploy `app-apollo-frontend`

- [ ] **Step 1: Build e deploy em accept**

```bash
APOLLO_SERVER_ACCEPT_URL=$(gcloud run services describe app-apollo-server \
  --project=zeus-accept --region=us-central1 --format="value(status.url)")

gcloud builds submit \
  --config=cloudbuild.yaml \
  --project=zeus-accept \
  --substitutions=_BACKEND_URL=$APOLLO_SERVER_ACCEPT_URL,_AR_REPO=app-apollo-frontend,_SERVICE_NAME=app-apollo-frontend \
  /Users/jorge/Documents/Git/olympus-ai-frontend
```

- [ ] **Step 2: Smoke test frontend (accept)**

```bash
APOLLO_FRONTEND_ACCEPT_URL=$(gcloud run services describe app-apollo-frontend \
  --project=zeus-accept --region=us-central1 --format="value(status.url)")
curl "$APOLLO_FRONTEND_ACCEPT_URL"
```

Expected: HTML do LibreChat com título "Apollo".

- [ ] **Step 3: Build e deploy em prod**

```bash
APOLLO_SERVER_PROD_URL=$(gcloud run services describe app-apollo-server \
  --project=zeus-prod-335018 --region=us-central1 --format="value(status.url)")

gcloud builds submit \
  --config=cloudbuild.yaml \
  --project=zeus-prod-335018 \
  --substitutions=_BACKEND_URL=$APOLLO_SERVER_PROD_URL,_AR_REPO=app-apollo-frontend,_SERVICE_NAME=app-apollo-frontend \
  /Users/jorge/Documents/Git/olympus-ai-frontend
```

- [ ] **Step 4: Reconfigurar URL customizada do frontend**

Se houver domínio customizado mapeado para `olympus-ai-frontend`, remapeá-lo para `app-apollo-frontend`:

```bash
# Verificar mapeamentos existentes
gcloud run domain-mappings list --project=zeus-prod-335018 --region=us-central1

# Se existir mapeamento para olympus-ai-frontend, removê-lo e recriar para app-apollo-frontend
# (substituir <DOMINIO> pelo domínio real)
gcloud run domain-mappings delete --domain=<DOMINIO> --project=zeus-prod-335018 --region=us-central1
gcloud run domain-mappings create --service=app-apollo-frontend --domain=<DOMINIO> --project=zeus-prod-335018 --region=us-central1
```

---

### Task 14: GCP — Atualizar secrets do `chronos-diagnosis` e limpeza

- [ ] **Step 1: Atualizar `OLYMPUS_BASE_URL` no Secret Manager**

```bash
# Obter URLs reais dos novos serviços
OLYMPUS_PROD_URL=$(gcloud run services describe olympus-ai-server \
  --project=zeus-prod-335018 --region=us-central1 --format="value(status.url)")
OLYMPUS_ACCEPT_URL=$(gcloud run services describe olympus-ai-server \
  --project=zeus-accept --region=us-central1 --format="value(status.url)")

# Atualizar secret em prod
echo -n "$OLYMPUS_PROD_URL" | gcloud secrets versions add OLYMPUS_BASE_URL \
  --data-file=- \
  --project=zeus-prod-335018

# Atualizar secret em accept
echo -n "$OLYMPUS_ACCEPT_URL" | gcloud secrets versions add OLYMPUS_BASE_URL \
  --data-file=- \
  --project=zeus-accept
```

- [ ] **Step 2: Atualizar `OLYMPUS_AUTH_KEY` no Secret Manager**

```bash
# Obter o novo valor do OLYMPUS_SERVER_AUTH_KEY
NEW_KEY=$(gcloud secrets versions access latest \
  --secret=OLYMPUS_SERVER_AUTH_KEY \
  --project=zeus-prod-335018)

echo -n "$NEW_KEY" | gcloud secrets versions add OLYMPUS_AUTH_KEY \
  --data-file=- \
  --project=zeus-prod-335018

NEW_KEY_ACCEPT=$(gcloud secrets versions access latest \
  --secret=OLYMPUS_SERVER_AUTH_KEY \
  --project=zeus-accept)

echo -n "$NEW_KEY_ACCEPT" | gcloud secrets versions add OLYMPUS_AUTH_KEY \
  --data-file=- \
  --project=zeus-accept
```

- [ ] **Step 3: Verificar chronos-diagnosis com novos secrets**

Disparar execução manual:
```bash
gcloud run jobs execute chronos-diagnosis \
  --project=zeus-prod-335018 \
  --region=us-central1
```

Verificar logs:
```bash
gcloud run jobs executions list --job=chronos-diagnosis \
  --project=zeus-prod-335018 \
  --region=us-central1 \
  --limit=1
```

- [ ] **Step 4: Deletar serviços antigos**

```bash
# Confirmar que os novos estão saudáveis antes de deletar
gcloud run services delete olympus-ai-backend --project=zeus-prod-335018 --region=us-central1
gcloud run services delete olympus-ai-frontend --project=zeus-prod-335018 --region=us-central1

gcloud run services delete olympus-ai-backend --project=zeus-accept --region=us-central1
gcloud run services delete olympus-ai-frontend --project=zeus-accept --region=us-central1
```

- [ ] **Step 5: Deletar Artifact Registry repos antigos**

```bash
gcloud artifacts repositories delete olympus-ai-backend \
  --location=us-central1 --project=zeus-prod-335018
gcloud artifacts repositories delete olympus \
  --location=us-central1 --project=zeus-prod-335018

gcloud artifacts repositories delete olympus-ai-backend \
  --location=us-central1 --project=zeus-accept
gcloud artifacts repositories delete olympus \
  --location=us-central1 --project=zeus-accept
```

---

## Fase 3 — CI/CD (Cloud Build Triggers)

---

### Task 15: Criar Cloud Build Triggers e remover os antigos

- [ ] **Step 1: Criar triggers do `olympus-ai-server`**

```bash
gcloud beta builds triggers import \
  --source=/Users/jorge/Documents/Git/olympus-ai-backend/ci/cloudbuild-trigger-accept.yaml \
  --project=zeus-accept

gcloud beta builds triggers import \
  --source=/Users/jorge/Documents/Git/olympus-ai-backend/ci/cloudbuild-trigger-prod.yaml \
  --project=zeus-prod-335018
```

- [ ] **Step 2: Criar triggers do `app-apollo-server`**

```bash
gcloud beta builds triggers import \
  --source=/Users/jorge/Documents/Git/app-apollo-server/ci/cloudbuild-trigger-accept.yaml \
  --project=zeus-accept

gcloud beta builds triggers import \
  --source=/Users/jorge/Documents/Git/app-apollo-server/ci/cloudbuild-trigger-prod.yaml \
  --project=zeus-prod-335018
```

- [ ] **Step 3: Criar triggers do `app-apollo-frontend`**

```bash
gcloud beta builds triggers import \
  --source=/Users/jorge/Documents/Git/olympus-ai-frontend/ci/cloudbuild-trigger-accept.yaml \
  --project=zeus-accept

gcloud beta builds triggers import \
  --source=/Users/jorge/Documents/Git/olympus-ai-frontend/ci/cloudbuild-trigger-prod.yaml \
  --project=zeus-prod-335018
```

- [ ] **Step 4: Verificar triggers criados**

```bash
gcloud builds triggers list --project=zeus-prod-335018 --format="table(name,github.name)"
gcloud builds triggers list --project=zeus-accept --format="table(name,github.name)"
```

Expected: triggers `olympus-ai-server`, `app-apollo-server`, `app-apollo-frontend` listados em ambos projetos.

- [ ] **Step 5: Deletar triggers antigos**

```bash
# Listar IDs dos triggers antigos
gcloud builds triggers list --project=zeus-prod-335018 --filter="github.name=olympus-ai-backend OR github.name=olympus-ai-frontend" --format="value(id)"

# Deletar cada ID retornado
gcloud builds triggers delete <ID> --project=zeus-prod-335018

# Repetir para zeus-accept
gcloud builds triggers list --project=zeus-accept --filter="github.name=olympus-ai-backend OR github.name=olympus-ai-frontend" --format="value(id)"
gcloud builds triggers delete <ID> --project=zeus-accept
```

---

## Estado Atual — O que foi feito e o que falta

> Atualizado em 2026-05-19. Use este sumário ao iniciar uma nova sessão.

---

### ✅ Feito (commitado)

| Repo | O que foi feito |
|---|---|
| `olympus-ai-backend` | Task 1: CI/CD renomeado para `olympus-ai-server` (commit `88f3b78`) |
| `olympus-ai-backend` | `cloudbuild.yaml`: `--min-instances=1` → `--min-instances=0` (frontend resiliente ao coldstart via polling) |
| `app-apollo-server` | Tasks 2–7: bootstrap completo, proxy, server, entrypoints, CI/CD configs (5 commits, branch `main`, não pusheados) |
| `app-apollo-server` | `cloudbuild.yaml`: `--min-instances=1` → `--min-instances=0` (idem) |

---

### ⚠️ Feito mas NÃO commitado

| Repo | Branch | O que está pendente de commit |
|---|---|---|
| `olympus-ai-backend` | `acceptance` | Atualização do plano (`docs/superpowers/plans/`) |
| `olympus-ai-frontend` | `main` | 13 arquivos modificados + `librechat.prod.yaml` (untracked) — ver lista abaixo |

**Arquivos modificados no `olympus-ai-frontend` (não commitados):**
- `ci/cloudbuild-trigger-accept.yaml` — renomeado para `app-apollo-frontend`, `_ENVIRONMENT: accept`
- `ci/cloudbuild-trigger-prod.yaml` — renomeado para `app-apollo-frontend`, `_ENVIRONMENT: production`
- `cloudbuild.yaml` — step `sync-config` copia yaml por ambiente, imagens renomeadas, env vars/secrets atualizados
- `librechat.yaml` — acceptance: Apollo + Olympus, `fetch: true`, sem `default`
- `librechat.prod.yaml` *(untracked)* — prod: só Apollo, `fetch: true`, sem `default`
- `librechat/api/server/controllers/ModelController.js` — cache removido (sempre re-fetch dos backends)
- `librechat/client/src/hooks/Endpoint/useEndpoints.ts` — polling: 10s (vazio) / 5min (preenchido)
- `librechat/client/src/components/Chat/Menus/Endpoints/components/EndpointItem.tsx` — spinner sempre quando `!hasModels`, `handleRefreshModels` removido
- Outros arquivos (`selector.ts`, `types.ts`, `ModelSelect.tsx`, `OpenAI.tsx`, `react-query-service.ts`) — alterações da sessão anterior (spinner, isLoadingModels)

---

### ❌ Pendente no código (não implementado)

| Repo | O que falta |
|---|---|
| `app-apollo-server` | Remover `ALLOWED_MODELS` do código: `proxy/olympus.py` (`_allowed_models`, `is_model_allowed`, `_fallback_models`, filtragem em `list_models`) e `server/server.py` (check `is_model_allowed` em `/chat/completions`). O apollo deve ser proxy puro. |

---

### 🔲 Não iniciado (Fase 2 e 3 — Cloud Run)

- Task 9: Teste de integração local
- Task 10: GCP — Artifact Registry repos + secrets (`OLYMPUS_SERVER_AUTH_KEY`, `APOLLO_AUTH_API_KEY`)
- Task 11: Deploy `olympus-ai-server` no Cloud Run
- Task 12: Deploy `app-apollo-server` no Cloud Run
- Task 13: Deploy `app-apollo-frontend` no Cloud Run
- Task 14: Atualizar secrets do `chronos-diagnosis`, deletar serviços antigos
- Task 15: Criar Cloud Build Triggers novos, deletar antigos

---

### ⚠️ Atenção antes de continuar

1. **Branch do apollo:** está em `main`, não em `acceptance`. Definir estratégia de branch antes de pushar.
2. **Branch do frontend:** está em `main`. Os 13 arquivos não commitados precisam ser commitados e a branch definida.
3. **ALLOWED_MODELS no apollo:** ainda presente no código — remover antes de qualquer deploy.
4. **Commits do olympus (plano):** não commitados — commitá-los na branch `acceptance`.
