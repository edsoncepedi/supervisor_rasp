import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522  # type: ignore
import requests
import paho.mqtt.client as mqtt  # type: ignore
import time
import os
import threading
from dotenv import load_dotenv
import spidev
import socket

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

# --- RESYNC CHECKOUT (quando não há cartão) ---
checkout_pendente = False
checkout_retry_interval = 2.0      # começa tentando a cada 2s
CHECKOUT_RETRY_MAX = 30.0          # máximo entre tentativas
checkout_next_try_ts = 0.0
SEM_CARTAO_HEARTBEAT = 10.0
ultimo_heartbeat_sem_cartao = 0

# TESTE SPI
SPI_BUS = 0
SPI_DEV = 0  # CE0 (mude para 1 se seu SDA estiver no CE1)
SPI_HZ = 1_000_000

RC522_VERSION_REG = 0x37
RC522_OK_VALUES = {0x91, 0x92}
HEALTHCHECK_INTERVAL = 2.0

CONFIRM_TIMEOUT = 15.0  # tempo máximo para esperar uma leitura após reconectar
ts_reconexao = 0.0

# Compartilhamento thread -> main
uid_atual = None
uid_ts = 0.0
uid_lock = threading.Lock()

stop_event = threading.Event()

# --- CONFIGURAÇÕES DO BROKER ---
BROKER = os.getenv('IP_SERVER')
PORT = int(os.getenv('PORT_MQTT', 1883))
PORT_SERVER = int(os.getenv('PORT_SERVER', 8000))
TOPIC_PRODUCAO = "ControleProducao_DD"

# --- CONFIGURAÇÕES DO FLASK ---
URL = f"http://{os.getenv('IP_SERVER')}:{PORT_SERVER}/rfid__checkin_posto"
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

HEARTBEAT_INTERVAL = 5
ultimo_heartbeat = 0

