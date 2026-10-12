"""Webcam -> posicao 3D metrica da cabeca.

M1: localizar as duas irises e medir a distancia interpupilar em pixels.

Nota sobre a API do MediaPipe: no Python 3.14 nenhuma wheel traz a API legada
`mp.solutions.face_mesh`, entao usamos `mediapipe.tasks.vision.FaceLandmarker`.
E o mesmo modelo attention-mesh por baixo, com os mesmos 478 landmarks e os
mesmos indices de iris; a refinacao de iris vem embutida no .task, nao e mais
uma flag `refine_landmarks=True`.
"""

import json
import os
import time

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

import config

# Indices no mesh de 478 pontos. 468 = centro da iris esquerda, 473 = centro da
# iris direita ("esquerda"/"direita" do ponto de vista da pessoa). Como so usamos
# a norma e o ponto medio entre as duas, a troca de rotulo nao afeta nada.
IRIS_L = 468
IRIS_R = 473

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "face_landmarker.task")


def open_camera():
    """Abre a webcam ja com a exposicao automatica ligada e estabilizada.

    Duas armadilhas encontradas nesta maquina, ambas medidas:

    1. Backend. Com CAP_DSHOW a captura fica em 15 fps. Com CAP_MSMF sobe para
       ~20 fps. 30 fps seria melhor: a latencia do tracking, e nao o jitter, e o
       defeito perceptual dominante em head-coupled perspective.

    2. Exposicao. Sem forcar CAP_PROP_AUTO_EXPOSURE a camera abre com exposicao
       curta travada e devolve frame quase preto (brilho medio 3 de 255, zero
       deteccoes) rodando a 29 fps. Ligando a auto-exposicao o brilho vai para
       ~114 e a deteccao para 100%, ao custo de cair para 20 fps, porque em luz
       fraca o sensor alonga o tempo de integracao. Mais luz no ambiente encurta
       a exposicao e o fps sobe sozinho na direcao de 30.
    """
    cap = cv2.VideoCapture(config.CAM_INDEX, cv2.CAP_MSMF)
    if not cap.isOpened():
        raise RuntimeError(f"Nao consegui abrir a webcam (CAM_INDEX={config.CAM_INDEX})")
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_REQ_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_REQ_H)
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)

    # Descarta frames ate a auto-exposicao convergir, senao os primeiros vem pretos.
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < config.CAM_WARMUP_S:
        cap.read()
    return cap


def make_landmarker():
    """Cria o FaceLandmarker em modo VIDEO.

    O modo VIDEO mantem tracking entre frames (equivalente ao antigo
    static_image_mode=False), o que reduz jitter e custo por frame.
    """
    if not os.path.exists(MODEL_PATH):
        raise RuntimeError(f"Modelo nao encontrado em {MODEL_PATH}")
    options = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
    )
    return vision.FaceLandmarker.create_from_options(options)


def read_frame(cap):
    """Le um frame ja espelhado, se FLIP_FRAME estiver ligado.

    Por que espelhar: numa imagem de camera crua, mover a cabeca para a SUA
    direita faz `u` DIMINUIR (voce aparece indo para a esquerda da imagem, como
    numa foto). Mas o sistema de coordenadas da tela tem X crescendo para a
    direita do observador. Espelhando o frame, `u` cresce junto com o X da tela
    e a formula X = (u - cx) * Z / f_px vale como escrita, sem sinal extra.
    """
    ok, frame = cap.read()
    if not ok:
        return None
    if config.FLIP_FRAME:
        frame = cv2.flip(frame, 1)
    return frame


