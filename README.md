# Diagnóstico de PICs

Este repositório contém um servidor Flask compatível com endpoints OpenAI e agentes declarativos para diagnóstico de PICs instalados no parque.

O objetivo principal do sistema é identificar e classificar problemas operacionais, como falhas de rede, problemas de hardware ou configurações incorretas, permitindo uma resposta rápida e manutenção assertiva.

## Instalação e Execução

### Instalação

O sistema pode ser executado em modo local ou via Docker:

```bash
# Modo local (cria ambiente virtual e instala dependências)
./install.sh --local

# Modo Docker (constrói a imagem Docker)
./install.sh --docker
```

### Execução

```bash
# Modo local (ativa venv e executa main.py)
./run.sh --local

# Modo Docker (inicia container em background)
./run.sh --docker
```

### Parar o Servidor

```bash
# Para processo local na porta 6001
./stop.sh --local

# Para container Docker
./stop.sh --docker
```

### Desinstalação

O script de desinstalação remove recursos do sistema e pergunta interativamente se deseja deletar o banco de autenticação:

```bash
# Desinstala ambiente local
./uninstall.sh --local
# ⚠️ Pergunta: "Do you want to delete the authentication database (auth/auth.db)? [y/N]"

# Remove recursos Docker
./uninstall.sh --docker
# ⚠️ Pergunta: "Do you want to delete the authentication database (auth/auth.db)? [y/N]"
```

**Nota:** O banco de dados de autenticação (`auth/auth.db`) contém as chaves de API cadastradas. Se deletado, todas as chaves serão perdidas permanentemente.

## Endpoints Principais

O servidor expõe os seguintes endpoints HTTP:

- `GET /health` - Health check do serviço
- `GET /models` e `GET /v1/models` - Listagem de modelos registrados
- `POST /chat/completions` e `POST /v1/chat/completions` - Chat completions compatível com OpenAI

### Autenticação

- Rotas públicas: `/health`, `/models` e `/v1/models`
- Demais rotas exigem header `Authorization: Bearer <API_KEY>`

## Gerenciamento de Chaves de API

O sistema utiliza autenticação por chaves de API. Use o script `keys.sh` para gerenciar as chaves:

### Criar Chave

```bash
# Criar chave sem data de expiração
./keys.sh create "Nome do Cliente"
./keys.sh -c "Nome do Cliente"              # Forma abreviada

# Criar chave com data de expiração
./keys.sh create "Cliente" "2024-12-31"
./keys.sh -c "Cliente" "2024-12-31"         # Forma abreviada
```

### Listar Chaves

```bash
./keys.sh list
./keys.sh -ls                                # Forma abreviada
```

### Deletar Chave Específica

```bash
./keys.sh delete 5                           # Deleta chave com ID 5
./keys.sh -rm 5                              # Forma abreviada
```

### Deletar Todas as Chaves

```bash
./keys.sh delete-all
./keys.sh -rma                               # Forma abreviada
# ⚠️ Requer confirmação: digite 'DELETAR TUDO'
```

### Modo Docker

Para gerenciar chaves dentro do container Docker:

```bash
./keys.sh --docker list
./keys.sh -D -ls                             # Forma abreviada
```

### Resumo de Comandos

| Comando | Abreviação | Descrição |
|---------|------------|-----------|
| `create` | `-c` | Criar nova chave |
| `list` | `-ls` | Listar todas as chaves |
| `delete` | `-rm` | Deletar chave por ID |
| `delete-all` | `-rma` | Deletar todas as chaves |

**Flags de modo:**
- `-l`, `--local` - Executa localmente (padrão)
- `-D`, `--docker` - Executa no container Docker

## Estrutura de Autenticação

Os arquivos relacionados à autenticação estão organizados no diretório `auth/`:

- `auth/auth.db` - Banco SQLite com as chaves de API cadastradas
- `auth/manage_keys.py` - Script Python para gerenciamento de chaves
- [📄 Ver documentação da camada Auth](auth/README.md)

## Agentes Disponíveis

| Agente | Modelo | Uso Recomendado |
|---|---|---|
| `athena` | GPT-5.4 | Análises complexas, diagnósticos detalhados, planejamento estratégico |
| `saori` | GPT-5-mini | Tarefas simples, respostas rápidas, uso cotidiano |

