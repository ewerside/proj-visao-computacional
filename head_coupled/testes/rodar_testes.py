"""Roda todos os testes automaticos e resume. Nao precisa de webcam, monitor
externo nem celular: tudo que depende de hardware e simulado.

    python testes/rodar_testes.py

Leva de 1 a 3 minutos (a calibracao gera 10 fotos sinteticas de 12 MP). Cada
teste tambem roda sozinho: python testes/teste_<nome>.py. As imagens e arquivos
gerados ficam em testes/saida/ (ignorada pelo git).
"""

import glob
import os
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))


def main():
    testes = sorted(glob.glob(os.path.join(AQUI, "teste_*.py")))
    resultados = []
    t_total = time.time()
    for caminho in testes:
        nome = os.path.basename(caminho)
        t0 = time.time()
        r = subprocess.run([sys.executable, caminho], cwd=os.path.dirname(AQUI),
                           capture_output=True, text=True)
        dt = time.time() - t0
        linhas = (r.stdout or "").strip().splitlines()
        final = linhas[-1] if linhas else ""
        ok = r.returncode == 0 and final.startswith("OK")
        resultados.append((nome, ok, dt, final))
        print(f"{'OK    ' if ok else 'FALHOU'}  {nome:32s} {dt:5.1f} s  {final[8:]}")
        if not ok:
            print("        --- saida ---")
            for linha in (linhas[-25:] + (r.stderr or "").strip().splitlines()[-25:]):
                print("        " + linha)
    n_ok = sum(ok for _n, ok, _d, _f in resultados)
    print(f"\n{n_ok}/{len(resultados)} testes OK em {time.time() - t_total:.0f} s")
    return 0 if n_ok == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
