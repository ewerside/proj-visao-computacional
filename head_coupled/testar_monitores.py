"""Teste rapido do Windows com os dois monitores. Rode ANTES de tudo.

    python testar_monitores.py

Abre uma janela em tela cheia em CADA monitor e mostra nelas o nome do
monitor, o tamanho da janela contra o do monitor, a escala do Windows, uma
moldura branca de 1 px nas 4 bordas, um xadrez de 1 px num canto e a ultima
tecla recebida.

O que conferir (as mesmas instrucoes aparecem nas janelas):
  1. Ha uma janela em cada monitor, cobrindo tudo, sem barra de titulo e sem a
     barra de tarefas por cima.
  2. A moldura branca de 1 px aparece INTEIRA nos 4 lados. Faltou um lado no
     monitor ou na TV? E overscan: no menu da TV procure "Ajustar a tela",
     "Just Scan" ou "Tamanho original".
  3. O xadrez de 1 px no canto inferior direito parece um cinza fino e
     uniforme de perto, com quadradinhos nitidos. Borrado ou com faixas: a
     imagem esta sendo esticada (escala do Windows nao tratada).
  4. Clique numa janela, aperte uma tecla, e ela aparece nas DUAS janelas.
     Faca o mesmo clicando na outra.
  5. A palavra NOTEBOOK aparece na tela do notebook. Trocado? Aperte t ate
     ficar certo; ao sair o script diz o que por no config.py.

q ou ESC sai.
"""

import sys

import cv2
import numpy as np

import config
import monitores

FONT = cv2.FONT_HERSHEY_SIMPLEX


def desenhar(img, papel, mon, tam, modo_dpi, tecla):
    h, w = img.shape[:2]
    s = h / 1080.0
    img[:] = 25
    # Moldura de 1 px exatamente na borda: e ela que denuncia overscan.
    img[0, :] = 255
    img[-1, :] = 255
    img[:, 0] = 255
    img[:, -1] = 255
    cv2.rectangle(img, (20, 20), (w - 21, h - 21), (0, 160, 255), 1)
    # Xadrez de 1 px: so continua nitido se a imagem nao for reamostrada.
    lado = int(160 * s)
    xadrez = ((np.indices((lado, lado)).sum(axis=0) % 2) * 255).astype(np.uint8)
    img[h - lado - 40:h - 40, w - lado - 40:w - 40] = xadrez[..., None]

    ok_tam = (tam[0], tam[1]) == (mon.largura, mon.altura)
    cor_tam = (0, 220, 0) if ok_tam else (0, 0, 255)
    cv2.putText(img, papel, (int(60 * s), int(150 * s)), FONT, 3.2 * s,
                (255, 255, 255), max(2, int(7 * s)), cv2.LINE_AA)
    linhas = [
        (f"{mon.dispositivo}   posicao ({mon.x}, {mon.y})"
         + ("   principal" if mon.principal else ""), (210, 210, 210)),
        (f"janela {tam[0]}x{tam[1]}   monitor {mon.largura}x{mon.altura}   "
         + ("OK" if ok_tam else "DIFERENTE (escala/DPI?)"), cor_tam),
        (f"escala do Windows {mon.escala_pct or '?'}%   modo DPI do programa: {modo_dpi}",
         (210, 210, 210)),
        (f"ultima tecla: {tecla}", (0, 220, 255)),
        ("", None),
        ("1. moldura branca de 1 px inteira nos 4 lados? (faltou = overscan da TV)",
         (170, 170, 170)),
        ("2. xadrez do canto inferior direito nitido? (borrado = imagem esticada)",
         (170, 170, 170)),
        ("3. clique em cada janela e aperte uma tecla: aparece nas duas?",
         (170, 170, 170)),
        ("4. NOTEBOOK esta mesmo no notebook? senao aperte t", (170, 170, 170)),
        ("q ou ESC sai", (170, 170, 170)),
    ]
    for i, (txt, cor) in enumerate(linhas):
        if txt:
            cv2.putText(img, txt, (int(60 * s), int((240 + 52 * i) * s)), FONT,
                        1.0 * s, cor, max(1, int(2 * s)), cv2.LINE_AA)


def main():
    modo = monitores.tornar_dpi_aware()
    mons = monitores.listar_monitores()
    print(f"modo DPI do programa: {modo}")
    for i, m in enumerate(mons):
        print(f"  [{i}] {m}")
    if len(mons) < 2:
        print("\nSo ha 1 monitor. Ligue o monitor externo e, no Windows, aperte "
              "Win+P e escolha 'Estender'. Depois rode de novo.")
    i_auto = i_nb = monitores.escolher_notebook(mons)
    nomes = [f"teste monitor {i}" for i in range(len(mons))]
    tamanhos = {}
    # Os outros primeiro e o notebook por ultimo: ele fica com o foco.
    for i in [j for j in range(len(mons)) if j != i_nb] + [i_nb]:
        topo = i != i_nb and getattr(config, "MONITOR_SEMPRE_NO_TOPO", True)
        tamanhos[i] = monitores.abrir_tela_cheia(nomes[i], mons[i], topo)
    canvases = {i: np.zeros((h, w, 3), np.uint8) for i, (w, h) in tamanhos.items()}
    tecla = "-"
    while True:
        for i, m in enumerate(mons):
            desenhar(canvases[i], "NOTEBOOK" if i == i_nb else "MONITOR", m,
                     tamanhos[i], modo, tecla)
            cv2.imshow(nomes[i], canvases[i])
        k = cv2.waitKey(30) & 0xFF
        if k in (ord("q"), 27):
            break
        if k != 255:
            tecla = chr(k) if 32 <= k < 127 else str(k)
        if k == ord("t") and len(mons) > 1:
            i_nb = (i_nb + 1) % len(mons)
        try:
            if any(cv2.getWindowProperty(n, cv2.WND_PROP_VISIBLE) < 1 for n in nomes):
                break
        except cv2.error:
            break
    cv2.destroyAllWindows()

    print("\nResumo:")
    for i, m in enumerate(mons):
        w, h = tamanhos[i]
        ok = (w, h) == (m.largura, m.altura)
        print(f"  [{i}] {m.dispositivo}: janela {w}x{h}, monitor {m.largura}x{m.altura}"
              f" -> {'OK' if ok else 'DIFERENTE: confira a escala do Windows'}")
    print(f"  notebook = [{i_nb}] {mons[i_nb].dispositivo}")
    if i_nb != i_auto:
        print("\nA escolha automatica errou o notebook. Ponha isto no config.py:\n"
              f"    MONITOR_NOTEBOOK = {mons[i_nb].dispositivo!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
