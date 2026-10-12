"""Geometria da cena e projecao off-axis, tudo em numpy."""

import numpy as np

import config

# Cores BGR, sobrias e de alto contraste sobre fundo preto.
WALL = (150, 130, 105)        # azul acinzentado frio
WALL_BACK = (200, 180, 150)   # fundo um pouco mais claro, ajuda a ler a profundidade
CUBES = [
    ((0.0, 165, 255), "ambar"),
    ((170, 190, 60), "verde-agua"),
    ((130, 110, 235), "rosa"),
]


def _seg(a, b, color, th=1):
    return {"kind": "seg", "v": np.array([a, b], float), "color": color, "th": th}


def _poly(verts, color, th=2, fill=None):
    """fill=None escurece a propria cor; passe uma cor para preenchimento cheio."""
    return {"kind": "poly", "v": np.array(verts, float), "color": color,
            "th": th, "fill": fill}


def wall_grid(c00, c10, c11, c01, n, color):
    """Grid de linhas numa parede plana definida por 4 cantos, em ordem.

    Interpolacao bilinear entre os cantos: n+1 linhas em cada direcao. O grid e
    o que vende a ilusao, porque da ao olho referencia de perspectiva. Sem ele
    uma parede lisa nao tem como revelar que esta inclinada.
    """
    c00, c10, c11, c01 = (np.array(c, float) for c in (c00, c10, c11, c01))
    segs = []
    for i in range(n + 1):
        s = i / n
        segs.append(_seg(c00 + (c10 - c00) * s, c01 + (c11 - c01) * s, color))
        segs.append(_seg(c00 + (c01 - c00) * s, c10 + (c11 - c10) * s, color))
    return segs


def make_room(d=None, n=None, com_fundo=True):
    """A caixa: frente aberta no plano da tela, fundo em -d, 4 paredes.

    Esta e a concha que TODOS os cenarios usam, e a razao e a unica coisa que faz
    a ilusao funcionar: a boca em z=0 tem exatamente as dimensoes da tela, entao
    projeta em si mesma (t=1) para qualquer posicao do olho. As bordas ficam
    pregadas no bezel do notebook, e o bezel fisico vira a moldura da janela.

    Cenario que flutua sem nada em z=0 nao tem essa ancora: a imagem inteira
    desliza junto com a cabeca, e deslizar numa tela plana le como figura
    escorregando, nao como janela.
    """
    w, h = config.SCREEN_W / 2, config.SCREEN_H / 2
    d = config.BOX_DEPTH if d is None else d
    n = config.GRID_N if n is None else n

    # Cantos da boca (z=0) e do fundo (z=-d). Ordem: inf-esq, inf-dir, sup-dir, sup-esq.
    f = [(-w, -h, 0.0), (w, -h, 0.0), (w, h, 0.0), (-w, h, 0.0)]
    b = [(-w, -h, -d), (w, -h, -d), (w, h, -d), (-w, h, -d)]

    segs = []
    if com_fundo:
        segs += wall_grid(b[0], b[1], b[2], b[3], n, WALL_BACK)    # fundo
    segs += wall_grid(f[0], b[0], b[3], f[3], n, WALL)             # parede esquerda
    segs += wall_grid(f[1], b[1], b[2], f[2], n, WALL)             # parede direita
    segs += wall_grid(f[0], f[1], b[1], b[0], n, WALL)             # chao
    segs += wall_grid(f[3], f[2], b[2], b[3], n, WALL)             # teto
    return segs


def make_cube(center, size, color):
    """Cubo solido: 6 faces preenchidas com aresta destacada."""
    cx, cy, cz = center
    r = size / 2
    v = np.array([[cx - r, cy - r, cz - r], [cx + r, cy - r, cz - r],
                  [cx + r, cy + r, cz - r], [cx - r, cy + r, cz - r],
                  [cx - r, cy - r, cz + r], [cx + r, cy - r, cz + r],
                  [cx + r, cy + r, cz + r], [cx - r, cy + r, cz + r]])
    faces = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)]
    return [_poly(v[list(f)], color) for f in faces]


def build_caixa():
    """A cena inteira: a caixa mais tres cubos flutuando em profundidades diferentes."""
    scene = make_room()
    d = config.BOX_DEPTH
    # Os tres numeros sao FRACOES da profundidade da caixa: 22%, 52% e 84%.
    # Antes eles vinham multiplicados por d/0.5, o que dobrava a fracao e punha
    # dois dos cubos atras da parede do fundo (a -104% e -168% da profundidade).
    # Em mono isso quase nao aparece, porque o fundo e um grid vazado e cubo
    # atras dele ainda se ve. Em estereo aparece na hora: era o cubo de tras que
    # sozinho definia a paralaxe maxima da cena.
    posicoes = [((-0.075, 0.035, -0.22 * d), 0.048),
                ((0.085, -0.030, -0.52 * d), 0.056),
                ((-0.020, -0.055, -0.84 * d), 0.042)]
    for (centro, lado), (cor, _nome) in zip(posicoes, CUBES):
        scene += make_cube(centro, lado, cor)
    return scene


