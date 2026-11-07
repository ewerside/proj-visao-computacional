"""Cena "janelas": as duas telas como duas janelas para o MESMO ambiente.

Desenhada para a pose calibrada (telas.json), nao para numeros fixos. Tudo sai
de uma analise da geometria (classe Geometria), e cada escolha corrige um
defeito que a cena "sala" mostrou na montagem real:

1. O "para cima" da cena e a GRAVIDADE, nao o Y do notebook. A tampa do
   notebook fica inclinada para tras e o monitor quase vertical, mas as bordas
   de BAIXO das duas telas sao horizontais de verdade (a dobradica esta na
   mesa e o monitor nao esta torto no pe). Entao a vertical e a direcao
   perpendicular as duas bordas: u = X_notebook x X_monitor. Na montagem
   medida isso da a tampa ~15 graus para tras e o monitor ~6, e poe o olho
   ~32 cm ACIMA do centro do notebook: voce olha as duas telas de cima, uns 20
   graus para baixo. Um chao "horizontal no notebook", como o da sala, e visto
   quase de raspao; um chao horizontal de verdade e visto de cima, como uma
   maquete sobre a mesa. Por isso a cena e uma maquete de ferromodelismo.

2. Toda superficie da casca passa por uma BORDA de tela, que e a licao da AP1
   (vertice em z=0 projeta nele mesmo, a imagem fica presa na moldura):
     - chao      pela borda de baixo da tela mais baixa (o notebook);
     - peitoril  pela borda de baixo da tela mais alta (o monitor): uma
                 janela mais alta tem peitoril, e o chao aparece alem dele;
     - paredes   pelas bordas de fora (esquerda de uma, direita da outra);
     - teto      pela borda de cima da tela mais alta. Com o olho acima das
                 telas ele nem aparece; segura a moldura se voce abaixar.
   Todas sao extrudadas na MESMA direcao de profundidade, a media das duas
   normais deitada na horizontal. As linhas de fuga convergem para um ponto so
   nas duas telas, e elas leem como uma sala so, nao como duas caixas.

3. O conteudo principal fica na SOMBRA DO VAO: a faixa do chao que o olho
   tipico veria pelo vao entre as telas, se ele fosse transparente. La fica um
   oval de trilhos que atravessa essa faixa duas vezes, entao metade dele
   aparece em cada tela e o trem some atras do vao e reaparece do outro lado,
   como passaria atras de um pilar entre duas janelas. A profundidade dele e a
   menor em que as DUAS telas ja enxergam o chao.

O resto da maquete (casas, arvores, moinho, montanhas no fundo) e posicionado
pela tela em que deve aparecer, como fracao do trecho de chao que ela mostra
do olho tipico (Geometria.no_chao), e nao em metros fixos.

Profundidade moderada: o fundo fica a PROF_SALA do canto mais fundo das telas.
Tudo fica atras do plano de cada tela; o que passa na frente de uma tela (as
paredes e o chao continuam alem das bordas) e cortado por ela, pela regra do
portal de telas.render_tela.

Coordenadas de construcao: (a, h, d) no referencial da SALA, com a para a
direita, h para cima (gravidade) e d para o observador, origem no centro do
notebook. Os objetos da miniatura (scene.py) usam y para cima, entao funcionam
direto em (a, h, d); no fim tudo passa para o mundo por uma rotacao so.
"""

import numpy as np

import config
import scene as scn
import sala

# Posicao tipica da cabeca, como a tecla d mostra (em relacao a webcam, em
# metros): X -1 cm, Y -2 cm, Z 90 cm. O olho no mundo soma o deslocamento da
# webcam, como tracking.eye_in_screen_coords faz.
CABECA_TIPICA = (-0.01, -0.02, 0.90)
OLHO_TIPICO = np.array([CABECA_TIPICA[0] + config.CAM_OFFSET_X,
                        CABECA_TIPICA[1] + config.CAM_OFFSET_Y,
                        CABECA_TIPICA[2]])

PROF_SALA = 0.55         # fundo da sala, alem do canto mais fundo das telas
ESTRADO_MIN = 0.015      # diferenca de altura a partir da qual ha peitoril
PEITORIL = 0.035         # profundidade do peitoril
PASSO_GRADE = 0.08       # malha do chao, em metros
PROF_OVAL = (0.22, 0.40)  # limites da profundidade do oval, atras da juncao
RAIO_OVAL = 0.065        # raio das curvas do oval
RAIO_CANTO = 0.18        # canto arredondado do ceu (fundo de maquete)
CEU_ACIMA = 0.20         # o ceu passa do topo da tela mais alta: olho baixo ve ceu

