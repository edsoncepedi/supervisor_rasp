import os

def getenv_bool(nome, default=False):
    return os.getenv(nome, str(default)).lower() in ("1", "true", "yes", "on")

interface_grafica = getenv_bool("INTERFACE_GRAFICA", True)

import signal
import cv2
import numpy as np
import degirum as dg
import json
import multiprocessing
import requests 
import math
import time
from pprint import pprint
from picamera2 import Picamera2
from dotenv import load_dotenv
from queue import Empty, Full
import aiomqtt
import asyncio
import socket

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# Imports locais (assumindo que estão na mesma pasta ou no PATH)
from hailo_postprocess import postprocess_detection_results
from hailo_postprocess import IDManager
from assembly_manager import AssemblyManagar
from assembly_manager import bbox_inside_roi
from calibracao_aruco import process_calibracao

BROKER = os.getenv('IP_SERVER')
PORT = int(os.getenv('PORT_MQTT'))
POSTO = int(os.getenv("POSTO"))

CMD_TOPIC = f"sistema/camera/posto_{POSTO}"

# ===== estado atual do pipeline =====
_current = {
    "queue": None,
    "stop_event": None,
    "p_yolo": None,
    "p_sender": None,
}

# ================================
# Configurações Globais (Constantes)
# ================================
MODEL_NAME = "digitaldashv6"
ZOO_PATH = "/home/cepedi/supervisor_rasp/script_camera/modelos/digitaldashv6/digitaldashv6.json"
LABELS_FILES = "/home/cepedi/supervisor_rasp/script_camera/modelos/digitaldashv6/labels_coco.json"
CAMERA_ID = 0
SERVER_URL = f"http://{os.getenv('IP_SERVER')}:{os.getenv('PORT_FRONTEND')}/camera/{POSTO}"
# Base: a calibração pendura /homografia (sucesso) e /falha (desistiu) em cima.
CALIB_URL = f"http://{os.getenv('IP_SERVER')}:{os.getenv('PORT_FRONTEND')}/api/calibracao/{POSTO}"
SEND_FPS = 20  # Taxa de envio para o servidor

# FPS Camera
PROCESS_FPS =15

FRAME_TIME = 1.0 / PROCESS_FPS

VIDEO_W_SENSOR = 640 
VIDEO_H_SENSOR = 640 

MODEL_W = 640
MODEL_H = 640

# ROI: x, y, largura, altura, em pixel da câmera (é onde vivem as bboxes do YOLO,
# que ele filtra). Fonte de verdade: o config do posto no servidor. A calibração
# ArUco recalcula o ROI a partir dos marcadores e grava lá, então aqui basta reler.
CONFIG_URL = f"http://{os.getenv('IP_SERVER')}:{os.getenv('PORT_FRONTEND')}/api/config/{POSTO}"

ROI = {"x1": 35, "y1": 211, "x2": 35 + 535, "y2": 211 + 300}
CONFIDENCE_THRESHOLD = 0.3


def carregar_config(bloqueante=True):
    """Puxa ROI e threshold do servidor para as globais que o process_yolo lê.

    O fork copia as globais do pai, então chamar isto ANTES do start_pipeline é o
    que faz o pipeline novo enxergar o ROI recém-calibrado.

    Com bloqueante=False tenta uma vez só e mantém a config atual se falhar: depois
    da calibração não dá para travar o religamento do pipeline por causa da rede.
    """
    global ROI, CONFIDENCE_THRESHOLD

    while True:
        try:
            response = requests.get(CONFIG_URL, timeout=5)
            response.raise_for_status()
            data = response.json()

            roi_x = data.get("ROI_X", 35)
            roi_y = data.get("ROI_Y", 211)
            roi_w = data.get("ROI_W", 535)
            roi_h = data.get("ROI_H", 300)

            ROI = {
                "x1": roi_x,
                "y1": roi_y,
                "x2": roi_x + roi_w,
                "y2": roi_y + roi_h,
            }
            CONFIDENCE_THRESHOLD = data.get("CONFIDENCE_THRESHOLD", 0.3)

            print(f"✅ Config do posto {POSTO}: ROI={ROI} "
                  f"CONFIDENCE_THRESHOLD={CONFIDENCE_THRESHOLD}")
            return True

        except requests.exceptions.RequestException as e:
            print("Erro ao buscar config no servidor:", e)
            if not bloqueante:
                print(f"↩️ Mantendo config atual: ROI={ROI}")
                return False
            print("Tentando novamente em 3 segundos...")
            time.sleep(3)


