import cv2
import numpy as np
import degirum as dg
import os
import json
import time
from pprint import pprint

# Import da biblioteca nativa da câmera Raspberry Pi
from picamera2 import Picamera2

# Imports do seu projeto
from hailo_postprocess import postprocess_detection_results
from hailo_postprocess import IDManager
from assembly_manager import AssemblyManagar
from assembly_manager import bbox_inside_roi

id_manager = IDManager()
assembly_manager = AssemblyManagar(posto=2) 

# ================================
# Configurações
# ================================
MODEL_NAME = "digitaldashv3"
ZOO_PATH = "/home/cepedi/supervisor_rasp/script_camera/modelos/digitaldashv3/digitaldashv3.json"
LABELS_FILES = "/home/cepedi/supervisor_rasp/script_camera/modelos/digitaldashv3/labels_coco.json"

# Dimensões do Modelo (Para configurar a câmera direto)
MODEL_W = 640
MODEL_H = 640

# ================================
# Carregar modelo PySDK (Hailo)
# ================================
# Nota: Você está usando o acelerador Hailo. A AI Camera tem seu próprio acelerador,
# mas aqui estamos usando-a apenas como fonte de vídeo de alta qualidade.
model = dg.load_model(
    model_name=MODEL_NAME,
    zoo_url=ZOO_PATH,
    inference_host_address="@local",
    token="",
    device_type="HAILORT/HAILO8"
)

# ROI: x, y, largura, altura
ROI_X = 0
ROI_Y = 230
ROI_W = 550
ROI_H = 300

ROI = {
    "x1": ROI_X,
    "y1": ROI_Y,
    "x2": ROI_X + ROI_W,
    "y2": ROI_Y + ROI_H
}

def filtrar_detections_por_roi(detections, roi):
    return [
        d for d in detections
        if bbox_inside_roi(d["bbox"], roi)
    ]
    

# Carregar labels uma única vez antes do loop para otimizar
with open(LABELS_FILES, "r") as json_file:
    label_dictionary = json.load(json_file)

print("✅ Modelo carregado!")

# ================================
# Configurar Câmera (Picamera2)
# ================================
print("📷 Iniciando Raspberry Pi AI Camera...")
picam2 = Picamera2()

# Configura a câmera para já entregar 640x640 em formato BGR (compatível com OpenCV)
config = picam2.create_video_configuration(
    main={"size": (MODEL_W, MODEL_H), "format": "RGB888"}
)

picam2.configure(config)
picam2.start()

print("✅ Câmera iniciada!")

# ================================
# Loop principal
# ================================
try:
    while True:
        # Captura o frame direto como array numpy (já em 640x640)
        # O método capture_array é bloqueante, aguarda o próximo frame
        frame_resized = picam2.capture_array()

        # O redimensionamento manual (cv2.resize) foi removido pois 
        # a câmera já está entregando no tamanho certo.
        #frame_resized = cv2.resize(frame, (640, 640))
        # Converte BGR (OpenCV) para RGB (Modelo)
        #frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # Adiciona batch dimension (1, H, W, C)
        frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
        frame_resized = cv2.GaussianBlur(frame_rgb, (3, 3), 0)

        input_tensor = np.expand_dims(frame_resized, axis=0)
        

        # Rodar inferência
        try:
            result = model(input_tensor)
        except dg.exceptions.DegirumException as e:
            print("❌ Erro na inferência:", e)
            break
        
        # ================================
        # Processar resultados
        # ================================
        detections = postprocess_detection_results(
            result.results[0]["data"],
            model.input_shape[0],
            6, 
            label_dictionary,
            confidence_threshold=0.3
        )
        
        detections_roi = filtrar_detections_por_roi(detections, ROI)

        assembly_manager.contar_produtos_posto(detections_roi)
        
        fixed_objects = id_manager.check_available_ids(detections_roi)
        assembly_manager.gerenciador_etapas(fixed_objects)
        
        #print(f"Objetos: {len(fixed_objects)}")

        # Desenhar na tela (usando frame_resized que já é BGR e 640x640)
        for fid, obj in fixed_objects.items():
            if obj["bbox"] is None:
                continue
            x1, y1, x2, y2 = map(int, obj["bbox"])
            color = (0, 255, 0) if obj["active"] else (0, 0, 255)
            
            cv2.rectangle(frame_resized, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame_resized, f"{fid}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # Desenhar ROI
        cv2.rectangle(frame_resized, (ROI["x1"], ROI["y1"]), (ROI["x2"], ROI["y2"]), (255, 255, 0), 2)

        # Mostrar resultado
        frame_corrigido = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB) 
        cv2.imshow("Hailo PySDK - DigitalDash", frame_resized)

        # Sair com ESC
        if cv2.waitKey(1) & 0xFF == 27:
            break

except Exception as e:
    print(f"Erro no loop principal: {e}")

finally:
    # ================================
    # Limpeza
    # ================================
    picam2.stop()
    picam2.close() # Libera a câmera corretamente
    cv2.destroyAllWindows()
    print("Encerrado")