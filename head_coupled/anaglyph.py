"""Composicao anaglifo vermelho-ciano: duas imagens viram uma.

Convencao padrao, que e a dos oculos de papelao: lente VERMELHA no olho
esquerdo, lente CIANO no direito. A lente vermelha so deixa passar luz
vermelha, entao o olho esquerdo enxerga o que estiver escrito no canal R; a
lente ciano deixa passar verde e azul, entao o olho direito enxerga G e B.

Cuidado com a ordem dos canais: OpenCV e BGR. Canal 0 = azul, 1 = verde,
2 = vermelho.

O par de imagens que entra aqui tem que vir da MESMA ordenacao de faces, ou os
dois olhos podem discordar sobre qual face esta na frente. Ver order_faces em
scene.py.

Sobre fantasma: nenhum destes algoritmos elimina o vazamento das lentes, que num
oculos de papelao chega a 5-10% do verde passando pela lente vermelha. O que
determina se esse vazamento aparece como halo ou como um segundo objeto e a
PARALAXE: com disparidade pequena o fantasma cai em cima da imagem verdadeira e
some na fusao; com disparidade grande ele cai no vazio ao lado, sobre fundo
preto, e fica obvio. Fantasma incomodando e quase sempre sintoma de paralaxe
excessiva, nao de algoritmo errado.
"""

import cv2
import numpy as np

import config

MODOS = ["gray", "true", "dubois"]

# As matrizes de Dubois sao para RGB e a imagem esta em BGR. Inverter linhas e
# colunas de uma matriz 3x3 e exatamente a conjugacao pela permutacao que troca
# R com B: m_bgr[i][j] = m_rgb[2-i][2-j]. Assim nao e preciso virar a imagem,
# que custaria duas copias de 6 MB por quadro.
_DUBOIS_L_BGR = np.array(config.DUBOIS_L, np.float32)[::-1, ::-1]
_DUBOIS_R_BGR = np.array(config.DUBOIS_R, np.float32)[::-1, ::-1]

# Rascunhos do modo dubois, alocados uma vez por resolucao. Sem isso o modo
# custa 30 ms por quadro so de alocar e converter; com isso, 15 ms.
_SCRATCH = {}


def _scratch(shape):
    if shape not in _SCRATCH:
        _SCRATCH[shape] = tuple(np.zeros(shape, np.int16) for _ in range(4))
    return _SCRATCH[shape]


def _ciano(cinza_R):
    """Aplica o balanco de brilho do lado ciano, se houver."""
    if config.ANAGLYPH_BALANCE == 1.0:
        return cinza_R
    return cv2.convertScaleAbs(cinza_R, alpha=config.ANAGLYPH_BALANCE)


