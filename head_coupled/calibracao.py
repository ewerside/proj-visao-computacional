"""Calibracao das telas pelas fotos: intrinsecos do celular e pose da tela B em A.

Referenciais (metros):
  - MUNDO = referencial da tela A (notebook): origem no centro da area acesa,
    x direita, y para cima, z saindo da tela na direcao do rosto. E o mesmo
    referencial que o head_coupled ja usa, e a webcam fica presa nele.
  - tela B: o mesmo, mas da tela B. A saida e T_A<-B:   x_A = R @ x_B + t.
  - camera de cada foto: convencao OpenCV (x direita, y baixo, z para frente),
    pose T_cam<-mundo.

Etapas:
  1. intrinsecos com cv2.calibrateCamera, cada par (foto, tela) como uma vista
     plana separada (a rigidez entre as duas telas ainda nao e conhecida);
  2. pose de cada tela em cada foto: solvePnP IPPE (feito para alvo plano) e
     refino Levenberg-Marquardt;
  3. pose relativa por foto que ve as duas telas, T_A<-B = inv(T_c<-A) T_c<-B.
     Media robusta: rotacao pela media cordal (SVD da soma das matrizes),
     translacao pela mediana, e descarte de fotos discrepantes;
  4. ajuste de feixes (scipy.optimize.least_squares, perda huber): pose de cada
     foto + UMA pose de B compartilhada + intrinsecos (+ escala de B, opcional),
     minimizando o erro de reprojecao de todos os cantos em todas as fotos.
     E aqui que a restricao "as duas telas estao paradas uma em relacao a outra"
     entra de verdade; a media do passo 3 so serve de chute inicial.

Escala de B (estimada por padrao; --fixar-escala-b desliga): o tamanho fisico de B costuma vir da diagonal nominal
(24 pol vendido pode ser 23.8). Com fotos de pontos de vista diferentes a escala
e observavel: numa foto so, B duas vezes maior e duas vezes mais longe da a mesma
imagem, mas a paralaxe entre fotos desfaz a ambiguidade. A escala de A NAO e
estimada: ela e a regua do sistema inteiro.

Quem chama isto e o calibrar_telas.py (comandos mostrar e calcular); o passo a
passo com o celular esta no docstring dele e em docs/TESTE_AP2.md.
"""

import math
import time
from dataclasses import dataclass, field, replace

import cv2
import numpy as np
import scipy.sparse as sp
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

N_MIN_VISTA = 12          # cantos minimos para uma tela numa foto contar
FLAGS_INTRINSECOS = cv2.CALIB_FIX_K3 | cv2.CALIB_ZERO_TANGENT_DIST

# ------------------------------------------------------------- utilidades


def angulo_graus(Ra, Rb):
    """Angulo da rotacao relativa Ra^T Rb, em graus."""
    c = (np.trace(Ra.T @ Rb) - 1) / 2
    return math.degrees(math.acos(float(np.clip(c, -1, 1))))


def media_rotacoes(Rs, pesos=None):
    """Media cordal: a rotacao mais proxima (Frobenius) da soma das matrizes."""
    Rs = np.asarray(Rs)
    w = np.ones(len(Rs)) if pesos is None else np.asarray(pesos, float)
    M = np.einsum("i,ijk->jk", w, Rs)
    U, _, Vt = np.linalg.svd(M)
    D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
    return U @ D @ Vt


