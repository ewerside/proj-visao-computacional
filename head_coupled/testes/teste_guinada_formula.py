"""A correcao de guinada (tracking.fator_escorco / head_position) em casos com
resposta conhecida, sem webcam e sem MediaPipe:

  - cabeca de frente (eixo = x da imagem): k = 1, nada muda;
  - guinada pura psi com a cabeca no eixo optico: k = cos(psi);
  - cabeca fora do eixo (angulo phi) e guinada psi: k = cos(psi+phi)/cos(phi);
  - EXATIDAO: os dois olhos projetados por uma camera pinhole de verdade, em
    poses aleatorias; head_position com o eixo verdadeiro recupera o Z exato
    (erro ~1e-12 m) e X, Y com menos de 2 mm (o ponto medio das duas irises na
    imagem nao e exatamente a projecao do ponto medio 3D), enquanto sem
    correcao o erro chega a dezenas de centimetros;
  - irises no mesmo pixel: devolve NaN em vez de quebrar.

    python testes/teste_guinada_formula.py
"""

import math
import sys

import _ambiente

_ambiente.stub_mediapipe()

import numpy as np  # noqa: E402

import config  # noqa: E402
import tracking  # noqa: E402

F, W, H = 970.0, 1280, 720


def projetar(p):
    """Camera pinhole no referencial da imagem: x direita, y baixo, z frente."""
    return np.array([W / 2 + F * p[0] / p[2], H / 2 + F * p[1] / p[2]])


def main():
    falhas = []
    meio = (W / 2, H / 2)
    k = tracking.fator_escorco(np.array([1.0, 0, 0]), meio, (H, W), F)
    if abs(k - 1) > 1e-12:
        falhas.append(f"de frente: k = {k}")
    for psi in (10, 20, 30):
        a = np.array([math.cos(math.radians(psi)), 0, math.sin(math.radians(psi))])
        k = tracking.fator_escorco(a, meio, (H, W), F)
        if abs(k - math.cos(math.radians(psi))) > 1e-12:
            falhas.append(f"guinada pura {psi}: k = {k}")
        phi = 15.0
        mid = (W / 2 + F * math.tan(math.radians(phi)), H / 2)
        k = tracking.fator_escorco(a, mid, (H, W), F)
        esperado = math.cos(math.radians(psi + phi)) / math.cos(math.radians(phi))
        if abs(k - esperado) > 1e-12:
            falhas.append(f"fora do eixo psi={psi}: k = {k}, esperado {esperado}")

    rng = np.random.default_rng(3)
    pior_z, pior_xy, pior_sem = 0.0, 0.0, 0.0
    for _ in range(2000):
        P = np.array([rng.uniform(-0.2, 0.2), rng.uniform(-0.15, 0.1), rng.uniform(0.4, 0.9)])
        psi, teta = np.radians(rng.uniform(-40, 40)), np.radians(rng.uniform(-20, 20))
        a = np.array([math.cos(psi) * math.cos(teta), math.sin(teta),
                      math.sin(psi) * math.cos(teta)])
        if not (tracking.K_MIN < np.hypot(a[0], a[1]) and
                np.hypot(a[0], a[1]) < tracking.K_MAX):
            continue
        d = config.IPD_REAL / 2 * a
        pts = np.zeros((478, 2))
        pts[tracking.IRIS_L] = projetar(P - d)
        pts[tracking.IRIS_R] = projetar(P + d)
        k = tracking.fator_escorco(a, (pts[tracking.IRIS_L] + pts[tracking.IRIS_R]) / 2,
                                   (H, W), F)
        if not (tracking.K_MIN < k < tracking.K_MAX):
            continue                                   # fora da trava de seguranca
        verdade = np.array([P[0], -P[1], P[2]])        # head_position: Y para cima
        com = tracking.head_position(pts, (H, W), F, a)
        sem = tracking.head_position(pts, (H, W), F, None)
        pior_z = max(pior_z, float(abs(com[2] - verdade[2])))
        pior_xy = max(pior_xy, float(np.abs(com[:2] - verdade[:2]).max()))
        pior_sem = max(pior_sem, float(np.abs(sem - verdade).max()))
    print(f"2000 poses: com correcao, pior erro em Z {pior_z:.1e} m e em X/Y "
          f"{pior_xy * 1000:.2f} mm; sem correcao {pior_sem * 100:.1f} cm")
    if pior_z > 1e-9:
        falhas.append(f"Z corrigido nao e exato: erro {pior_z} m")
    if pior_xy > 0.002:
        falhas.append(f"X/Y corrigidos erram {pior_xy * 1000:.2f} mm (limite 2 mm)")
    if pior_sem < 0.02:
        falhas.append("sem correcao o erro devia ser de centimetros")

    pts = np.zeros((478, 2))
    pts[tracking.IRIS_L] = pts[tracking.IRIS_R] = (640, 360)
    if np.isfinite(tracking.head_position(pts, (H, W), F)).any():
        falhas.append("irises no mesmo pixel deviam dar NaN")
    for f in falhas:
        print("  " + f)
    return _ambiente.resultado(not falhas, "formula da correcao de guinada")


if __name__ == "__main__":
    sys.exit(main())