def compor(img_L, img_R, out, modo="gray", ghost_k=0.0, pedestal=0):
    """Compoe o par estereo em `out`, no lugar. Retorna `out`.

    `ghost_k` e `pedestal` ligam o cancelamento de vazamento, e so valem no modo
    "gray". Ver o bloco sobre cancelamento no fim deste docstring.

    "gray": cada olho vira luminancia, e a luminancia do esquerdo vai para o
    vermelho enquanto a do direito vai para verde e azul.

        out[:, :, 2] = cinza_L        vermelho, olho esquerdo
        out[:, :, 1] = cinza_R        verde  \\ os dois juntos sao o ciano
        out[:, :, 0] = cinza_R        azul   /  do olho direito

    Perde a cor da cena inteira, e e por isso mesmo que e o padrao. Rivalidade
    retiniana em anaglifo aparece quando os dois olhos recebem LUMINANCIAS
    diferentes na mesma regiao, e e isso que o cerebro se recusa a fundir.
    Mandando a mesma luminancia para os dois lados do espectro, so resta a
    diferenca de posicao, que e justamente o sinal que queremos. De longe o mais
    confortavel de olhar por varios minutos.

    "true": os canais originais, sem passar por cinza. Guarda alguma cor, mas
    uma superficie vermelha saturada vira luminancia alta no olho esquerdo e
    quase zero no direito, o que e o caso extremo da rivalidade acima. So vale a
    pena com a paleta neutra ligada.

    "dubois": projecao por minimos quadrados (Dubois, 2001). Em vez de escolher
    canais na marra, resolve qual cor exibir para minimizar o erro percebido
    DEPOIS que cada lente filtra a tela, usando o espectro real de filtro e
    monitor. E o que melhor preserva cor, e o mais caro: 15 ms por quadro contra
    2 ms do gray.
    """
    if modo == "gray":
        cinza_L = cv2.cvtColor(img_L, cv2.COLOR_BGR2GRAY)
        cinza_R = cv2.cvtColor(img_R, cv2.COLOR_BGR2GRAY)

        if ghost_k > 0.0 or pedestal > 0:
            # Cancelamento de vazamento. Cada canal leva, alem da sua propria
            # imagem, MENOS a fracao que a lente do outro olho vai deixar vazar,
            # para que a soma dos dois na retina de o valor certo:
            #
            #     base_L  = piso + L*esc              o que o olho esq deve ver
            #     base_R  = (piso + R*esc) * balanco  idem, ja balanceado
            #     canal_L = base_L - k*base_R
            #     canal_R = base_R - k*base_L
            #
            # O balanco entra ANTES da subtracao, e nao depois: o que vaza pela
            # lente vermelha e o ciano que sai da tela, ja atenuado. Subtrair o
            # ciano cheio e depois atenuar descontaria o dobro do que vaza, e o
            # fantasma ficaria mais escuro que o fundo em vez de sumir nele.
            #
            # As duas equacoes se referem uma a outra; resolver em uma passada
            # so, com os valores nao-cancelados, deixa um residuo de k^2, que
            # em 10% de vazamento sao 2 niveis em 255.
            #
            # Onde so existe imagem do olho direito, o canal vermelho cai ABAIXO
            # do piso; ai o vazamento do ciano soma de volta e o fantasma termina
            # na mesma luminancia do fundo, sumindo nele. Sobre preto puro isso
            # nao funciona, porque a subtracao saturaria em zero e nao teria de
            # onde descer: e essa a razao do pedestal. `esc` comprime a imagem
            # para caber acima do piso, senao o branco estouraria.
            esc = (255.0 - pedestal) / 255.0
            bal = config.ANAGLYPH_BALANCE
            base_L = cv2.convertScaleAbs(cinza_L, alpha=esc, beta=pedestal)
            base_R = cv2.convertScaleAbs(cinza_R, alpha=esc * bal,
                                         beta=pedestal * bal)
            cinza_L = cv2.addWeighted(base_L, 1.0, base_R, -ghost_k, 0)
            cinza_R = cv2.addWeighted(base_R, 1.0, base_L, -ghost_k, 0)
        else:
            cinza_R = _ciano(cinza_R)

        # merge monta B, G, R de uma vez e escreve direto no destino.
        cv2.merge([cinza_R, cinza_R, cinza_L], out)
        return out

    # Os dois modos abaixo ficam sem cancelamento de proposito. O dubois ja o
    # tem embutido: os coeficientes negativos das matrizes SAO pre-compensacao
    # de vazamento, medida no espectro real, e somar outra por cima estragaria
    # a otimizacao. O true e a implementacao ingenua e serve de referencia; se
    # ele nao doesse os olhos, nao haveria por que existir gray.
    if modo == "true":
        out[:, :, 2] = img_L[:, :, 2]
        out[:, :, 1] = _ciano(img_R[:, :, 1])
        out[:, :, 0] = _ciano(img_R[:, :, 0])
        return out

    if modo == "dubois":
        # int16 em vez de float32: o erro contra a conta em ponto flutuante e de
        # 1 nivel em 255, invisivel, e a largura de banda de memoria cai pela
        # metade. O balanco de brilho NAO se aplica aqui: as matrizes ja foram
        # ajustadas contra o espectro medido das lentes, e mexer no ganho de um
        # lado desfaz exatamente a otimizacao que elas fazem.
        iL, iR, ac1, ac2 = _scratch(out.shape)
        np.copyto(iL, img_L)
        np.copyto(iR, img_R)
        cv2.transform(iL, _DUBOIS_L_BGR, ac1)
        cv2.transform(iR, _DUBOIS_R_BGR, ac2)
        cv2.add(ac1, ac2, ac1)
        np.clip(ac1, 0, 255, out=ac1)
        np.copyto(out, ac1, casting="unsafe")
        return out

    raise ValueError(f"modo de composicao desconhecido: {modo!r}")