# Cores BGR.
GRAMA = (58, 100, 64)
GRAMA_LINHA = (70, 120, 78)
PEITORIL_COR = (88, 112, 140)
BRITA = (70, 80, 92)
TRILHO = (175, 185, 200)
LOCOMOTIVA = (40, 40, 190)
CABINE = (55, 55, 60)
VAGOES = [(170, 110, 50), (40, 185, 230), (80, 160, 60)]
FUMACA = (215, 215, 220)
LAGO = (120, 70, 30)
LAGO_BORDA = (180, 140, 90)
# Ceu do fundo, de cima para baixo: entardecer, escuro em cima e quente no
# horizonte. Faixas chapadas: o fillPoly nao faz degrade e nao precisa.
CEU = [(70, 32, 22), (110, 58, 38), (150, 96, 70), (120, 150, 220), (110, 175, 245)]
ROCHA = (110, 82, 84)
NEVE = (235, 225, 225)
ESTRELA = (230, 230, 230)


# ------------------------------------------------------------ geometria ---

def base_sala(telas):
    """(r, u, b): direita, cima e "para o observador" da sala, no mundo.

    u e a vertical da gravidade, estimada pelas bordas de baixo das duas telas
    (ver o docstring do modulo). Se as duas bordas forem paralelas (telas
    lado a lado sem angulo, ou uma em cima da outra) o produto vetorial nao diz
    nada, e se ele apontar longe do Y das telas (monitor em retrato) a premissa
    falhou; nos dois casos u e a media dos Y das telas.

    b e a media das normais, deitada na horizontal: a sala se afasta em -b, a
    mesma direcao para as duas telas.
    """
    telas = list(telas[:2])
    Y = sum(tl.R[:, 1] for tl in telas)
    Y = Y / np.linalg.norm(Y)
    u = None
    if len(telas) == 2:
        c = np.cross(telas[0].R[:, 0], telas[1].R[:, 0])
        if np.linalg.norm(c) > np.sin(np.radians(4.0)):
            c = c / np.linalg.norm(c)
            c = c if c @ Y >= 0 else -c
            if all(c @ tl.R[:, 1] > np.cos(np.radians(35.0)) for tl in telas):
                u = c
    if u is None:
        u = Y
    n = sum(tl.normal for tl in telas)
    b = n - (n @ u) * u
    b = b / np.linalg.norm(b)
    return np.cross(u, b), u, b


