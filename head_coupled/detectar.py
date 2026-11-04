"""Deteccao dos cantos ChArUco das duas telas numa foto.

Fluxo por foto:
  1. Um ArucoDetector acha TODOS os marcadores de uma vez (as duas telas usam
     o mesmo dicionario com faixas de id disjuntas). Opcionalmente numa copia
     reduzida da foto, que e bem mais rapido em 12 MP (ver escala_marcadores).
  2. Os marcadores sao separados por faixa de id, um grupo por tela.
  3. Para cada tela, CharucoDetector.detectBoard(foto, markerCorners=grupo,
     markerIds=grupo) interpola os cantos do xadrez a partir dos marcadores e os
     refina com cornerSubPix NA FOTO EM RESOLUCAO CHEIA.
  4. Verificacao geometrica barata: homografia RANSAC entre a posicao metrica
     dos cantos na tela e a posicao na foto. Canto com id trocado cai a um
     quadrado inteiro de distancia e sai aqui. A tolerancia e uma fracao do
     tamanho do quadrado na foto, porque a distorcao da lente afasta os pontos
     de uma homografia exata em alguns pixels.
  5. Cada canto vira um par (ponto 3D metrico no referencial da tela, pixel).

Por que nao um CharucoDetector por tela direto na foto: funcionaria (o
detector de A ignora os marcadores de B, testado em padroes.validar()), mas
rodaria a deteccao de marcadores, que e a parte cara, uma vez por tela.

Convencao de pixel: a mesma do OpenCV (centro do pixel em inteiro). O
CharucoDetector devolve os cantos nela (medido em padroes.validar()).
"""

import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class DeteccaoTela:
    """Cantos de uma tela numa foto."""
    ids: np.ndarray       # (n,) ids dos cantos ChArUco, 0-based por tela
    img: np.ndarray       # (n,2) pixels na foto
    obj: np.ndarray       # (n,3) metros no referencial da tela (z = 0)
    n_marcadores: int     # marcadores desta tela achados na foto

    @property
    def n(self):
        return len(self.ids)


def parametros_aruco():
    """Parametros do ArucoDetector ajustados para fotos de 12 MP de telas.

    - minMarkerPerimeterRate: o padrao 0.03 exige perimetro >= 3% da maior
      dimensao da imagem, 120 px em 4000 px, isto e marcador de 30 px de lado.
      Marcador do notebook a 1.5 m e 45 graus fica perto disso. 0.01 libera.
    - janelas do limiar adaptativo maiores: em 12 MP uma celula do marcador tem
      de 5 a 30 px, e janela de 23 px (padrao) e pequena para as celulas
      grandes. 3..53 passo 10 mantem o custo razoavel.
    - refinamento subpixel dos cantos dos MARCADORES: melhora o chute inicial da
      interpolacao dos cantos ChArUco. Os cantos ChArUco sao refinados de
      qualquer jeito pelo CharucoDetector.
    """
    p = cv2.aruco.DetectorParameters()
    p.minMarkerPerimeterRate = 0.01
    p.adaptiveThreshWinSizeMin = 3
    p.adaptiveThreshWinSizeMax = 53
    p.adaptiveThreshWinSizeStep = 10
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return p


class Detector:
    """Detector das telas de um conjunto de Padroes (mesmo dicionario)."""

    def __init__(self, padroes, params=None, escala_marcadores=1.0, verificar=True,
                 refinar_marcadores=False, min_marcadores=2):
        """refinar_marcadores: procura, entre os candidatos rejeitados, marcadores
        que o layout do tabuleiro diz que deveriam estar ali (refineDetectedMarkers).
        min_marcadores: quantos marcadores vizinhos um canto ChArUco exige (o
        padrao do OpenCV e 2; 1 recupera cantos na borda de um reflexo)."""
        self.padroes = padroes
        self.refinar = refinar_marcadores
        dic_id = {p.dicionario_id for p in padroes}
        if len(dic_id) != 1:
            raise ValueError("todas as telas precisam do mesmo dicionario")
        self.params = params or parametros_aruco()
        self.aruco = cv2.aruco.ArucoDetector(padroes[0].dic, self.params)
        cp = cv2.aruco.CharucoParameters()
        cp.minMarkers = int(min_marcadores)
        self.charuco = [cv2.aruco.CharucoDetector(p.board, cp, self.params) for p in padroes]
        self.escala = float(escala_marcadores)
        self.verificar = verificar
        self.tempo = {}

    def marcadores(self, cinza, com_rejeitados=False):
        """Todos os marcadores da foto: (lista de (4,2), ids (n,)) [+ rejeitados]."""
        if self.escala != 1.0:
            peq = cv2.resize(cinza, None, fx=self.escala, fy=self.escala,
                             interpolation=cv2.INTER_AREA)
            cantos, ids, rej = self.aruco.detectMarkers(peq)
            s = 1.0 / self.escala
            cantos = [((c + 0.5) * s - 0.5).astype(np.float32) for c in cantos]
            rej = [((c + 0.5) * s - 0.5).astype(np.float32) for c in rej]
        else:
            cantos, ids, rej = self.aruco.detectMarkers(cinza)
        if ids is None:
            cantos, ids = [], np.zeros(0, int)
        else:
            cantos, ids = [c.reshape(4, 2) for c in cantos], ids.ravel()
        return (cantos, ids, rej) if com_rejeitados else (cantos, ids)

    def detectar(self, cinza, n_min=8):
        """Lista com um DeteccaoTela (ou None) por padrao."""
        t0 = time.perf_counter()
        cantos, ids, rej = self.marcadores(cinza, com_rejeitados=True)
        t1 = time.perf_counter()
        saida = []
        for p, det in zip(self.padroes, self.charuco):
            sel = np.flatnonzero(p.contem_marcador(ids))
            if len(sel) < 2:
                saida.append(None)
                continue
            mc = tuple(cantos[i].reshape(1, 4, 2).astype(np.float32) for i in sel)
            mi = ids[sel].reshape(-1, 1).astype(np.int32)
            if self.refinar and len(rej):
                mc, mi, _, _ = self.aruco.refineDetectedMarkers(cinza, p.board, mc, mi, rej)
                ok = p.contem_marcador(mi)
                mc = tuple(c for c, o in zip(mc, ok) if o)
                mi = mi.reshape(-1, 1)[ok].astype(np.int32)
                sel = np.arange(len(mi))
            ch, chid, _, _ = det.detectBoard(cinza, markerCorners=mc, markerIds=mi)
            if chid is None or len(chid) < n_min:
                saida.append(None)
                continue
            chid = chid.ravel().astype(int)
            ch = ch.reshape(-1, 2).astype(float)
            if self.verificar:
                ok = _consistente(p, chid, ch)
                chid, ch = chid[ok], ch[ok]
                if len(chid) < n_min:
                    saida.append(None)
                    continue
            saida.append(DeteccaoTela(chid, ch, p.cantos_metricos(chid), len(sel)))
        t2 = time.perf_counter()
        self.tempo = {"marcadores_s": t1 - t0, "charuco_s": t2 - t1}
        return saida


