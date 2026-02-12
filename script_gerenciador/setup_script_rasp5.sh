#!/bin/bash
set -e

# --- CONFIGURAOEES INICIAIS ---
PROJECT_DIR="$(pwd)"


# --- CRIA E CONFIGURA VENV (COM USUARIO NORMAL) ---
echo "=== Criando ambiente virtual ==="
python3 -m venv venv
bash -c "source '$PROJECT_DIR/venv/bin/activate' && pip install --upgrade pip && pip install -r requirements5.txt" 

echo "Venv criada e dependencias instaladas com sucesso!"


