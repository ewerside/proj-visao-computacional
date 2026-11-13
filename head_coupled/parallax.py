"""Parallax: o menu do projeto. Tudo comeca aqui, sem linha de comando.

    python parallax.py          (ou dois cliques em Parallax.bat, na raiz)

Telas do menu:
  Inicio          escolhe entre uma tela, duas telas, calibrar e configuracoes
  Uma tela        cenas do notebook; chave do anaglifo (so com uma tela)
  Duas telas      cenas do mundo compartilhado; exige a calibracao feita
  Calibrar        padroes nas telas + pagina do celular (QR code), com status
  Configuracoes   medidas da tela e do monitor, conexao do celular, webcam

O menu e desenhado com o Pillow (texto com fonte de verdade) numa janela do
OpenCV em tela cheia, no monitor do notebook, e controlado pelo mouse. Uma cena
roda no laco do main.py, chamado daqui com --app; ESC na cena devolve o
controle ao menu. A calibracao roda o calibrar_telas.py (comando celular).

Teclas no menu: ESC ou q volta uma tela (no Inicio, sai).
"""

import argparse
import json
import os
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config
import monitores
import sala
import scene as scn
import telas as tls

JANELA = "Parallax"
AQUI = os.path.dirname(os.path.abspath(__file__))

NOME = "Parallax"
LEMA = "A tela vira uma janela 3D que acompanha o seu olhar."
CREDITOS = ("Projeto da disciplina Visão Computacional (IBM3131) · Ibmec · "
            "Prof. Rigel Fernandes · Ewerton Arrais, Miguel Veiga e Emilly Fernandes")

# Cores em RGB (o Pillow desenha em RGB; a conversao para BGR e no fim).
FUNDO_A, FUNDO_B = (10, 13, 20), (18, 22, 34)
CARTAO, CARTAO_SOBRE = (24, 29, 40), (34, 42, 60)
BORDA, BORDA_SOBRE = (44, 52, 68), (91, 140, 255)
TEXTO, FRACO = (232, 238, 245), (140, 150, 165)
ACAO, ACAO2 = (91, 140, 255), (124, 92, 255)
OK, AVISO, RUIM = (63, 185, 80), (210, 153, 34), (255, 123, 114)

CENAS_UMA = ["caixa", "corredor", "miniatura", "asteroides"]
CENAS_DUAS = ["janelas", "planeta"]
OLHO_MINIATURA = np.array([0.07, 0.035, 0.55])