def _consistente(padrao, ids, uv, frac=0.25):
    """Mascara dos cantos coerentes com uma homografia tela->foto (RANSAC)."""
    xy = padrao.pixels_cantos(ids)
    if len(ids) < 6:
        return np.ones(len(ids), bool)
    H, _ = cv2.findHomography(xy, uv, 0)
    if H is None:
        return np.ones(len(ids), bool)
    # tamanho tipico de um quadrado na foto, para a tolerancia
    J = np.linalg.norm(cv2.perspectiveTransform((xy + [padrao.quad_px, 0]).reshape(-1, 1, 2), H).reshape(-1, 2)
                       - cv2.perspectiveTransform(xy.reshape(-1, 1, 2), H).reshape(-1, 2), axis=1)
    tol = max(2.0, frac * float(np.median(J)))
    H, mask = cv2.findHomography(xy, uv, cv2.RANSAC, tol)
    if mask is None:
        return np.ones(len(ids), bool)
    return mask.ravel().astype(bool)


def ler_foto(caminho):
    """Le a foto em tons de cinza IGNORANDO a orientacao EXIF.

    Celular segurado em pe grava a foto deitada com uma etiqueta EXIF de
    rotacao. O imread do OpenCV aplica essa rotacao por padrao, e ai fotos em pe
    e deitadas teriam cx/cy e fx/fy trocados entre si: nao existe UM modelo de
    camera para todas. Ignorando o EXIF, todas ficam na orientacao do sensor.
    (Se o aplicativo girar os pixels de verdade em vez de usar a etiqueta, as
    fotos em pe chegam com h > w; o calibrar_telas.py recusa tamanhos misturados.)

    Le por np.fromfile + imdecode, e nao por imread: no Windows o imread abre o
    arquivo com fopen de 8 bits e falha em caminho com acento (por exemplo
    "OneDrive\\Area de Trabalho" com acento no A).
    """
    caminho = str(caminho)
    if caminho.lower().endswith((".heic", ".heif")):
        raise IOError(f"{caminho}: o OpenCV nao le HEIC/HEIF. No celular, desligue "
                      "'fotos de alta eficiencia' (Samsung) ou escolha JPEG, e tire "
                      "as fotos de novo.")
    try:
        dados = np.fromfile(caminho, dtype=np.uint8)
    except OSError as e:
        raise IOError(f"nao consegui abrir {caminho}: {e}") from e
    img = cv2.imdecode(dados, cv2.IMREAD_GRAYSCALE | cv2.IMREAD_IGNORE_ORIENTATION)
    if img is None:
        raise IOError(f"nao consegui ler {caminho} como imagem")
    return img


def desenhar(cinza, deteccoes, escala=0.25):
    """Miniatura colorida com os cantos detectados (para conferir a olho)."""
    img = cv2.cvtColor(cv2.resize(cinza, None, fx=escala, fy=escala,
                                  interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
    cores = [(0, 200, 255), (255, 120, 0)]
    for d, cor in zip(deteccoes, cores):
        if d is None:
            continue
        for (u, v), i in zip(d.img, d.ids):
            c = (int((u + 0.5) * escala - 0.5), int((v + 0.5) * escala - 0.5))
            cv2.circle(img, c, 3, cor, -1)
    return img