def media_robusta(Rs, ts, k=3.0, rot_min=0.3, trans_min=0.003):
    """Media de poses com descarte iterativo de discrepantes.

    Discrepante: angulo ate a media > max(k * mediana dos angulos, rot_min graus)
    ou distancia ate a mediana das translacoes > max(k * mediana, trans_min m).
    Devolve R, t e a mascara das fotos aceitas.
    """
    Rs, ts = np.asarray(Rs), np.asarray(ts)
    ok = np.ones(len(Rs), bool)
    for _ in range(5):
        R = media_rotacoes(Rs[ok])
        t = np.median(ts[ok], axis=0)
        ang = np.array([angulo_graus(R, Ri) for Ri in Rs])
        dt = np.linalg.norm(ts - t, axis=1)
        lim_r = max(k * np.median(ang[ok]), rot_min)
        lim_t = max(k * np.median(dt[ok]), trans_min)
        novo = (ang <= lim_r) & (dt <= lim_t)
        if novo.sum() < max(2, len(Rs) // 3) or np.array_equal(novo, ok):
            break
        ok = novo
    return media_rotacoes(Rs[ok]), np.median(ts[ok], axis=0), ok


def compor_inv(R1, t1, R2, t2):
    """inv(T1) @ T2."""
    return R1.T @ R2, R1.T @ (t2 - t1)


# ------------------------------------------------------------- intrinsecos


def calibrar_intrinsecos(fotos_det, tam, flags=FLAGS_INTRINSECOS):
    """cv2.calibrateCamera com cada (foto, tela) como vista separada.

    fotos_det: lista (por foto) de listas (por tela) de DeteccaoTela ou None.
    tam: (w, h) da foto. Devolve K, dist (5,), rms em px.
    """
    obj, img = [], []
    for dets in fotos_det:
        for d in dets:
            if d is not None and d.n >= N_MIN_VISTA:
                obj.append(d.obj.astype(np.float32))
                img.append(d.img.astype(np.float32).reshape(-1, 1, 2))
    if len(obj) < 3:
        raise RuntimeError("poucas vistas para calibrar os intrinsecos")
    # Com FIX_ASPECT_RATIO o OpenCV le so a razao fx/fy daqui (1:1).
    K0 = np.array([[1.0, 0, tam[0] / 2], [0, 1.0, tam[1] / 2], [0, 0, 1]])
    crit = (cv2.TERM_CRITERIA_COUNT + cv2.TERM_CRITERIA_EPS, 100, 1e-10)
    rms, K, dist, _, _ = cv2.calibrateCamera(obj, img, tuple(tam), K0, None,
                                             flags=flags, criteria=crit)
    return K, dist.ravel()[:5], rms


def pose_pnp(d, K, dist):
    """Pose T_cam<-tela de uma deteccao. Devolve R, t, rms."""
    obj = d.obj.astype(np.float64)
    img = d.img.astype(np.float64)
    ok, rvec, tvec = cv2.solvePnP(obj, img, K, dist, flags=cv2.SOLVEPNP_IPPE)
    rvec, tvec = cv2.solvePnPRefineLM(obj, img, K, dist, rvec, tvec)
    proj, _ = cv2.projectPoints(obj, rvec, tvec, K, dist)
    rms = float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - img) ** 2, 1))))
    return cv2.Rodrigues(rvec)[0], tvec.ravel(), rms


def poses_relativas(fotos_det, K, dist):
    """Pose de cada tela em cada foto e T_A<-B das fotos que veem as duas."""
    poses = []                 # por foto: [ (R,t,rms) ou None, ... ]
    rel = []                   # (indice da foto, R_AB, t_AB)
    for j, dets in enumerate(fotos_det):
        pj = [pose_pnp(d, K, dist) if d is not None and d.n >= N_MIN_VISTA else None
              for d in dets]
        poses.append(pj)
        if pj[0] is not None and pj[1] is not None:
            R, t = compor_inv(pj[0][0], pj[0][1], pj[1][0], pj[1][1])
            rel.append((j, R, t))
    return poses, rel


# ------------------------------------------------------------ ajuste de feixes


def _projetar(Xc, intr):
    fx, fy, cx, cy, k1, k2, p1, p2, k3 = intr
    x = Xc[:, 0] / Xc[:, 2]
    y = Xc[:, 1] / Xc[:, 2]
    r2 = x * x + y * y
    rad = 1 + r2 * (k1 + r2 * (k2 + r2 * k3))
    xd = x * rad + 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
    yd = y * rad + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
    return np.stack([fx * xd + cx, fy * yd + cy], 1)


@dataclass
class ResultadoBA:
    intr: np.ndarray           # fx fy cx cy k1 k2 p1 p2 k3
    R_AB: np.ndarray
    t_AB: np.ndarray
    escala_B: float
    poses: dict                # j -> (R_cw, t_cw)
    rms: float
    rms_por_tela: list
    sigma_rot_graus: float     # 1-sigma (norma) da rotacao de B, pela covariancia
    sigma_trans_mm: float
    sigma_escala: float
    n_obs: int
    custo: float
    sucesso: bool


