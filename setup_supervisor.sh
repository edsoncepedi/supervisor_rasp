#!/bin/bash
set -e

sudo apt-get update
sudo apt-get install supervisor

# --- CONFIGURAOEES INICIAIS ---
PROJECT_DIR="$(pwd)"
START_SCRIPT="$PROJECT_DIR/**/setup_*.sh"

# --- DA PERMISSAO AO SCRIPT PRINCIPAL ---
chmod +x "$START_SCRIPT"

echo "Instalaçao concluida!"
echo "Se desejar, reinicie o sistema com: sudo reboot"
