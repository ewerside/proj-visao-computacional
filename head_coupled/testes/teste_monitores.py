"""monitores.py e testar_monitores.py sem Windows: monitores falsos e GUI falsa.

  - escolha do notebook (config, nome, tamanho do driver, principal);
  - achar_monitor pelo nome do dispositivo e pela posicao;
  - testar_monitores.py abre uma janela por monitor, cada uma no seu lugar,
    aceita t e sai com q.

    python testes/teste_monitores.py
"""

import os
import sys

import _ambiente

os.environ["AP2_MONITORES_FALSOS"] = "2560x1440+-2560+0"

import config  # noqa: E402
import monitores  # noqa: E402


def main():
    falhas = []
    mons = monitores.listar_monitores()
    if [m.dispositivo for m in mons] != ["FALSO0", "FALSO1"] or mons[1].x != -2560:
        falhas.append(f"monitores falsos errados: {mons}")
    if monitores.escolher_notebook(mons) != 0:
        falhas.append("o notebook devia ser o FALSO0 (tamanho do driver = SCREEN_W)")
    antigo = config.MONITOR_NOTEBOOK
    try:
        config.MONITOR_NOTEBOOK = "falso1"
        if monitores.escolher_notebook(mons) != 1:
            falhas.append("config.MONITOR_NOTEBOOK por nome nao foi respeitado")
        config.MONITOR_NOTEBOOK = 1
        if monitores.escolher_notebook(mons) != 1:
            falhas.append("config.MONITOR_NOTEBOOK por indice nao foi respeitado")
    finally:
        config.MONITOR_NOTEBOOK = antigo
    if monitores.achar_monitor(mons, {"dispositivo": "FALSO1"}) is not mons[1]:
        falhas.append("achar_monitor por nome")
    if monitores.achar_monitor(mons, {"dispositivo": "X", "x": -2560, "y": 0}) is not mons[1]:
        falhas.append("achar_monitor pela posicao")
    if monitores.achar_monitor(mons, [0, 0]) is not mons[0]:
        falhas.append("achar_monitor com a forma antiga [x, y]")
    if monitores.achar_monitor(mons, {"dispositivo": "NENHUM", "x": 7, "y": 7}) is not None:
        falhas.append("achar_monitor devia devolver None")

    gui = _ambiente.GuiFalsa(avancar_no_waitkey=True).instalar()
    import testar_monitores
    gui.reiniciar({3: "t", 5: "a", 8: "q"})
    cod = testar_monitores.main()
    janelas = sorted({g[1] for g in gui.gravados})
    if cod != 0 or len(janelas) != 2:
        falhas.append(f"testar_monitores: codigo {cod}, janelas {janelas}")
    if gui.pos.get("teste monitor 1", (0, 0))[0] >= 0:
        falhas.append(f"janela do monitor da esquerda fora do lugar: {gui.pos}")
    for f in falhas:
        print("  " + f)
    return _ambiente.resultado(not falhas, "monitores.py e testar_monitores.py")


if __name__ == "__main__":
    sys.exit(main())
