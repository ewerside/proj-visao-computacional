"""Avaliacao quantitativa da calibracao das telas: compara os estimadores.

Tres estimadores da pose do monitor no referencial do notebook:
    PnP+media : PnP por foto + media robusta entre as fotos (calibracao.calibrar(ba=False))
    BA        : ajuste de feixes, tamanho do monitor conhecido
    BA+tam    : ajuste de feixes, tamanho do monitor tambem estimado (padrao do calcular)

Dois modos:

    python avaliar.py simulado [--niveis limpo tipico ruim] [--sementes 5] [--ns 4 10 15]
        Fotos sinteticas (simular.py) com verdade conhecida. Para cada nivel e
        semente gera 15 fotos e usa as N primeiras. Erro de cada estimador contra
        a verdade: rotacao (graus), translacao (mm) e pior quina do monitor (mm).
        E a Tabela II do artigo. Leva ~1 min por semente.

    python avaliar.py real [pasta_das_fotos] [--subconjuntos 30] [--n 10]
        Fotos reais do celular (padrao: fotos/, com o padroes.json do mostrar).
        Sem verdade de referencia, mede a REPETIBILIDADE: calibra com varios
        subconjuntos aleatorios de N fotos e relata o quanto as quinas do monitor
        mudam de um subconjunto para outro (desvio padrao e maximo, em mm).

Nenhum dos modos grava telas.json. --json <arquivo> guarda os numeros.
"""

import argparse
import json
import os

import numpy as np

import calibracao
import config
import detectar
import padroes
import simular

METODOS = (("PnP+media", dict(ba=False)),
           ("BA", dict(ba=True, estimar_escala=False)),
           ("BA+tam", dict(ba=True, estimar_escala=True)))
N_POOL = 15


def _duas_telas(dets):
    return all(d is not None and d.n >= calibracao.N_MIN_VISTA for d in dets)


def _quinas(pads, cal):
    return calibracao.quinas_no_mundo(pads[1], cal.R, cal.t, cal.escala_B)


def _med_max(v):
    return f"{np.median(v):.3f} ({np.max(v):.3f})"


def cmd_simulado(args):
    pads = padroes.padroes_projeto()
    cena = simular.cena_padrao(pads)
    cam = simular.Camera()
    det = detectar.Detector(pads)
    Rv, tv = cena.poses[1]
    Qv = pads[1].quinas_tela() @ Rv.T + tv
    linhas = []
    for nivel in args.niveis:
        for semente in range(1, args.sementes + 1):
            fotos = simular.gerar_fotos(cena, cam, simular.NIVEIS[nivel], N_POOL, semente=semente)
            dets = [det.detectar(f["img"]) for f in fotos]
            del fotos
            print(f"[{nivel}, semente {semente}] {sum(map(_duas_telas, dets))}/{N_POOL} fotos "
                  "com as duas telas", flush=True)
            for n in args.ns:
                for nome, kw in METODOS:
                    try:
                        cal = calibracao.calibrar(dets[:n], (cam.w, cam.h), **kw)
                    except RuntimeError as e:
                        print(f"   N={n} {nome}: falhou ({e})")
                        continue
                    linhas.append({
                        "nivel": nivel, "semente": semente, "n": n, "metodo": nome,
                        "rot_graus": float(calibracao.angulo_graus(Rv, cal.R)),
                        "trans_mm": float(1000 * np.linalg.norm(cal.t - tv)),
                        "pior_quina_mm": float(1000 * np.max(
                            np.linalg.norm(_quinas(pads, cal) - Qv, axis=1))),
                        "tempo_s": float(sum(cal.tempo_s.values()))})
    print("\nErro contra a verdade: mediana (maximo) entre as sementes")
    print(f"{'nivel':8s} {'N':>3s} {'metodo':10s} {'rot (graus)':>16s} {'trans (mm)':>16s} "
          f"{'pior quina (mm)':>16s} {'tempo (s)':>10s}")
    for nivel in args.niveis:
        for n in args.ns:
            for nome, _kw in METODOS:
                g = [l_ for l_ in linhas
                     if (l_["nivel"], l_["n"], l_["metodo"]) == (nivel, n, nome)]
                if g:
                    print(f"{nivel:8s} {n:3d} {nome:10s} "
                          f"{_med_max([l_['rot_graus'] for l_ in g]):>16s} "
                          f"{_med_max([l_['trans_mm'] for l_ in g]):>16s} "
                          f"{_med_max([l_['pior_quina_mm'] for l_ in g]):>16s} "
                          f"{np.median([l_['tempo_s'] for l_ in g]):10.2f}")
    return linhas


