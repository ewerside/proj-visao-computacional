"""Varias telas fisicas num referencial comum: pose, projecao, recorte e render.

MUNDO = referencial da tela do notebook, o mesmo do AP1: origem no centro da
area acesa, X para a direita, Y para cima, Z saindo da tela para o rosto, em
metros. O notebook e a tela cuja webcam faz o tracking, entao o olho ja chega
neste referencial e nada no tracking muda.

Cada tela tem o seu referencial LOCAL, com a mesma convencao do AP1 aplicada a
ela: origem no centro da area acesa DELA, X para a direita dos pixels dela, Y
para cima, Z saindo dela. A pose leva local para mundo:

    x_mundo = R @ x_local + t

R e a orientacao (as colunas sao os eixos X, Y e Z da tela escritos no mundo,
entao a terceira coluna e a normal) e t e o centro da area acesa. No notebook
R = I e t = 0, e o caminho de uma tela so continua sendo o do AP1.

Projetar numa tela qualquer e trocar de base e chamar a mesma intersecao
raio-plano do AP1: no referencial local a tela e o plano z=0 de novo. O que
muda de verdade e so isto:

  - a ORDEM do pintor e calculada uma vez, no mundo, com o olho ciclopico, e
    serve a todas as telas. Distancia e produto escalar nao mudam com a troca
    de base, entao a oclusao concorda dos dois lados do bezel;
  - cada tela mostra so o que esta ATRAS dela (z_local <= 0, a regra do
    portal), recortando segmentos e poligonos que atravessam o plano dela.
"""

import itertools
import json
import os

import numpy as np

import config
import scene as scn

ARQUIVO = config.TELAS_FILE

# Tolerancia do recorte pelo plano da tela, em metros. Vertice a menos de um
# micrometro do plano conta como NO plano. A boca de uma caixa construida no
# referencial local fica em z=0 exato, mas depois de ida e volta pela pose ela
# volta com ruido da ordem de 1e-17, e um "> 0" estrito picaria a moldura em
# lascas invisiveis, caras e sem efeito nenhum.
EPS_PORTAL = 1e-6

# Versao de pose, global e crescente. Chave do cache de vertices locais: um
# id() de objeto pode ser reaproveitado depois que o objeto morre, uma versao
# daqui nunca se repete.
_VERSOES = itertools.count(1)


# ------------------------------------------------------------------ a tela ---

