"""Calibracao das duas telas com o celular: onde o monitor externo esta em
relacao ao notebook. Gera o telas.json que o main.py usa para desenhar nas duas.

JEITO MAIS RAPIDO: python calibrar_telas.py celular
  Mostra os padroes e um QR code. O celular le o QR, abre uma pagina, tira as
  fotos pela camera dele e manda direto para ca; o botao Calcular da pagina
  grava o telas.json. Celular e notebook na mesma rede. Ver celular.py.

PASSO A PASSO COPIANDO AS FOTOS (detalhado em docs/TESTE_AP2.md)
  1. python calibrar_telas.py mostrar
       Cada tela mostra um padrao ChArUco em tela cheia, com o nome dela por
       cima. Confira que NOTEBOOK esta no notebook (senao aperte t), aperte
       ESPACO para esconder o rotulo e tire as fotos. q sai. Grava padroes.json.
  2. Celular, app de camera normal, modo Foto, lente 1x, sempre deitado:
       10 a 15 fotos com as DUAS telas inteiras no quadro, de lugares
       diferentes (esquerda, centro, direita, mais alto, mais baixo), de 0.6 a
       1.2 m, girando um pouco o celular em algumas. Nao tire todas do mesmo
       lugar. Evite reflexo de lampada. Tire o mouse de cima dos padroes.
  3. Copie as fotos ORIGINAIS para a pasta fotos/ ao lado deste arquivo (cabo
       USB, Quick Share ou Google Drive; WhatsApp so "como documento").
  4. python calibrar_telas.py calcular
       Le fotos/ e padroes.json, grava telas.json e mostra o resumo: onde esta
       o monitor, erro de reprojecao, avisos. Miniaturas e vista de cima em dbg/.
  5. python main.py
  Mexeu na tampa do notebook ou no monitor? Refaca os passos 1 a 4.

PLANO B, SEM FOTOS (medidas de trena, bem menos preciso)
  python calibrar_telas.py manual --angulo 30 --folga 0.03 --base 0.05 --inclinacao 15

TESTE SEM CELULAR
  python simular.py --pasta fotos_sim --n 12
  python calibrar_telas.py calcular fotos_sim -o fotos_sim/telas.json
"""

import argparse
import glob
import json
import math
import os
import sys

import cv2
import numpy as np

import config

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA_FOTOS = os.path.join(AQUI, "fotos")
PASTA_DEBUG = os.path.join(AQUI, "dbg")
PASTA_CELULAR = os.path.join(AQUI, "fotos_celular")     # uma subpasta por sessao
EXTENSOES = (".jpg", ".jpeg", ".png")
FONT = cv2.FONT_HERSHEY_SIMPLEX


# ================================================================ mostrar ===