Especifique o agente desejado no campo `model` da requisição. Se omitido, o servidor usa o agente padrão.

## Arquitetura do Sistema

O projeto segue uma arquitetura em camadas bem definida para separar responsabilidades, facilitar a manutenção e garantir a escalabilidade.

### Camadas

1.  **Agents (Camada de Apresentação / Rotas)**
    *   **Localização:** [`agents/`](agents/README.md)
    *   **Responsabilidade:** Atuam como pontos de entrada declarativos. Cada arquivo define um agente com metadados, aliases e modelo associado.
    *   **Função:** Conectam as requisições HTTP ao comportamento de chat e, quando aplicável, às rotas de ferramenta.
    *   [📄 Ver documentação e template da camada Agents](agents/README.md)

2.  **Services (Camada de Regra de Negócio)**
    *   **Localização:** [`services/`](services/README.md)
    *   **Responsabilidade:** Encapsular integrações e regras de negócio de diagnóstico.
    *   **Função:** Consumir serviços externos e retornar dados estruturados para os modelos/agentes.
    *   [📄 Ver documentação e template da camada Services](services/README.md)

3.  **Models (Camada de Modelo e Orquestração LLM)**
    *   **Localização:** [`models/`](models/README.md)
    *   **Responsabilidade:** Definir comportamento dos modelos de chat, prompts e tools.
    *   **Função:** Orquestrar execução via LangChain, com suporte a pensamento intermediário e contagem de tokens.
    *   [📄 Ver documentação e template da camada Models](models/README.md)

4.  **RAG (Recuperação de Conhecimento)**
    *   **Localização:** [`rag/`](rag/README.md)
    *   **Responsabilidade:** Fornecer coleções vetoriais e busca semântica (Weaviate), incluindo suporte a pesquisa web.
    *   **Função:** Indexar e recuperar contexto para enriquecer respostas dos modelos.
    *   [📄 Ver documentação e template da camada RAG](rag/README.md)

5.  **Server (Camada HTTP e Contrato OpenAI)**
    *   **Localização:** [`server/`](server/README.md)
    *   **Responsabilidade:** Disponibilizar endpoints HTTP, autenticação e stream SSE.
    *   **Função:** Resolver modelo de chat, rotear chamadas e montar payloads OpenAI-compatíveis.
    *   [📄 Ver documentação e template da camada Server](server/README.md)

6.  **Auth (Autenticação e Chaves)**
    *   **Localização:** [`auth/`](auth/README.md)
    *   **Responsabilidade:** Persistência e validação de chaves de API.
    *   **Função:** Criar/listar/remover chaves e validar acesso Bearer nas requisições.
    *   [📄 Ver documentação e template da camada Auth](auth/README.md)

7.  **Tools (Utilitários)**
    *   **Localização:** [`tools/`](tools/README.md)
    *   **Responsabilidade:** Scripts e funções auxiliares de uso geral.
    *   [📄 Ver documentação e template da camada Tools](tools/README.md)

8.  **Docs**
    *   **Localização:** [`docs/`](docs/README.md)
    *   **Conteúdo:** Documentação auxiliar, coleção do Postman e guias de uso.
    *   [📄 Ver documentação da pasta Docs](docs/README.md)
    *   [📄 Collection do Postman](docs/postman.json)

## Fluxo de Execução Típico

1.  Uma requisição chega em `POST /v1/chat/completions` com `Authorization: Bearer <API_KEY>`.
2.  O `server/server.py` valida autenticação, mensagem e modelo solicitado.
3.  O agente correspondente (camada `agents/`) encaminha a chamada para seu modelo (`models/`).
4.  O modelo pode acionar tools internas, serviços externos (`services/`) e/ou busca semântica (`rag/`).
5.  O servidor retorna resposta no formato OpenAI (`chat.completion` ou stream SSE).

## Documentação por Pasta

- [📄 Agents](agents/README.md)
- [📄 Auth](auth/README.md)
- [📄 Models](models/README.md)
- [📄 RAG](rag/README.md)
- [📄 Server](server/README.md)
- [📄 Services](services/README.md)
- [📄 Tools](tools/README.md)
- [📄 Docs](docs/README.md)
