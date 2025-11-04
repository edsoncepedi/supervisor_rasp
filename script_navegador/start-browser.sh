#!/bin/bash

# Define display e permissões
export DISPLAY=:0
export XAUTHORITY=/home/$USER/.Xauthority

# Abre Chromium em modo kiosk
/usr/bin/chromium-browser \
  --noerrdialogs \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --kiosk \
  --start-fullscreen \
  "$URL" 
#&

# Aguarda o navegador abrir
#sleep 10

# Foca a janela
#xdotool search -sync --onlyvisible --class Chromium windowactivate