"""Padroes ChArUco exibidos nas telas e o mapa canto -> coordenada metrica.

Cada tela mostra, em tela cheia, um tabuleiro ChArUco proprio. O celular
fotografa as duas telas juntas e o calibrar_telas.py descobre onde a tela B
(monitor externo) esta no referencial da tela A (o notebook, cuja webcam faz o
tracking). Quem mostra os padroes nas telas e o calibrar_telas.py mostrar, que
grava a descricao exata deles no padroes.json; este modulo so gera e descreve.

Por que ChArUco e nao xadrez puro:
  - cada canto tem identidade (id). Uma foto que ve so metade de uma tela ainda
    serve, e duas telas na mesma foto nao se confundem;
  - os cantos do xadrez (pontos de sela entre quadrados pretos) sao refinados
    com subpixel e sao bem mais precisos que os cantos dos marcadores ArUco. Os
    marcadores so servem para dar nome e posicao aproximada aos cantos.

IDs disjuntos: a tela A usa os marcadores id0_A .. id0_A+nA-1 e a B usa os
seguintes, do MESMO dicionario. Um unico ArucoDetector acha todos os marcadores
da foto de uma vez e a separacao por tela e so um filtro por faixa de id.

CONVENCAO, medida (igual no OpenCV 4.14 e no 5.0, ver validar()):
  - board.getChessboardCorners()[k] = ((x+1)*q, (y+1)*q, 0) com x = k % (cols-1)
    e y = k // (cols-1). Origem no canto SUPERIOR esquerdo do tabuleiro, X para
    a direita e Y PARA BAIXO, igual as linhas da imagem de generateImage().
    (OpenCV <= 4.5 contrib usava origem embaixo e Y para cima. Nao dependemos
    disso: o mapa abaixo e nosso, so usamos o id do canto.)
  - Com generateImage((cols*q, rows*q), marginSize=0) e q inteiro, a coordenada
    0 do tabuleiro e a borda esquerda do pixel 0. Na convencao do OpenCV (centro
    do pixel em coordenada inteira) o canto k fica em
        u = off_x + (x+1)*q - 0.5        v = off_y + (y+1)*q - 0.5
    e e exatamente ai que o CharucoDetector o devolve (erro medido: 0.0000 px).
  - No referencial da TELA (metros, origem no centro da area acesa, x direita,
    y para cima, z saindo da tela na direcao do rosto) a area acesa vai da borda
    esquerda do pixel 0 a borda direita do pixel W-1, entao
        x_m = (u + 0.5) * LARG/W - LARG/2
        y_m = ALT/2 - (v + 0.5) * ALT/H
    Isso so supoe pixel uniforme no painel, o que vale para LCD/OLED.
  - Numero IMPAR de linhas de quadrados. Com numero par o OpenCV >= 4.6 mudou o
    desenho (setLegacyPattern): um tabuleiro gerado num programa e detectado
    noutro com a outra convencao poe os marcadores nos quadrados errados. Com
    linhas impares os dois desenhos coincidem e a armadilha some.

Uso:
    python padroes.py                 gera padrao_<nome>.png de cada tela
    python padroes.py --validar       detecta os cantos nas proprias imagens
"""

import argparse
import math
from dataclasses import dataclass

import cv2
import numpy as np

import config

# Dicionario ArUco: 5x5 com 250 codigos (usamos 90). Medido em experimentos.py
# (exp_deteccao, 400 fotos simuladas de uma tela so, 0.6-2.5 m, 0-70 graus):
#   - dentro do protocolo (ate ~1.2 m e 45 graus) 4x4 e 5x5 detectam igual;
#   - longe E obliquo o 4x4 ganha (celula 17% maior: 6 celulas de lado contra
#     7), p.ex. notebook a 1.5 m e 60 graus: 42% dos cantos contra 18%;
#   - mas o 4x4 leu 4 marcadores FALSOS (id de uma tela que nem estava na foto)
#     em 200 fotos e o 5x5 nenhum. Distancia de Hamming minima entre os codigos:
#     3 no 4x4 contra 7 no 5x5, e o detector do OpenCV nao corrige nenhum bit no
#     4x4 (errorCorrectionRate 0.6 * 1 bit -> 0) e corrige 1 no 5x5.
# Fora do protocolo a perda e de cantos, que se compensa com mais uma foto; um
# marcador falso, num fundo real cheio de teclas e texto, e erro silencioso.
DICIONARIO = cv2.aruco.DICT_5X5_250

