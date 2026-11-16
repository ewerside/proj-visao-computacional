"""Loop principal do head-coupled perspective.

Teclas:
  q ou ESC  sai
  f         liga/desliga o One Euro Filter (comparacao A/B)
  y         liga/desliga a correcao de guinada no Z (comparacao A/B)
  d         liga/desliga o overlay de debug
  ESPACO    congela a posicao do olho e a rolagem
  n         troca de cenario (cubos / corredor / vila / asteroides)
  , / .     min_cutoff para baixo / para cima
  k / l     beta para baixo / para cima

Estereo:
  3         liga/desliga o anaglifo vermelho-ciano
  c         cicla o algoritmo de composicao: gray, true, dubois
  p         liga/desliga a paleta neutra do anaglifo
  g         liga/desliga o cancelamento de vazamento (custa o fundo preto)
  a         escala automatica (padrao) ou manual
  [ / ]     escala para baixo / para cima, em passos de 0.1 (passa a manual)
  1 / 2     mostra so o olho esquerdo / so o olho direito (diagnostico)
  s         troca esquerdo com direito, se a profundidade sair invertida
  0         padrao de medicao de vazamento das lentes ([ e ] ajustam)

Varias telas (AP2): com um telas.json ao lado deste arquivo (gerado pelo
calibrar_telas.py, ver telas.py), abre uma janela fullscreen por tela, cada uma
no seu monitor. Os cenarios do AP1 ganham uma caixa por tela, e a tecla n passa
tambem pelos cenarios do mundo compartilhado (trem, planeta, sala, alinhamento).
Sem telas.json, ou com --uma-tela, e o AP1 de sempre, uma tela so. O anaglifo so
existe com uma tela.

    python main.py                  abre o menu do Parallax (o mesmo que parallax.py)
    python main.py --direto         laco das cenas; usa o telas.json, se existir
    python main.py --uma-tela       ignora o telas.json (modo AP1)
    python main.py --telas outro.json

O menu do Parallax (parallax.py) chama este laco com --app: comeca na cena
pedida (--cena), circula so pelas cenas dadas (--cenas), esconde as legendas de
teclas e ESC devolve o controle ao menu.
"""

import argparse
import math
import os
import time
from collections import deque

import cv2
import numpy as np

import anaglyph
import config
import filters
import monitores
import sala
import scene as scn
import telas as tls
import tracking

WINDOW = "head-coupled"
FONT = cv2.FONT_HERSHEY_SIMPLEX

# Com o anaglifo ligado, toda cena comeca com a menor separacao entre as duas
# imagens; as teclas [ e ] ajustam a partir dai.
ESCALA_MINIMA = 0.1

# Posicao da cabeca usada antes da primeira deteccao de rosto.
HEAD_PADRAO = np.array([0.0, -config.CAM_OFFSET_Y, 0.60])


def _nome_janela(tela, i):
    """Titulo ASCII e unico: o OpenCV cria a janela com CreateWindowExA."""
    if i == 0:
        return WINDOW
    nome = tela.nome.encode("ascii", "ignore").decode() or f"tela{i}"
    return f"{WINDOW} {i} {nome}"


