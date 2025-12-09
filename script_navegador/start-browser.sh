#!/bin/bash
# --- 1. DESCOBRE ONDE O SCRIPT ESTÁ ---
# Isso pega o caminho completo da pasta onde este arquivo .sh está salvo
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

# Define o caminho do .env baseando-se na localização do script (sobe um nível)
ENV_PATH="$SCRIPT_DIR/../.env"

# --- 2. CARREGA O .ENV ---
set -a
if [ -f "$ENV_PATH" ]; then
    source "$ENV_PATH"
    echo "Sucesso: .env carregado de $ENV_PATH"
else
    echo "ERRO CRÍTICO: .env não encontrado em $ENV_PATH"
    # Opcional: exit 1
fi
set +a

# Usu�rio dono da sess�o gr�fica
USER_HOME="/home/cepedi"

# Exporta vari�veis necess�rias para usar o X da sess�o gr�fica
export DISPLAY=":0"
export XAUTHORITY="$USER_HOME/.Xauthority"
export HOME="$USER_HOME"

# Garante que os diret�rios de config/crashpad existem
mkdir -p "$HOME/.config/chromium/Crashpad"

# Opcional: pequeno delay pra garantir que a interface j� subiu
sleep 3

echo "http://$IP_SERVER/posto/$POSTO"

exec /usr/bin/chromium \
  --noerrdialogs \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --kiosk \
  --disable-features=UseOzonePlatform,Translate,TranslateUI \
  --disable-translate \
  --no-first-run \
  --disable-gpu \
  --start-fullscreen \
  "http://$IP_SERVER/posto/$POSTO"
