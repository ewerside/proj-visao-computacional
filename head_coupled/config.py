"""Parametros fisicos e de execucao. TUDO EM METROS.

As linhas marcadas com [MEDIR] precisam ser preenchidas com regua/trena antes
de rodar. Elas definem a escala metrica de todo o sistema: erro aqui vira erro
proporcional na posicao estimada da cabeca e na perspectiva.
"""

import os

# ---------------------------------------------------------------- antropometria
# Distancia interpupilar, centro de pupila a centro de pupila.
# Valor atual: media antropometrica de homem adulto (~64 mm, desvio ~3.5 mm,
# cf. Dodgson 2004). Estatura correlaciona mal com IPD, entao a altura nao
# refina esse palpite. Substitua pela sua medida real quando puder (a DP da
# receita de oculos serve).
#
# IMPORTANTE, e contra-intuitivo: um erro aqui NAO afeta o Z. Substituindo
# f_px = ipd_px_calib * D / IPD_REAL na formula Z = f_px * IPD_REAL / ipd_px,
# o IPD_REAL cancela e sobra Z = D * ipd_px_calib / ipd_px. O Z depende so da
# trena. O erro de IPD vira ganho lateral: X e Y escalam linearmente com ele.
#
# Mas o cancelamento SO vale se calibrate.py e main.py usarem o mesmo valor.
# Mudou este numero, recalibre. O main.py confere isso contra o focal.json.
IPD_REAL = 0.064

# ------------------------------------------------------------------------- tela
# Area VISIVEL (acesa) da tela. NAO medido com regua: derivado do EDID do
# painel, que o firmware do monitor reporta ao Windows como 34 x 19 cm. O EDID
# trunca para centimetro inteiro, entao refinamos encaixando no painel padrao:
# a diagonal implicada, 15.33 pol, so e compativel com um 15.6 pol 16:9, que da
# 34.54 x 19.43 cm. Confirmacao independente: isso resulta em 141.2 DPI a
# 1920x1080, o valor canonico de um 15.6 pol Full HD.
# Incerteza da ordem de 1 mm. Se um dia medir com regua, substitua.
SCREEN_W = 0.345
SCREEN_H = 0.194

# Deslocamento da lente da webcam em relacao ao CENTRO da tela, Y positivo para
# cima. Este e o unico numero ainda estimado: 10 mm da borda superior da area
# acesa ate o centro da lente, tipico de moldura superior de notebook moderno.
# Incerteza de +-5 mm, que desloca o olho virtual em 5 mm. Efeito desprezivel:
# e um vies constante na posicao neutra de visao, nao um erro de escala nem
# tremor, e a percepcao absorve inteiramente.
CAM_OFFSET_Y = SCREEN_H / 2 + 0.010
# Quase sempre 0 (webcam centralizada). Medir so se a sua for deslocada.
CAM_OFFSET_X = 0.0

# Resolucao da tela em pixels. O main.py confere contra o tamanho real da janela
# em fullscreen e usa o valor real; este aqui e so referencia.
SCREEN_PX_W = 1920
SCREEN_PX_H = 1080

# ---------------------------------------------------------------------- webcam
CAM_INDEX = 0
CAM_REQ_W = 1280   # resolucao pedida a webcam; quanto maior, menos ruido no ipd_px
CAM_REQ_H = 720
FLIP_FRAME = True  # espelha o frame; ver nota de sinal em tracking.py
CAM_WARMUP_S = 1.5 # descarte inicial de frames ate a auto-exposicao convergir

# ------------------------------------------------------------------ calibracao
# [MEDIR] Distancia usada no calibrate.py, da lente ate os seus olhos,
# medida PERPENDICULAR ao plano da tela (nao na diagonal).
CALIB_DISTANCE = 0.60
CALIB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "focal.json")

# ------------------------------------------------------------------- One Euro
# Valores de partida da especificacao. ATENCAO, medido: neste sistema BETA=0.007
# e indistinguivel de BETA=0, e o filtro degenera num passa-baixa de corte fixo.
#
# O motivo e escala de unidade. O corte adaptativo e fc = min_cutoff + beta*|v|,
# e aqui v esta em METROS por segundo. Cabeca se move a 0.1-0.5 m/s, entao
# beta=0.007 acrescenta 0.003 Hz a um corte de 1.0 Hz: nada. Os valores
# canonicos do artigo pressupoem sinais em pixels ou graus, onde |v| e centenas
# de vezes maior. Em metros, beta precisa ser da ordem de 1 a 20.
#
# Varredura medida (tremor de 1.19 cm parado, movimento de 20 cm em 0.5 s):
#   min_cutoff  beta  | tremor parado | erro em movimento
#      1.0      0.007 |    0.48 cm    |    4.22 cm
#      1.0      5.0   |    0.56 cm    |    1.93 cm
#      0.3     15.0   |    0.61 cm    |    1.17 cm
#      0.3      0.007 |    0.27 cm    |    7.23 cm
#
# Ajuste ao vivo com as teclas 1,2 (min_cutoff) e 3,4 (beta) e veja o tremor
# medido no overlay de debug.
MIN_CUTOFF = 1.0
BETA = 0.007
D_CUTOFF = 1.0