# ------------------------------------------------------- medicao de vazamento

# Nivel dos quadrados de teste, igual ao objeto mais claro da paleta: e o
# vazamento NESSE brilho que interessa, nao no branco puro que a cena nunca usa.
_NIVEL = 195


def padrao_vazamento(out, pct):
    """Padrao para MEDIR quanto cada lente deixa passar do olho errado.

    Cada faixa e um quadrado partido ao meio, com as duas metades ENCOSTADAS:
    de um lado a cor pura, do outro um cinza a `pct` por cento do mesmo nivel.
    Olhando por uma lente so, a metade colorida aparece apenas pelo que vaza e a
    metade cinza aparece pelo canal legitimo daquela lente. Quando as duas
    metades ficam iguais e a fronteira entre elas some, `pct` E o vazamento.

    Duas metades encostadas sao muito mais faceis de igualar que dois quadrados
    separados: o olho e pessimo para julgar brilho absoluto e otimo para
    detectar uma borda. Por isso o ajuste substituiu a regua de degraus.

    Como usar, uma lente de cada vez, com o outro olho fechado:
      faixa de cima, pela lente VERMELHA;  faixa de baixo, pela lente CIANO.
      Ajuste com [ e ] ate a fronteira sumir e leia a porcentagem.

    Referencia: abaixo de 5% funde sem esforco; 10% e o tipico de oculos de
    papelao e ja incomoda em cena de alto contraste; acima de 20% a fusao nao
    acontece, e nenhum ajuste de paralaxe ou de algoritmo resolve.
    """
    out[:] = 0
    fonte = cv2.FONT_HERSHEY_SIMPLEX
    cinza = (150, 150, 150)
    v = round(_NIVEL * pct / 100)

    cv2.putText(out, "TESTE DE VAZAMENTO DAS LENTES", (120, 70), fonte, 0.9,
                cinza, 2, cv2.LINE_AA)
    cv2.putText(out, "Feche um olho, olhe por UMA lente, e ajuste com [ e ] ate "
                     "a metade colorida ficar igual a cinza ao lado.",
                (120, 112), fonte, 0.65, cinza, 1, cv2.LINE_AA)

    faixas = [("faixa de cima: olhe pela lente VERMELHA", (_NIVEL, _NIVEL, 0)),
              ("faixa de baixo: olhe pela lente CIANO", (0, 0, _NIVEL))]
    for i, (titulo, cor) in enumerate(faixas):
        y = 190 + i * 380
        cv2.putText(out, titulo, (120, y), fonte, 0.7, cinza, 1, cv2.LINE_AA)
        cv2.rectangle(out, (120, y + 25), (420, y + 325), cor, -1)
        cv2.rectangle(out, (420, y + 25), (720, y + 325), (v, v, v), -1)

    cv2.putText(out, f"{pct}%", (820, 430), fonte, 3.0, cinza, 4, cv2.LINE_AA)
    cv2.putText(out, "abaixo de 5% funde sem esforco     10% e o tipico de "
                     "oculos de papelao     acima de 20% nao funde",
                (120, 1010), fonte, 0.7, cinza, 1, cv2.LINE_AA)
    return out
