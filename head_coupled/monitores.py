"""Monitores do Windows: escala de tela (DPI), lista de monitores e janela em
tela cheia num monitor escolhido. Usado pelo main.py, pelo calibrar_telas.py e
pelo testar_monitores.py.

Tres armadilhas que este modulo existe para evitar, todas conferidas no codigo
do OpenCV (window_w32.cpp) e na documentacao da Microsoft:

1. ESCALA DE TELA. O Python roda, por padrao, sem avisar o Windows que sabe
   lidar com escala (processo "DPI-unaware"). Com o notebook em 125% ou 150%,
   o Windows entao mente para o programa: diz que a tela tem 1536x864 em vez de
   1920x1080, e estica a imagem depois (fica borrada). Com dois monitores de
   escalas diferentes as posicoes viram uma mistura de coordenadas logicas e
   fisicas. tornar_dpi_aware() resolve, mas TEM de ser chamada antes de criar
   qualquer janela: depois que o modo do processo e definido, o Windows recusa
   mudar.

2. TELA CHEIA NO MONITOR CERTO. O fullscreen do OpenCV ocupa o monitor onde a
   janela ESTA (MonitorFromRect, maior area de intersecao). Por isso a janela e
   movida para dentro do monitor ANTES de virar fullscreen. Janela ja em
   fullscreen ignora outro pedido de fullscreen, e janela AUTOSIZE nunca vira
   fullscreen: daqui sai sempre WINDOW_NORMAL.

3. QUAL MONITOR E O NOTEBOOK. O "monitor principal" do Windows pode ser o
   externo. O notebook e escolhido por config.MONITOR_NOTEBOOK, ou pelo tamanho
   fisico que o driver informa (o mais parecido com SCREEN_W), ou, sem essa
   informacao, pelo principal. Quem chama mostra o resultado na tela para o
   usuario conferir.

NAO usamos o pacote screeninfo: ele chama SetProcessDpiAwareness(2) sozinho a
cada get_monitors(), o que mudaria o modo de DPI no meio do programa.

Fora do Windows (testes automaticos, sem tela) listar_monitores() devolve
monitores falsos: um do tamanho do config, mais os da variavel de ambiente
AP2_MONITORES_FALSOS, no formato "LxA+X+Y;LxA+X+Y" (ex. "1920x1080+1920+0").
"""

import ctypes
import os
import sys
from dataclasses import dataclass

import numpy as np

import config

E_ACCESSDENIED = -2147024891            # 0x80070005 como HRESULT com sinal
MONITORINFOF_PRIMARY = 1
MDT_EFFECTIVE_DPI = 0
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
HORZSIZE, VERTSIZE = 4, 6                # GetDeviceCaps: tamanho fisico em mm

# A janela vai para (x + 50, y + 50) do monitor antes do fullscreen: assim a
# maior parte dela fica dentro dele, mesmo que o OpenCV restaure um tamanho
# antigo do registro.
_RECUO_JANELA = 50

_modo_dpi = None                         # cache: o modo so pode ser definido uma vez


@dataclass
class Monitor:
    """Um monitor no desktop virtual do Windows, em pixels FISICOS.

    x e y podem ser negativos (monitor a esquerda ou acima do principal).
    largura_mm/altura_mm vem do EDID pelo driver: so um palpite (EDID guarda
    centimetro inteiro, TV costuma mentir). A medida que vale e a de regua.
    """
    dispositivo: str          # ex. "\\\\.\\DISPLAY1"
    x: int
    y: int
    largura: int
    altura: int
    principal: bool = False
    dpi: int = None           # 96 = 100%, 120 = 125%, 144 = 150%
    largura_mm: int = 0
    altura_mm: int = 0

    @property
    def escala_pct(self):
        return None if not self.dpi else round(self.dpi * 100 / 96)

    def para_json(self):
        return {"dispositivo": self.dispositivo, "x": self.x, "y": self.y,
                "largura_px": self.largura, "altura_px": self.altura}

    def __str__(self):
        extra = []
        if self.principal:
            extra.append("principal")
        if self.escala_pct:
            extra.append(f"escala {self.escala_pct}%")
        if self.largura_mm:
            extra.append(f"{self.largura_mm}x{self.altura_mm} mm (driver)")
        return (f"{self.dispositivo}: {self.largura}x{self.altura} px em "
                f"({self.x}, {self.y})" + (f"  [{', '.join(extra)}]" if extra else ""))


# ----------------------------------------------------------------- DPI ---