class Geometria:
    """Analise da montagem: referencial da sala, alturas, paredes e o oval.

    Tudo em coordenadas da sala (a, h, d), ver o docstring do modulo. Calculada
    uma vez por pose (cache em geometria()), porque o dinamico usa a cada quadro.
    """

    def __init__(self, telas, olho=None):
        self.telas = list(telas[:2])
        self.olho_mundo = np.asarray(OLHO_TIPICO if olho is None else olho, float)
        self.r, self.u, self.b = base_sala(self.telas)
        self.M = np.column_stack([self.r, self.u, self.b])
        self.olho = self.sala(self.olho_mundo)
        cantos = [self.sala(tl.cantos_mundo()) for tl in self.telas]
        todos = np.vstack(cantos)
        # Telas da esquerda para a direita, pelo centro.
        self.ordem = sorted(range(len(cantos)), key=lambda i: cantos[i][:, 0].mean())

        # Bordas de cada tela em coordenadas da sala: (tela, p0, p1), com p0 e
        # p1 cantos consecutivos (ordem do cantos_mundo: ie, id, sd, se).
        bordas = [(i, c[k], c[(k + 1) % 4]) for i, c in enumerate(cantos)
                  for k in range(4)]
        laterais = [e for e in bordas
                    if abs(e[2][1] - e[1][1]) >= abs(e[2][0] - e[1][0])]
        esq = min(laterais, key=lambda e: e[1][0] + e[2][0])
        dir_ = max(laterais, key=lambda e: e[1][0] + e[2][0])
        self.parede_esq = self._parede(esq[1], esq[2])
        self.parede_dir = self._parede(dir_[1], dir_[2])

        # Borda de baixo de cada tela: a de menor altura media.
        baixo = [min((e for e in bordas if e[0] == i),
                     key=lambda e: e[1][1] + e[2][1]) for i in range(len(cantos))]
        alturas = [(e[1][1] + e[2][1]) / 2 for e in baixo]
        self.h_piso = float(todos[:, 1].min())
        self.h_teto = float(todos[:, 1].max())
        self.alta = int(np.argmax(alturas))
        self.h_peitoril = float(alturas[self.alta])
        self.peitoril = None
        if len(cantos) == 2 and self.h_peitoril - self.h_piso > ESTRADO_MIN:
            p0, p1 = baixo[self.alta][1].copy(), baixo[self.alta][2].copy()
            p0[1] = p1[1] = self.h_peitoril
            self.peitoril = (p0, p1) if p0[0] < p1[0] else (p1, p0)

        self.d_frente = float(todos[:, 2].max()) + 0.05
        self.d_fundo = float(todos[:, 2].min()) - PROF_SALA
        self.J = self.sala(sala.juncao(self.telas))
        self.prof_oval, self.C = self._centro()

    # -- trocas de base. A sala tem a mesma origem do mundo: so rotacao.
    def sala(self, P):
        return np.asarray(P, float) @ self.M

    def mundo(self, P):
        return np.asarray(P, float) @ self.M.T

    def _parede(self, q0, q1):
        """Plano que contem a borda q0-q1 e a direcao de profundidade.

        Devolve a(h): a coordenada a da parede na altura h. Nao depende de d,
        porque o plano contem a direcao d: a parede vai reto para o fundo, na
        mesma direcao das outras superficies.
        """
        e = q1 - q0
        n = np.array([e[1], -e[0], 0.0])   # e x (0, 0, 1)
        k0 = n @ q0
        return lambda h: (k0 - h * n[1]) / n[0]

    def _centro(self):
        """Profundidade e centro do oval de trilhos, sobre a sombra do vao.

        Perto da juncao a tela de cima ainda nao mostra chao nenhum ao lado da
        sombra (a borda de baixo dela esconde), e a "sombra" medida no chao fica
        larga. A profundidade escolhida e a menor, dentro de PROF_OVAL, em que a
        reta da FRENTE do oval ja tem a sombra estreita, so a do vao: ai as duas
        telas mostram trilho dos dois lados dele. O centro, em a, e o meio da
        sombra. Sem sombra (uma tela so), cai na linha de visada olho -> juncao.
        """
        h = self.h_piso + 0.003

        def largura(prof):
            sombra = self.faixa(self.J[2] - prof, h)[1]
            return None if sombra is None else sombra[1] - sombra[0]

        prof = PROF_OVAL[1]
        ref = largura(prof)
        if ref is not None:
            # Folga de 2 cm sobre a sombra "pura": ai a tela de cima ja mostra o
            # trilho da frente encostado no vao, e nao so la na outra ponta.
            for p in np.arange(PROF_OVAL[0], PROF_OVAL[1], 0.01):
                w = largura(p - RAIO_OVAL - 0.015)
                if w is not None and w <= ref + 0.02:
                    prof = float(p)
                    break
        d = self.J[2] - prof
        sombra = self.faixa(d, h)[1]
        if sombra is not None:
            a = (sombra[0] + sombra[1]) / 2
        else:
            E, J = self.olho, self.J
            s = (d - E[2]) / (J[2] - E[2]) if abs(J[2] - E[2]) > 1e-6 else 1.0
            a = E[0] + s * (J[0] - E[0])
        return prof, np.array([a, self.h_piso, d])

    def visivel(self, P_sala, olho=None):
        """Para cada ponto (coords da sala), o indice da tela que o mostra, ou -1."""
        olho = self.olho_mundo if olho is None else olho
        P = self.mundo(P_sala)
        qual = np.full(len(P), -1)
        for i, tl in enumerate(self.telas):
            L, e = tl.do_mundo(P), tl.do_mundo(olho)
            t = e[2] / (e[2] - L[:, 2])
            x = e[0] + t * (L[:, 0] - e[0])
            y = e[1] + t * (L[:, 1] - e[1])
            ok = ((L[:, 2] <= 1e-9) & (np.abs(x) <= tl.w_m / 2)
                  & (np.abs(y) <= tl.h_m / 2))
            qual[ok & (qual < 0)] = i
        return qual

    def faixa(self, d, h, olho=None, passo=0.002):
        """Na reta (h, d), ao longo de a: o trecho visto por cada tela e a sombra
        do vao entre elas. Devolve ([(a0, a1) ou None, por tela], sombra)."""
        a = np.arange(self.parede_esq(h), self.parede_dir(h), passo)
        P = np.stack([a, np.full_like(a, h), np.full_like(a, d)], axis=1)
        qual = self.visivel(P, olho)
        trechos = []
        for i in range(len(self.telas)):
            ai = a[qual == i]
            trechos.append((float(ai.min()), float(ai.max())) if ai.size else None)
        sombra = None
        if len(trechos) == 2 and all(trechos):
            (_e0, e1), (d0, _d1) = sorted(trechos)
            if d0 > e1:
                sombra = (e1, d0)
        return trechos, sombra

    def no_chao(self, lado, fracao, prof, folga=0.0):
        """Ponto do chao que aparece na tela `lado` (0 esquerda, 1 direita).

        prof: metros atras da juncao. fracao: posicao ao longo do trecho de
        chao que a tela mostra nessa profundidade (0 borda esquerda, 1 direita),
        com `folga` metros de margem de cada lado. Se a tela nao mostra chao
        ali, devolve None.
        """
        d = self.J[2] - prof
        trechos, _ = self.faixa(d, self.h_piso + 0.01)
        tr = trechos[self.ordem[min(lado, len(self.ordem) - 1)]]
        if tr is None:
            return None
        a0, a1 = tr[0] + folga, tr[1] - folga
        return np.array([a0 + (a1 - a0) * fracao, self.h_piso, d])

    def resumo(self):
        """Texto para conferir a analise (impresso pelo script de visualizacao)."""
        def graus(v, w):
            return np.degrees(np.arccos(np.clip(v @ w, -1, 1)))
        linhas = ["vertical da sala u = " + np.array2string(self.u, precision=3)
                  + " (mundo)"]
        for tl in self.telas:
            dv = self.olho - self.sala(tl.t)
            desce = np.degrees(np.arctan2(dv[1], np.hypot(dv[0], dv[2])))
            linhas.append(f"  {tl.nome}: inclinada {graus(tl.R[:, 1], self.u):4.1f} "
                          f"graus da vertical; olho {dv[1] * 100:+.1f} cm acima do "
                          f"centro dela, olhando {desce:.1f} graus para baixo")
        if len(self.telas) == 2:
            linhas.append(f"angulo entre as telas {graus(*(tl.normal for tl in self.telas)):.1f}"
                          " graus")
        linhas.append(f"alturas: piso {self.h_piso * 100:+.1f} cm, peitoril "
                      + (f"{self.h_peitoril * 100:+.1f} cm" if self.peitoril else "nao ha")
                      + f", teto {self.h_teto * 100:+.1f} cm, olho {self.olho[1] * 100:+.1f} cm")
        linhas.append(f"paredes em a = {self.parede_esq(self.h_piso) * 100:+.1f} e "
                      f"{self.parede_dir(self.h_piso) * 100:+.1f} cm; fundo "
                      f"{(self.J[2] - self.d_fundo) * 100:.0f} cm atras da juncao")
        linhas.append("juncao J = " + np.array2string(self.J * 100, precision=1)
                      + " cm (a, h, d)")
        linhas.append("chao visto do olho tipico (a em cm), por profundidade atras de J:")
        for prof in (0.10, 0.20, 0.30, 0.40, 0.50):
            trechos, sombra = self.faixa(self.J[2] - prof, self.h_piso + 0.01)
            partes = [f"{self.telas[i].nome} " + ("nada" if trechos[i] is None else
                      f"{trechos[i][0] * 100:+.0f}..{trechos[i][1] * 100:+.0f}")
                      for i in self.ordem]
            if sombra:
                partes.append(f"sombra do vao {(sombra[1] - sombra[0]) * 100:.0f} cm")
            linhas.append(f"  {prof * 100:2.0f} cm: " + ", ".join(partes))
        linhas.append(f"oval: centro a = {self.C[0] * 100:+.1f} cm, "
                      f"{self.prof_oval * 100:.0f} cm atras da juncao")
        return "\n".join(linhas)


