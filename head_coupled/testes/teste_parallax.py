"""Menu do Parallax sem monitor, sem webcam e sem mouse de verdade.

  1. todas as telas do menu desenham, e cada uma tem botoes clicaveis;
  2. clique simulado em "Uma tela" leva ao seletor de cenas;
  3. sem telas.json o cartao "Duas telas" fica travado e avisa para calibrar;
  4. uma cena de uma tela roda pelo menu (com anaglifo) e volta ao menu;
  5. com um telas.json de duas telas, uma cena de duas telas roda e volta;
  6. os ajustes do menu (ajustes.json) valem sobre os padroes do config.

    python testes/teste_parallax.py
"""

import json
import os
import subprocess
import sys

import _ambiente

_ambiente.stub_mediapipe()
os.environ["AP2_MONITORES_FALSOS"] = "1920x1080+1920+0"

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import config  # noqa: E402
import telas  # noqa: E402

GUI = _ambiente.GuiFalsa().instalar()
MOUSE = {}
cv2.setMouseCallback = lambda nome, fn, *a: MOUSE.__setitem__(nome, fn)


def clicar(app, x, y):
    MOUSE[app.__class__.__module__ and "Parallax"](cv2.EVENT_LBUTTONUP, x, y, 0, None)
    alvo = app._sobre(app.clique)
    app.clique = None
    if alvo is not None:
        alvo.acao()
    app.desenhar()


def main():
    import parallax
    falhas = []
    saida = os.path.join(_ambiente.SAIDA, "parallax")
    os.makedirs(saida, exist_ok=True)
    telas_json = os.path.join(saida, "telas.json")
    original = config.TELAS_FILE
    config.TELAS_FILE = telas_json           # nunca mexe na calibracao de verdade
    if os.path.exists(telas_json):
        os.remove(telas_json)
    ultimo = {}
    imshow = cv2.imshow

    def grava(nome, img):
        ultimo["img"] = img
        return imshow(nome, img)

    cv2.imshow = grava
    try:
        app = parallax.App()
        for tela in ("inicio", "uma", "calibrar", "config"):
            app.ir(tela)
            app.desenhar()
            if len(app.botoes) < 2:
                falhas.append(f"tela {tela}: so {len(app.botoes)} botoes")
            cv2.imwrite(os.path.join(saida, f"menu_{tela}.png"),
                        cv2.resize(ultimo["img"], (960, 540), interpolation=cv2.INTER_AREA))

        # 2 e 3: cliques nos cartoes do inicio.
        app.ir("inicio")
        app.desenhar()
        cartoes = [b for b in app.botoes if b.caixa[3] - b.caixa[1] > app.px(200)]
        if len(cartoes) != 4:
            falhas.append(f"inicio: esperava 4 cartoes, vieram {len(cartoes)}")
        elif cartoes[1].ativo:
            falhas.append("sem calibracao, o cartao Duas telas deveria estar travado")
        else:
            x0, y0, x1, y1 = cartoes[0].caixa
            clicar(app, (x0 + x1) // 2, (y0 + y1) // 2)
            if app.tela != "uma":
                falhas.append(f"clique em Uma tela levou a {app.tela!r}")

        # 4: cena de uma tela pelo menu, com anaglifo, e volta.
        app.anaglifo = True
        _ambiente.instalar_tracking_falso(GUI, eixo=None)
        GUI.reiniciar({6: "n", 12: "q"})
        app.rodar("corredor", False)
        n_cena = len(GUI.gravados)
        if n_cena < 10 or app.aviso:
            falhas.append(f"cena de uma tela: {n_cena} quadros, aviso {app.aviso}")

        # 5: duas telas com um telas.json de teste.
        a = telas.tela_do_config()
        a.monitor = {"dispositivo": "FALSO0", "x": 0, "y": 0}
        R = telas.rot_y(-35.0)
        t = np.array([a.w_m / 2 + 0.025, 0.04, -0.010]) + R @ np.array([0.5313 / 2, 0.0, 0.0])
        b = telas.Tela("monitor", 0.5313, 0.2989, 1920, 1080, R, t,
                       {"dispositivo": "FALSO1", "x": 1920, "y": 0})
        telas.salvar([a, b], telas_json, {"origem": "teste_parallax"})
        lista, motivo = app.estado_duas_telas()
        if motivo:
            falhas.append(f"com telas.json, duas telas ainda travado: {motivo}")
        else:
            app.ir("duas")
            app.desenhar()
            cv2.imwrite(os.path.join(saida, "menu_duas.png"),
                        cv2.resize(ultimo["img"], (960, 540), interpolation=cv2.INTER_AREA))
            _ambiente.instalar_tracking_falso(GUI, eixo=np.array([1.0, 0.0, 0.0]))
            GUI.reiniciar({6: "3", 8: "n", 14: "q"})
            app.rodar("planeta", True)
            janelas = sorted({g[1] for g in GUI.gravados if g[1] != parallax.JANELA})
            if len(janelas) != 2 or app.aviso:
                falhas.append(f"cena de duas telas: janelas {janelas}, aviso {app.aviso}")
        print(f"menu: telas desenhadas; cena de uma tela {n_cena} quadros; duas telas ok")
    finally:
        cv2.imshow = imshow
        config.TELAS_FILE = original

    # 6: ajustes.json vale sobre os padroes (em outro processo, para nao sujar este).
    ajustes = config.AJUSTES_FILE
    if os.path.exists(ajustes):
        print("ajustes.json do usuario presente: teste dos ajustes pulado")
    else:
        try:
            with open(ajustes, "w", encoding="utf-8") as fh:
                json.dump({"SCREEN_W": 0.31, "SCREEN_H": 0.174, "CELULAR_TUNEL": False}, fh)
            r = subprocess.run([sys.executable, "-c",
                                "import config; print(config.SCREEN_W, config.SCREEN_H, "
                                "round(config.CAM_OFFSET_Y, 4), config.CELULAR_TUNEL)"],
                               capture_output=True, text=True, cwd=_ambiente.PASTA)
        finally:
            os.remove(ajustes)
        if r.stdout.split() != ["0.31", "0.174", "0.097", "False"]:
            falhas.append(f"ajustes.json nao foi aplicado: {r.stdout!r} {r.stderr[-200:]!r}")

    for f in falhas:
        print("  " + f)
    return _ambiente.resultado(not falhas, "menu do Parallax: telas, cliques, trava das duas "
                               "telas, cenas pelo menu e ajustes" if not falhas else "; ".join(falhas))


if __name__ == "__main__":
    sys.exit(main())