class Tela:
    """Uma tela fisica: medidas da area acesa, resolucao e pose no mundo.

    `monitor` diz em qual monitor do Windows esta tela aparece: dicionario com
    "dispositivo" (ex. "\\\\.\\DISPLAY2"), "x" e "y" (canto superior esquerdo
    no desktop virtual, em pixels), ou None. Nao entra em conta nenhuma de
    geometria: serve so para o main.py achar o monitor e abrir a janela nele
    (monitores.achar_monitor).
    """

    def __init__(self, nome, w_m, h_m, px_w, px_h, R=None, t=None, monitor=None):
        self.nome = nome
        self.w_m, self.h_m = float(w_m), float(h_m)
        self.px_w, self.px_h = int(px_w), int(px_h)
        self.monitor = _info_monitor(monitor)
        self.mover(np.eye(3) if R is None else R, np.zeros(3) if t is None else t)

    def mover(self, R, t):
        """Troca a pose. Invalida o cache de vertices locais desta tela.

        E por aqui que um ajuste fino ao vivo (tecla que gira 0.2 grau, por
        exemplo) tem que passar: mexer em .R direto deixaria o cache velho.
        """
        self.R = np.asarray(R, float).reshape(3, 3)
        self.t = np.asarray(t, float).reshape(3)
        # Atalho exato: com a pose identidade a troca de base e pulada. Nao e
        # so velocidade, e garantia de que o modo de uma tela e o AP1 bit a bit.
        self.identidade = bool(np.array_equal(self.R, np.eye(3))
                               and not self.t.any())
        self.versao = next(_VERSOES)

    def __repr__(self):
        return (f"Tela({self.nome!r}, {self.w_m:.4f}x{self.h_m:.4f} m, "
                f"{self.px_w}x{self.px_h} px)")

    @property
    def dims(self):
        return (self.w_m, self.h_m)

    @property
    def normal(self):
        """Normal da tela no mundo, apontando para fora dela (para o rosto)."""
        return self.R[:, 2]

    def do_mundo(self, P):
        """Mundo -> local. Aceita (3,) ou (N,3).

        Com vetores-linha, R^T (P - t) e escrito (P - t) @ R.
        """
        P = np.asarray(P, float)
        if self.identidade:
            return P
        return (P - self.t) @ self.R

    def para_mundo(self, P):
        """Local -> mundo. Aceita (3,) ou (N,3)."""
        P = np.asarray(P, float)
        if self.identidade:
            return P
        return P @ self.R.T + self.t

    def pixel_para_local(self, px, py):
        """Pixel (continuo) -> ponto 3D na superficie da tela, referencial local.

        Inversa exata da conversao de project(): x = (px / px_w - 0.5) * w.
        """
        px, py = np.asarray(px, float), np.asarray(py, float)
        x = (px / self.px_w - 0.5) * self.w_m
        y = (0.5 - py / self.px_h) * self.h_m
        return np.stack([x, y, np.zeros_like(x)], axis=-1)

    def pixel_para_mundo(self, px, py):
        """Pixel -> ponto 3D na superficie fisica da tela, no mundo."""
        return self.para_mundo(self.pixel_para_local(px, py))

    def cantos_mundo(self):
        """Os 4 cantos da area acesa no mundo: inf-esq, inf-dir, sup-dir, sup-esq."""
        w, h = self.w_m / 2, self.h_m / 2
        return self.para_mundo(np.array([(-w, -h, 0.0), (w, -h, 0.0),
                                         (w, h, 0.0), (-w, h, 0.0)]))

    def para_json(self):
        return {"nome": self.nome, "monitor": self.monitor,
                "resolucao_px": [self.px_w, self.px_h],
                "tamanho_m": [self.w_m, self.h_m],
                "R": self.R.tolist(), "t": self.t.tolist()}


def _info_monitor(monitor):
    """Normaliza o campo "monitor": None, dicionario, ou a forma antiga [x, y]."""
    if monitor is None:
        return None
    if isinstance(monitor, dict):
        return dict(monitor)
    return {"x": int(monitor[0]), "y": int(monitor[1])}


def tela_do_config():
    """O notebook do AP1: medidas do config e pose identidade."""
    return Tela("notebook", config.SCREEN_W, config.SCREEN_H,
                config.SCREEN_PX_W, config.SCREEN_PX_H)


def rot_y(graus):
    """Rotacao em torno do Y do mundo. Positivo gira o +X da tela para longe
    do observador (para -Z); a tela da direita virada PARA o observador e
    negativo."""
    a = np.radians(graus)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def carregar(caminho=ARQUIVO):
    """Le telas.json e devolve a lista de Tela, ou None se o arquivo nao existe.

    None e o sinal para o main.py seguir no modo AP1, de uma tela so. A primeira
    tela TEM que ser o notebook com pose identidade: ela define o mundo, e e
    nela que esta a webcam do tracking. Isso e conferido aqui, porque uma pose
    trocada nessa lista nao da erro nenhum, so uma perspectiva errada.
    """
    if not os.path.exists(caminho):
        return None
    with open(caminho, encoding="utf-8") as fh:
        dados = json.load(fh)
    telas = [_tela_de_json(d) for d in dados["telas"]]
    if len(telas) < 1:
        raise ValueError("telas.json: lista de telas vazia")
    base = telas[0]
    if not (np.allclose(base.R, np.eye(3), atol=1e-9)
            and np.allclose(base.t, 0.0, atol=1e-9)):
        raise ValueError("telas.json: a primeira tela precisa ser o notebook, "
                         "com R = identidade e t = 0 (ela define o mundo)")
    for tl in telas:
        # R tem que ser rotacao de verdade: ortonormal e sem espelhamento.
        if (not np.allclose(tl.R.T @ tl.R, np.eye(3), atol=1e-6)
                or np.linalg.det(tl.R) < 0):
            raise ValueError(f"telas.json: R da tela {tl.nome!r} nao e rotacao")
    return telas