_CACHE = {}


def geometria(telas):
    """Geometria da pose atual, com cache pela versao de pose das telas."""
    chave = tuple(tl.versao for tl in telas[:2])
    g = _CACHE.get(chave)
    if g is None:
        _CACHE.clear()
        g = _CACHE[chave] = Geometria(telas)
    return g


# --------------------------------------------------------------- casca ---

def _casca(o):
    o["camada"] = 0
    return o


def _linha(p0, p1, cor, th=1):
    return _casca(scn._seg(p0, p1, cor, th))


def _chapa(verts, cor, borda=None):
    """Poligono cheio da casca, cor chapada (sem sombreamento)."""
    return _casca(scn._poly(verts, borda or cor, th=1, fill=cor))


def _malha(c00, c10, c11, c01, cor, passo=PASSO_GRADE):
    """Grade plana, com o passo aproximado nas duas direcoes."""
    c00, c10, c11, c01 = (np.asarray(c, float) for c in (c00, c10, c11, c01))
    nu = sala._n(np.linalg.norm(c10 - c00), passo)
    nv = sala._n(np.linalg.norm(c01 - c00), passo)
    return sala._grade(c00, c10, c11, c01, nu, nv, cor)


def contorno(g, h, n_arco=4):
    """Contorno do ceu na altura h, como pontos (a, d), da frente para a frente.

    Parede esquerda, canto arredondado, fundo, canto, parede direita: o fundo
    de uma maquete de ferromodelismo, que faz a curva nos cantos para o ceu nao
    ter quina. As paredes laterais sao as das bordas de fora das telas, entao o
    ceu comeca exatamente na moldura e as faixas dele sao linhas de fuga presas
    nela.
    """
    ae, ad = g.parede_esq(h), g.parede_dir(h)
    df, dfr = g.d_fundo, g.d_frente
    r = min(RAIO_CANTO, 0.45 * (ad - ae), 0.45 * (dfr - df))
    pts = [(ae, dfr)]
    for k in range(n_arco + 1):
        ang = np.pi + 0.5 * np.pi * k / n_arco
        pts.append((ae + r + r * np.cos(ang), df + r + r * np.sin(ang)))
    for k in range(n_arco + 1):
        ang = 1.5 * np.pi + 0.5 * np.pi * k / n_arco
        pts.append((ad - r + r * np.cos(ang), df + r + r * np.sin(ang)))
    pts.append((ad, dfr))
    return np.array(pts)