QUAD_PX = 140            # lado do quadrado numa tela de 1080 linhas (inteiro!)
FRACAO_MARCADOR = 0.7    # lado do marcador / lado do quadrado
MARGEM_MIN_PX = 40       # borda branca minima ate a moldura


@dataclass(frozen=True)
class Tela:
    """Uma tela fisica: resolucao em pixels e tamanho da AREA ACESA em metros."""
    nome: str
    px_w: int
    px_h: int
    larg_m: float
    alt_m: float

    @classmethod
    def de_diagonal(cls, nome, px_w, px_h, diagonal_pol):
        """Tamanho a partir da diagonal nominal, supondo pixel quadrado.

        Cuidado: monitor vendido como 24 pol costuma ser 23.8 pol (0.527 m de
        largura), 1% menor. O calibrar_telas.py estima essa escala por padrao
        (--fixar-escala-b desliga).
        """
        k = diagonal_pol * 0.0254 / math.hypot(px_w, px_h)
        return cls(nome, px_w, px_h, px_w * k, px_h * k)

    def escalada(self, s):
        """Mesma tela com o tamanho fisico multiplicado por s."""
        return Tela(self.nome, self.px_w, self.px_h, self.larg_m * s, self.alt_m * s)


# As duas telas padrao do projeto: o notebook do config.py e um monitor de
# 1920x1080 com a diagonal do config. O calibrar_telas.py mostrar troca isso
# pelas resolucoes reais dos monitores e grava no padroes.json.
TELA_A = Tela("notebook", config.SCREEN_PX_W, config.SCREEN_PX_H,
              config.SCREEN_W, config.SCREEN_H)
TELA_B = Tela.de_diagonal("monitor", 1920, 1080, config.MONITOR_DIAGONAL_POL)


def quad_px_para(px_w, px_h):
    """Lado do quadrado em pixels para uma tela desta resolucao.

    140 px numa tela de 1080 linhas (o layout medido nos experimentos: 13x7
    quadrados com margem). Em outras resolucoes escala com o MENOR lado, para o
    tabuleiro continuar com ~13x7 quadrados: 4K vira 280 px, 1366x768 vira 100
    px, um monitor em pe (1080x1920) continua 140 px e fica 7x13.
    """
    return max(60, int(round(QUAD_PX * min(px_w, px_h) / 1080)))


