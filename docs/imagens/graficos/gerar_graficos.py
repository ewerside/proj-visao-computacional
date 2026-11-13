"""Gera os graficos do artigo e dos slides a partir dos dados desta pasta.

    python docs/imagens/graficos/gerar_graficos.py

Dados (pasta dados/):
  simulado_*.json   saida de `python head_coupled/avaliar.py simulado --json ...`
                    (erro contra a verdade, por nivel, semente, numero de fotos e metodo)
  real_13nov.json   saida de `python head_coupled/avaliar.py real <fotos> --json ...`
                    (repetibilidade nas 12 fotos reais de 13/11/2026)

Saidas: erro_simulado_por_fotos.png, repetibilidade_fotos_reais.png e as mesmas
tabelas em CSV (para quem preferir os numeros).
"""

import csv
import glob
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(AQUI, "dados")

# Paleta categorica validada (azul, laranja, verde-agua), na mesma ordem nos
# dois graficos: a cor acompanha o metodo.
METODOS = [("PnP+mean", "PnP + média", "#2a78d6"),
           ("BA", "Ajuste de feixes", "#eb6834"),
           ("BA+size", "Ajuste de feixes + tamanho", "#1baf7a")]
APELIDOS = {"PnP+media": "PnP+mean", "BA+tam": "BA+size"}
TEXTO, FRACO, GRADE, FUNDO = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRADE,
                     "axes.labelcolor": FRACO, "xtick.color": FRACO, "ytick.color": FRACO,
                     "figure.facecolor": FUNDO, "axes.facecolor": FUNDO})


def _limpar(ax):
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.grid(axis="y", color=GRADE, linewidth=1)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def simulado():
    linhas = []
    for arq in sorted(glob.glob(os.path.join(DADOS, "simulado_*.json"))):
        with open(arq, encoding="utf-8") as fh:
            linhas += [l_ for l_ in json.load(fh) if "falha" not in l_]
    niveis = [("tipico", "Fotos típicas"), ("ruim", "Fotos ruins")]
    ns = sorted({l_["n"] for l_ in linhas})
    fig, eixos = plt.subplots(1, 2, figsize=(9.6, 3.9), sharey=True)
    tabela = []
    for ax, (nivel, titulo) in zip(eixos, niveis):
        for chave, nome, cor in METODOS:
            med = []
            for n in ns:
                v = [l_["pior_quina_mm"] for l_ in linhas
                     if l_["nivel"] == nivel and l_["n"] == n
                     and APELIDOS.get(l_["metodo"], l_["metodo"]) == chave]
                med.append(float(np.median(v)) if v else np.nan)
                if v:
                    tabela.append([nivel, n, nome, len(v), round(float(np.median(v)), 3),
                                   round(float(np.max(v)), 3)])
            ax.plot(ns, med, color=cor, linewidth=2, marker="o", markersize=7,
                    markeredgecolor=FUNDO, markeredgewidth=2, label=nome)
        ax.set_title(titulo, loc="left", color=TEXTO, fontsize=12, fontweight="bold")
        ax.set_xticks(ns)
        ax.set_xlabel("número de fotos")
        ax.set_xlim(ns[0] - 0.8, ns[-1] + 0.8)
        _limpar(ax)
    eixos[0].set_ylabel("erro na pior quina do monitor (mm)")
    eixos[0].set_ylim(bottom=0)
    eixos[0].legend(frameon=False, loc="upper right", fontsize=10, labelcolor=TEXTO)
    fig.suptitle("Calibração simulada: erro contra a verdade, mediana de 5 conjuntos de fotos",
                 x=0.012, ha="left", color=TEXTO, fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(AQUI, "erro_simulado_por_fotos.png"), dpi=200)
    plt.close(fig)
    with open(os.path.join(AQUI, "erro_simulado_por_fotos.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["nivel", "fotos", "metodo", "conjuntos", "pior_quina_mediana_mm",
                    "pior_quina_maxima_mm"])
        w.writerows(tabela)


def real():
    with open(os.path.join(DADOS, "real_13nov.json"), encoding="utf-8") as fh:
        linhas = {APELIDOS.get(l_["metodo"], l_["metodo"]): l_ for l_ in json.load(fh)}
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    nomes, vals, maxs, cores = [], [], [], []
    for chave, nome, cor in METODOS:
        nomes.append(nome.replace(" + ", "\n+ "))
        vals.append(linhas[chave]["desvio_padrao_mm"])
        maxs.append(linhas[chave]["desvio_max_mm"])
        cores.append(cor)
    barras = ax.bar(nomes, vals, color=cores, width=0.5)
    for b, v, m in zip(barras, vals, maxs):
        ax.annotate(f"{v:.1f} mm", (b.get_x() + b.get_width() / 2, v), xytext=(0, 6),
                    textcoords="offset points", ha="center", color=TEXTO, fontsize=12,
                    fontweight="bold")
        ax.annotate(f"máx. {m:.1f}", (b.get_x() + b.get_width() / 2, v), xytext=(0, 22),
                    textcoords="offset points", ha="center", color=FRACO, fontsize=9)
    ax.set_ylabel("desvio padrão das quinas (mm)")
    ax.set_ylim(0, max(vals) * 1.4)
    ax.set_title("Fotos reais: quanto a posição do monitor muda\nentre 30 subconjuntos de 10 fotos",
                 loc="left", color=TEXTO, fontsize=12, fontweight="bold")
    _limpar(ax)
    ax.tick_params(axis="x", labelcolor=TEXTO)
    fig.tight_layout()
    fig.savefig(os.path.join(AQUI, "repetibilidade_fotos_reais.png"), dpi=200)
    plt.close(fig)
    with open(os.path.join(AQUI, "repetibilidade_fotos_reais.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metodo", "desvio_padrao_mm", "desvio_maximo_mm", "rot_max_graus",
                    "diagonal_pol"])
        for chave, nome, _cor in METODOS:
            l_ = linhas[chave]
            w.writerow([nome, round(l_["desvio_padrao_mm"], 2), round(l_["desvio_max_mm"], 2),
                        round(l_["rot_max_graus"], 3), round(l_["diagonal_pol"], 1)])


if __name__ == "__main__":
    simulado()
    real()
    print("graficos gravados em", AQUI)
