"""Calibracao das telas de ponta a ponta, sem celular e sem monitor.

  1. calibrar_telas.py mostrar com dois monitores falsos e GUI falsa: abre uma
     janela por monitor, troca os papeis com t, grava o padroes.json certo;
  2. simular.py gera 10 fotos sinteticas de 12 MP (resposta conhecida);
  3. calibrar_telas.py calcular nessas fotos: erro contra a verdade abaixo
     dos limites, telas.json legivel pelo telas.py;
  4. calibrar_telas.py manual: a geometria de trena volta nas medidas dadas;
  5. o telas.json da calibracao alimenta o main.py (sem hardware): duas janelas.

    python testes/teste_calibracao.py
"""

import json
import os
import shutil
import subprocess
import sys

import _ambiente

_ambiente.stub_mediapipe()
os.environ["AP2_MONITORES_FALSOS"] = "1920x1080+1920+0"

import numpy as np  # noqa: E402

import config  # noqa: E402

LIMITES = {"rot_graus": 0.2, "trans_mm": 3.0, "pior_quina_mm": 3.0, "tamanho_pct": 0.5}


def teste_mostrar(falhas):
    import calibrar_telas
    gui = _ambiente.GuiFalsa(avancar_no_waitkey=True).instalar()
    destino = os.path.join(_ambiente.SAIDA, "padroes_mostrar.json")
    # quadro 3: esconde o rotulo; 5: troca os papeis; 7: troca de volta; 9: sai
    gui.reiniciar({3: " ", 5: "t", 7: "t", 9: "q"})
    cod = calibrar_telas.main(["mostrar", "-o", destino, "--diagonal", "27"])
    janelas = sorted({g[1] for g in gui.gravados})
    if cod != 0 or len(janelas) != 2:
        falhas.append(f"mostrar: codigo {cod}, janelas {janelas}")
        return
    with open(destino, encoding="utf-8") as fh:
        d = json.load(fh)
    mons = [t["monitor"]["dispositivo"] for t in d["telas"]]
    if [t["nome"] for t in d["telas"]] != ["notebook", "monitor"] or mons != ["FALSO0", "FALSO1"]:
        falhas.append(f"mostrar: padroes.json com telas/monitores errados: {mons}")
    if d.get("diagonal_pol_nominal") != 27:
        falhas.append("mostrar: diagonal nominal nao gravada")
    import padroes
    pads = padroes.de_json(d)
    diag = np.hypot(pads[1].tela.larg_m, pads[1].tela.alt_m) / 0.0254
    if abs(diag - 27) > 0.01:
        falhas.append(f"mostrar: monitor com diagonal {diag:.2f} em vez de 27")
    print(f"mostrar: janelas {janelas}, padroes.json ok ({mons})")


def teste_calcular(falhas):
    import calibrar_telas
    import telas
    pasta = os.path.join(_ambiente.SAIDA, "fotos_sim_teste")
    if os.path.isdir(pasta):
        shutil.rmtree(pasta)
    r = subprocess.run([sys.executable, os.path.join(_ambiente.PASTA, "simular.py"),
                        "--pasta", pasta, "--n", "10", "--nivel", "tipico",
                        "--semente", "7"], capture_output=True, text=True,
                       cwd=_ambiente.PASTA)
    if r.returncode != 0:
        falhas.append("simular.py falhou: " + r.stderr[-500:])
        return None
    saida = os.path.join(pasta, "telas.json")
    res = calibrar_telas.calcular([pasta], saida=saida,
                                  pasta_debug=os.path.join(pasta, "dbg"), verbose=False)
    e = res["erro"]
    print("calcular: erro " + ", ".join(f"{k} {v:.4f}" for k, v in e.items())
          + f"; {res['n_duas_telas']} fotos com as duas telas")
    for k, lim in LIMITES.items():
        if abs(e[k]) > lim:
            falhas.append(f"calcular: {k} = {e[k]:.4f} acima do limite {lim}")
    lista = telas.carregar(saida)
    if lista is None or len(lista) != 2:
        falhas.append("calcular: telas.json nao carrega no telas.py")
    if not os.path.exists(os.path.join(pasta, "dbg", "planta.png")):
        falhas.append("calcular: planta.png nao foi gravada")
    return saida


