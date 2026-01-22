#!/bin/bash

# Define que o script deve parar imediatamente se qualquer comando der erro
set -e
cd "$(dirname "$0")"

echo "--- Iniciando Setup Geral (Parte 3) ---"

# 1. REMOVER A TAREFA DO CRON
crontab -l | grep -v "setup_apps_3.sh" | crontab - || true

echo "--- Instalando Dependencias do Sistema ---"
sudo apt update && sudo apt install rpicam-apps -y
sudo apt install imx500-all -y

# Função para rodar scripts de forma segura
rodar_script() {
    PASTA=$1
    SCRIPT=$2

    echo "--- Entrando em $PASTA para rodar $SCRIPT ---"

    if [ -d "$PASTA" ]; then
        cd "$PASTA"
        chmod +x "$SCRIPT"
        ./"$SCRIPT"
        cd ..
    else
        echo "ERRO: Pasta $PASTA não encontrada!"
        exit 1
    fi
}

# Executa a sequência
rodar_script "script_camera" "setup_script_rasp5.sh"
rodar_script "script_comando" "setup_script_rasp5.sh"
rodar_script "script_gerenciador" "setup_script_rasp5.sh"

echo "--- Rodando Supervisor ---"
chmod +x setup_supervisor.sh
./setup_supervisor.sh

# --- LIMPEZA FINAL ---
echo "--- Limpando arquivos de inicialização ---"
# Remove o lançador visual para não abrir mais janelas nos próximos boots
rm "$HOME/.config/autostart/monitor_install.desktop"

echo "--- INSTALAÇÃO TOTALMENTE CONCLUÍDA! ---"
echo "Você pode fechar esta janela agora."

# Pequena pausa para garantir que a mensagem apareça antes de qualquer fechamento
sleep 5