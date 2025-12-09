#!/bin/bash

# Usuário dono da sessão gráfica
USER_HOME="/home/cepedi"

# Exporta variáveis necessárias para usar o X da sessão gráfica
export DISPLAY=":0"
export XAUTHORITY="$USER_HOME/.Xauthority"
export HOME="$USER_HOME"

# Garante que os diretórios de config/crashpad existem
mkdir -p "$HOME/.config/chromium/Crashpad"

# Opcional: pequeno delay pra garantir que a interface já subiu
sleep 3

exec /usr/bin/chromium \
  --noerrdialogs \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --kiosk \
  --disable-features=UseOzonePlatform \
  --disable-gpu \
  --start-fullscreen \
  "http://172.16.10.175/posto/0"