def _tela_de_json(d):
    """Uma entrada de "telas". Aceita o formato da calibracao (tamanho_m,
    resolucao_px) e o do prototipo (w_m, h_m, px_w, px_h)."""
    if "tamanho_m" in d:
        w_m, h_m = d["tamanho_m"]
        px_w, px_h = d["resolucao_px"]
    else:
        w_m, h_m, px_w, px_h = d["w_m"], d["h_m"], d["px_w"], d["px_h"]
    return Tela(d["nome"], w_m, h_m, px_w, px_h, d.get("R"), d.get("t"),
                d.get("monitor"))


REFERENCIAL = ("tela do notebook: origem no centro da area acesa, X direita, Y cima, "
               "Z saindo da tela para o rosto, metros. Para cada tela: "
               "x_notebook = R @ x_tela + t")


def salvar(telas, caminho=ARQUIVO, extra=None):
    """Grava o telas.json. `extra` entra no nivel de cima (qualidade, fotos...)."""
    dados = {"versao": 1, "referencial": REFERENCIAL,
             "telas": [tl.para_json() for tl in telas]}
    if extra:
        dados.update(extra)
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- recorte ---

def recortar(v, fechado, z_corte=EPS_PORTAL):
    """Recorta contra o semi-espaco z <= z_corte, no referencial LOCAL da tela.

    fechado=True: poligono, por Sutherland-Hodgman com um plano so. Cada aresta
    a->b contribui com a (se dentro) e com o ponto de cruzamento (se a aresta
    atravessa o plano). Poligono convexo continua convexo; o resultado pode
    ganhar um vertice (quadrilatero cortado num canto vira pentagono).
    fechado=False: segmento de 2 pontos, cortado no ponto de cruzamento.

    Devolve o proprio `v` quando nada precisa mudar (o caso comum, sem copia),
    um array novo quando corta, ou None quando nada sobra.
    """
    z = v[:, 2]
    dentro = z <= z_corte
    if dentro.all():
        return v
    if not dentro.any():
        return None
    if not fechado:
        a, b = v[0], v[1]
        s = (z_corte - a[2]) / (b[2] - a[2])
        p = a + s * (b - a)
        return np.array([a, p]) if dentro[0] else np.array([p, b])
    saida = []
    n = len(v)
    for i in range(n):
        j = (i + 1) % n
        if dentro[i]:
            saida.append(v[i])
        if dentro[i] != dentro[j]:
            a, b = v[i], v[j]
            s = (z_corte - a[2]) / (b[2] - a[2])
            saida.append(a + s * (b - a))
    return np.array(saida) if len(saida) >= 3 else None


def local_recortado(obj, tela, z_corte=EPS_PORTAL):
    """Vertices do objeto no referencial da tela, ja recortados. None se some.

    Fica guardado no proprio objeto. A regra do portal (z_local <= 0) nao
    depende do olho, entao para a parte ESTATICA da cena a troca de base e o
    recorte sao feitos uma vez so, no primeiro quadro, e o resto dos quadros so
    projeta. A parte dinamica e reconstruida a cada quadro com dicionarios
    novos, entao nunca encontra um cache velho.
    """
    cache = obj.get("_loc")
    if cache is None:
        cache = obj["_loc"] = {}
    chave = (tela.versao, z_corte)
    if chave not in cache:
        v = tela.do_mundo(obj["v"])
        cache[chave] = v if z_corte is None else recortar(
            v, obj["kind"] == "poly", z_corte)
    return cache[chave]


# --------------------------------------------------------------- projecao ---