def tornar_dpi_aware():
    """Avisa o Windows que o programa lida com escala de tela. Idempotente.

    Ordem de preferencia: Per-Monitor v2 (Windows 10 1703+), Per-Monitor v1
    (8.1+), System-aware. Devolve o nome do modo conseguido, que vale a pena
    mostrar ao usuario: "system-aware" ainda estica a imagem no monitor cuja
    escala difere da do principal.
    """
    global _modo_dpi
    if _modo_dpi is not None:
        return _modo_dpi
    if sys.platform != "win32":
        _modo_dpi = "nao-windows"
        return _modo_dpi
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    modo = "falhou"
    try:
        f = user32.SetProcessDpiAwarenessContext
        f.argtypes = [ctypes.c_void_p]
        f.restype = wintypes.BOOL
        if f(ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)):
            modo = "per-monitor-v2"
    except AttributeError:
        pass
    if modo == "falhou":
        # Se o modo ja tinha sido definido (manifesto, outra biblioteca), esta
        # chamada devolve E_ACCESSDENIED e ficamos sabendo.
        try:
            hr = ctypes.windll.shcore.SetProcessDpiAwareness(2)
            if hr == 0:
                modo = "per-monitor-v1"
            elif hr == E_ACCESSDENIED:
                modo = "ja-definido-antes"
        except (AttributeError, OSError):
            pass
    if modo == "falhou":
        try:
            if user32.SetProcessDPIAware():
                modo = "system-aware"
        except AttributeError:
            pass
    _modo_dpi = modo
    return modo


# ------------------------------------------------------------ monitores ---

def listar_monitores():
    """Lista os monitores, o principal primeiro. Chama tornar_dpi_aware() antes."""
    tornar_dpi_aware()
    if sys.platform != "win32":
        mons = _monitores_falsos()
    else:
        mons = _monitores_windows()
    mons.sort(key=lambda m: (not m.principal, m.x, m.y))
    return mons


def _monitores_falsos():
    mons = [Monitor("FALSO0", 0, 0, config.SCREEN_PX_W, config.SCREEN_PX_H, True,
                    96, int(round(config.SCREEN_W * 1000)),
                    int(round(config.SCREEN_H * 1000)))]
    extra = os.environ.get("AP2_MONITORES_FALSOS", "").strip()
    for i, item in enumerate(filter(None, extra.split(";")), start=1):
        tam, x, y = item.split("+")
        w, h = tam.lower().split("x")
        mons.append(Monitor(f"FALSO{i}", int(x), int(y), int(w), int(h), False, 96))
    return mons


def _monitores_windows():
    from ctypes import wintypes

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                    ("szDevice", wintypes.WCHAR * 32)]      # CCHDEVICENAME

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR,
                                         wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                         wintypes.LPARAM)
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                           MONITORENUMPROC, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    gdi32.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                ctypes.c_void_p]
    gdi32.CreateDCW.restype = wintypes.HDC
    gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.GetDeviceCaps.restype = ctypes.c_int
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    try:
        get_dpi = ctypes.windll.shcore.GetDpiForMonitor
        get_dpi.argtypes = [wintypes.HMONITOR, ctypes.c_int,
                            ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT)]
        get_dpi.restype = ctypes.c_long
    except (AttributeError, OSError):
        get_dpi = None

    mons = []

    def cb(hmon, _hdc, _rect, _lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            dpi = None
            if get_dpi is not None:
                dx, dy = wintypes.UINT(), wintypes.UINT()
                if get_dpi(hmon, MDT_EFFECTIVE_DPI, ctypes.byref(dx),
                           ctypes.byref(dy)) == 0:
                    dpi = int(dx.value)
            mm_w = mm_h = 0
            try:
                hdc = gdi32.CreateDCW("DISPLAY", info.szDevice, None, None)
                if hdc:
                    mm_w = gdi32.GetDeviceCaps(hdc, HORZSIZE)
                    mm_h = gdi32.GetDeviceCaps(hdc, VERTSIZE)
                    gdi32.DeleteDC(hdc)
            except OSError:
                pass
            mons.append(Monitor(info.szDevice, r.left, r.top, r.right - r.left,
                                r.bottom - r.top,
                                bool(info.dwFlags & MONITORINFOF_PRIMARY), dpi,
                                int(mm_w), int(mm_h)))
        return True                                   # continua a enumeracao

    proc = MONITORENUMPROC(cb)                        # referencia viva na chamada
    user32.EnumDisplayMonitors(None, None, proc, 0)
    return mons


def escolher_notebook(mons):
    """Indice, em mons, do monitor que e a tela do notebook.

    1. config.MONITOR_NOTEBOOK, se definido: indice (int) ou nome do
       dispositivo (ex. "\\\\.\\DISPLAY2").
    2. O monitor cujo tamanho fisico informado pelo driver mais se parece com
       SCREEN_W do config, se essa informacao existir e for plausivel.
    3. O monitor principal.
    """
    escolha = getattr(config, "MONITOR_NOTEBOOK", None)
    if isinstance(escolha, int) and 0 <= escolha < len(mons):
        return escolha
    if isinstance(escolha, str):
        for i, m in enumerate(mons):
            if m.dispositivo.lower() == escolha.lower():
                return i
        print(f"aviso: config.MONITOR_NOTEBOOK = {escolha!r} nao encontrado; "
              "escolhendo automaticamente")
    alvo_mm = config.SCREEN_W * 1000
    com_mm = [(abs(m.largura_mm - alvo_mm), i) for i, m in enumerate(mons)
              if m.largura_mm > 0]
    if len(com_mm) == len(mons) and len(mons) > 1:
        com_mm.sort()
        melhor, segundo = com_mm[0], com_mm[1]
        # So confia no palpite se ele separa bem os candidatos.
        if melhor[0] < 40 and segundo[0] - melhor[0] > 40:
            return melhor[1]
    for i, m in enumerate(mons):
        if m.principal:
            return i
    return 0


def achar_monitor(mons, info):
    """Monitor de `mons` descrito por `info` (campo "monitor" do telas.json).

    info pode ser {"dispositivo", "x", "y", ...} ou a forma antiga [x, y].
    Procura pelo nome do dispositivo; se nao achar (o Windows renumera as
    vezes), pela posicao no desktop virtual. Devolve None se nada bater.
    """
    if info is None:
        return None
    if isinstance(info, dict):
        nome = info.get("dispositivo")
        x, y = info.get("x"), info.get("y")
        w, h = info.get("largura_px"), info.get("altura_px")
    else:
        nome, (x, y), w, h = None, info, None, None
    if nome:
        for m in mons:
            if m.dispositivo.lower() == str(nome).lower() and (
                    w is None or (m.largura, m.altura) == (w, h)):
                return m
    if x is not None:
        for m in mons:
            if (m.x, m.y) == (x, y):
                return m
    if nome:
        for m in mons:
            if m.dispositivo.lower() == str(nome).lower():
                return m
    return None


# ------------------------------------------------------------- janelas ---

def focar_janela(nome):
    """Traz a janela para frente e entrega o foco de teclado a ela.

    Sem isso o foco continua no terminal que lancou o script e o cv2.waitKey
    nunca ve tecla nenhuma. O toque no ALT antes do SetForegroundWindow
    contorna a trava de foreground do Windows. O titulo precisa ser ASCII: o
    OpenCV cria a janela com CreateWindowExA.
    """
    if sys.platform != "win32":
        return
    try:
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, nome)
        if hwnd:
            u.keybd_event(0x12, 0, 0, 0)
            u.SetForegroundWindow(hwnd)
            u.keybd_event(0x12, 0, 2, 0)
    except Exception:
        pass


