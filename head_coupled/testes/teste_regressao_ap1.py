"""Regressao do desenho: o caminho novo, com UMA tela na pose identidade, tem
de desenhar exatamente o mesmo que o scene.py da AP1 (tirado do git).

Para cada cenario da AP1, varios instantes da animacao e varias posicoes do
olho (inclusive o limite EYE_Z_MIN), compara canvases 1920x1080:
  B  scene.render novo                                   -> identico
  C  telas.render_tela, tela identidade, sem recorte     -> identico
  D  idem C forcando a troca de base (P - t) @ R, R = I  -> identico
Tambem confere a geometria construida (vertices, normais, cores), bit a bit.

    python testes/teste_regressao_ap1.py
"""

import sys

import _ambiente

import numpy as np

import config
import scene as scn
import telas

EYES = [(0.0, 0.0, 0.60), (0.12, 0.05, 0.45), (-0.20, -0.08, 0.75),
        (0.30, -0.15, 0.35), (0.0, 0.0, config.EYE_Z_MIN)]
T_ANIM = [0.0, 1.234, 4.5]


def mesma_geometria(a, b):
    if len(a) != len(b):
        return False
    for oa, ob in zip(a, b):
        if oa["kind"] != ob["kind"] or oa["color"] != ob["color"]:
            return False
        if not np.array_equal(oa["v"], ob["v"]):
            return False
        na, nb = oa.get("n"), ob.get("n")
        if (na is None) != (nb is None) or (na is not None and not np.array_equal(na, nb)):
            return False
    return True


def main():
    try:
        ap1 = _ambiente.carregar_ap1("scene")
    except _ambiente.Pular as e:
        print(e)
        return _ambiente.resultado(True, "regressao AP1 pulada (sem git)")
    W, H = config.SCREEN_PX_W, config.SCREEN_PX_H
    cv_a, cv_b, cv_c, cv_d = (np.zeros((H, W, 3), np.uint8) for _ in range(4))
    t_id = telas.tela_do_config()
    t_forcada = telas.tela_do_config()
    t_forcada.identidade = False          # obriga o caminho (P - t) @ R
    falhas, casos = [], 0
    # So a cena que o projeto final manteve identica a da AP1. O corredor e a
    # vila ganharam pecas novas e a das barras saiu.
    for nome in [n for n in ap1.CENAS if n == "caixa"]:
        if not mesma_geometria(ap1.build(nome), scn.build(nome)):
            falhas.append(f"{nome}: geometria estatica diferente")
        for t in T_ANIM:
            if not mesma_geometria(ap1.dinamico(nome, t), scn.dinamico(nome, t)):
                falhas.append(f"{nome} t={t}: geometria dinamica diferente")
            for eye in EYES:
                eye = np.array(eye, float)
                cena_a = ap1.build(nome) + ap1.dinamico(nome, t)
                cena_n = scn.build(nome) + scn.dinamico(nome, t)
                ap1.render(eye, ap1.order_faces(cena_a, eye), cv_a)
                ordem = scn.order_faces(cena_n, eye)
                scn.render(eye, ordem, cv_b)
                telas.render_tela(eye, ordem, t_id, cv_c, z_corte=None)
                telas.render_tela(eye, ordem, t_forcada, cv_d, z_corte=None)
                casos += 1
                for k, cv in (("B", cv_b), ("C", cv_c), ("D", cv_d)):
                    n = int(np.count_nonzero(cv != cv_a))
                    if n:
                        falhas.append(f"{nome} t={t} olho={tuple(eye)}: {k} difere "
                                      f"em {n} valores")
    for f in falhas[:20]:
        print("  " + f)
    return _ambiente.resultado(
        not falhas, f"regressao AP1: {casos} casos x 3 caminhos, "
                    f"{len(falhas)} diferencas")


if __name__ == "__main__":
    sys.exit(main())