def ao_longo(g, fracoes):
    """Pontos do pe do ceu em fracoes do comprimento do contorno.

    Devolve (a, d, phi) por fracao, com phi o angulo (de +a para +d) da normal
    que aponta para dentro da sala: e para onde uma montanha encostada ali olha.
    """
    c = contorno(g, g.h_piso, 12)
    seg = np.diff(c, axis=0)
    comp = np.linalg.norm(seg, axis=1)
    acum = np.concatenate([[0.0], np.cumsum(comp)])
    saida = []
    for f in fracoes:
        s = f * acum[-1]
        j = int(np.clip(np.searchsorted(acum, s) - 1, 0, len(seg) - 1))
        p = c[j] + seg[j] * (s - acum[j]) / comp[j]
        # Tangente (ta, td) -> normal para dentro (-td, ta).
        saida.append((p[0], p[1], np.arctan2(seg[j][0], -seg[j][1])))
    return saida


def build_casca(g):
    """Ceu, estrelas, chao e malha do chao. Tudo camada 0, NESTA ordem.

    A casca e desenhada na ordem da lista, sem ordenar, antes de tudo: o ceu
    primeiro, o chao cheio por cima do pe do ceu.
    """
    hp = g.h_piso
    topo = g.h_teto + CEU_ACIMA
    df, dfr = g.d_fundo, g.d_frente
    ae, ad = g.parede_esq, g.parede_dir
    objs = []
    # Ceu: faixas horizontais ao longo do contorno. Um quadrilatero por trecho
    # e por faixa, nunca um poligono so: o recorte de cada tela e o de um plano,
    # e um poligono nao convexo cortado ganharia uma "ponte" pelo plano da tela.
    alturas = [topo - (topo - hp) * k / len(CEU) for k in range(len(CEU) + 1)]
    for k, cor in enumerate(CEU):
        h0, h1 = alturas[k], alturas[k + 1]
        c0, c1 = contorno(g, h0), contorno(g, h1)
        for j in range(len(c0) - 1):
            objs.append(_chapa([(c1[j][0], h1, c1[j][1]), (c1[j + 1][0], h1, c1[j + 1][1]),
                                (c0[j + 1][0], h0, c0[j + 1][1]), (c0[j][0], h0, c0[j][1])],
                               cor))
    rng = np.random.default_rng(7)
    for (a, d, phi) in ao_longo(g, rng.uniform(0.15, 0.85, 22)):
        h = rng.uniform(topo - (topo - hp) * 0.40, topo)
        dentro = 0.002 * np.array([np.cos(phi), 0.0, np.sin(phi)])
        p = np.array([a, h, d]) + dentro
        objs.append(_linha(p, p + [0.0, 0.0015, 0.0], ESTRELA, 2))
    # Chao: grama cheia e malha. Comeca na frente das telas: cada tela corta o
    # chao no proprio plano, e o do notebook passa pela borda de baixo dele.
    objs.append(_chapa([(ae(hp), hp, dfr), (ad(hp), hp, dfr), (ad(hp), hp, df),
                        (ae(hp), hp, df)], GRAMA))
    objs += _malha((ae(hp), hp, dfr), (ad(hp), hp, dfr), (ad(hp), hp, df),
                   (ae(hp), hp, df), GRAMA_LINHA)
    return objs


def build_peitoril(g):
    """Peitoril da janela mais alta: tabua presa na borda de baixo dela.

    A aresta da frente e a propria borda da tela, entao fica parada na moldura
    enquanto a de tras se mexe com a cabeca: e a ancora dessa borda. Entra na
    ordem do pintor (nao na casca) porque tampa o chao logo atras da janela.
    """
    if g.peitoril is None:
        return []
    p0, p1 = g.peitoril
    fundo = np.array([0.0, 0.0, -PEITORIL])
    baixo = np.array([0.0, -0.012, 0.0])
    v = [p0, p1, p1 + fundo, p0 + fundo]
    vb = [p + baixo for p in v]
    dentro = (p0 + p1) / 2 + fundo / 2 + baixo / 2
    faces = [v, vb, [v[0], v[1], vb[1], vb[0]], [v[1], v[2], vb[2], vb[1]],
             [v[2], v[3], vb[3], vb[2]], [v[3], v[0], vb[0], vb[3]]]
    return [scn._face(f, PEITORIL_COR, dentro=dentro) for f in faces]


# ---------------------------------------------------------- maquete ---

