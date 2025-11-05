#!/bin/bash
set -e

# --- CONFIGURAOEES INICIAIS ---
PROJECT_DIR="$(pwd)"


# --- CRIA E CONFIGURA VENV (COM USUARIO NORMAL) ---
echo "=== Criando ambiente virtual ==="
python3 -m venv venv --system-site-packages
bash -c "source '$PROJECT_DIR/venv/bin/activate' && pip install --upgrade pip"


echo "Instalacao concluida!"
echo "Se desejar, reinicie o sistema com: sudo reboot"