# --- CONFIGURAÇÃO DOS PINOS ---
GPIO.setup(TOMADA_POSTO, GPIO.OUT)
GPIO.setup(BATEDOR_POSTO, GPIO.OUT)
GPIO.setup(SENSOR_PALETE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(SENSOR_CORRENTE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PEDAL, GPIO.IN, pull_up_down=GPIO.PUD_UP)

rele_tomada_ativo_em = int(os.getenv('RELE_TOMADA_ATIVO_EM', '0'))
rele_batedor_ativo_em = int(os.getenv('RELE_BATEDOR_ATIVO_EM', '0'))

if rele_tomada_ativo_em == 0:
    GPIO.output(TOMADA_POSTO, GPIO.HIGH)
else:
    GPIO.output(TOMADA_POSTO, GPIO.LOW)

if rele_batedor_ativo_em == 0:
    GPIO.output(BATEDOR_POSTO, GPIO.HIGH)
else:
    GPIO.output(BATEDOR_POSTO, GPIO.LOW)

### =================================
### Controle Batedor
### =================================

aguardando_saida_palete = False
tempo_ultimo_batedor = 0
TEMPO_RETENTATIVA_BATEDOR = 3.0

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
    global rfid_reconectado, ts_reconexao
    global rfid_desconectou, uid_no_momento_da_falha, aguardando_confirmacao_pos_reconexao

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

                with uid_lock:
                    ultimo_uid_visto = uid_atual

                leitor = None
                try:
                    spi.close()
                except Exception:
                    pass
                spi = None

                with uid_lock:
                    uid_atual = None
                    uid_ts = 0.0

                time.sleep(0.5)

                with rfid_flag_lock:
                    rfid_desconectou = True
                    uid_no_momento_da_falha = ultimo_uid_visto
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
            
            rfid_desconectou = False
        # 6) Watchdog extra (caso tudo fique estranho)
        if (agora - last_ok) > RFID_WATCHDOG_TIMEOUT:
            print("⚠️ RFID: watchdog. Reiniciando...")

            with uid_lock:
                uid_atual = None
                uid_ts = 0.0

            leitor = None
            try:
                spi.close()
            except Exception:
                pass
            spi = None
        """
        if (agora - last_uid_seen_ts) > RFID_UID_TIMEOUT:
            print("⚠️ RFID: sem leitura de UID há muito tempo. Forçando reinicialização...")

            with uid_lock:
                uid_atual = None
                uid_ts = 0.0

            leitor = None
            try:
                spi.close()
            except Exception:
                pass
            spi = None
            last_uid_seen_ts = agora"""

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
            if rele_tomada_ativo_em == 0:
                GPIO.output(TOMADA_POSTO, GPIO.LOW)
            else:
                GPIO.output(TOMADA_POSTO, GPIO.HIGH)
            print("Posto Liberado")
        else:
            if rele_tomada_ativo_em == 0:
                GPIO.output(TOMADA_POSTO, GPIO.HIGH)
            else:
                GPIO.output(TOMADA_POSTO, GPIO.LOW)
            print("Posto Desligado")

        is_output_active = ativo


def ativar_batedor():
    global batedor, tempo_batedor
    global aguardando_saida_palete, tempo_ultimo_batedor

    tempo_batedor = time.time()
    tempo_ultimo_batedor = tempo_batedor
    batedor = True

    aguardando_saida_palete = True

    print("🔨 Batedor acionado, aguardando saída do palete")

def checkout() -> bool:
    """Realiza o checkout do funcionário. Retorna True se o backend respondeu."""
    payload = {'tag': None, 'posto': POSTO, 'acao': 'saida'}
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(URL, json=payload, headers=headers, timeout=2)

        if response.ok:
            print("Checkout sincronizado com backend.")
            return True

        else:
            print(f"Checkout erro HTTP: {response.status_code}")
            return False

    except Exception as e:
        print(f"Checkout falhou (rede): {e}")
        return False


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

BOOT_GRACE_PERIOD = 15.0
program_start_ts = time.time()

def confirmar_remocao_cartao():
    """
    Faz algumas tentativas curtas antes de concluir que o cartão saiu.
    Evita checkout falso por falha momentânea do RC522.
    """
    tentativas = 8

    for _ in range(tentativas):
        with uid_lock:
            uid = uid_atual
            ts = uid_ts

        agora = time.time()

        if uid and (agora - ts) < 2.5:
            return False

        time.sleep(0.15)

    return True

def processar_rfid():
    global ultimo_id, ultimo_id_lido, ultimo_tempo_lido
    global checkout_pendente, checkout_retry_interval, checkout_next_try_ts

    if (time.time() - program_start_ts) < BOOT_GRACE_PERIOD:
        return

    with rfid_flag_lock:
        if aguardando_confirmacao_pos_reconexao:
            return

    agora = time.time()

    with uid_lock:
        uid = uid_atual
        ts = uid_ts

    # Se houve leitura recente, mantém sessão viva
    if uid and (agora - ts) < 2.5:
        ultimo_id_lido = uid
        ultimo_tempo_lido = agora

        if uid != ultimo_id:
            ultimo_id = uid
            print(f"Cartão detectado: {uid}")
            verifica_id(uid)

        return

    # Se não há ninguém logado, não há o que fazer
    if ultimo_id is None:
        return

    # Ainda não passou o tempo de perda
    if (agora - ultimo_tempo_lido) <= TEMPO_PERDA_CARTAO:
        return

    # Confirma ausência antes de derrubar sessão
    if not confirmar_remocao_cartao():
        ultimo_tempo_lido = time.time()
        return

    print("Cartão removido.")
    ok = checkout()
    set_lamp_state(False)
    ultimo_id = None

    if not ok:
        checkout_pendente = True
        checkout_retry_interval = 2.0
        checkout_next_try_ts = time.time() + checkout_retry_interval
"""
def processar_rfid():
    global ultimo_id, ultimo_id_lido, ultimo_tempo_lido
    global checkout_pendente, checkout_retry_interval, checkout_next_try_ts
    global rfid_desconectou

    if (time.time() - program_start_ts) < BOOT_GRACE_PERIOD:
        return
    
    if rfid_desconectou:
        return

    with rfid_flag_lock:
        if aguardando_confirmacao_pos_reconexao:
            return

    agora = time.time()

    with uid_lock:
        uid = uid_atual
        ts = uid_ts

    cartao_presente = bool(uid and (agora - ts) < 2.5)

    if cartao_presente:
        ultimo_id_lido = uid
        ultimo_tempo_lido = agora

        if uid != ultimo_id:
            ultimo_id = uid
            print(f"Cartão detectado: {uid}")
            verifica_id(uid)

    else:
        if ultimo_id is not None and (agora - ultimo_tempo_lido > TEMPO_PERDA_CARTAO):
            print("Cartão removido.")
            ok = checkout()
            set_lamp_state(False)
            ultimo_id = None

            if not ok:
                checkout_pendente = True
                checkout_retry_interval = 2.0
                checkout_next_try_ts = time.time() + checkout_retry_interval"""


def tratar_checkout_pendente():
    """Trata o modo resync de checkout pendente."""
    global checkout_pendente, checkout_retry_interval, checkout_next_try_ts

    if not checkout_pendente:
        return

    agora = time.time()
    if agora >= checkout_next_try_ts:
        print("Tentando reenviar checkout pendente...")
        ok = checkout()
        if ok:
            print("Checkout reenviado com sucesso.")
            checkout_pendente = False
        else:
            # aumenta o intervalo de retry (exponencial)
            checkout_retry_interval = min(checkout_retry_interval * 2.0, CHECKOUT_RETRY_MAX)
            checkout_next_try_ts = agora + checkout_retry_interval


def verifica_sensor_indutivo(pino_sensor, cliente):
    global estado_anterior_palete
    global aguardando_saida_palete

    estado_atual = GPIO.input(pino_sensor)

    if estado_atual != estado_anterior_palete:

        estado_anterior_palete = estado_atual

        if estado_atual == GPIO.LOW:
            print("Chegou palete")

        else:
            print("Palete removido")
            cliente.publish(TOPIC_ENVIO_ESP, "BD")

            if aguardando_saida_palete:
                aguardando_saida_palete = False
                print("BD enviado (ciclo concluído)")
            


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

def verificar_palete_preso():
    global aguardando_saida_palete
    global tempo_ultimo_batedor
    global batedor, tempo_batedor

    if not aguardando_saida_palete:
        return

    agora = time.time()

    if agora - tempo_ultimo_batedor > TEMPO_RETENTATIVA_BATEDOR:

        print("⚠️ Palete possivelmente preso, tentando novamente")

        tempo_batedor = agora
        tempo_ultimo_batedor = agora
        batedor = True

def resync_checkout_se_necessario():
    global checkout_pendente, checkout_retry_interval, checkout_next_try_ts

    if not checkout_pendente:
        return

    agora = time.time()
    if agora < checkout_next_try_ts:
        return

    # Só faz sentido resync se NÃO há cartão e a tomada está desligada
    with uid_lock:
        uid = uid_atual
        ts = uid_ts

    cartao_presente = bool(uid and (agora - ts) < 2.0)
    if cartao_presente:
        # cartão voltou, não insistir em "saida"
        checkout_pendente = False
        return

    ok = checkout()
    if ok:
        checkout_pendente = False
        checkout_retry_interval = 2.0
        return

    # backoff (2s, 4s, 8s... até 30s)
    checkout_retry_interval = min(checkout_retry_interval * 2.0, CHECKOUT_RETRY_MAX)
    checkout_next_try_ts = agora + checkout_retry_interval
    print(f"🔁 Checkout pendente. Tentando novamente em {checkout_retry_interval:.0f}s...")

def heartbeat_sem_cartao():
    global ultimo_heartbeat_sem_cartao

    agora = time.time()

    with uid_lock:
        uid = uid_atual
        ts = uid_ts

    cartao_presente = bool(uid and (agora - ts) < 2.0)

    if cartao_presente:
        return

    if (agora - ultimo_heartbeat_sem_cartao) < SEM_CARTAO_HEARTBEAT:
        return

    print("🔄 Heartbeat sem cartão -> sincronizando saída")
    checkout()

    ultimo_heartbeat_sem_cartao = agora


def enviar_heartbeat():
    global ultimo_heartbeat, ultimo_id, checkout_pendente

    agora = time.time()

    if agora - ultimo_heartbeat < HEARTBEAT_INTERVAL:
        return

    ultimo_heartbeat = agora

    if ultimo_id is None:
        return

    payload = {
        "posto": POSTO,
        "tag": str(ultimo_id)
    }

    try:
        response = requests.post(
            f"http://{os.getenv('IP_SERVER')}/rfid_heartbeat",
            json=payload,
            timeout=(1, 2)
        )

        if not response.ok:
            print(f"Heartbeat erro HTTP: {response.status_code}")
            return

        data = response.json()
        acao = data.get("acao")
        motivo = data.get("motivo", "")

        print("Heartbeat resposta completa:", data)

        if acao == "logout":
            print(f"⚠️ Logout forçado pelo backend: {motivo}")

            # desliga o posto imediatamente
            set_lamp_state(False)

            # limpa o estado local para permitir novo login automático
            ultimo_id = None

            # cancela qualquer resync antigo de checkout
            checkout_pendente = False

    except Exception as e:
        print("Falha heartbeat:", e)
# =========================
# MAIN
# =========================
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

# Reconnect automático do paho (quando cair depois de já ter conectado)
client.reconnect_delay_set(min_delay=1, max_delay=30)

def conectar_mqtt_bloqueante():
    """
    Não deixa o programa morrer se a rede ainda não subiu.
    Fica tentando até conectar.
    """
    while not stop_event.is_set():
        try:
            print(f"🌐 Tentando MQTT em {BROKER}:{PORT} ...")
            client.connect(BROKER, PORT, keepalive=60)
            print("✅ MQTT conectado (connect OK).")
            return True
        except (OSError, socket.error) as e:
            print(f"⏳ Rede/MQTT indisponível: {e}. Tentando de novo em 1s...")
            time.sleep(1)
    return False

# Só inicia o loop do MQTT depois que conectar
if conectar_mqtt_bloqueante():
    client.loop_start()
else:
    # stop_event foi setado, saindo
    raise SystemExit(0)

# Inicia a thread do RFID
t_rfid = threading.Thread(target=rfid_worker, daemon=True)
t_rfid.start()

# --- LOOP PRINCIPAL ---
try:
    while True:
        # RFID agora é consumido via thread
        tratar_pos_reconexao()
        processar_rfid()
        resync_checkout_se_necessario()
        enviar_heartbeat()

        # Sensores continuam iguais
        verifica_parafusadeira(SENSOR_CORRENTE, client)  # BT1
        verifica_pedal(PEDAL, client)                    # BT2
        verifica_sensor_indutivo(SENSOR_PALETE, client)  # BD

        verificar_palete_preso()

        # Controle do batedor com tempo
        if batedor:
            print("Palete livre")
            if time.time() - tempo_batedor <= 2:
                if rele_batedor_ativo_em == 0:
                    GPIO.output(BATEDOR_POSTO, GPIO.LOW)
                else:
                    GPIO.output(BATEDOR_POSTO, GPIO.HIGH)
            else:
                if rele_batedor_ativo_em == 0:
                    GPIO.output(BATEDOR_POSTO, GPIO.HIGH)
                else:
                    GPIO.output(BATEDOR_POSTO, GPIO.LOW)
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
