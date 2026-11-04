"""Cenarios do MUNDO compartilhado: um espaco so, atras de todas as telas.

Os cenarios do AP1 sao uma caixa por tela, com a boca pregada no bezel dela.
Estes vivem no referencial do mundo (a tela do notebook) e cada tela mostra o
pedaco que esta atras dela, pela regra do portal de telas.render_tela. O bezel
e o vao entre as telas viram a parede entre duas janelas da mesma sala.

Tudo e posicionado a partir das telas calibradas (juncao, cantos), entao o
cenario continua bem enquadrado para qualquer pose que a calibracao devolver.

  sala         casca de sala (chao, paredes, teto em grade), cubos atravessando
               a juncao, um cubo que anda de uma tela para a outra e tres
               varetas retas cruzando o bezel.
  alinhamento  so varetas retas em tres profundidades, sobre preto. E o padrao
               de teste: se a pose estiver certa, cada vareta parece UMA reta
               continua atravessando o bezel, vista da posicao do olho.
"""

import numpy as np

import scene as scn

CENAS_MUNDO = ["sala", "alinhamento"]

GRADE_SALA = (110, 95, 80)
GRADE_CHAO = (90, 120, 95)
# Varetas: cores saturadas e distintas, uma por profundidade no alinhamento.
VARETAS = [(255, 255, 255), (0, 220, 255), (255, 110, 255),
           (255, 220, 0), (90, 255, 90), (0, 140, 255)]

OLHO_NOMINAL = np.array([0.0, 0.0, 0.60])


def _casca(seg):
    """Marca o segmento como casca: desenhado antes de tudo, sem ordenar."""
    seg["camada"] = 0
    return seg


def _grade(c00, c10, c11, c01, nu, nv, cor):
    """Grade plana com nu divisoes de c00 a c10 e nv de c00 a c01."""
    c00, c10, c11, c01 = (np.asarray(c, float) for c in (c00, c10, c11, c01))
    segs = []
    for i in range(nu + 1):
        s = i / nu
        segs.append(_casca(scn._seg(c00 + (c10 - c00) * s, c01 + (c11 - c01) * s, cor)))
    for j in range(nv + 1):
        s = j / nv
        segs.append(_casca(scn._seg(c00 + (c01 - c00) * s, c10 + (c11 - c10) * s, cor)))
    return segs


def _n(comprimento, passo):
    return max(1, int(round(comprimento / passo)))


def limites(telas):
    """Caixa da sala no mundo, a partir dos cantos de todas as telas."""
    cantos = np.vstack([tl.cantos_mundo() for tl in telas])
    x0, x1 = cantos[:, 0].min() - 0.55, cantos[:, 0].max() + 0.55
    y0, y1 = cantos[:, 1].min() - 0.03, cantos[:, 1].max() + 0.20
    z0, z1 = -1.20, cantos[:, 2].max() + 0.35
    return x0, x1, y0, y1, z0, z1


def juncao(telas):
    """Ponto no meio do vao entre as duas primeiras telas, no mundo.

    Pega a borda vertical de cada tela mais proxima da outra e devolve o ponto
    medio entre os pontos medios dessas bordas. Com uma tela so, o centro dela.
    """
    if len(telas) < 2:
        return telas[0].t.copy()
    bordas = []
    for tl in telas[:2]:
        w = tl.w_m / 2
        bordas.append(tl.para_mundo(np.array([(-w, 0.0, 0.0), (w, 0.0, 0.0)])))
    d = [(np.linalg.norm(a - b), a, b) for a in bordas[0] for b in bordas[1]]
    _dist, a, b = min(d, key=lambda item: item[0])
    return (a + b) / 2


def _atras_da_juncao(telas, k):
    """Ponto a k metros alem da juncao, na direcao olho nominal -> juncao."""
    j = juncao(telas)
    d = j - OLHO_NOMINAL
    return j + d / np.linalg.norm(d) * k


