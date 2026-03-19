#!/bin/bash

# Define paths
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_CMD="python3"
SCRIPT_PATH="$BASE_DIR/auth/manage_keys.py"
VENV_PYTHON="$BASE_DIR/.venv/bin/python"

# Use venv python if available
if [ -f "$VENV_PYTHON" ]; then
    PYTHON_CMD="$VENV_PYTHON"
fi

# Check for mode flag
MODE=""
GCP_FLAG=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --docker|-D) MODE="docker"; shift ;;
        --local|-l)  MODE="local";  shift ;;
        --gcp|-G)    GCP_FLAG="--gcp"; shift ;;
        *) break ;;
    esac
done

# Default to local if no mode specified
if [ -z "$MODE" ]; then
    MODE="local"
fi

# Function to show usage
show_usage() {
    echo "Uso: ./keys.sh [MODO] [COMANDO] [ARGUMENTOS]"
    echo ""
    echo "Opções de modo:"
    echo "  -l, --local            Executa localmente (padrão)"
    echo "  -D, --docker           Executa dentro do container Docker"
    echo "  -G, --gcp              Adiciona chave ao GCP Secret Manager (Cloud Run)"
    echo ""
    echo "Comandos:"
    echo "  create, -c             Cria uma nova chave de API"
    echo "                         Ex: ./keys.sh create \"Cliente A\""
    echo "                         Ex: ./keys.sh -c \"Cliente A\" \"2024-12-31\""
    echo "                         Ex: ./keys.sh -G create \"Cloud Run Client\""
    echo "  list, -ls              Lista todas as chaves"
    echo "  delete, -rm            Deleta uma chave pelo ID"
    echo "  delete-all, -rma       Deleta TODAS as chaves (com confirmação)"
    echo ""
}

# Check if command is provided
if [ -z "$1" ]; then
    show_usage
    exit 1
fi

command="$1"
shift  # remove command from args

# Define execution command based on mode
if [ "$MODE" == "docker" ]; then
    CONTAINER_NAME="zeus-mcp-diagnosis-container"
    # Check if container is running
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        echo "Erro: Container '$CONTAINER_NAME' não está rodando."
        echo "Inicie-o primeiro com: ./run.sh --docker"
        exit 1
    fi
    EXEC_CMD="docker exec -i $CONTAINER_NAME python auth/manage_keys.py"
else
    EXEC_CMD="$PYTHON_CMD $SCRIPT_PATH"
fi

case "$command" in
    create|-c)
        if [ -z "$1" ]; then
            echo "Erro: Nome é obrigatório."
            show_usage
            exit 1
        fi
        $EXEC_CMD $GCP_FLAG create "$@"
        ;;
    list|-ls)
        $EXEC_CMD list
        ;;
    delete|-rm)
        if [ -z "$1" ]; then
            echo "Erro: ID é obrigatório."
            show_usage
            exit 1
        fi
        $EXEC_CMD delete "$@"
        ;;
    delete-all|-rma)
        $EXEC_CMD delete-all
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        echo "Comando desconhecido: $command"
        show_usage
        exit 1
        ;;
esac
