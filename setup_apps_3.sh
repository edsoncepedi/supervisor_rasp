#!/bin/bash

cd "$(dirname "$0")"

# 1. REMOVER A TAREFA DO CRON (Auto-limpeza)
# Remove qualquer linha que contenha o nome deste script do crontab
crontab -l | grep -v "setup_apps_3.sh" | crontab -

sudo apt update && sudo apt install rpicam-apps

sudo apt install imx500-all -y

cd script_camera

./setup_script_rasp5.sh

cd ..

cd script_comando

./setup_script_rasp5.sh

cd ..

cd script_gerencidador

./setup_script_rasp5.sh

cd ..

./setup_supervisor.sh
