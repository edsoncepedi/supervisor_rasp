#!/bin/bash
cd "$(dirname "$0")"

# --- RECONFIGURAÇÃO DE AMBIENTE ---
REAL_USER="$USER"
REAL_HOME="$HOME"

# 1. REMOVER A TAREFA DO CRON DESTE SCRIPT
crontab -l | grep -v "setup_apps_2.sh" | crontab -

echo "--- Iniciando Parte 2 (Pós-Reboot) ---"
echo "Instalando dependências pesadas..."

# Instalações
sudo apt install dkms -y
sudo apt install hailo-all -y

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- PREPARAÇÃO PARA O PRÓXIMO BOOT (Parte 3) ---
SCRIPT_POS_REBOOT="$SCRIPT_DIR/setup_apps_3.sh"
LOG_FILE="$REAL_HOME/setup_log3.txt"

# 1. Cria o log 3 e ajusta permissões
touch "$LOG_FILE"

# 2. ATUALIZA o Autostart Visual para ler o NOVO log
# Simplesmente sobrescrevemos o arquivo .desktop apontando para o setup_log3.txt
DESKTOP_FILE="$REAL_HOME/.config/autostart/monitor_install.desktop"

cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Application
Name=Instalação Parte 3
Exec=lxterminal --title="Finalizando Instalação... (NÃO FECHE)" -e "tail -f $LOG_FILE"
Terminal=false
X-KeepTerminal=true
EOF

# 3. Agenda a Parte 3 no Cron
(crontab -l 2>/dev/null; echo "@reboot $SCRIPT_POS_REBOOT >> $LOG_FILE 2>&1") | crontab -

echo "Parte 2 concluída. Reiniciando para etapa final..."
sudo reboot