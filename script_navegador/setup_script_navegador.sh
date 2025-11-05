#!/bin/bash
set -e

# --- RECONFIGURA SISTEMA ---
echo "=== Reconfigurando pacotes quebrados ==="
dpkg --configure -a

echo "=== Atualizando sistema ==="
apt update && apt upgrade -y

echo "=== Instalando dependncias ==="
apt install -y chromium xdotool wmctrl

chmod +x $PWD/start-browser.sh

# --- CRIA SERVIO SYSTEMD ---
echo "=== Criando servico systemd ==="
cat << EOF > /usr/lib/systemd/system/auto_nav.service
[Unit]
Description=Inicia o navegador automaticamente em modo kiosk
After=network.target graphical.target
Requires=graphical.target

[Service]
User=$SUDO_USER
Environment=XDG_RUNTIME_DIR=/run/user/1000
Environment=DISPLAY=:0
Environment=URL=$KIOSK_URL

ExecStartPre=/bin/sleep $WAIT_TIME
ExecStart=$PWD/start-browser.sh

Restart=always

[Install]
WantedBy=graphical.target
EOF


sudo reboot
