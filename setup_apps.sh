#!/bin/bash
cd "$(dirname "$0")"

./enable_spi.sh
./enable_pcie3.sh

sudo apt update
sudo apt full-upgrade -y
sudo rpi-eeprom-update -a

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Caminho absoluto do script que deve rodar DEPOIS do reboot
SCRIPT_POS_REBOOT="$SCRIPT_DIR/setup_apps_2.sh"
LOG_FILE="$HOME/setup_log.txt"

# Adiciona ao Cronjob para rodar no próximo boot
# A linha abaixo diz: "No reboot, rode o script e envie o log para um arquivo"
(crontab -l 2>/dev/null; echo "@reboot $SCRIPT_POS_REBOOT >> $LOG_FILE 2>&1") | crontab -

echo "Configuração inicial feita. Reiniciando..."
sudo reboot