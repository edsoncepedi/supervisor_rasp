#!/bin/bash
set -e

CONF="/etc/lightdm/lightdm.conf"

echo "➡️ Forçando X11 (LXDE-pi-x) via LightDM..."

sudo mkdir -p /etc/lightdm

# Se o arquivo não existir, cria com a seção correta
if [ ! -f "$CONF" ]; then
  echo "[Seat:*]" | sudo tee "$CONF" >/dev/null
fi

# Remove qualquer user-session existente
sudo sed -i '/^user-session=/d' "$CONF"

# Garante que a seção [Seat:*] existe e insere user-session logo abaixo
if grep -q "^\[Seat:\*\]" "$CONF"; then
  sudo sed -i '/^\[Seat:\*\]/a user-session=LXDE-pi-x' "$CONF"
else
  echo "[Seat:*]" | sudo tee -a "$CONF" >/dev/null
  echo "user-session=LXDE-pi-x" | sudo tee -a "$CONF" >/dev/null
fi

echo "✅ LightDM configurado para X11."
sleep 2