class Padrao:
    """Tabuleiro ChArUco de uma tela, com a geometria toda em pixels da tela.

    O board do OpenCV e criado com lado do quadrado em PIXELS (QUAD_PX), nao em
    metros. A escala do board nao importa para o detector (a interpolacao dos
    cantos usa homografias locais, invariantes a escala) e assim o mapa para a
    tela e so um deslocamento de off_x, off_y.
    """

    def __init__(self, tela, id0, quad_px=None, fracao_marcador=FRACAO_MARCADOR,
                 margem_min_px=MARGEM_MIN_PX, dicionario=DICIONARIO):
        self.tela = tela
        self.id0 = int(id0)
        if quad_px is None:
            quad_px = quad_px_para(tela.px_w, tela.px_h)
        self.quad_px = int(quad_px)
        self.cols = (tela.px_w - 2 * margem_min_px) // self.quad_px
        self.rows = (tela.px_h - 2 * margem_min_px) // self.quad_px
        if self.rows % 2 == 0:
            self.rows -= 1                    # linhas impares: sem ambiguidade legacy
        if self.cols < 3 or self.rows < 3:
            raise ValueError("tela pequena demais para esse quadrado")
        self.off_x = (tela.px_w - self.cols * self.quad_px) // 2
        self.off_y = (tela.px_h - self.rows * self.quad_px) // 2
        # Marcador com borda branca (q - m)/2 inteira, para o desenho ser exato.
        m = int(round(fracao_marcador * self.quad_px))
        if (self.quad_px - m) % 2:
            m -= 1
        self.marcador_px = m
        self.dicionario_id = dicionario
        self.dic = cv2.aruco.getPredefinedDictionary(dicionario)

        # Quantos marcadores cabem: board temporario sem ids.
        tmp = cv2.aruco.CharucoBoard((self.cols, self.rows), float(self.quad_px),
                                     float(m), self.dic)
        self.n_marcadores = len(tmp.getIds())
        if self.id0 + self.n_marcadores > self.dic.bytesList.shape[0]:
            raise ValueError("dicionario nao tem ids suficientes para as duas telas "
                             f"({self.id0 + self.n_marcadores} > "
                             f"{self.dic.bytesList.shape[0]})")
        ids = np.arange(self.id0, self.id0 + self.n_marcadores, dtype=np.int32)
        self.board = cv2.aruco.CharucoBoard((self.cols, self.rows), float(self.quad_px),
                                            float(m), self.dic, ids)
        self.board.setLegacyPattern(False)
        self.n_cantos = (self.cols - 1) * (self.rows - 1)

    # ---------------------------------------------------------------- ids
    @property
    def id_fim(self):
        """Primeiro id de marcador que NAO pertence a esta tela."""
        return self.id0 + self.n_marcadores

    def contem_marcador(self, ids):
        ids = np.asarray(ids).ravel()
        return (ids >= self.id0) & (ids < self.id_fim)

    # ------------------------------------------------------------- imagem
    def imagem(self):
        """Imagem uint8 do tamanho exato da tela: branco com o tabuleiro no meio."""
        w, h = self.cols * self.quad_px, self.rows * self.quad_px
        tab = self.board.generateImage((w, h), marginSize=0, borderBits=1)
        img = np.full((self.tela.px_h, self.tela.px_w), 255, np.uint8)
        img[self.off_y:self.off_y + h, self.off_x:self.off_x + w] = tab
        return img

    # ------------------------------------------------------- geometria
    def pixels_cantos(self, ids=None):
        """(n,2) posicao dos cantos ChArUco na imagem da tela, convencao OpenCV."""
        ids = np.arange(self.n_cantos) if ids is None else np.asarray(ids).ravel()
        x = ids % (self.cols - 1)
        y = ids // (self.cols - 1)
        u = self.off_x + (x + 1) * self.quad_px - 0.5
        v = self.off_y + (y + 1) * self.quad_px - 0.5
        return np.stack([u, v], axis=1).astype(float)

    def metros_de_pixel(self, uv, tela=None):
        """(n,2) pixels da tela -> (n,3) metros no referencial da tela (z = 0).

        tela permite trocar o tamanho fisico (escala estimada da tela B).
        """
        t = self.tela if tela is None else tela
        uv = np.asarray(uv, float).reshape(-1, 2)
        x = (uv[:, 0] + 0.5) * (t.larg_m / t.px_w) - t.larg_m / 2
        y = t.alt_m / 2 - (uv[:, 1] + 0.5) * (t.alt_m / t.px_h)
        return np.stack([x, y, np.zeros_like(x)], axis=1)

    def cantos_metricos(self, ids=None, tela=None):
        """(n,3) cantos ChArUco no referencial metrico da tela."""
        return self.metros_de_pixel(self.pixels_cantos(ids), tela)

    def quinas_tela(self, tela=None):
        """(4,3) quinas da area acesa: inf-esq, inf-dir, sup-dir, sup-esq."""
        t = self.tela if tela is None else tela
        w, h = t.larg_m / 2, t.alt_m / 2
        return np.array([[-w, -h, 0], [w, -h, 0], [w, h, 0], [-w, h, 0]], float)

    def descricao(self):
        """Dicionario serializavel com tudo que define o padrao."""
        nome_dic = next((n for n in dir(cv2.aruco) if n.startswith("DICT_")
                         and getattr(cv2.aruco, n) == self.dicionario_id), "?")
        return {"dicionario": int(self.dicionario_id), "dicionario_nome": nome_dic,
                "quad_px": self.quad_px,
                "marcador_px": self.marcador_px, "cols": self.cols, "rows": self.rows,
                "off_px": [self.off_x, self.off_y], "id0": self.id0,
                "n_marcadores": self.n_marcadores, "n_cantos": self.n_cantos}


