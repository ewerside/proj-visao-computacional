"""Simulador de fotos de celular das duas telas, com verdade de campo.

Serve para testar o pipeline inteiro (deteccao, intrinsecos, pose relativa) sem
celular nem monitor: sabemos exatamente onde a tela B esta, entao da para medir
o erro do calibrar_telas.py em milimetros e graus.

Modelo da foto, na ordem fisica:
  1. Geometria. Cada tela e um retangulo no espaco com pose T_mundo<-tela; o
     mundo e o referencial da tela A. Para cada pixel da foto (com distorcao),
     tiramos a distorcao (iteracao de ponto fixo numa grade grossa, interpolada
     em separavel), formamos o raio e intersectamos com o plano de cada tela.
     Isso da a coordenada no padrao, amostrada com cv2.remap. Uma unica
     reamostragem, sem a imagem intermediaria sem distorcao.
  2. Fotometria em luz linear: nivel de preto e de branco da tela caindo com o
     angulo de visao (IPS), moldura preta, fundo escuro com textura suave,
     moire (a grade de pixels da tela amostrada pontualmente pelos pixels da
     foto, que e de onde o moire vem), reflexo (mancha gaussiana aditiva).
  3. Camera: desfoque optico gaussiano, curva de tom 1/2.2, ruido, JPEG.
  4. Respiracao de foco: a lente do celular foca deslocando o conjunto optico,
     e a distancia focal em pixels cresce ~ f/d. Com f ~ 6 mm, de 0.6 m a
     1.5 m isso e 0.6% de diferenca no f_px. Opcional, por nivel.

Pixels na convencao do OpenCV: centro do pixel (i, j) em (u=j, v=i). A verdade
de campo dos cantos sai da mesma projecao usada na renderizacao, entao uma
deteccao perfeita teria erro zero (medido: mediana 0.02 px no nivel limpo).

Niveis (NIVEIS): "limpo" (quase ideal), "tipico" (ruido leve, JPEG 85, moire
fraco, respiracao de foco) e "ruim" (desfoque 1.5 px, ruido 8, JPEG 75, moire
forte, reflexo em metade das fotos, tremido em 30%). O erro de canto medido no
"tipico" (~0.04 px) e provavelmente OTIMISTA para fotos reais; o "ruim"
(~0.15-0.25 px) e o substituto mais honesto do mundo real.

Uso:
    python simular.py --pasta fotos_sim --n 12 --nivel tipico [--estranha]
gera fotos_sim/foto_XX.jpg e fotos_sim/verdade.json (pose verdadeira de B).
"""

import math
from dataclasses import dataclass, replace

import cv2
import numpy as np
import scipy.sparse as sp
from scipy.spatial.transform import Rotation

# ------------------------------------------------------------------- camera


@dataclass(frozen=True)
class Camera:
    """Camera do celular: modelo pinhole + distorcao radial/tangencial do OpenCV."""
    w: int = 4000
    h: int = 3000
    fx: float = 3050.0
    fy: float = 3048.0
    cx: float = 2011.0
    cy: float = 1493.0
    k1: float = 0.05
    k2: float = -0.10
    p1: float = 0.0
    p2: float = 0.0
    k3: float = 0.0

    @property
    def K(self):
        return np.array([[self.fx, 0, self.cx], [0, self.fy, self.cy], [0, 0, 1.0]])

    @property
    def dist(self):
        return np.array([self.k1, self.k2, self.p1, self.p2, self.k3])


def _distorcer(x, y, c):
    r2 = x * x + y * y
    rad = 1 + r2 * (c.k1 + r2 * (c.k2 + r2 * c.k3))
    xd = x * rad + 2 * c.p1 * x * y + c.p2 * (r2 + 2 * x * x)
    yd = y * rad + c.p1 * (r2 + 2 * y * y) + 2 * c.p2 * x * y
    return xd, yd


def _desdistorcer(xd, yd, c, iters=30):
    """Inverte o modelo de distorcao por ponto fixo (converge rapido: |k r^2| << 1)."""
    x, y = xd.copy(), yd.copy()
    for _ in range(iters):
        r2 = x * x + y * y
        rad = 1 + r2 * (c.k1 + r2 * (c.k2 + r2 * c.k3))
        dx = 2 * c.p1 * x * y + c.p2 * (r2 + 2 * x * x)
        dy = c.p1 * (r2 + 2 * y * y) + 2 * c.p2 * x * y
        x = (xd - dx) / rad
        y = (yd - dy) / rad
    return x, y


