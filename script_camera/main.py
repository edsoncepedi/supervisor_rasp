import cv2
import numpy as np
import degirum as dg
import os
import json
from pprint import pprint
from hailo_postprocess import postprocess_detection_results
import numpy as np
import json
from sort import Sort

tracker = Sort(
    max_age=200,
    min_hits=3,
    iou_threshold=0.3
)




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
        pprint(result.results)

    except dg.exceptions.DegirumException as e:
        print("❌ Erro na inferência:", e)
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
    print(detections)
    sort_input = []
    sort_input_with_label = []
    for det in detections:
        x1, y1, x2, y2 = map(int, det["bbox"])
        label = det["label"]
        score = det["score"]

        sort_input.append([x1, y1, x2, y2, score])
        sort_input_with_label.append([x1, y1, x2, y2, score, label])
        # Desenhar retângulo e label
        #cv2.rectangle(frame_resized, (x1, y1), (x2, y2), (0, 255, 0), 2)
        #cv2.putText(frame_resized, f"{label} {score:.2f}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0),  2 )
    
    sort_input = np.array(sort_input) if len(sort_input) > 0 else np.empty((0, 5))

    tracks = tracker.update(sort_input)
    for track in tracks:
        x1, y1, x2, y2, track_id = map(int, track)
        cv2.rectangle(frame_resized, (x1, y1), (x2, y2), (255, 0, 0), 2)
        cv2.putText(
            frame_resized,
            f"ID {track_id}",
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 0, 0),
            2
        )
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
print("🛑 Encerrado")
