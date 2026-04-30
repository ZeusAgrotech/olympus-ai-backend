# Deploy do olympus-ai-backend no Google Cloud Run

Este documento orienta um agente (ou desenvolvedor) a publicar o repositório [olympus-ai-backend](https://github.com/ZeusAgrotech/olympus-ai-backend) no GCP, seguindo o mesmo padrão usado no `mcp-diagnosis-server` (Cloud Run, Artifact Registry, Cloud Build, Secret Manager, VPC opcional).

O repositório já inclui `cloudbuild.yaml` na raiz e um `Dockerfile` que sobe **gunicorn** com o app Flask exposto em [`wsgi.py`](../../wsgi.py).

---

## 0. Pré-requisitos

- Projeto GCP (ex.: `zeus-accept`) com billing
- `gcloud` instalado e autenticado: `gcloud auth login`
- Repositório clonado localmente com `Dockerfile` funcional; produção usa **gunicorn** + `wsgi:app`; desenvolvimento local usa [`main.py`](../../main.py) com `PORT` (default `6001`) e `debug` desligado quando `ENVIRONMENT=production`

```bash
gcloud config set project SEU_PROJETO
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
```

### IAM para o Cloud Build (primeiro deploy)

A service account padrão do Cloud Build (`PROJECT_NUMBER@cloudbuild.gserviceaccount.com`) precisa, no mínimo, de:

- `roles/artifactregistry.writer` — push da imagem
- `roles/run.admin` — deploy no Cloud Run
- `roles/iam.serviceAccountUser` — atuar como a service account de runtime do Cloud Run (ao publicar revisões)

Ajuste conforme a política da sua organização.

---

## 1. Auditar o código antes do deploy

1. Abrir [`Dockerfile`](../../Dockerfile) e confirmar:
   - Base Python adequada
   - `CMD` inicia **gunicorn** em `0.0.0.0` com `--bind` usando `${PORT:-8080}` (shell form)
   - `ENV ENVIRONMENT=production`
2. Em desenvolvimento, [`main.py`](../../main.py) usa `PORT` (default `6001`) e `debug=False` quando `ENVIRONMENT=production`.
3. Produção WSGI: [`wsgi.py`](../../wsgi.py) importa `agents` para registro declarativo e expõe `app` para o gunicorn.
4. Listar variáveis a partir de [`.env.example`](../../.env.example) e do [`cloudbuild.yaml`](../../cloudbuild.yaml) (`--set-env-vars` / `--set-secrets`).
5. Se o app carregar módulos no import que abrem conexão com banco ou Weaviate, tratar falhas ou usar lazy connection (evitar falha de health por import).

---

## 2. Artifact Registry (uma vez por projeto)

```bash
REGION=us-central1
PROJECT=$(gcloud config get-value project)

gcloud artifacts repositories create olympus-ai-backend \
  --repository-format=docker \
  --location=$REGION \
  --description="Olympus AI Backend images"
```

---

## 3. Arquivo `cloudbuild.yaml` na raiz

O repositório inclui [`cloudbuild.yaml`](../../cloudbuild.yaml): build Docker, push para `REGION-docker.pkg.dev/$PROJECT_ID/olympus-ai-backend/olympus-ai-backend:TAG` e `gcloud run deploy`.

**Substituições:**

| Variável | Uso |
|----------|-----|
| `_REGION` | ex. `us-central1` |
| `_SERVICE_NAME` | ex. `olympus-ai-backend` |
| `_ARTIFACT_REPO` | ex. `olympus-ai-backend` |
| `_IMAGE_TAG` | default `latest`; em trigger Git usar `$SHORT_SHA` |
| `_MCP_DIAGNOSIS_BASE_URL` | URL pública do MCP (não secreta) |
| `_MCP_DIAGNOSIS_TIMEOUT_SECONDS` | ex. `"300"` (string no YAML) |

**Secrets esperados no Secret Manager** (nomes iguais aos secrets; mapeados com `--set-secrets`):

- `OPENAI_API_KEY`
- `TAVILY_API_KEY`
- `MCP_DIAGNOSIS_AUTH_TOKEN`
- `OLYMPUS_AUTH_API_KEY` — valores de API separados por vírgula (mesmo formato que a variável de ambiente). No Cloud Run, o serviço recebe isso como env var `AUTH_API_KEY` (mapeado no `cloudbuild.yaml`).

**Regras YAML:** valores numéricos em `args` devem ser strings (`"10"`, não `10`).

**Referência adicional:** repositório `mcp-diagnosis-server` (`cloudbuild.yaml`, `docs/CLOUDRUN.md`).

---

## 4. Dockerfile

- `EXPOSE 8080` alinhado ao uso típico do Cloud Run
- `ENV ENVIRONMENT=production`
- `CMD` em forma shell com gunicorn: `wsgi:app`, workers/threads e timeout adequados a chamadas LLM

---

## 5. Secret Manager

1. **Nunca** colocar newline no final de valores de secret. Usar:

   ```bash
   printf 'valor_sem_newline' | gcloud secrets versions add NOME_DO_SECRET --data-file=- --project=SEU_PROJETO
   ```

2. Criar os secrets listados na seção 3 (nomes sugeridos iguais às variáveis de ambiente).

3. Se a OpenAI (ou outro provedor) responder **401 / invalid API key** mesmo com valor certo no console do Secret Manager, verifique **newline ou espaço no fim** do secret ao colar (`printf` sem `\n` no final). O app normaliza `OPENAI_API_KEY` e outros com **`.strip()`** em [`tools/env_bootstrap.py`](../../tools/env_bootstrap.py); faça **novo deploy** após mudanças no código.

4. Conceder à service account **de runtime** do Cloud Run `roles/secretmanager.secretAccessor` no projeto (ou por secret).

5. O deploy mapeia com `--set-secrets=ENV_VAR=SECRET_NAME:latest` (ver [`cloudbuild.yaml`](../../cloudbuild.yaml)).

---

## 6. RAG e Weaviate (opcional)

O código em `rag/` pode usar `weaviate.connect_to_local` por padrão. Isso **não** atinge um Weaviate dentro da rede local do container no Cloud Run.

Se precisar de RAG em produção:

- Hospedar Weaviate acessível à internet ou na mesma VPC (Weaviate Cloud, cluster na VPC, etc.), ou
- Evoluir o cliente para URL/API key remotos, e então guardar credenciais no Secret Manager.

Enquanto nenhum fluxo de agente instanciar RAG contra um host inacessível, o restante da API pode funcionar sem Weaviate.

---

## 7. Rede: IP fixo de saída (allowlist em APIs / DBs externos)

Se o backend precisa acessar recursos que **só aceitam IPs na allowlist** (como Cloud SQL em outra conta, MySQL externo, etc.):

1. Reutilizar VPC Connector + Cloud NAT já criados no projeto **ou** seguir `scripts/setup-cloudnat-egress.sh` (referência no repositório mcp-diagnosis-server).
2. Anotar o **IP de saída** (ex. `35.x.x.x`) e adicionar na allowlist do destino.
3. Atualizar o serviço:

   ```bash
   gcloud run services update olympus-ai-backend \
     --region=us-central1 \
     --vpc-connector=cloudrun-connector \
     --vpc-egress=all-traffic
   ```

---

## 8. Chaves de API

- Em **Cloud Run**, o secret `OLYMPUS_AUTH_API_KEY` contém uma ou mais chaves brutas separadas por vírgula (sem espaços). Ex.: `sk_abc,sk_def`. O deploy mapeia esse secret para a env var `AUTH_API_KEY`.

- Em **local**, definir `AUTH_API_KEY=sk_dev` no `.env`.

- Requisições HTTP: header `Authorization: Bearer sk_...` (sempre com prefixo `Bearer `).

---

## 9. Primeiro deploy manual

```bash
cd olympus-ai-backend
gcloud builds submit --config=cloudbuild.yaml --project=SEU_PROJETO
```

Corrigir erros de build, variáveis faltantes e secrets.

### Comandos úteis para criar secrets (ajuste valores)

```bash
PROJECT=SEU_PROJETO
for NAME in OPENAI_API_KEY TAVILY_API_KEY MCP_DIAGNOSIS_AUTH_TOKEN OLYMPUS_AUTH_API_KEY; do
  gcloud secrets describe "$NAME" --project="$PROJECT" >/dev/null 2>&1 || \
    gcloud secrets create "$NAME" --replication-policy=automatic --project="$PROJECT"
done
# Depois adicione versões com printf '|' gcloud secrets versions add ...
```

---

## 10. Cloud Build Trigger (GitHub)

### 10.1. Conectar o repositório (obrigatório na primeira vez)

Se o comando de criação do gatilho retornar `Repository mapping does not exist`, o GitHub ainda não expõe este repositório ao Cloud Build. Faça **um** dos seguintes:

1. **Console GCP:** Cloud Build → Triggers → **Connect repository** (ou abra `https://console.cloud.google.com/cloud-build/triggers/connect?project=SEU_PROJETO`) → GitHub → selecione `ZeusAgrotech/olympus-ai-backend`.
2. **GitHub:** **Settings** → **Applications** → **Google Cloud Build** → **Configure** → **Repository access** → inclua `olympus-ai-backend` (ou a organização inteira, conforme política).

### 10.2. Criar o gatilho (push na branch `main`)

Após o mapeamento existir, use **um** dos métodos:

**Opção A — `gcloud` (recomendado)**

```bash
gcloud builds triggers create github \
  --name=olympus-ai-backend \
  --description="Olympus AI backend - build and deploy on push to main" \
  --repo-owner=ZeusAgrotech \
  --repo-name=olympus-ai-backend \
  --branch-pattern="^main$" \
  --build-config=cloudbuild.yaml \
  --substitutions=_IMAGE_TAG='$SHORT_SHA' \
  --project=SEU_PROJETO
```

No **PowerShell**, `--substitutions="_IMAGE_TAG=$SHORT_SHA"` esvazia o `$SHORT_SHA`. Use aspas simples (`--substitutions='_IMAGE_TAG=$SHORT_SHA'`) ou crie o trigger e corrija com:

`gcloud builds triggers update github olympus-ai-backend --project=SEU_PROJETO '--update-substitutions=_IMAGE_TAG=$SHORT_SHA'`

**Opção B — import do manifest versionado**

Arquivo: [`ci/cloudbuild-github-trigger-olympus-main.yaml`](../../ci/cloudbuild-github-trigger-olympus-main.yaml)

```bash
gcloud beta builds triggers import \
  --source=ci/cloudbuild-github-trigger-olympus-main.yaml \
  --project=SEU_PROJETO
```

O [`cloudbuild.yaml`](../../cloudbuild.yaml) na raiz define `_REGION`, `_SERVICE_NAME` e `_ARTIFACT_REPO`; o gatilho sobrescreve apenas `_IMAGE_TAG` com `$SHORT_SHA` para marcar a imagem com o commit.

Se o nome `olympus-ai-backend` já estiver em uso, apague o trigger antigo (`gcloud builds triggers delete olympus-ai-backend --project=SEU_PROJETO`) ou altere o campo `name` no YAML / flag `--name`.

---

## 11. Pós-deploy

- Testar: `GET https://URL_DO_SERVICO/health`
- Testar: `GET /v1/models` ou equivalente documentado no README do olympus.
- Testar: `POST /v1/chat/completions` com `Authorization: Bearer ...` e payload mínimo.
- Verificar logs do Cloud Run em caso de 500 (timeouts LLM, MCP, CORS).

---

## 12. Checklist para o agente

- [ ] `Dockerfile` e gunicorn usam `PORT`; `ENVIRONMENT=production` sem Flask debug
- [ ] `cloudbuild.yaml` válido (strings, tags de imagem, secrets existentes)
- [ ] Artifact Registry criado
- [ ] Secrets criados sem newline; mapeados no Cloud Run
- [ ] IAM Secret Accessor para o SA do Cloud Run; IAM do Cloud Build para deploy
- [ ] VPC egress se allowlist externa for necessária
- [ ] RAG/Weaviate planejado se features dependerem disso
- [ ] Trigger Git configurado
- [ ] Health e um endpoint crítico testados com curl

---

## Referências cruzadas

- Padrão completo de deploy MCP: repositório `mcp-diagnosis-server`, arquivos `cloudbuild.yaml`, `docs/CLOUDRUN.md`, `scripts/setup-cloudnat-egress.sh`.
