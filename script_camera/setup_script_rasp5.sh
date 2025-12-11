#!/bin/bash
set -e

# --- CONFIGURAOEES INICIAIS ---
PROJECT_DIR="$(pwd)"


# --- CRIA E CONFIGURA VENV (COM USUARIO NORMAL) ---
echo "=== Criando ambiente virtual ==="
python3 -m venv degirum_env
bash -c "source '$PROJECT_DIR/degirum_env/bin/activate' && pip install --upgrade pip && pip install -r requirements.txt" 

echo "Instalacao concluida!"
echo "Se desejar, reinicie o sistema com: sudo reboot"

