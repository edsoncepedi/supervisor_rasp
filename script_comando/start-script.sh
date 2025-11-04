#!/bin/bash
# Ativa o ambiente virtual e executa o script Python (que roda em loop)

# Caminho absoluto para o diretorio do projeto
PROJECT_DIR="$(dirname "$(realpath "$0")")"

# Caminho da venv
VENV_DIR="$PROJECT_DIR/venv"

# Ativa a virtualenv
source "$VENV_DIR/bin/activate"

# Executa o script Python
python "$PROJECT_DIR/main.py"