def _matriz_interp(n_fino, passo, n_grosso):
    """Matriz esparsa (n_fino x n_grosso) de interpolacao linear 1D.

    No grosso i fica na coordenada fina passo*(i-1), cobrindo -passo..n_fino+passo.
    """
    u = np.arange(n_fino) / passo + 1.0
    i0 = np.floor(u).astype(int)
    a = u - i0
    lin = np.repeat(np.arange(n_fino), 2)
    col = np.stack([i0, i0 + 1], 1).ravel()
    val = np.stack([1 - a, a], 1).ravel()
    return sp.csr_matrix((val, (lin, col)), shape=(n_fino, n_grosso))


_CACHE_RAIOS = {}


def raios_normalizados(c, passo=8):
    """(xn, yn) sem distorcao para cada pixel da foto, float32 (h, w).

    Calculado exato numa grade grossa e interpolado bilinear (separavel, via
    matrizes esparsas). Erro de interpolacao ~ passo^2/8 * |d''| < 0.001 px.
    """
    chave = (c, passo)
    if chave in _CACHE_RAIOS:
        return _CACHE_RAIOS[chave]
    ng_u = c.w // passo + 3
    ng_v = c.h // passo + 3
    ug = passo * (np.arange(ng_u) - 1.0)
    vg = passo * (np.arange(ng_v) - 1.0)
    U, V = np.meshgrid(ug, vg)
    xd = (U - c.cx) / c.fx
    yd = (V - c.cy) / c.fy
    xu, yu = _desdistorcer(xd, yd, c)
    Mu = _matriz_interp(c.w, passo, ng_u)
    Mv = _matriz_interp(c.h, passo, ng_v)
    xn = (Mv @ (Mu @ xu.T).T).astype(np.float32)
    yn = (Mv @ (Mu @ yu.T).T).astype(np.float32)
    if len(_CACHE_RAIOS) > 4:
        _CACHE_RAIOS.clear()
    _CACHE_RAIOS[chave] = (xn, yn)
    return xn, yn


def projetar(P, R, t, c):
    """Projeta pontos do mundo (n,3) com T_cam<-mundo = (R, t). Devolve (n,2) e z."""
    Pc = np.asarray(P, float) @ R.T + t
    z = Pc[:, 2]
    x, y = Pc[:, 0] / z, Pc[:, 1] / z
    xd, yd = _distorcer(x, y, c)
    return np.stack([c.fx * xd + c.cx, c.fy * yd + c.cy], 1), z


# --------------------------------------------------------------- geometria


def rot_euler(guinada=0.0, arfagem=0.0, rolagem=0.0):
    """R = Ry(guinada) @ Rx(arfagem) @ Rz(rolagem), angulos em graus."""
    return Rotation.from_euler("YXZ", [guinada, arfagem, rolagem], degrees=True).as_matrix()


def pose_ao_lado(tela_a, tela_b, lado="direita", giro=35.0, vao=0.03, base=0.03,
                 arfagem=0.0, rolagem=0.0):
    """Pose T_mundo<-B de um monitor ao lado do notebook, girado para o usuario.

    giro: graus em torno do eixo vertical, positivo = borda externa vem para
    frente (na direcao do rosto). vao: folga horizontal entre as areas acesas.
    base: altura da borda inferior de B acima da borda inferior de A.
    arfagem > 0 inclina o topo para tras; rolagem gira no proprio plano.
    A quina interna inferior de B fica exatamente no ponto definido por vao/base.
    """
    s = -1.0 if lado == "direita" else 1.0
    R = rot_euler(s * giro, -arfagem, rolagem)
    quina_local = np.array([s * tela_b.larg_m / 2, -tela_b.alt_m / 2, 0.0])
    quina_mundo = np.array([-s * (tela_a.larg_m / 2 + vao), -tela_a.alt_m / 2 + base, 0.0])
    return R, quina_mundo - R @ quina_local


def olhar_para(pos, alvo, rolagem_graus=0.0):
    """T_cam<-mundo de uma camera em pos olhando para alvo (y do mundo para cima).

    Camera OpenCV: x direita, y para baixo, z para frente.
    """
    z = alvo - pos
    z = z / np.linalg.norm(z)
    cima = np.array([0.0, 1.0, 0.0])
    x = np.cross(z, cima)
    if np.linalg.norm(x) < 1e-6:
        x = np.array([1.0, 0, 0])
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z])                        # linhas: eixos da camera no mundo
    rr = Rotation.from_euler("z", rolagem_graus, degrees=True).as_matrix()
    R = rr @ R
    return R, -R @ pos


