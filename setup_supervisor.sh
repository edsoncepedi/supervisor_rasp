#!/bin/bash
set -e

# Atualiza pacotes e instala o Supervisor
sudo apt-get update
sudo apt-get install -y supervisor

# Caminho da pasta onde o script esta
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Exemplo: criar link simbolico de uma subpasta "origem" para "link_origem"
ORIGEM="$SCRIPT_DIR/supervisor_rasp.conf"
DESTINO="/etc/supervisor/conf.d/"

# Cria o link apenas se nao existir
if [ ! -L "$DESTINO" ]; then
    echo "Criando link simbolico de $ORIGEM -> $DESTINO"
    ln -s "$ORIGEM" "$DESTINO"
else
    echo "Link simbolico ja existe: $DESTINO"
fi

echo "Se desejar, reinicie o sistema com: sudo reboot"