def abrir_janelas(lista, multi):
    """Abre uma janela em tela cheia por tela, cada uma no seu monitor.

    Devolve (nomes, tamanhos). Os tamanhos sao os REAIS das janelas, nao os do
    config nem os do telas.json: se o Windows estiver com escala diferente de
    100% eles podem divergir. Como cada janela cobre a sua tela inteira, mapear
    metros para fracao da janela continua correto de qualquer jeito.

    Modo de uma tela (AP1): a janela vai para o monitor do notebook, que pode
    nao ser o principal do Windows. Varias telas: cada tela do telas.json acha
    o seu monitor pelo nome do dispositivo (monitores.achar_monitor). A janela
    do notebook abre por ultimo, para ficar com o foco do teclado.
    """
    mons = monitores.listar_monitores()
    if multi:
        alvos = []
        for tl in lista:
            m = monitores.achar_monitor(mons, tl.monitor)
            if m is None:
                raise SystemExit(
                    f"telas.json: nao achei o monitor da tela {tl.nome!r} "
                    f"({tl.monitor}). Monitores agora: "
                    + "; ".join(str(x) for x in mons)
                    + ". Confira se o monitor esta ligado e em 'Estender' (Win+P), "
                    "rode de novo o calibrar_telas.py, ou use --uma-tela.")
            if (abs(m.largura / m.altura - tl.px_w / tl.px_h) > 0.01):
                print(f"aviso: o monitor de {tl.nome!r} esta em {m.largura}x{m.altura}, "
                      f"mas foi calibrado em {tl.px_w}x{tl.px_h}: proporcao diferente, "
                      "a imagem sai distorcida. Volte a resolucao ou recalibre.")
            alvos.append(m)
        if len({id(m) for m in alvos}) != len(alvos):
            raise SystemExit("telas.json: duas telas apontam para o mesmo monitor. "
                             "Rode de novo o calibrar_telas.py mostrar.")
    else:
        alvos = [mons[monitores.escolher_notebook(mons)] if len(mons) > 1 else None]
        if alvos[0] is not None:
            print(f"modo de uma tela no monitor {alvos[0].dispositivo} (o notebook). "
                  "Errado? Ajuste MONITOR_NOTEBOOK no config.py.")
    nomes = [_nome_janela(tl, i) for i, tl in enumerate(lista)]
    tamanhos = [None] * len(lista)
    for i in reversed(range(len(lista))):
        topo = i > 0 and config.MONITOR_SEMPRE_NO_TOPO
        tamanhos[i] = monitores.abrir_tela_cheia(nomes[i], alvos[i], topo)
        aviso = monitores.conferir_tamanho(nomes[i], *tamanhos[i], alvos[i])
        if aviso:
            print(aviso)
    return nomes, tamanhos


def construir(nome, lista):
    """Parte estatica do cenario.

    Cenario do AP1: uma caixa POR TELA, com as medidas dela e no referencial
    local dela, porque a boca de cada caixa tem que ser o retangulo da sua tela.
    Cenario de sala.py: uma cena so, no mundo, atras de todas as telas.
    """
    if nome in sala.CENAS_MUNDO:
        return sala.build(nome, lista)
    return [scn.build(nome, tl.dims) for tl in lista]


def z_min_estaticos(nome, estatica, lista):
    """Vertice mais fundo da parte estatica, por tela, no referencial dela."""
    if nome in sala.CENAS_MUNDO:
        return [tls.z_minimo_tela(estatica, tl) for tl in lista]
    return [scn.z_minimo(est) for est in estatica]


def render_tela_i(olho, i, lista, ordem, mundo, alvo, fundo=None, paleta=None):
    """Desenha a tela i vista de `olho` (no MUNDO; pode ser um olho do estereo).

    mundo=True: `ordem` e a ordem do mundo compartilhado, a mesma para todas as
    telas. mundo=False: `ordem` e a lista de ordens locais, uma por tela.
    """
    tl = lista[i]
    if mundo:
        return tls.render_tela(olho, ordem, tl, alvo, fundo, paleta)
    return tls.render_local(tls.olho_local(olho, tl), ordem[i], alvo, tl.dims, fundo,
                            paleta)