def cmd_real(args):
    import calibrar_telas
    pasta = args.fotos or calibrar_telas.PASTA_FOTOS
    arquivos, _heic = calibrar_telas.listar_fotos([pasta])
    local = os.path.join(pasta, "padroes.json")
    caminho_pad = local if os.path.exists(local) else config.PADROES_FILE
    if not arquivos or not os.path.exists(caminho_pad):
        raise SystemExit(f"preciso de fotos em {pasta} e do {caminho_pad} "
                         "(rode antes: python calibrar_telas.py mostrar)")
    with open(caminho_pad, encoding="utf-8") as fh:
        pads = padroes.de_json(json.load(fh))
    det = detectar.Detector(pads)
    dets, tam = [], None
    for arq in arquivos:
        img = detectar.ler_foto(arq)
        r = det.detectar(img)
        if _duas_telas(r) and tam in (None, (img.shape[1], img.shape[0])):
            tam = (img.shape[1], img.shape[0])
            dets.append(r)
    print(f"{len(dets)} de {len(arquivos)} fotos com as duas telas")
    n = min(args.n, len(dets) - 1)
    if n < 4:
        raise SystemExit("poucas fotos com as duas telas para avaliar (minimo 5)")

    rng = np.random.default_rng(1)
    grupos = [sorted(rng.choice(len(dets), n, replace=False)) for _ in range(args.subconjuntos)]
    linhas = []
    print(f"\nTodas as {len(dets)} fotos, e repetibilidade em {args.subconjuntos} subconjuntos "
          f"de {n} fotos (desvio das quinas do monitor em relacao a media dos subconjuntos)")
    print(f"{'metodo':10s} {'centro do monitor (cm)':>26s} {'diag (pol)':>10s} "
          f"{'desvio padrao (mm)':>19s} {'maximo (mm)':>12s} {'rot max (graus)':>16s}")
    for nome, kw in METODOS:
        cal = calibracao.calibrar(dets, tam, **kw)
        Q, R = [], []
        for g in grupos:
            try:
                c = calibracao.calibrar([dets[i] for i in g], tam, **kw)
            except RuntimeError:
                continue
            Q.append(_quinas(pads, c))
            R.append(c.R)
        Q = np.array(Q)
        desvio = 1000 * np.linalg.norm(Q - Q.mean(0), axis=2)      # subconjunto x quina
        rot = max(calibracao.angulo_graus(calibracao.media_rotacoes(R), Ri) for Ri in R)
        tb = pads[1].tela.escalada(cal.escala_B)
        diag = float(np.hypot(tb.larg_m, tb.alt_m) / 0.0254)
        centro = np.round(100 * cal.t, 1).tolist()
        dp = float(np.sqrt((desvio ** 2).mean()))
        print(f"{nome:10s} {str(centro):>26s} {diag:10.1f} {dp:19.2f} "
              f"{desvio.max():12.2f} {rot:16.3f}")
        linhas.append({"metodo": nome, "centro_cm": centro, "diagonal_pol": diag,
                       "desvio_padrao_mm": dp, "desvio_max_mm": float(desvio.max()),
                       "rot_max_graus": float(rot), "subconjuntos": len(Q), "n": n,
                       "rms_px": None if cal.ba is None else cal.ba.rms})
    return linhas


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("simulado", help="erro contra a verdade em fotos sinteticas")
    s.add_argument("--niveis", nargs="+", default=["limpo", "tipico", "ruim"],
                   choices=list(simular.NIVEIS))
    s.add_argument("--sementes", type=int, default=5)
    s.add_argument("--ns", type=int, nargs="+", default=[4, 10, 15])
    r = sub.add_parser("real", help="repetibilidade nas fotos reais do celular")
    r.add_argument("fotos", nargs="?")
    r.add_argument("--subconjuntos", type=int, default=30)
    r.add_argument("--n", type=int, default=10)
    for p in (s, r):
        p.add_argument("--json", help="grava os numeros neste arquivo")
    args = ap.parse_args(argv)
    linhas = cmd_simulado(args) if args.cmd == "simulado" else cmd_real(args)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(linhas, fh, indent=1)
        print("gravado em", args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
