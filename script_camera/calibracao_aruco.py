"""Calibração projetor <-> câmera por marcadores ArUco.

O projetor (navegador, app/static/scripts/projetor.js) desenha 4 marcadores do
dicionário DICT_4X4_50 (ids 0..3) nos cantos. Este módulo abre a câmera, detecta
os quatro, e resolve a homografia

    H : pixel da câmera (CAM_W x CAM_H)  ->  espaço de referência (REF_W x REF_H)

O espaço de referência é uma constante compartilhada com o projetor.js: é ele
que torna H independente da resolução real do projetor. O navegador só escala
referência -> canvas na hora de desenhar.

⚠️ REF_W, REF_H e MARGIN abaixo TÊM que bater com as constantes de mesmo nome em
   moc_digital_dash/app/static/scripts/projetor.js. Se um lado mudar, o outro
   muda junto, senão a homografia fica silenciosamente errada.

Roda num processo próprio, disparado por main.py ao receber "calibrate" via MQTT.
Precisa da câmera exclusiva, então o pipeline do YOLO é parado antes.
"""

import os
import time

import cv2
import numpy as np
import requests

# ---- Espaço de referência (espelhado em projetor.js) -------------------
REF_W, REF_H = 1280, 720
MARGIN = 140

# Centros dos marcadores, no espaço de referência. Ordem = id do marcador.
TARGETS = np.array([
    (MARGIN, MARGIN),                    # id 0: superior esquerdo
    (REF_W - MARGIN, MARGIN),            # id 1: superior direito
    (REF_W - MARGIN, REF_H - MARGIN),    # id 2: inferior direito
    (MARGIN, REF_H - MARGIN),            # id 3: inferior esquerdo
], dtype=np.float32)

# ---- Parâmetros da detecção -------------------------------------------
TIMEOUT_S = 25.0          # desiste depois disso e devolve o pipeline
FRAMES_PARA_MEDIA = 10    # média dos centros: abate ruído do sensor
INTERVALO_LOG_S = 1.0


def _get_aruco():
    """Compat entre a API nova (>=4.7, ArucoDetector) e a antiga."""
    aruco = cv2.aruco
    dicionario = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)

    try:
        params = aruco.DetectorParameters()
        params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
        detector = aruco.ArucoDetector(dicionario, params)

        def detectar(gray):
            corners, ids, _ = detector.detectMarkers(gray)
            return corners, ids

    except AttributeError:
        params = aruco.DetectorParameters_create()
        params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX

        def detectar(gray):
            corners, ids, _ = aruco.detectMarkers(gray, dicionario, parameters=params)
            return corners, ids

    return detectar


def _centros(corners, ids):
    """Centro de cada marcador = média dos 4 cantos.

    Devolve (achados_por_id, pontos_ordenados) e pontos_ordenados é None
    enquanto os 4 marcadores não estiverem todos visíveis.
    """
    if ids is None:
        return {}, None

    achados = {
        int(i): c.reshape(4, 2).mean(axis=0)
        for c, i in zip(corners, ids.flatten())
    }
    if not all(i in achados for i in range(4)):
        return achados, None

    return achados, np.array([achados[i] for i in range(4)], dtype=np.float32)


def detectar_homografia(picam2):
    """Loop de detecção. Devolve H (3x3) ou None se estourar o timeout."""
    detectar = _get_aruco()
    amostras = []
    inicio = time.time()
    ultimo_log = 0.0

    while time.time() - inicio < TIMEOUT_S:
        frame = picam2.capture_array()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        achados, cam_pts = _centros(*detectar(gray))

        if cam_pts is not None:
            amostras.append(cam_pts)

        agora = time.time()
        if agora - ultimo_log > INTERVALO_LOG_S:
            print(f"🔍 marcadores: {len(achados)}/4 ids={sorted(achados)} "
                  f"amostras={len(amostras)}/{FRAMES_PARA_MEDIA}")
            ultimo_log = agora

        if len(amostras) >= FRAMES_PARA_MEDIA:
            media = np.mean(amostras, axis=0).astype(np.float32)
            return cv2.getPerspectiveTransform(media, TARGETS)

    print(f"❌ Timeout: não achei os 4 marcadores em {TIMEOUT_S:.0f}s. "
          f"O projetor está exibindo a tela de calibração?")
    return None


def _abrir_camera(cam_w, cam_h, fps):
    """Mesma configuração do process_yolo. Se divergir, H fica calibrada para um
    espaço de entrada em que os retângulos do YOLO não vivem."""
    # Import local: a Picamera2 só pode ser instanciada dentro do processo filho,
    # nunca no supervisor que faz fork.
    from picamera2 import Picamera2

    picam2 = Picamera2()
    picam2.configure(picam2.create_video_configuration(
        main={"size": (cam_w, cam_h), "format": "RGB888"},
        controls={"FrameRate": fps},
    ))
    picam2.start()
    time.sleep(0.5)  # deixa o AE/AWB assentar antes do primeiro frame
    return picam2


def process_calibracao(posto, url_homografia, cam_w, cam_h, fps):
    """Entry point do processo filho. Nunca levanta: o pai precisa religar o
    pipeline aconteça o que acontecer."""
    if not os.getenv("INTERFACE_GRAFICA", "").lower() in ("1", "true", "yes", "on"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    print(f"🎯 Calibração ArUco do posto {posto} iniciada")
    picam2 = None

    try:
        picam2 = _abrir_camera(cam_w, cam_h, fps)
        H = detectar_homografia(picam2)

        if H is None:
            return

        payload = {"H": H.tolist(), "ref_w": REF_W, "ref_h": REF_H}
        resposta = requests.post(url_homografia, json=payload, timeout=5)
        resposta.raise_for_status()
        print(f"✅ Homografia enviada para {url_homografia}")
        print(np.array_str(H, precision=4, suppress_small=True))

    except requests.exceptions.RequestException as e:
        print(f"❌ Falha ao enviar homografia: {e}")

    except Exception as e:
        print(f"❌ Erro na calibração: {e}")

    finally:
        if picam2 is not None:
            picam2.stop()
            picam2.close()
        print("🏁 Calibração encerrada")