def _vareta(p0, p1, cor, pedacos=1, th=2):
    """Vareta reta de p0 a p1. Em pedacos, para o pintor ordenar localmente."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    objs = []
    for i in range(pedacos):
        a = p0 + (p1 - p0) * (i / pedacos)
        b = p0 + (p1 - p0) * ((i + 1) / pedacos)
        o = scn._seg(a, b, cor, th)
        o["vareta"] = True
        objs.append(o)
    return objs


def _pilar(base_xz, y_piso, altura, largura, cor, giro=0.0):
    v = scn._rot_y(scn._verts_caixa(largura, altura, largura), giro)
    return scn._solido_caixa(v + np.array([base_xz[0], y_piso + altura / 2, base_xz[1]]), cor)


def build_sala(telas):
    x0, x1, y0, y1, z0, z1 = limites(telas)
    objs = []
    # Casca: chao, fundo, paredes e teto. Grade de ~10 cm.
    objs += _grade((x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0),
                   _n(x1 - x0, 0.10), _n(z1 - z0, 0.10), GRADE_CHAO)        # chao
    objs += _grade((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                   _n(x1 - x0, 0.10), _n(y1 - y0, 0.10), GRADE_SALA)        # fundo
    objs += _grade((x0, y0, z1), (x0, y0, z0), (x0, y1, z0), (x0, y1, z1),
                   _n(z1 - z0, 0.10), _n(y1 - y0, 0.10), GRADE_SALA)        # esquerda
    objs += _grade((x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0),
                   _n(z1 - z0, 0.10), _n(y1 - y0, 0.10), GRADE_SALA)        # direita
    objs += _grade((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1),
                   _n(x1 - x0, 0.10), _n(z1 - z0, 0.10), GRADE_SALA)        # teto

    # Cubos atravessando a juncao: vistos do olho nominal, metade em cada tela.
    c1 = _atras_da_juncao(telas, 0.22)
    c2 = _atras_da_juncao(telas, 0.50)
    objs += scn._cubo(c1, 0.07, scn.CUBES[0][0], 0.25, 0.35)
    objs += scn._cubo(c2, 0.10, scn.CUBES[1][0], -0.15, -0.30)
    p3 = _atras_da_juncao(telas, 0.85)
    objs += _pilar((p3[0], p3[2]), y0, 0.30, 0.08, scn.CUBES[2][0], 0.4)
    # Pilares de referencia, um atras de cada tela.
    objs += _pilar((x0 + 0.40, -0.65), y0, 0.25, 0.06, (150, 150, 150), 0.2)
    objs += _pilar((x1 - 0.35, -0.35), y0, 0.25, 0.06, (150, 150, 150), -0.3)

    # Varetas cruzando a juncao, na frente dos cubos.
    objs += _vareta((x0 + 0.30, -0.05, -0.10), (x1 - 0.10, -0.05, -0.10), VARETAS[0], 8)
    objs += _vareta((x0 + 0.30, 0.07, -0.35), (x1 - 0.10, 0.07, -0.35), VARETAS[1], 8)
    objs += _vareta((x0 + 0.30, -0.10, -0.15), (x1 - 0.10, 0.15, -0.60), VARETAS[2], 8)
    return objs


def dinamico_sala(t, telas):
    """Um cubo que vai e volta de tras de uma tela para tras da outra."""
    j = juncao(telas)
    s = np.sin(t * 0.45)
    centro = np.array([j[0] + 0.30 * s, -0.02, -0.40 + 0.05 * np.cos(t * 0.45)])
    return scn._cubo(centro, 0.06, (60, 200, 255), 0.4 * t, 0.7 * t)


def varetas_alinhamento(telas):
    """As varetas do padrao de teste, como pares (p0, p1, cor), no mundo.

    Tres profundidades. Em cada uma, tres horizontais e duas diagonais, com o
    espalhamento vertical crescendo com a profundidade para continuarem dentro
    do campo de visao das telas.
    """
    x0, x1, _y0, _y1, _z0, _z1 = limites(telas)
    xa, xb = x0 + 0.25, x1 - 0.05
    varetas = []
    for k, z in enumerate([-0.02, -0.30, -0.90]):
        abre = (OLHO_NOMINAL[2] - z) / OLHO_NOMINAL[2]
        cor = VARETAS[k]
        for y in (-0.06, 0.0, 0.06):
            varetas.append(((xa, y * abre, z), (xb, y * abre, z), cor))
        varetas.append(((xa, -0.08 * abre, z), (xb, 0.08 * abre, z), VARETAS[3 + k]))
        varetas.append(((xa, 0.08 * abre, z), (xb, -0.08 * abre, z), VARETAS[3 + k]))
    return varetas


def build_alinhamento(telas):
    x0, x1, y0, _y1, z0, z1 = limites(telas)
    objs = _grade((x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0),
                  _n(x1 - x0, 0.20), _n(z1 - z0, 0.20), (70, 70, 70))
    for p0, p1, cor in varetas_alinhamento(telas):
        objs += _vareta(p0, p1, cor, 1, th=2)
    return objs


def build(nome, telas):
    if nome == "sala":
        return build_sala(telas)
    return build_alinhamento(telas)


def dinamico(nome, t, telas):
    if nome == "sala":
        return dinamico_sala(t, telas)
    return []