def _rotulo(img_cinza, papel, dispositivo):
    """Padrao em BGR com o rotulo da tela por cima (para conferir de longe)."""
    img = cv2.cvtColor(img_cinza, cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    s = h / 1080.0
    x0, y0, x1, y1 = int(w * 0.18), int(h * 0.28), int(w * 0.82), int(h * 0.72)
    cv2.rectangle(img, (x0, y0), (x1, y1), (30, 30, 30), -1)
    cv2.putText(img, papel, (x0 + int(40 * s), y0 + int(150 * s)), FONT, 3.6 * s,
                (0, 220, 255), max(2, int(8 * s)), cv2.LINE_AA)
    linhas = [dispositivo,
              "ESPACO esconde este rotulo (para fotografar)",
              "t troca notebook <-> monitor     q sai"]
    for i, txt in enumerate(linhas):
        cv2.putText(img, txt, (x0 + int(40 * s), y0 + int((230 + 55 * i) * s)), FONT,
                    1.1 * s, (230, 230, 230), max(1, int(2 * s)), cv2.LINE_AA)
    return img


def _rotulo_celular(img_cinza, papel, dispositivo, url, qr, tunel=False):
    """Rotulo do modo celular: nome da tela e, no notebook, o QR code da pagina."""
    img = cv2.cvtColor(img_cinza, cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    s = h / 1080.0
    x0, y0, x1, y1 = int(w * 0.12), int(h * 0.22), int(w * 0.88), int(h * 0.78)
    cv2.rectangle(img, (x0, y0), (x1, y1), (30, 30, 30), -1)
    cv2.putText(img, papel, (x0 + int(40 * s), y0 + int(140 * s)), FONT, 3.2 * s,
                (0, 220, 255), max(2, int(8 * s)), cv2.LINE_AA)
    if qr is not None:
        lado = y1 - y0 - int(60 * s)
        q = cv2.resize(qr, (lado, lado), interpolation=cv2.INTER_NEAREST)
        qx, qy = x1 - lado - int(30 * s), y0 + (y1 - y0 - lado) // 2
        img[qy:qy + lado, qx:qx + lado] = q
        rede = "1. Celular com internet (4G/5G ou Wi-Fi)" if tunel else \
            "1. Celular e notebook na mesma rede"
        linhas = [rede, "2. Leia o QR code com a camera",
                  "3. Siga a pagina que abrir", url, "t troca as telas     q sai"]
    else:
        linhas = [dispositivo, "O QR code esta na tela do notebook",
                  "t troca notebook <-> monitor     q sai"]
    for i, txt in enumerate(linhas):
        cv2.putText(img, txt, (x0 + int(40 * s), y0 + int((225 + 60 * i) * s)), FONT,
                    1.0 * s, (230, 230, 230), max(1, int(2 * s)), cv2.LINE_AA)
    return img


def cmd_mostrar(args, servidor=None):
    """servidor: celular.Servidor ja criado (comando celular), ou None."""
    import monitores
    import padroes

    modo = monitores.tornar_dpi_aware()
    mons = monitores.listar_monitores()
    print(f"modo DPI: {modo}")
    for i, m in enumerate(mons):
        print(f"  [{i}] {m}")
    if len(mons) < 2:
        print("\nSo ha 1 monitor. Ligue o monitor externo e aperte Win+P > Estender.")
        return 1
    i_nb = monitores.escolher_notebook(mons)
    outros = [i for i in range(len(mons)) if i != i_nb]
    if args.monitor:
        achados = [i for i in outros if mons[i].dispositivo.lower() == args.monitor.lower()]
        if not achados:
            print(f"--monitor {args.monitor!r} nao encontrado")
            return 1
        i_mon = achados[0]
    else:
        i_mon = outros[0]
        if len(outros) > 1:
            print(f"aviso: ha {len(mons)} monitores; usando {mons[i_mon].dispositivo} "
                  "como monitor externo (escolha outro com --monitor)")

    nomes = {i: f"padrao {i}" for i in (i_nb, i_mon)}
    tam = {}
    for i in (i_mon, i_nb):                 # o notebook por ultimo: fica com o foco
        topo = i == i_mon and config.MONITOR_SEMPRE_NO_TOPO
        tam[i] = monitores.abrir_tela_cheia(nomes[i], mons[i], topo)
        aviso = monitores.conferir_tamanho(nomes[i], *tam[i], mons[i])
        if aviso:
            print(aviso)

    destino = args.saida or config.PADROES_FILE

    def gerar_e_salvar(i_nb, i_mon):
        (wa, ha), (wb, hb) = tam[i_nb], tam[i_mon]
        ta = padroes.Tela("notebook", wa, ha, config.SCREEN_W, config.SCREEN_H)
        tb = padroes.Tela.de_diagonal("monitor", wb, hb, args.diagonal)
        pads = padroes.padroes_projeto(ta, tb)
        dados = padroes.para_json(pads, [mons[i_nb], mons[i_mon]],
                                  extra={"diagonal_pol_nominal": args.diagonal,
                                         "modo_dpi": modo})
        with open(destino, "w", encoding="utf-8") as fh:
            json.dump(dados, fh, indent=2, ensure_ascii=False)
        imgs = {i_nb: pads[0].imagem(), i_mon: pads[1].imagem()}
        if servidor is not None:
            servidor.definir_padroes(pads)
        for p in pads:
            mm = p.quad_px * p.tela.larg_m / p.tela.px_w * 1000
            print(f"  {p.tela.nome}: tabuleiro {p.cols}x{p.rows}, quadrado {p.quad_px} px "
                  f"(~{mm:.1f} mm), marcadores {p.id0}..{p.id_fim - 1}")
        return imgs

    imgs = gerar_e_salvar(i_nb, i_mon)
    print(f"\npadroes.json gravado em {destino}")
    qr = None
    if servidor is None:
        print("Confira os rotulos, aperte ESPACO para esconde-los e fotografe.\n"
              "Tecla t troca notebook <-> monitor. q ou ESC sai.")
    else:
        import celular
        qr = celular.imagem_qr(servidor.url)
        servidor.iniciar()
        onde = "com internet" if getattr(args, "tunel", False) else "na mesma rede do notebook"
        print(f"\nNo celular ({onde}), leia o QR code ou abra:\n"
              f"    {servidor.url}\n"
              "Se o Windows perguntar, permita o Python na rede. O rotulo some quando o\n"
              "celular abrir a pagina. Tecla t troca as telas, ESPACO mostra o QR de novo.")
    mostrar_rotulo = True
    ja_conectou = False
    while True:
        if servidor is not None:
            if servidor.conectado and not ja_conectou:
                ja_conectou, mostrar_rotulo = True, False
                print("celular conectado: tire as fotos pela pagina")
            if servidor.terminou:
                break
        for i in (i_nb, i_mon):
            papel = "NOTEBOOK" if i == i_nb else "MONITOR"
            if not mostrar_rotulo:
                img = imgs[i]
            elif servidor is None:
                img = _rotulo(imgs[i], papel, mons[i].dispositivo)
            else:
                img = _rotulo_celular(imgs[i], papel, mons[i].dispositivo, servidor.url,
                                      qr if i == i_nb else None,
                                      getattr(args, "tunel", False))
            cv2.imshow(nomes[i], img)
        k = cv2.waitKey(50) & 0xFF
        if k in (ord("q"), 27):
            break
        if k == ord(" "):
            mostrar_rotulo = not mostrar_rotulo
        if k == ord("t"):
            i_nb, i_mon = i_mon, i_nb
            print("trocado: notebook agora e", mons[i_nb].dispositivo)
            imgs = gerar_e_salvar(i_nb, i_mon)
            mostrar_rotulo = True
        try:
            if any(cv2.getWindowProperty(n, cv2.WND_PROP_VISIBLE) < 1
                   for n in nomes.values()):
                break
        except cv2.error:
            break
    cv2.destroyAllWindows()
    print(f"\nnotebook = {mons[i_nb].dispositivo}, monitor = {mons[i_mon].dispositivo}")
    if i_nb != monitores.escolher_notebook(mons):
        print("A escolha automatica tinha errado. Para nao precisar trocar toda vez,\n"
              f"ponha no config.py:  MONITOR_NOTEBOOK = {mons[i_nb].dispositivo!r}")
    if servidor is None:
        print("Proximo passo: copie as fotos para a pasta fotos/ e rode\n"
              "    python calibrar_telas.py calcular\n"
              "(ou use  python calibrar_telas.py celular  para mandar as fotos pelo celular)")
    return 0


# ================================================================ celular ===

def cmd_celular(args):
    """mostrar + servidor: o celular manda as fotos e pede o calculo pela pagina."""
    import celular
    destino = args.saida or config.PADROES_FILE

    def calcular_sessao(pasta):
        return calcular([pasta], caminho_padroes=destino, saida=args.telas,
                        pasta_debug=PASTA_DEBUG, verbose=False)

    try:
        servidor = celular.Servidor(PASTA_CELULAR, calcular_sessao, args.porta,
                                    host="127.0.0.1" if args.tunel else "0.0.0.0")
    except OSError as e:
        print(f"nao consegui abrir a porta {args.porta}: {e}. Tente --porta 8766")
        return 1
    tunel = None
    if args.tunel:
        print("abrindo o tunel pela internet...")
        try:
            tunel, publico, servico = celular.abrir_tunel(servidor.porta, args.tunel_servico)
            print(f"tunel aberto por {servico}")
        except RuntimeError as e:
            print(f"{e}")
            servidor.http.server_close()
            return 1
        servidor.url = f"{publico}/{servidor.token}/"
    try:
        cod = cmd_mostrar(args, servidor)
    finally:
        if servidor.thread.is_alive():
            servidor.parar()
        if tunel is not None:
            tunel.terminate()
    if cod == 0 and servidor.terminou:
        r = servidor.resultado
        g, q = r["resumo"], r["qualidade"]
        print(f"\nCalibracao pronta com {r['n_fotos']} fotos: monitor a {g['lado']}, "
              f"{g['angulo_entre_telas_graus']} graus entre as telas, "
              f"{g['monitor_diagonal_pol']} pol, reprojecao {q['rms_reproj_px']} px")
        for a in r["avisos"]:
            print("AVISO: " + a)
        print(f"fotos em {servidor.pasta}\nProximo passo:  python main.py")
    elif cod == 0:
        print("saiu sem calcular. As fotos recebidas ficaram em", servidor.pasta)
    return cod


# =============================================================== calcular ===

def listar_fotos(entrada):
    """Arquivos de foto de uma pasta, de um padrao glob ou de uma lista."""
    arquivos = []
    for e in entrada:
        if os.path.isdir(e):
            arquivos += [os.path.join(e, f) for f in os.listdir(e)]
        else:
            arquivos += glob.glob(e)
    heic = sorted(f for f in arquivos if f.lower().endswith((".heic", ".heif")))
    fotos = sorted(f for f in arquivos if f.lower().endswith(EXTENSOES)
                   and not os.path.basename(f).startswith("."))
    return fotos, heic


def resumo_geometria(R, t, pad_a, pad_b, escala_b):
    """Numeros em linguagem de gente para conferir com a trena."""
    from scipy.spatial.transform import Rotation
    wa, ha = pad_a.tela.larg_m, pad_a.tela.alt_m
    wb, hb = pad_b.tela.larg_m * escala_b, pad_b.tela.alt_m * escala_b
    lado = "direita" if t[0] > 0 else "esquerda"
    s = 1.0 if lado == "direita" else -1.0
    # Menor distancia entre as bordas internas (verticais) das areas acesas,
    # no referencial do notebook: e a "folga" que se mede com a trena.
    ua = np.linspace(-1, 1, 41)
    borda_a = np.stack([np.full_like(ua, s * wa / 2), ua * ha / 2, 0 * ua], axis=1)
    borda_b = np.stack([np.full_like(ua, -s * wb / 2), ua * hb / 2, 0 * ua], axis=1) @ R.T + t
    folga = float(np.min(np.linalg.norm(borda_a[:, None] - borda_b[None], axis=2)))
    guinada, arfagem, rolagem = Rotation.from_matrix(R).as_euler("YXZ", degrees=True)
    ang = math.degrees(math.acos(max(-1.0, min(1.0, float(R[2, 2])))))
    diag = math.hypot(wb, hb) / 0.0254
    return {
        "lado": lado,
        "centro_cm": [round(float(x) * 100, 1) for x in t],
        "angulo_entre_telas_graus": round(ang, 1),
        "guinada_graus": round(float(guinada), 1),
        "arfagem_graus": round(float(arfagem), 1),
        "rolagem_graus": round(float(rolagem), 1),
        "folga_bordas_internas_cm": round(folga * 100, 1),
        "altura_centro_cm": round(float(t[1]) * 100, 1),
        "monitor_cm": [round(wb * 100, 1), round(hb * 100, 1)],
        "monitor_diagonal_pol": round(diag, 1),
    }


def desenhar_planta(caminho, R, t, pad_a, pad_b, escala_b, cameras=()):
    """Vista de cima (plano X-Z do notebook): telas, normais, webcam e fotos."""
    W = H = 800
    img = np.full((H, W, 3), 255, np.uint8)
    wb = pad_b.tela.larg_m * escala_b
    qa = np.array([[-pad_a.tela.larg_m / 2, 0, 0], [pad_a.tela.larg_m / 2, 0, 0]])
    qb = np.array([[-wb / 2, 0, 0], [wb / 2, 0, 0]]) @ R.T + t
    pontos = [qa, qb] + ([np.array(cameras)] if len(cameras) else [])
    todos = np.vstack(pontos)[:, [0, 2]]
    lo, hi = todos.min(axis=0) - 0.15, todos.max(axis=0) + 0.15
    esc = 0.9 * min(W, H) / max(hi - lo)
    centro = (lo + hi) / 2

    def px(p):
        x, z = p[0], p[2]
        return (int(W / 2 + (x - centro[0]) * esc), int(H / 2 + (z - centro[1]) * esc))
    # Grade de 10 cm
    for k in np.arange(math.floor(lo[0] * 10), math.ceil(hi[0] * 10) + 1) / 10:
        cv2.line(img, px((k, 0, lo[1])), px((k, 0, hi[1])), (235, 235, 235), 1)
    for k in np.arange(math.floor(lo[1] * 10), math.ceil(hi[1] * 10) + 1) / 10:
        cv2.line(img, px((lo[0], 0, k)), px((hi[0], 0, k)), (235, 235, 235), 1)
    for q, nome, cor, n in ((qa, "notebook", (40, 40, 40), np.array([0, 0, 1.0])),
                            (qb, "monitor", (200, 90, 0), R[:, 2])):
        cv2.line(img, px(q[0]), px(q[1]), cor, 4, cv2.LINE_AA)
        meio = q.mean(axis=0)
        cv2.arrowedLine(img, px(meio), px(meio + 0.08 * n), cor, 2, cv2.LINE_AA)
        cv2.putText(img, nome, px(meio + np.array([0.0, 0, -0.04])), FONT, 0.6, cor, 2,
                    cv2.LINE_AA)
    cam = np.array([config.CAM_OFFSET_X, config.CAM_OFFSET_Y, 0.0])
    cv2.circle(img, px(cam), 6, (0, 0, 200), -1)
    cv2.putText(img, "webcam", px(cam + np.array([0.02, 0, 0.03])), FONT, 0.5,
                (0, 0, 200), 1, cv2.LINE_AA)
    for c in cameras:
        cv2.circle(img, px(c), 5, (0, 150, 0), -1)
    cv2.putText(img, "vista de cima (X para a direita, Z para quem olha). "
                     "Pontos verdes: onde o celular estava em cada foto. Grade: 10 cm",
                (10, H - 12), FONT, 0.42, (90, 90, 90), 1, cv2.LINE_AA)
    import detectar
    detectar.gravar_imagem(caminho, img)


def calcular(fotos, caminho_padroes=None, saida=None, fixar_escala_b=False,
             pasta_debug=PASTA_DEBUG, verdade=None, verbose=True):
    """Fotos -> telas.json. Devolve um dicionario com o resultado (para testes).

    Levanta SystemExit com mensagem legivel nos erros que o usuario resolve
    (faltou padroes.json, nenhuma foto, poucas fotos com as duas telas).
    """
    import calibracao
    import detectar
    import padroes
    import telas

    def log(*a):
        if verbose:
            print(*a)

    arquivos, heic = listar_fotos(fotos)
    if heic:
        log(f"aviso: {len(heic)} foto(s) HEIC/HEIF ignoradas: o OpenCV nao le esse "
            "formato. No celular escolha JPEG (Samsung: desligue 'fotos de alta "
            "eficiencia').")
    if not arquivos:
        raise SystemExit(f"nenhuma foto .jpg/.png em {fotos}. Copie as fotos do celular "
                         f"para {PASTA_FOTOS} ou passe a pasta: calcular <pasta>")
    if caminho_padroes is None:
        pasta0 = fotos[0] if os.path.isdir(fotos[0]) else os.path.dirname(fotos[0])
        local = os.path.join(pasta0, "padroes.json")
        caminho_padroes = local if os.path.exists(local) else config.PADROES_FILE
    if not os.path.exists(caminho_padroes):
        raise SystemExit(f"nao achei {caminho_padroes}. Rode primeiro:\n"
                         "    python calibrar_telas.py mostrar\n"
                         "e tire as fotos com os padroes na tela.")
    with open(caminho_padroes, encoding="utf-8") as fh:
        dados_pad = json.load(fh)
    pads = padroes.de_json(dados_pad)
    # A regua (tamanho do notebook) vale a do config ATUAL: o usuario pode ter
    # medido com regua depois do mostrar. O tabuleiro nao depende dos metros.
    ta = pads[0].tela
    if dados_pad.get("origem") != "simular.py" and (
            abs(ta.larg_m - config.SCREEN_W) > 1e-9 or abs(ta.alt_m - config.SCREEN_H) > 1e-9):
        log(f"usando o tamanho do notebook do config.py ({config.SCREEN_W} x "
            f"{config.SCREEN_H} m) em vez do gravado no padroes.json ({ta.larg_m} x "
            f"{ta.alt_m} m)")
        pads[0] = padroes.Padrao(padroes.Tela(ta.nome, ta.px_w, ta.px_h, config.SCREEN_W,
                                              config.SCREEN_H), pads[0].id0,
                                 quad_px=pads[0].quad_px, dicionario=pads[0].dicionario_id)
    det = detectar.Detector(pads)
    if pasta_debug:
        os.makedirs(pasta_debug, exist_ok=True)

    log(f"{len(arquivos)} fotos, padroes de {caminho_padroes}")
    n_min = calibracao.N_MIN_VISTA

    def boa(d):
        return d is not None and d.n >= n_min

    # Todas as fotos tem de ter o mesmo tamanho (mesma lente, mesmo modo): o
    # modelo da camera do celular e um so. Vale o tamanho com mais fotos boas,
    # nao o da primeira foto da lista.
    por_tam = {}
    for arq in arquivos:
        nome = os.path.basename(arq)
        try:
            img = detectar.ler_foto(arq)
        except IOError as e:
            log(f"  {nome}: {e}")
            continue
        r = det.detectar(img)
        na = 0 if r[0] is None else r[0].n
        nb = 0 if r[1] is None else r[1].n
        log(f"  {nome}: {img.shape[1]}x{img.shape[0]}, notebook {na:3d} cantos, "
            f"monitor {nb:3d} cantos")
        if pasta_debug:
            detectar.gravar_imagem(os.path.join(pasta_debug, nome + ".png"),
                                   detectar.desenhar(img, r))
        if r[0] is None and r[1] is None:
            continue
        por_tam.setdefault((img.shape[1], img.shape[0]), []).append((nome, r))
    if not por_tam:
        raise SystemExit("nenhuma foto teve uma tela reconhecida. Veja as miniaturas em "
                         f"{pasta_debug}: os padroes estavam na tela? Chegue mais perto "
                         "(0.6-0.8 m) e evite reflexo.")
    tam = max(por_tam, key=lambda k: (sum(boa(r[0]) and boa(r[1]) for _n, r in por_tam[k]),
                                      len(por_tam[k])))
    for k, lista in por_tam.items():
        if k != tam:
            log(f"aviso: {len(lista)} foto(s) de {k[0]}x{k[1]} ignoradas; as usadas sao as "
                f"de {tam[0]}x{tam[1]} (fotos com outra lente, outro modo ou celular em pe)")
    fotos_det = [r for _n, r in por_tam[tam]]
    usadas = [n for n, _r in por_tam[tam]]
    n_duas = sum(1 for r in fotos_det if boa(r[0]) and boa(r[1]))
    dica = ("Veja as miniaturas em " + str(pasta_debug) + ": os pontos coloridos sao os "
            "cantos achados. Chegue mais perto (0.6-0.8 m), deixe as duas telas inteiras "
            "no quadro, evite reflexo e confira os padroes na tela.")
    if n_duas < 3:
        raise SystemExit(f"so {n_duas} foto(s) mostram as DUAS telas com cantos suficientes "
                         f"(>= {n_min} por tela); sao necessarias pelo menos 3 (o ideal e "
                         "10 a 15). " + dica)

    try:
        cal = calibracao.calibrar(fotos_det, tam, estimar_escala=not fixar_escala_b)
    except RuntimeError as e:
        raise SystemExit(f"a calibracao falhou: {e}. " + dica)
    d = calibracao.telas_json(pads, cal, tam,
                              extra={"fotos": usadas, "opencv": cv2.__version__,
                                     "padroes": os.path.abspath(caminho_padroes),
                                     "origem": "calibrar_telas.py calcular"})
    d["referencial"] = telas.REFERENCIAL
    d["qualidade"]["fotos_descartadas_media"] = [usadas[j] for j in cal.descartadas]
    for t_json, t_pad in zip(d["telas"], dados_pad["telas"]):
        t_json["monitor"] = t_pad.get("monitor")
    geo = resumo_geometria(cal.R, cal.t, pads[0], pads[1], cal.escala_B)
    d["resumo"] = geo
    saida = saida or config.TELAS_FILE
    with open(saida, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=2, ensure_ascii=False)
    telas.carregar(saida)                      # confere que o main.py consegue ler

    cameras = []
    if cal.ba is not None:
        for Rcw, tcw in cal.ba.poses.values():
            cameras.append(-np.asarray(Rcw).T @ np.asarray(tcw).ravel())
    if pasta_debug:
        desenhar_planta(os.path.join(pasta_debug, "planta.png"), cal.R, cal.t,
                        pads[0], pads[1], cal.escala_B, cameras)

    q = d["qualidade"]
    avisos = []
    if q["rms_reproj_px"] is not None and q["rms_reproj_px"] > 1.0:
        avisos.append(f"erro de reprojecao alto ({q['rms_reproj_px']} px): fotos tremidas, "
                      "desfocadas ou algo mexeu entre as fotos")
    if q["dispersao_entre_fotos"]["trans_mm"] > 5:
        avisos.append("as fotos discordam entre si (dispersao "
                      f"{q['dispersao_entre_fotos']['trans_mm']} mm): algo mexeu?")
    if cal.ba is not None and not cal.ba.sucesso:
        avisos.append("o ajuste de feixes nao convergiu: o resultado pode estar longe do "
                      "certo. Tire fotos de pontos de vista mais variados")
    if n_duas < 6:
        avisos.append(f"so {n_duas} fotos com as duas telas: tire 10 a 15")
    diag_nom = dados_pad.get("diagonal_pol_nominal")
    if diag_nom and not fixar_escala_b and abs(geo["monitor_diagonal_pol"] / diag_nom - 1) > 0.08:
        avisos.append(f"o tamanho do monitor estimado pelas fotos ({geo['monitor_diagonal_pol']}"
                      f" pol) difere bastante da diagonal informada ({diag_nom} pol). O "
                      "valor estimado ja foi usado no telas.json. Se a etiqueta do monitor "
                      "confirma a diagonal informada, tire fotos de pontos de vista mais "
                      "variados e rode o calcular de novo")
    lado = geo["lado"]
    log("")
    log(f"Monitor a {lado} do notebook. Centro dele: x {geo['centro_cm'][0]} cm, "
        f"y {geo['centro_cm'][1]} cm, z {geo['centro_cm'][2]} cm (z = para quem olha)")
    log(f"Angulo entre as telas {geo['angulo_entre_telas_graus']} graus (guinada "
        f"{geo['guinada_graus']}, arfagem {geo['arfagem_graus']}, rolagem "
        f"{geo['rolagem_graus']}); folga entre as bordas internas "
        f"{geo['folga_bordas_internas_cm']} cm")
    log(f"Tamanho estimado do monitor: {geo['monitor_cm'][0]} x {geo['monitor_cm'][1]} cm "
        f"({geo['monitor_diagonal_pol']} pol)")
    log(f"Qualidade: reprojecao {q['rms_reproj_px']} px, {n_duas} fotos com as duas "
        f"telas, dispersao {q['dispersao_entre_fotos']}")
    for a in avisos:
        log("AVISO: " + a)
    log(f"\ntelas.json gravado em {saida}")
    if pasta_debug:
        log(f"miniaturas e vista de cima (planta.png) em {pasta_debug}")

    resultado = {"telas_json": d, "calibracao": cal, "padroes": pads, "avisos": avisos,
                 "n_duas_telas": n_duas, "saida": saida}
    if verdade is None:
        pasta0 = fotos[0] if os.path.isdir(fotos[0]) else os.path.dirname(fotos[0])
        cand = os.path.join(pasta0, "verdade.json")
        verdade = cand if os.path.exists(cand) else None
    if verdade:
        resultado["erro"] = comparar_com_verdade(verdade, cal, pads)
        e = resultado["erro"]
        log(f"ERRO contra a verdade ({os.path.basename(verdade)}): rotacao "
            f"{e['rot_graus']:.4f} graus, translacao {e['trans_mm']:.3f} mm, pior quina "
            f"{e['pior_quina_mm']:.3f} mm, tamanho do monitor {e['tamanho_pct']:+.3f}%")
    return resultado


def comparar_com_verdade(caminho, cal, pads):
    """Erro da calibracao contra o verdade.json do simular.py."""
    import calibracao
    import padroes
    with open(caminho, encoding="utf-8") as fh:
        v = json.load(fh)
    Rv, tv = np.array(v["R_AB"]), np.array(v["t_AB"])
    tb = pads[1].tela
    tela_v = padroes.Tela(tb.nome, tb.px_w, tb.px_h, *v["tela_B_m"])
    Qe = calibracao.quinas_no_mundo(pads[1], cal.R, cal.t, cal.escala_B)
    Qv = pads[1].quinas_tela(tela_v) @ Rv.T + tv
    return {"rot_graus": float(calibracao.angulo_graus(Rv, cal.R)),
            "trans_mm": float(1000 * np.linalg.norm(cal.t - tv)),
            "pior_quina_mm": float(1000 * np.max(np.linalg.norm(Qe - Qv, axis=1))),
            "tamanho_pct": float(100 * (tb.larg_m * cal.escala_B / tela_v.larg_m - 1))}


def cmd_calcular(args):
    calcular(args.fotos or [PASTA_FOTOS], args.padroes, args.saida, args.fixar_escala_b,
             None if args.sem_debug else (args.debug or PASTA_DEBUG), args.verdade)
    return 0


# ================================================================= manual ===

def _rot_x(graus):
    a = math.radians(graus)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0, 0], [0, c, -s], [0, s, c]])