# --------------------------------------------------------------------- cena

# Molduras (m): esquerda, direita, cima, baixo.
MOLDURA_NOTEBOOK = (0.006, 0.006, 0.010, 0.025)
MOLDURA_MONITOR = (0.008, 0.008, 0.008, 0.020)


@dataclass
class Cena:
    padroes: list          # [Padrao A, Padrao B]
    poses: list            # [(R, t)] T_mundo<-tela; A = identidade
    molduras: tuple = (MOLDURA_NOTEBOOK, MOLDURA_MONITOR)


@dataclass(frozen=True)
class Nivel:
    """Severidade da foto."""
    nome: str
    desfoque: float = 0.8          # sigma optico, px da foto
    ruido: float = 3.0             # sigma em niveis de 8 bits
    jpeg: int = 85
    moire: float = 0.0             # amplitude da grade de pixels da tela
    p_reflexo: float = 0.0         # probabilidade de reflexo na foto
    reflexo: tuple = (0.2, 0.5)    # intensidade relativa ao branco
    respiracao_mm: float = 0.0     # distancia focal fisica para respiracao de foco
    jitter_c: float = 0.0          # sigma do ponto principal por foto (OIS), px
    p_tremido: float = 0.0         # probabilidade de borrao de movimento
    tremido_px: tuple = (3, 7)


NIVEIS = {
    "limpo": Nivel("limpo", desfoque=0.6, ruido=1.0, jpeg=95),
    "tipico": Nivel("tipico", desfoque=0.9, ruido=3.0, jpeg=85, moire=0.08,
                    p_reflexo=0.2, reflexo=(0.15, 0.4), respiracao_mm=6.0, jitter_c=1.0),
    "ruim": Nivel("ruim", desfoque=1.5, ruido=8.0, jpeg=75, moire=0.2,
                  p_reflexo=0.5, reflexo=(0.3, 0.9), respiracao_mm=6.0, jitter_c=3.0,
                  p_tremido=0.3),
}


def camera_da_foto(cam, nivel, dist_foco, rng):
    """Intrinsecos efetivos de uma foto: respiracao de foco + deslocamento OIS."""
    if nivel.respiracao_mm <= 0 and nivel.jitter_c <= 0:
        return cam
    # Lente fina: distancia imagem = f*d/(d-f). Normalizado para foco a 1 m.
    f = nivel.respiracao_mm / 1000.0
    ganho = (dist_foco / (dist_foco - f)) / (1.0 / (1.0 - f)) if f > 0 else 1.0
    return replace(cam, fx=cam.fx * ganho, fy=cam.fy * ganho,
                   cx=cam.cx + rng.normal(0, nivel.jitter_c),
                   cy=cam.cy + rng.normal(0, nivel.jitter_c))


def verdade_cantos(cena, cam, R_cw, t_cw, margem=4):
    """GT por tela: (ids, uv (n,2)) dos cantos ChArUco que caem dentro da foto."""
    saida = []
    for p, (R, t) in zip(cena.padroes, cena.poses):
        P = p.cantos_metricos() @ R.T + t
        uv, z = projetar(P, R_cw, t_cw, cam)
        ok = (z > 0) & (uv[:, 0] > margem) & (uv[:, 0] < cam.w - 1 - margem) & \
             (uv[:, 1] > margem) & (uv[:, 1] < cam.h - 1 - margem)
        saida.append((np.flatnonzero(ok), uv[ok]))
    return saida