def project(P, eye, px_w, px_h):
    """Projeta pontos 3D no plano da tela e converte para pixels.

    P: (N,3) em metros, referencial da tela. eye: (3,). Retorna (N,2) em pixels.

    A projecao e a intersecao do raio olho->P com o plano z=0:

        t = eye.z / (eye.z - P.z)
        x_tela = eye.x + t * (P.x - eye.x)

    Isso e matematicamente equivalente ao frustum assimetrico de Kooima (2008),
    mas derivado direto do modelo pinhole: o olho e o centro de projecao e a
    propria tela e o plano de imagem. Nao ha matriz de projecao nem espaco de
    recorte porque nao precisamos deles: projetamos no plano fisico e ja saimos
    em pixels. E a mesma geometria da camera de furo do tracking, invertida.
    """
    P = np.asarray(P, float)
    t = eye[2] / (eye[2] - P[:, 2])
    x = eye[0] + t * (P[:, 0] - eye[0])
    y = eye[1] + t * (P[:, 1] - eye[1])

    px = (x / config.SCREEN_W + 0.5) * px_w
    py = (0.5 - y / config.SCREEN_H) * px_h
    return np.stack([px, py], axis=1)


def z_minimo(objs):
    """Profundidade do vertice mais fundo. E o pior caso de paralaxe."""
    return min((float(o["v"][:, 2].min()) for o in objs), default=0.0)


def paralaxe_px(eye, z_min, px_w, theta=0.0, escala=None):
    """Maior disparidade horizontal entre os dois olhos, em pixels.

    Nao precisa projetar a cena duas vezes para achar isso. Subtraindo as duas
    projecoes de um mesmo ponto, tudo que depende de x e y se cancela e sobra um
    termo que so depende da PROFUNDIDADE:

        x = (1 - t) * eye.x + t * P.x,   t = eye.z / (eye.z - P.z)
        dx = x_R - x_L = (1 - t) * (eye_R.x - eye_L.x)
           = 2 * meia * cos(theta) * (-P.z) / (eye.z - P.z)

    Cresce monotonicamente com a profundidade, entao o pior caso e sempre o
    vertice mais fundo e o resto da cena nao importa. Em z=0 da exatamente zero,
    que e o plano de paralaxe nula.

    Usa a cena inteira, inclusive o que o culling descartou: e o limite
    geometrico da cena, nao do quadro, e e assim que ele serve para decidir
    BOX_DEPTH ou STEREO_SCALE.
    """
    escala = config.STEREO_SCALE if escala is None else escala
    meia = (config.IPD_REAL / 2.0) * escala
    dx = 2.0 * meia * np.cos(theta) * (-z_min) / (eye[2] - z_min)
    return abs(dx) / config.SCREEN_W * px_w


def escala_confortavel(eye, z_min, max_deg=None):
    """Separacao interocular que deixa a cena inteira dentro do limite de fusao,
    como fracao da IPD real. E o valor do STEREO_AUTO.

    Duas imagens so fundem enquanto a disparidade entre elas cabe na area de
    Panum, da ordem de 1 grau. Esse limite e ANGULAR, entao em milimetros de
    tela ele encolhe conforme voce se aproxima: e por isso que a escala nao pode
    ser constante, e por isso que ela sai daqui e nao do config.

    Basta igualar a paralaxe do ponto mais fundo ao limite e isolar a separacao:

        p_max  = eye.z * tan(max_deg)                    limite, em metros
        p      = 2 * meia * (-z_min) / (eye.z - z_min)   paralaxe do mais fundo
        meia   = p_max * (eye.z - z_min) / (2 * (-z_min))

    O teto de 1.0 e proposital: esta funcao existe para ATENUAR o estereo ate o
    fusionavel, nunca para exagera-lo alem do geometricamente correto. Cena rasa
    o bastante ja cabe no limite, e ai ela devolve 1.0 e nao mexe em nada.
    """
    max_deg = config.STEREO_MAX_DISPARITY_DEG if max_deg is None else max_deg
    if z_min >= 0.0:
        return 1.0
    p_max = eye[2] * np.tan(np.radians(max_deg))
    meia = p_max * (eye[2] - z_min) / (2.0 * (-z_min))
    return min(1.0, meia / (config.IPD_REAL / 2.0))


class _PaletaNeutra(dict):
    """Mapa cor -> cor neutra. O que nao esta no mapa vira sua luminancia.

    Cache: a luminancia de cada cor nova e calculada uma vez e guardada, entao
    cenario com centenas de cores nao paga nada por quadro.
    """

    def __missing__(self, cor):
        y = round(0.114 * cor[0] + 0.587 * cor[1] + 0.299 * cor[2])
        self[cor] = neutro = (y, y, y)
        return neutro


def paleta_neutra():
    """A paleta do config aplicada as cores desta cena. Ver ANAGLYPH_PALETTE."""
    p = config.ANAGLYPH_PALETTE
    mapa = _PaletaNeutra({WALL: p["grid"], WALL_BACK: p["grid_fundo"]})
    for (cor, _nome), neutro in zip(CUBES, p["objetos"]):
        mapa[cor] = neutro
    return mapa


def stereo_eyes(eye_c, theta=0.0, escala=None):
    """Os dois olhos, como TRANSLACOES puras do olho ciclopico.

    `theta` e a rolagem da cabeca em radianos, medida em outro lugar; 0 deixa o
    eixo interocular na horizontal da tela. `escala` multiplica a separacao;
    None usa config.STEREO_SCALE.

        meia = (IPD_REAL / 2) * escala
        d    = (cos(theta), sin(theta), 0)
        eye_L = eye_c - meia * d        eye_R = eye_c + meia * d

    Translacao pura, nunca toe-in. Convergir as duas camaras num ponto parece a
    coisa natural a fazer, e e o erro classico: girar a camara inclina o plano
    de imagem de cada olho, e dois planos de imagem inclinados em sentidos
    opostos jogam pontos correspondentes em ALTURAS diferentes. Paralaxe
    vertical o sistema visual nao funde, so acumula fadiga.

    Aqui nao ha nem tentacao de fazer isso, porque nao existe camara para girar:
    o plano de imagem e a tela fisica, ele e o mesmo para os dois olhos e nao se
    mexe. A assimetria de frustum que o toe-in tenta imitar sai sozinha da
    projecao off-axis, e sai certa.
    """
    escala = config.STEREO_SCALE if escala is None else escala
    meia = (config.IPD_REAL / 2.0) * escala
    d = np.array([np.cos(theta), np.sin(theta), 0.0]) * meia
    eye_c = np.asarray(eye_c, float)
    return eye_c - d, eye_c + d


