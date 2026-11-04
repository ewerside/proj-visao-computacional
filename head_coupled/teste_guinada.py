"""Teste A/B da correcao de guinada. Uns 10 minutos, com a webcam do notebook.

O que mede: o Z estimado com e sem a correcao enquanto voce GIRA A CABECA
sentado no mesmo lugar. Sem correcao o Z cresce com a guinada (o segmento entre
as irises encurta na imagem); com correcao ele deve ficar quase parado.

"Quase" porque a cabeca gira em torno do pescoco, uns 9 cm atras dos olhos: a
30 graus os olhos de verdade recuam ~1.2 cm e andam ~4.5 cm para o lado. A
tabela mostra essa previsao na coluna "pescoco" para comparar.

Uso ao vivo:
    python teste_guinada.py
  ESPACO comeca/para a gravacao (ao parar, imprime a tabela e grava um CSV)
  q sai

Uso com video gravado (mesma resolucao da calibracao):
    python teste_guinada.py video.mp4 [--f 970.1] [--sem-janela] [--sem-espelho]
  --f usa esse f_px em vez do focal.json; --sem-espelho nao espelha os frames
  (use se o video ja foi gravado espelhado).

PROTOCOLO (10 minutos, notebook com focal.json valido)
 1. Cadeira fixa, costas no encosto, olhos a ~60 cm da tela (trena). Cole dois
    post-its a direita, no plano da tela, a 22 cm e a 35 cm do centro dela
    (20 e 30 graus vistos de 60 cm), e dois iguais a esquerda.
 2. Rode `python teste_guinada.py` e olhe o centro da tela: os dois Z devem
    coincidir (diferenca < 0.5 cm), porque de frente k = 1.
 3. ESPACO. Sem mexer o tronco, aponte o NARIZ para o post-it de 20 graus,
    segure 2 s; para o de 30, segure 2 s; volte ao centro 2 s. Mesmo para a
    esquerda. Repita duas vezes. ESPACO de novo imprime a tabela e grava o CSV.
 4. Arraste a cadeira ~15 cm para a direita e repita o passo 3. E o caso que
    mais pesa com duas telas: cabeca fora do eixo da camera E virada para longe
    dela. Sem correcao o erro aqui passa de 20 cm a 30 graus.
 5. Leitura: "OK" = a correcao removeu 60% ou mais do erro. Na cabeca
    sintetica ela removeu 61 a 100% entre 17 e 35 graus de guinada medida.
    - "corrige demais" ou Z corrigido CAINDO com a guinada: convencao do eixo
      errada. Imprima a matriz de frente: a rotacao deve ser quase a identidade
      e matriz[2, 3] negativo (camera olhando para -z). Confira os sinais em
      tracking.eixo_interocular.
    - "PARCIAL"/"FALHOU" sem corrigir demais: a guinada da matriz esta saindo
      pequena demais; teste o eixo do solvePnP (opcional_pnp.py).
"""

import sys
import time

import cv2
import numpy as np

import config
import tracking

FONT = cv2.FONT_HERSHEY_SIMPLEX
JANELA = "teste de guinada"
R_PESCOCO = 0.09    # olhos ~9 cm a frente do eixo de rotacao da cabeca (medio)


def medir(landmarker, frame, t_ms, f_px):
    """Uma linha de medida, ou None sem rosto/sem matriz."""
    pts, eixo = tracking.find_landmarks_pose(landmarker, frame, t_ms)
    if pts is None or eixo is None:
        return None
    antigo = tracking.head_position(pts, frame.shape, f_px)
    corrigido = tracking.head_position(pts, frame.shape, f_px, eixo)
    _ipd, mid = tracking.ipd_and_midpoint(pts[tracking.IRIS_L], pts[tracking.IRIS_R])
    k = tracking.fator_escorco(eixo, mid, frame.shape, f_px)
    return {"guinada": tracking.guinada_graus(eixo), "k": k,
            "X_ant": antigo[0], "Z_ant": antigo[2],
            "X_cor": corrigido[0], "Z_cor": corrigido[2]}


