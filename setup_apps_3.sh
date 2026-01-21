#!/bin/bash

cd "$(dirname "$0")"

# 1. REMOVER A TAREFA DO CRON (Auto-limpeza)
# Remove qualquer linha que contenha o nome deste script do crontab
crontab -l | grep -v "setup_apps_3.sh" | crontab -

sudo apt update && sudo apt install rpicam-apps

sudo apt install imx500-all -y

sudo reboot