def order_faces(scene, eye):
    """Ordena a cena para o painter's algorithm: de tras para frente.

    Devolve a lista de objetos ja filtrada e ordenada, pronta para o render.

    Esta etapa e separada do desenho de proposito. Em estereo a ordem tem que
    ser calculada UMA vez, com o olho ciclopico, e servir aos dois olhos: se
    cada olho ordenasse por conta propria, as duas imagens poderiam discordar
    sobre qual face esta na frente, e o cerebro nao funde. Isso e rivalidade
    binocular, e o sintoma nao e um erro visivel na tela, e desconforto.

    A ordenacao usa a distancia ao OLHO, nao a profundidade em z. Com o olho
    fora do eixo as duas discordam, e a distancia ao olho e a correta.

    Os dois descartes que dependem do olho tambem moram aqui:
      - o que estiver atras do olho, que a projecao nao sabe tratar;
      - back-face culling: a face some se a normal aponta para longe do olho.
        Corta quase metade do trabalho num solido fechado e ainda elimina os
        artefatos do painter's algorithm entre faces do mesmo objeto.
    """
    eye = np.asarray(eye, float)

    ordenado = []
    for obj in scene:
        v = obj["v"]
        # Descarta o que estiver atras do olho. Com o olho em z>0 e a cena em
        # z<=0 isso nunca dispara, mas uma falha de tracking pode inverter.
        if np.any(v[:, 2] >= eye[2]):
            continue
        centro = v.mean(axis=0)
        n = obj.get("n")
        if n is not None and obj.get("cull", True) and np.dot(n, eye - centro) <= 0:
            continue
        ordenado.append((np.linalg.norm(v - eye, axis=1).mean(), obj))
    ordenado.sort(key=lambda item: -item[0])
    return [obj for _dist, obj in ordenado]


def render(eye, face_order, out, fundo=None, paleta=None):
    """Desenha em `out` a cena ja ordenada, vista de `eye`. So a cena.

    Sem HUD, sem overlay, sem estado: mesma entrada, mesma imagem. E o que
    permite chamar esta funcao duas vezes por quadro, uma por olho, e compor o
    resultado depois.

    `out` e o canvas de destino, reaproveitado entre quadros (alocar os 6 MB por
    quadro custava 13 ms, tanto quanto desenhar a cena inteira) e e dele que sai
    o tamanho em pixels. `fundo` e a imagem de fundo do cenario; None preenche
    de preto. `paleta` troca as cores na hora de desenhar, sem tocar na
    geometria; None desenha com as cores da propria cena. Retorna o proprio
    `out`, por conveniencia.

    Faces que trazem normal ("n") ganham flat shading: a cor e modulada pelo
    cosseno entre a normal e a direcao da luz. E o unico calculo de iluminacao
    do projeto, e e por face, nao por pixel: uma multiplicacao de cor, nada de
    raster de sombra. Repare que ele NAO depende do olho, so da normal, entao os
    dois olhos veem exatamente a mesma cor em cada face, como tem que ser.
    """
    import cv2

    px_h, px_w = out.shape[:2]
    eye = np.asarray(eye, float)
    if fundo is None:
        out[:] = 0
    else:
        np.copyto(out, fundo)

    for obj in face_order:
        pts = project(obj["v"], eye, px_w, px_h).astype(np.int32)
        cor_obj = obj["color"] if paleta is None else paleta[obj["color"]]
        if obj["kind"] == "seg":
            cv2.line(out, tuple(pts[0]), tuple(pts[1]), cor_obj, obj["th"],
                     cv2.LINE_AA)
            continue

        n = obj.get("n")
        if n is not None:
            # Aresta na mesma cor do preenchimento: fecha a costura que o
            # antialias deixa entre faces vizinhas, e da o acabamento liso de
            # low poly em vez de wireframe colorido.
            cor = sombrear(cor_obj, n)
            cv2.fillPoly(out, [pts], cor, cv2.LINE_AA)
            cv2.polylines(out, [pts], True, cor, 1, cv2.LINE_AA)
        else:
            fill = obj.get("fill")
            if not fill:
                fill = tuple(c * 0.30 for c in cor_obj)
            elif paleta is not None:
                fill = paleta[fill]
            cv2.fillPoly(out, [pts], fill, cv2.LINE_AA)
            cv2.polylines(out, [pts], True, cor_obj, obj["th"], cv2.LINE_AA)
    return out


# ---------------------------------------------------------------- corredor ---
#
# Mesma concha da caixa, so que funda e sem parede no fundo. A secao transversal
# continua sendo o retangulo da tela, entao a boca segue pregada no bezel.

TOCHA_SUPORTE = (95, 95, 105)
TOCHA_FORA = (0, 130, 250)       # laranja
TOCHA_DENTRO = (120, 225, 255)   # amarelo palido
TOCHA_HALO = (0, 26, 56)         # laranja quase preto, faz as vezes de brilho


