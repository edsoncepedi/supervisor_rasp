import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522  # type: ignore
import requests
import paho.mqtt.client as mqtt  # type: ignore
import time
import os
import threading
from dotenv import load_dotenv
import spidev


dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

GPIO.setwarnings(False)

try:
    GPIO.setmode(GPIO.BCM)
except Exception:
    pass

try:
    GPIO.cleanup()
except Exception:
    pass

GPIO.setmode(GPIO.BCM)

# =========================
# RC522 - AUTO RECOVER (THREAD)
# =========================
RST_PIN = 25  # GPIO ligado no RST do RC522
GPIO.setup(RST_PIN, GPIO.OUT, initial=GPIO.HIGH)

RFID_WATCHDOG_TIMEOUT = 8.0   # se o SPI travar, reseta
RFID_REINIT_COOLDOWN = 1.0    # espera entre tentativas de reinit
RFID_READ_INTERVAL = 0.15     # intervalo de leitura
RFID_DEBOUNCE = 1.0           # evita spam do mesmo UID

rfid_desconectou = False
uid_no_momento_da_falha = None
aguardando_confirmacao_pos_reconexao = False

rfid_reconectado = False
rfid_flag_lock = threading.Lock()

# TESTE SPI
SPI_BUS = 0
SPI_DEV = 0  # CE0 (mude para 1 se seu SDA estiver no CE1)
SPI_HZ = 1_000_000

RC522_VERSION_REG = 0x37
RC522_OK_VALUES = {0x91, 0x92}
HEALTHCHECK_INTERVAL = 2.0

CONFIRM_TIMEOUT = 8.0  # tempo máximo para esperar uma leitura após reconectar
ts_reconexao = 0.0

# Compartilhamento thread -> main
uid_atual = None
uid_ts = 0.0
uid_lock = threading.Lock()

stop_event = threading.Event()

# --- CONFIGURAÇÕES DO BROKER ---
BROKER = os.getenv('IP_SERVER')
PORT = int(os.getenv('PORT_MQTT', 1883))
TOPIC_PRODUCAO = "ControleProducao_DD"

# --- CONFIGURAÇÕES DO FLASK ---
URL = f"http://{os.getenv('IP_SERVER')}/rfid__checkin_posto"
POSTO = f"posto_{int(os.getenv('POSTO'))}"
TOPIC_SISTEMA = f"rastreio_nfc/raspberry/{POSTO}/sistema"
TOPIC_ENVIO_RASP = f"rastreio_nfc/raspberry/{POSTO}/dispositivo"
TOPIC_ENVIO_ESP = f"rastreio_nfc/esp32/{POSTO}/dispositivo"

# --- DEFINIÇÃO DOS PINOS ---
TOMADA_POSTO = int(os.getenv('TOMADA_POSTO'))
BATEDOR_POSTO = int(os.getenv('BATEDOR_POSTO'))
PEDAL = int(os.getenv('PEDAL'))
SENSOR_PALETE = int(os.getenv('SENSOR_PALETE'))
SENSOR_CORRENTE = int(os.getenv('SENSOR_CORRENTE'))  # Sensor da parafusadeira (digital)

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


# =========================
# HELPERS RC522
# =========================
def reset_rc522():
    GPIO.output(RST_PIN, GPIO.LOW)
    time.sleep(0.2)
    GPIO.output(RST_PIN, GPIO.HIGH)
    time.sleep(0.2)

def spi_read_reg(spi, addr):
    resp = spi.xfer2([((addr << 1) & 0x7E) | 0x80, 0x00])
    return resp[1]

def rc522_healthcheck(spi) -> bool:
    """
    Verifica se o RC522 está respondendo de verdade no SPI.
    """
    try:
        v = spi_read_reg(spi, RC522_VERSION_REG)
        return v in RC522_OK_VALUES
    except Exception:
        return False

