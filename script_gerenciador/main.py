import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import paho.mqtt.client as mqtt
import time

GPIO.setmode(GPIO.BCM) 

# --- CONFIGURAÇÕES DO BROKER ---
BROKER = "172.16.10.175"   
PORT = 1883                     
TOPIC = "ControleProducao_DD"          

# --- Definição dos Pinos ---a
TOMADA_POSTO = 17 
BATEDOR_POSTO = 27  
BUTTON_PIN = 21 

is_output_active = False
miss_count = 0                # Conta quantas leituras falharam seguidas
MISS_LIMIT = 5                # Tolerância: 5 leituras falhas (~0,5s)
batedor = False
tempo = time.time()

ultimo_id = None              # Último cartão confirmado
ultimo_id_lido = None         # Último cartão detectado (mesmo que temporário)
ultimo_tempo_lido = 0         # Momento em que o cartão foi lido pela última vez
TEMPO_PERDA_CARTAO = 1.0      # Tempo em segundos para considerar o cartão removido

# --- Configuração dos Pinos ---

GPIO.setup(TOMADA_POSTO, GPIO.OUT)
GPIO.setup(BATEDOR_POSTO, GPIO.OUT)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

GPIO.output(TOMADA_POSTO, GPIO.HIGH)
GPIO.output(BATEDOR_POSTO, GPIO.HIGH)

def on_connect(client, userdata, flags, rc):
    """Chamado quando o Raspberry conecta ao broker."""
    if rc == 0:
        print("✅ Conectado ao broker MQTT!")
        client.subscribe(TOPIC)
        print(f"📡 Assinado o tópico: {TOPIC}")
    else:
        print(f"❌ Falha na conexão. Código de retorno: {rc}")


def on_message(client, userdata, msg):
    mensagem = msg.payload.decode()

    match mensagem:
        case "batedor":
            global batedor, tempo 
            print("✅ - Palete liberado")
            batedor = True
            tempo = time.time()
        
        case "libera_posto":
            set_lamp_state(True)
        
        case "desliga_posto":
            set_lamp_state(False)

def set_lamp_state(active_status):
    global is_output_active

    if active_status != is_output_active:
        if active_status:
            GPIO.output(TOMADA_POSTO, GPIO.LOW)
            print("✅ - Posto Liberado")
        else:
            GPIO.output(TOMADA_POSTO, GPIO.HIGH)
            print("❌ - Posto Desligado")

        is_output_active = active_status

def verificar_cartao(leitor, cliente_mqtt, topico):

    global ultimo_id, ultimo_id_lido, ultimo_tempo_lido

    id_atual = leitor.read_id_no_block()  # Lê o cartão (ou None)

    # --- Quando há um cartão detectado ---
    if id_atual:
        ultimo_id_lido = id_atual
        ultimo_tempo_lido = time.time()

        # Se for um novo cartão, diferente do anterior confirmado
        if id_atual != ultimo_id:
            ultimo_id = id_atual
            print(f"🪪 Novo cartão detectado: {id_atual}")
            cliente_mqtt.publish(topico, f"{id_atual}")

    # --- Quando não há cartão detectado ---
    else:
        # Se havia um cartão e já passou tempo suficiente sem detectar nada
        if ultimo_id is not None and (time.time() - ultimo_tempo_lido > TEMPO_PERDA_CARTAO):
            print("🚫 Cartão removido.")
            cliente_mqtt.publish(topico, "REMOVIDO")
            ultimo_id = None  # Reseta o estado

    # Pode colocar um pequeno atraso se quiser aliviar a CPU
    time.sleep(0.1)

def verifica_palete():
    mensagem = "Chegou Palete"
    client.publish(TOPIC, mensagem)

# Crie um objeto SimpleMFRC522
reader = SimpleMFRC522()

# --- CRIA CLIENTE MQTT ---
client = mqtt.Client()
client.connect(BROKER, PORT, keepalive=60)

# --- CONFIGURA E CONECTA O CLIENTE ---
client.on_connect = on_connect
client.on_message = on_message

client.loop_start()

try:
    print("ONLINE!!")
    while True:
        id = reader.read_id_no_block()
        status_botao = GPIO.input(BUTTON_PIN)

        verificar_cartao(reader, client, TOPIC)

        if status_botao == GPIO.LOW:
            print("Pedal Pressionado")
            client.publish(TOPIC, "Pedal")
        
        if batedor:
            tempo_decorrido = time.time() - tempo
            if tempo_decorrido <= 2:
                GPIO.output(BATEDOR_POSTO, GPIO.LOW)
            else:
                GPIO.output(BATEDOR_POSTO, GPIO.HIGH)
                batedor = False

        time.sleep(0.1)

except KeyboardInterrupt:   
    print("\nStop: Programa encerrado.")

finally:
    GPIO.cleanup()
    client.loop_stop()
    client.disconnect()
