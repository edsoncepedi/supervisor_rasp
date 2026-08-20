"""Calibração projetor <-> câmera por marcadores ArUco.

O projetor (navegador, app/static/scripts/projetor.js) desenha 4 marcadores do
dicionário DICT_4X4_50 (ids 0..3) nos cantos. Este módulo abre a câmera, detecta
os quatro, e resolve duas coisas:

    H   : pixel da câmera (CAM_W x CAM_H)  ->  espaço de referência (REF_W x REF_H)
    ROI : bounding box dos 16 cantos dos 4 marcadores, em pixel da câmera

O espaço de referência é uma constante compartilhada com o projetor.js: é ele
que torna H independente da resolução real do projetor. O navegador só escala
referência -> canvas na hora de desenhar.

O ROI vai junto no mesmo POST e o servidor o grava no config do posto, de onde
o process_yolo o relê. Ele existe em pixel da câmera porque é lá que vivem as
bboxes do YOLO, que ele filtra.

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
FRAMES_PARA_MEDIA = 10    # média dos cantos: abate ruído do sensor
INTERVALO_LOG_S = 1.0

JANELA = "Calibracao ArUco"
HOLD_OK_MS = 1500         # tempo que a janela segura o resultado antes de fechar
HOLD_ERRO_MS = 3000


def _interface_grafica():
    # Mesmo default do main.py: com display, mostramos a câmera durante a
    # calibração igual ao process_yolo faz no "start".
    return os.getenv("INTERFACE_GRAFICA", "True").lower() in ("1", "true", "yes", "on")


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


def _ordenar_por_id(corners, ids):
    """Devolve (achados_por_id, cantos) com cantos no formato (4 marcadores, 4 cantos, xy),
    indexado pelo id do marcador. cantos é None enquanto os 4 não estiverem todos visíveis."""
    if ids is None:
        return {}, None

    achados = {
        int(i): c.reshape(4, 2)
        for c, i in zip(corners, ids.flatten())
    }
    if not all(i in achados for i in range(4)):
        return achados, None

    return achados, np.array([achados[i] for i in range(4)], dtype=np.float32)


def _roi_dos_cantos(cantos, cam_w, cam_h):
    """ROI = bounding box alinhada aos eixos dos 16 cantos dos 4 marcadores.

    Recortada ao frame: com o projetor mal enquadrado um canto pode cair fora,
    e um ROI negativo passaria batido até o YOLO filtrar tudo.
    """
    pts = cantos.reshape(-1, 2)
    x1 = max(0, int(np.floor(pts[:, 0].min())))
    y1 = max(0, int(np.floor(pts[:, 1].min())))
    x2 = min(cam_w, int(np.ceil(pts[:, 0].max())))
    y2 = min(cam_h, int(np.ceil(pts[:, 1].max())))

    if x2 <= x1 or y2 <= y1:
        return None

    return {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}


def _desenhar_roi(vis, roi, cor):
    cv2.rectangle(vis, (roi["x"], roi["y"]),
                  (roi["x"] + roi["w"], roi["y"] + roi["h"]), cor, 2)


def _hud(vis, linhas, cor=(0, 255, 255)):
    """Texto com contorno preto: legível sobre a mesa clara e sobre o marcador escuro."""
    for i, txt in enumerate(linhas):
        y = 24 + i * 24
        cv2.putText(vis, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(vis, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor, 1, cv2.LINE_AA)


def _snapshot_falha(posto, vis):
    """Último frame anotado, em disco. É o que sobra para debugar quando o Pi roda
    headless (supervisor) e ninguém viu a janela."""
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           f"calib_falhou_{posto}.jpg")
    try:
        cv2.imwrite(caminho, vis)
        print(f"🖼️ Último frame salvo em {caminho}")
    except Exception as e:
        print(f"⚠️ Não consegui salvar o snapshot de falha: {e}")


def detectar_homografia(picam2, posto, mostrar):
    """Loop de detecção. Devolve (H, roi, motivo_falha), com motivo_falha None no
    sucesso. O motivo sobe até o navegador, que sem ele ficaria esperando às cegas."""
    detectar = _get_aruco()
    amostras = []            # cada item: cantos (4,4,2) de um frame com os 4 marcadores
    inicio = time.time()
    ultimo_log = 0.0
    vis = None
    achados = {}

    while True:
        restante = TIMEOUT_S - (time.time() - inicio)
        if restante <= 0:
            break

        frame = picam2.capture_array()
        cam_h, cam_w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        corners, ids = detectar(gray)
        achados, cantos = _ordenar_por_id(corners, ids)

        if cantos is not None:
            amostras.append(cantos)

        # O frame anotado é montado sempre, mesmo headless: é ele que vira o
        # snapshot de falha.
        vis = frame.copy()
        if ids is not None:
            cv2.aruco.drawDetectedMarkers(vis, corners, ids)

        roi_previa = _roi_dos_cantos(cantos, cam_w, cam_h) if cantos is not None else None
        if roi_previa:
            _desenhar_roi(vis, roi_previa, (0, 255, 255))

        faltando = [i for i in range(4) if i not in achados]
        _hud(vis, [
            f"Posto {posto} | calibracao ArUco | ESC aborta",
            f"marcadores: {len(achados)}/4  faltando: {faltando if faltando else '-'}",
            f"amostras: {len(amostras)}/{FRAMES_PARA_MEDIA}   restam {restante:.0f}s",
        ], cor=(0, 255, 0) if not faltando else (0, 255, 255))

        if mostrar:
            cv2.imshow(JANELA, vis)
            if (cv2.waitKey(1) & 0xFF) == 27:  # ESC
                print("⏹️ Calibração abortada pelo operador (ESC)")
                return None, None, "abortada no Pi (ESC)"

        agora = time.time()
        if agora - ultimo_log > INTERVALO_LOG_S:
            print(f"🔍 marcadores: {len(achados)}/4 ids={sorted(achados)} "
                  f"amostras={len(amostras)}/{FRAMES_PARA_MEDIA}")
            ultimo_log = agora

        if len(amostras) >= FRAMES_PARA_MEDIA:
            media = np.mean(amostras, axis=0).astype(np.float32)   # (4,4,2)
            centros = media.mean(axis=1).astype(np.float32)        # (4,2), um por marcador
            H = cv2.getPerspectiveTransform(centros, TARGETS)
            roi = _roi_dos_cantos(media, cam_w, cam_h)

            if mostrar:
                _desenhar_roi(vis, roi, (0, 255, 0))
                _hud(vis, [
                    "CALIBRADO",
                    f"ROI: x={roi['x']} y={roi['y']} w={roi['w']} h={roi['h']}",
                ], cor=(0, 255, 0))
                cv2.imshow(JANELA, vis)
                cv2.waitKey(HOLD_OK_MS)

            return H, roi, None

    # O motivo diz QUANTOS marcadores apareceram: "0/4" é projetor apagado ou fora
    # do campo de visão; "3/4" é um canto cortado ou reflexo. São problemas diferentes.
    motivo = (f"timeout em {TIMEOUT_S:.0f}s, vi {len(achados)}/4 marcadores "
              f"(ids {sorted(achados) if achados else 'nenhum'})")
    print(f"❌ {motivo}. O projetor está exibindo a tela de calibração?")

    if vis is not None:
        _hud(vis, ["TIMEOUT: nao achei os 4 marcadores"], cor=(0, 0, 255))
        _snapshot_falha(posto, vis)
        if mostrar:
            cv2.imshow(JANELA, vis)
            cv2.waitKey(HOLD_ERRO_MS)

    return None, None, motivo


TENTATIVAS_CAMERA = 4
ESPERA_CAMERA_S = 1.5


def _abrir_camera(cam_w, cam_h, fps):
    """Mesma configuração do process_yolo. Se divergir, H fica calibrada para um
    espaço de entrada em que os retângulos do YOLO não vivem.

    Tenta algumas vezes: o process_yolo acabou de ser parado e, se ele levou um
    terminate() no meio de uma inferência, não chegou a fechar a câmera. Ela leva
    um instante para ser liberada e a primeira tentativa aqui pega "device busy".
    """
    # Import local: a Picamera2 só pode ser instanciada dentro do processo filho,
    # nunca no supervisor que faz fork.
    from picamera2 import Picamera2

    for tentativa in range(1, TENTATIVAS_CAMERA + 1):
        try:
            picam2 = Picamera2()
            picam2.configure(picam2.create_video_configuration(
                main={"size": (cam_w, cam_h), "format": "RGB888"},
                controls={"FrameRate": fps},
            ))
            picam2.start()
            time.sleep(0.5)  # deixa o AE/AWB assentar antes do primeiro frame
            return picam2

        except Exception as e:
            print(f"⏳ Câmera ocupada ({tentativa}/{TENTATIVAS_CAMERA}): {e}")
            if tentativa == TENTATIVAS_CAMERA:
                raise
            time.sleep(ESPERA_CAMERA_S)


def _avisar_falha(url_falha, motivo):
    """O navegador está esperando: ou avisamos, ou ele fica preso na tela de
    marcadores até a própria janela dele expirar."""
    try:
        requests.post(url_falha, json={"motivo": motivo[:200]}, timeout=5)
        print(f"📨 Falha reportada ao servidor: {motivo}")
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Não consegui reportar a falha: {e}")


def process_calibracao(posto, url_base, cam_w, cam_h, fps):
    """Entry point do processo filho. Nunca levanta: o pai precisa religar o
    pipeline aconteça o que acontecer.

    url_base é .../api/calibracao/{posto}; daqui saem o POST do resultado e o da falha.
    """
    mostrar = _interface_grafica()
    if not mostrar:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    url_homografia = f"{url_base}/homografia"
    url_falha = f"{url_base}/falha"

    print(f"🎯 Calibração ArUco do posto {posto} iniciada")
    picam2 = None

    try:
        picam2 = _abrir_camera(cam_w, cam_h, fps)
        H, roi, motivo = detectar_homografia(picam2, posto, mostrar)

        if H is None:
            _avisar_falha(url_falha, motivo or "falha desconhecida")
            return

        payload = {"H": H.tolist(), "ref_w": REF_W, "ref_h": REF_H, "roi": roi}
        resposta = requests.post(url_homografia, json=payload, timeout=5)
        resposta.raise_for_status()
        print(f"✅ Homografia enviada para {url_homografia}")
        print(np.array_str(H, precision=4, suppress_small=True))
        print(f"✅ ROI estimado pelos marcadores: {roi}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Falha ao enviar homografia: {e}")
        _avisar_falha(url_falha, f"erro de rede ao enviar a homografia: {e}")

    except Exception as e:
        print(f"❌ Erro na calibração: {e}")
        _avisar_falha(url_falha, f"erro no Pi: {e}")

    finally:
        if picam2 is not None:
            picam2.stop()
            picam2.close()
        if mostrar:
            cv2.destroyAllWindows()
        print("🏁 Calibração encerrada")
