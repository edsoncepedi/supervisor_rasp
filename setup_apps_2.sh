#!/bin/bash
cd "$(dirname "$0")"

# 1. REMOVER A TAREFA DO CRON (Auto-limpeza)
# Remove qualquer linha que contenha o nome deste script do crontab
crontab -l | grep -v "setup_apps_2.sh" | crontab -

# 2. Seu código continua aqui...
echo "Estou rodando após o reboot!"
# Instalar docker, baixar pacotes, etc...

sudo apt install dkms -y
sudo apt install hailo-all -y

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Caminho absoluto do script que deve rodar DEPOIS do reboot
SCRIPT_POS_REBOOT="$SCRIPT_DIR/setup_apps_3.sh"
LOG_FILE="$HOME/setup_log3.txt"

# Adiciona ao Cronjob para rodar no próximo boot
# A linha abaixo diz: "No reboot, rode o script e envie o log para um arquivo"
(crontab -l 2>/dev/null; echo "@reboot $SCRIPT_POS_REBOOT >> $LOG_FILE 2>&1") | crontab -

echo "Configuração inicial feita. Reiniciando..."
sudo reboot