def amostrar_camera(cena, cam, rng, dist=(0.6, 1.5), azimute=40.0, elev=(-10.0, 35.0),
                    rolagem=15.0, max_obliq=55.0, frac_min=0.5, p_uma_tela=0.15,
                    max_tent=2000):
    """Sorteia uma pose plausivel do celular. Devolve (R_cw, t_cw, distancia).

    Posicao: a uma distancia d do ponto medio das telas, numa direcao sorteada em
    torno da normal media (azimute +-azimute, elevacao em elev). Mira no ponto
    medio com jitter, rolagem +-rolagem. Aceita se, para cada tela, ou ela nao
    aparece ou aparece com >= frac_min dos cantos e obliquidade <= max_obliq.
    Exige as duas telas, exceto com probabilidade p_uma_tela (foto de uma so).
    """
    centros = np.array([t for _, t in cena.poses])
    normais = np.array([R[:, 2] for R, _ in cena.poses])
    alvo0 = centros.mean(0)
    n = normais.sum(0)
    n /= np.linalg.norm(n)
    az0 = math.degrees(math.atan2(n[0], n[2]))
    precisa = 1 if rng.random() < p_uma_tela else 2
    for _ in range(max_tent):
        d = rng.uniform(*dist)
        az = math.radians(az0 + rng.uniform(-azimute, azimute))
        el = math.radians(rng.uniform(*elev))
        direc = np.array([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])
        alvo = alvo0 + rng.normal(0, 0.06, 3)
        pos = alvo + d * direc
        mira = alvo + rng.normal(0, 0.05, 3)
        R_cw, t_cw = olhar_para(pos, mira, rng.uniform(-rolagem, rolagem))
        gt = verdade_cantos(cena, cam, R_cw, t_cw)
        boas = 0
        valido = True
        for (ids, _), p, (R, t) in zip(gt, cena.padroes, cena.poses):
            v = pos - t
            obliq = math.degrees(math.acos(np.clip(R[:, 2] @ v / np.linalg.norm(v), -1, 1)))
            frac = len(ids) / p.n_cantos
            if frac >= frac_min and obliq <= max_obliq:
                boas += 1
            elif frac > 0.05:
                valido = False                  # tela cortada ou obliqua demais
        if valido and boas >= precisa:
            return R_cw, t_cw, float(np.linalg.norm(pos - mira))
    raise RuntimeError("nao achei pose de camera valida")


# ------------------------------------------------------------- renderizacao


def _caixa_tela(R_tc, t_tc, tela, mold, cam):
    """Retangulo da foto que contem a tela + moldura (amostra o contorno)."""
    e, d, c, b = mold
    xs = np.linspace(-tela.larg_m / 2 - e, tela.larg_m / 2 + d, 40)
    ys = np.linspace(-tela.alt_m / 2 - b, tela.alt_m / 2 + c, 40)
    borda = np.concatenate([np.stack([xs, np.full(40, ys[0])], 1), np.stack([xs, np.full(40, ys[-1])], 1),
                            np.stack([np.full(40, xs[0]), ys], 1), np.stack([np.full(40, xs[-1]), ys], 1)])
    P = np.concatenate([borda, np.zeros((len(borda), 1))], 1)
    uv, z = projetar(P, R_tc, t_tc, cam)
    if np.any(z <= 0.05):
        return 0, cam.w, 0, cam.h
    u0, v0 = np.floor(uv.min(0)).astype(int) - 8
    u1, v1 = np.ceil(uv.max(0)).astype(int) + 8
    return max(u0, 0), min(u1, cam.w), max(v0, 0), min(v1, cam.h)


