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


def _dims(dims):
    """(largura, altura) da tela em metros. None e a tela do config (AP1).

    Todo cenario de caixa tem a boca igual ao retangulo da tela. Com uma tela so
    esse retangulo e o do config; com varias, cada tela tem a sua caixa, do
    tamanho dela. Por isso as medidas viram parametro, com o config de padrao:
    sem passar dims nada muda, nem um bit.
    """
    if dims is None:
        return config.SCREEN_W, config.SCREEN_H
    return dims


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


def make_room(d=None, n=None, com_fundo=True, dims=None):
    """A caixa: frente aberta no plano da tela, fundo em -d, 4 paredes.

    Esta e a concha que TODOS os cenarios usam, e a razao e a unica coisa que faz
    a ilusao funcionar: a boca em z=0 tem exatamente as dimensoes da tela, entao
    projeta em si mesma (t=1) para qualquer posicao do olho. As bordas ficam
    pregadas no bezel do notebook, e o bezel fisico vira a moldura da janela.

    Cenario que flutua sem nada em z=0 nao tem essa ancora: a imagem inteira
    desliza junto com a cabeca, e deslizar numa tela plana le como figura
    escorregando, nao como janela.

    `dims` e (largura, altura) da tela dona da caixa, no referencial LOCAL dela;
    None usa a tela do config.
    """
    largura, altura = _dims(dims)
    w, h = largura / 2, altura / 2
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


def build_caixa(dims=None):
    """A cena inteira: a caixa mais tres cubos flutuando em profundidades diferentes.

    Os cubos ficam em metros fixos, centrados: numa tela maior a caixa alarga e
    os cubos continuam do mesmo tamanho, no meio dela.
    """
    scene = make_room(dims=dims)
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


def project(P, eye, px_w, px_h, dims=None):
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

    P e eye estao no referencial LOCAL da tela. `dims` e (largura, altura) dela
    em metros; None usa o config. Para varias telas, telas.projetar() faz a
    troca de base do mundo para o local e chama esta mesma funcao.
    """
    P = np.asarray(P, float)
    t = eye[2] / (eye[2] - P[:, 2])
    x = eye[0] + t * (P[:, 0] - eye[0])
    y = eye[1] + t * (P[:, 1] - eye[1])

    largura, altura = _dims(dims)
    px = (x / largura + 0.5) * px_w
    py = (0.5 - y / altura) * px_h
    return np.stack([px, py], axis=1)


def z_minimo(objs):
    """Profundidade do vertice mais fundo. E o pior caso de paralaxe."""
    return min((float(o["v"][:, 2].min()) for o in objs), default=0.0)


def paralaxe_px(eye, z_min, px_w, theta=0.0, escala=None, largura=None):
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
    largura = config.SCREEN_W if largura is None else largura
    return abs(dx) / largura * px_w


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


def order_faces(scene, eye, descartar_atras=True):
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

    Com varias telas a ordem e calculada no MUNDO, uma vez, com o olho
    ciclopico, e serve a todas as telas: distancia e produto escalar nao mudam
    com a troca de referencial, entao a oclusao concorda dos dois lados do
    bezel pelo mesmo motivo que concorda entre os dois olhos do estereo. Ai o
    descarte por z abaixo nao faz sentido (o z e o de UMA tela) e vai desligado
    com descartar_atras=False: quem protege a projecao e o recorte de cada tela.
    """
    eye = np.asarray(eye, float)

    ordenado = []
    for obj in scene:
        v = obj["v"]
        # Descarta o que estiver atras do olho. Com o olho em z>0 e a cena em
        # z<=0 isso nunca dispara, mas uma falha de tracking pode inverter.
        if descartar_atras and np.any(v[:, 2] >= eye[2]):
            continue
        centro = v.mean(axis=0)
        n = obj.get("n")
        if n is not None and obj.get("cull", True) and np.dot(n, eye - centro) <= 0:
            continue
        ordenado.append((np.linalg.norm(v - eye, axis=1).mean(), obj))
    ordenado.sort(key=lambda item: -item[0])
    return [obj for _dist, obj in ordenado]