def _escalar(objs, centro, k):
    """Escala uniforme em torno de `centro`. Normais nao mudam."""
    for o in objs:
        o["v"] = (o["v"] - centro) * k + centro
    return objs


def _cone(base, raio, topo, cor, n=5, giro=0.0):
    """Cone sem fundo (o fundo nunca aparece de cima): n triangulos."""
    anel = scn._anel(raio, 0.0, n, giro) + base
    dentro = (base + topo) / 2
    return [scn._face([anel[i], anel[(i + 1) % n], topo], cor, dentro=dentro)
            for i in range(n)]


def _arvore(p, altura):
    """Pinheiro barato: tronco de 4 faces e duas saias de 5.

    O da miniatura tem 18 faces; com uma dezena de arvores, isso era o maior
    custo da ordem do pintor (que e Python, objeto por objeto).
    """
    p = np.asarray(p, float)
    H = altura
    tronco = scn._rot_y(scn._verts_caixa(0.09 * H, 0.30 * H, 0.09 * H), 0.4)
    tronco = tronco + p + [0.0, 0.15 * H, 0.0]
    faces = [f for f in scn._solido_caixa(tronco, scn.TRONCO) if abs(f["n"][1]) < 0.5]
    faces += _cone(p + [0, 0.22 * H, 0], 0.30 * H, p + [0, 0.66 * H, 0], scn.FOLHA_A)
    faces += _cone(p + [0, 0.48 * H, 0], 0.22 * H, p + [0, 1.00 * H, 0], scn.FOLHA_B,
                   giro=0.6)
    return faces


def _moinho(p, giro, k):
    return _escalar(scn._moinho(np.asarray(p, float), giro), np.asarray(p, float), k)


def _pas(p, giro, k, t):
    """As quatro pas do moinho em `p` (escala k), girando."""
    centro = np.asarray(p, float) + np.array([0.0, 0.066 * k, 0.0])
    faces = []
    for i in range(4):
        a = t * 1.4 + i * np.pi / 2
        c, s = np.cos(a), np.sin(a)
        canto = np.array([(0.0035, 0.0035), (0.0035, 0.045), (-0.0035, 0.045),
                          (-0.0035, 0.0035)]) * k
        v = np.stack([canto[:, 0] * c - canto[:, 1] * s,
                      canto[:, 0] * s + canto[:, 1] * c,
                      np.full(4, 0.017 * k)], axis=1)
        faces.append(scn._face(scn._rot_y(v, giro) + centro, scn.MADEIRA, cull=False))
    return faces


def _montanha(a, h0, d, raio, altura, phi=0.5 * np.pi, n=4):
    """Meia montanha encostada no ceu: so a metade virada para a sala.

    phi e a direcao (de +a para +d) para onde ela olha. Rocha ate 60% da
    altura e ponta de neve. A metade de tras nunca aparece (fica contra o ceu),
    entao nem existe.
    """
    ang = np.linspace(phi - 0.5 * np.pi, phi + 0.5 * np.pi, n + 1)
    cos, sen = np.cos(ang), np.sin(ang)
    base = np.stack([a + raio * cos, np.full(n + 1, h0), d + raio * sen], 1)
    meio = np.stack([a + 0.4 * raio * cos, np.full(n + 1, h0 + 0.6 * altura),
                     d + 0.4 * raio * sen], 1)
    pico = np.array([a, h0 + altura, d])
    dentro = np.array([a, h0 + 0.3 * altura, d])
    faces = []
    for i in range(n):
        faces.append(scn._face([base[i], base[i + 1], meio[i + 1], meio[i]], ROCHA,
                               dentro=dentro))
        faces.append(scn._face([meio[i], meio[i + 1], pico], NEVE, dentro=dentro))
    return faces


def _lago(c, raio, n=10):
    ang = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
    v = np.stack([c[0] + raio * np.cos(ang), np.full(n, c[1] + 0.0005),
                  c[2] + 0.7 * raio * np.sin(ang)], 1)
    return [_chapa(v, LAGO, LAGO_BORDA)]


def _sombra(p, raio):
    return scn._sombra((p[0], 0.0, p[2]), raio, p[1])