def teste_robustez(falhas, pasta_fotos):
    """Casos que a revisao levantou, reaproveitando as fotos simuladas:
    (a) uma foto de outro tamanho que vem PRIMEIRO na lista nao pode derrubar
        as outras; (b) diagonal nominal errada (27 em vez de 24) nao pode
        disparar o aviso de 'fotos discordam' nem estragar o resultado."""
    import cv2
    import calibrar_telas
    import detectar
    if pasta_fotos is None:
        return
    pasta = os.path.join(_ambiente.SAIDA, "fotos_sim_robustez")
    if os.path.isdir(pasta):
        shutil.rmtree(pasta)
    shutil.copytree(os.path.dirname(pasta_fotos), pasta,
                    ignore=shutil.ignore_patterns("dbg", "telas.json"))
    img = detectar.ler_foto(os.path.join(pasta, "foto_00.jpg"))
    detectar.gravar_imagem(os.path.join(pasta, "aaa_em_pe.jpg"), cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE))
    caminho = os.path.join(pasta, "padroes.json")
    with open(caminho, encoding="utf-8") as fh:
        d = json.load(fh)
    w, h = d["telas"][1]["tamanho_m"]
    d["telas"][1]["tamanho_m"] = [w * 27 / 24, h * 27 / 24]
    d["diagonal_pol_nominal"] = 27.0
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    res = calibrar_telas.calcular([pasta], saida=os.path.join(pasta, "telas.json"),
                                  pasta_debug=None, verbose=False)
    e, q = res["erro"], res["telas_json"]["qualidade"]
    print(f"robustez: {len(res['telas_json']['fotos'])} fotos usadas, erro pior quina "
          f"{e['pior_quina_mm']:.3f} mm, tamanho {e['tamanho_pct']:+.3f}%, dispersao "
          f"{q['dispersao_entre_fotos']}, avisos {res['avisos']}")
    if "aaa_em_pe.jpg" in res["telas_json"]["fotos"] or len(res["telas_json"]["fotos"]) != 10:
        falhas.append("robustez: a foto em pe devia ser ignorada e as 10 boas usadas")
    if e["pior_quina_mm"] > LIMITES["pior_quina_mm"] or abs(e["tamanho_pct"]) > LIMITES["tamanho_pct"]:
        falhas.append(f"robustez: diagonal nominal errada estragou o resultado {e}")
    if q["dispersao_entre_fotos"]["trans_mm"] > 2.0 or any("discordam" in a for a in res["avisos"]):
        falhas.append("robustez: diagonal nominal errada disparou a dispersao/aviso falso")


def teste_manual(falhas):
    import calibrar_telas
    import telas
    saida = os.path.join(_ambiente.SAIDA, "telas_manual.json")
    medidas = dict(angulo=35.0, folga=0.025, base=0.04, recuo=0.01)
    cod = calibrar_telas.main(["manual", "-o", saida, "--diagonal", "24"]
                              + sum([[f"--{k}", str(v)] for k, v in medidas.items()], []))
    lista = telas.carregar(saida)
    if cod != 0 or lista is None:
        falhas.append("manual: nao gerou telas.json")
        return
    a, b = lista
    # Sem inclinacao da tampa, a quina interna de baixo do monitor fica onde
    # as medidas dizem, no referencial do notebook.
    quina = b.para_mundo(np.array([-b.w_m / 2, -b.h_m / 2, 0.0]))
    esperado = np.array([a.w_m / 2 + medidas["folga"], -a.h_m / 2 + medidas["base"],
                         -medidas["recuo"]])
    ang = np.degrees(np.arccos(np.clip(b.normal @ np.array([0, 0, 1.0]), -1, 1)))
    if np.abs(quina - esperado).max() > 1e-9 or abs(ang - medidas["angulo"]) > 1e-6:
        falhas.append(f"manual: quina {quina} != {esperado} ou angulo {ang}")
    if b.normal[0] >= 0:
        falhas.append("manual: monitor da direita devia estar virado para a esquerda")
    # Com a tampa inclinada 15 graus, o monitor (em pe) fica inclinado no
    # referencial do notebook, e a quina continua na mesma altura da mesa.
    R, t = calibrar_telas.pose_manual(a.w_m, a.h_m, b.w_m, b.h_m, inclinacao=15.0,
                                      **medidas)
    R_mesa = calibrar_telas._rot_x(-15.0)
    c_nb = R_mesa @ np.array([0, a.h_m / 2, 0])
    quina_mesa = R_mesa @ (R @ np.array([-b.w_m / 2, -b.h_m / 2, 0]) + t) + c_nb
    if np.abs(quina_mesa - (esperado + [0, a.h_m / 2, 0])).max() > 1e-9:
        falhas.append(f"manual inclinado: quina na mesa {quina_mesa}")
    print(f"manual: quina interna {np.round(quina * 100, 2).tolist()} cm, angulo {ang:.2f}")


def teste_main_com_calibracao(falhas, telas_json):
    """O telas.json da calibracao (com os monitores falsos) roda no main.py."""
    if telas_json is None:
        return
    with open(telas_json, encoding="utf-8") as fh:
        d = json.load(fh)
    for t_json, disp, x in zip(d["telas"], ("FALSO0", "FALSO1"), (0, 1920)):
        t_json["monitor"] = {"dispositivo": disp, "x": x, "y": 0}
    caminho = os.path.join(_ambiente.SAIDA, "telas_calibrado_teste.json")
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    gui = _ambiente.GuiFalsa().instalar()
    _ambiente.instalar_tracking_falso(gui)
    import main as main_mod
    gui.reiniciar({8: "n", 10: "n", 12: "n", 14: "n", 18: "q"})
    main_mod.main(["--telas", caminho])
    janelas = sorted({g[1] for g in gui.gravados})
    if len(janelas) != 2:
        falhas.append(f"main com telas.json calibrado: janelas {janelas}")
    print(f"main.py com o telas.json calibrado: {len(gui.gravados)} imshow em {janelas}")


def main():
    falhas = []
    teste_mostrar(falhas)
    telas_json = teste_calcular(falhas)
    teste_robustez(falhas, telas_json)
    teste_manual(falhas)
    teste_main_com_calibracao(falhas, telas_json)
    for f in falhas:
        print("  " + f)
    return _ambiente.resultado(not falhas, "calibracao: mostrar, calcular (fotos "
                                           "simuladas), manual e main.py com o resultado")


if __name__ == "__main__":
    assert config.TELAS_FILE                      # o config da AP2 esta carregado
    sys.exit(main())