carregar_config()

def clean_data(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj): return 0
        return float(obj)
    elif isinstance(obj, int):
        return int(obj)
    return obj

def filtrar_detections_por_roi(detections, roi):
    return [
        d for d in detections
        if bbox_inside_roi(d["bbox"], roi)
    ]

# ==========================================
# PROCESSO 1: ENVIO VIA HTTP
# ==========================================
def process_sender(input_queue, stop_event, start_event):
    print("📡 Processo de envio HTTP iniciado...")
    session = requests.Session()
    intervalo = 1.0 / SEND_FPS

    while not stop_event.is_set():

        if not start_event.is_set():
            time.sleep(0.05)
            continue
        loop_start = time.time()
        payload = None
        try:
            # Esvazia a fila para pegar apenas o mais recente
            while not input_queue.empty():
                payload = input_queue.get_nowait()
        except:
            pass

        if payload:
            try:
                session.post(SERVER_URL, json=payload, timeout=0.2)
            except requests.exceptions.RequestException:
                pass 

        elapsed = time.time() - loop_start
        wait = intervalo - elapsed
        if wait > 0:
            time.sleep(wait)

# ==========================================
# PROCESSO 2: YOLO / HAILO (Processamento de Imagem)
# ==========================================
def process_yolo(output_queue, stop_event, start_event):

    print("⚙️ Inicializando processo YOLO...")
    
    # --- 1. Inicialização de Objetos (DENTRO DO PROCESSO) ---
    try:
        id_manager = IDManager()
        assembly_manager = AssemblyManagar(posto=POSTO) 

        if not interface_grafica:
            os.environ["QT_QPA_PLATFORM"] = "offscreen"

        print(f"📂 Carregando modelo: {ZOO_PATH}")
        model = dg.load_model(
            model_name=MODEL_NAME,
            zoo_url=ZOO_PATH,
            inference_host_address="@local",
            token="",
            device_type="HAILORT/HAILO8"
        )
        print("✅ Modelo Hailo carregado com sucesso!")

        # Carrega labels
        with open(LABELS_FILES, "r") as json_file:
            label_dictionary = json.load(json_file)

    except Exception as e:
        print(f"❌ Erro crítico na inicialização do modelo/classes: {e}")
        return
    
    # ================================
    # Configurar Câmera (Picamera2)
    # ================================
    print("📷 Iniciando Raspberry Pi AI Camera...")
    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"size": (VIDEO_W_SENSOR, VIDEO_H_SENSOR), "format": "RGB888"},
        controls={"FrameRate": PROCESS_FPS}
    )
    picam2.configure(config)
    picam2.start()

    print("✅ Câmera iniciada!")

    # Controle fps e frame
    frame_count = 0
    frame_id = 0

    t0 = time.perf_counter()

    # --- 3. Loop Principal ---
    while not stop_event.is_set():


        if not start_event.is_set():
            time.sleep(0.05)
            continue

        loop_start = time.perf_counter() # Controle FPS
        # Captura o frame direto como array numpy (já em 640x640)
        frame = picam2.capture_array()
        #roi_frame = frame[ROI["y1"]:ROI["y2"], ROI["x1"]:ROI["x2"]]
        #roi_resized = cv2.resize(roi_frame, (MODEL_W, MODEL_H))

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_blur = cv2.GaussianBlur(frame_rgb, (3, 3), 0)     
        input_tensor = np.expand_dims(frame_blur, axis=0)

        # Inferência

        frame_id += 1
        do_predict_only  = (frame_id % 3 == 0)

        all_tracks = []

        if not do_predict_only :
            
            try:
                result = model(input_tensor)
            except dg.exceptions.DegirumException as e:
                print("❌ Erro na inferência Hailo:", e)
                continue # Tenta próximo frame em vez de crashar
            
            # Pós-processamento
            detections = postprocess_detection_results(
                result.results[0]["data"], 
                model.input_shape[0], 
                6, 
                label_dictionary,
                confidence_threshold=CONFIDENCE_THRESHOLD

            )

            detections_roi = filtrar_detections_por_roi(detections, ROI)
            all_tracks = id_manager.assign_tracks_all_classes(detections_roi)
            fixed_objects = id_manager.check_available_ids_from_tracks(all_tracks)


        else:
            fixed_objects = id_manager.predict_only()

        if fixed_objects is None:
            continue

        # Desenho e Preparação do Payload
        retangulos = []
        for fid, obj in fixed_objects.items():
            if obj["bbox"] is None:
                continue
            
            x1, y1, x2, y2 = map(int, obj["bbox"])

            if (f"{fid}" == "cpu1" or f"{fid}" == "fan1"):
                pad_w = 20
                pad_h = 20

                x1 = max(0, x1 - pad_w)
                y1 = max(0, y1 - pad_h)
                x2 = x2 + pad_w
                y2 = y2 + pad_h

            elif (f"{fid}" == "pallet1"):
                continue
            
            color = (0, 255, 0) if obj["active"] else (0, 0, 255)

            retangulos.append({
                "id": f"{fid}",
                "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1,
                "texto": f"{fid}",
                #"texto": f"",
                "cor": "#FFFB00",
                "mostra": True
            })
            if interface_grafica:
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{fid}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        if interface_grafica:
            cv2.rectangle(frame, (ROI["x1"], ROI["y1"]), (ROI["x2"], ROI["y2"]), (255, 255, 0), 2)

        # Lógica de posto 1 e 2 unidas
        
        #assembly_manager.contar_produtos_posto(detections_roi)
        etapa_atual = assembly_manager.update(fixed_objects)
        print( etapa_atual)
        # Envia para o processo HTTP
        payload = {
            "acao": "overlay_update",
            "retangulos": retangulos,
            "etapa": etapa_atual
        }

        #if not output_queue.full():
        #    output_queue.put(payload)
        
        try:
            output_queue.put(payload, timeout=0.01)
        except Full:
            # se encheu, descarta (ou você pode fazer "substituir o último")
            pass

        # Controle FPS
        elapsed = time.perf_counter() - loop_start
        sleep_time = FRAME_TIME - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


        if interface_grafica:
            cv2.imshow("Hailo PySDK - DigitalDash", frame)

            if cv2.waitKey(1) & 0xFF == 27: # ESC
                break


    print("🛑 Processo YOLO Encerrado")
    picam2.stop()
    picam2.close()
    if interface_grafica:
        cv2.destroyAllWindows()
    