def build_corredor():
    """Caixa funda sem parede no fundo: as linhas convergem e somem no preto."""
    w, h = config.SCREEN_W / 2, config.SCREEN_H / 2
    segs = make_room(d=config.COR_DEPTH, n=config.COR_DIVISOES, com_fundo=False)

    for z_tocha in config.TOCHA_Z:
        for lado in (-1, 1):
            x = lado * (w - 0.002)
            xi = lado * (w - 0.022)
            y = config.TOCHA_Y - 0.008
            segs.append(_poly([(x, y, z_tocha - 0.004), (xi, y, z_tocha - 0.003),
                               (xi, y, z_tocha + 0.003), (x, y, z_tocha + 0.004)],
                              TOCHA_SUPORTE, th=1))
    return segs


# Contorno de chama em coordenadas locais, ponta para cima, altura ~1.
_CHAMA = np.array([(0.0, 1.0), (0.32, 0.34), (0.42, -0.08), (0.16, -0.34),
                   (-0.16, -0.34), (-0.42, -0.08), (-0.32, 0.34)])


def _chama(x, y, z, escala, cor):
    v = [(x + px * escala, y + py * escala, z) for px, py in _CHAMA]
    return _poly(v, cor, th=1, fill=cor)


def tochas_corredor(t):
    """As chamas, reconstruidas a cada frame para tremular.

    O tremor vem da soma de tres senoides de frequencias incomensuraveis, o que
    da um padrao que nunca se repete de forma perceptivel sem precisar de random,
    e portanto continua deterministico e reproduzivel entre execucoes.
    """
    w = config.SCREEN_W / 2
    objs = []
    for i, z_tocha in enumerate(config.TOCHA_Z):
        for j, lado in enumerate((-1, 1)):
            fase = (i * 2 + j) * 1.7
            tremor = (0.10 * np.sin(3.1 * t + fase)
                      + 0.06 * np.sin(5.7 * t + fase * 1.9)
                      + 0.04 * np.sin(9.3 * t + fase * 0.7))
            escala = 0.0062 * (1.0 + tremor)
            x = lado * (w - 0.010)
            y = config.TOCHA_Y
            objs.append(_chama(x, y, z_tocha, escala * 1.9, TOCHA_HALO))
            objs.append(_chama(x, y, z_tocha, escala, TOCHA_FORA))
            objs.append(_chama(x, y - escala * 0.10, z_tocha, escala * 0.55,
                               TOCHA_DENTRO))
    return objs


# --------------------------------------------------------------- miniatura ---
#
# Vilarejo assentado no chao da MESMA caixa. Aqui entram flat shading e sombras,
# que os dois cenarios anteriores nao usam.

LUZ = np.array([-0.5, 0.85, 0.55])
LUZ = LUZ / np.linalg.norm(LUZ)

PISO_A = (44, 74, 52)
PISO_B = (38, 66, 46)
MADEIRA = (58, 88, 130)
PAREDE_CASA = (168, 196, 214)
TELHADO = (58, 66, 172)
FOLHA_A = (72, 142, 76)
FOLHA_B = (60, 122, 66)
TRONCO = (52, 74, 104)
SOMBRA = (22, 38, 28)
PELE = (150, 190, 224)
ROUPAS = [((150, 96, 62), (92, 62, 44)), ((70, 70, 190), (48, 48, 110)),
          ((60, 160, 210), (44, 100, 132))]


def sombrear(cor, normal):
    """Flat shading Lambert com termo ambiente. Uma multiplicacao por face."""
    i = 0.34 + 0.66 * max(0.0, float(np.dot(normal, LUZ)))
    return tuple(min(255.0, c * i) for c in cor)


def _face(pontos, cor, dentro=None, cull=True):
    """Face poligonal com normal.

    Passando "dentro", um ponto no interior do solido, a normal e virada para
    fora automaticamente. Isso dispensa raciocinar sobre a ordem dos vertices em
    cada face, que e a principal fonte de erro silencioso nesse tipo de codigo.
    """
    v = np.array(pontos, float)
    n = np.cross(v[1] - v[0], v[2] - v[0])
    ln = np.linalg.norm(n)
    n = n / ln if ln > 1e-12 else np.array([0.0, 1.0, 0.0])
    if dentro is not None and np.dot(n, v.mean(axis=0) - np.asarray(dentro, float)) < 0:
        n, v = -n, v[::-1]
    return {"kind": "poly", "v": v, "color": cor, "th": 1, "fill": None,
            "n": n, "cull": cull}


_CAIXA_FACES = [(4, 5, 6, 7), (1, 0, 3, 2), (5, 1, 2, 6),
                (0, 4, 7, 3), (7, 6, 2, 3), (0, 1, 5, 4)]


def _verts_caixa(sx, sy, sz):
    x, y, z = sx / 2, sy / 2, sz / 2
    return np.array([(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
                     (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)])


def _solido_caixa(v, cor):
    """Seis faces de uma caixa ja transformada.

    As normais saem das tres arestas da caixa, nao de seis produtos vetoriais.
    Para um solido cujo winding ja e conhecido as duas coisas sao equivalentes,
    e esta custa metade. Vale a pena porque os bonecos sao reconstruidos a cada
    frame.
    """
    ex = v[1] - v[0]
    ey = v[3] - v[0]
    ez = v[4] - v[0]
    ex = ex / np.linalg.norm(ex)
    ey = ey / np.linalg.norm(ey)
    ez = ez / np.linalg.norm(ez)
    normais = (ez, -ez, ex, -ex, ey, -ey)
    return [{"kind": "poly", "v": v[list(f)], "color": cor, "th": 1,
             "fill": None, "n": n, "cull": True}
            for f, n in zip(_CAIXA_FACES, normais)]


def _rot_y(v, ang):
    c, s = np.cos(ang), np.sin(ang)
    return v @ np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]).T