def projetar(P, eye, tela, px_w=None, px_h=None):
    """project() generalizado: P (N,3) e eye (3,) no MUNDO; pixels da `tela`.

    A troca de base acontece aqui dentro, e depois e a mesma intersecao do AP1
    com o plano z=0 local. Sem recorte: e a funcao de referencia para teste. O
    render usa local_recortado() + scene.project() para nao refazer a troca de
    base da parte estatica a cada quadro.
    """
    px_w = tela.px_w if px_w is None else px_w
    px_h = tela.px_h if px_h is None else px_h
    return scn.project(tela.do_mundo(P), tela.do_mundo(eye), px_w, px_h, tela.dims)


def olho_local(eye, tela):
    """Olho no referencial da tela, com a mesma trava do AP1 (EYE_Z_MIN).

    Para o notebook a trava ja foi aplicada no main.py e aqui nao muda nada.
    Para outra tela ela so dispara se o rosto chegar a 10 cm do plano DELA, ou
    passar para tras dele (falha de tracking): a projecao nao tem sentido ali.
    """
    e = np.array(tela.do_mundo(eye), float)
    e[2] = max(e[2], config.EYE_Z_MIN)
    return e


def z_minimo_tela(objs, tela, z_corte=EPS_PORTAL):
    """O z_minimo do AP1 para uma tela do mundo compartilhado.

    Vertice mais fundo que a tela pode mostrar (ja recortado), no referencial
    dela. E o que entra na escala_confortavel daquela tela.
    """
    zs = [float(v[:, 2].min()) for v in (local_recortado(o, tela, z_corte) for o in objs)
          if v is not None]
    return min(zs, default=0.0)


def ordenar_mundo(cena, eye):
    """Ordem do pintor para o mundo compartilhado, valida para todas as telas.

    Objetos com "camada": 0 (a casca da sala: chao, paredes, grade) vem
    primeiro e sem ordenar. Sao linhas que nao ocluem nada e ficam atras de
    tudo por construcao; deixa-las no sort por distancia media faria uma linha
    de chao de 2 m, ordenada pelo meio dela, ser pintada por cima de um cubo.
    O resto vai pelo order_faces do AP1, no mundo, sem o descarte por z.
    """
    casca = [o for o in cena if o.get("camada") == 0]
    resto = [o for o in cena if o.get("camada") != 0]
    return casca + scn.order_faces(resto, eye, descartar_atras=False)


def render_tela(eye, ordem, tela, out, fundo=None, paleta=None,
                z_corte=EPS_PORTAL):
    """Desenha em `out` a cena do MUNDO, ja ordenada, como vista atraves de `tela`.

    eye: olho (ou um dos olhos do estereo) no mundo. ordem: saida de
    ordenar_mundo() ou de order_faces(), a MESMA para todas as telas.

    z_corte=EPS_PORTAL aplica a regra do portal: a tela so mostra o que esta
    atras dela. z_corte=None nao recorta e cai no descarte do AP1 (objeto com
    algum vertice na altura do olho ou atras some inteiro); e o modo de
    compatibilidade, usado pelo teste de regressao.

    Sombreamento: a normal "n" fica no mundo, entao uma face tem a mesma cor
    nas duas telas. A projecao e a do AP1, com o olho e os vertices no
    referencial local da tela.
    """
    olho = olho_local(eye, tela)
    objs, vs = [], []
    for obj in ordem:
        v = local_recortado(obj, tela, z_corte)
        if v is None:
            continue
        if z_corte is None and np.any(v[:, 2] >= olho[2]):
            continue
        objs.append(obj)
        vs.append(v)
    return desenhar_lote(olho, objs, vs, out, tela.dims, fundo, paleta)


def desenhar_lote(olho, objs, vs, out, dims, fundo=None, paleta=None):
    """Projeta TODOS os vertices numa chamada so e desenha objeto por objeto.

    olho e vs (lista de arrays (n,3)) no referencial local da tela. Medido na
    miniatura: projetar objeto por objeto custa ~5 ms por tela so de overhead
    do numpy em arrays de 4 a 8 pontos; em lote, ~0.4 ms. O resultado e o mesmo
    bit a bit: a projecao e elemento a elemento, nao importa o tamanho do lote.
    """
    import cv2

    px_h, px_w = out.shape[:2]
    if fundo is None:
        out[:] = 0
    else:
        np.copyto(out, fundo)
    if not objs:
        return out
    P = scn.pixels_inteiros(scn.project(np.concatenate(vs), olho, px_w, px_h, dims),
                            px_w, px_h)
    ini = 0
    for obj, v in zip(objs, vs):
        fim = ini + len(v)
        scn.desenhar(out, obj, P[ini:fim], paleta, cv2)
        ini = fim
    return out