def render(eye, face_order, out, fundo=None, paleta=None, dims=None):
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
        pts = pixels_inteiros(project(obj["v"], eye, px_w, px_h, dims), px_w, px_h)
        desenhar(out, obj, pts, paleta, cv2)
    return out


# Faixa de seguranca das coordenadas, em multiplos do maior lado do canvas.
# Nas cenas do projeto a maior coordenada medida foi ~7.500 px (4x a largura),
# entao nada que e desenhado de verdade chega perto do limite.
LIMITE_PX = 8


def pixels_inteiros(P, px_w, px_h):
    """Pixels float -> int32 para o OpenCV, sem as duas armadilhas da conversao.

    1. NaN, inf ou valor fora do int32 viram -2147483648 no astype do numpy,
       sem erro nenhum. Um vertice assim faz o fillPoly varrer 2 bilhoes de
       linhas: medido, ~20 s travado por poligono.
    2. Mesmo dentro do int32, o fillPoly percorre as linhas desde o vertice
       mais alto, entao o custo cresce com a distancia dele acima da imagem.

    A faixa [-LIMITE_PX, +LIMITE_PX] larguras resolve as duas. Dentro dela
    (todo caso normal) o resultado e identico ao astype puro.
    """
    lim = float(LIMITE_PX * max(px_w, px_h))
    P = np.nan_to_num(P, nan=-lim, posinf=lim, neginf=-lim)
    return np.clip(P, -lim, lim).astype(np.int32)


def desenhar(out, obj, pts, paleta=None, cv2=None):
    """Desenha UM objeto ja projetado (pts em pixels inteiros) em `out`.

    E o corpo do laco do render, separado para o render de varias telas
    (telas.render_tela) desenhar exatamente igual: mesma cor, mesmo
    antialias, mesmo sombreamento. A normal "n" esta no referencial em que a
    cena foi construida (o MUNDO, no caso compartilhado), entao a cor de uma
    face nao depende da tela em que ela cai.
    """
    if cv2 is None:
        import cv2
    cor_obj = obj["color"] if paleta is None else paleta[obj["color"]]
    if obj["kind"] == "seg":
        cv2.line(out, tuple(pts[0]), tuple(pts[1]), cor_obj, obj["th"],
                 cv2.LINE_AA)
        return

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


# ---------------------------------------------------------------- corredor ---
#
# Mesma concha da caixa, so que funda e sem parede no fundo. A secao transversal
# continua sendo o retangulo da tela, entao a boca segue pregada no bezel.

TOCHA_SUPORTE = (95, 95, 105)
TOCHA_FORA = (0, 130, 250)       # laranja
TOCHA_DENTRO = (120, 225, 255)   # amarelo palido
TOCHA_HALO = (0, 26, 56)         # laranja quase preto, faz as vezes de brilho


def build_corredor(dims=None):
    """Caixa funda sem parede no fundo: as linhas convergem e somem no preto."""
    largura, altura = _dims(dims)
    w, h = largura / 2, altura / 2
    segs = make_room(d=config.COR_DEPTH, n=config.COR_DIVISOES, com_fundo=False,
                     dims=dims)

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


def tochas_corredor(t, dims=None):
    """As chamas, reconstruidas a cada frame para tremular.

    O tremor vem da soma de tres senoides de frequencias incomensuraveis, o que
    da um padrao que nunca se repete de forma perceptivel sem precisar de random,
    e portanto continua deterministico e reproduzivel entre execucoes.
    """
    w = _dims(dims)[0] / 2
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


