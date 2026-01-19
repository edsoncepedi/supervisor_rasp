#!/bin/bash

# --- 1. DESCOBRE ONDE O SCRIPT ESTÁ ---
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
ENV_PATH="$SCRIPT_DIR/../.env"

# --- 2. CARREGA O .ENV ---
set -a
if [ -f "$ENV_PATH" ]; then
    source "$ENV_PATH"
    echo "Sucesso: .env carregado de $ENV_PATH"
else
    echo "ERRO CRÍTICO: .env não encontrado em $ENV_PATH"
fi
set +a

# Usuário da sessão gráfica
USER_HOME="/home/cepedi"

export DISPLAY=":0"
export XAUTHORITY="$USER_HOME/.Xauthority"
export HOME="$USER_HOME"

mkdir -p "$HOME/.config/chromium/Crashpad"

# Aguarda interface gráfica
sleep 3

# URLs
URL_MONITOR_1="http://$IP_SERVER:$PORT_SERVER/posto/$POSTO"
URL_MONITOR_2="http://$IP_SERVER:$PORT_FRONTEND/"

# Resolução dos monitores (AJUSTE SE NECESSÁRIO)
MONITOR_WIDTH=1920
MONITOR_HEIGHT=1080

# ---------------- MONITOR 1 ----------------
/usr/bin/chromium \
  --user-data-dir=/tmp/chrome1 \
  --noerrdialogs \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --kiosk \
  --no-first-run \
  --disable-gpu \
  --window-position=0,0 \
  --window-size=${MONITOR_WIDTH},${MONITOR_HEIGHT} \
  "$URL_MONITOR_1" &

sleep 1

# ---------------- MONITOR 2 ----------------
/usr/bin/chromium \
  --user-data-dir=/tmp/chrome2 \
  --noerrdialogs \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --kiosk \
  --no-first-run \
  --disable-gpu \
  --window-position=${MONITOR_WIDTH},0 \
  --window-size=${MONITOR_WIDTH},${MONITOR_HEIGHT} \
  "$URL_MONITOR_2"