def build_maquete(g, oval):
    """Casas, arvores, moinho, lago e montanhas, posicionados pela tela.

    Cada item diz em que tela deve aparecer (0 esquerda, 1 direita), em que
    fracao do chao visivel dela e a quantos metros atras da juncao. Assim a
    maquete se ajusta sozinha a outra pose sem sair do campo de visao.
    """
    objs = []
    # Montanhas no pe do ceu, ao longo do contorno: a parede esquerda e o
    # canto aparecem pela tela de cima, o fundo pelas duas.
    picos = [(0.22, 0.09, 0.17), (0.29, 0.12, 0.25), (0.36, 0.10, 0.19),
             (0.44, 0.12, 0.27), (0.51, 0.10, 0.20), (0.58, 0.11, 0.23),
             (0.65, 0.09, 0.16), (0.72, 0.10, 0.18)]
    for (a, d, phi), (_f, raio, alt) in zip(ao_longo(g, [p[0] for p in picos]), picos):
        dentro = 0.004 * np.array([np.cos(phi), np.sin(phi)])
        objs += _montanha(a + dentro[0], g.h_piso, d + dentro[1], raio, alt, phi)

    def ponto(lado, fracao, prof, folga=0.03):
        p = g.no_chao(lado, fracao, prof, folga)
        if p is None or oval.perto(p, 0.035):
            return None
        return p

    casas = [(0, 0.22, 0.47, 0.6, (0.060, 0.042, 0.050)),
             (0, 0.70, 0.52, -0.4, (0.052, 0.038, 0.046)),
             (1, 0.25, 0.50, 0.3, (0.056, 0.040, 0.048)),
             (1, 0.80, 0.44, -0.8, (0.062, 0.046, 0.052)),
             (1, 0.86, 0.12, 0.9, (0.050, 0.036, 0.044))]
    for lado, f, prof, giro, (lg, al, pr) in casas:
        p = ponto(lado, f, prof)
        if p is None:
            continue
        objs += scn._casa(p + [0, al / 2, 0], giro, lg, al, pr)
        objs.append(_sombra(p, max(lg, pr) * 0.62))
    arvores = [(0, 0.05, 0.40, 0.095), (0, 0.42, 0.55, 0.085), (0, 0.92, 0.42, 0.075),
               (1, 0.05, 0.42, 0.080), (1, 0.55, 0.53, 0.090), (1, 0.97, 0.30, 0.085),
               (1, 0.10, 0.10, 0.070), (1, 0.62, 0.05, 0.065), (1, 0.50, 0.26, 0.060)]
    for lado, f, prof, alt in arvores:
        p = ponto(lado, f, prof)
        if p is None:
            continue
        objs += _arvore(p, alt)
        objs.append(_sombra(p, alt * 0.22))
    m = _moinho_pos(g, oval)
    if m is not None:
        objs += _moinho(m, -0.5, MOINHO_K)
        objs.append(_sombra(m, 0.028))
    p = g.no_chao(1, 0.45, 0.13, 0.05)
    if p is not None:
        objs += _lago(p, 0.065)
    return objs


MOINHO_K = 1.7


def _moinho_pos(g, oval):
    p = g.no_chao(0, 0.50, 0.42, 0.04)
    if p is None or oval.perto(p, 0.04):
        return None
    return p


# --------------------------------------------------------------- trilho ---

class Oval:
    """Pista oval no chao: duas retas ao longo de a e dois semicirculos.

    Parametrizada por comprimento de arco, para os vagoes andarem com
    espacamento constante.
    """

    def __init__(self, centro, meia_reta, raio):
        self.c = np.asarray(centro, float)
        self.L, self.R = meia_reta, raio
        self.comprimento = 4 * meia_reta + 2 * np.pi * raio

    def ponto(self, s):
        """(posicao (a, h, d), rumo) no arco s. O rumo e o angulo da direcao de
        movimento, medido de +a para +d."""
        L, R = self.L, self.R
        s = s % self.comprimento
        a0, h, d0 = self.c
        if s < 2 * L:                                  # reta da frente, para +a
            return np.array([a0 - L + s, h, d0 + R]), 0.0
        s -= 2 * L
        if s < np.pi * R:                              # curva da direita
            ang = s / R
            return np.array([a0 + L + R * np.sin(ang), h, d0 + R * np.cos(ang)]), -ang
        s -= np.pi * R
        if s < 2 * L:                                  # reta do fundo, para -a
            return np.array([a0 + L - s, h, d0 - R]), np.pi
        s -= 2 * L
        ang = s / R                                    # curva da esquerda
        return (np.array([a0 - L - R * np.sin(ang), h, d0 - R * np.cos(ang)]),
                np.pi - ang)

    def perto(self, p, margem):
        """True se o ponto p (no chao) cai a menos de `margem` da pista."""
        a = np.clip(p[0], self.c[0] - self.L, self.c[0] + self.L)
        dist = np.hypot(p[0] - a, p[2] - self.c[2])
        return abs(dist - self.R) < margem + 0.015


def _oval(g):
    """Oval centrado na sombra do vao, com as retas cruzando a sombra inteira."""
    _trechos, sombra = g.faixa(g.C[2], g.h_piso + 0.02)
    meia = 0.15
    if sombra is not None:
        meia = max(meia, (sombra[1] - sombra[0]) * 1.5)
    return Oval(g.C, meia, RAIO_OVAL)