def find_landmarks(landmarker, frame, timestamp_ms):
    """Retorna os 478 landmarks em pixels, array (478, 2), ou None se nao houver rosto."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(image, timestamp_ms)
    if not result.face_landmarks:
        return None
    h, w = frame.shape[:2]
    return np.array([[p.x * w, p.y * h] for p in result.face_landmarks[0]])


def find_irises(landmarker, frame, timestamp_ms):
    """Retorna (iris_esq_px, iris_dir_px) em pixels, ou None se nao houver rosto."""
    pts = find_landmarks(landmarker, frame, timestamp_ms)
    if pts is None:
        return None
    return pts[IRIS_L], pts[IRIS_R]


def ipd_and_midpoint(left, right):
    """Distancia interpupilar em pixels e ponto medio entre as irises."""
    ipd_px = float(np.linalg.norm(left - right))
    mid = (left + right) / 2.0
    return ipd_px, mid


class Clock:
    """Timestamps em ms, estritamente crescentes (exigencia do modo VIDEO)."""

    def __init__(self):
        self._t0 = time.perf_counter()
        self._last = -1

    def now_ms(self):
        ms = int((time.perf_counter() - self._t0) * 1000)
        if ms <= self._last:
            ms = self._last + 1
        self._last = ms
        return ms


def load_calibration(frame_w, frame_h):
    """Le o f_px do focal.json e confere que ele ainda vale para esta captura.

    Duas checagens que existem porque a falha delas e silenciosa e o resultado
    e um Z errado sem nenhum sintoma visivel:

    - Resolucao. f_px esta em pixels do frame capturado. Trocar CAM_REQ_W depois
      de calibrar escala o f_px pelo mesmo fator e o Z sai errado.
    - IPD_REAL. Na formula final o IPD_REAL cancela (Z = D * ipd_calib / ipd),
      mas so se o valor usado aqui for o mesmo usado na calibracao, porque o f_px
      gravado ja carrega o valor antigo dentro dele.
    """
    if not os.path.exists(config.CALIB_FILE):
        raise RuntimeError("Sem calibracao. Rode calibrate.py primeiro.")
    with open(config.CALIB_FILE, encoding="utf-8") as fh:
        data = json.load(fh)

    if (data["frame_w"], data["frame_h"]) != (frame_w, frame_h):
        raise RuntimeError(
            f"Calibracao feita em {data['frame_w']}x{data['frame_h']} mas a captura "
            f"esta em {frame_w}x{frame_h}. Recalibre ou volte a resolucao antiga.")

    if abs(data["ipd_real_m"] - config.IPD_REAL) > 1e-9:
        raise RuntimeError(
            f"Calibracao usou IPD_REAL={data['ipd_real_m']:.4f} mas o config diz "
            f"{config.IPD_REAL:.4f}. Recalibre, senao o Z sai errado pelo fator "
            f"{config.IPD_REAL / data['ipd_real_m']:.3f}.")

    return data["f_px"]


def head_position(pts, frame_shape, f_px):
    """Posicao 3D metrica da cabeca no referencial da CAMERA, em metros.

    Modelo pinhole com a distancia interpupilar como segmento de comprimento
    conhecido. O ponto retornado e o meio das duas irises: o "olho ciclopico",
    que e o centro de projecao correto para display monoscopico.

        Z = f_px * IPD_REAL / ipd_px
        X = (u - cx) * Z / f_px
        Y = -(v - cy) * Z / f_px

    O sinal negativo em Y converte o eixo da imagem, que cresce para baixo, para
    o eixo do mundo, que cresce para cima. O sinal de X ja esta certo porque o
    frame vem espelhado (ver read_frame).

    Assume o ponto principal no centro da imagem, o que e aproximacao: a rigor
    ele sai um pouco do centro e so uma calibracao completa com tabuleiro daria
    o valor real. Assume tambem ipd_px medido sem guinada; virar a cabeca encolhe
    ipd_px por cos(yaw) e infla o Z. Essa e a maior fonte de erro do sistema.
    """
    h, w = frame_shape[:2]
    cx, cy = w / 2.0, h / 2.0
    ipd_px, (u, v) = ipd_and_midpoint(pts[IRIS_L], pts[IRIS_R])

    Z = f_px * config.IPD_REAL / ipd_px
    X = (u - cx) * Z / f_px
    Y = -(v - cy) * Z / f_px
    return np.array([X, Y, Z])


def eye_in_screen_coords(head_cam):
    """Do referencial da camera para o da TELA.

    Tela: origem no centro da area visivel, X para a direita, Y para cima,
    Z saindo da tela na direcao do rosto. Plano da tela em Z = 0.

    A camera fica acima do centro da tela, entao basta somar o deslocamento.
    Assume o eixo optico perpendicular ao plano da tela. Em notebook isso vale
    praticamente por construcao, porque a camera e solidaria a tampa e gira junto
    com ela; o sistema de coordenadas inclina junto, que e o que queremos. A
    premissa quebraria com webcam externa apoiada em outro plano.
    """
    X, Y, Z = head_cam
    return np.array([X + config.CAM_OFFSET_X, Y + config.CAM_OFFSET_Y, Z])


def _debug_view():
    """M3: posicao 3D metrica ao vivo, com medicao congelavel para validar."""
    cap = open_camera()
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    f_px = load_calibration(frame_w, frame_h)
    landmarker = make_landmarker()
    clock = Clock()
    font = cv2.FONT_HERSHEY_SIMPLEX
    print(f"f_px = {f_px:.1f}   captura {frame_w}x{frame_h}")
    print("ESPACO mede (mediana de 60 frames)   q sai")

    fps, t_prev = 0.0, time.perf_counter()
    samples, frozen = None, None

    while True:
        frame = read_frame(cap)
        if frame is None:
            break
        pts = find_landmarks(landmarker, frame, clock.now_ms())

        now = time.perf_counter()
        fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-6)
        t_prev = now

        if pts is None:
            cv2.putText(frame, "sem rosto", (20, 50), font, 1.0, (0, 0, 255), 2)
        else:
            head = head_position(pts, frame.shape, f_px)
            ipd_px, mid = ipd_and_midpoint(pts[IRIS_L], pts[IRIS_R])
            cv2.line(frame, tuple(pts[IRIS_L].astype(int)),
                     tuple(pts[IRIS_R].astype(int)), (0, 255, 0), 1)
            cv2.circle(frame, tuple(mid.astype(int)), 4, (255, 0, 255), -1)

            cv2.putText(frame, f"Z = {head[2]*100:6.1f} cm", (20, 60),
                        font, 1.4, (0, 255, 0), 3)
            cv2.putText(frame, f"X = {head[0]*100:6.1f} cm    Y = {head[1]*100:6.1f} cm",
                        (20, 110), font, 0.9, (0, 255, 255), 2)
            cv2.putText(frame, f"ipd_px {ipd_px:.2f}    {fps:.1f} fps", (20, 145),
                        font, 0.6, (200, 200, 200), 1)
            cv2.putText(frame, "X>0 cabeca a direita    Y>0 cabeca acima da camera",
                        (20, 175), font, 0.55, (140, 140, 140), 1)

            if samples is not None:
                samples.append(head)
                cv2.putText(frame, f"medindo {len(samples)}/60", (20, 215),
                            font, 0.8, (0, 165, 255), 2)
                if len(samples) >= 60:
                    frozen = np.median(np.array(samples), axis=0)
                    samples = None

        if frozen is not None:
            cv2.putText(frame,
                        f"MEDIDO   Z {frozen[2]*100:.2f} cm   "
                        f"X {frozen[0]*100:.2f}   Y {frozen[1]*100:.2f}",
                        (20, frame_h - 60), font, 0.85, (255, 255, 255), 2)
        cv2.putText(frame, "ESPACO mede    q sai", (20, frame_h - 20),
                    font, 0.6, (200, 200, 200), 1)

        cv2.imshow("M3 - posicao 3D metrica", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" "):
            samples, frozen = [], None

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    _debug_view()