def ajuste_feixes(fotos_det, K, dist, poses_ini, R_AB, t_AB, refinar_intr=True,
                  estimar_escala=False, perda="huber", f_escala=1.0):
    """Ajuste de feixes conjunto. poses_ini: j -> (R_cw, t_cw) de cada foto usada.

    Parametros: [intrinsecos (6: fx fy cx cy k1 k2) se refinar_intr] +
    [rotvec_B (3), t_B (3)] + [escala_B (1) se estimar_escala] +
    [rotvec_j, t_j (6) por foto]. p1, p2, k3 ficam fixos no valor de entrada.
    """
    fotos = sorted(poses_ini)
    idx_foto = {j: k for k, j in enumerate(fotos)}
    X, U, F, T = [], [], [], []
    for j in fotos:
        for tela, d in enumerate(fotos_det[j]):
            if d is None or d.n < N_MIN_VISTA:
                continue
            X.append(d.obj)
            U.append(d.img)
            F.append(np.full(d.n, idx_foto[j]))
            T.append(np.full(d.n, tela))
    X, U = np.concatenate(X), np.concatenate(U)
    F, T = np.concatenate(F), np.concatenate(T)
    eh_b = T == 1
    m = len(X)

    intr0 = np.array([K[0, 0], K[1, 1], K[0, 2], K[1, 2], *np.asarray(dist).ravel()[:5]], float)
    # dist do OpenCV: k1 k2 p1 p2 k3 -> intr = fx fy cx cy k1 k2 p1 p2 k3
    n_i = 6 if refinar_intr else 0
    o_b = n_i
    o_s = o_b + 6
    o_f = o_s + (1 if estimar_escala else 0)
    n_par = o_f + 6 * len(fotos)

    x0 = np.zeros(n_par)
    if refinar_intr:
        x0[:6] = intr0[:6]
    x0[o_b:o_b + 3] = Rotation.from_matrix(R_AB).as_rotvec()
    x0[o_b + 3:o_b + 6] = t_AB
    if estimar_escala:
        x0[o_s] = 1.0
    for k, j in enumerate(fotos):
        R, t = poses_ini[j]
        x0[o_f + 6 * k:o_f + 6 * k + 3] = Rotation.from_matrix(R).as_rotvec()
        x0[o_f + 6 * k + 3:o_f + 6 * k + 6] = t

    def desempacotar(x):
        intr = intr0.copy()
        if refinar_intr:
            intr[:6] = x[:6]
        Rb = Rotation.from_rotvec(x[o_b:o_b + 3]).as_matrix()
        tb = x[o_b + 3:o_b + 6]
        s = x[o_s] if estimar_escala else 1.0
        cams = x[o_f:].reshape(-1, 6)
        return intr, Rb, tb, s, cams

    def residuos(x):
        intr, Rb, tb, s, cams = desempacotar(x)
        Xw = X.copy()
        Xw[eh_b] = (s * X[eh_b]) @ Rb.T + tb
        Rc = Rotation.from_rotvec(cams[:, :3]).as_matrix()
        Xc = np.einsum("mij,mj->mi", Rc[F], Xw) + cams[F, 3:]
        return (_projetar(Xc, intr) - U).ravel()

    # Esparsidade do jacobiano: cada observacao depende dos intrinsecos, da
    # pose da sua foto e (se for de B) da pose/escala de B.
    S = sp.lil_matrix((2 * m, n_par), dtype=np.int8)
    lin = np.arange(m)
    for r in (0, 1):
        rr = 2 * lin + r
        if refinar_intr:
            for c in range(6):
                S[rr, c] = 1
        for c in range(6):
            S[rr[eh_b], o_b + c] = 1
            S[rr, o_f + 6 * F + c] = 1
        if estimar_escala:
            S[rr[eh_b], o_s] = 1

    # Duas etapas. Primeiro minimos quadrados puros: com chute ruim (tamanho de
    # B errado em 7% da residuos de dezenas de pixels) a perda robusta trata
    # TUDO como discrepante, os passos ficam minusculos e o trf estoura o limite
    # de iteracoes longe do minimo (medido: 3 graus e 25 mm de erro, contra
    # 0.006 graus e 0.03 mm com a etapa linear antes). Depois, perda robusta a
    # partir dessa solucao, so para baixar o peso de cantos ruins.
    S = S.tocsr()
    sol = least_squares(residuos, x0, jac_sparsity=S, method="trf", loss="linear",
                        x_scale="jac", max_nfev=500)
    # "Convergiu" e o da etapa linear. A etapa robusta, em fotos reais, costuma
    # parar no limite de avaliacoes ainda rastejando (medido: 4x mais iteracoes
    # mudam a pose em 0.01 mm), e isso nao e falha.
    convergiu = bool(sol.success)
    if perda != "linear":
        # Partindo do minimo linear converge em poucas iteracoes quando o modelo
        # esta certo; com modelo errado (tamanho de B fixo e errado) iterar mais
        # nao ajuda e so gasta tempo, dai o limite menor.
        sol = least_squares(residuos, sol.x, jac_sparsity=S, method="trf", loss=perda,
                            f_scale=f_escala, x_scale="jac", max_nfev=100)
    intr, Rb, tb, s, cams = desempacotar(sol.x)
    r = sol.fun.reshape(-1, 2)
    e2 = np.sum(r * r, 1)
    rms = float(np.sqrt(e2.mean()))
    rms_t = [float(np.sqrt(e2[T == k].mean())) if np.any(T == k) else float("nan") for k in (0, 1)]

    # Covariancia aproximada (Gauss-Newton) dos parametros de B.
    sig_r = sig_t = sig_s = float("nan")
    try:
        J = sol.jac.toarray() if sp.issparse(sol.jac) else sol.jac
        dof = max(1, 2 * m - n_par)
        s2 = float(np.sum(sol.fun ** 2) / dof)
        cov = np.linalg.pinv(J.T @ J) * s2
        sig_r = math.degrees(math.sqrt(np.trace(cov[o_b:o_b + 3, o_b:o_b + 3])))
        sig_t = 1000 * math.sqrt(np.trace(cov[o_b + 3:o_b + 6, o_b + 3:o_b + 6]))
        if estimar_escala:
            sig_s = math.sqrt(cov[o_s, o_s])
    except Exception:
        pass
    poses = {j: (Rotation.from_rotvec(cams[k, :3]).as_matrix(), cams[k, 3:].copy())
             for k, j in enumerate(fotos)}
    return ResultadoBA(intr, Rb, tb, float(s), poses, rms, rms_t, sig_r, sig_t, sig_s,
                       m, float(sol.cost), convergiu)


