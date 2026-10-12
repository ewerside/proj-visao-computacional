"""Calibracao da distancia focal da webcam, em pixels. Rode uma vez.

Modelo pinhole: um segmento de comprimento real L, perpendicular ao eixo optico
e a distancia D, projeta l pixels na imagem, com l = f_px * L / D. Usando a sua
distancia interpupilar como o segmento conhecido:

    f_px = ipd_px * D / IPD_REAL

Como usar:
  1. Preencha IPD_REAL e CALIB_DISTANCE no config.py.
  2. Sente-se a CALIB_DISTANCE da lente, medida PERPENDICULAR ao plano da tela.
  3. Centralize o rosto no quadro e olhe reto para a camera.
  4. Rode este script e aperte ESPACO para capturar.

Duas fontes de erro sistematico que o script tenta te proteger:
  - Guinada da cabeca. ipd_px encolhe com cos(yaw), o que infla o f_px. Por isso
    o indicador de frontalidade, e a captura so libera acima do limiar.
  - Rosto fora do centro do quadro. Longe do eixo optico a distorcao radial da
    lente cresce e o segmento deixa de ser perpendicular ao eixo.
"""

import json
import sys
import time

import cv2
import numpy as np

import config
import tracking

# Landmarks para o proxy de frontalidade: cantos externos dos dois olhos e ponta
# do nariz. O nariz projeta para fora do plano do rosto, entao a razao entre as
# duas distancias canto->nariz e sensivel a guinada e barata de calcular.
NOSE_TIP = 1
EYE_OUTER_A = 33
EYE_OUTER_B = 263

FRONTAL_MIN = 0.92    # abaixo disso o rosto esta virado demais para calibrar
N_SAMPLES = 90        # ~4 s a 23 fps
FONT = cv2.FONT_HERSHEY_SIMPLEX
WINDOW = "calibracao"


def frontality(pts):
    """1.0 = rosto de frente para a camera. Cai conforme a cabeca gira."""
    da = np.linalg.norm(pts[EYE_OUTER_A] - pts[NOSE_TIP])
    db = np.linalg.norm(pts[EYE_OUTER_B] - pts[NOSE_TIP])
    return min(da, db) / max(da, db)


def centering(pts, frame_shape):
    """Distancia do ponto medio das irises ao centro do quadro, em fracao da largura."""
    h, w = frame_shape[:2]
    mid = (pts[tracking.IRIS_L] + pts[tracking.IRIS_R]) / 2.0
    return float(np.linalg.norm(mid - np.array([w / 2.0, h / 2.0])) / w)


