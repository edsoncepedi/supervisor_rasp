import cv2
import numpy as np
import degirum as dg
import os
import json
import time
from picamera2 import Picamera2
from collections import Counter
from assembly_manager import AssemblyManagar
from hailo_postprocess import postprocess_detection_results, IDManager
from assembly_manager import bbox_inside_roi


# =========================================================
# CONFIGURAÇÕES GERAIS
# =========================================================

POSTO = int(2)

INTERFACE_GRAFICA = True

TARGET_FPS = 15
FRAME_TIME = 1.0 / TARGET_FPS

MODEL_NAME = "digitaldashv3"
ZOO_PATH = "/home/cepedi/supervisor_rasp/script_camera/modelos/digitaldashv3/digitaldashv3.json"
LABELS_FILES = "/home/cepedi/supervisor_rasp/script_camera/modelos/digitaldashv3/labels_coco.json"

MODEL_W = 640
MODEL_H = 640

# ROI (x, y, largura, altura)
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



# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def filtrar_detections_por_roi(detections, roi):
    return [d for d in detections if bbox_inside_roi(d["bbox"], roi)]


# =========================================================
# MAIN
# =========================================================

def main():

    ultima_etapa = None
    etapa_atual = None

    frame_id = 0
    last_fixed_objects = None

    if not INTERFACE_GRAFICA:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    print("📦 Carregando modelo Hailo...")
    model = dg.load_model(
        model_name=MODEL_NAME,
        zoo_url=ZOO_PATH,
        inference_host_address="@local",
        token="",
        device_type="HAILORT/HAILO8"
    )
    print("✅ Modelo carregado!")

    with open(LABELS_FILES, "r") as f:
        label_dictionary = json.load(f)

    print("📷 Iniciando Raspberry Pi AI Camera...")
    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"size": (MODEL_W, MODEL_H), "format": "RGB888"},
        controls={"FrameRate": TARGET_FPS}
    )
    picam2.configure(config)
    picam2.start()

    id_manager = IDManager()
    assembly_manager = AssemblyManagar(posto=POSTO)
    frame_count = 0
    t0 = time.perf_counter()

    try:
        while True:

            
            loop_start = time.perf_counter()

            # -------------------------------------------------
            # Captura frame (já em RGB)
            # -------------------------------------------------
            frame = picam2.capture_array()
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # -------------------------------------------------
            # Blur SOMENTE na ROI
            # -------------------------------------------------

            frame_blur = cv2.GaussianBlur(frame_rgb, (3, 3), 0)


            # -------------------------------------------------
            # Inferência
            # -------------------------------------------------
            input_tensor = np.expand_dims(frame_blur, axis=0)

            frame_id += 1
            do_predict_only  = (frame_id % 6 == 0)

            if not do_predict_only :
                result = model(input_tensor)

                detections = postprocess_detection_results(
                    result.results[0]["data"],
                    model.input_shape[0],
                    6,
                    label_dictionary,
                    confidence_threshold=0.3
                )

                detections_roi = filtrar_detections_por_roi(detections, ROI)
                c = Counter(d["label"] for d in detections_roi)
                top = sorted(detections_roi, key=lambda d: d["score"], reverse=True)[:8]
                #print("ROI det count:", len(detections_roi), c)
                #print("Top:", [(d["label"], round(d["score"], 3)) for d in top])
                fixed_objects = id_manager.check_available_ids(detections_roi)

                last_fixed_objects = fixed_objects

            else:
                fixed_objects = id_manager.predict_only()

            if fixed_objects is None:
                continue


            etapa_atual = assembly_manager.update(fixed_objects)
            if etapa_atual != ultima_etapa:
                print(f"➡️ Avançou para etapa {etapa_atual}")
                ultima_etapa = etapa_atual


            # -------------------------------------------------
            # Interface gráfica (opcional)
            # -------------------------------------------------
            if INTERFACE_GRAFICA:
                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                for fid, obj in fixed_objects.items():
                    if obj["bbox"] is None:
                        continue
                    x1, y1, x2, y2 = map(int, obj["bbox"])
                    color = (0, 255, 0) if obj["active"] else (0, 0, 255)
                    cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame_bgr, fid, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                cv2.rectangle(frame_bgr, (ROI["x1"], ROI["y1"]), (ROI["x2"], ROI["y2"]), (255,0,0), 2)
                cv2.imshow("Hailo - DigitalDash", frame_bgr)
                if cv2.waitKey(1) & 0xFF == 27:
                    break

            # -------------------------------------------------
            # Controle de FPS
            # -------------------------------------------------
            elapsed = time.perf_counter() - loop_start
            sleep_time = FRAME_TIME - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

            # -------------------------------------------------
            # Log de FPS real
            # -------------------------------------------------
            frame_count += 1
            if frame_count % 60 == 0:
                fps_real = frame_count / (time.perf_counter() - t0)
                #print(f"📊 FPS real: {fps_real:.2f}")

    finally:
        print("🛑 Encerrando...")
        picam2.stop()
        picam2.close()
        if INTERFACE_GRAFICA:
            cv2.destroyAllWindows()


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()