def abrir_tela_cheia(nome, monitor=None, sempre_no_topo=False):
    """Abre a janela `nome` em tela cheia no `monitor` e devolve (w, h) reais.

    O tamanho devolvido e o da area de imagem da janela, e e dele que o canvas
    tem de ser alocado: o OpenCV estica a imagem para a janela, entao canvas de
    outro tamanho seria reamostrado (e um padrao ChArUco deixaria de ser 1:1).

    sempre_no_topo: para a janela do monitor externo, que nao fica com o foco.
    Sem isso a barra de tarefas desse monitor pode ficar por cima dela.
    """
    import cv2
    tornar_dpi_aware()
    cv2.namedWindow(nome, cv2.WINDOW_NORMAL)
    if monitor is not None:
        cv2.moveWindow(nome, monitor.x + _RECUO_JANELA, monitor.y + _RECUO_JANELA)
        w0, h0 = monitor.largura, monitor.altura
    else:
        w0, h0 = config.SCREEN_PX_W, config.SCREEN_PX_H
    cv2.setWindowProperty(nome, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    if sempre_no_topo and hasattr(cv2, "WND_PROP_TOPMOST"):
        try:
            cv2.setWindowProperty(nome, cv2.WND_PROP_TOPMOST, 1)
        except cv2.error:
            pass
    cv2.imshow(nome, np.zeros((h0, w0, 3), np.uint8))
    cv2.waitKey(1)
    focar_janela(nome)
    try:
        _x, _y, w, h = cv2.getWindowImageRect(nome)
    except cv2.error:
        w = h = 0
    if w <= 0 or h <= 0:
        w, h = w0, h0
    return int(w), int(h)


def conferir_tamanho(nome, w, h, monitor):
    """Aviso legivel quando a janela nao tem o tamanho do monitor.

    Acontece quando a escala de tela nao foi tratada (janela menor que o
    monitor, imagem esticada) ou o fullscreen nao pegou. A geometria continua
    certa, porque tudo e mapeado por fracao da janela, mas a imagem fica
    borrada e o padrao ChArUco deixa de ser 1:1.
    """
    if monitor is None or (w, h) == (monitor.largura, monitor.altura):
        return None
    return (f"aviso: janela {nome!r} tem {w}x{h} px, mas o monitor "
            f"{monitor.dispositivo} tem {monitor.largura}x{monitor.altura}. "
            f"Modo de DPI: {tornar_dpi_aware()}. Se a imagem parecer borrada, "
            "ponha a escala do Windows em 100% nesse monitor.")


if __name__ == "__main__":
    print("modo DPI:", tornar_dpi_aware())
    lista = listar_monitores()
    i_nb = escolher_notebook(lista)
    for i, m in enumerate(lista):
        print(("* " if i == i_nb else "  ") + str(m))
    print("* = escolhido como notebook")
