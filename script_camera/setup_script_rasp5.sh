#!/bin/bash
set -e

# --- CONFIGURAOEES INICIAIS ---
PROJECT_DIR="$(pwd)"

sudo apt-get update
sudo apt-get install -y make build-essential libssl-dev zlib1g-dev \
libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev \
libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev python3-openssl

#curl https://pyenv.run | bash

#echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
#echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
#echo 'eval "$(pyenv init - bash)"' >> ~/.bashrc
#echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc

#source ~/.bashrc

#pyenv install 3.11.2
#~/.pyenv/versions/3.11.2/bin/python -m venv degirum_env --system-site-packages

sudo apt install python3-opencv python3-munkres -y
sudo apt install python3-libcamera python3-kms++ -y

#/usr/bin/python3 -m venv --system-site-packages /home/cepedi/supervisor_rasp/script_camera/degirum_env

# --- CRIA E CONFIGURA VENV (COM USUARIO NORMAL) ---
echo "=== Criando ambiente virtual ==="
python3 -m venv degirum_env --system-site-packages
bash -c "source '$PROJECT_DIR/degirum_env/bin/activate' && pip install --upgrade pip && pip install -r requirements.txt" 

#echo "=== Criando ambiente virtual - Sem GUI ==="
#python3 -m venv venv_headless
#bash -c "source '$PROJECT_DIR/venv_headless/bin/activate' && pip install --upgrade pip && pip install -r requirements_headless.txt"

echo "Instalacao concluida!"