def desenhar_debug(canvas, head, ipd_px, fps, ms_render, tem_rosto,
                   usar_filtro, min_cutoff, beta, tremor_mm, nome_cena,
                   roll_graus, estereo, guinada=None):
    """Overlay de debug, desenhado SEMPRE por ultimo.

    Com o anaglifo ligado isso nao e detalhe de ordem: texto desenhado antes da
    composicao entra nela e sai fantasmado, vermelho de um lado e ciano do
    outro, ilegivel com os oculos. Por isso o HUD vem depois, e em branco, que e
    a unica cor que as duas lentes deixam passar igual.
    """
    branco = (255, 255, 255)
    composto = estereo["ativo"] and estereo["solo"] is None
    linhas = [
        f"X  {head[0]*100:+7.1f} cm",
        f"Y  {head[1]*100:+7.1f} cm",
        f"Z  {head[2]*100:7.1f} cm",
        f"ipd_px  {ipd_px:.2f}",
        f"roll  {roll_graus:+6.1f} deg"
        + ("" if config.USE_HEAD_ROLL else "   (nao usado)"),
        f"{fps:.1f} fps   render {ms_render:.1f} ms",
        f"cena: {nome_cena}",
        "estereo: " + (f"anaglifo {estereo['modo']}" if estereo["ativo"]
                       else "mono")
        + f"   escala {estereo['escala']:.2f}"
        + ("  auto" if estereo["auto"] else "  manual")
        + ("" if estereo["paleta"] else "   paleta OFF")
        + (f"   cancelamento {estereo['ghost']}%" if estereo["ghost"] else ""),
        f"paralaxe {estereo['paralaxe']:5.1f} px   conforto ate "
        f"{estereo['limite']:.0f} px (W/30)"
        + ("   ESTOUROU" if estereo["paralaxe"] > estereo["limite"] else ""),
    ]
    if guinada is not None:
        # guinada = (graus, k, ligada, tem_matriz). k multiplica X, Y e Z.
        graus, k, ligada, tem_matriz = guinada
        if ligada and not tem_matriz:
            estado = "SEM MATRIZ do MediaPipe (correcao inativa)"
        else:
            estado = "ON" if ligada else "OFF (y liga)"
        linhas.append(f"guinada {graus:+5.1f} deg   k {k:.3f}   correcao {estado}")
    for i, linha in enumerate(linhas):
        cv2.putText(canvas, linha, (24, 50 + i * 34), FONT, 0.7,
                    branco if composto else (0, 230, 0), 2, cv2.LINE_AA)
    y = 50 + len(linhas) * 34 + 14
    cor = branco if composto else ((0, 230, 0) if usar_filtro else (0, 165, 255))
    cv2.putText(canvas, f"One Euro {'ON ' if usar_filtro else 'OFF'}   "
                        f"min_cutoff {min_cutoff:.2f}   beta {beta:.3f}",
                (24, y), FONT, 0.7, cor, 2, cv2.LINE_AA)
    cv2.putText(canvas, f"tremor  X {tremor_mm[0]:4.1f}  Y {tremor_mm[1]:4.1f}  "
                        f"Z {tremor_mm[2]:4.1f} mm   (fique parado para ler)",
                (24, y + 32), FONT, 0.6, branco if composto else (170, 170, 170),
                1, cv2.LINE_AA)
    if not tem_rosto:
        cv2.putText(canvas, "SEM ROSTO", (24, y + 70), FONT, 0.8,
                    branco if composto else (0, 0, 255), 2, cv2.LINE_AA)


def argumentos(argv=None):
    ap = argparse.ArgumentParser(description="head-coupled perspective, 1 ou 2 telas")
    ap.add_argument("--uma-tela", action="store_true",
                    help="ignora o telas.json e roda o modo AP1 (so o notebook)")
    ap.add_argument("--telas", default=config.TELAS_FILE,
                    help="caminho do telas.json (padrao: ao lado do main.py)")
    ap.add_argument("--cena", default=None, help="cena inicial")
    ap.add_argument("--cenas", default=None,
                    help="cenas por onde a tecla n circula, separadas por virgula")
    ap.add_argument("--anaglifo", action="store_true",
                    help="comeca com o anaglifo ligado (so com uma tela)")
    ap.add_argument("--app", action="store_true",
                    help="chamado pelo menu: sem legendas de teclas")
    ap.add_argument("--direto", action="store_true",
                    help="abre direto o laco das cenas, sem passar pelo menu")
    return ap.parse_args(argv)