def _rot_x(v, ang):
    c, s = np.cos(ang), np.sin(ang)
    return v @ np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]).T


def _anel(raio, y, n=8, giro=0.0):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False) + giro
    return np.stack([raio * np.cos(a), np.full(n, y), raio * np.sin(a)], axis=1)


# Chao da caixa, onde o vilarejo se assenta.
PISO_Y = -config.SCREEN_H / 2


def _piso():
    """Chao ladrilhado da caixa.

    Ladrilhado, e nao um poligono unico, por causa do algoritmo do pintor: a
    distancia media de um piso inteiro e a do centro dele, entao uma casa no
    fundo ficaria ordenada atras do piso todo e sumiria. Cada ladrilho ordena
    junto do que esta em cima dele.
    """
    w, d = config.SCREEN_W / 2, config.MINI_DEPTH
    nx, nz = 6, 9
    faces = []
    abaixo = np.array([0.0, PISO_Y - 0.05, -d / 2])
    for i in range(nx):
        for k in range(nz):
            x0, x1 = -w + 2 * w * i / nx, -w + 2 * w * (i + 1) / nx
            z0, z1 = -d * k / nz, -d * (k + 1) / nz
            cor = PISO_A if (i + k) % 2 == 0 else PISO_B
            faces.append(_face([(x0, PISO_Y, z0), (x1, PISO_Y, z0),
                                (x1, PISO_Y, z1), (x0, PISO_Y, z1)],
                               cor, dentro=abaixo))
    return faces


def _casa(pos, yaw, largura, alt, prof):
    """Casa: corpo em caixa mais telhado de duas aguas com empenas."""
    v = _rot_y(_verts_caixa(largura, alt, prof), yaw) + pos
    faces = _solido_caixa(v, PAREDE_CASA)

    h_tel = alt * 0.55
    cume = np.array([[0.0, alt / 2 + h_tel, -prof / 2 * 1.05],
                     [0.0, alt / 2 + h_tel, prof / 2 * 1.05]])
    beira = np.array([[-largura / 2 * 1.15, alt / 2, -prof / 2 * 1.05],
                      [largura / 2 * 1.15, alt / 2, -prof / 2 * 1.05],
                      [largura / 2 * 1.15, alt / 2, prof / 2 * 1.05],
                      [-largura / 2 * 1.15, alt / 2, prof / 2 * 1.05]])
    cume = _rot_y(cume, yaw) + pos
    beira = _rot_y(beira, yaw) + pos
    dentro = pos + np.array([0.0, alt * 0.35, 0.0])
    faces.append(_face([beira[0], beira[3], cume[1], cume[0]], TELHADO, dentro=dentro))
    faces.append(_face([beira[1], beira[2], cume[1], cume[0]], TELHADO, dentro=dentro))
    faces.append(_face([beira[0], beira[1], cume[0]], TELHADO, dentro=dentro))
    faces.append(_face([beira[3], beira[2], cume[1]], TELHADO, dentro=dentro))
    return faces


def _arvore(pos, altura):
    """Pinheiro: tronco em caixa e duas saias conicas de seis lados."""
    faces = _solido_caixa(_verts_caixa(0.006, altura * 0.35, 0.006)
                          + pos + np.array([0.0, altura * 0.17, 0.0]), TRONCO)
    for k, (base_y, raio, alt, cor) in enumerate(
            [(0.28, 0.030, 0.33, FOLHA_A), (0.52, 0.022, 0.30, FOLHA_B)]):
        centro = pos + np.array([0.0, altura * base_y, 0.0])
        topo = pos + np.array([0.0, altura * (base_y + alt), 0.0])
        anel = _anel(raio * altura / 0.075, 0.0, 6, giro=k * 0.5) + centro
        for i in range(6):
            faces.append(_face([anel[i], anel[(i + 1) % 6], topo], cor, dentro=centro))
    return faces


def _moinho(pos, yaw):
    """Torre com pas. As pas giram, entao ficam na parte dinamica."""
    v = _rot_y(_verts_caixa(0.026, 0.060, 0.026), yaw) + pos + np.array([0, 0.030, 0])
    faces = _solido_caixa(v, PAREDE_CASA)
    centro = pos + np.array([0.0, 0.060, 0.0])
    topo = pos + np.array([0.0, 0.084, 0.0])
    anel = _anel(0.021, 0.0, 6) + centro
    for i in range(6):
        faces.append(_face([anel[i], anel[(i + 1) % 6], topo], TELHADO, dentro=centro))
    return faces


def _sombra(pos, raio):
    """Mancha de sombra no chao. Poligono chato, sem projecao de luz calculada."""
    v = _anel(raio, 0.0, 8) + np.array([pos[0], PISO_Y + 0.0008, pos[2]])
    return _face(v, SOMBRA, dentro=np.array([pos[0], PISO_Y - 0.05, pos[2]]),
                 cull=False)


