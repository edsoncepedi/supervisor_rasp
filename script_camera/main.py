import cv2
import numpy as np
import degirum as dg
import os
import json
from pprint import pprint
from hailo_postprocess import postprocess_detection_results
from hailo_postprocess import IDManager
import numpy as np
import json

id_manager = IDManager()


# ================================
# Configurações
# ================================
MODEL_NAME = "digitaldashv1"
ZOO_PATH = "/home/cepedi/hailo_examples/models/digitaldashv1/digitaldashv1.json"
LABELS_FILES = "/home/cepedi/hailo_examples/models/digitaldashv1/labels_coco.json"
CAMERA_ID = 0

# ================================
# Carregar modelo PySDK
# ================================
model = dg.load_model(
    model_name=MODEL_NAME,
    zoo_url=ZOO_PATH,
    inference_host_address="@local",
    token="",
    device_type="HAILORT/HAILO8"
)

print("✅ Modelo carregado!")

# ================================
# Abrir câmera
# ================================
cap = cv2.VideoCapture(CAMERA_ID)
if not cap.isOpened():
    raise RuntimeError("Erro ao abrir a câmera!")

# ================================
# Loop principal
# ================================
while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Redimensiona para o tamanho esperado pelo modelo
    frame_resized = cv2.resize(frame, (640, 640))
    frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)

    # Adiciona batch dimension (1, H, W, C)
    input_tensor = np.expand_dims(frame_rgb, axis=0)

    # Rodar inferência
    try:
        result = model(input_tensor)
        print(result.results[0]["data"])
        #pprint(result.results)

    except dg.exceptions.DegirumException as e:
        print(" Erro na inferência:", e)
        break
    
    # ================================
    # Processar resultados
    # ================================
    # O PySDK usa o postprocessor definido no JSON.
    # Cada detecção tem "bbox", "score", "label"

    with open(LABELS_FILES, "r") as json_file:
        label_dictionary = json.load(json_file)

    detections = postprocess_detection_results(result.results[0]["data"],model.input_shape[0],6, label_dictionary )
    #pprint(detections)
    fixed_objects = id_manager.check_available_ids(detections)

    for fid, obj in fixed_objects.items():
        if obj["bbox"] is None:
            continue
        x1, y1, x2, y2 = map(int, obj["bbox"])
        color = (0, 255, 0) if obj["active"] else (0, 0, 255)
        cv2.rectangle(frame_resized, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame_resized, f"{fid}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    print("SORT -> id fixo:", id_manager.sort_to_fixed)

    # Mostrar resultado
    cv2.imshow("Hailo PySDK - DigitalDash", frame_resized)

    # Sair com ESC
    if cv2.waitKey(1) & 0xFF == 27:
        break

# ================================
# Limpeza
# ================================
cap.release()
cv2.destroyAllWindows()
print("Encerrado")