"""
def shutdown_handler(sig, frame):
    print("🛑 SIGTERM recebido, encerrando processos...")
    stop_event.set()
"""

def pipeline_running():
    p_yolo = _current.get("p_yolo")
    p_sender = _current.get("p_sender")
    return (p_yolo and p_yolo.is_alive()) and (p_sender and p_sender.is_alive())


def start_pipeline():
    # Se já existe pipeline vivo, não inicia outro
    p_yolo = _current.get("p_yolo")
    p_sender = _current.get("p_sender")
    if (p_yolo and p_yolo.is_alive()) or (p_sender and p_sender.is_alive()):
        print("⚠️ Pipeline já está rodando. Ignorando start.")
        return

    print("🚀 Iniciando pipeline (instância NOVA)")

    fila = multiprocessing.Queue(maxsize=3)
    stop_event = multiprocessing.Event()
    start_event = multiprocessing.Event()
    start_event.set()

    p_sender = multiprocessing.Process(
        target=process_sender,
        args=(fila, stop_event, start_event),
        name="sender"
    )
    p_yolo = multiprocessing.Process(
        target=process_yolo,
        args=(fila, stop_event, start_event),
        name="yolo"
    )

    p_sender.start()
    p_yolo.start()

    _current.update({
        "queue": fila,
        "stop_event": stop_event,
        "p_sender": p_sender,
        "p_yolo": p_yolo
    })