def main(argv=None):
    args = argumentos(argv)
    # Antes de qualquer janela: depois o Windows nao deixa mudar (monitores.py).
    modo_dpi = monitores.tornar_dpi_aware()
    # Sem telas.json e o AP1: uma tela, a do config, com pose identidade.
    if not args.uma_tela and not os.path.exists(args.telas):
        if os.path.abspath(args.telas) != os.path.abspath(config.TELAS_FILE):
            raise SystemExit(f"--telas {args.telas}: arquivo nao existe")
        print(f"sem {args.telas}: modo de uma tela (AP1). Para usar as duas telas, "
              "rode o calibrar_telas.py (ver docs/TESTE_AP2.md).")
    lista = None if args.uma_tela else tls.carregar(args.telas)
    multi = lista is not None
    if not multi:
        lista = [tls.tela_do_config()]
    elif len(lista) == 1:
        multi = False
    if multi:
        # Calibracao de duas telas, mas o monitor externo nao esta ligado agora:
        # em vez de parar pedindo --uma-tela, abre so no notebook.
        mons = monitores.listar_monitores()
        if len(mons) < 2 or any(monitores.achar_monitor(mons, tl.monitor) is None
                                for tl in lista):
            print("monitor externo nao encontrado: abrindo com uma tela so. Para as duas "
                  "telas, ligue o monitor e escolha Estender (Win+P).")
            lista, multi = [tls.tela_do_config()], False
    janelas, tamanhos = abrir_janelas(lista, multi)
    px_w, px_h = tamanhos[0]
    cap = tracking.open_camera()
    cam_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cam_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    f_px = tracking.load_calibration(cam_w, cam_h)
    landmarker = tracking.make_landmarker()
    clock = tracking.Clock()
    cenas = scn.CENAS + (sala.CENAS_MUNDO if multi else [])
    if args.cenas:
        cenas = [c for c in args.cenas.split(",") if c in cenas] or cenas
    nome_cena = args.cena if args.cena in cenas else (
        config.CENA_INICIAL if config.CENA_INICIAL in cenas else cenas[0])
    cena_estatica = construir(nome_cena, lista)
    # Fundos pre-calculados por cenario e por tela. None e preencher de preto.
    fundos = {nome_cena: [scn.fundo(nome_cena, w, h) for w, h in tamanhos]}
    t_inicio = time.perf_counter()
    # Canvas alocado uma vez e reusado: alocar 6 MB por frame custava 13 ms,
    # tanto quanto desenhar a cena inteira.
    canvases = [np.zeros((h, w, 3), np.uint8) for w, h in tamanhos]
    canvas = canvases[0]          # o do notebook: e nele que vai o HUD
    # Um alvo por olho e por tela, tambem reaproveitados. So o anaglifo usa: o
    # modo mono e o de olho unico desenham direto no canvas, sem copia nenhuma.
    bufs = [(np.zeros_like(c), np.zeros_like(c)) for c in canvases]
    monitores.focar_janela(janelas[0])

    min_cutoff, beta = config.MIN_CUTOFF, config.BETA
    filtro = filters.OneEuro3D(min_cutoff, beta, config.D_CUTOFF)
    # Instancia propria para a rolagem, com os mesmos parametros de partida.
    # Theta e um escalar em radianos, nao um quarto eixo de posicao: nao entra
    # no OneEuro3D e nao acompanha os ajustes ao vivo de min_cutoff e beta.
    filtro_theta = filters.OneEuro(config.MIN_CUTOFF, config.BETA, config.D_CUTOFF)
    usar_filtro = True
    corrigir_guinada = config.CORRIGIR_GUINADA
    guinada, k_escorco, tem_matriz = 0.0, 1.0, False   # so para o overlay
    # Eixo entre os olhos em 3D, no mundo, para o par estereo (ver abaixo).
    filtro_eixo = filters.OneEuro3D(config.MIN_CUTOFF, config.BETA, config.D_CUTOFF)
    eixo_olhos = None
    head = HEAD_PADRAO.copy()
    theta = 0.0
    ipd_px = 0.0
    stereo_scale = config.STEREO_SCALE
    escala_auto = config.STEREO_AUTO
    if args.anaglifo and not multi:
        stereo_scale, escala_auto = ESCALA_MINIMA, False
    paleta = scn.paleta_neutra()
    usar_paleta = True
    z_min_estatico = z_min_estaticos(nome_cena, cena_estatica, lista)
    congelado = None     # (eye, theta, eixo) capturados pela barra de espaco
    solo = None          # None, "L" ou "R": um olho so, para diagnostico
    trocar_olhos = False
    teste_vazamento = False
    # Medido pelo usuario na tecla 0, e reaproveitado como o k do cancelamento:
    # e exatamente a mesma grandeza, a fracao que a lente errada deixa passar.
    vazamento_pct = 10
    cancelar_ghost = False
    anaglifo = bool(args.anaglifo and not multi)   # mono e o padrao; a tecla 3 liga
    modo_comp = "gray"
    debug = False
    historico = deque(maxlen=45)
    fps, t_prev, ms_render = 0.0, time.perf_counter(), 0.0

    print(f"janela {px_w}x{px_h}   webcam {cam_w}x{cam_h}   f_px {f_px:.1f}   "
          f"DPI {modo_dpi}")
    if multi:
        print("telas.json: " + ", ".join(f"{tl.nome} {w}x{h}"
                                         for tl, (w, h) in zip(lista, tamanhos)))
    print("q sai | n cena | f filtro | y guinada | d debug | ESPACO congela | "
          ",. min_cutoff | kl beta")
    print("estereo: 3 anaglifo | c algoritmo | p paleta | a escala auto "
          "| g cancelamento | [ ] escala | 1 so olho esq | 2 so olho dir "
          "| s troca L/R | 0 teste de vazamento")

    while True:
        frame = tracking.read_frame(cap)
        tem_rosto = False
        if frame is not None:
            pts, eixo = tracking.find_landmarks_pose(landmarker, frame,
                                                     clock.now_ms())
            if pts is not None:
                # eixo None = sem correcao (tecla y, ou MediaPipe sem matriz).
                bruto = tracking.head_position(
                    pts, frame.shape, f_px,
                    eixo if corrigir_guinada else None)
                if not np.isfinite(bruto).all():
                    # Medida absurda (ipd_px zero, landmark perdido): conta como
                    # quadro sem rosto. Um inf que entrasse no One Euro deixaria
                    # o estado dele em NaN para sempre.
                    pts = None
            if pts is not None:
                tem_rosto = True
                ipd_px, _mid = tracking.ipd_and_midpoint(pts[tracking.IRIS_L],
                                                         pts[tracking.IRIS_R])
                tem_matriz = eixo is not None
                if eixo is not None:
                    guinada = tracking.guinada_graus(eixo)
                    k_escorco = tracking.fator_escorco(eixo, _mid, frame.shape,
                                                       f_px)
                else:
                    guinada, k_escorco = 0.0, 1.0
                # O filtro e alimentado sempre, mesmo desligado, para que o
                # estado dele fique atual e o toggle nao provoque salto.
                suave = np.array(filtro(bruto, time.perf_counter()))
                head = suave if usar_filtro else bruto

                # Rolagem da cabeca: a inclinacao da reta entre as duas irises.
                # O menos em v e a conversao de eixo de sempre, porque o eixo
                # vertical da imagem cresce para baixo.
                #
                # O 468 e a iris do olho ESQUERDO da pessoa. Como o frame chega
                # espelhado (FLIP_FRAME), ela cai do lado esquerdo da imagem,
                # com u menor, e a conta entrega d apontando para a SUA direita,
                # que e o +X da tela. Se a profundidade sair invertida a correcao
                # e a tecla s, que troca os dois olhos: nao mexa nos indices,
                # porque o resto do tracking depende deles.
                (u_l, v_l), (u_r, v_r) = pts[tracking.IRIS_L], pts[tracking.IRIS_R]
                # Filtrado sempre, mesmo com o One Euro da posicao desligado: o
                # A/B da tecla f e sobre a posicao, e theta treme de qualquer
                # jeito porque os landmarks tremem.
                theta = filtro_theta(math.atan2(-(v_r - v_l), u_r - u_l),
                                     time.perf_counter())

                # Eixo entre os olhos em 3D, para o par estereo. O theta acima e
                # so a inclinacao 2D na imagem, e com duas telas ele mente:
                # virar a cabeca para o monitor, com a camera 10 cm acima dos
                # olhos, aparece como rolagem falsa (a iris mais longe sobe), e
                # um eixo preso ao plano do notebook poe os dois olhos a
                # distancias diferentes do monitor girado. As duas coisas viram
                # paralaxe vertical, que nao funde. A rotacao da cabeca do
                # MediaPipe da o eixo de verdade. Imagem espelhada -> mundo:
                # x = +X, y para baixo = -Y, profundidade = +Z. O sinal segue
                # o vetor iris esquerda -> direita, que aponta para +X.
                if eixo is not None:
                    d = np.array([eixo[0], -eixo[1], eixo[2]], float)
                    if d[0] * (u_r - u_l) - d[1] * (v_r - v_l) < 0:
                        d = -d
                    if not config.USE_HEAD_ROLL:
                        d[1] = 0.0
                    d = np.array(filtro_eixo(d, time.perf_counter()), float)
                    eixo_olhos = d / max(np.linalg.norm(d), 1e-9)
                else:
                    eixo_olhos = None

        eye = tracking.eye_in_screen_coords(head)
        eye[2] = max(eye[2], config.EYE_Z_MIN)
        theta_uso = theta if config.USE_HEAD_ROLL else 0.0
        eixo_uso = eixo_olhos
        if congelado is not None:
            eye, theta_uso, eixo_uso = congelado
        historico.append(eye.copy())

        t0 = time.perf_counter()
        t_cena = t0 - t_inicio
        mundo = nome_cena in sala.CENAS_MUNDO
        # O olho no referencial de cada tela. No notebook (pose identidade) e o
        # proprio eye: o modo de uma tela continua sendo o AP1 bit a bit.
        olhos = [tls.olho_local(eye, tl) for tl in lista]
        # Parte estatica construida uma vez, parte dinamica (as chamas) por frame.
        # Ordenar e desenhar sao passos separados: a ordem sai uma vez so, do
        # olho ciclopico, e no modo estereo servira aos dois olhos.
        if mundo:
            # Mundo compartilhado: UMA ordem, no mundo, para todas as telas, e a
            # oclusao concorda dos dois lados do bezel.
            dinamicos = sala.dinamico(nome_cena, t_cena, lista)
            ordem = tls.ordenar_mundo(cena_estatica + dinamicos, eye)
            z_mins = [min(ze, tls.z_minimo_tela(dinamicos, tl))
                      for ze, tl in zip(z_min_estatico, lista)]
        else:
            # Uma caixa por tela: o AP1 repetido, cada um no referencial da sua.
            dinamicos = [scn.dinamico(nome_cena, t_cena, tl.dims) for tl in lista]
            ordem = [scn.order_faces(est + din, e)
                     for est, din, e in zip(cena_estatica, dinamicos, olhos)]
            z_mins = [min(ze, scn.z_minimo(din))
                      for ze, din in zip(z_min_estatico, dinamicos)]
        if escala_auto:
            # UMA escala para todas as telas, senao a disparidade salta no bezel.
            # A formula do AP1 no referencial de cada tela e exata no notebook e
            # conservadora no monitor girado (t_estereo.py); vale a menor.
            stereo_scale = min(scn.escala_confortavel(e, z) for e, z in zip(olhos, z_mins))
        if eixo_uso is not None:
            # Translacao pura, como no stereo_eyes, mas pelo eixo 3D da cabeca.
            meia = (config.IPD_REAL / 2.0) * stereo_scale
            eye_L, eye_R = eye - meia * eixo_uso, eye + meia * eixo_uso
        else:
            eye_L, eye_R = scn.stereo_eyes(eye, theta_uso, stereo_scale)
        if trocar_olhos:
            eye_L, eye_R = eye_R, eye_L
        pal = paleta if (anaglifo and usar_paleta) else None
        for i, (cv, (buf_L, buf_R)) in enumerate(zip(canvases, bufs)):
            fnd = fundos[nome_cena][i]
            if teste_vazamento:
                if i == 0:
                    anaglyph.padrao_vazamento(cv, vazamento_pct)
                else:
                    cv[:] = 0
            elif solo is not None:
                # Diagnostico: um olho so, sem composicao. E o que deixa conferir
                # o estereo sem os oculos.
                render_tela_i(eye_L if solo == "L" else eye_R, i, lista, ordem, mundo,
                              cv, fnd, pal)
            elif anaglifo:
                render_tela_i(eye_L, i, lista, ordem, mundo, buf_L, fnd, pal)
                render_tela_i(eye_R, i, lista, ordem, mundo, buf_R, fnd, pal)
                anaglyph.compor(buf_L, buf_R, cv, modo_comp,
                                vazamento_pct / 100.0 if cancelar_ghost else 0.0,
                                config.ANAGLYPH_PEDESTAL if cancelar_ghost else 0)
            else:
                # O monoscopico de sempre: o olho ciclopico, uma vez so, direto
                # no canvas, com as cores da cena.
                render_tela_i(eye, i, lista, ordem, mundo, cv, fnd)
        ms_render = (time.perf_counter() - t0) * 1000

        agora = time.perf_counter()
        fps = 0.9 * fps + 0.1 / max(agora - t_prev, 1e-6)
        t_prev = agora

        if debug:
            tremor = np.array(historico).std(axis=0) * 1000
            desenhar_debug(canvas, head, ipd_px, fps, ms_render, tem_rosto,
                           usar_filtro, min_cutoff, beta, tremor, nome_cena,
                           math.degrees(theta_uso),
                           {"ativo": anaglifo, "modo": modo_comp, "solo": solo,
                            "paleta": usar_paleta, "escala": stereo_scale,
                            "ghost": vazamento_pct if cancelar_ghost else 0,
                            "auto": escala_auto, "limite": px_w / 30,
                            "paralaxe": scn.paralaxe_px(olhos[0], z_mins[0], px_w,
                                                        theta_uso, stereo_scale)},
                           (guinada, k_escorco, corrigir_guinada, tem_matriz))
        # Daqui para baixo e tudo overlay, sempre DEPOIS da composicao e sempre
        # em cor neutra quando ela esta ativa: canal isolado fantasma.
        cor_aviso = (255, 255, 255) if (anaglifo and solo is None) else (0, 200, 255)
        if congelado is not None:
            cv2.putText(canvas, "OLHO CONGELADO", (px_w - 340, 50), FONT, 0.8,
                        cor_aviso, 2, cv2.LINE_AA)
        if solo is not None:
            texto = "OLHO ESQUERDO" if solo == "L" else "OLHO DIREITO"
            cv2.putText(canvas, texto + (" (trocado)" if trocar_olhos else ""),
                        (px_w - 340, 88), FONT, 0.8, cor_aviso, 2, cv2.LINE_AA)

        if args.app and not debug:
            # Apresentacao: tela limpa. So uma dica curta nos primeiros segundos.
            if t_cena < 6.0:
                dica = "ESC menu    N proxima cena    ESPACO congela    D detalhes"
                if anaglifo:
                    dica += "    [ ] profundidade do 3D"
                cv2.putText(canvas, dica, (24, px_h - 24), FONT, 0.6, (120, 120, 120),
                            1, cv2.LINE_AA)
        else:
            # Legenda sempre visivel: em fullscreen nao da para consultar o terminal.
            cv2.putText(canvas, "q sai   n cena   f filtro   y guinada   d debug   "
                                "ESPACO congela   ,. min_cutoff   kl beta",
                        (24, px_h - 56), FONT, 0.55, (90, 90, 90), 1, cv2.LINE_AA)
            # Cinza neutro (90,90,90) ja sobrevive a composicao: canais iguais nao
            # fantasmam, os dois olhos leem o mesmo texto.
            cv2.putText(canvas, "3 anaglifo   c algoritmo   p paleta   "
                                "a escala auto   g cancelamento   [ ] escala   "
                                "1 so olho esq   2 so olho dir   s troca L/R   "
                                "0 teste de vazamento",
                        (24, px_h - 24), FONT, 0.55, (90, 90, 90), 1, cv2.LINE_AA)

        for nome_janela, cv in zip(janelas, canvases):
            cv2.imshow(nome_janela, cv)
        tecla = cv2.waitKey(1) & 0xFF
        if tecla in (ord("q"), 27):
            break
        if tecla == ord("f"):
            usar_filtro = not usar_filtro
        if tecla == ord("y"):
            # O One Euro amacia o degrau da troca; nao precisa resetar o filtro.
            corrigir_guinada = not corrigir_guinada
        if tecla == ord("d"):
            debug = not debug
        if tecla == ord("n"):
            nome_cena = cenas[(cenas.index(nome_cena) + 1) % len(cenas)]
            cena_estatica = construir(nome_cena, lista)
            z_min_estatico = z_min_estaticos(nome_cena, cena_estatica, lista)
            if nome_cena not in fundos:
                fundos[nome_cena] = [scn.fundo(nome_cena, w, h) for w, h in tamanhos]
            t_inicio = time.perf_counter()
            if anaglifo:
                stereo_scale, escala_auto = ESCALA_MINIMA, False
        if tecla == ord(" "):
            congelado = (None if congelado is not None else
                         (eye.copy(), theta_uso, None if eixo_uso is None else eixo_uso.copy()))
        if tecla in (ord(","), ord(".")):
            min_cutoff = max(0.05, min_cutoff * (0.8 if tecla == ord(",") else 1.25))
            filtro.ajustar(min_cutoff=min_cutoff)
        if tecla in (ord("k"), ord("l")):
            beta = 0.007 if tecla == ord("l") and beta < 0.007 else beta
            beta = max(0.0, beta * (0.7 if tecla == ord("k") else 1.4))
            filtro.ajustar(beta=beta)
        # ------------------------------------------------------------- estereo
        if tecla == ord("0"):
            teste_vazamento = not teste_vazamento
        if tecla == ord("3") and not multi:
            # So com uma tela. Ao ligar, comeca da menor separacao.
            anaglifo = not anaglifo
            if anaglifo:
                stereo_scale, escala_auto = ESCALA_MINIMA, False
        if tecla == ord("g"):
            cancelar_ghost = not cancelar_ghost
        if tecla == ord("p"):
            # Com a paleta neutra ligada, gray e true dao a MESMA imagem: num
            # pixel cinza os dois algoritmos coincidem por construcao. Desligar
            # devolve a cor da cena e e o unico jeito de comparar os tres.
            usar_paleta = not usar_paleta
        if tecla == ord("c"):
            modo_comp = anaglyph.MODOS[(anaglyph.MODOS.index(modo_comp) + 1)
                                       % len(anaglyph.MODOS)]
        if tecla == ord("a"):
            escala_auto = not escala_auto
        if tecla in (ord("["), ord("]")):
            passo = -1 if tecla == ord("[") else 1
            if teste_vazamento:
                # No teste as mesmas teclas ajustam a referencia, porque a
                # escala do estereo nao significa nada com o padrao na tela.
                vazamento_pct = min(60, max(0, vazamento_pct + passo))
            else:
                # Mexer na mao desliga o automatico, continuando do valor atual:
                # sem isso a tecla nao teria efeito e pareceria quebrada.
                escala_auto = False
                stereo_scale = max(0.0, round(stereo_scale + passo * 0.1, 1))
        if tecla in (ord("1"), ord("2")):
            # Apertar de novo a mesma tecla volta ao normal.
            alvo = "L" if tecla == ord("1") else "R"
            solo = None if solo == alvo else alvo
        if tecla == ord("s"):
            trocar_olhos = not trocar_olhos
        if any(cv2.getWindowProperty(n, cv2.WND_PROP_VISIBLE) < 1 for n in janelas):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 1:
        # Sem argumentos (por exemplo, o botao de executar do editor): abre o
        # menu do Parallax, que e a porta de entrada do programa. Para cair
        # direto no laco das cenas, com as legendas de teclas: --direto.
        import parallax
        sys.exit(parallax.main())
    main()