def _fonte(tamanho, peso="normal"):
    nomes = {"normal": ["segoeui.ttf", "arial.ttf"], "forte": ["seguisb.ttf", "segoeuib.ttf",
             "arialbd.ttf"], "negrito": ["segoeuib.ttf", "arialbd.ttf"]}[peso]
    for n in nomes:
        try:
            return ImageFont.truetype(os.path.join(r"C:\Windows\Fonts", n), tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


class Botao:
    def __init__(self, caixa, acao, ativo=True):
        self.caixa, self.acao, self.ativo = caixa, acao, ativo

    def dentro(self, x, y):
        x0, y0, x1, y1 = self.caixa
        return x0 <= x <= x1 and y0 <= y <= y1


class App:
    def __init__(self):
        self.modo_dpi = monitores.tornar_dpi_aware()
        self.tela = "inicio"
        self.botoes = []
        self.mouse = (-1, -1)
        self.clique = None
        self.sujo = True
        self.anaglifo = False
        self.aviso = None                 # (texto, cor) mostrado no rodape da tela
        self.resultado = None             # da ultima calibracao feita nesta sessao
        self.miniaturas = {}
        self.ajustes = {n: getattr(config, n) for n in config.AJUSTAVEIS}
        self.sair = False
        self._abrir_janela()

    # ------------------------------------------------------------- janela

    def _abrir_janela(self):
        mons = monitores.listar_monitores()
        alvo = mons[monitores.escolher_notebook(mons)] if len(mons) > 1 else None
        self.w, self.h = monitores.abrir_tela_cheia(JANELA, alvo, False)
        self.s = self.h / 1080.0
        cv2.setMouseCallback(JANELA, self._ao_mouse)
        monitores.focar_janela(JANELA)
        self.sujo = True

    def _ao_mouse(self, evento, x, y, _flags, _param):
        if evento == cv2.EVENT_MOUSEMOVE:
            antes = self._sobre(self.mouse)
            self.mouse = (x, y)
            if self._sobre(self.mouse) is not antes:
                self.sujo = True
        elif evento == cv2.EVENT_LBUTTONUP:
            self.clique = (x, y)

    def _sobre(self, pos):
        for b in self.botoes:
            if b.ativo and b.dentro(*pos):
                return b
        return None

    def px(self, v):
        return int(round(v * self.s))

    # ------------------------------------------------------------ desenho

    def _base(self):
        """Fundo em degrade vertical, com a marca no canto."""
        g = np.linspace(0, 1, self.h)[:, None, None]
        arr = (np.array(FUNDO_A) * (1 - g) + np.array(FUNDO_B) * g).astype(np.uint8)
        img = Image.fromarray(np.repeat(arr, self.w, axis=1))
        return img, ImageDraw.Draw(img)

    def _titulo_degrade(self, img, texto, xy, fonte):
        """Texto preenchido com o degrade da marca."""
        x, y = xy
        caixa = fonte.getbbox(texto)
        w, h = caixa[2] + 4, caixa[3] + 8
        mascara = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mascara).text((0, 0), texto, font=fonte, fill=255)
        t = np.linspace(0, 1, w)[None, :, None]
        cor = (np.array(ACAO) * (1 - t) + np.array(ACAO2) * t).astype(np.uint8)
        img.paste(Image.fromarray(np.repeat(cor, h, axis=0)), (x, y), mascara)
        return w

    def _cabecalho(self, img, d, titulo, sub=None):
        m = self.px(90)
        self._titulo_degrade(img, NOME, (m, self.px(54)), _fonte(self.px(34), "negrito"))
        d.text((m, self.px(128)), titulo, font=_fonte(self.px(54), "forte"), fill=TEXTO)
        if sub:
            d.text((m, self.px(200)), sub, font=_fonte(self.px(24)), fill=FRACO)
        self._botao_texto(d, (self.w - m - self.px(190), self.px(60), self.w - m, self.px(116)),
                          "Voltar  (Esc)", lambda: self.ir("inicio"))

    def _cartao(self, d, caixa, acao, ativo=True, destaque=False):
        b = Botao(caixa, acao, ativo)
        self.botoes.append(b)
        sobre = ativo and b.dentro(*self.mouse)
        d.rounded_rectangle(caixa, radius=self.px(22),
                            fill=CARTAO_SOBRE if sobre else CARTAO,
                            outline=BORDA_SOBRE if (sobre or destaque) else BORDA,
                            width=self.px(3) if (sobre or destaque) else self.px(2))
        return sobre

    def _botao_texto(self, d, caixa, texto, acao, ativo=True, cheio=False):
        b = Botao(caixa, acao, ativo)
        self.botoes.append(b)
        sobre = ativo and b.dentro(*self.mouse)
        fonte = _fonte(self.px(24), "forte")
        if cheio:
            d.rounded_rectangle(caixa, radius=self.px(16), fill=ACAO2 if sobre else ACAO)
            cor = (255, 255, 255)
        else:
            d.rounded_rectangle(caixa, radius=self.px(16), fill=CARTAO_SOBRE if sobre else None,
                                outline=BORDA_SOBRE if sobre else BORDA, width=self.px(2))
            cor = TEXTO if ativo else FRACO
        x0, y0, x1, y1 = caixa
        tw = d.textlength(texto, font=fonte)
        d.text(((x0 + x1 - tw) / 2, (y0 + y1) / 2 - self.px(17)), texto, font=fonte, fill=cor)

    def _quebrar(self, d, texto, fonte, largura):
        linhas, atual = [], ""
        for palavra in texto.split():
            tentativa = (atual + " " + palavra).strip()
            if d.textlength(tentativa, font=fonte) <= largura:
                atual = tentativa
            else:
                linhas.append(atual)
                atual = palavra
        return linhas + [atual] if atual else linhas

    def _rodape(self, d):
        fonte = _fonte(self.px(17))
        tw = d.textlength(CREDITOS, font=fonte)
        d.text(((self.w - tw) / 2, self.h - self.px(46)), CREDITOS, font=fonte, fill=(96, 104, 118))
        if self.aviso:
            texto, cor = self.aviso
            f2 = _fonte(self.px(24), "forte")
            tw = d.textlength(texto, font=f2)
            d.text(((self.w - tw) / 2, self.h - self.px(104)), texto, font=f2, fill=cor)

    def _mostrar(self, img):
        cv2.imshow(JANELA, cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR))

    def espera(self, texto):
        """Tela de espera, mostrada antes de algo que demora (abrir a webcam)."""
        img, d = self._base()
        fonte = _fonte(self.px(40), "forte")
        tw = d.textlength(texto, font=fonte)
        d.text(((self.w - tw) / 2, self.h / 2 - self.px(30)), texto, font=fonte, fill=TEXTO)
        self._mostrar(img)
        cv2.waitKey(1)

    # ---------------------------------------------------------- miniaturas

    def _miniatura(self, nome, lista=None):
        """Previa da cena, desenhada uma vez pelo mesmo codigo que roda a cena."""
        chave = (nome, lista is not None)
        if chave in self.miniaturas:
            return self.miniaturas[chave]
        t = 4.0
        try:
            if lista is None:
                out = np.zeros((270, 480, 3), np.uint8)
                cena = scn.build(nome) + scn.dinamico(nome, t)
                scn.render(OLHO_MINIATURA, scn.order_faces(cena, OLHO_MINIATURA), out)
            else:
                import janelas
                olho = janelas.OLHO_TIPICO
                cena = sala.build(nome, lista) + sala.dinamico(nome, t, lista)
                ordem = tls.ordenar_mundo(cena, olho)
                partes = []
                for i in sorted(range(len(lista)), key=lambda k: lista[k].t[0]):
                    o = np.zeros((270, 480, 3), np.uint8)
                    tls.render_tela(olho, ordem, lista[i], o)
                    partes.append(o)
                    partes.append(np.zeros((270, 6, 3), np.uint8))
                out = np.hstack(partes[:-1])
        except Exception as e:                       # a previa nunca derruba o menu
            print("miniatura", nome, "falhou:", e)
            out = np.zeros((270, 480, 3), np.uint8)
        img = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
        self.miniaturas[chave] = img
        return img

    def _colar_miniatura(self, img, mini, caixa):
        x0, y0, x1, y1 = caixa
        m = mini.resize((x1 - x0, y1 - y0), Image.LANCZOS)
        mascara = Image.new("L", m.size, 0)
        ImageDraw.Draw(mascara).rounded_rectangle((0, 0, m.size[0], m.size[1]),
                                                  radius=self.px(14), fill=255)
        img.paste(m, (x0, y0), mascara)

    # --------------------------------------------------------------- telas

    def estado_duas_telas(self):
        """(lista de telas ou None, motivo de nao poder usar duas telas ou None)."""
        if not os.path.exists(config.TELAS_FILE):
            return None, "Calibre as telas primeiro"
        try:
            lista = tls.carregar(config.TELAS_FILE)
        except (ValueError, KeyError, OSError):
            return None, "Calibração inválida: refaça"
        if lista is None or len(lista) < 2:
            return None, "Calibre as telas primeiro"
        mons = monitores.listar_monitores()
        if len(mons) < 2 or any(monitores.achar_monitor(mons, tl.monitor) is None
                                for tl in lista):
            return None, "Ligue o monitor externo (Win+P, Estender)"
        return lista, None

    def desenhar(self):
        self.botoes = []
        img, d = self._base()
        getattr(self, "tela_" + self.tela)(img, d)
        self._rodape(d)
        self._mostrar(img)
        self.sujo = False

    def tela_inicio(self, img, d):
        cx = self.w // 2
        f_t = _fonte(self.px(150), "negrito")
        tw = f_t.getbbox(NOME)[2]
        self._titulo_degrade(img, NOME, (cx - tw // 2, self.px(120)), f_t)
        f_l = _fonte(self.px(30))
        d.text((cx - d.textlength(LEMA, font=f_l) / 2, self.px(318)), LEMA, font=f_l, fill=FRACO)

        _lista, motivo = self.estado_duas_telas()
        itens = [
            ("Uma tela", "Cenas no notebook, com opção de 3D anáglifo.", lambda: self.ir("uma"), True, None),
            ("Duas telas", "O notebook e o monitor como janelas para o mesmo mundo.",
             lambda: self.ir("duas"), motivo is None, motivo),
            ("Calibrar telas", "Descobre onde o monitor está, com fotos do celular.",
             lambda: self.ir("calibrar"), True, None),
            ("Configurações", "Medidas da tela, do monitor e da webcam.",
             lambda: self.ir("config"), True, None),
        ]
        lw, lh, vao = self.px(400), self.px(300), self.px(34)
        x0 = cx - (4 * lw + 3 * vao) // 2
        y0 = self.px(440)
        f_n, f_d = _fonte(self.px(36), "forte"), _fonte(self.px(22))
        for i, (nome, desc, acao, ativo, trava) in enumerate(itens):
            caixa = (x0 + i * (lw + vao), y0, x0 + i * (lw + vao) + lw, y0 + lh)
            self._cartao(d, caixa, acao, ativo)
            cor = TEXTO if ativo else FRACO
            d.text((caixa[0] + self.px(30), caixa[1] + self.px(34)), nome, font=f_n, fill=cor)
            for k, linha in enumerate(self._quebrar(d, desc, f_d, lw - self.px(60))):
                d.text((caixa[0] + self.px(30), caixa[1] + self.px(104) + k * self.px(32)),
                       linha, font=f_d, fill=FRACO)
            if trava:
                d.text((caixa[0] + self.px(30), caixa[3] - self.px(60)), trava,
                       font=_fonte(self.px(20), "forte"), fill=AVISO)
            elif i == 1:
                d.text((caixa[0] + self.px(30), caixa[3] - self.px(60)), "Calibração pronta",
                       font=_fonte(self.px(20), "forte"), fill=OK)
        self._botao_texto(d, (cx - self.px(110), self.px(810), cx + self.px(110), self.px(870)),
                          "Sair", self.encerrar)

    def tela_uma(self, img, d):
        self._cabecalho(img, d, "Uma tela", "Escolha uma cena. Dentro dela, Esc volta para cá.")
        self._grade_cenas(img, d, CENAS_UMA, scn.ROTULOS, None, self.px(290))
        # Chave do anaglifo.
        x, y = self.px(90), self.px(840)
        caixa = (x, y, x + self.px(760), y + self.px(96))
        self._cartao(d, caixa, self.alternar_anaglifo, destaque=self.anaglifo)
        kx, ky = x + self.px(28), y + self.px(30)
        d.rounded_rectangle((kx, ky, kx + self.px(74), ky + self.px(38)), radius=self.px(19),
                            fill=ACAO if self.anaglifo else (60, 68, 84))
        bx = kx + (self.px(40) if self.anaglifo else self.px(4))
        d.ellipse((bx, ky + self.px(4), bx + self.px(30), ky + self.px(34)), fill=(255, 255, 255))
        d.text((kx + self.px(100), y + self.px(14)), "3D anáglifo  " + ("ligado" if self.anaglifo else "desligado"),
               font=_fonte(self.px(28), "forte"), fill=TEXTO)
        d.text((kx + self.px(100), y + self.px(54)),
               "Óculos vermelho-ciano. Começa suave; as teclas [ e ] ajustam a profundidade.",
               font=_fonte(self.px(18)), fill=FRACO)

    def tela_duas(self, img, d):
        lista, motivo = self.estado_duas_telas()
        if motivo:
            self.aviso = (motivo, AVISO)
            self.tela = "inicio"
            return self.tela_inicio(img, d)
        self._cabecalho(img, d, "Duas telas", "O mesmo mundo visto pelo notebook e pelo monitor.")
        self._grade_cenas(img, d, CENAS_DUAS, sala.ROTULOS, lista, self.px(300))
        self._botao_texto(d, (self.px(90), self.px(850), self.px(530), self.px(916)),
                          "Conferir o alinhamento", lambda: self.rodar("alinhamento", True))

    def _grade_cenas(self, img, d, nomes, rotulos, lista, y0):
        m, vao = self.px(90), self.px(30)
        n = len(nomes)
        lw = (self.w - 2 * m - (n - 1) * vao) // n
        proporcao = (960 + 6) / 270 if lista is not None else 16 / 9
        ih = int((lw - self.px(28)) / proporcao)
        lh = ih + self.px(150)
        f_n, f_d = _fonte(self.px(32), "forte"), _fonte(self.px(20))
        for i, nome in enumerate(nomes):
            x = m + i * (lw + vao)
            caixa = (x, y0, x + lw, y0 + lh)
            self._cartao(d, caixa, lambda nome=nome: self.rodar(nome, lista is not None))
            self._colar_miniatura(img, self._miniatura(nome, lista),
                                  (x + self.px(14), y0 + self.px(14), x + lw - self.px(14),
                                   y0 + self.px(14) + ih))
            titulo, desc = rotulos[nome]
            d.text((x + self.px(24), y0 + ih + self.px(28)), titulo, font=f_n, fill=TEXTO)
            for k, linha in enumerate(self._quebrar(d, desc, f_d, lw - self.px(48))[:2]):
                d.text((x + self.px(24), y0 + ih + self.px(76) + k * self.px(28)), linha,
                       font=f_d, fill=FRACO)

    def tela_calibrar(self, img, d):
        self._cabecalho(img, d, "Calibrar telas",
                        "O programa descobre a posição do monitor com fotos tiradas pelo celular.")
        passos = [
            "Ligue o monitor externo e escolha Estender (Win+P).",
            "Toque em Começar: as duas telas mostram padrões e o notebook mostra um QR code.",
            "Leia o QR code com a câmera do celular e siga a página que abrir.",
            "Tire 12 fotos das duas telas, de lugares diferentes. A página confere cada uma.",
            "Toque em Calcular no celular. O menu volta sozinho, com o resultado.",
        ]
        f = _fonte(self.px(26))
        for i, texto in enumerate(passos):
            y = self.px(300) + i * self.px(64)
            d.ellipse((self.px(90), y, self.px(134), y + self.px(44)), outline=ACAO, width=self.px(2))
            num = str(i + 1)
            d.text((self.px(112) - d.textlength(num, font=f) / 2, y + self.px(4)), num, font=f, fill=ACAO)
            d.text((self.px(156), y + self.px(4)), texto, font=f, fill=TEXTO)
        tunel = self.ajustes["CELULAR_TUNEL"]
        d.text((self.px(90), self.px(640)),
               "Conexão do celular: " + ("pela internet (funciona em qualquer rede)" if tunel
                                         else "direta (celular e notebook na mesma rede)")
               + ". Mude em Configurações.", font=_fonte(self.px(20)), fill=FRACO)
        tem = os.path.exists(config.TELAS_FILE)
        d.text((self.px(90), self.px(676)),
               "Situação: " + ("já existe uma calibração; refazer substitui a atual."
                               if tem else "ainda não há calibração."),
               font=_fonte(self.px(20)), fill=OK if tem else AVISO)
        self._botao_texto(d, (self.px(90), self.px(740), self.px(430), self.px(816)),
                          "Começar", self.calibrar, cheio=True)
        if tem:
            self._botao_texto(d, (self.px(460), self.px(740), self.px(900), self.px(816)),
                              "Conferir o alinhamento", lambda: self.rodar("alinhamento", True))

    def tela_resultado(self, img, d):
        self._cabecalho(img, d, "Calibração pronta", "Posição do monitor em relação ao notebook.")
        r = self.resultado
        g, q = r["resumo"], r["qualidade"]
        linhas = [("Monitor à", f"{g['lado']} do notebook"),
                  ("Ângulo entre as telas", f"{g['angulo_entre_telas_graus']}°"),
                  ("Folga entre as bordas", f"{g['folga_bordas_internas_cm']} cm"),
                  ("Tamanho do monitor", f"{g['monitor_diagonal_pol']} pol"),
                  ("Erro de reprojeção", f"{q['rms_reproj_px']} px"),
                  ("Fotos usadas", str(r["n_fotos"]))]
        f, fb = _fonte(self.px(26)), _fonte(self.px(26), "forte")
        for i, (a, b) in enumerate(linhas):
            y = self.px(300) + i * self.px(56)
            d.text((self.px(90), y), a, font=f, fill=FRACO)
            d.text((self.px(470), y), b, font=fb, fill=TEXTO)
        for i, a in enumerate(r["avisos"][:3]):
            for k, linha in enumerate(self._quebrar(d, "Aviso: " + a, _fonte(self.px(20)), self.px(760))[:2]):
                d.text((self.px(90), self.px(650) + (2 * i + k) * self.px(28)), linha,
                       font=_fonte(self.px(20)), fill=AVISO)
        planta = os.path.join(AQUI, "dbg", "planta.png")
        if os.path.exists(planta):
            p = Image.open(planta).convert("RGB")
            lado = self.px(620)
            self._colar_miniatura(img, p, (self.w - self.px(90) - lado, self.px(280),
                                            self.w - self.px(90), self.px(280) + lado))
        self._botao_texto(d, (self.px(90), self.px(850), self.px(470), self.px(920)),
                          "Ver nas duas telas", lambda: self.ir("duas"), cheio=True)
        self._botao_texto(d, (self.px(500), self.px(850), self.px(940), self.px(920)),
                          "Conferir o alinhamento", lambda: self.rodar("alinhamento", True))

    def tela_config(self, img, d):
        self._cabecalho(img, d, "Configurações",
                        "O padrão é o notebook do projeto (tela de 15,6 pol). Mude só se o seu for outro.")
        a = self.ajustes
        linhas = [
            ("Largura da tela do notebook", f"{a['SCREEN_W'] * 1000:.1f} mm", "SCREEN_W", 0.0005),
            ("Altura da tela do notebook", f"{a['SCREEN_H'] * 1000:.1f} mm", "SCREEN_H", 0.0005),
            ("Diagonal do monitor externo", f"{a['MONITOR_DIAGONAL_POL']:.1f} pol", "MONITOR_DIAGONAL_POL", 0.5),
        ]
        f, fb = _fonte(self.px(26)), _fonte(self.px(28), "forte")
        for i, (rotulo, valor, chave, passo) in enumerate(linhas):
            y = self.px(300) + i * self.px(84)
            d.text((self.px(90), y + self.px(14)), rotulo, font=f, fill=TEXTO)
            self._botao_texto(d, (self.px(640), y, self.px(710), y + self.px(64)), "−",
                              lambda c=chave, p=passo: self.ajustar(c, -p))
            d.text((self.px(740), y + self.px(12)), valor, font=fb, fill=TEXTO)
            self._botao_texto(d, (self.px(930), y, self.px(1000), y + self.px(64)), "+",
                              lambda c=chave, p=passo: self.ajustar(c, +p))
        y = self.px(300) + 3 * self.px(84)
        d.text((self.px(90), y + self.px(14)), "Conexão do celular na calibração", font=f, fill=TEXTO)
        tunel = a["CELULAR_TUNEL"]
        self._botao_texto(d, (self.px(640), y, self.px(1000), y + self.px(64)),
                          "Pela internet" if tunel else "Mesma rede",
                          lambda: self.ajustar("CELULAR_TUNEL", None))
        d.text((self.px(1030), y + self.px(18)),
               "As fotos passam por um serviço de túnel." if tunel
               else "Celular e notebook na mesma rede Wi-Fi.", font=_fonte(self.px(20)), fill=FRACO)

        mudou = any(a[n] != getattr(config, n) for n in config.AJUSTAVEIS)
        y = self.px(680)
        self._botao_texto(d, (self.px(90), y, self.px(470), y + self.px(70)),
                          "Salvar e reiniciar", self.salvar_ajustes, ativo=mudou, cheio=mudou)
        self._botao_texto(d, (self.px(500), y, self.px(880), y + self.px(70)),
                          "Restaurar o padrão", self.restaurar_ajustes)
        self._botao_texto(d, (self.px(910), y, self.px(1290), y + self.px(70)),
                          "Calibrar a webcam", self.calibrar_webcam)
        d.text((self.px(90), y + self.px(96)),
               "Medidas da área acesa da tela, sem a moldura. Mudou a tela ou o monitor? Calibre as telas de novo.",
               font=_fonte(self.px(20)), fill=FRACO)
        d.text((self.px(90), y + self.px(128)),
               "Calibrar a webcam: sente-se a 60 cm da câmera, olhe reto e aperte Espaço.",
               font=_fonte(self.px(20)), fill=FRACO)

    # --------------------------------------------------------------- acoes

    def ir(self, tela):
        self.tela, self.aviso, self.sujo = tela, None, True

    def encerrar(self):
        self.sair = True

    def alternar_anaglifo(self):
        self.anaglifo = not self.anaglifo
        self.sujo = True

    def ajustar(self, chave, delta):
        if delta is None:
            self.ajustes[chave] = not self.ajustes[chave]
        else:
            self.ajustes[chave] = round(max(0.05, self.ajustes[chave] + delta), 4)
        self.sujo = True

    def salvar_ajustes(self):
        dados = {n: v for n, v in self.ajustes.items() if v != config.PADROES[n]}
        if dados:
            with open(config.AJUSTES_FILE, "w", encoding="utf-8") as fh:
                json.dump(dados, fh, indent=2)
        elif os.path.exists(config.AJUSTES_FILE):
            os.remove(config.AJUSTES_FILE)
        # As medidas entram nos modulos na importacao: o jeito limpo de valerem
        # em tudo e abrir o programa de novo.
        self.espera("Reiniciando com os novos ajustes…")
        cv2.destroyAllWindows()
        subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=AQUI)
        self.sair = True

    def restaurar_ajustes(self):
        self.ajustes = dict(config.PADROES)
        self.sujo = True

    def _depois_de_sair(self):
        """Outro laco (cena, calibracao) fechou as janelas: reabre o menu."""
        cv2.destroyAllWindows()
        self._abrir_janela()
        self.clique = None

    def rodar(self, cena, multi):
        import main
        argv = ["--app", "--cena", cena]
        if multi:
            _lista, motivo = self.estado_duas_telas()
            if motivo:
                self.aviso, self.sujo = (motivo, AVISO), True
                return
            argv += ["--cenas", ",".join(CENAS_DUAS + ["alinhamento"])]
        else:
            argv += ["--uma-tela", "--cenas", ",".join(CENAS_UMA)]
            if self.anaglifo:
                argv.append("--anaglifo")
        self.espera("Abrindo a cena…")
        self.aviso = None
        try:
            main.main(argv)
        except SystemExit as e:
            self.aviso = (str(e).split(". ")[0][:110] if e.code else "", RUIM)
        except Exception as e:                       # webcam ocupada, etc.
            self.aviso = (f"Não consegui abrir a cena: {e}"[:110], RUIM)
        self._depois_de_sair()

    def calibrar(self):
        import calibrar_telas
        if len(monitores.listar_monitores()) < 2:
            self.aviso, self.sujo = ("Ligue o monitor externo e escolha Estender (Win+P).", AVISO), True
            return
        self.espera("Preparando a calibração…" + ("  abrindo o túnel" if self.ajustes["CELULAR_TUNEL"] else ""))
        args = argparse.Namespace(diagonal=config.MONITOR_DIAGONAL_POL, monitor=None, saida=None,
                                  telas=None, porta=8765, tunel=bool(config.CELULAR_TUNEL),
                                  tunel_servico=None)
        retorno = {}
        try:
            calibrar_telas.cmd_celular(args, retorno)
        except Exception as e:
            retorno["erro"] = f"A calibração falhou: {e}"
        self._depois_de_sair()
        self.miniaturas = {k: v for k, v in self.miniaturas.items() if not k[1]}
        if retorno.get("resultado"):
            self.resultado = retorno["resultado"]
            self.ir("resultado")
        else:
            self.ir("calibrar")
            self.aviso = ((retorno.get("erro") or "Calibração cancelada antes do cálculo.")[:120],
                          RUIM if retorno.get("erro") else AVISO)

    def calibrar_webcam(self):
        import calibrate
        self.espera("Abrindo a webcam…")
        antigo = sys.argv
        sys.argv = [antigo[0]]
        try:
            calibrate.main()
            self.aviso = ("Calibração da webcam encerrada.", OK)
        except Exception as e:
            self.aviso = (f"Não consegui calibrar a webcam: {e}"[:110], RUIM)
        finally:
            sys.argv = antigo
        self._depois_de_sair()

    # ---------------------------------------------------------------- laco

    def executar(self):
        while not self.sair:
            if self.sujo:
                self.desenhar()
            tecla = cv2.waitKey(30) & 0xFF
            if tecla in (27, ord("q")):
                if self.tela == "inicio":
                    break
                self.ir("inicio")
            if self.clique is not None:
                alvo = self._sobre(self.clique)
                self.clique = None
                if alvo is not None:
                    alvo.acao()
                    self.sujo = True
            try:
                if cv2.getWindowProperty(JANELA, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
        cv2.destroyAllWindows()


def main():
    App().executar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
