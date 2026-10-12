"""Loop principal do head-coupled perspective.

Teclas:
  q ou ESC  sai
  f         liga/desliga o One Euro Filter (comparacao A/B)
  d         liga/desliga o overlay de debug
  ESPACO    congela a posicao do olho e a rolagem
  n         troca de cenario (caixa / corredor / miniatura / barras)
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
"""

import ctypes
import math
import time
from collections import deque

import cv2
import numpy as np

import anaglyph
import config
import filters
import scene as scn
import tracking

WINDOW = "head-coupled"
FONT = cv2.FONT_HERSHEY_SIMPLEX

# Posicao da cabeca usada antes da primeira deteccao de rosto.
HEAD_PADRAO = np.array([0.0, -config.CAM_OFFSET_Y, 0.60])


def focar_janela():
    """Traz a janela para frente e entrega o foco de teclado a ela.

    Sem isso o foco continua no terminal que lancou o script e o cv2.waitKey
    nunca ve tecla nenhuma: a janela fica em fullscreen sem responder nem ao q.
    O toque no ALT antes do SetForegroundWindow contorna a trava de foreground
    do Windows, que de outro modo recusa a troca de foco vinda de outro processo.
    """
    try:
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, WINDOW)
        if hwnd:
            u.keybd_event(0x12, 0, 0, 0)
            u.SetForegroundWindow(hwnd)
            u.keybd_event(0x12, 0, 2, 0)
    except Exception:
        pass


def abrir_janela():
    """Abre em fullscreen, pega o foco e devolve o tamanho real em pixels.

    Usamos o tamanho real da janela, nao o do config: se o Windows estiver com
    escala de DPI diferente de 100%, os dois divergem. Como a janela cobre a tela
    inteira, mapear metros para fracao da janela continua correto de qualquer jeito.
    """
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.imshow(WINDOW, np.zeros((config.SCREEN_PX_H, config.SCREEN_PX_W, 3), np.uint8))
    cv2.waitKey(1)
    focar_janela()
    _x, _y, w, h = cv2.getWindowImageRect(WINDOW)
    if w <= 0 or h <= 0:
        w, h = config.SCREEN_PX_W, config.SCREEN_PX_H
    return w, h


def desenhar_debug(canvas, head, ipd_px, fps, ms_render, tem_rosto,
                   usar_filtro, min_cutoff, beta, tremor_mm, nome_cena,
                   roll_graus, estereo):
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


