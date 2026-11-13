"""Pagina para o celular mandar as fotos da calibracao direto para o notebook.

O notebook sobe um servidor HTTP na rede local e mostra um QR code. O celular
le o QR, abre a pagina no navegador e, a cada toque em "Tirar foto", a camera
NATIVA do celular abre (foto em resolucao total, sem app para instalar). A foto
sobe, o notebook procura os tabuleiros nela e responde na hora quantos cantos
achou em cada tela. Com fotos suficientes, o botao "Calcular" roda a calibracao
e grava o telas.json.

Quem usa isto e o comando  python calibrar_telas.py celular.

Por que camera nativa e nao video na pagina: o navegador so libera a camera
dentro da pagina (getUserMedia) em HTTPS, e os quadros de video tem bem menos
resolucao que a foto. O <input type="file" capture> funciona em HTTP simples.

Seguranca: o servidor so existe enquanto o comando roda, so aceita pedidos com
o codigo aleatorio que vai no QR code, so grava JPEG/PNG com nome gerado por
ele, dentro da pasta da sessao, e limita o tamanho de cada envio.

O celular e o notebook precisam estar na MESMA rede. Se o Wi-Fi isolar os
aparelhos (comum em rede de faculdade), ligue o roteador do celular e conecte o
notebook nele. Na primeira vez o Windows pergunta se o Python pode receber
conexoes: permita.
"""

import json
import os
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

import calibracao
import detectar

PORTA = 8765
MAX_BYTES = 40 * 1024 * 1024
MIN_CALCULAR = 5            # fotos com as duas telas para liberar o Calcular
IDEAL = 12

# De onde tirar cada foto: variar o ponto de vista importa mais que o numero.
SUGESTOES = [
    "de frente, no meio das duas telas",
    "bem da esquerda",
    "bem da direita",
    "do meio, com o celular mais alto",
    "do meio, com o celular mais baixo",
    "da esquerda, mais alto",
    "da direita, mais alto",
    "de frente, mais perto (60 cm)",
    "de frente, mais longe (1,2 m)",
    "da esquerda, mais baixo",
    "da direita, mais baixo",
    "de frente, com o celular um pouco girado",
]


