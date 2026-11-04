"""Bancada comum dos testes automaticos: roda sem webcam, sem MediaPipe e sem
janela, em qualquer sistema (inclusive o Linux da nuvem onde foram escritos).

Importe este modulo ANTES de config/tracking/main: ele poe a pasta head_coupled
no sys.path e oferece:

  - stub_mediapipe(): modulos falsos, so para o import do tracking.py passar;
  - stub_gui(): troca as funcoes de janela do cv2 por versoes que so gravam o
    que seria mostrado (hash de cada imshow), com relogio deterministico;
  - carregar_ap1(nome): o arquivo `nome`.py exatamente como estava no fim da
    AP1 (commit REF_AP1), tirado do git, para os testes de regressao.
"""

import hashlib
import importlib.util
import os
import subprocess
import sys
import types

import numpy as np

TESTES = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.dirname(TESTES)                      # head_coupled/
SAIDA = os.path.join(TESTES, "saida")
os.makedirs(SAIDA, exist_ok=True)
if PASTA not in sys.path:
    sys.path.insert(0, PASTA)

# Ultimo commit da AP1 no main (merge do PR #2). Se um dia existir a tag "ap1",
# ela tem preferencia.
REF_AP1 = "42e5f68"


class Pular(Exception):
    """O teste nao pode rodar neste ambiente (falta git, por exemplo)."""


def stub_mediapipe():
    if "mediapipe" in sys.modules and getattr(sys.modules["mediapipe"], "_falso", False):
        return
    mp = types.ModuleType("mediapipe")
    mp._falso = True
    tasks = types.ModuleType("mediapipe.tasks")
    py = types.ModuleType("mediapipe.tasks.python")
    vision = types.ModuleType("mediapipe.tasks.python.vision")
    py.vision = vision
    tasks.python = py
    mp.tasks = tasks
    sys.modules.update({"mediapipe": mp, "mediapipe.tasks": tasks,
                        "mediapipe.tasks.python": py,
                        "mediapipe.tasks.python.vision": vision})


def carregar_ap1(nome, como=None, injetar=None):
    """Importa `nome`.py da AP1 (do git) como o modulo `como` (padrao nome_ap1).

    injetar: {nome_de_modulo: modulo} posto em sys.modules so durante o import,
    para o arquivo antigo importar as versoes antigas dos vizinhos (o main da
    AP1 importa "scene", que tem de ser o scene da AP1).
    """
    como = como or f"{nome}_ap1"
    if como in sys.modules:
        return sys.modules[como]
    destino = os.path.join(SAIDA, "ap1", f"{nome}.py")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    fonte = None
    for ref in ("ap1", REF_AP1):
        try:
            fonte = subprocess.run(["git", "show", f"{ref}:head_coupled/{nome}.py"],
                                   cwd=PASTA, capture_output=True, check=True).stdout
            break
        except (OSError, subprocess.CalledProcessError):
            continue
    if fonte is None:
        raise Pular(f"sem git ou sem o commit {REF_AP1} da AP1: regressao pulada")
    with open(destino, "wb") as fh:
        fh.write(fonte)
    antigos = {}
    for k, mod in (injetar or {}).items():
        antigos[k] = sys.modules.get(k)
        sys.modules[k] = mod
    try:
        spec = importlib.util.spec_from_file_location(como, destino)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[como] = mod
        spec.loader.exec_module(mod)
    finally:
        for k, mod_antigo in antigos.items():
            if mod_antigo is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = mod_antigo
    return mod


