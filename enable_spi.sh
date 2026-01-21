#!/bin/bash

# Caminho do arquivo de configuração no Raspberry Pi 5
CONFIG_FILE="/boot/firmware/config.txt"
BACKUP_FILE="/boot/firmware/config.txt.bak"

echo "--- Configurando SPI no Raspberry Pi 5 ---"

# 1. Verificar se o arquivo existe
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERRO: Arquivo $CONFIG_FILE não encontrado."
    exit 1
fi

# 2. Criar backup por segurança
echo "Criando backup em $BACKUP_FILE..."
sudo cp "$CONFIG_FILE" "$BACKUP_FILE"

# 3. Verificar e modificar
if grep -q "^dtparam=spi=on" "$CONFIG_FILE"; then
    echo "O SPI já está habilitado (linha encontrada e descomentada)."
elif grep -q "dtparam=spi=on" "$CONFIG_FILE"; then
    echo "Linha encontrada, mas comentada. Habilitando..."
    # Usa sed para substituir qualquer coisa antes de dtparam=spi=on por nada, efetivamente descomentando
    sudo sed -i 's/^#*dtparam=spi=on/dtparam=spi=on/' "$CONFIG_FILE"
    echo "Sucesso! Linha descomentada."
else
    echo "Linha não encontrada. Adicionando ao final do arquivo..."
    echo "dtparam=spi=on" | sudo tee -a "$CONFIG_FILE" > /dev/null
    echo "Sucesso! Linha adicionada."
fi

echo "--- Concluído ---"
echo "Por favor, reinicie o Raspberry Pi para aplicar as alterações."