def tabela(linhas):
    """Mediana por faixa de 5 graus e veredito. Devolve o texto impresso."""
    g = np.array([l_["guinada"] for l_ in linhas])
    za = np.array([l_["Z_ant"] for l_ in linhas]) * 100
    zc = np.array([l_["Z_cor"] for l_ in linhas]) * 100
    xc = np.array([l_["X_cor"] for l_ in linhas]) * 100
    centro = np.abs(g) < 2.5
    if centro.sum() < 5:
        return "poucos frames de frente (|guinada| < 2.5 graus): olhe reto para a tela tambem"
    za0, zc0 = np.median(za[centro]), np.median(zc[centro])
    out = [f"{len(g)} frames.  De frente: Z sem correcao {za0:.1f} cm, com correcao {zc0:.1f} cm",
           "",
           " faixa (graus) |   n | guinada | dZ sem corr | dZ com corr | pescoco | X com corr",
           "---------------+-----+---------+-------------+-------------+---------+-----------"]
    veredito = []
    for lo in range(-45, 45, 5):
        m = (g >= lo) & (g < lo + 5)
        if m.sum() < 3:
            continue
        gm = np.median(g[m])
        da, dc = np.median(za[m]) - za0, np.median(zc[m]) - zc0
        pesc = R_PESCOCO * (1 - np.cos(np.radians(gm))) * 100
        out.append(f"  {lo:+4d} a {lo + 5:+4d}  | {m.sum():3d} | {gm:+6.1f}  |   {da:+7.1f}   |"
                   f"   {dc:+7.1f}   | {pesc:+6.1f}  |  {np.median(xc[m]):+6.1f}")
        if 15 <= abs(gm) <= 35:
            veredito.append((gm, da, dc, pesc))
    out.append("")
    out.append("dZ = mediana da faixa menos a mediana de frente, em cm. 'pescoco' e o")
    out.append("quanto os olhos recuam de verdade so por girar em torno do pescoco.")
    if not veredito:
        out.append("Sem frames entre 15 e 35 graus: gire mais a cabeca (aponte o NARIZ para o alvo).")
    # Criterio: quanto do erro a correcao removeu. Erro = dZ menos o recuo real
    # do pescoco. Na cabeca sintetica a correcao removeu 75 a 100% do erro entre
    # 20 e 40 graus; abaixo de ~2 cm de erro sem correcao nao ha o que medir.
    for gm, da, dc, pesc in veredito:
        e_sem, e_com = da - pesc, dc - pesc
        if e_sem < 2.0:
            out.append(f"guinada {gm:+5.1f}: erro sem correcao so {e_sem:+4.1f} cm, pouco para julgar")
            continue
        reducao = 1.0 - e_com / e_sem
        if e_com < -3.0:
            nota = "FALHOU: corrige demais (sinal do eixo? ver protocolo)"
        elif reducao >= 0.6:
            nota = "OK"
        elif reducao >= 0.4:
            nota = "PARCIAL"
        else:
            nota = "FALHOU"
        out.append(f"guinada {gm:+5.1f}: erro sem correcao {e_sem:+5.1f} cm, com correcao "
                   f"{e_com:+5.1f} cm, reducao {reducao * 100:4.0f}% -> {nota}")
    return "\n".join(out)


def gravar_csv(linhas, caminho):
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write("guinada_graus,k,X_ant_m,Z_ant_m,X_cor_m,Z_cor_m\n")
        for l_ in linhas:
            fh.write(f"{l_['guinada']:.3f},{l_['k']:.5f},{l_['X_ant']:.5f},{l_['Z_ant']:.5f},"
                     f"{l_['X_cor']:.5f},{l_['Z_cor']:.5f}\n")


def hud(frame, m, gravando, n):
    if m is None:
        cv2.putText(frame, "sem rosto", (20, 50), FONT, 1.0, (0, 0, 255), 2)
    else:
        cv2.putText(frame, f"Z sem correcao {m['Z_ant']*100:6.1f} cm", (20, 50), FONT, 1.0,
                    (0, 165, 255), 2)
        cv2.putText(frame, f"Z com correcao {m['Z_cor']*100:6.1f} cm", (20, 95), FONT, 1.0,
                    (0, 255, 0), 2)
        cv2.putText(frame, f"guinada {m['guinada']:+5.1f} graus   k {m['k']:.3f}", (20, 135),
                    FONT, 0.8, (255, 255, 255), 2)
    estado = f"GRAVANDO {n}" if gravando else "ESPACO grava   q sai"
    cv2.putText(frame, estado, (20, frame.shape[0] - 20), FONT, 0.8,
                (0, 0, 255) if gravando else (200, 200, 200), 2)


def ao_vivo():
    cap = tracking.open_camera()
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    f_px = tracking.load_calibration(w, h)
    landmarker = tracking.make_landmarker()
    clock = tracking.Clock()
    linhas, gravando = [], False
    while True:
        frame = tracking.read_frame(cap)
        if frame is None:
            break
        m = medir(landmarker, frame, clock.now_ms(), f_px)
        if gravando and m is not None:
            linhas.append(m)
        hud(frame, m, gravando, len(linhas))
        cv2.imshow(JANELA, frame)
        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord("q"):
            break
        if tecla == ord(" "):
            if gravando and linhas:
                print(tabela(linhas))
                nome = time.strftime("guinada_%H%M%S.csv")
                gravar_csv(linhas, nome)
                print("gravado em", nome)
                linhas = []
            gravando = not gravando
    cap.release()
    cv2.destroyAllWindows()


def de_video(caminho, f_px=None, janela=True, espelhar=True):
    cap = cv2.VideoCapture(caminho)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if f_px is None:
        f_px = tracking.load_calibration(w, h)
    landmarker = tracking.make_landmarker()
    linhas, i = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if espelhar and config.FLIP_FRAME:
            frame = cv2.flip(frame, 1)
        m = medir(landmarker, frame, int(i * 1000 / fps), f_px)
        i += 1
        if m is not None:
            linhas.append(m)
        if janela:
            hud(frame, m, True, len(linhas))
            cv2.imshow(JANELA, frame)
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                break
    cap.release()
    print(f"{i} frames lidos, f_px = {f_px:.1f}")
    print(tabela(linhas))
    gravar_csv(linhas, caminho + ".guinada.csv")
    print("gravado em", caminho + ".guinada.csv")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        ao_vivo()
    else:
        f_arg = float(args[args.index("--f") + 1]) if "--f" in args else None
        de_video(args[0], f_arg, janela="--sem-janela" not in args,
                 espelhar="--sem-espelho" not in args)