def rfid_worker():
    global uid_atual, uid_ts

    leitor = None
    spi = None

    last_healthcheck = 0.0
    last_ok = time.time()

    last_uid_seen_ts = time.time()
    RFID_UID_TIMEOUT = 10.0  # se ficar 10s sem conseguir ler nenhum UID, reinicia o leitor


    while not stop_event.is_set():
        agora = time.time()

        # 1) Abre SPI se necessário
        if spi is None:
            try:
                spi = spidev.SpiDev()
                spi.open(SPI_BUS, SPI_DEV)
                spi.max_speed_hz = SPI_HZ
                spi.mode = 0
            except Exception as e:
                print(f"❌ RFID: falha ao abrir SPI: {e}")
                spi = None
                time.sleep(1.0)
                continue

        # 2) Inicializa leitor se necessário
        if leitor is None:
            try:
                print("⚙️ RFID: inicializando RC522...")
                reset_rc522()
                leitor = SimpleMFRC522()
                print("✅ RFID: RC522 inicializado!")
                with rfid_flag_lock:
                    global rfid_reconectado, ts_reconexao
                    rfid_reconectado = True
                    ts_reconexao = time.time()
                last_ok = agora
                last_healthcheck = 0.0
            except Exception as e:
                print(f"⏳ RFID: falha init RC522: {e}")
                leitor = None
                time.sleep(RFID_REINIT_COOLDOWN)
                continue

        # 3) Healthcheck REAL (VersionReg)
        if (agora - last_healthcheck) >= HEALTHCHECK_INTERVAL:
            last_healthcheck = agora

            if not rc522_healthcheck(spi):
                print("⚠️ RFID: RC522 não responde SPI (healthcheck). Reiniciando...")
                leitor = None
                try:
                    spi.close()
                except Exception:
                    pass
                spi = None
                time.sleep(0.5)
                with rfid_flag_lock:
                    global rfid_desconectou, uid_no_momento_da_falha, aguardando_confirmacao_pos_reconexao
                    rfid_desconectou = True
                    uid_no_momento_da_falha = uid_atual  # captura o último UID visto
                    aguardando_confirmacao_pos_reconexao = True
                continue
            else:
                last_ok = agora  # SPI respondeu corretamente

        # 4) Leitura normal (não bloqueante)
        try:
            uid = leitor.read_id_no_block()
        except Exception as e:
            print(f"❌ RFID: erro lendo: {e}")
            uid = None

        # 5) Debounce + publicar UID
        if uid:
            last_uid_seen_ts = agora  # <<< ADICIONE ISSO
            with uid_lock:
                if uid != uid_atual or (agora - uid_ts) > RFID_DEBOUNCE:
                    uid_atual = uid
                    uid_ts = agora

        # 6) Watchdog extra (caso tudo fique estranho)
        if (agora - last_ok) > RFID_WATCHDOG_TIMEOUT:
            print("⚠️ RFID: watchdog. Reiniciando...")
            leitor = None
            try:
                spi.close()
            except Exception:
                pass
            spi = None
        
        if (agora - last_uid_seen_ts) > RFID_UID_TIMEOUT:
            print("⚠️ RFID: sem leitura de UID há muito tempo. Forçando reinicialização...")
            leitor = None
            try:
                spi.close()
            except Exception:
                pass
            spi = None
            last_uid_seen_ts = agora

        time.sleep(RFID_READ_INTERVAL)

