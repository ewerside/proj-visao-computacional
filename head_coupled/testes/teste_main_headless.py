"""Roda o main.py de verdade, sem webcam, sem MediaPipe e sem janela.

Substitui so as bordas do sistema (ver _ambiente.py): MediaPipe, webcam, GUI
do cv2 e relogio. O resto (tracking, filtros, cena, render, HUD, teclas) e o
codigo real. Tres execucoes com o mesmo roteiro de teclas:

  1. o main.py da AP1 (do git), com o scene.py da AP1;
  2. o main.py novo com --uma-tela  -> tem de dar os MESMOS quadros, bit a bit;
  3. o main.py novo com um telas.json de duas telas (monitor falso a direita)
     -> duas janelas, a do monitor no monitor certo, todas as cenas, anaglifo,
     HUD e a tecla y da guinada sem erro.

    python testes/teste_main_headless.py
"""

import os
import sys

import _ambiente

_ambiente.stub_mediapipe()
os.environ["AP2_MONITORES_FALSOS"] = "1920x1080+1920+0"

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import config  # noqa: E402
import detectar  # noqa: E402
import telas  # noqa: E402

GUI = _ambiente.GuiFalsa().instalar()

# caixa, corredor, miniatura com anaglifo e olho so, barras. Sem o HUD de
# debug (d): a AP2 acrescentou nele a linha da guinada, de proposito.
TECLAS_AP1 = {12: "n", 20: "n", 28: "3", 34: "1", 38: "1", 40: "3", 41: "n",
              55: "n", 60: "q"}
# idem, depois sala e alinhamento (so com duas telas), anaglifo, y, d.
TECLAS_MULTI = {12: "n", 20: "n", 28: "3", 34: "3", 35: "n", 43: "n", 44: "d",
                48: "y", 50: "y", 52: "n", 60: "3", 64: "3", 65: "q"}


def rodar(main_mod, teclas, argv=None, guardar=()):
    GUI.reiniciar(teclas, guardar)
    if argv is None:
        main_mod.main()
    else:
        main_mod.main(argv)
    return list(GUI.gravados), dict(GUI.imagens)


def telas_de_teste(caminho):
    """Notebook + monitor 24" a direita, girado 35 graus para o usuario."""
    a = telas.tela_do_config()
    a.monitor = {"dispositivo": "FALSO0", "x": 0, "y": 0}
    R = telas.rot_y(-35.0)
    borda = np.array([a.w_m / 2 + 0.025, 0.04, -0.010])
    t = borda + R @ np.array([0.5313 / 2, 0.0, 0.0])
    b = telas.Tela("monitor", 0.5313, 0.2989, 1920, 1080, R, t,
                   {"dispositivo": "FALSO1", "x": 1920, "y": 0})
    telas.salvar([a, b], caminho, {"origem": "teste_main_headless"})


def main():
    import scene
    import tracking
    try:
        scene_ap1 = _ambiente.carregar_ap1("scene")
        main_ap1 = _ambiente.carregar_ap1("main", injetar={"scene": scene_ap1})
    except _ambiente.Pular as e:
        print(e)
        main_ap1 = None
    import main as main_novo
    assert main_novo.scn is scene

    falhas = []
    if main_ap1 is not None:
        _ambiente.instalar_tracking_falso(GUI, eixo=None)
        g_ap1, _ = rodar(main_ap1, TECLAS_AP1)
        _ambiente.instalar_tracking_falso(GUI, eixo=None)
        g_novo, img = rodar(main_novo, TECLAS_AP1, ["--uma-tela"], guardar=(11, 54))
        # Compara tudo menos a legenda do rodape (texto novo da tecla y).
        iguais = sum(a[:2] == b[:2] and a[3] == b[3] for a, b in zip(g_ap1, g_novo))
        print(f"AP1 x novo --uma-tela: {len(g_ap1)} x {len(g_novo)} quadros, "
              f"{iguais} identicos fora da legenda")
        if len(g_ap1) != len(g_novo) or iguais != len(g_ap1):
            falhas.append("modo de uma tela diferente da AP1")
        for (q, nome), im in img.items():
            detectar.gravar_imagem(os.path.join(_ambiente.SAIDA, f"main_uma_tela_q{q}.png"),
                        cv2.resize(im, (960, 540), interpolation=cv2.INTER_AREA))

    caminho = os.path.join(_ambiente.SAIDA, "telas_teste.json")
    telas_de_teste(caminho)
    # Eixo interocular de frente (rotacao identidade): k = 1, o numero nao muda,
    # mas o caminho da correcao de guinada roda de verdade.
    _ambiente.instalar_tracking_falso(GUI, eixo=np.array([1.0, 0.0, 0.0]))
    quadros = (11, 19, 27, 42, 51, 59)
    g_multi, img_multi = rodar(main_novo, TECLAS_MULTI, ["--telas", caminho],
                               guardar=quadros)
    janelas = sorted({g[1] for g in g_multi})
    print(f"duas telas: {len(g_multi)} imshow em {janelas}; posicoes {GUI.pos}")
    if len(janelas) != 2:
        falhas.append(f"esperava 2 janelas, vieram {janelas}")
    else:
        monitor = [n for n in janelas if n != main_novo.WINDOW][0]
        x, y = GUI.pos.get(monitor, (None, None))
        if x is None or not (1920 <= x < 3840):
            falhas.append(f"janela do monitor em x={x}, devia estar em 1920..3839")
        por_janela = {n: sum(1 for g in g_multi if g[1] == n) for n in janelas}
        if len(set(por_janela.values())) != 1:
            falhas.append(f"numero de quadros diferente por janela: {por_janela}")
        # As duas telas tem de mostrar coisas diferentes (nao a mesma imagem).
        for q in quadros:
            ims = [img_multi.get((q, n)) for n in janelas]
            if all(im is not None for im in ims) and np.array_equal(ims[0], ims[1]):
                falhas.append(f"quadro {q}: as duas telas iguais")
            if all(im is not None for im in ims):
                lado = np.hstack([cv2.resize(im, (640, 360), interpolation=cv2.INTER_AREA)
                                  for im in ims])
                detectar.gravar_imagem(os.path.join(_ambiente.SAIDA, f"main_duas_telas_q{q}.png"),
                            lado)
    topo = [a for a in GUI.propriedades if len(a) >= 3 and a[1] == getattr(
        cv2, "WND_PROP_TOPMOST", -999)]
    if config.MONITOR_SEMPRE_NO_TOPO and hasattr(cv2, "WND_PROP_TOPMOST") and not topo:
        falhas.append("janela do monitor nao ficou sempre no topo")
    assert hasattr(tracking, "find_landmarks_pose")

    for f in falhas:
        print("  " + f)
    return _ambiente.resultado(not falhas, "main.py sem hardware: uma tela = AP1; "
                                           "duas telas abrem e desenham")


if __name__ == "__main__":
    sys.exit(main())