def _boneco(base, yaw, fase, cor_roupa, cor_calca):
    """Boneco articulado de seis pecas, com ciclo de caminhada.

    Pernas e bracos balancam em oposicao em torno de quadril e ombro, e o tronco
    sobe e desce no dobro da frequencia do passo. Sao tres senoides ao todo: nao
    e captura de movimento, mas o olho le como andar.
    """
    passo = np.sin(fase) * 0.6
    bob = abs(np.cos(fase)) * 0.0020
    quadril = np.array([0.0, 0.0125 + bob, 0.0])
    ombro = np.array([0.0, 0.0238 + bob, 0.0])

    pecas = [
        (0.0043, 0.0130, 0.0043, (-0.0032, 0.0065 + bob, 0.0), cor_calca, passo, quadril),
        (0.0043, 0.0130, 0.0043, (0.0032, 0.0065 + bob, 0.0), cor_calca, -passo, quadril),
        (0.0104, 0.0121, 0.0069, (0.0, 0.0190 + bob, 0.0), cor_roupa, 0.0, None),
        (0.0035, 0.0112, 0.0035, (-0.0071, 0.0193 + bob, 0.0), cor_roupa, -passo * 0.75, ombro),
        (0.0035, 0.0112, 0.0035, (0.0071, 0.0193 + bob, 0.0), cor_roupa, passo * 0.75, ombro),
        (0.0087, 0.0087, 0.0078, (0.0, 0.0292 + bob, 0.0), PELE, 0.0, None),
    ]
    faces = []
    for sx, sy, sz, centro, cor, ang, pivo in pecas:
        v = _verts_caixa(sx, sy, sz) + np.array(centro)
        if pivo is not None and ang != 0.0:
            v = _rot_x(v - pivo, ang) + pivo
        faces += _solido_caixa(_rot_y(v, yaw) + base, cor)
    return faces


# Bonecos andam em elipses no chao da caixa: raio x, raio z, velocidade, fase.
ORBITAS = [(0.075, 0.105, 0.55, 0.0), (0.115, 0.150, -0.38, 2.2),
           (0.045, 0.062, 0.72, 4.1)]
ORBITA_CENTRO = np.array([0.0, 0.0, -0.30])

_CASAS = [((-0.105, -0.40), 0.5, 0.040, 0.030, 0.034),
          ((0.098, -0.31), -0.9, 0.034, 0.026, 0.030),
          ((0.010, -0.51), 2.4, 0.030, 0.023, 0.028)]
_ARVORES = [((-0.058, -0.19), 0.060), ((0.128, -0.46), 0.050),
            ((-0.140, -0.28), 0.044), ((0.055, -0.55), 0.038)]
_MOINHO = ((0.125, -0.17), -0.6)


def build_miniatura():
    """Vilarejo assentado no chao da caixa padrao."""
    faces = make_room(d=config.MINI_DEPTH, n=config.MINI_DIVISOES)
    faces += _piso()
    for (x, z), yaw, lg, al, pr in _CASAS:
        pos = np.array([x, PISO_Y + al / 2, z])
        faces += _casa(pos, yaw, lg, al, pr)
        faces.append(_sombra((x, 0, z), max(lg, pr) * 0.60))
    for (x, z), altura in _ARVORES:
        faces += _arvore(np.array([x, PISO_Y, z]), altura)
        faces.append(_sombra((x, 0, z), 0.014))
    faces += _moinho(np.array([_MOINHO[0][0], PISO_Y, _MOINHO[0][1]]), _MOINHO[1])
    faces.append(_sombra((_MOINHO[0][0], 0, _MOINHO[0][1]), 0.017))
    return faces


def _pas_moinho(t):
    """As quatro pas girando. Faces sem culling, porque sao chapas finas."""
    pos = np.array([_MOINHO[0][0], PISO_Y + 0.066, _MOINHO[0][1]])
    ang0 = t * 1.4
    faces = []
    for k in range(4):
        a = ang0 + k * np.pi / 2
        c, s = np.cos(a), np.sin(a)
        canto = np.array([(0.0035, 0.0035, 0.0), (0.0035, 0.045, 0.0),
                          (-0.0035, 0.045, 0.0), (-0.0035, 0.0035, 0.0)])
        giro = np.stack([canto[:, 0] * c - canto[:, 1] * s,
                         canto[:, 0] * s + canto[:, 1] * c,
                         canto[:, 2] + 0.017], axis=1)
        faces.append(_face(_rot_y(giro, _MOINHO[1]) + pos, MADEIRA, cull=False))
    return faces


def miniatura_dinamico(t):
    """Bonecos andando e pas do moinho, reconstruidos a cada frame."""
    objs = _pas_moinho(t)
    for i, (rx, rz, vel, fase0) in enumerate(ORBITAS):
        ang = fase0 + vel * t
        pos = ORBITA_CENTRO + np.array([rx * np.cos(ang), 0.0, rz * np.sin(ang)])
        pos[1] = PISO_Y
        # Olha para onde anda: a tangente da elipse.
        rumo = np.arctan2(rz * np.cos(ang) * vel, -rx * np.sin(ang) * vel)
        roupa, calca = ROUPAS[i % len(ROUPAS)]
        objs.append(_sombra((pos[0], 0, pos[2]), 0.007))
        objs += _boneco(pos, rumo, t * abs(vel) * 13.0 + fase0 * 3.0, roupa, calca)
    return objs


CENAS = ["caixa", "corredor", "miniatura", "barras"]


def build(nome):
    """Parte estatica da cena, construida uma vez."""
    if nome == "caixa":
        return build_caixa()
    if nome == "corredor":
        return build_corredor()
    if nome == "barras":
        return build_barras()
    return build_miniatura()


def dinamico(nome, t):
    """Parte que muda a cada frame. Vazia na caixa."""
    if nome == "caixa":
        return []
    if nome == "corredor":
        return tochas_corredor(t)
    if nome == "barras":
        return barras_dinamico(t)
    return miniatura_dinamico(t)


def fundo(nome, largura, altura):
    """Imagem de fundo por cenario. None significa preencher de preto.

    Todos os cenarios sao interiores de caixa agora, entao nenhum tem ceu: o
    fundo preto e o que faz as paredes iluminadas e os objetos saltarem.
    """
    return None








