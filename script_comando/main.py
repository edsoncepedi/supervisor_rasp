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

TOPIC_ENVIO_ESP = f"rastreio_nfc/esp32/{POSTO}/dispositivo"


BROKER = os.getenv('IP_SERVER')
PORT = int(os.getenv('PORT_MQTT', 1883))


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

client.reconnect_delay_set(min_delay=1, max_delay=30)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Conectado ao broker MQTT!")
        print(f"Publicando no tópico: {TOPIC_ENVIO_ESP}")
    else:
        print(f"Falha na conexão MQTT. Código: {reason_code}")


client.on_connect = on_connect


def conectar_mqtt_bloqueante():
    while True:
        try:
            print(f"Tentando MQTT em {BROKER}:{PORT} ...")
            client.connect(BROKER, PORT, keepalive=60)
            print("MQTT conectado.")
            return True
        except (OSError, socket.error) as e:
            print(f"Rede/MQTT indisponível: {e}. Tentando novamente em 1s...")
            time.sleep(1)

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

    client.publish(TOPIC_ENVIO_ESP, "BS")
    print(f"MQTT enviado: BS -> {TOPIC_ENVIO_ESP}")

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

conectar_mqtt_bloqueante()
client.loop_start()

try:
    while True:
        verifica_botao(BOTAO_IMPRESSORA)                    
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nPrograma encerrado.")

finally:
    time.sleep(0.3)
    GPIO.cleanup()    
    client.loop_stop()
    client.disconnect()

