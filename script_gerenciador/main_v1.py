import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
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
TARGET_ID = [1052806641544, 357730659549, 584197438736, 584183791522]

is_output_active = False
miss_count = 0                # Conta quantas leituras falharam seguidas
MISS_LIMIT = 5                # Tolerância: 5 leituras falhas (~0,5s)
batedor = False
tempo_batedor = 2

# --- Configuração dos Pinos ---

GPIO.setup(TOMADA_POSTO, GPIO.OUT)
GPIO.setup(BATEDOR_POSTO, GPIO.OUT)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

GPIO.output(TOMADA_POSTO, GPIO.HIGH)
GPIO.output(BATEDOR_POSTO, GPIO.HIGH)

# Crie um objeto SimpleMFRC522
reader = SimpleMFRC522()

def set_lamp_state(active_status):
    global is_output_active

    if active_status != is_output_active:
        if active_status:
            GPIO.output(TOMADA_POSTO, GPIO.LOW)
            print("✅ Lâmpada LIGADA.")
        else:
            GPIO.output(TOMADA_POSTO, GPIO.HIGH)
            print("❌ Lâmpada DESLIGADA.")

        is_output_active = active_status

try:
    while True:
        id = reader.read_id_no_block()
        status_botao = GPIO.input(BUTTON_PIN)

        if id:
            for i in TARGET_ID:
                if i == id:
                    miss_count = 0
                    set_lamp_state(True)
                    break
                else:
                    pass
            
        elif id is None:
            miss_count += 1
            if miss_count >= MISS_LIMIT:
                set_lamp_state(False)
        else:
            set_lamp_state(False)
            miss_count = 0
        
        if status_botao == GPIO.LOW:
            tempo = time.time()
            batedor = True
        
        if batedor:
            tempo_decorrido = time.time() - tempo
            if tempo_decorrido <= tempo_batedor:
                GPIO.output(BATEDOR_POSTO, GPIO.LOW)
            else:
                GPIO.output(BATEDOR_POSTO, GPIO.HIGH)
                batedor = False

        time.sleep(0.1)

except KeyboardInterrupt:   
    print("\nStop: Programa encerrado.")

finally:
    GPIO.cleanup()