# --------------------------------------------------------------- pipeline


@dataclass
class Calibracao:
    K: np.ndarray
    dist: np.ndarray
    rms_intr: float
    R_media: np.ndarray            # media robusta (passo 3)
    t_media: np.ndarray
    aceitas: list                  # fotos usadas na media
    descartadas: list
    disp_rot_graus: float          # mediana do desvio das fotos aceitas
    disp_trans_mm: float
    ba: ResultadoBA = None
    tempo_s: dict = field(default_factory=dict)

    @property
    def R(self):
        return self.ba.R_AB if self.ba is not None else self.R_media

    @property
    def t(self):
        return self.ba.t_AB if self.ba is not None else self.t_media

    @property
    def escala_B(self):
        return self.ba.escala_B if self.ba is not None else 1.0


def calibrar(fotos_det, tam, flags=FLAGS_INTRINSECOS, ba=True, refinar_intr=True,
             estimar_escala=False, perda="huber"):
    """Pipeline completo sobre deteccoes ja feitas. Devolve Calibracao."""
    t0 = time.perf_counter()
    K, dist, rms_i = calibrar_intrinsecos(fotos_det, tam, flags)
    t1 = time.perf_counter()
    poses, rel = poses_relativas(fotos_det, K, dist)
    if len(rel) < 1:
        raise RuntimeError("nenhuma foto mostra as duas telas")
    js = [j for j, _, _ in rel]
    R_m, t_m, ok = media_robusta([R for _, R, _ in rel], [t for _, _, t in rel])
    ang = np.array([angulo_graus(R_m, R) for _, R, _ in rel])
    dtt = np.array([np.linalg.norm(t - t_m) for _, _, t in rel]) * 1000
    cal = Calibracao(K, dist, rms_i, R_m, t_m,
                     [j for j, o in zip(js, ok) if o], [j for j, o in zip(js, ok) if not o],
                     float(np.median(ang[ok])), float(np.median(dtt[ok])))
    t2 = time.perf_counter()
    if ba:
        # Chute da pose de cada foto: pela tela A se ela aparece, senao por B.
        # Fotos descartadas na media continuam no ajuste (a perda huber cuida).
        ini = {}
        for j, pj in enumerate(poses):
            if pj[0] is not None:
                ini[j] = (pj[0][0], pj[0][1])
            elif pj[1] is not None:
                Rcb, tcb = pj[1][0], pj[1][1]
                Rcw = Rcb @ R_m.T
                ini[j] = (Rcw, tcb - Rcw @ t_m)
        cal.ba = ajuste_feixes(fotos_det, K, dist, ini, R_m, t_m, refinar_intr,
                               estimar_escala, perda)
        if estimar_escala and abs(cal.ba.escala_B - 1.0) > 1e-6:
            _dispersao_com_escala(cal, fotos_det)
    cal.tempo_s = {"intrinsecos": t1 - t0, "media": t2 - t1, "ba": time.perf_counter() - t2}
    return cal


