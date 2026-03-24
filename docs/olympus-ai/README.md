# Documentação de deploy Olympus (templates)

Esta pasta contém guias para deploy no GCP dos repositórios **olympus-ai-backend** e **olympus-ai-frontend**.

## Como usar

1. Clone cada repositório na sua máquina.
2. Copie o conteúdo correspondente para dentro do repositório alvo:

| Repositório GitHub | Onde está o guia |
|--------------------|------------------|
| `ZeusAgrotech/olympus-ai-backend` | [`docs/olympus-ai-backend/DEPLOY_GCP.md`](../olympus-ai-backend/DEPLOY_GCP.md) (também `cloudbuild.yaml` na raiz do backend) |
| `ZeusAgrotech/olympus-ai-frontend` | Copiar template para `olympus-ai-frontend/docs/DEPLOY_GCP.md` (ou raiz), se ainda não existir |

3. Siga os passos no documento; o padrão técnico segue o projeto **mcp-diagnosis-server** (Cloud Run, Artifact Registry, Cloud Build, Secret Manager, VPC/NAT quando necessário).

## Arquivos

- `olympus-ai-backend/DEPLOY_GCP.md` — backend Python/Flask + **gunicorn** (`wsgi.py`), secrets, rede, Cloud Build.
- `olympus-ai-frontend/DEPLOY_GCP.md` — frontend SPA (Vite/estático) ou Next.js SSR.