def tratar_pos_reconexao():
    global ultimo_id
    global rfid_reconectado, aguardando_confirmacao_pos_reconexao
    global uid_no_momento_da_falha, ts_reconexao

    agora = time.time()

    # Só roda quando houve reconexão e estamos aguardando confirmação
    with rfid_flag_lock:
        if not rfid_reconectado or not aguardando_confirmacao_pos_reconexao:
            return
        # NÃO consome rfid_reconectado aqui ainda, pois podemos precisar aguardar leitura
        t0 = ts_reconexao

    # Lê UID mais recente vindo da thread
    with uid_lock:
        uid = uid_atual
        ts = uid_ts

    # (A) Se já tivemos UMA leitura válida depois da reconexão:
    if uid and ts >= t0:
        # consome flags (decisão tomada)
        with rfid_flag_lock:
            rfid_reconectado = False
            aguardando_confirmacao_pos_reconexao = False

        # mesmo cartão do momento da queda -> não faz nada
        if uid_no_momento_da_falha is not None and uid == uid_no_momento_da_falha:
            print("✅ RFID voltou e o mesmo cartão ainda está presente. Não faz checkout.")
            return

        # cartão mudou -> se tinha alguém logado, faz checkout confirmado
        if ultimo_id is not None:
            print("⚠️ RFID voltou e o cartão mudou. Fazendo checkout confirmado.")
            checkout()
            set_lamp_state(False)
            ultimo_id = None
        return

    # (B) Ainda não leu nada após reconectar: espera até CONFIRM_TIMEOUT
    if (agora - t0) < CONFIRM_TIMEOUT:
        return

    # (C) Estourou timeout: assume que NÃO há cartão (confirmado)
    with rfid_flag_lock:
        rfid_reconectado = False
        aguardando_confirmacao_pos_reconexao = False

    if ultimo_id is not None:
        print("⚠️ RFID voltou, mas não houve leitura após timeout. Fazendo checkout confirmado.")
        checkout()
        set_lamp_state(False)
        ultimo_id = None



# --- CALLBACKS MQTT ---
def on_connect(client, userdata, flags, reason_code, properties):
    """Chamado quando o Raspberry conecta ao broker."""
    if reason_code == 0:
        print("Conectado ao broker MQTT!")
        client.subscribe(TOPIC_PRODUCAO)
        print(f"Assinado o tópico: {TOPIC_PRODUCAO}")
        client.subscribe(TOPIC_SISTEMA)
        print(f"Assinado o tópico: {TOPIC_SISTEMA}")
    else:
        print(f"Falha na conexão. Código de retorno: {reason_code}")


def on_message(cliente, userdata, msg):
    """Processa mensagens recebidas via MQTT."""
    global ultimo_id, batedor, tempo_batedor
    mensagem = msg.payload.decode()

    if msg.topic == TOPIC_SISTEMA:
        match mensagem:
            case "statusPalete":
                status = GPIO.input(SENSOR_PALETE)
                if not status:
                    print("MQTT Check: Palete no Posto")
                    cliente.publish(TOPIC_ENVIO_RASP, 1)
                else:
                    print("MQTT Check: Sem Palete")
                    cliente.publish(TOPIC_ENVIO_RASP, 0)

            case "statusCard":
                # Verifica a memória do programa, não o hardware
                if ultimo_id is None:
                    print("MQTT Check: Sem cartão")
                    cliente.publish(TOPIC_ENVIO_RASP, "None")
                else:
                    print(f"MQTT Check: ID {ultimo_id}")
                    cliente.publish(TOPIC_ENVIO_RASP, ultimo_id)

            case "batedor":
                ativar_batedor()


# --- FUNÇÕES AUXILIARES ---
def set_lamp_state(ativo):
    global is_output_active

    if ativo != is_output_active:
        if ativo:
            GPIO.output(TOMADA_POSTO, GPIO.LOW)
            print("Posto Liberado")
        else:
            GPIO.output(TOMADA_POSTO, GPIO.HIGH)
            print("Posto Desligado")

        is_output_active = ativo


def ativar_batedor():
    global batedor, tempo_batedor
    tempo_batedor = time.time()
    batedor = True


def checkout():
    """Realiza o checkout do funcionário."""
    payload = {'tag': None, 'posto': POSTO, 'acao': 'saida'}
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(URL, json=payload, headers=headers, timeout=2)

        if response.ok:
            print("Checkout realizado com sucesso.")
        else:
            print("Erro ao realizar checkout.")

    except Exception as e:
        print(f"Erro ao enviar requisição: {e}")


