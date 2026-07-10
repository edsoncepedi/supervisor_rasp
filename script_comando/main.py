import requests
import RPi.GPIO as GPIO
import time
import os
from dotenv import load_dotenv
import socket
import paho.mqtt.client as mqtt  # type: ignore



dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

GPIO.setwarnings(False)

POSTO = f"posto_{int(os.getenv('POSTO'))}"


try:
    GPIO.setmode(GPIO.BCM)
except Exception:
    pass

try:
    GPIO.cleanup()
except Exception:
    pass

GPIO.setmode(GPIO.BCM)

BOTAO_IMPRESSORA = int(os.getenv('BOTAO_IMPRESSORA'))
estado_anterior_pedal = GPIO.HIGH

GPIO.setup(BOTAO_IMPRESSORA, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def button_calback(channel):
    print("Botão Pressionado")

    # Defina a URL e os dados a serem enviados na requisição POST
    url = f"http://{os.getenv('IP_SERVER')}/comando"
    payload = {'comando': 'imprime_produto'}

    # Cabeçalhos da requisição
    headers = {'Content-Type': 'application/json'}

    # Envia o POST
    response = requests.post(url, json=payload, headers=headers)

    # Imprima o código de status e o conteúdo da resposta
    print(f"Código de Status: {response.status_code}")
    print(f"Conteúdo da Resposta: {response.text}")

def verifica_botao(pino):
    """Detecta acionamento do pedal."""
    global estado_anterior_pedal
    estado_atual = GPIO.input(pino)

    if estado_atual != estado_anterior_pedal:
        estado_anterior_pedal = estado_atual

        if estado_atual == GPIO.LOW:
            print("Botão pressionado")
            button_calback(pino)


try:
    while True:
        verifica_botao(BOTAO_IMPRESSORA)                    
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nPrograma encerrado.")

finally:
    time.sleep(0.3)
    GPIO.cleanup()    