def padroes_projeto(tela_a=TELA_A, tela_b=TELA_B, **kw):
    """Os dois padroes do projeto, com ids disjuntos: A primeiro, B em seguida."""
    pa = Padrao(tela_a, 0, **kw)
    pb = Padrao(tela_b, pa.id_fim, **kw)
    return [pa, pb]


def para_json(padroes, monitores=None, extra=None):
    """Descricao completa dos padroes exibidos: o padroes.json.

    E o contrato entre o calibrar_telas.py mostrar (que exibe) e o calcular (que
    precisa saber EXATAMENTE onde cada canto estava em cada tela). monitores:
    um Monitor (monitores.py) por padrao, ou None.
    """
    import time
    monitores = monitores or [None] * len(padroes)
    telas = []
    for p, mon in zip(padroes, monitores):
        telas.append({"nome": p.tela.nome,
                      "monitor": None if mon is None else mon.para_json(),
                      "resolucao_px": [p.tela.px_w, p.tela.px_h],
                      "tamanho_m": [p.tela.larg_m, p.tela.alt_m],
                      "id0": p.id0, "padrao": p.descricao()})
    d = {"versao": 1, "data": time.strftime("%Y-%m-%d %H:%M:%S"), "telas": telas}
    if extra:
        d.update(extra)
    return d


def de_json(dados):
    """Reconstroi os Padroes de um padroes.json, conferindo que batem.

    O tabuleiro e deterministico dada a resolucao, o id0 e o quadrado, entao
    reconstruir e refazer a mesma conta. A conferencia pega um padroes.json de
    outra versao deste arquivo (layout diferente), que daria cantos trocados.
    """
    padroes = []
    for d in dados["telas"]:
        (px_w, px_h), (w_m, h_m) = d["resolucao_px"], d["tamanho_m"]
        desc = d["padrao"]
        p = Padrao(Tela(d["nome"], int(px_w), int(px_h), float(w_m), float(h_m)),
                   int(d["id0"]), quad_px=int(desc["quad_px"]),
                   dicionario=int(desc["dicionario"]))
        nova = p.descricao()
        for k in ("cols", "rows", "off_px", "marcador_px", "n_cantos"):
            if nova[k] != desc[k]:
                raise ValueError(f"padroes.json: o padrao da tela {d['nome']!r} nao bate "
                                 f"com este codigo ({k}: {desc[k]} != {nova[k]}). "
                                 "Rode de novo o calibrar_telas.py mostrar e tire as "
                                 "fotos de novo.")
        padroes.append(p)
    return padroes


# ------------------------------------------------------------------- validacao
def _detectar_cantos(img, padrao):
    det = cv2.aruco.CharucoDetector(padrao.board)
    ch, chid, _, _ = det.detectBoard(img)
    if chid is None:
        return np.zeros(0, int), np.zeros((0, 2))
    return chid.ravel(), ch.reshape(-1, 2)