def pose_manual(larg_a, alt_a, larg_b, alt_b, lado="direita", angulo=30.0, folga=0.03,
                base=0.0, recuo=0.0, inclinacao=0.0):
    """Pose do monitor no referencial do notebook a partir de medidas de trena.

    Referencial da MESA (auxiliar): origem no meio da borda de BAIXO da area
    acesa do notebook, X para a direita, Y vertical para cima, Z horizontal
    para quem olha. O notebook esta inclinado para tras `inclinacao` graus
    (tampa em relacao a vertical); o monitor esta em pe, girado `angulo` graus
    em torno da vertical com a borda de FORA vindo para quem olha.
      folga: distancia horizontal entre as bordas internas das areas acesas
      base:  altura da borda de baixo da area acesa do monitor menos a do
             notebook (as duas medidas a partir da mesa)
      recuo: quanto a quina interna de baixo do monitor esta ATRAS da linha
             da borda de baixo do notebook (positivo = mais longe de quem olha)
    """
    import telas
    R_mn = _rot_x(-inclinacao)                     # notebook na mesa
    s = 1.0 if lado == "direita" else -1.0
    R_mm = telas.rot_y(-s * angulo)                # monitor na mesa
    c_nb = R_mn @ np.array([0.0, alt_a / 2, 0.0])
    quina = np.array([s * (larg_a / 2 + folga), base, -recuo])
    c_mon = quina - R_mm @ np.array([-s * larg_b / 2, -alt_b / 2, 0.0])
    return R_mn.T @ R_mm, R_mn.T @ (c_mon - c_nb)


