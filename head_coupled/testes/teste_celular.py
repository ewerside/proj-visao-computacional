"""Pagina do celular de ponta a ponta, sem celular, sem monitor e sem rede.

  1. sobe o celular.Servidor em 127.0.0.1, numa porta livre;
  2. confere que sem o codigo do QR nada responde (404) e que a pagina abre;
  3. manda um arquivo que nao e foto e uma foto sem tela nenhuma: recusadas;
  4. manda 8 fotos sinteticas de 12 MP (simular.py), como o celular faria;
  5. pede o calculo: telas.json gravado, erro contra a verdade dentro do limite;
  6. calibrar_telas.py celular com GUI falsa: QR code na tela e saida com q.

    python testes/teste_celular.py
"""

import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request

import _ambiente

_ambiente.stub_mediapipe()
os.environ["AP2_MONITORES_FALSOS"] = "1920x1080+1920+0"

import cv2  # noqa: E402
import numpy as np  # noqa: E402

N_FOTOS = 8
LIMITE_QUINA_MM = 3.0


def pedir(url, corpo=None):
    req = urllib.request.Request(url, data=corpo, method="GET" if corpo is None else "POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        dados = r.read()
        tipo = r.headers.get("Content-Type", "")
    return json.loads(dados) if "json" in tipo else dados.decode("utf-8")


def teste_servidor(falhas):
    import calibracao
    import calibrar_telas
    import celular
    import padroes
    import simular

    base = os.path.join(_ambiente.SAIDA, "celular")
    if os.path.isdir(base):
        shutil.rmtree(base)
    os.makedirs(base)
    pads = padroes.padroes_projeto()
    cena = simular.cena_padrao(pads)
    cam = simular.Camera()
    fotos = simular.gerar_fotos(cena, cam, simular.NIVEIS["tipico"], N_FOTOS, semente=11)
    caminho_pad = os.path.join(base, "padroes.json")
    with open(caminho_pad, "w", encoding="utf-8") as fh:
        json.dump(padroes.para_json(pads, extra={"origem": "simular.py"}), fh)
    saida = os.path.join(base, "telas.json")

    def calcular(pasta):
        return calibrar_telas.calcular([pasta], caminho_padroes=caminho_pad, saida=saida,
                                       pasta_debug=None, verbose=False)

    srv = celular.Servidor(os.path.join(base, "fotos"), calcular, porta=0, host="127.0.0.1")
    srv.definir_padroes(pads)
    srv.iniciar()
    raiz = f"http://127.0.0.1:{srv.porta}/{srv.token}/"
    try:
        try:
            pedir(f"http://127.0.0.1:{srv.porta}/errado/")
            falhas.append("servidor respondeu sem o codigo do QR")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                falhas.append(f"sem codigo: esperava 404, veio {e.code}")
        if "Tirar foto" not in pedir(raiz) or not srv.conectado:
            falhas.append("a pagina nao abriu ou nao marcou o celular como conectado")

        r = pedir(raiz + "foto", b"isto nao e uma foto")
        if "erro" not in r:
            falhas.append("aceitou um arquivo que nao e imagem")
        cinza = cv2.imencode(".jpg", np.full((600, 800), 128, np.uint8))[1].tobytes()
        r = pedir(raiz + "foto", cinza)
        if r.get("boas") != 0 or not r.get("aviso"):
            falhas.append("foto sem telas deveria ser descartada com aviso")
        if "erro" not in pedir(raiz + "calcular", b""):
            falhas.append("calculou sem fotos suficientes")

        for f in fotos:
            jpg = cv2.imencode(".jpg", f["img"], [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()
            r = pedir(raiz + "foto", jpg)
        boas = r.get("boas", 0)
        gravadas = [n for n in os.listdir(srv.pasta) if n.endswith(".jpg")]
        if boas < N_FOTOS - 1 or len(gravadas) != boas:
            falhas.append(f"so {boas} fotos boas de {N_FOTOS}; {len(gravadas)} gravadas")

        r = pedir(raiz + "calcular", b"")
        if not r.get("calculando"):
            falhas.append("calcular deveria responder na hora, com calculando = true")
        for _ in range(120):                     # a pagina consulta o estado
            if not r.get("calculando"):
                break
            time.sleep(0.5)
            r = pedir(raiz + "estado")
        if r.get("erro_calculo") or not r.get("resultado") or not srv.terminou \
                or not srv.resultado_entregue:
            r["erro"] = r.get("erro_calculo")
            falhas.append(f"calcular falhou: {r.get('erro')}")
            return
        with open(saida, encoding="utf-8") as fh:
            d = json.load(fh)
        Rv, tv = cena.poses[1]
        R, t = np.array(d["telas"][1]["R"]), np.array(d["telas"][1]["t"])
        s = d["qualidade"]["escala_B_estimada"]
        erro = 1000 * np.max(np.linalg.norm(
            calibracao.quinas_no_mundo(pads[1], R, t, s) - (pads[1].quinas_tela() @ Rv.T + tv),
            axis=1))
        print(f"servidor: {boas} fotos boas, pior quina {erro:.2f} mm, "
              f"monitor a {r['resultado']['resumo']['lado']}")
        if erro > LIMITE_QUINA_MM:
            falhas.append(f"pior quina {erro:.2f} mm acima de {LIMITE_QUINA_MM}")
    finally:
        srv.parar()


def teste_comando(falhas):
    import calibrar_telas
    gui = _ambiente.GuiFalsa(avancar_no_waitkey=True).instalar()
    gui.reiniciar({4: "t", 8: "q"})
    base = os.path.join(_ambiente.SAIDA, "celular")
    cod = calibrar_telas.main(["celular", "-o", os.path.join(base, "padroes_cmd.json"),
                               "--telas", os.path.join(base, "telas_cmd.json"),
                               "--porta", "0"])
    janelas = sorted({g[1] for g in gui.gravados})
    if cod != 0 or len(janelas) != 2:
        falhas.append(f"comando celular: codigo {cod}, janelas {janelas}")
    print(f"comando celular: janelas {janelas}, saiu com q")


def main():
    falhas = []
    teste_servidor(falhas)
    teste_comando(falhas)
    return _ambiente.resultado(not falhas, "pagina do celular: envio das fotos, recusas, "
                               "calculo e comando celular" if not falhas else "; ".join(falhas))


if __name__ == "__main__":
    sys.exit(main())
