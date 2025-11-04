#!/bin/bash
set -e

# --- CONFIGURAOEES INICIAIS ---
PROJECT_DIR="$(pwd)"
START_SCRIPT="$PROJECT_DIR/start-script.sh"

# --- CRIA E CONFIGURA VENV (COM USUARIO NORMAL) ---
echo "=== Criando ambiente virtual ==="
sudo -u "$SUDO_USER" python3 -m venv "$PROJECT_DIR/venv" --system-site-packages
sudo -u "$SUDO_USER" bash -c "source '$PROJECT_DIR/venv/bin/activate' && pip install --upgrade pip"

if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    echo "=== Instalando dependencias ==="
    sudo -u "$SUDO_USER" bash -c "source '$PROJECT_DIR/venv/bin/activate' && pip install -r '$PROJECT_DIR/requirements.txt'"
else
    echo "??  Arquivo requirements.txt nao encontrado. Pulando instalaçao de dependencias."
fi

# --- DA PERMISSAO AO SCRIPT PRINCIPAL ---
chmod +x "$START_SCRIPT"

echo "Instalaçao concluida!"
echo "Se desejar, reinicie o sistema com: sudo reboot"