def _indice_monitor(mons, escolha):
    """Indice em mons de um dispositivo ("\\\\.\\DISPLAY2") ou de um indice ("1")."""
    if escolha is None:
        return None
    if str(escolha).isdigit() and int(escolha) < len(mons):
        return int(escolha)
    for i, m in enumerate(mons):
        if m.dispositivo.lower() == str(escolha).lower():
            return i
    raise SystemExit(f"monitor {escolha!r} nao encontrado. Monitores: "
                     + "; ".join(f"[{i}] {m.dispositivo}" for i, m in enumerate(mons)))


def cmd_manual(args):
    import monitores
    import padroes
    import telas
    mons = monitores.listar_monitores()
    if len(mons) < 2:
        print("So ha 1 monitor ligado. Ligue o monitor externo (Win+P > Estender) e rode "
              "de novo: o telas.json precisa saber em qual monitor do Windows ele esta.")
        return 1
    escolhido = _indice_monitor(mons, args.notebook)
    i_nb = escolhido if escolhido is not None else monitores.escolher_notebook(mons)
    outros = [i for i in range(len(mons)) if i != i_nb]
    i_mon = _indice_monitor(mons, args.monitor) if args.monitor else outros[0]
    if i_mon == i_nb:
        print("--notebook e --monitor apontam para o mesmo monitor")
        return 1
    nb, mon = mons[i_nb], mons[i_mon]
    tb = padroes.Tela.de_diagonal("monitor", mon.largura, mon.altura, args.diagonal)
    R, t = pose_manual(config.SCREEN_W, config.SCREEN_H, tb.larg_m, tb.alt_m, args.lado,
                       args.angulo, args.folga, args.base, args.recuo, args.inclinacao)
    a = telas.Tela("notebook", config.SCREEN_W, config.SCREEN_H, nb.largura, nb.altura,
                   monitor=nb.para_json())
    b = telas.Tela("monitor", tb.larg_m, tb.alt_m, mon.largura, mon.altura, R, t,
                   mon.para_json())
    saida = args.saida or config.TELAS_FILE
    telas.salvar([a, b], saida, {"origem": "calibrar_telas.py manual (trena)",
                                 "medidas": {k: v for k, v in vars(args).items()
                                             if k not in ("func", "comando")}})
    print(f"notebook = {nb.dispositivo}   monitor = {mon.dispositivo}")
    if escolhido is None:
        print("  (escolha automatica do notebook. Se estiver trocado, rode de novo com "
              f"--notebook {mon.dispositivo!r}, ou ponha no config.py:\n"
              f"   MONITOR_NOTEBOOK = {mon.dispositivo!r})")
    print(f"telas.json gravado em {saida} a partir das medidas de trena.")
    print(f"Monitor {tb.larg_m * 100:.1f} x {tb.alt_m * 100:.1f} cm, centro em "
          f"{np.round(t * 100, 1).tolist()} cm. Use para testar; a calibracao por fotos "
          "e bem mais precisa.")
    return 0