def _dispersao_com_escala(cal, fotos_det):
    """Refaz a dispersao entre fotos com o tamanho de B que o ajuste estimou.

    As poses por foto do passo 3 usam o tamanho NOMINAL de B (da diagonal
    informada). Com a diagonal errada, B sai mais perto ou mais longe em cada
    foto por um fator que depende de onde a foto foi tirada, e as fotos
    "discordam" sem nada ter mexido: um monitor de 32 pol informado como 24
    dava 110 mm de dispersao com o resultado final certo. Refazendo com a
    escala estimada, a dispersao volta a medir so o que interessa.
    """
    s = cal.ba.escala_B
    fd = [[d if (i != 1 or d is None) else replace(d, obj=d.obj * s)
           for i, d in enumerate(dets)] for dets in fotos_det]
    K, dist = _K(cal.ba.intr), np.asarray(cal.ba.intr[4:], float)
    _poses, rel = poses_relativas(fd, K, dist)
    if not rel:
        return
    js = [j for j, _, _ in rel]
    R_m, t_m, ok = media_robusta([R for _, R, _ in rel], [t for _, _, t in rel])
    ang = np.array([angulo_graus(R_m, R) for _, R, _ in rel])
    dtt = np.array([np.linalg.norm(t - t_m) for _, _, t in rel]) * 1000
    cal.aceitas = [j for j, o in zip(js, ok) if o]
    cal.descartadas = [j for j, o in zip(js, ok) if not o]
    cal.disp_rot_graus = float(np.median(ang[ok]))
    cal.disp_trans_mm = float(np.median(dtt[ok]))


# ------------------------------------------------------------------ saida


def quinas_no_mundo(padrao, R, t, escala=1.0):
    """(4,3) quinas da area acesa da tela em A: inf-esq, inf-dir, sup-dir, sup-esq."""
    return (escala * padrao.quinas_tela()) @ R.T + t


def telas_json(padroes, cal, tam_foto, extra=None):
    """Monta o dicionario do telas.json (formato proposto, versao 1)."""
    pa, pb = padroes
    s = cal.escala_B
    tb = pb.tela.escalada(s)
    ba = cal.ba

    def tela(p, tela, R, t, papel):
        return {"nome": tela.nome, "papel": papel,
                "resolucao_px": [tela.px_w, tela.px_h],
                "tamanho_m": [round(tela.larg_m, 6), round(tela.alt_m, 6)],
                "R": np.round(R, 8).tolist(), "t": np.round(t, 6).tolist(),
                "quinas_m": np.round(p.quinas_tela(tela) @ R.T + t, 6).tolist(),
                "padrao": p.descricao()}
    d = {
        "versao": 1,
        "referencial": ("tela A: origem no centro da area acesa, x direita, y cima, z saindo "
                        "da tela; metros. Para cada tela: x_A = R @ x_tela + t. quinas_m: "
                        "inf-esq, inf-dir, sup-dir, sup-esq da area acesa, em A."),
        "data": time.strftime("%Y-%m-%d %H:%M:%S"),
        "telas": [tela(pa, pa.tela, np.eye(3), np.zeros(3), "referencia (webcam do tracking)"),
                  tela(pb, tb, cal.R, cal.t, "pose estimada")],
        "qualidade": {
            "rms_reproj_px": None if ba is None else round(ba.rms, 3),
            "rms_reproj_px_por_tela": None if ba is None else [round(x, 3) for x in ba.rms_por_tela],
            "rms_intrinsecos_px": round(cal.rms_intr, 3),
            "fotos_duas_telas": len(cal.aceitas) + len(cal.descartadas),
            "fotos_descartadas_media": cal.descartadas,
            "dispersao_entre_fotos": {"rot_graus": round(cal.disp_rot_graus, 3),
                                      "trans_mm": round(cal.disp_trans_mm, 2)},
            "incerteza_1sigma": None if ba is None else {
                "rot_graus": round(ba.sigma_rot_graus, 4), "trans_mm": round(ba.sigma_trans_mm, 3),
                "escala": None if math.isnan(ba.sigma_escala) else round(ba.sigma_escala, 5)},
            "escala_B_estimada": None if ba is None else round(ba.escala_B, 5),
            "ajuste_convergiu": None if ba is None else ba.sucesso,
        },
        "camera_celular": {"tamanho_px": list(tam_foto),
                           "K": np.round(cal.K if ba is None else _K(ba.intr), 3).tolist(),
                           "dist": np.round(cal.dist if ba is None else ba.intr[4:], 6).tolist()},
    }
    if extra:
        d.update(extra)
    return d


def _K(intr):
    return np.array([[intr[0], 0, intr[2]], [0, intr[1], intr[3]], [0, 0, 1.0]])


if __name__ == "__main__":
    print("Use: python calibrar_telas.py calcular [pasta_das_fotos]")