def stop_pipeline(force=True):
    print("🛑 Parando pipeline")

    stop_event = _current.get("stop_event")
    p_sender = _current.get("p_sender")
    p_yolo = _current.get("p_yolo")

    if stop_event:
        stop_event.set()

    for p in (p_sender, p_yolo):
        if p and p.is_alive():
            p.join(timeout=2.0)

    if force:
        for p in (p_sender, p_yolo):
            if p and p.is_alive():
                print(f"⚠️ Forçando terminate em {p.name}")
                p.terminate()
                p.join(timeout=1.0)

    _current.update({
        "queue": None,
        "stop_event": None,
        "p_sender": None,
        "p_yolo": None
    })

    print("✅ Pipeline parado")

def restart_pipeline():
    stop_pipeline(force=True)
    start_pipeline()


# Camera aberta pelo process_yolo e exclusiva: a calibracao so roda com o
# pipeline parado, e num processo proprio (nunca no supervisor, que faz fork).
CALIB_TIMEOUT_S = 40


async def run_calibracao():
    print("🎯 Pausando pipeline para calibrar")
    estava_rodando = pipeline_running()
    stop_pipeline(force=True)

    p = multiprocessing.Process(
        target=process_calibracao,
        args=(POSTO, CALIB_URL, VIDEO_W_SENSOR, VIDEO_H_SENSOR, PROCESS_FPS),
        name="calib"
    )
    p.start()

    try:
        await asyncio.to_thread(p.join, CALIB_TIMEOUT_S)
        if p.is_alive():
            print("⚠️ Calibração travou. Forçando terminate.")
            p.terminate()
            await asyncio.to_thread(p.join, 2.0)
    finally:
        # A calibração gravou o ROI novo no servidor; relemos antes do fork para
        # que o pipeline volte já com ele. Se a calibração falhou, o servidor
        # devolve o ROI antigo e nada muda.
        #
        # Blindado de propósito: qualquer erro aqui NÃO pode impedir o religamento.
        # Voltar sem o ROI novo é ruim; voltar sem pipeline nenhum é o posto parado.
        try:
            await asyncio.to_thread(carregar_config, False)
        except Exception as e:
            print(f"⚠️ Erro ao reler a config, seguindo com a atual: {e}")

        if estava_rodando:
            start_pipeline()


async def mqtt_supervisor():
    backoff = 2  # começa tentando a cada 2s
    max_backoff = 30

    while True:
        try:
            print(f"🌐 Tentando conectar MQTT (aiomqtt) em {BROKER}:{PORT} ...")
            async with aiomqtt.Client(BROKER, PORT) as client:
                backoff = 2  # reset backoff quando conecta

                await client.subscribe(CMD_TOPIC)
                print(f"📡 MQTT conectado e escutando: {CMD_TOPIC}")

                async for message in client.messages:
                    try:
                        cmd = message.payload.decode().strip().lower()
                    except Exception:
                        continue

                    if cmd == "start":
                        if not pipeline_running():
                            start_pipeline()

                    elif cmd == "stop":
                        stop_pipeline(force=True)

                    elif cmd == "restart":
                        restart_pipeline()

                    elif cmd == "calibrate":
                        await run_calibracao()
                    else:
                        pass

        except (OSError, socket.error, aiomqtt.MqttError) as e:
            # rede não subiu / broker fora / conexão caiu
            print(f"⏳ MQTT indisponível: {e}. Tentando novamente em {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(max_backoff, backoff * 2)

        except Exception as e:
            # qualquer outra exceção inesperada: não deixa morrer
            print(f"❌ Erro inesperado no mqtt_supervisor: {e}. Reiniciando em 5s...")
            await asyncio.sleep(5)


def main():
    multiprocessing.set_start_method("fork", force=True)

    def handle_signal(sig, frame):
        print(f"\n🛑 Sinal {sig} recebido")
        stop_pipeline(force=True)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    asyncio.run(mqtt_supervisor())


if __name__ == "__main__":
    main()