def draw_hud(frame, pts, samples):
    """Desenha o estado atual. Retorna True se esta em condicao de capturar."""
    h, w = frame.shape[:2]
    ipd_px, mid = tracking.ipd_and_midpoint(pts[tracking.IRIS_L], pts[tracking.IRIS_R])
    front = frontality(pts)
    off = centering(pts, frame.shape)
    ok = front >= FRONTAL_MIN

    cv2.line(frame, tuple(pts[tracking.IRIS_L].astype(int)),
             tuple(pts[tracking.IRIS_R].astype(int)), (0, 255, 0), 1)
    cv2.drawMarker(frame, (w // 2, h // 2), (80, 80, 80), cv2.MARKER_CROSS, 24, 1)
    cv2.circle(frame, tuple(mid.astype(int)), 4, (255, 0, 255), -1)

    cv2.putText(frame, f"ipd_px {ipd_px:6.2f}", (20, 40), FONT, 0.9, (0, 255, 0), 2)
    cv2.putText(frame, f"frontalidade {front:.3f}" + ("" if ok else "  <-- OLHE RETO"),
                (20, 75), FONT, 0.6, (0, 255, 0) if ok else (0, 0, 255), 2)
    cv2.putText(frame, f"descentralizacao {off:.3f}", (20, 100), FONT, 0.6,
                (200, 200, 200) if off < 0.12 else (0, 165, 255), 1)

    if samples is None:
        cv2.putText(frame, "ESPACO captura   q sai", (20, h - 20), FONT, 0.6, (200, 200, 200), 1)
    else:
        cv2.putText(frame, f"capturando {len(samples)}/{N_SAMPLES}", (20, h - 20),
                    FONT, 0.7, (0, 255, 255), 2)
    return ok


def compute_and_save(ipd_samples, frame_w, frame_h, distance_m):
    """Calcula f_px a partir das amostras, grava o focal.json e devolve o resumo."""
    a = np.array(ipd_samples)
    # Mediana em vez de media: imune a frames em que o landmark pulou.
    ipd_px = float(np.median(a))
    f_px = ipd_px * distance_m / config.IPD_REAL

    # Sanidade: o campo de visao horizontal implicado por esse f_px. Webcam de
    # notebook fica tipicamente entre 55 e 78 graus. Fora disso, algo esta errado
    # na distancia informada.
    hfov = float(np.degrees(2 * np.arctan(frame_w / (2 * f_px))))

    # A resolucao vai junto: f_px esta em pixels do frame capturado. Se a captura
    # mudar de resolucao, o f_px desta calibracao deixa de valer. E o IPD_REAL
    # tambem, porque main.py precisa usar o mesmo valor para o Z fechar.
    data = {
        "f_px": f_px,
        "ipd_px_median": ipd_px,
        "ipd_px_std": float(a.std()),
        "n_samples": len(a),
        "calib_distance_m": distance_m,
        "ipd_real_m": config.IPD_REAL,
        "frame_w": frame_w,
        "frame_h": frame_h,
        "hfov_deg": hfov,
        "sane": bool(45.0 <= hfov <= 85.0),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(config.CALIB_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return data


def print_result(d):
    print()
    print(f"  amostras       {d['n_samples']}")
    print(f"  ipd_px mediana {d['ipd_px_median']:.2f}  (desvio {d['ipd_px_std']:.2f} px)")
    print(f"  D              {d['calib_distance_m']:.3f} m")
    print(f"  IPD_REAL       {d['ipd_real_m']:.4f} m")
    print()
    print(f"  f_px = {d['f_px']:.1f}")
    print(f"  campo de visao horizontal implicado: {d['hfov_deg']:.1f} graus"
          + ("   OK" if d["sane"] else "   <-- SUSPEITO, confira a distancia informada"))
    print()
    print("  gravado em " + config.CALIB_FILE)


def draw_result(d, w, h):
    """Tela de resultado, desenhada na propria janela.

    Durante a captura voce esta olhando para a camera, nao para a tela. O
    resultado precisa ficar parado na janela esperando, senao passa despercebido.
    """
    canvas = np.zeros((h, w, 3), np.uint8)
    green, grey, white = (0, 255, 0), (170, 170, 170), (255, 255, 255)
    red, yellow = (0, 0, 255), (0, 255, 255)

    cv2.putText(canvas, "CALIBRACAO CONCLUIDA", (60, 90), FONT, 1.1, white, 2)
    cv2.putText(canvas, f"f_px = {d['f_px']:.1f}", (60, 200), FONT, 2.0, green, 3)

    sane = d["sane"]
    cv2.putText(canvas, f"campo de visao implicado: {d['hfov_deg']:.1f} graus",
                (60, 270), FONT, 0.85, green if sane else red, 2)
    cv2.putText(canvas,
                "esperado 55-78 para webcam de notebook" if sane
                else "FORA DO ESPERADO - a distancia informada provavelmente esta errada",
                (60, 305), FONT, 0.6, grey if sane else red, 1)

    lines = [
        f"ipd_px mediana   {d['ipd_px_median']:.2f} px   (desvio {d['ipd_px_std']:.2f})",
        f"distancia usada  {d['calib_distance_m']:.3f} m",
        f"IPD_REAL         {d['ipd_real_m']:.4f} m",
        f"amostras         {d['n_samples']}",
        f"resolucao        {d['frame_w']}x{d['frame_h']}",
    ]
    for i, line in enumerate(lines):
        cv2.putText(canvas, line, (60, 370 + i * 34), FONT, 0.65, grey, 1)

    cv2.putText(canvas, "gravado em focal.json", (60, 370 + len(lines) * 34 + 20),
                FONT, 0.65, yellow, 1)
    cv2.putText(canvas, "ESPACO repete a calibracao      q sai", (60, h - 40),
                FONT, 0.7, white, 2)
    return canvas


def capture(cap, landmarker, clock):
    """Roda o preview e devolve as amostras de ipd_px, ou None se cancelado."""
    samples = None
    while True:
        frame = tracking.read_frame(cap)
        if frame is None:
            return None
        pts = tracking.find_landmarks(landmarker, frame, clock.now_ms())

        if pts is None:
            cv2.putText(frame, "sem rosto", (20, 40), FONT, 0.9, (0, 0, 255), 2)
        else:
            ok = draw_hud(frame, pts, samples)
            if samples is not None:
                if ok:
                    samples.append(tracking.ipd_and_midpoint(
                        pts[tracking.IRIS_L], pts[tracking.IRIS_R])[0])
                if len(samples) >= N_SAMPLES:
                    return samples

        cv2.imshow(WINDOW, frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            return None
        if key == ord(" ") and samples is None and pts is not None:
            samples = []


def main():
    # A distancia pode vir na linha de comando: `python calibrate.py 0.594`.
    # O valor nao precisa ser redondo nem ser 60 cm, precisa ser CONHECIDO: ele
    # e a unica regua do sistema. Duas folhas A4 no lado comprido dao 0.594 m.
    distance_m = float(sys.argv[1]) if len(sys.argv) > 1 else config.CALIB_DISTANCE

    print("CALIBRACAO DA DISTANCIA FOCAL")
    print(f"  sente-se a {distance_m:.3f} m da lente (perpendicular ao plano da tela)")
    print(f"  usando IPD_REAL = {config.IPD_REAL:.4f} m")
    print("  centralize o rosto, olhe reto, ESPACO para capturar")
    print()

    cap = tracking.open_camera()
    landmarker = tracking.make_landmarker()
    clock = tracking.Clock()
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    while True:
        samples = capture(cap, landmarker, clock)
        if not samples:
            print()
            print("  cancelado, nada gravado")
            break

        data = compute_and_save(samples, frame_w, frame_h, distance_m)
        print_result(data)

        # A janela fica parada no resultado ate voce decidir.
        cv2.imshow(WINDOW, draw_result(data, frame_w, frame_h))
        while True:
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("q"), ord(" ")):
                break
        if key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
