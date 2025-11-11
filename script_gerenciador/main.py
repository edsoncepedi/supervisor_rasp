import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import paho.mqtt.client as mqtt
import time

GPIO.setmode(GPIO.BCM)

# --- CONFIGURAÇÕES DO BROKER ---
BROKER = "172.16.10.175"
PORT = 1883
TOPIC = "ControleProducao_DD"

# --- DEFINIÇÃO DOS PINOS ---
TOMADA_POSTO = 17
BATEDOR_POSTO = 27
PEDAL = 21
SENSOR_PALETE = 20
SENSOR_CORRENTE = 16  # Sensor da parafusadeira (digital)

# --- VARIÁVEIS GLOBAIS ---
is_output_active = False
batedor = False
tempo_batedor = 0

estado_anterior_parafusadeira = GPIO.HIGH
estado_anterior_palete = GPIO.HIGH
estado_anterior_pedal = GPIO.HIGH

ultimo_id = None
ultimo_id_lido = None
ultimo_tempo_lido = 0
TEMPO_PERDA_CARTAO = 1.0  # Tempo para considerar que o cartão saiu

# --- CONFIGURAÇÃO DOS PINOS ---
GPIO.setup(TOMADA_POSTO, GPIO.OUT)
GPIO.setup(BATEDOR_POSTO, GPIO.OUT)
GPIO.setup(SENSOR_PALETE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(SENSOR_CORRENTE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PEDAL, GPIO.IN, pull_up_down=GPIO.PUD_UP)

GPIO.output(TOMADA_POSTO, GPIO.HIGH)
GPIO.output(BATEDOR_POSTO, GPIO.HIGH)

# --- CALLBACKS MQTT ---
def on_connect(client, userdata, flags, reason_code, properties):
    """Chamado quando o Raspberry conecta ao broker."""
    if reason_code == 0:
        print("Conectado ao broker MQTT!")
        client.subscribe(TOPIC)
        print(f"Assinado o tópico: {TOPIC}")
    else:
        print(f"Falha na conexão. Código de retorno: {reason_code}")

def on_message(client, userdata, msg):
    """Processa mensagens recebidas via MQTT."""
    global batedor, tempo_batedor
    mensagem = msg.payload.decode()

    match mensagem:
        case "batedor":
            print("Palete liberado")
            batedor = True
            tempo_batedor = time.time()

        case "libera_posto":
            set_lamp_state(True)

        case "desliga_posto":
            set_lamp_state(False)

# --- FUNÇÕES AUXILIARES ---
def set_lamp_state(ativo):

    global is_output_active
    # Só faz algo se o novo estado for diferente do atual
    if ativo != is_output_active:
        if ativo:
            # Liga a tomada (nível baixo no pino)
            GPIO.output(TOMADA_POSTO, GPIO.LOW)
            print("Posto Liberado (Tomada LIGADA)")
        else:
            # Desliga a tomada (nível alto no pino)
            GPIO.output(TOMADA_POSTO, GPIO.HIGH)
            print("Posto Desligado (Tomada DESLIGADA)")

        # Atualiza o estado armazenado
        is_output_active = ativo

def verificar_cartao(leitor, cliente, topico):
    """Verifica presença e remoção de cartões RFID."""
    global ultimo_id, ultimo_id_lido, ultimo_tempo_lido

    id_atual = leitor.read_id_no_block()

    if id_atual:  # Cartão detectado
        ultimo_id_lido = id_atual
        ultimo_tempo_lido = time.time()

        if id_atual != ultimo_id:
            ultimo_id = id_atual
            print(f"Cartão detectado: {id_atual}")
            cliente.publish(topico, f"{id_atual}")

    else:  # Nenhum cartão detectado
        if ultimo_id is not None and (time.time() - ultimo_tempo_lido > TEMPO_PERDA_CARTAO):
            print("Cartão removido.")
            cliente.publish(topico, "REMOVIDO")
            ultimo_id = None

def verifica_sensor_indutivo(pino_sensor, cliente):
    """Detecta chegada e saída de palete."""
    global estado_anterior_palete
    estado_atual = GPIO.input(pino_sensor)

    if estado_atual != estado_anterior_palete:
        estado_anterior_palete = estado_atual

        if estado_atual == GPIO.LOW:
            print("Chegou palete")
            cliente.publish(TOPIC, "Chegou palete")
        else:
            print("Palete removido")
            cliente.publish(TOPIC, "Palete removido")

def verifica_pedal(pino_pedal, cliente):
    """Detecta acionamento do pedal."""
    global estado_anterior_pedal
    estado_atual = GPIO.input(pino_pedal)

    if estado_atual != estado_anterior_pedal:
        estado_anterior_pedal = estado_atual

        if estado_atual == GPIO.LOW:
            print("Pedal pressionado")
            cliente.publish(TOPIC, "Pedal")

def verifica_parafusadeira(pino_sensor, cliente):
    """Detecta acionamento da parafusadeira."""
    global estado_anterior_parafusadeira
    estado_atual = GPIO.input(pino_sensor)

    if estado_atual != estado_anterior_parafusadeira:
        estado_anterior_parafusadeira = estado_atual

        if estado_atual == GPIO.LOW:
            print("Parafusadeira acionada")
            cliente.publish(TOPIC, "Parafusadeira")

# --- CONFIGURAÇÃO INICIAL ---
leitor = SimpleMFRC522()
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()

# --- LOOP PRINCIPAL ---
try:
    while True:
        verificar_cartao(leitor, client, TOPIC)
        verifica_sensor_indutivo(SENSOR_PALETE, client)
        verifica_pedal(PEDAL, client)
        verifica_parafusadeira(SENSOR_CORRENTE, client)

        # Controle do batedor com tempo
        if batedor:
            if time.time() - tempo_batedor <= 2:
                GPIO.output(BATEDOR_POSTO, GPIO.LOW)
            else:
                GPIO.output(BATEDOR_POSTO, GPIO.HIGH)
                batedor = False

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\n🛑 Programa encerrado.")

finally:
    GPIO.cleanup()
    client.loop_stop()
    client.disconnect()