# ================================================================== main ===

def main(argv=None):
    ap = argparse.ArgumentParser(description="calibracao das duas telas com o celular",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    sub = ap.add_subparsers(dest="comando", required=True)

    m = sub.add_parser("mostrar", help="mostra os padroes ChArUco nas duas telas")
    m.add_argument("--diagonal", type=float, default=config.MONITOR_DIAGONAL_POL,
                   help="diagonal nominal do monitor externo, em polegadas")
    m.add_argument("--monitor", default=None,
                   help="dispositivo do monitor externo, se houver mais de um")
    m.add_argument("-o", "--saida", default=None, help="padroes.json (padrao: config)")
    m.set_defaults(func=cmd_mostrar)

    e = sub.add_parser("celular", help="padroes nas telas + pagina para o celular mandar "
                                       "as fotos (QR code) e calcular")
    e.add_argument("--diagonal", type=float, default=config.MONITOR_DIAGONAL_POL,
                   help="diagonal nominal do monitor externo, em polegadas")
    e.add_argument("--monitor", default=None,
                   help="dispositivo do monitor externo, se houver mais de um")
    e.add_argument("-o", "--saida", default=None, help="padroes.json (padrao: config)")
    e.add_argument("--telas", default=None, help="telas.json (padrao: config)")
    e.add_argument("--porta", type=int, default=8765)
    e.add_argument("--tunel", action="store_true",
                   help="o celular acessa pela internet (tunel ssh), sem precisar estar "
                        "na mesma rede; as fotos passam pelo servico de tunel")
    e.add_argument("--tunel-servico", choices=["serveo", "localhost.run"], default=None,
                   help="servico do tunel (padrao: tenta serveo, depois localhost.run)")
    e.set_defaults(func=cmd_celular)

    c = sub.add_parser("calcular", help="calcula o telas.json a partir das fotos")
    c.add_argument("fotos", nargs="*", help="pasta ou arquivos (padrao: fotos/)")
    c.add_argument("--padroes", default=None,
                   help="padroes.json (padrao: o da pasta das fotos, senao o do config)")
    c.add_argument("-o", "--saida", default=None, help="telas.json (padrao: config)")
    c.add_argument("--fixar-escala-b", action="store_true",
                   help="NAO estima o tamanho do monitor (so se a diagonal for exata)")
    c.add_argument("--debug", default=None, help="pasta das miniaturas (padrao: dbg/)")
    c.add_argument("--sem-debug", action="store_true", help="nao grava miniaturas")
    c.add_argument("--verdade", default=None, help="verdade.json do simular.py")
    c.set_defaults(func=cmd_calcular)

    n = sub.add_parser("manual", help="telas.json a partir de medidas de trena")
    n.add_argument("--lado", choices=["direita", "esquerda"], default="direita")
    n.add_argument("--angulo", type=float, default=30.0,
                   help="graus que o monitor esta virado para quem olha")
    n.add_argument("--folga", type=float, default=0.03,
                   help="m entre as bordas internas das areas acesas, medidos na "
                        "horizontal ao longo da borda de baixo do notebook")
    n.add_argument("--base", type=float, default=0.0,
                   help="m: altura da borda de baixo do monitor menos a do notebook")
    n.add_argument("--recuo", type=float, default=0.0,
                   help="m que o monitor esta atras do notebook")
    n.add_argument("--inclinacao", type=float, default=0.0,
                   help="graus que a tampa do notebook esta inclinada para tras")
    n.add_argument("--diagonal", type=float, default=config.MONITOR_DIAGONAL_POL)
    n.add_argument("--notebook", default=None,
                   help="dispositivo (ex. \\\\.\\DISPLAY1) ou indice do monitor do notebook")
    n.add_argument("--monitor", default=None,
                   help="dispositivo ou indice do monitor externo, se houver mais de um")
    n.add_argument("-o", "--saida", default=None)
    n.set_defaults(func=cmd_manual)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