def render_local(olho, ordem, out, dims, fundo=None, paleta=None):
    """scene.render do AP1 em lote: cena e olho no referencial LOCAL da tela.

    E o caminho do modo de caixas por tela (cada tela com a sua caixa). Mesmo
    resultado que scene.render(olho, ordem, out, fundo, paleta, dims), bit a bit.
    """
    return desenhar_lote(olho, ordem, [o["v"] for o in ordem], out, dims, fundo, paleta)


def transformar(objs, tela):
    """Leva objetos construidos no referencial LOCAL de `tela` para o mundo.

    Vertices pela pose completa, normais so pela rotacao. Devolve dicionarios
    novos; os originais ficam intactos.
    """
    novos = []
    for o in objs:
        d = {k: val for k, val in o.items() if k != "_loc"}
        d["v"] = tela.para_mundo(o["v"])
        if o.get("n") is not None:
            d["n"] = tela.R @ o["n"]
        novos.append(d)
    return novos


# ---------------------------------------------------------------- estereo ---

def _vergencia(P, eye_L, eye_R):
    """Angulo, em radianos, entre as retas que ligam cada olho a cada ponto P."""
    a = P - eye_L
    b = P - eye_R
    c = np.einsum("ij,ij->i", a, b) / (np.linalg.norm(a, axis=1)
                                        * np.linalg.norm(b, axis=1))
    return np.arccos(np.clip(c, -1.0, 1.0))


def disparidade_graus(P_local, eye_L, eye_R, eye_c):
    """Disparidade angular de cada ponto em relacao a superficie da tela, em graus.

    Tudo no referencial LOCAL da tela. Para cada ponto P da cena, Q e onde o
    raio do olho ciclopico ate P fura a tela, que e onde a imagem de P aparece.
    A disparidade e a diferenca de vergencia entre P e Q: e o conflito
    vergencia-acomodacao que o limite de 1 grau do config controla.

    Para tela de frente com o eixo interocular paralelo a ela, isso coincide
    com a formula fechada de paralaxe_px/escala_confortavel. Para tela
    obliqua (o monitor girado) a formula fechada deixa de valer, porque os
    dois olhos ficam a distancias diferentes da tela; esta nao supoe nada.
    """
    P = np.asarray(P_local, float)
    t = eye_c[2] / (eye_c[2] - P[:, 2])
    Q = eye_c + t[:, None] * (P - eye_c)
    return np.degrees(np.abs(_vergencia(P, eye_L, eye_R) - _vergencia(Q, eye_L, eye_R)))


def escala_confortavel_telas(eye, theta, verts_mundo_por_tela, telas, max_deg=None):
    """Escala estereo UNICA que deixa todas as telas dentro do limite de fusao.

    Tem que ser uma so: com escalas diferentes por tela a disparidade de um
    mesmo objeto saltaria ao atravessar o bezel. A disparidade e linear na
    separacao dos olhos (angulos pequenos), entao basta medir com a separacao
    real e dividir. verts_mundo_por_tela: para cada tela, os vertices que ela
    pode mostrar (ja recortados), no mundo ou ja locais (ver chamador).
    """
    max_deg = config.STEREO_MAX_DISPARITY_DEG if max_deg is None else max_deg
    eye_L, eye_R = scn.stereo_eyes(eye, theta, 1.0)
    escala = 1.0
    for tela, verts in zip(telas, verts_mundo_por_tela):
        if verts is None or len(verts) == 0:
            continue
        P = tela.do_mundo(verts)
        disp = disparidade_graus(P, tela.do_mundo(eye_L), tela.do_mundo(eye_R),
                                 tela.do_mundo(eye)).max()
        if disp > 0:
            escala = min(escala, max_deg / disp)
    return escala
