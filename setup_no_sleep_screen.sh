#!/bin/bash
set -e

USER_HOME="/home/cepedi"

SCRIPT_PATH="/usr/local/bin/disable-screen-blank.sh"
SERVICE_PATH="/etc/systemd/system/disable-screen-blank.service"

echo "================================================="
echo "➡️ Instalando script para NÃO apagar a tela (X11)"
echo "================================================="

# 1) Cria o script
sudo tee "$SCRIPT_PATH" >/dev/null <<EOF
#!/bin/bash
export DISPLAY=":0"
export XAUTHORITY="$USER_HOME/.Xauthority"

xset s off
xset s noblank
xset -dpms
EOF

sudo chmod +x "$SCRIPT_PATH"

echo "✅ Script criado em: $SCRIPT_PATH"

# 2) Cria o service
sudo tee "$SERVICE_PATH" >/dev/null <<EOF
[Unit]
Description=Disable screen blanking and DPMS
After=graphical.target

[Service]
Type=oneshot
ExecStart=$SCRIPT_PATH
RemainAfterExit=yes

[Install]
WantedBy=graphical.target
EOF

echo "✅ Service criado em: $SERVICE_PATH"

# 3) Ativa e roda agora
sudo systemctl daemon-reload
sudo systemctl enable --now disable-screen-blank.service

echo "================================================="
echo "✅ Pronto! A tela não vai mais apagar."
echo "================================================="

echo
echo "📌 Status do service:"
systemctl status disable-screen-blank.service --no-pager | head -n 25
