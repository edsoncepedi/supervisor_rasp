import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

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

from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# Imports locais (assumindo que estão na mesma pasta ou no PATH)
from hailo_postprocess import postprocess_detection_results
from hailo_postprocess import IDManager
from assembly_manager import AssemblyManagar
from assembly_manager import bbox_inside_roi

# ================================
# Configurações Globais (Constantes)
# ================================
POSTO = int(os.getenv("POSTO"))
MODEL_NAME = "digitaldashv3"
ZOO_PATH = "/home/cepedi/supervisor_rasp/script_camera/modelos/digitaldashv3/digitaldashv3.json"
LABELS_FILES = "/home/cepedi/supervisor_rasp/script_camera/modelos/digitaldashv3/labels_coco.json"
CAMERA_ID = 0
SERVER_URL = f"http://{os.getenv('IP_SERVER')}:{os.getenv('PORT_FRONTEND')}/api/atualizar_borda"
SEND_FPS = 20  # Taxa de envio para o servidor

interface_grafica = False  # Define se a interface gráfica (OpenCV) será usada

# ROI: x, y, largura, altura
ROI_X = 0
ROI_Y = 230
ROI_W = 550
ROI_H = 410

ROI = {
    "x1": ROI_X,
    "y1": ROI_Y,
    "x2": ROI_X + ROI_W,
    "y2": ROI_Y + ROI_H
}

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
def process_sender(input_queue, stop_event):
    print("📡 Processo de envio HTTP iniciado...")
    session = requests.Session()
    intervalo = 1.0 / SEND_FPS

    while not stop_event.is_set():
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
def process_yolo(output_queue, stop_event):
    print("⚙️ Inicializando processo YOLO...")

    # --- 1. Inicialização de Objetos (DENTRO DO PROCESSO) ---
    try:
        id_manager = IDManager()
        assembly_manager = AssemblyManagar(posto=2) 
        
        print(f"📂 Carregando modelo: {ZOO_PATH}")
        model = dg.load_model(
            model_name=MODEL_NAME,
            zoo_url=ZOO_PATH,
            inference_host_address="@local",
            token="",
            device_type="HAILORT/HAILO8"
        )
        print("✅ Modelo Hailo carregado com sucesso!")

        # Carrega Labels UMA VEZ só
        with open(LABELS_FILES, "r") as json_file:
            label_dictionary = json.load(json_file)
        print("✅ Labels carregadas.")

    except Exception as e:
        print(f"❌ Erro crítico na inicialização do modelo/classes: {e}")
        return

    # --- 2. Abrir Câmera ---
    print(f"📷 Tentando abrir câmera ID {CAMERA_ID}...")
    cap = cv2.VideoCapture(CAMERA_ID)
    
    # Configurações opcionais para forçar resolução/FPS (melhora estabilidade no Rasp)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():
        print(f"❌ Erro: Não foi possível abrir a câmera {CAMERA_ID}!")
        return
    else:
        print("✅ Câmera aberta!")

    # --- 3. Loop Principal ---
    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Falha ao ler frame da câmera.")
            time.sleep(0.1)
            continue
        
        # Redimensiona para o input do modelo (640x640)
        # Nota: Isso pode distorcer a imagem se a câmera for 4:3 (640x480)
        frame_resized = cv2.resize(frame, (640, 640))
        
        # Converte para RGB (Hailo espera RGB, OpenCV usa BGR)
        frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
        input_tensor = np.expand_dims(frame_rgb, axis=0)

        # Inferência
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
            label_dictionary
        )
        
        detections_roi = filtrar_detections_por_roi(detections, ROI)

        # Lógica de Negócio
        assembly_manager.contar_produtos_posto(detections_roi)
        fixed_objects = id_manager.check_available_ids(detections_roi)
        assembly_manager.gerenciador_etapas(fixed_objects)

        # Desenho e Preparação do Payload
        retangulos = []
        for fid, obj in fixed_objects.items():
            if obj["bbox"] is None:
                continue
            
            x1, y1, x2, y2 = map(int, obj["bbox"])
            color = (0, 255, 0) if obj["active"] else (0, 0, 255)

            retangulos.append({
                "id": f"{fid}",
                "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1,
                "texto": f"{fid}",
                "cor": "#FFFFFF",
                "mostra": True
            })
            if interface_grafica:
                cv2.rectangle(frame_resized, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame_resized, f"{fid}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        if interface_grafica:
            cv2.rectangle(frame_resized, (ROI["x1"], ROI["y1"]), (ROI["x2"], ROI["y2"]), (255, 255, 0), 2)

        # Envia para o processo HTTP
        payload = {
            "acao": "overlay_update",
            "retangulos": retangulos
        }

        if not output_queue.full():
            output_queue.put(payload)
        
        if interface_grafica:
            cv2.imshow("Hailo PySDK - DigitalDash", frame_resized)

            if cv2.waitKey(1) & 0xFF == 27: # ESC
                break

    cap.release()
    if interface_grafica:
        cv2.destroyAllWindows()
    print("🛑 Processo YOLO Encerrado")

def shutdown_handler(sig, frame):
    print("🛑 SIGTERM recebido, encerrando processos...")
    stop_event.set()

if __name__ == "__main__":
    multiprocessing.set_start_method('fork', force=True)

    fila_dados = multiprocessing.Queue(maxsize=3)
    stop_event = multiprocessing.Event()

    p_sender = multiprocessing.Process(
        target=process_sender,
        args=(fila_dados, stop_event)
    )

    p_yolo = multiprocessing.Process(
        target=process_yolo,
        args=(fila_dados, stop_event)
    )

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    print("🚀 Iniciando processos...")
    p_sender.start()
    p_yolo.start()

    p_sender.join()
    p_yolo.join()

    print("✅ Finalizado corretamente")