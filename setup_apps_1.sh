#!/bin/bash
cd "$(dirname "$0")"

# --- CONFIGURAÇÃO DE USUÁRIO (Para o modo visual funcionar) ---
# Detecta quem é o usuário real logado na interface (evita ser root se usar sudo)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

echo "--- Iniciando Parte 1 ---"
echo "Usuário detectado: $REAL_USER"

# Executa scripts de hardware
chmod +x ./enable_spi.sh ./enable_pcie3.sh ./disable_wayland.sh
./enable_spi.sh
./enable_pcie3.sh
./disable_wayland.sh

sudo systemctl disable wayvnc
sudo systemctl stop wayvnc

sudo systemctl enable vncserver-x11-serviced
sudo systemctl start vncserver-x11-serviced

sudo apt update
sudo apt full-upgrade -y
sudo rpi-eeprom-update -a

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- PREPARAÇÃO PARA O PRÓXIMO BOOT (Parte 2) ---
SCRIPT_POS_REBOOT="$SCRIPT_DIR/setup_apps_2.sh"
LOG_FILE="$REAL_HOME/setup_log2.txt"

# 1. Cria o arquivo de log vazio agora e dá permissão ao usuário (para o terminal conseguir ler)
touch "$LOG_FILE"
chown "$REAL_USER":"$REAL_USER" "$LOG_FILE"

# 2. Cria o Autostart Visual (A janela que abre sozinha)
AUTOSTART_DIR="$REAL_HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/monitor_install.desktop"

mkdir -p "$AUTOSTART_DIR"
chown "$REAL_USER":"$REAL_USER" "$AUTOSTART_DIR"

cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Application
Name=Instalação Parte 2
Exec=lxterminal --title="Instalando Parte 2... (NÃO FECHE)" -e "tail -f $LOG_FILE"
Terminal=false
X-KeepTerminal=true
EOF
chown "$REAL_USER":"$REAL_USER" "$DESKTOP_FILE"

# 3. Adiciona ao Cronjob
# Nota: Usamos 'sudo -u $REAL_USER' para garantir que o cron rode no user certo
(crontab -u "$REAL_USER" -l 2>/dev/null; echo "@reboot $SCRIPT_POS_REBOOT >> $LOG_FILE 2>&1") | crontab -u "$REAL_USER" -

echo "Configuração inicial feita. Reiniciando..."
sudo reboot