def renderizar(cena, cam, R_cw, t_cw, nivel, rng, imagens=None):
    """Foto uint8 (h, w) em tons de cinza das telas vistas pela camera."""
    xn_all, yn_all = raios_normalizados(cam)
    H, W = cam.h, cam.w
    # Fundo escuro com textura suave e alguns retangulos (objetos na mesa).
    baixa = rng.uniform(0.01, 0.10, (12, 16)).astype(np.float32)
    L = cv2.resize(baixa, (W, H), interpolation=cv2.INTER_CUBIC)
    for _ in range(rng.integers(2, 6)):
        x0, y0 = rng.integers(0, W - 200), rng.integers(0, H - 200)
        L[y0:y0 + rng.integers(50, 600), x0:x0 + rng.integers(50, 600)] = rng.uniform(0.05, 0.35)
    zbuf = np.full((H, W), np.inf, np.float32)
    imagens = imagens or [p.imagem() for p in cena.padroes]

    for p, (R, t), mold, img in zip(cena.padroes, cena.poses, cena.molduras, imagens):
        tela = p.tela
        R_tc = R_cw @ R                                  # tela -> camera
        t_tc = R_cw @ t + t_cw
        u0, u1, v0, v1 = _caixa_tela(R_tc, t_tc, tela, mold, cam)
        if u1 <= u0 or v1 <= v0:
            continue
        xn, yn = xn_all[v0:v1, u0:u1], yn_all[v0:v1, u0:u1]
        M = np.column_stack([R_tc[:, 0], R_tc[:, 1], t_tc])
        Mi = np.linalg.inv(M).astype(np.float32)
        h2 = Mi[2, 0] * xn + Mi[2, 1] * yn + Mi[2, 2]
        frente = h2 > 1e-6
        h2 = np.where(frente, h2, 1.0)
        X = (Mi[0, 0] * xn + Mi[0, 1] * yn + Mi[0, 2]) / h2
        Y = (Mi[1, 0] * xn + Mi[1, 1] * yn + Mi[1, 2]) / h2
        z = (1.0 / h2) * np.sqrt(1 + xn * xn + yn * yn)  # distancia ao longo do raio
        w2, a2 = tela.larg_m / 2, tela.alt_m / 2
        e, d, c, b = mold
        dentro_mold = frente & (X >= -w2 - e) & (X <= w2 + d) & (Y >= -a2 - b) & (Y <= a2 + c)
        acesa = dentro_mold & (np.abs(X) <= w2) & (np.abs(Y) <= a2)
        # Coordenada no padrao (convencao OpenCV).
        mu = (X * (tela.px_w / tela.larg_m) + tela.px_w / 2 - 0.5).astype(np.float32)
        mv = (-Y * (tela.px_h / tela.alt_m) + tela.px_h / 2 - 0.5).astype(np.float32)
        # Pre-filtro contra aliasing: quantos pixels da tela cabem num pixel da foto.
        dist_c = np.linalg.norm(t_tc)
        pegada = dist_c / cam.fx / (tela.larg_m / tela.px_w)
        pad = img.astype(np.float32) / 255.0
        if pegada > 1.0:
            pad = cv2.GaussianBlur(pad, (0, 0), 0.5 * pegada)
        val = cv2.remap(pad, mu, mv, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        # Fotometria: branco/preto da tela caindo com o angulo de visao.
        cosang = float(np.clip(-(R_tc[:, 2] @ t_tc) / dist_c, 0, 1))
        branco = rng.uniform(0.75, 0.95) * (0.55 + 0.45 * cosang)
        preto = 0.015 + 0.03 * (1 - cosang)
        lum = preto + (branco - preto) * val
        if nivel.moire > 0:
            # grade de pixels da tela amostrada pontualmente pela foto -> moire.
            fase = rng.uniform(0, 2 * np.pi, 2)
            grade = (1 - nivel.moire * 0.5 * (1 - np.cos(2 * np.pi * mu + fase[0]))) * \
                    (1 - nivel.moire * 0.5 * (1 - np.cos(2 * np.pi * mv + fase[1])))
            lum = lum * grade
        if rng.random() < nivel.p_reflexo:
            # reflexo de lampada/janela: mancha aditiva no vidro da tela
            gx, gy = rng.uniform(-w2, w2), rng.uniform(-a2, a2)
            s = rng.uniform(0.15, 0.35) * tela.larg_m
            lum = lum + rng.uniform(*nivel.reflexo) * np.exp(-((X - gx) ** 2 + (Y - gy) ** 2) / (2 * s * s))
        lum = np.where(acesa, lum, 0.02).astype(np.float32)   # moldura preta
        zb = zbuf[v0:v1, u0:u1]
        usa = dentro_mold & (z < zb)
        L[v0:v1, u0:u1] = np.where(usa, lum, L[v0:v1, u0:u1])
        zb[usa] = z[usa]

    # Camera: desfoque optico, tremido, exposicao + curva de tom, ruido, JPEG.
    L = cv2.GaussianBlur(L, (0, 0), nivel.desfoque)
    if rng.random() < nivel.p_tremido:
        n = int(rng.integers(*nivel.tremido_px)) | 1      # impar: nucleo centrado, sem deslocar
        k = np.zeros((n, n), np.float32)
        k[n // 2, :] = 1.0 / n
        rot = cv2.getRotationMatrix2D(((n - 1) / 2, (n - 1) / 2), rng.uniform(0, 180), 1.0)
        k = cv2.warpAffine(k, rot, (n, n))
        L = cv2.filter2D(L, -1, k / k.sum())
    expo = rng.uniform(0.9, 1.1)
    v8 = 255.0 * np.power(np.clip(L * expo, 0, 1), 1 / 2.2)
    v8 += rng.normal(0, nivel.ruido, v8.shape).astype(np.float32)
    foto = np.clip(v8 + 0.5, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", foto, [cv2.IMWRITE_JPEG_QUALITY, nivel.jpeg])
    return cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)


# ----------------------------------------------------------------- conjunto


def cena_padrao(padroes, estranha=False):
    """Cena do projeto: A na origem, B a direita girado 35 graus (ou pose estranha)."""
    ta, tb = padroes[0].tela, padroes[1].tela
    if estranha:
        Rb, tbv = pose_ao_lado(ta, tb, "esquerda", giro=40.0, vao=0.05, base=0.06,
                               arfagem=12.0, rolagem=4.0)
    else:
        Rb, tbv = pose_ao_lado(ta, tb, "direita", giro=35.0, vao=0.03, base=0.03)
    return Cena(padroes, [(np.eye(3), np.zeros(3)), (Rb, tbv)])


def gerar_fotos(cena, cam, nivel, n, semente, imagens=None):
    """Lista de dicts: foto, GT dos cantos, pose e camera efetiva de cada foto."""
    rng = np.random.default_rng(semente)
    imagens = imagens or [p.imagem() for p in cena.padroes]
    fotos = []
    for _ in range(n):
        R_cw, t_cw, d = amostrar_camera(cena, cam, rng)
        cam_j = camera_da_foto(cam, nivel, d, rng)
        img = renderizar(cena, cam_j, R_cw, t_cw, nivel, rng, imagens)
        fotos.append({"img": img, "R_cw": R_cw, "t_cw": t_cw, "cam": cam_j, "dist": d,
                      "gt": verdade_cantos(cena, cam_j, R_cw, t_cw)})
    return fotos


def salvar_verdade(caminho, cena, cam, fotos, nivel):
    """verdade.json: pose verdadeira de B e da camera, para comparar com telas.json."""
    import json
    R, t = cena.poses[1]
    d = {"R_AB": R.tolist(), "t_AB": t.tolist(),
         "tela_B_m": [cena.padroes[1].tela.larg_m, cena.padroes[1].tela.alt_m],
         "camera": {"K": cam.K.tolist(), "dist": cam.dist.tolist(), "tam": [cam.w, cam.h]},
         "nivel": nivel.nome,
         "fotos": [{"fx": f["cam"].fx, "cx": f["cam"].cx, "cy": f["cam"].cy,
                    "dist_m": f["dist"]} for f in fotos]}
    with open(caminho, "w") as fh:
        json.dump(d, fh, indent=1)


if __name__ == "__main__":
    # Gera uma pasta de fotos sinteticas para testar a calibracao sem celular:
    #   python simular.py --pasta fotos_sim --n 12 --nivel tipico [--estranha]
    #   python calibrar_telas.py calcular fotos_sim -o fotos_sim/telas.json
    # A pasta recebe tambem o padroes.json (o que o "mostrar" gravaria) e o
    # verdade.json (pose verdadeira), que o calcular le sozinho de la.
    import argparse
    import os
    import time
    import padroes as pd
    ap = argparse.ArgumentParser(description="fotos sinteticas das duas telas")
    ap.add_argument("--pasta", default="fotos_sim")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--nivel", default="tipico", choices=list(NIVEIS))
    ap.add_argument("--estranha", action="store_true", help="B a esquerda, inclinado")
    ap.add_argument("--semente", type=int, default=1)
    args = ap.parse_args()
    pad = pd.padroes_projeto()
    cena = cena_padrao(pad, estranha=args.estranha)
    cam = Camera()
    nivel = NIVEIS[args.nivel]
    t0 = time.time()
    fotos = gerar_fotos(cena, cam, nivel, args.n, semente=args.semente)
    os.makedirs(args.pasta, exist_ok=True)
    for i, f in enumerate(fotos):
        cv2.imwrite(os.path.join(args.pasta, f"foto_{i:02d}.jpg"), f["img"],
                    [cv2.IMWRITE_JPEG_QUALITY, 95])
    salvar_verdade(os.path.join(args.pasta, "verdade.json"), cena, cam, fotos, nivel)
    import json
    with open(os.path.join(args.pasta, "padroes.json"), "w", encoding="utf-8") as fh:
        json.dump(pd.para_json(pad, extra={"origem": "simular.py"}), fh, indent=2)
    print(f"{len(fotos)} fotos em {time.time() - t0:.1f} s -> {args.pasta}/")