def build_trilhos(oval, n=36):
    """A pista: n quadrilateros de brita contornados na cor do trilho.

    O contorno de cada quadrilatero ja desenha os dois trilhos (arestas
    compridas) e um dormente (aresta curta): um objeto por trecho, em vez de
    tres. Casca: fica no chao, por baixo do trem.
    """
    objs = []
    pts, rumos = zip(*(oval.ponto(oval.comprimento * k / n) for k in range(n + 1)))
    lado = [np.array([-np.sin(r), 0.0, np.cos(r)]) * 0.012 for r in rumos]
    sobe = np.array([0.0, 0.0008, 0.0])
    for k in range(n):
        p0, p1, l0, l1 = pts[k] + sobe, pts[k + 1] + sobe, lado[k], lado[k + 1]
        objs.append(_chapa([p0 - l0, p1 - l1, p1 + l1, p0 + l0], BRITA, TRILHO))
    return objs


def _caixa(centro, sx, sy, sz, giro, cor):
    v = scn._rot_y(scn._verts_caixa(sx, sy, sz), giro) + np.asarray(centro, float)
    return scn._solido_caixa(v, cor)


def _sombra_ret(p, comp, larg, giro):
    v = scn._rot_y(np.array([(-comp / 2, 0, -larg / 2), (comp / 2, 0, -larg / 2),
                             (comp / 2, 0, larg / 2), (-comp / 2, 0, larg / 2)]), giro)
    return scn._face(v + p + [0, 0.0012, 0], scn.SOMBRA,
                     dentro=p - [0, 0.05, 0], cull=False)


VELOCIDADE = 0.075     # m/s: uma volta em ~13 s
ESPACO = 0.056         # entre centros de vagoes


def _baforada(c, raio, olho):
    """Fumaca: hexagono chapado de frente para o olho tipico. Uma face so, em
    vez das seis de um cubo: e reconstruida a cada quadro."""
    olhar = olho - c
    olhar = olhar / np.linalg.norm(olhar)
    e1 = np.cross(olhar, [0.0, 1.0, 0.0])
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(e1, olhar)
    ang = np.linspace(0.0, 2 * np.pi, 6, endpoint=False) + 0.3
    v = c + raio * (np.cos(ang)[:, None] * e1 + np.sin(ang)[:, None] * e2)
    return scn._face(v, FUMACA, dentro=c - 0.01 * olhar, cull=False)


def trem(oval, t, olho):
    """Locomotiva, tres vagoes e fumaca, andando no oval. A cada quadro."""
    objs = []
    s0 = (t * VELOCIDADE) % oval.comprimento
    pecas = [(LOCOMOTIVA, True)] + [(c, False) for c in VAGOES]
    for k, (cor, loco) in enumerate(pecas):
        p, rumo = oval.ponto(s0 - k * ESPACO)
        # _rot_y gira +x para -z; com giro = -rumo o comprimento da caixa (x)
        # fica na direcao (cos rumo, sin rumo) de movimento.
        giro = -rumo
        objs.append(_sombra_ret(p, 0.050, 0.028, giro))
        objs += _caixa(p + [0, 0.014, 0], 0.046, 0.020, 0.024, giro, cor)
        if loco:
            frente = np.array([np.cos(rumo), 0.0, np.sin(rumo)])
            objs += _caixa(p + [0, 0.031, 0] - 0.013 * frente, 0.018, 0.016, 0.024,
                           giro, CABINE)
            chamine = p + [0, 0.029, 0] + 0.015 * frente
            objs += _caixa(chamine, 0.008, 0.014, 0.008, giro, CABINE)
            for i in range(3):
                fase = (t * 0.9 + i / 3) % 1.0
                atras, _r = oval.ponto(s0 - fase * 0.05)
                c = atras + [0, 0.040 + 0.045 * fase, 0]
                objs.append(_baforada(c, 0.008 * (1.0 - 0.5 * fase), olho))
    return objs


# ------------------------------------------------------------ montagem ---

def _para_mundo(objs, g):
    """Coordenadas da sala -> mundo. So rotacao: a origem e a mesma."""
    for o in objs:
        o["v"] = g.mundo(o["v"])
        if o.get("n") is not None:
            o["n"] = g.M @ o["n"]
    return objs


def build(telas):
    """Parte estatica: casca, pista, peitoril e maquete, ja no mundo."""
    g = geometria(telas)
    oval = _oval(g)
    objs = build_casca(g) + build_trilhos(oval)
    objs += build_peitoril(g) + build_maquete(g, oval)
    return _para_mundo(objs, g)


def dinamico(t, telas):
    """Trem e pas do moinho, reconstruidos a cada quadro."""
    g = geometria(telas)
    oval = _oval(g)
    objs = trem(oval, t, g.olho)
    m = _moinho_pos(g, oval)
    if m is not None:
        objs += _pas(m, -0.5, MOINHO_K, t)
    return _para_mundo(objs, g)
