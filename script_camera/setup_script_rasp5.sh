#!/bin/bash
set -e

# --- CONFIGURAOEES INICIAIS ---
PROJECT_DIR="$(pwd)"


# --- CRIA E CONFIGURA VENV (COM USUARIO NORMAL) ---
echo "=== Criando ambiente virtual ==="
python3 -m venv degirum_env
bash -c "source '$PROJECT_DIR/degirum_env/bin/activate' && pip install --upgrade pip && pip install -r requirements.txt" 

echo "=== Criando ambiente virtual - Sem GUI ==="
python3 -m venv venv_headless
bash -c "source '$PROJECT_DIR/venv_headless/bin/activate' && pip install --upgrade pip && pip install -r requeriments_headless.txt" 

echo "Instalacao concluida!"
echo "Se desejar, reinicie o sistema com: sudo reboot"