def main():
    px_w, px_h = abrir_janela()
    cap = tracking.open_camera()
    cam_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cam_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    f_px = tracking.load_calibration(cam_w, cam_h)
    landmarker = tracking.make_landmarker()
    clock = tracking.Clock()
    nome_cena = config.CENA_INICIAL
    cena_estatica = scn.build(nome_cena)
    # Fundos pre-calculados por cenario. None significa preencher de preto.
    fundos = {nome_cena: scn.fundo(nome_cena, px_w, px_h)}
    t_inicio = time.perf_counter()
    # Canvas alocado uma vez e reusado: alocar 6 MB por frame custava 13 ms,
    # tanto quanto desenhar a cena inteira.
    canvas = np.zeros((px_h, px_w, 3), np.uint8)
    # Um alvo por olho, tambem reaproveitados. So o anaglifo usa os dois: o modo
    # mono e o de olho unico desenham direto no canvas, sem copia nenhuma.
    buf_L = np.zeros_like(canvas)
    buf_R = np.zeros_like(canvas)
    focar_janela()

    min_cutoff, beta = config.MIN_CUTOFF, config.BETA
    filtro = filters.OneEuro3D(min_cutoff, beta, config.D_CUTOFF)
    # Instancia propria para a rolagem, com os mesmos parametros de partida.
    # Theta e um escalar em radianos, nao um quarto eixo de posicao: nao entra
    # no OneEuro3D e nao acompanha os ajustes ao vivo de min_cutoff e beta.
    filtro_theta = filters.OneEuro(config.MIN_CUTOFF, config.BETA, config.D_CUTOFF)
    usar_filtro = True
    head = HEAD_PADRAO.copy()
    theta = 0.0
    ipd_px = 0.0
    stereo_scale = config.STEREO_SCALE
    escala_auto = config.STEREO_AUTO
    paleta = scn.paleta_neutra()
    usar_paleta = True
    z_min_estatico = scn.z_minimo(cena_estatica)
    congelado = None     # (eye, theta) capturados pela barra de espaco
    solo = None          # None, "L" ou "R": um olho so, para diagnostico
    trocar_olhos = False
    teste_vazamento = False
    # Medido pelo usuario na tecla 0, e reaproveitado como o k do cancelamento:
    # e exatamente a mesma grandeza, a fracao que a lente errada deixa passar.
    vazamento_pct = 10
    cancelar_ghost = False
    anaglifo = False     # mono e o padrao; a tecla 3 liga
    modo_comp = "gray"
    debug = False
    historico = deque(maxlen=45)
    fps, t_prev, ms_render = 0.0, time.perf_counter(), 0.0

    print(f"janela {px_w}x{px_h}   webcam {cam_w}x{cam_h}   f_px {f_px:.1f}")
    print("q sai | n cena | f filtro | d debug | ESPACO congela | "
          ",. min_cutoff | kl beta")
    print("estereo: 3 anaglifo | c algoritmo | p paleta | a escala auto "
          "| g cancelamento | [ ] escala | 1 so olho esq | 2 so olho dir "
          "| s troca L/R | 0 teste de vazamento")

    while True:
        frame = tracking.read_frame(cap)
        tem_rosto = False
        if frame is not None:
            pts = tracking.find_landmarks(landmarker, frame, clock.now_ms())
            if pts is not None:
                tem_rosto = True
                bruto = tracking.head_position(pts, frame.shape, f_px)
                ipd_px, _mid = tracking.ipd_and_midpoint(pts[tracking.IRIS_L],
                                                         pts[tracking.IRIS_R])
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

        eye = tracking.eye_in_screen_coords(head)
        eye[2] = max(eye[2], config.EYE_Z_MIN)
        theta_uso = theta if config.USE_HEAD_ROLL else 0.0
        if congelado is not None:
            eye, theta_uso = congelado
        historico.append(eye.copy())

        t0 = time.perf_counter()
        # Parte estatica construida uma vez, parte dinamica (as chamas) por frame.
        dinamicos = scn.dinamico(nome_cena, t0 - t_inicio)
        cena = cena_estatica + dinamicos
        # Ordenar e desenhar sao passos separados: a ordem sai uma vez so, do
        # olho ciclopico, e no modo estereo servira aos dois olhos.
        ordem = scn.order_faces(cena, eye)
        z_min = min(z_min_estatico, scn.z_minimo(dinamicos))
        if escala_auto:
            stereo_scale = scn.escala_confortavel(eye, z_min)
        eye_L, eye_R = scn.stereo_eyes(eye, theta_uso, stereo_scale)
        if trocar_olhos:
            eye_L, eye_R = eye_R, eye_L
        fnd = fundos[nome_cena]
        pal = paleta if (anaglifo and usar_paleta) else None
        if teste_vazamento:
            anaglyph.padrao_vazamento(canvas, vazamento_pct)
        elif solo is not None:
            # Diagnostico: um olho so, sem composicao. E o que deixa conferir o
            # estereo sem os oculos.
            scn.render(eye_L if solo == "L" else eye_R, ordem, canvas, fnd, pal)
        elif anaglifo:
            scn.render(eye_L, ordem, buf_L, fnd, pal)
            scn.render(eye_R, ordem, buf_R, fnd, pal)
            anaglyph.compor(buf_L, buf_R, canvas, modo_comp,
                            vazamento_pct / 100.0 if cancelar_ghost else 0.0,
                            config.ANAGLYPH_PEDESTAL if cancelar_ghost else 0)
        else:
            # O monoscopico de sempre: o olho ciclopico, uma vez so, direto no
            # canvas, com as cores da cena. Nao passa por nada novo.
            scn.render(eye, ordem, canvas, fnd)
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
                            "paralaxe": scn.paralaxe_px(eye, z_min, px_w,
                                                        theta_uso, stereo_scale)})
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

        # Legenda sempre visivel: em fullscreen nao da para consultar o terminal.
        cv2.putText(canvas, "q sai   n cena   f filtro   d debug   ESPACO congela   "
                            ",. min_cutoff   kl beta",
                    (24, px_h - 56), FONT, 0.55, (90, 90, 90), 1, cv2.LINE_AA)
        # Cinza neutro (90,90,90) ja sobrevive a composicao: canais iguais nao
        # fantasmam, os dois olhos leem o mesmo texto.
        cv2.putText(canvas, "3 anaglifo   c algoritmo   p paleta   "
                            "a escala auto   g cancelamento   [ ] escala   "
                            "1 so olho esq   2 so olho dir   s troca L/R   "
                            "0 teste de vazamento",
                    (24, px_h - 24), FONT, 0.55, (90, 90, 90), 1, cv2.LINE_AA)

        cv2.imshow(WINDOW, canvas)
        tecla = cv2.waitKey(1) & 0xFF
        if tecla in (ord("q"), 27):
            break
        if tecla == ord("f"):
            usar_filtro = not usar_filtro
        if tecla == ord("d"):
            debug = not debug
        if tecla == ord("n"):
            nome_cena = scn.CENAS[(scn.CENAS.index(nome_cena) + 1) % len(scn.CENAS)]
            cena_estatica = scn.build(nome_cena)
            z_min_estatico = scn.z_minimo(cena_estatica)
            if nome_cena not in fundos:
                fundos[nome_cena] = scn.fundo(nome_cena, px_w, px_h)
        if tecla == ord(" "):
            congelado = None if congelado is not None else (eye.copy(), theta_uso)
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
        if tecla == ord("3"):
            anaglifo = not anaglifo
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
        if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