def verifica_id(tag):
    payload = {'tag': str(tag), 'posto': POSTO, 'acao': 'entrada'}
    headers = {'Content-Type': 'application/json'}

    print(payload)

    try:
        response = requests.post(URL, json=payload, headers=headers, timeout=2)

        if response.ok:
            data = response.json()
            if data.get("autorizado"):
                set_lamp_state(True)
            else:
                print("Acesso negado ou tag não reconhecida.")
        else:
            print("Erro na comunicação com o servidor.")

    except Exception as e:
        print(f"Erro ao enviar requisição: {e}")


def processar_rfid():
    """
    Consome o UID vindo da thread do RFID e aplica a mesma lógica original:
    - detecta entrada de novo cartão
    - detecta remoção (timeout)
    """
    with rfid_flag_lock:
        if aguardando_confirmacao_pos_reconexao:
            # enquanto o RFID está em falha/reconexão, não faz checkout "normal"
            return

    global ultimo_id, ultimo_id_lido, ultimo_tempo_lido

    agora = time.time()

    with uid_lock:
        uid = uid_atual
        ts = uid_ts

    # Se temos um UID "recente"
    if uid and (agora - ts) < 2.0:
        ultimo_id_lido = uid
        ultimo_tempo_lido = agora

        if uid != ultimo_id:
            ultimo_id = uid
            print(f"Cartão detectado: {uid}")
            verifica_id(uid)

    else:
        # Nenhum UID novo recentemente => pode considerar cartão removido
        if ultimo_id is not None and (agora - ultimo_tempo_lido > TEMPO_PERDA_CARTAO):
            print("Cartão removido.")
            checkout()
            set_lamp_state(False)
            ultimo_id = None


def verifica_sensor_indutivo(pino_sensor, cliente):
    """Detecta chegada e saída de palete."""
    global estado_anterior_palete
    estado_atual = GPIO.input(pino_sensor)

    if estado_atual != estado_anterior_palete:
        estado_anterior_palete = estado_atual

        if estado_atual == GPIO.LOW:
            print("Chegou palete")
            cliente.publish(TOPIC_ENVIO_ESP, "BS")
        else:
            print("Palete removido")
            cliente.publish(TOPIC_ENVIO_ESP, "BD")


def verifica_pedal(pino_pedal, cliente):
    """Detecta acionamento do pedal."""
    global estado_anterior_pedal
    estado_atual = GPIO.input(pino_pedal)

    if estado_atual != estado_anterior_pedal:
        estado_anterior_pedal = estado_atual

        if estado_atual == GPIO.LOW:
            print("Pedal pressionado")
            cliente.publish(TOPIC_ENVIO_ESP, "BT2")


def verifica_parafusadeira(pino_sensor, cliente):
    """Detecta acionamento da parafusadeira."""
    global estado_anterior_parafusadeira
    estado_atual = GPIO.input(pino_sensor)

    if estado_atual != estado_anterior_parafusadeira:
        estado_anterior_parafusadeira = estado_atual

        if estado_atual == GPIO.LOW:
            print("Parafusadeira acionada")
            cliente.publish(TOPIC_ENVIO_ESP, "BT1")


# =========================
# MAIN
# =========================
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()

# Inicia a thread do RFID
t_rfid = threading.Thread(target=rfid_worker, daemon=True)
t_rfid.start()

# --- LOOP PRINCIPAL ---
try:
    while True:
        # RFID agora é consumido via thread
        tratar_pos_reconexao()
        processar_rfid()

        # Sensores continuam iguais
        verifica_parafusadeira(SENSOR_CORRENTE, client)  # BT1
        verifica_pedal(PEDAL, client)                    # BT2
        verifica_sensor_indutivo(SENSOR_PALETE, client)  # BD

        # Controle do batedor com tempo
        if batedor:
            print("Palete livre")
            if time.time() - tempo_batedor <= 2:
                GPIO.output(BATEDOR_POSTO, GPIO.LOW)
            else:
                GPIO.output(BATEDOR_POSTO, GPIO.HIGH)
                batedor = False

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nPrograma encerrado.")

finally:
    stop_event.set()
    time.sleep(0.3)

    GPIO.cleanup()
    client.loop_stop()
    client.disconnect()