# ------------------------------------------------------------------ barras ---
#
# Grade vertical no plano da tela, e um braco que a atravessa.
#
# O ponto do efeito NAO e um objeto passar da frente para tras. E um objeto
# LONGO estar dos dois lados ao mesmo tempo: perto da mao ele cobre a barra,
# perto do ombro a barra cobre ele, e a barra parece cortar o braco no meio.
# Objeto compacto so troca de camada inteiro, e ai parece que atravessou a
# barra como fantasma.
#
# Isso nao precisa de codigo de oclusao. O algoritmo do pintor ja ordena por
# POLIGONO, entao basta o braco ser segmentado ao longo do comprimento: cada
# anel do tubo tem a sua propria distancia ao olho, e a divisao acontece
# exatamente onde o braco cruza z = 0.
#
# Por isso a mao inteira, palma e dedos, tambem e feita de tubos e nao de
# caixas. Uma palma em caixa unica vira de lado de uma vez so, e volta a dar o
# efeito fantasma bem no momento em que ela atravessa a grade.
#
# Objeto com z > 0 esta entre a tela e o seu rosto. A projecao aguenta sem
# mudanca: com 0 < P.z < eye.z o denominador continua positivo e t fica maior
# que 1, ampliando em vez de reduzir.

COR_BARRA = (196, 200, 206)
MANGA = (74, 66, 150)              # manga vermelho escuro
PELE_MAO = (150, 190, 224)
CUBOS_FUNDO = [(150, 120, 96), (110, 140, 105)]

# O braco SOBE da base esquerda para o centro-direita, indo para a frente.
#
# A subida nao e estetica, e a diferenca entre o efeito funcionar e nao
# funcionar. Com o braco varrendo na horizontal, as linhas de profundidade
# constante saem VERTICAIS, paralelas as barras: duas retas paralelas se
# sobrepoem num sliver de poucos pixels, e nenhum ajuste de z conserta isso.
# Subindo em diagonal, a transicao de profundidade cruza a barra de through e a
# oclusao vira area em vez de linha.
#
# Medido em pixels, comparando quantos pixels disputados entre barra e braco
# ficam com cada um: a versao horizontal entregava 5160 pontos de corte, esta
# entrega 24739, quase cinco vezes mais.
OMBRO = np.array([-0.110, -0.170, -0.325])
PUNHO_RECOLHIDO = np.array([-0.065, -0.115, -0.240])
PUNHO_ESTENDIDO = np.array([0.025, 0.015, -0.015])

BRACO_ANEIS = 12
RAIO_OMBRO = 0.026
RAIO_PUNHO = 0.016
# A mao continua o eixo do braco: para cima, para a direita e para a frente.
MAO_DIR = np.array([0.60, 0.50, 0.62])
MAO_DIR = MAO_DIR / np.linalg.norm(MAO_DIR)


def _barras():
    """Barras verticais exatamente em z=0, o plano da tela.

    Divididas em segmentos verticais de proposito. O algoritmo do pintor ordena
    por distancia MEDIA ao olho, entao uma barra inteira competiria com o braco
    usando a distancia do meio dela. Segmentada, a comparacao vira local e a
    oclusao acerta em cada altura.
    """
    w, h = config.SCREEN_W / 2, config.SCREEN_H / 2
    n, meia = config.BARRAS_N, config.BARRAS_LARGURA / 2
    segs = config.BARRAS_SEGMENTOS
    objs = []
    for i in range(n):
        x = -w + 2 * w * (i + 0.5) / n
        for k in range(segs):
            y0 = -h + 2 * h * k / segs
            y1 = -h + 2 * h * (k + 1) / segs
            objs.append(_poly([(x - meia, y0, 0.0), (x + meia, y0, 0.0),
                               (x + meia, y1, 0.0), (x - meia, y1, 0.0)],
                              COR_BARRA, th=1, fill=COR_BARRA))
    return objs


def build_barras():
    """A caixa de sempre, mais a grade pregada no vidro."""
    return make_room() + _barras()


def _cubo(centro, lado, cor, ang_x, ang_y):
    v = _rot_y(_rot_x(_verts_caixa(lado, lado, lado), ang_x), ang_y)
    return _solido_caixa(v + np.asarray(centro, float), cor)


def _base_local(pontos, i):
    """Direcao da curva e dois eixos perpendiculares a ela, no ponto i."""
    if i == 0:
        d = pontos[1] - pontos[0]
    elif i == len(pontos) - 1:
        d = pontos[-1] - pontos[-2]
    else:
        d = pontos[i + 1] - pontos[i - 1]
    d = d / np.linalg.norm(d)
    cima = np.array([0.0, 1.0, 0.0])
    if abs(float(np.dot(d, cima))) > 0.9:
        cima = np.array([1.0, 0.0, 0.0])
    e1 = np.cross(d, cima)
    e1 = e1 / np.linalg.norm(e1)
    return d, e1, np.cross(d, e1)


