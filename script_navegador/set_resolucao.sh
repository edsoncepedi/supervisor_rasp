#!/bin/bash

export DISPLAY=":0"
export XAUTHORITY="/home/cepedi/.Xauthority"

TARGET_MODE="1280x720"

mapfile -t MONS < <(xrandr --query | awk '/ connected/{print $1}')

M1="${MONS[0]}"
M2="${MONS[1]}"

if [ -z "$M1" ]; then
  echo "❌ Nenhum monitor conectado detectado."
  exit 1
fi

echo "➡️ Monitor 1: $M1"
xrandr --output "$M1" --mode "$TARGET_MODE" --pos 0x0 --primary

if [ -n "$M2" ]; then
  echo "➡️ Monitor 2: $M2"
  xrandr --output "$M2" --mode "$TARGET_MODE" --pos 1280x0 --right-of "$M1"
fi

echo "✅ Resolução aplicada!"