def _piso(dims=None):
    """Chao ladrilhado da caixa.

    Ladrilhado, e nao um poligono unico, por causa do algoritmo do pintor: a
    distancia media de um piso inteiro e a do centro dele, entao uma casa no
    fundo ficaria ordenada atras do piso todo e sumiria. Cada ladrilho ordena
    junto do que esta em cima dele.
    """
    largura, altura = _dims(dims)
    w, d = largura / 2, config.MINI_DEPTH
    piso_y = -altura / 2
    nx, nz = 6, 9
    faces = []
    abaixo = np.array([0.0, piso_y - 0.05, -d / 2])
    for i in range(nx):
        for k in range(nz):
            x0, x1 = -w + 2 * w * i / nx, -w + 2 * w * (i + 1) / nx
            z0, z1 = -d * k / nz, -d * (k + 1) / nz
            cor = PISO_A if (i + k) % 2 == 0 else PISO_B
            faces.append(_face([(x0, piso_y, z0), (x1, piso_y, z0),
                                (x1, piso_y, z1), (x0, piso_y, z1)],
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


def _sombra(pos, raio, piso_y=PISO_Y):
    """Mancha de sombra no chao. Poligono chato, sem projecao de luz calculada."""
    v = _anel(raio, 0.0, 8) + np.array([pos[0], piso_y + 0.0008, pos[2]])
    return _face(v, SOMBRA, dentro=np.array([pos[0], piso_y - 0.05, pos[2]]),
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


def build_miniatura(dims=None):
    """Vilarejo assentado no chao da caixa padrao.

    O vilarejo fica em metros fixos, centrado; so a caixa e o chao acompanham
    `dims`. O chao desce junto com a borda de baixo da tela.
    """
    piso_y = -_dims(dims)[1] / 2
    faces = make_room(d=config.MINI_DEPTH, n=config.MINI_DIVISOES, dims=dims)
    faces += _piso(dims)
    for (x, z), yaw, lg, al, pr in _CASAS:
        pos = np.array([x, piso_y + al / 2, z])
        faces += _casa(pos, yaw, lg, al, pr)
        faces.append(_sombra((x, 0, z), max(lg, pr) * 0.60, piso_y))
    for (x, z), altura in _ARVORES:
        faces += _arvore(np.array([x, piso_y, z]), altura)
        faces.append(_sombra((x, 0, z), 0.014, piso_y))
    faces += _moinho(np.array([_MOINHO[0][0], piso_y, _MOINHO[0][1]]), _MOINHO[1])
    faces.append(_sombra((_MOINHO[0][0], 0, _MOINHO[0][1]), 0.017, piso_y))
    return faces


def _pas_moinho(t, piso_y=PISO_Y):
    """As quatro pas girando. Faces sem culling, porque sao chapas finas."""
    pos = np.array([_MOINHO[0][0], piso_y + 0.066, _MOINHO[0][1]])
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


def miniatura_dinamico(t, dims=None):
    """Bonecos andando e pas do moinho, reconstruidos a cada frame."""
    piso_y = -_dims(dims)[1] / 2
    objs = _pas_moinho(t, piso_y)
    for i, (rx, rz, vel, fase0) in enumerate(ORBITAS):
        ang = fase0 + vel * t
        pos = ORBITA_CENTRO + np.array([rx * np.cos(ang), 0.0, rz * np.sin(ang)])
        pos[1] = piso_y
        # Olha para onde anda: a tangente da elipse.
        rumo = np.arctan2(rz * np.cos(ang) * vel, -rx * np.sin(ang) * vel)
        roupa, calca = ROUPAS[i % len(ROUPAS)]
        objs.append(_sombra((pos[0], 0, pos[2]), 0.007, piso_y))
        objs += _boneco(pos, rumo, t * abs(vel) * 13.0 + fase0 * 3.0, roupa, calca)
    return objs


# ------------------------------------------------ corredor: acabamento ---
#
# O corredor original era so a casca funda com tochas. Aqui entram as pecas que
# aumentam a leitura de profundidade: piso em xadrez (lajes que encolhem com a
# distancia), arcos de pedra em intervalos regulares (oclusao em camadas), um
# portal aceso no fim (ponto de fuga com destino) e brasas que voam do fundo
# ate passar da tela (objeto que cruza o plano z = 0).

PEDRA = (74, 70, 66)
PEDRA_ARESTA = (112, 106, 100)
LAJE = (48, 44, 42)
PORTAL = [(16, 44, 96), (36, 110, 210), (150, 228, 255)]
BRASA = (90, 190, 255)
ARCO_RECUO = 0.10         # cada arco fica este tanto a frente do par de tochas
ARCO_LARGURA = 0.018      # quanto o arco avanca da parede para dentro
ARCO_FUNDO = 0.014        # espessura do arco na direcao do corredor
N_BRASAS = 12


def _extras_corredor(dims=None):
    largura, altura = _dims(dims)
    w, h = largura / 2, altura / 2
    d, n = config.COR_DEPTH, config.COR_DIVISOES
    objs = []
    colunas = 4
    for i in range(n):
        z0, z1 = -d * i / n, -d * (i + 1) / n
        for j in range(colunas):
            if (i + j) % 2:
                continue
            x0, x1 = -w + largura * j / colunas, -w + largura * (j + 1) / colunas
            objs.append(_poly([(x0, -h, z0), (x1, -h, z0), (x1, -h, z1), (x0, -h, z1)],
                              WALL, th=1, fill=LAJE))
    e, p = ARCO_LARGURA, ARCO_FUNDO
    for z_tocha in config.TOCHA_Z:
        z = z_tocha + ARCO_RECUO
        if z > -0.03:
            continue
        for lado in (-1, 1):
            xa, xb = lado * w, lado * (w - e)
            objs.append(_poly([(xa, -h, z), (xb, -h, z), (xb, h - e, z), (xa, h - e, z)],
                              PEDRA_ARESTA, th=1, fill=PEDRA))
            objs.append(_poly([(xb, -h, z), (xb, -h, z - p), (xb, h - e, z - p),
                               (xb, h - e, z)], PEDRA_ARESTA, th=1, fill=LAJE))
        objs.append(_poly([(-w, h - e, z), (w, h - e, z), (w, h, z), (-w, h, z)],
                          PEDRA_ARESTA, th=1, fill=PEDRA))
        objs.append(_poly([(-w + e, h - e, z), (w - e, h - e, z), (w - e, h - e, z - p),
                           (-w + e, h - e, z - p)], PEDRA_ARESTA, th=1, fill=LAJE))
    for k, cor in enumerate(PORTAL):
        s = (1.0, 0.72, 0.42)[k]
        lx, ly = 0.34 * largura * s, 0.78 * altura * s
        y0 = -h
        objs.append(_poly([(-lx / 2, y0, -d), (lx / 2, y0, -d), (lx / 2, y0 + ly, -d),
                           (-lx / 2, y0 + ly, -d)], cor, th=1, fill=cor))
    return objs


def _brasas(t, dims=None):
    """Brasas que saem do portal e voam ate passar da tela, em linha reta."""
    largura, altura = _dims(dims)
    d = config.COR_DEPTH
    objs = []
    for i in range(N_BRASAS):
        a = i * 2.399963                      # angulo aureo: espalha sem repetir
        r = 0.18 + 0.30 * ((i * 0.618034) % 1.0)
        x, y = r * largura / 2 * np.cos(a), r * altura / 2 * np.sin(a)
        frente = 0.10 * (1.0 - r / 0.48)      # as do meio passam mais da tela
        curso = d + frente
        z = -d + ((0.17 + 0.05 * (i % 3)) * t + i * 0.37) % curso
        s = 0.0035 * (1.0 + 0.3 * np.sin(7.0 * t + i))
        objs.append(_poly([(x, y + s, z), (x + s, y, z), (x, y - s, z), (x - s, y, z)],
                          BRASA, th=1, fill=BRASA))
    return objs


# ----------------------------------------------- miniatura: acabamento ---

BALAO = [(60, 70, 215), (236, 236, 240)]
CESTO = (58, 88, 130)
AGUA = (150, 104, 44)
AGUA_BORDA = (190, 150, 96)
AVE = (235, 235, 235)
_PERFIL_BALAO = [(0.0, -0.50), (0.42, -0.28), (0.80, 0.12), (0.78, 0.48),
                 (0.48, 0.80), (0.0, 0.96)]


def _balao(centro, escala, giro):
    """Balao de ar quente: solido de revolucao em gomos de duas cores, e cesto."""
    centro = np.asarray(centro, float)
    n = 8
    aneis = [_anel(r * escala, y * escala, n, giro) + centro for r, y in _PERFIL_BALAO]
    dentro = centro + np.array([0.0, 0.25 * escala, 0.0])
    faces = []
    for k in range(len(aneis) - 1):
        a, b = aneis[k], aneis[k + 1]
        for i in range(n):
            j = (i + 1) % n
            if _PERFIL_BALAO[k][0] == 0.0:
                pts = [a[i], b[i], b[j]]
            elif _PERFIL_BALAO[k + 1][0] == 0.0:
                pts = [a[i], a[j], b[i]]
            else:
                pts = [a[i], a[j], b[j], b[i]]
            faces.append(_face(pts, BALAO[i % 2], dentro=dentro))
    cesto = _verts_caixa(0.30 * escala, 0.22 * escala, 0.30 * escala)
    cesto = _rot_y(cesto, giro) + centro + np.array([0.0, -0.80 * escala, 0.0])
    faces += _solido_caixa(cesto, CESTO)
    for i in (0, 2, 4, 6):
        faces.append(_seg(aneis[1][i], cesto[[7, 6, 2, 3][i // 2]], CESTO))
    return faces


def _lago(piso_y):
    a = np.linspace(0, 2 * np.pi, 12, endpoint=False)
    v = np.stack([0.034 * np.cos(a), np.full(12, piso_y + 0.0008),
                  -0.30 + 0.024 * np.sin(a)], axis=1)
    return [_poly(v, AGUA_BORDA, th=1, fill=AGUA)]


def _extras_miniatura_dinamico(t, piso_y):
    objs = []
    ang = 0.21 * t
    c = np.array([0.020 + 0.085 * np.cos(ang), piso_y + 0.128 + 0.010 * np.sin(0.6 * t),
                  -0.30 + 0.150 * np.sin(ang)])
    objs.append(_sombra((c[0], 0, c[2]), 0.016, piso_y))
    objs += _balao(c, 0.034, 0.3 * t)
    for i in range(3):
        a = 0.55 * t + i * 2.1
        p = np.array([0.10 * np.cos(a), piso_y + 0.150 + 0.008 * i, -0.30 + 0.16 * np.sin(a)])
        tang = np.array([-np.sin(a), 0.0, np.cos(a)])
        lado = np.array([tang[2], 0.0, -tang[0]])
        bate = 0.004 * np.sin(9.0 * t + i)
        for s in (-1, 1):
            ponta = p + s * 0.008 * lado + np.array([0.0, bate, 0.0])
            objs.append(_seg(p, ponta, AVE, 2))
    return objs


# -------------------------------------------------------------- asteroides ---
#
# Cena pensada para o anaglifo. O que o estereo mostra melhor e objeto solido,
# de aresta marcada, espalhado em MUITAS profundidades e cruzando o plano da
# tela: a disparidade muda de sinal quando a pedra passa de tras da tela para a
# frente dela, e e ai que ela "sai". Todas as pedras seguem em frente depois da
# tela, ate a distancia tipica do espectador (ver AST_ALCANCE).

AST_DEPTH = 0.90
# As pedras continuam vindo depois de cruzar o plano da tela, crescendo, e so
# somem ao passar de onde o espectador costuma estar. Nao e a posicao medida do
# olho: e a distancia tipica de uso, proporcional ao tamanho da tela (cerca de
# 1.7 larguras, 60 cm numa tela de 15.6 pol). Perto da moldura a pedra aparece
# cortada pela borda; e de proposito, para o efeito de "passar por voce".
AST_ALCANCE = 1.7
ROCHAS = [(132, 126, 120), (100, 108, 122), (124, 112, 142), (92, 98, 104)]
_OCTA = np.array([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)], float)
_OCTA_F = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4),
           (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]


def _pedras():
    rng = np.random.RandomState(7)
    pedras = []
    for i in range(16):
        a = i * 2.399963
        r = 0.08 + 0.86 * ((i * 0.618034) % 1.0)
        pedras.append({
            "rx": r * np.cos(a), "ry": r * np.sin(a), "r": r,
            "vel": 0.085 + 0.07 * rng.rand(), "fase": rng.rand() * 1.2,
            "tam": 0.010 + 0.016 * rng.rand(),
            "forma": 0.65 + 0.7 * rng.rand(6),
            "wx": 0.5 + 1.2 * rng.rand(), "wy": 0.4 + 1.0 * rng.rand(),
            "cor": ROCHAS[i % len(ROCHAS)]})
    return pedras


_PEDRAS = _pedras()


def build_asteroides(dims=None):
    return make_room(d=AST_DEPTH, n=6, dims=dims)


def asteroides_dinamico(t, dims=None):
    largura, altura = _dims(dims)
    objs = []
    for p in _PEDRAS:
        frente = AST_ALCANCE * largura
        curso = AST_DEPTH - 0.04 + frente
        z = -(AST_DEPTH - 0.04) + (p["fase"] + p["vel"] * t) % curso
        x, y = p["rx"] * largura * 0.42, p["ry"] * altura * 0.42
        v = _OCTA * p["forma"][:, None] * p["tam"]
        v = _rot_x(_rot_y(v, t * p["wy"] + p["fase"]), t * p["wx"])
        centro = np.array([x, y, z])
        v = v + centro
        objs += [_face(v[list(f)], p["cor"], dentro=centro) for f in _OCTA_F]
    return objs


CENAS = ["caixa", "corredor", "miniatura", "asteroides"]

# Nome de exibicao e uma linha de descricao, para o menu do Parallax.
ROTULOS = {
    "caixa": ("Cubos", "A cena clássica: três cubos flutuando numa caixa."),
    "corredor": ("Corredor", "Arcos, tochas e brasas até um portal no fundo."),
    "miniatura": ("Vila", "Um vilarejo em miniatura, com balão e pássaros."),
    "asteroides": ("Asteroides", "Pedras que saem da tela. Feita para o anáglifo."),
}


def build(nome, dims=None):
    """Parte estatica da cena, construida uma vez, no referencial da tela dona.

    `dims` e (largura, altura) dessa tela em metros; None usa o config.
    """
    if nome == "caixa":
        return build_caixa(dims)
    if nome == "corredor":
        return build_corredor(dims) + _extras_corredor(dims)
    if nome == "asteroides":
        return build_asteroides(dims)
    return build_miniatura(dims) + _lago(-_dims(dims)[1] / 2)


def dinamico(nome, t, dims=None):
    """Parte que muda a cada frame. Vazia na caixa."""
    if nome == "caixa":
        return []
    if nome == "corredor":
        return tochas_corredor(t, dims) + _brasas(t, dims)
    if nome == "asteroides":
        return asteroides_dinamico(t, dims)
    return miniatura_dinamico(t, dims) + _extras_miniatura_dinamico(
        t, -_dims(dims)[1] / 2)


def fundo(nome, largura, altura):
    """Imagem de fundo por cenario. None significa preencher de preto.

    Todos os cenarios sao interiores de caixa, entao nenhum tem ceu: o fundo
    preto e o que faz as paredes iluminadas e os objetos saltarem.
    """
    return None


def _cubo(centro, lado, cor, ang_x, ang_y):
    """Cubo sombreado, girado em x e em y. Usado pela cena sala."""
    v = _rot_y(_rot_x(_verts_caixa(lado, lado, lado), ang_x), ang_y)
    return _solido_caixa(v + np.asarray(centro, float), cor)