def validar(verbose=True):
    """Confere a convencao detectando os cantos nas proprias imagens geradas.

    Tres testes:
      1. cada padrao sozinho, nitido e com desfoque gaussiano: erro maximo entre
         canto detectado e pixels_cantos() (meta < 0.1 px);
      2. os dois padroes lado a lado na MESMA imagem, cada um detectado pelo
         CharucoDetector do seu board: o detector de A tem de ignorar os
         marcadores de B (ids fora do board) e vice-versa;
      3. o tabuleiro par no desenho legacy, detectado com board nao-legacy: mostra
         o que acontece quando as convencoes se misturam.
    Devolve o maior erro encontrado nos testes 1 e 2.
    """
    pad = padroes_projeto()
    pior = 0.0
    for p in pad:
        img = p.imagem()
        for sigma in (0.0, 1.0, 2.0):
            im = img if sigma == 0 else cv2.GaussianBlur(img, (0, 0), sigma)
            ids, uv = _detectar_cantos(im, p)
            err = np.abs(uv - p.pixels_cantos(ids)).max() if len(ids) else np.inf
            pior = max(pior, err)
            if verbose:
                print(f"[1] {p.tela.nome:9s} sigma={sigma:.0f}: {len(ids)}/{p.n_cantos} cantos, "
                      f"erro max {err:.4f} px")

    # 2. lado a lado, B reduzida a metade para caber
    a, b = pad[0].imagem(), pad[1].imagem()
    b2 = cv2.resize(b, (b.shape[1] // 2, b.shape[0] // 2), interpolation=cv2.INTER_AREA)
    canvas = np.full((1200, a.shape[1] + b2.shape[1] + 100), 255, np.uint8)
    canvas[60:60 + a.shape[0], 0:a.shape[1]] = a
    x0 = a.shape[1] + 100
    canvas[60:60 + b2.shape[0], x0:x0 + b2.shape[1]] = b2
    for p, (dx, dy, s) in zip(pad, [(0, 60, 1.0), (x0, 60, 0.5)]):
        ids, uv = _detectar_cantos(canvas, p)
        esperado = (p.pixels_cantos(ids) + 0.5) * s - 0.5 + [dx, dy]
        err = np.abs(uv - esperado).max() if len(ids) else np.inf
        pior = max(pior, err)
        if verbose:
            print(f"[2] {p.tela.nome:9s} na imagem com as duas: {len(ids)}/{p.n_cantos} cantos, "
                  f"erro max {err:.4f} px")

    # 3. mistura de convencoes num tabuleiro com linhas PARES
    dic = cv2.aruco.getPredefinedDictionary(DICIONARIO)
    q = QUAD_PX
    bl = cv2.aruco.CharucoBoard((13, 6), float(q), 0.7 * q, dic)
    bl.setLegacyPattern(True)
    img = cv2.copyMakeBorder(bl.generateImage((13 * q, 6 * q)), 50, 50, 50, 50,
                             cv2.BORDER_CONSTANT, value=255)
    bn = cv2.aruco.CharucoBoard((13, 6), float(q), 0.7 * q, dic)
    bn.setLegacyPattern(False)
    ch, chid, mc, mid = cv2.aruco.CharucoDetector(bn).detectBoard(img)
    n = 0 if chid is None else len(chid)
    if verbose:
        print(f"[3] tabuleiro 13x6 desenhado legacy, detectado nao-legacy: {n}/{12 * 5} cantos "
              f"({0 if mid is None else len(mid)} marcadores lidos)")
    return pior


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--validar", action="store_true")
    args = ap.parse_args()
    pad = padroes_projeto()
    for p in pad:
        d = p.descricao()
        print(f"{p.tela.nome}: {p.tela.px_w}x{p.tela.px_h} px, {p.tela.larg_m:.4f}x"
              f"{p.tela.alt_m:.4f} m, quadrado {p.quad_px} px = "
              f"{p.quad_px * p.tela.larg_m / p.tela.px_w * 1000:.1f} mm, tabuleiro "
              f"{d['cols']}x{d['rows']}, {d['n_cantos']} cantos, marcadores "
              f"{p.id0}..{p.id_fim - 1}")
    if args.validar:
        print(f"OpenCV {cv2.__version__}: pior erro {validar():.4f} px")
    else:
        for p in pad:
            nome = f"padrao_{p.tela.nome}.png"
            cv2.imwrite(nome, p.imagem())
            print("gravado", nome)


if __name__ == "__main__":
    main()
