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

# --- Declaração de Variaveis ---
TARGET_ID = [1052806641544, 357730659549, 584197438736]

is_output_active = False
miss_count = 0                # Conta quantas leituras falharam seguidas
MISS_LIMIT = 5                # Tolerância: 5 leituras falhas (~0,5s)
batedor = False
tempo = time.time()

last_id = None          # Último cartão detectado
last_seen_id = None     # Último ID realmente lido
last_seen_time = 0      # Última vez que o cartão foi visto
CARD_LOST_TIMEOUT = 1.0 # Tempo (em segundos) para considerar o cartão removido

# --- Configuração dos Pinos ---

GPIO.setup(TOMADA_POSTO, GPIO.OUT)
GPIO.setup(BATEDOR_POSTO, GPIO.OUT)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

GPIO.output(TOMADA_POSTO, GPIO.HIGH)
GPIO.output(BATEDOR_POSTO, GPIO.HIGH)

# Crie um objeto SimpleMFRC522
reader = SimpleMFRC522()

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
    print(f"📨 Mensagem recebida no tópico '{msg.topic}': {mensagem}")

    match mensagem:
        case "batedor":
            global batedor
            global tempo 
            print("Palete liberado")
            batedor = True
            tempo = time.time()
        
        case "posto":
            print("Posto liberado")

def set_lamp_state(active_status):
    global is_output_active
    if active_status != is_output_active:
        GPIO.output(TOMADA_POSTO, GPIO.LOW if active_status else GPIO.HIGH)
        print("✅ Lâmpada LIGADA." if active_status else "❌ Lâmpada DESLIGADA.")
        is_output_active = active_status

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


        # --- Se um cartão foi detectado ---
        if id:
            last_seen_id = id
            last_seen_time = time.time()

            # Se for um novo cartão diferente do anterior
            if id != last_id:
                last_id = id
                print(f"🪪 Novo cartão detectado: {id}")
                client.publish("danilo/cartao", f"{id}")

        # --- Se nenhum cartão foi detectado ---
        else:
            # Verifica se já faz tempo suficiente sem detectar nada
            if last_id is not None and (time.time() - last_seen_time > CARD_LOST_TIMEOUT):
                print("🚫 Cartão removido.")
                client.publish("danilo/cartao", "REMOVIDO")
                last_id = None  # Reseta estado
        
        
        if status_botao == GPIO.LOW:
            mensagem = "Pedal"
            client.publish(TOPIC, mensagem)
        
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


'''
        if id:
            client.publish(TOPIC, id)
            miss_count = 0
            #set_lamp_state(True)

        elif id is None:
            # Se não leu nada, conta uma falha
            miss_count += 1
            if miss_count >= MISS_LIMIT:
                set_lamp_state(False)
        else:
            # Cartão diferente do alvo
            set_lamp_state(False)
            miss_count = 0
'''