def _tubo(pontos, raios, cores, lados=8, achatamentos=None, tampas=(False, False)):
    """Tubo poligonal ao longo de uma curva, um anel por ponto.

    A segmentacao ao longo do comprimento e o mecanismo do efeito inteiro: cada
    anel vira faces com a sua propria profundidade, entao o algoritmo do pintor
    corta o tubo na altura da barra sem precisar saber que ela existe.

    achatamentos comprime o anel no eixo vertical (e2 sai quase paralelo a y),
    o que transforma o tubo redondo do braco na palma achatada da mao.
    tampas fecha as pontas: ponta aberta mostra o interior vazado e vira buraco.
    """
    aneis = []
    a = np.linspace(0, 2 * np.pi, lados, endpoint=False)
    for i, (p, r) in enumerate(zip(pontos, raios)):
        _d, e1, e2 = _base_local(pontos, i)
        ach = 1.0 if achatamentos is None else achatamentos[i]
        aneis.append(p + r * (np.cos(a)[:, None] * e1
                              + ach * np.sin(a)[:, None] * e2))

    faces = []
    for i in range(len(aneis) - 1):
        A, B = aneis[i], aneis[i + 1]
        centro = (pontos[i] + pontos[i + 1]) / 2.0
        for k in range(lados):
            k2 = (k + 1) % lados
            faces.append(_face([A[k], A[k2], B[k2], B[k]], cores[i], dentro=centro))
    if tampas[0]:
        faces.append(_face(aneis[0], cores[0], dentro=pontos[1]))
    if tampas[1]:
        faces.append(_face(aneis[-1], cores[-1], dentro=pontos[-2]))
    return faces


def _curva(S, C, W, n):
    u = np.linspace(0.0, 1.0, n)[:, None]
    return (1 - u) ** 2 * S + 2 * u * (1 - u) * C + u ** 2 * W


def _braco_e_mao(punho):
    """Braco, palma e dedos como um so sistema de tubos, sem emenda.

    Tres decisoes, cada uma consertando um problema concreto:

    1. Braco e mao sao UM tubo continuo. Antes eram duas pecas e sobrava um
       buraco no punho, onde o tubo terminava aberto e a palma comecava
       deslocada. Emendados, a _base_local suaviza a dobra do punho sozinha.

    2. A mao dobra para a DIREITA em vez de continuar apontando para o
       observador. Mao apontada para a camera fica escorcada e os dedos viram
       serrilha; de lado, a palma aparece de chapa e a silhueta le como mao.

    3. Palma e dedos sao tubos, nao caixas. Caixa e compacta e vira de lado de
       uma vez so quando cruza o plano da tela, que e exatamente o efeito
       fantasma. Segmentados, cada anel cruza no seu tempo e a barra corta a
       mao progressivamente.
    """
    controle = (OMBRO + punho) / 2.0 + np.array([0.0, 0.016, 0.015])
    pontos = list(_curva(OMBRO, controle, punho, BRACO_ANEIS))
    raios = list(np.linspace(RAIO_OMBRO, RAIO_PUNHO, BRACO_ANEIS))
    achata = [1.0] * BRACO_ANEIS

    # Palma: dobra do punho para a direita. O achatamento maior que 1 estica o
    # anel no eixo vertical, deixando a palma alta e fina em vez de redonda.
    for passo, raio, ach in [(0.010, 0.013, 1.35), (0.026, 0.013, 2.05),
                             (0.042, 0.0125, 2.30), (0.056, 0.011, 2.10)]:
        pontos.append(punho + MAO_DIR * passo)
        raios.append(raio)
        achata.append(ach)

    corte = int(BRACO_ANEIS * 0.62)
    cores = [MANGA] * corte + [PELE_MAO] * (len(pontos) - 1 - corte)
    faces = _tubo(pontos, raios, cores, lados=7, achatamentos=achata,
                  tampas=(True, True))

    # Eixos da mao: e1 e a espessura (quase z), e2 e a altura (quase y).
    _d, e1, e2 = _base_local(pontos, len(pontos) - 1)
    ponta = pontos[-1]

    # Dedos: continuam para a direita, abertos no eixo vertical.
    for desloc, comp in [(0.020, 0.026), (0.0068, 0.034),
                         (-0.0068, 0.036), (-0.020, 0.030)]:
        base = ponta + e2 * desloc
        pts = [base, base + MAO_DIR * comp * 0.5, base + MAO_DIR * comp]
        faces += _tubo(pts, [0.0075, 0.0070, 0.0058], [PELE_MAO] * 2, lados=5,
                       achatamentos=[1.0, 1.0, 1.0], tampas=(False, True))

    # Polegar: sai por baixo, aberto para longe da palma.
    base_p = pontos[-3] + e2 * (-0.020)
    dir_p = MAO_DIR * 0.42 - e2 * 0.91
    dir_p = dir_p / np.linalg.norm(dir_p)
    pts = [base_p, base_p + dir_p * 0.015, base_p + dir_p * 0.030]
    faces += _tubo(pts, [0.0090, 0.0082, 0.0068], [PELE_MAO] * 2, lados=5,
                   tampas=(False, True))
    return faces


def barras_dinamico(t):
    """Dois cubos que ficam sempre atras, e o braco que atravessa a grade.

    Os cubos existem como controle: eles nunca saem de tras das barras, entao o
    olho tem contra o que comparar quando o braco passa por cima.
    """
    objs = []
    for i, cor in enumerate(CUBOS_FUNDO):
        ang = t * 0.22 + i * np.pi
        centro = (0.125 * np.sin(ang),
                  0.048 * np.sin(1.7 * ang + i),
                  -0.30 + 0.08 * np.cos(ang))
        objs += _cubo(centro, 0.026, cor, 0.3 * np.sin(t * 0.2 + i), t * 0.18 + i)

    # Perfil de ida e volta. O (1-cos)/2 nao e so suavizacao: ele faz o braco
    # DEMORAR nas duas pontas, que e onde o efeito acontece.
    fase = 2.0 * np.pi * t / config.HERO_PERIODO
    s = 0.5 - 0.5 * np.cos(fase)
    punho = PUNHO_RECOLHIDO + (PUNHO_ESTENDIDO - PUNHO_RECOLHIDO) * s
    return objs + _braco_e_mao(punho)
