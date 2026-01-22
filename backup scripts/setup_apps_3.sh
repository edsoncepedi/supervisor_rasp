#!/bin/bash

# Define que o script deve parar imediatamente se qualquer comando der erro
set -e

cd "$(dirname "$0")"

echo "--- Iniciando Setup Geral ---"

# 1. REMOVER A TAREFA DO CRON
crontab -l | grep -v "setup_apps_3.sh" | crontab - || true
# (O || true evita que o script pare se o crontab estiver vazio)

echo "--- Instalando Dependencias do Sistema ---"
# CORREÇÃO: Adicionado -y para não travar pedindo confirmação
sudo apt update && sudo apt install rpicam-apps -y
sudo apt install imx500-all -y

# Função para rodar scripts de forma segura
rodar_script() {
    PASTA=$1
    SCRIPT=$2

    echo "--- Entrando em $PASTA para rodar $SCRIPT ---"

    # Verifica se a pasta existe antes de entrar
    if [ -d "$PASTA" ]; then
        cd "$PASTA"

        # Garante que o script é executável
        chmod +x "$SCRIPT"

        # Roda o script
        ./"$SCRIPT"

        # Volta para o diretório anterior (seguro)
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

echo "--- Concluido com Sucesso ---"
