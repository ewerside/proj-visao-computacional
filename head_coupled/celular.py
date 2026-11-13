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

O celular e o notebook precisam estar na MESMA rede, e a rede tem de deixar um
aparelho falar com o outro. Na primeira vez o Windows pergunta se o Python pode
receber conexoes: permita.

SEM A MESMA REDE (--tunel): rede de faculdade que isola os aparelhos, ou o
roteador do proprio celular, que em alguns aparelhos nao entrega conexoes dele
mesmo para o notebook. Com --tunel o notebook abre uma conexao de SAIDA por ssh
ate um servico de tunel (serveo.net; reserva: localhost.run) e ganha um endereco
publico https; o QR aponta para ele e o celular acessa pela internet (4G/5G ou
qualquer Wi-Fi). O servidor local passa a escutar so em 127.0.0.1. As fotos
passam pelo servico de terceiros, e o endereco fica publico enquanto o comando
roda, protegido pelo codigo do QR.
Medido em 13/11/2026: serveo.net levou 6.5 s para 5 MB; o plano gratuito do
localhost.run limita a ~16 kB/s (5 minutos por foto), por isso e so reserva.
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
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


# Servicos de tunel por ssh, na ordem de tentativa: destino e formato do endereco.
TUNEIS = {
    "serveo": ("serveo.net", r"https://[a-z0-9-]+\.serveo(?:usercontent)?\.(?:com|net)"),
    "localhost.run": ("nokey@localhost.run", r"https://[a-z0-9-]+\.lhr\.life"),
}


