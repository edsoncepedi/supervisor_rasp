#!/bin/bash

CONFIG_FILE="/boot/firmware/config.txt"
BACKUP_FILE="/boot/firmware/config.txt.bak_pcie"

echo "--- Ativando PCIe Gen 3.0 no Raspberry Pi 5 ---"

# 1. Verifica existência do arquivo
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERRO: Arquivo de configuração não encontrado."
    exit 1
fi

# 2. Backup
echo "Criando backup..."
sudo cp "$CONFIG_FILE" "$BACKUP_FILE"

# 3. Aplica a configuração
# Verifica se a chave dtparam=pciex1_gen já existe no arquivo
if grep -q "dtparam=pciex1_gen" "$CONFIG_FILE"; then
    echo "Configuração encontrada. Atualizando para Gen 3..."
    # Substitui a linha existente (ex: gen=2) para gen=3
    sudo sed -i 's/^.*dtparam=pciex1_gen.*/dtparam=pciex1_gen=3/' "$CONFIG_FILE"
else
    echo "Configuração não encontrada. Adicionando ao final do arquivo..."
    # Adiciona nova linha
    echo "dtparam=pciex1_gen=3" | sudo tee -a "$CONFIG_FILE" > /dev/null
fi

# 4. Verificação visual
if grep -q "dtparam=pciex1_gen=3" "$CONFIG_FILE"; then
    echo "SUCESSO: PCIe Gen 3 configurado."
else
    echo "FALHA: Não foi possível escrever no arquivo."
fi