def ip_local():
    """IP deste computador na rede local (nao envia nenhum pacote)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def imagem_qr(texto, lado_px=420):
    """QR code em BGR, com margem branca, pronto para colar numa imagem."""
    qr = cv2.QRCodeEncoder.create().encode(texto)
    qr = cv2.copyMakeBorder(qr, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=255)
    qr = cv2.resize(qr, (lado_px, lado_px), interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(qr, cv2.COLOR_GRAY2BGR)


class Servidor:
    """Servidor da sessao de fotos. calcular_fn(pasta) -> dicionario do calcular."""

    def __init__(self, pasta_base, calcular_fn, porta=PORTA, host="0.0.0.0"):
        self.calcular_fn = calcular_fn
        self.token = secrets.token_urlsafe(6)
        self.trava = threading.Lock()
        self.det = None
        self.pasta_base = pasta_base
        self.conectado = False          # o celular ja abriu a pagina
        self.terminou = False           # calculou com sucesso
        self.resultado = None
        self._nova_sessao()
        servidor = self

        class Pedido(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, d, cod=200):
                corpo = json.dumps(d, ensure_ascii=False).encode("utf-8")
                self.send_response(cod)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(corpo)

            def _rota(self):
                partes = self.path.split("?")[0].strip("/").split("/")
                if not partes or partes[0] != servidor.token:
                    self.send_error(404)
                    return None
                return partes[1] if len(partes) > 1 else ""

            def do_GET(self):
                rota = self._rota()
                if rota is None:
                    return
                if rota == "":
                    servidor.conectado = True
                    corpo = PAGINA.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(corpo)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(corpo)
                elif rota == "estado":
                    self._json(servidor.estado())
                else:
                    self.send_error(404)

            def do_POST(self):
                rota = self._rota()
                if rota is None:
                    return
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BYTES:
                    self._json({"erro": "foto grande demais"}, 413)
                    return
                dados = self.rfile.read(n) if n else b""
                try:
                    if rota == "foto":
                        self._json(servidor.receber_foto(dados))
                    elif rota == "calcular":
                        self._json(servidor.calcular())
                    elif rota == "recomecar":
                        servidor._nova_sessao()
                        self._json(servidor.estado())
                    else:
                        self.send_error(404)
                except Exception as e:                  # nao derruba o servidor
                    self._json({"erro": f"erro no notebook: {e}"}, 500)

        self.http = ThreadingHTTPServer((host, porta), Pedido)
        self.porta = self.http.server_address[1]
        self.url = f"http://{ip_local()}:{self.porta}/{self.token}/"
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)

    # ------------------------------------------------------------- sessao

    def _nova_sessao(self):
        with self.trava:
            self.pasta = os.path.join(self.pasta_base, time.strftime("%Y%m%d_%H%M%S"))
            self.fotos = []             # {"nome", "notebook", "monitor", "boa"}
            self.resultado = None

    def definir_padroes(self, pads):
        """Padroes que estao na tela agora (muda se o usuario trocar as telas)."""
        with self.trava:
            self.det = detectar.Detector(pads)

    def iniciar(self):
        self.thread.start()
        return self

    def parar(self):
        self.http.shutdown()
        self.http.server_close()

    def estado(self):
        boas = sum(f["boa"] for f in self.fotos)
        return {"fotos": self.fotos, "boas": boas, "minimo": MIN_CALCULAR, "ideal": IDEAL,
                "sugestao": SUGESTOES[boas % len(SUGESTOES)], "resultado": self.resultado}

    # -------------------------------------------------------------- acoes

    def receber_foto(self, dados):
        if dados[:2] != b"\xff\xd8" and dados[:8] != b"\x89PNG\r\n\x1a\n":
            return {"erro": "o arquivo nao e JPEG nem PNG. No celular, escolha JPEG "
                            "(Samsung: desligue 'fotos de alta eficiencia')."}
        ext = ".jpg" if dados[:2] == b"\xff\xd8" else ".png"
        img = cv2.imdecode(np.frombuffer(dados, np.uint8),
                           cv2.IMREAD_GRAYSCALE | cv2.IMREAD_IGNORE_ORIENTATION)
        if img is None:
            return {"erro": "nao consegui ler a foto"}
        with self.trava:
            if self.det is None:
                return {"erro": "os padroes ainda nao estao na tela"}
            r = self.det.detectar(img)
            na = 0 if r[0] is None else r[0].n
            nb = 0 if r[1] is None else r[1].n
            boa = na >= calibracao.N_MIN_VISTA and nb >= calibracao.N_MIN_VISTA
            aviso = ""
            if not boa:
                falta = "o notebook" if na < calibracao.N_MIN_VISTA else "o monitor"
                if na < calibracao.N_MIN_VISTA and nb < calibracao.N_MIN_VISTA:
                    falta = "nenhuma das telas"
                    aviso = "Nao achei nenhuma das telas. "
                else:
                    aviso = f"Nao achei {falta}. "
                aviso += "Deixe as DUAS telas inteiras no quadro, chegue mais perto e evite reflexo."
            elif img.shape[0] > img.shape[1]:
                aviso = "Foto em pe: segure o celular deitado nas proximas."
            if boa:                              # so guarda o que serve
                os.makedirs(self.pasta, exist_ok=True)
                nome = f"foto_{len(self.fotos) + 1:02d}{ext}"
                with open(os.path.join(self.pasta, nome), "wb") as fh:
                    fh.write(dados)
            else:
                nome = "(descartada)"
            self.fotos.append({"nome": nome, "notebook": na, "monitor": nb, "boa": boa,
                               "tam": [int(img.shape[1]), int(img.shape[0])]})
        return {**self.estado(), "aviso": aviso, "ultima": self.fotos[-1]}

    def calcular(self):
        with self.trava:
            boas = sum(f["boa"] for f in self.fotos)
            if boas < MIN_CALCULAR:
                return {"erro": f"so {boas} fotos boas; tire pelo menos {MIN_CALCULAR}"}
            try:
                res = self.calcular_fn(self.pasta)
            except SystemExit as e:              # erro legivel do calcular
                return {"erro": str(e)}
            d = res["telas_json"]
            self.resultado = {"resumo": d["resumo"], "qualidade": d["qualidade"],
                              "avisos": res["avisos"], "n_fotos": res["n_duas_telas"]}
            self.terminou = True
        return self.estado()


PAGINA = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calibrar as telas</title>
<style>
:root{color-scheme:light dark;--fundo:#f5f5f2;--cartao:#fff;--texto:#1c1c1a;--fraco:#6b6b66;
--ok:#1f7a45;--ruim:#b3371f;--acao:#1d4ed8;--borda:#dcdcd6}
@media (prefers-color-scheme:dark){:root{--fundo:#161615;--cartao:#222220;--texto:#ecece8;
--fraco:#a3a39c;--ok:#5fd08a;--ruim:#ff8a70;--acao:#7aa2ff;--borda:#3a3a36}}
*{box-sizing:border-box}
body{margin:0;padding:16px;font:17px/1.45 system-ui,sans-serif;background:var(--fundo);color:var(--texto)}
h1{font-size:21px;margin:0 0 4px}
p{margin:8px 0}
.fraco{color:var(--fraco);font-size:15px}
.cartao{background:var(--cartao);border:1px solid var(--borda);border-radius:14px;padding:14px;margin:12px 0}
.num{font-size:40px;font-weight:700;line-height:1}
.sug{font-size:19px;font-weight:600}
button,label.botao{display:block;width:100%;padding:16px;border-radius:12px;border:0;font:inherit;
font-weight:700;font-size:19px;text-align:center;background:var(--acao);color:#fff;margin:10px 0}
button.sec{background:transparent;color:var(--acao);border:2px solid var(--acao)}
button.leve{background:transparent;color:var(--fraco);font-weight:400;font-size:15px;padding:8px}
button:disabled{opacity:.4}
input[type=file]{display:none}
ul{list-style:none;margin:0;padding:0}
li{padding:6px 0;border-top:1px solid var(--borda);font-size:15px;font-variant-numeric:tabular-nums}
.ok{color:var(--ok)} .ruim{color:var(--ruim)}
#aviso{font-weight:600}
table{width:100%;border-collapse:collapse;font-size:15px}
td{padding:4px 0;border-top:1px solid var(--borda)} td:last-child{text-align:right;font-weight:600}
</style></head><body>
<h1>Calibrar as duas telas</h1>
<p class="fraco">Celular deitado, lente 1x, as duas telas inteiras no quadro. Mude de lugar a cada foto.</p>

<div class="cartao">
  <div class="num"><span id="boas">0</span><span class="fraco" style="font-size:19px"> de <span id="ideal">12</span> fotos boas</span></div>
  <p class="fraco">Pr&oacute;xima foto:</p>
  <p class="sug" id="sug">de frente, no meio das duas telas</p>
  <label class="botao" id="rotulo">Tirar foto
    <input type="file" id="arq" accept="image/*" capture="environment"></label>
  <p id="aviso" class="ruim"></p>
  <button id="calc" class="sec" disabled>Calcular</button>
</div>

<div class="cartao" id="res" hidden>
  <h1 id="restit">Calibra&ccedil;&atilde;o pronta</h1>
  <table id="tab"></table>
  <div id="avisos"></div>
  <p class="fraco">No notebook, rode <b>python main.py</b>. Pode fechar esta p&aacute;gina.</p>
</div>

<div class="cartao"><ul id="lista"><li class="fraco">Nenhuma foto ainda.</li></ul>
<button id="rec" class="leve">Recome&ccedil;ar do zero</button></div>

<script>
const $ = id => document.getElementById(id);
let ocupado = false;
function mostrar(e){
  if(e.erro){ $('aviso').textContent = e.erro; return; }
  $('boas').textContent = e.boas; $('ideal').textContent = e.ideal;
  $('sug').textContent = e.sugestao;
  $('aviso').textContent = e.aviso || '';
  $('calc').disabled = ocupado || e.boas < e.minimo;
  const l = $('lista'); l.innerHTML = '';
  if(!e.fotos.length) l.innerHTML = '<li class="fraco">Nenhuma foto ainda.</li>';
  e.fotos.slice().reverse().forEach((f,i) => {
    const li = document.createElement('li');
    li.className = f.boa ? 'ok' : 'ruim';
    li.textContent = (f.boa ? '✓ ' : '✗ ') + 'Foto ' + (e.fotos.length - i) +
      ': notebook ' + f.notebook + ' cantos, monitor ' + f.monitor + ' cantos';
    l.appendChild(li);
  });
  const r = e.resultado; $('res').hidden = !r;
  if(r){
    const g = r.resumo, q = r.qualidade, linhas = [
      ['Monitor à', g.lado + ' do notebook'],
      ['Ângulo entre as telas', g.angulo_entre_telas_graus + '°'],
      ['Folga entre as bordas', g.folga_bordas_internas_cm + ' cm'],
      ['Tamanho do monitor', g.monitor_diagonal_pol + ' pol'],
      ['Erro de reprojeção', q.rms_reproj_px + ' px'],
      ['Fotos usadas', r.n_fotos]];
    $('tab').innerHTML = '';
    linhas.forEach(([a,b]) => { const tr = $('tab').insertRow();
      tr.insertCell().textContent = a; tr.insertCell().textContent = b; });
    $('avisos').innerHTML = '';
    r.avisos.forEach(a => { const p = document.createElement('p');
      p.className = 'ruim'; p.textContent = 'Aviso: ' + a; $('avisos').appendChild(p); });
    $('restit').textContent = r.avisos.length ? 'Calibração pronta, com avisos' : 'Calibração pronta';
    $('res').scrollIntoView({behavior:'smooth'});
  }
}
async function pedir(rota, corpo){
  ocupado = true; $('calc').disabled = true;
  try{
    const r = await fetch(rota, {method: corpo === undefined ? 'GET' : 'POST', body: corpo});
    ocupado = false; mostrar(await r.json());
  }catch(err){ ocupado = false; $('aviso').textContent = 'Sem conexão com o notebook. Ele e o celular estão na mesma rede?'; }
}
$('arq').addEventListener('change', async ev => {
  const f = ev.target.files[0]; if(!f) return;
  $('rotulo').firstChild.textContent = 'Enviando… ';
  await pedir('foto', f);
  $('rotulo').firstChild.textContent = 'Tirar foto ';
  ev.target.value = '';
});
$('calc').addEventListener('click', async () => {
  $('calc').textContent = 'Calculando…'; await pedir('calcular', ''); $('calc').textContent = 'Calcular';
});
$('rec').addEventListener('click', () => { if(confirm('Apagar a contagem e recomeçar?')) pedir('recomecar', ''); });
pedir('estado');
</script></body></html>
"""