class GuiFalsa:
    """Substitui a GUI do cv2 e o relogio. Uso: gui = GuiFalsa(); gui.instalar().

    Cada imshow grava (quadro, janela, sha1 da imagem). waitKey devolve a tecla
    programada para o quadro atual. O relogio anda 1/30 s por quadro, entao o
    filtro, a animacao e o HUD dao o mesmo resultado em toda execucao.
    """

    def __init__(self, tam=(1920, 1080), avancar_no_waitkey=False):
        """avancar_no_waitkey: sem webcam falsa (calibrar_telas.py mostrar,
        testar_monitores.py) quem conta os quadros e o proprio waitKey."""
        self.tam = tam
        self.avancar_no_waitkey = avancar_no_waitkey
        self.reiniciar({})

    def reiniciar(self, teclas, guardar=()):
        self.quadro = 0
        self.teclas = {k: (ord(c) if isinstance(c, str) else c) for k, c in teclas.items()}
        self.gravados = []
        self.pos = {}
        self.guardar = set(guardar)
        self.imagens = {}
        self.propriedades = []

    def relogio(self):
        return 1000.0 + self.quadro / 30.0

    def instalar(self):
        import time

        import cv2
        time.perf_counter = self.relogio
        cv2.namedWindow = lambda *a, **k: None
        cv2.setWindowProperty = lambda *a, **k: self.propriedades.append(a)
        cv2.moveWindow = lambda nome, x, y: self.pos.__setitem__(nome, (x, y))
        cv2.imshow = self._imshow
        cv2.getWindowImageRect = self._rect
        cv2.getWindowProperty = lambda *a, **k: 1.0
        cv2.destroyAllWindows = lambda: None
        cv2.waitKey = self._waitkey
        return self

    def _waitkey(self, ms=0):
        if self.avancar_no_waitkey:
            self.quadro += 1
            if self.quadro > 10000:
                raise RuntimeError("GuiFalsa: o programa nunca saiu (faltou a tecla q?)")
        return self.teclas.get(self.quadro, -1) & 0xFFFFFFFF

    # Faixa de baixo onde o main.py escreve a legenda das teclas. A AP2 mudou
    # o texto (tecla y), entao a comparacao com a AP1 ignora essas linhas.
    RODAPE_PX = 80

    def _imshow(self, nome, img):
        h = hashlib.sha1(np.ascontiguousarray(img).tobytes()).hexdigest()
        h_corpo = hashlib.sha1(np.ascontiguousarray(img[:-self.RODAPE_PX]).tobytes()
                               ).hexdigest()
        self.gravados.append((self.quadro, nome, h, h_corpo))
        if self.quadro in self.guardar:
            self.imagens[(self.quadro, nome)] = img.copy()

    def _rect(self, nome):
        x, y = self.pos.get(nome, (0, 0))
        return (x, y, self.tam[0], self.tam[1])


class CapturaFalsa:
    """Webcam falsa: so conta quadros. As irises vem de landmarks_falsos()."""

    def __init__(self, gui):
        self.gui = gui

    def get(self, prop):
        import cv2
        return {cv2.CAP_PROP_FRAME_WIDTH: 1280, cv2.CAP_PROP_FRAME_HEIGHT: 720}.get(prop, 0)

    def read(self):
        self.gui.quadro += 1
        return True, np.zeros((720, 1280, 3), np.uint8)

    def release(self):
        pass


F_PX = 970.1153672240356


def cabeca(i):
    """Cabeca no referencial da CAMERA, em metros: passeia e se aproxima."""
    import config
    return np.array([0.10 * np.sin(i * 0.11) + 0.06,
                     -config.CAM_OFFSET_Y + 0.03 * np.sin(i * 0.07),
                     0.58 + 0.08 * np.cos(i * 0.05)])


def landmarks_falsos(gui):
    """find_landmarks falso: irises sinteticas da cabeca(i), pinhole inverso."""
    import config
    import tracking

    def f(_landmarker, _frame, _ts):
        X, Y, Z = cabeca(gui.quadro)
        u, v = 640 + X * F_PX / Z, 360 - Y * F_PX / Z
        meio = F_PX * config.IPD_REAL / Z / 2
        pts = np.zeros((478, 2))
        pts[tracking.IRIS_L] = (u - meio, v)
        pts[tracking.IRIS_R] = (u + meio, v)
        return pts
    return f


def instalar_tracking_falso(gui, eixo=None):
    """Webcam, calibracao e MediaPipe falsos no modulo tracking.

    eixo: o que find_landmarks_pose devolve como eixo interocular. None imita
    o MediaPipe sem a matriz (sem correcao de guinada, igual a AP1).
    """
    import tracking
    lm = landmarks_falsos(gui)
    tracking.open_camera = lambda: CapturaFalsa(gui)
    tracking.load_calibration = lambda w, h: F_PX
    tracking.make_landmarker = lambda: None
    tracking.find_landmarks = lm
    tracking.find_landmarks_pose = lambda a, b, c: (lm(a, b, c), eixo)


def resultado(ok, msg):
    """Linha final padronizada, lida pelo rodar_testes.py."""
    print(("OK      " if ok else "FALHOU  ") + msg)
    return 0 if ok else 1