def _tunel_ssh(ssh, porta, destino, padrao, espera_s):
    proc = subprocess.Popen(
        [ssh, "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=30",
         "-o", "ExitOnForwardFailure=yes", "-R", f"80:127.0.0.1:{porta}", destino],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    achado, linhas = [], []

    def ler():
        for bruto in proc.stdout:
            linha = bruto.decode("utf-8", "replace")
            linhas.append(linha.strip())
            m = re.search(padrao, linha)
            if m and not achado:
                achado.append(m.group(0))

    threading.Thread(target=ler, daemon=True).start()
    fim = time.time() + espera_s
    while time.time() < fim and not achado and proc.poll() is None:
        time.sleep(0.2)
    if not achado:
        proc.terminate()
        return None, " | ".join(l_ for l_ in linhas[-3:] if l_)
    return proc, achado[0]


def abrir_tunel(porta, servico=None, espera_s=20.0):
    """Tunel reverso por ssh. Devolve (processo, url https, nome do servico).

    So conexao de saida; nada e instalado. servico: nome em TUNEIS, ou None para
    tentar todos na ordem. Levanta RuntimeError com mensagem legivel se o ssh
    nao existir ou nenhum servico responder.
    """
    ssh = shutil.which("ssh")
    if ssh is None:
        raise RuntimeError("nao achei o programa ssh (no Windows: Configuracoes > "
                           "Recursos opcionais > Cliente OpenSSH)")
    erros = []
    for nome in ([servico] if servico else list(TUNEIS)):
        destino, padrao = TUNEIS[nome]
        proc, r = _tunel_ssh(ssh, porta, destino, padrao, espera_s)
        if proc is not None:
            return proc, r, nome
        erros.append(f"{nome}: {r or 'sem resposta'}")
    raise RuntimeError("o tunel nao abriu (sem internet, ou o servico esta fora do ar). "
                       + "; ".join(erros))


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
        self.t_terminou = None          # quando terminou (time.time())
        self.resultado_entregue = False  # o celular ja recebeu o resultado
        self.calculando = False
        self.erro_calculo = None
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
                try:
                    self.end_headers()
                    self.wfile.write(corpo)
                except OSError:                  # o celular desistiu de esperar
                    pass

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
                    e = servidor.estado()
                    self._json(e)
                    if e["resultado"] is not None:
                        servidor.resultado_entregue = True
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
            self.recebidas = {}         # sha1 dos bytes -> entrada de self.fotos
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
                "sugestao": SUGESTOES[boas % len(SUGESTOES)], "resultado": self.resultado,
                "calculando": self.calculando, "erro_calculo": self.erro_calculo}

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
        marca = hashlib.sha1(dados).hexdigest()
        with self.trava:
            if self.det is None:
                return {"erro": "os padroes ainda nao estao na tela"}
            if marca in self.recebidas:      # reenvio da mesma foto (rede instavel)
                return {**self.estado(), "aviso": "", "ultima": self.recebidas[marca]}
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
                               "tam": [int(img.shape[1]), int(img.shape[0])],
                               "kb": len(dados) // 1000, "hora": time.strftime("%H:%M:%S")})
            self.recebidas[marca] = self.fotos[-1]
        return {**self.estado(), "aviso": aviso, "ultima": self.fotos[-1]}

    def calcular(self):
        """Dispara o calculo em segundo plano e responde na hora.

        O calculo leva de 10 a 60 s; segurar o pedido aberto esse tempo todo faz
        o tunel ou o navegador desistir, e o resultado nao chega ao celular. A
        pagina consulta /estado ate "calculando" virar falso.
        """
        boas = sum(f["boa"] for f in self.fotos)
        if boas < MIN_CALCULAR:
            return {"erro": f"so {boas} fotos boas; tire pelo menos {MIN_CALCULAR}"}
        if not self.calculando:
            self.calculando, self.erro_calculo = True, None
            threading.Thread(target=self._calcular, daemon=True).start()
        return self.estado()

    def _calcular(self):
        try:
            with self.trava:
                res = self.calcular_fn(self.pasta)
            d = res["telas_json"]
            self.resultado = {"resumo": d["resumo"], "qualidade": d["qualidade"],
                              "avisos": res["avisos"], "n_fotos": res["n_duas_telas"]}
            self.t_terminou = time.time()
            self.terminou = True
        except SystemExit as e:                  # erro legivel do calcular
            self.erro_calculo = str(e)
        except Exception as e:
            self.erro_calculo = f"erro no notebook: {e}"
        finally:
            self.calculando = False


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
.barra{position:relative;height:18px;border-radius:9px;background:var(--borda);margin:14px 0 6px;overflow:hidden}
.cheio{height:100%;width:0;border-radius:9px;background:var(--acao);transition:width .4s ease,background .4s}
.cheio.pronto{background:var(--ok)}
.marca{position:absolute;top:0;bottom:0;width:2px;background:var(--texto);opacity:.55}
button,label.botao{display:block;width:100%;padding:16px;border-radius:12px;border:0;font:inherit;
font-weight:700;font-size:19px;text-align:center;background:var(--acao);color:#fff;margin:10px 0}
button.sec,label.sec2{background:transparent;color:var(--acao);border:2px solid var(--acao)}
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
  <div class="barra" role="progressbar" aria-valuemin="0" id="barra">
    <div class="cheio" id="cheio"></div><div class="marca" id="marca"></div></div>
  <p id="falta" class="fraco">Tire a primeira foto.</p>
  <p class="fraco">Pr&oacute;xima foto:</p>
  <p class="sug" id="sug">de frente, no meio das duas telas</p>
  <label class="botao" id="rotulo">Tirar foto
    <input type="file" id="arq" accept="image/*" capture="environment"></label>
  <label class="botao sec2" id="rotulo2">Enviar várias da galeria
    <input type="file" id="varias" accept="image/*" multiple></label>
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
  const pct = Math.min(100, 100 * e.boas / e.ideal);
  $('cheio').style.width = pct + '%';
  $('cheio').className = 'cheio' + (e.boas >= e.ideal ? ' pronto' : '');
  $('marca').style.left = (100 * e.minimo / e.ideal) + '%';
  $('barra').setAttribute('aria-valuemax', e.ideal);
  $('barra').setAttribute('aria-valuenow', e.boas);
  const plural = n => n + (n === 1 ? ' foto' : ' fotos');
  $('falta').textContent =
    e.boas === 0 ? 'Tire a primeira foto.' :
    e.boas < e.minimo ? 'Faltam ' + plural(e.minimo - e.boas) + ' para poder calcular.' :
    e.boas < e.ideal ? 'Já dá para calcular. Mais ' + plural(e.ideal - e.boas) + ' deixam o resultado melhor.' :
    'Pronto: toque em Calcular.';
  $('aviso').textContent = e.aviso || '';
  $('calc').disabled = ocupado || e.calculando || e.boas < e.minimo;
  $('calc').textContent = e.calculando ? 'Calculando… (até 1 minuto)' : 'Calcular';
  if(e.erro_calculo) $('aviso').textContent = e.erro_calculo;
  if(e.calculando) setTimeout(() => pedir('estado'), 2000);
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
  for(let tentativa = 1; tentativa <= 3; tentativa++){
    try{
      const r = await fetch(rota, {method: corpo === undefined ? 'GET' : 'POST', body: corpo});
      const e = await r.json();
      ocupado = false; mostrar(e); return;
    }catch(err){
      if(tentativa < 3){
        $('aviso').textContent = 'Falhou, tentando de novo (' + tentativa + '/3)…';
        await new Promise(ok => setTimeout(ok, 1500));
      }
    }
  }
  ocupado = false;
  $('aviso').textContent = 'Sem conexão com o notebook. Confira a rede do celular e tente de novo.';
}
$('arq').addEventListener('change', async ev => {
  const f = ev.target.files[0]; if(!f) return;
  $('rotulo').firstChild.textContent = 'Enviando… ';
  await pedir('foto', f);
  $('rotulo').firstChild.textContent = 'Tirar foto ';
  ev.target.value = '';
});
$('varias').addEventListener('change', async ev => {
  const lista = Array.from(ev.target.files);
  for(let i = 0; i < lista.length; i++){
    $('rotulo2').firstChild.textContent = 'Enviando ' + (i + 1) + ' de ' + lista.length + '… ';
    await pedir('foto', lista[i]);
  }
  $('rotulo2').firstChild.textContent = 'Enviar várias da galeria ';
  ev.target.value = '';
});
$('calc').addEventListener('click', () => pedir('calcular', ''));
$('rec').addEventListener('click', () => { if(confirm('Apagar a contagem e recomeçar?')) pedir('recomecar', ''); });
pedir('estado');
</script></body></html>
"""


def _teste(argv=None):
    """Teste so do envio, sem monitor externo e sem calibrar:

        python celular.py [--tunel]

    Abre o servidor (e o tunel), mostra o QR code numa janela e lista no
    terminal cada foto que chegar, com o tamanho e o tempo desde a anterior.
    As fotos nao sao guardadas (sem os padroes na tela nenhuma serve para a
    calibracao). q ou ESC na janela encerra.
    """
    import argparse
    import tempfile

    import padroes

    ap = argparse.ArgumentParser(description="teste do envio de fotos pelo celular")
    ap.add_argument("--tunel", action="store_true", help="acesso pela internet (ssh)")
    ap.add_argument("--tunel-servico", choices=list(TUNEIS), default=None)
    ap.add_argument("--porta", type=int, default=PORTA)
    args = ap.parse_args(argv)

    def sem_calculo(_pasta):
        raise SystemExit("modo de teste: aqui so o envio e testado")

    srv = Servidor(os.path.join(tempfile.gettempdir(), "celular_teste"), sem_calculo,
                   args.porta, host="127.0.0.1" if args.tunel else "0.0.0.0")
    srv.definir_padroes(padroes.padroes_projeto())
    tunel = None
    if args.tunel:
        print("abrindo o tunel pela internet...")
        try:
            tunel, publico, servico = abrir_tunel(srv.porta, args.tunel_servico)
        except RuntimeError as e:
            print(e)
            return 1
        srv.url = f"{publico}/{srv.token}/"
        print(f"tunel aberto por {servico}")
    srv.iniciar()
    print(f"\nNo celular, leia o QR code da janela ou abra:\n    {srv.url}\n"
          "Tire algumas fotos pela pagina (de qualquer coisa). Vao aparecer como\n"
          "descartadas, porque nao ha padroes na tela: aqui so o envio importa.\n"
          "q ou ESC na janela do QR encerra.\n")
    qr = imagem_qr(srv.url, 560)
    tela = np.full((660, 600, 3), 255, np.uint8)
    tela[20:580, 20:580] = qr
    cv2.putText(tela, "Leia com a camera do celular   (q sai)", (20, 630),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2, cv2.LINE_AA)
    vistas, t_ant, conectou = 0, time.time(), False
    try:
        while True:
            cv2.imshow("teste do celular", tela)
            if cv2.waitKey(200) & 0xFF in (ord("q"), 27):
                break
            if cv2.getWindowProperty("teste do celular", cv2.WND_PROP_VISIBLE) < 1:
                break
            if srv.conectado and not conectou:
                conectou, t_ant = True, time.time()
                print("celular abriu a pagina")
            while vistas < len(srv.fotos):
                f = srv.fotos[vistas]
                vistas += 1
                agora = time.time()
                print(f"  foto {vistas}: {f['kb'] / 1000:.1f} MB, {f['tam'][0]}x{f['tam'][1]}, "
                      f"chegou as {f['hora']} ({agora - t_ant:.0f} s depois da anterior)")
                t_ant = agora
    finally:
        cv2.destroyAllWindows()
        srv.parar()
        if tunel is not None:
            tunel.terminate()
    print(f"{vistas} foto(s) recebida(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_teste())