# --------------------------------------------------------------- estereoscopia
# O modo anaglifo renderiza a cena DUAS vezes, uma por olho, e compoe as duas
# imagens num par vermelho-ciano. A formula de projecao nao muda em nada: e a
# mesma intersecao raio-plano, chamada com dois `eye` diferentes.

# Fator sobre a separacao interocular real. 1.0 e o geometricamente correto: os
# dois olhos virtuais ficam exatamente a IPD_REAL um do outro, que e a distancia
# dos seus olhos de verdade.
#
# So que o geometricamente correto e frequentemente o infusionavel, e isso nao e
# defeito do modelo: uma caixa de verdade com 50 cm de profundidade, olhada de
# 60 cm, tambem produz disparidade grande demais para fundir o fundo e a boca ao
# mesmo tempo. Na vida real isso nao incomoda porque voce acomoda e converge
# juntos, e o que esta fora do plano de fixacao sai de foco e some. Na tela tudo
# esta a 60 cm e tudo esta em foco, entao a imagem dupla fica nitida e o cerebro
# nao tem como descartar.
#
# Usado quando STEREO_AUTO = False, ou depois que voce mexe nas teclas [ e ].
STEREO_SCALE = 1.0

# Escala calculada a cada quadro em vez de fixa. Ver escala_confortavel() em
# scene.py: e o valor que poe o vertice mais fundo da cena exatamente no limite
# de disparidade abaixo, dada a sua distancia atual da tela.
#
# Nao e um numero magico nem um ajuste a gosto: depende da distancia do seu
# rosto, que o sistema ja mede a cada quadro. Constante ele nao poderia estar
# certo, porque a mesma separacao em milimetros vira angulos diferentes conforme
# voce se aproxima ou se afasta.
STEREO_AUTO = True

# Disparidade maxima entre o ponto mais fundo e o plano da tela, em GRAUS de
# angulo visual. Duas imagens fundem enquanto a disparidade cabe na area de
# Panum, da ordem de 1 grau para conteudo com detalhe fino. E o limite em
# angulo, nao em pixels: 1 grau sao 10.5 mm a 60 cm e 7.0 mm a 40 cm.
#
# A regra pratica de 1/30 da largura da tela que se ve em cinema e este mesmo
# limite, escrito para uma distancia de visao tipica de sala.
STEREO_MAX_DISPARITY_DEG = 1.0

# Eixo interocular acompanhando a rolagem da cabeca, medida pela inclinacao da
# reta entre as duas irises.
#
# Com False o eixo fica travado na horizontal da tela, (1,0,0). E mais simples e
# nao tem tremor, mas se voce inclinar a cabeca os dois olhos virtuais deixam de
# estar alinhados com os seus olhos reais: parte da separacao horizontal na tela
# passa a cair no eixo vertical da sua retina, e paralaxe vertical e exatamente
# o que o sistema visual nao consegue fundir.
USE_HEAD_ROLL = True

# Matrizes de Dubois (Dubois, 2001, "A projection method to generate anaglyph
# stereo images", ICASSP). Entram em RGB normalizado em [0,1], NAO em BGR, e a
# soma das duas e cortada em [0,1]:
#
#     out_rgb = clip(M_L @ rgb_L + M_R @ rgb_R, 0, 1)
#
# O que elas fazem de diferente: em vez de escolher canais na marra, resolvem
# por minimos quadrados qual cor exibir para minimizar o erro que voce PERCEBE
# depois que cada lente filtra a tela, partindo do espectro medido de filtro e
# monitor. Os coeficientes negativos sao a pre-compensacao do vazamento.
DUBOIS_L = [[0.437, 0.449, 0.164],
            [-0.062, -0.062, -0.024],
            [-0.048, -0.050, -0.017]]
DUBOIS_R = [[-0.011, -0.032, -0.007],
            [0.377, 0.761, 0.009],
            [-0.026, -0.093, 1.234]]

# Ganho aplicado ao lado ciano (verde e azul) nos modos gray e true. 1.0 desliga.
#
# Existe porque as duas lentes nao entregam a mesma quantidade de luz: a ciano
# deixa passar dois primarios e a vermelha so um, entao o olho direito recebe
# uma imagem visivelmente mais clara que o esquerdo. Alem de desconfortavel por
# si so, isso faz o vazamento do ciano pela lente vermelha saltar mais. Se o
# lado ciano parecer forte demais, baixe mais.
#
# Quanto: numa tela sRGB o vermelho responde por 21% da luminancia do branco e o
# ciano (verde + azul) pelos outros 79%, entao o olho direito recebe 3.7 vezes
# mais luz que o esquerdo. Equalizar exatamente pediria 0.27, que escurece
# demais a cena inteira. 0.5 e meio caminho: corta metade do que vaza pela lente
# vermelha, que e o que voce esta enxergando, sem apagar o lado direito.
#
# Nao se aplica ao dubois: as matrizes dele ja embutem o espectro das lentes, e
# mexer no ganho de um lado desfaz a otimizacao.
ANAGLYPH_BALANCE = 0.5

