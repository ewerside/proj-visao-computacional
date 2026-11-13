"""Cena de duas telas "planeta": um gigante gasoso com aneis atras da juncao.

Pensada para as telas em "V" aberto para quem assiste. O planeta fica atras do
vao entre as duas telas, entao cada tela mostra uma metade dele: so parece UMA
esfera redonda, com aneis continuos, se a pose do monitor estiver certa. E a
mesma conferencia da cena alinhamento, so que com um objeto que impressiona.

O que se move:
  - o planeta gira (uma mancha e as faixas deixam a rotacao visivel);
  - duas luas em orbitas inclinadas, que passam de uma tela para a outra, por
    tras e pela frente do planeta;
  - um cinturao de pedras alem dos aneis;
  - as estrelas ficam bem ao fundo: ao mexer a cabeca elas quase nao se deslocam
    em relacao as luas, e essa paralaxe e que da a escala da cena.

Tudo e construido nas coordenadas da SALA do janelas.py (a = direita, h = cima
pela gravidade, d = para quem olha) e levado ao mundo no final, entao o "para
cima" da cena e o da mesa de verdade, mesmo com a tampa do notebook inclinada.
"""

import numpy as np

import janelas
import scene as scn

RAIO = 0.150
ATRAS = 0.52              # centro do planeta atras da juncao, em metros
FAIXAS = [(150, 185, 228), (112, 150, 212), (168, 204, 238), (96, 128, 196),
          (140, 176, 224), (118, 152, 208), (160, 196, 232), (104, 136, 200)]
MANCHA = (70, 90, 200)
ANEL = [(196, 214, 232), (150, 170, 196)]
LUAS = [(0.345, 0.050, 0.55, 0.35, (200, 200, 208)),      # raio da orbita, raio, vel, fase, cor
        (0.470, 0.032, -0.33, 2.10, (150, 190, 170))]
PEDRA = (120, 124, 134)
ESTRELAS = [(235, 235, 235), (200, 215, 255), (255, 225, 200)]
N_LAT, N_LON = 8, 14


def _centro(g):
    """Centro do planeta: ATRAS metros alem da juncao, na linha de visada do
    olho tipico ate o meio do vao, para ele aparecer centrado na juncao."""
    E = g.olho
    Jm = np.array([g.J[0], (g.h_piso + g.h_teto) / 2, g.J[2]])
    s = (E[2] - (Jm[2] - ATRAS)) / max(E[2] - Jm[2], 1e-6)
    return E + s * (Jm - E)


def _rot(v, eixo_x, eixo_z):
    """Inclina o plano da orbita: gira em torno de a (x) e depois de d (z)."""
    c, s = np.cos(eixo_x), np.sin(eixo_x)
    v = v @ np.array([[1, 0, 0], [0, c, -s], [0, s, c]]).T
    c, s = np.cos(eixo_z), np.sin(eixo_z)
    return v @ np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]).T


def _esfera(centro, raio, giro, cores, n_lat=N_LAT, n_lon=N_LON, mancha=None):
    """Esfera em faixas de latitude; devolve faces com normal (sombreadas)."""
    lat = np.linspace(-np.pi / 2, np.pi / 2, n_lat + 1)
    lon = np.linspace(0, 2 * np.pi, n_lon, endpoint=False) + giro
    aneis = [np.stack([raio * np.cos(b) * np.cos(lon), np.full(n_lon, raio * np.sin(b)),
                       raio * np.cos(b) * np.sin(lon)], axis=1) + centro for b in lat]
    faces = []
    for k in range(n_lat):
        a, b = aneis[k], aneis[k + 1]
        for i in range(n_lon):
            j = (i + 1) % n_lon
            if k == 0:
                pts = [a[i], b[j], b[i]]
            elif k == n_lat - 1:
                pts = [a[i], a[j], b[i]]
            else:
                pts = [a[i], a[j], b[j], b[i]]
            cor = cores[k % len(cores)]
            if mancha is not None and k == n_lat // 2 - 1 and i in (0, 1):
                cor = mancha
            faces.append(scn._face(pts, cor, dentro=centro))
    return faces


def _aneis(centro):
    n = 30
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    objs = []
    for (r0, r1), cor in zip(((1.38, 1.72), (1.78, 2.12)), ANEL):
        dentro = np.stack([r0 * RAIO * np.cos(ang), np.zeros(n), r0 * RAIO * np.sin(ang)], 1)
        fora = np.stack([r1 * RAIO * np.cos(ang), np.zeros(n), r1 * RAIO * np.sin(ang)], 1)
        dentro, fora = _rot(dentro, 0.36, 0.20) + centro, _rot(fora, 0.36, 0.20) + centro
        for i in range(n):
            j = (i + 1) % n
            objs.append(scn._poly([dentro[i], dentro[j], fora[j], fora[i]], cor, th=1,
                                  fill=cor))
    return objs


def _estrelas(g, centro):
    rng = np.random.RandomState(11)
    objs = []
    d = centro[2] - 1.10
    for i in range(110):
        a = centro[0] + (rng.rand() - 0.5) * 3.6
        h = centro[1] + (rng.rand() - 0.5) * 1.9
        s = 0.004 + 0.006 * rng.rand()
        cor = ESTRELAS[i % len(ESTRELAS)]
        objs.append(scn._seg((a - s, h, d), (a + s, h, d), cor, 2))
        if i % 4 == 0:
            objs.append(scn._seg((a, h - s, d), (a, h + s, d), cor, 2))
    return objs


def build(telas):
    """Parte estatica: estrelas e aneis, ja no mundo."""
    g = janelas.geometria(telas)
    c = _centro(g)
    return janelas._para_mundo(_estrelas(g, c) + _aneis(c), g)


def dinamico(t, telas):
    """Planeta girando, luas e cinturao, reconstruidos a cada quadro."""
    g = janelas.geometria(telas)
    c = _centro(g)
    objs = _esfera(c, RAIO, 0.25 * t, FAIXAS, mancha=MANCHA)
    for k, (r, raio, vel, fase, cor) in enumerate(LUAS):
        a = fase + vel * t
        p = _rot(np.array([[r * np.cos(a), 0.0, r * np.sin(a)]]),
                 0.36 + 0.22 * (k - 0.5), 0.20 - 0.5 * k)[0] + c
        objs += _esfera(p, raio, 0.6 * t, [cor, tuple(0.82 * x for x in cor)], 5, 9)
    for i in range(14):
        a = i * 2.399963 + 0.12 * t
        r = (2.45 + 0.35 * ((i * 0.618034) % 1.0)) * RAIO
        p = _rot(np.array([[r * np.cos(a), 0.012 * np.sin(i * 1.7), r * np.sin(a)]]),
                 0.36, 0.20)[0] + c
        v = scn._OCTA * (0.006 + 0.004 * (i % 3)) + p
        v = (v - p) @ np.array([[np.cos(t + i), 0, np.sin(t + i)], [0, 1, 0],
                                [-np.sin(t + i), 0, np.cos(t + i)]]).T + p
        objs += [scn._face(v[list(f)], PEDRA, dentro=p) for f in scn._OCTA_F]
    return janelas._para_mundo(objs, g)