# Piso de preto do cancelamento de vazamento, na tecla g. Ver compor() em
# anaglyph.py: cancelar vazamento e subtrair de cada canal o que ele vai receber
# do outro olho, e sobre preto puro essa subtracao satura em zero e nao faz nada.
# O piso da espaco para ela descer.
#
# E por isso que ligar o cancelamento custa o fundo preto, e por isso que ele
# esta numa tecla em vez de sempre ligado: 40 em 255 e cinza bem escuro, mas nao
# e preto, e o fundo preto e o que faz as paredes iluminadas saltarem.
ANAGLYPH_PEDESTAL = 40

# Paleta do modo anaglifo, por papel na cena. Vermelho e azul saturados sao o
# pior caso do anaglifo vermelho-ciano: um olho ve o objeto aceso e o outro ve
# preto, e o cerebro nao funde luminancias tao diferentes na mesma regiao. Em
# tom neutro os dois olhos recebem a mesma luminancia e so resta a diferenca de
# posicao, que e o sinal que interessa.
#
# Os objetos se distinguem por BRILHO, do mais proximo (mais claro) ao mais
# fundo (mais escuro). A ordem nao e so estetica: o objeto mais fundo e o de
# maior paralaxe, logo o de fantasma mais separado, e escurece-lo e o que mais
# reduz o fantasma visivel. O fundo continua preto.
#
# O que nao estiver aqui vira a propria luminancia, entao os outros cenarios
# tambem ficam neutros sem precisar de entrada propria.
# Os valores sao baixos de proposito. Vazamento de filtro e proporcional ao
# brilho: o mesmo oculos que deixa passar um fantasma obvio de um objeto quase
# branco deixa passar um fantasma desprezivel do mesmo objeto a 70% do branco.
# Aqui perde-se pouco, porque o que separa os objetos e o contraste entre eles,
# nao o brilho absoluto de nenhum.
ANAGLYPH_PALETTE = {
    "grid": (95, 95, 95),            # paredes laterais, chao e teto
    "grid_fundo": (130, 130, 130),   # parede do fundo, um pouco mais clara
    "objetos": [(195, 195, 195), (155, 155, 155), (115, 115, 115)],
}

# ------------------------------------------------------------------------ cena
EYE_Z_MIN = 0.10   # trava de seguranca: olho nunca colado no plano da tela
CENA_INICIAL = "caixa"     # caixa, corredor, miniatura ou barras; tecla n troca

# TODOS os cenarios sao interiores da mesma caixa, cuja boca em z=0 tem
# exatamente as dimensoes da tela. Essa coincidencia e o que faz a ilusao
# funcionar: vertices em z=0 projetam em si mesmos para qualquer posicao do
# olho, entao as bordas ficam pregadas no bezel e o bezel vira a moldura da
# janela. Cenario que flutua sem nada em z=0 desliza junto com a cabeca e le
# como figura escorregando, nao como janela.
#
# Cena "caixa": a caixa curta, com cubos flutuando dentro.
BOX_DEPTH = 0.5
GRID_N = 5

# Cena "corredor": a MESMA caixa, so que funda e sem parede no fundo. A secao
# transversal continua sendo o retangulo da tela, entao a boca segue pregada no
# bezel. Sem parede traseira, as linhas convergem e somem: le como infinito.
COR_DEPTH = 1.40
COR_DIVISOES = 11
TOCHA_Z = [-0.22, -0.48, -0.80, -1.16]   # profundidade de cada par de tochas
TOCHA_Y = 0.030                          # altura das tochas acima do centro

# Cena "miniatura": vilarejo assentado no chao da mesma caixa.
MINI_DEPTH = 0.62
MINI_DIVISOES = 7

# Cena "barras": poucas barras verticais no plano da tela e um objeto grande que
# atravessa esse plano pelo centro e volta.
#
# O alcance da frente e modesto de proposito. O que vende o efeito e a OCLUSAO
# pelas barras, nao a distancia percorrida; e z grande demais explode a
# ampliacao (fator t = eye.z / (eye.z - P.z)) se voce se aproximar da tela.
# Em z = +0.05, mesmo com o olho no limite de EYE_Z_MIN, o objeto ainda cabe
# dentro da tela, o que evita a violacao de janela descrita no scene.py.
BARRAS_N = 4
BARRAS_LARGURA = 0.007
BARRAS_SEGMENTOS = 6
HERO_LADO = 0.090
HERO_Z_FUNDO = -0.42
HERO_Z_FRENTE = 0.05
HERO_PERIODO = 9.0     # segundos para ida e volta completas
HERO_DERIVA = 0.060    # deriva lateral no fundo; vai a zero ao vir para a frente
