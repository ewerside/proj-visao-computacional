"""One Euro Filter (Casiez, Roussel, Vogel, CHI 2012)."""

import math


def _alpha(cutoff_hz, dt):
    """Coeficiente do passa-baixa exponencial para uma dada frequencia de corte."""
    tau = 1.0 / (2.0 * math.pi * cutoff_hz)
    return 1.0 / (1.0 + tau / dt)


class _PassaBaixa:
    """Passa-baixa exponencial de primeira ordem: y = a*x + (1-a)*y_anterior."""

    def __init__(self):
        self.y = None

    def filtrar(self, x, alpha):
        self.y = x if self.y is None else alpha * x + (1.0 - alpha) * self.y
        return self.y

    def reset(self):
        self.y = None


class OneEuro:
    """One Euro Filter para um escalar.

    A ideia central e que a frequencia de corte nao e fixa: ela sobe com a
    velocidade do sinal.

        fc = min_cutoff + beta * |velocidade estimada|

    Parado, a velocidade e quase zero, o corte cai para min_cutoff e o filtro
    mata o jitter. Em movimento, o corte sobe e o filtro deixa passar, evitando
    o atraso que faria a cena parecer de borracha presa a cabeca.

    E por isso que um passa-baixa comum nao resolve este problema: com corte fixo
    voce escolhe de uma vez entre tremer parado ou atrasar em movimento. O One
    Euro adia essa escolha para cada instante.

    Ajuste na pratica, nesta ordem:
      1. beta = 0, baixe min_cutoff ate o tremor parado sumir.
      2. suba beta ate o atraso em movimento rapido ficar aceitavel.
    """

    def __init__(self, min_cutoff, beta, d_cutoff):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x = _PassaBaixa()
        self._dx = _PassaBaixa()
        self._t_anterior = None
        self._x_anterior = None

    def reset(self):
        self._x.reset()
        self._dx.reset()
        self._t_anterior = None
        self._x_anterior = None

    def __call__(self, x, t):
        """x: valor bruto. t: tempo em segundos. Retorna o valor filtrado."""
        if self._t_anterior is None:
            self._t_anterior = t
            self._x_anterior = x
            return self._x.filtrar(x, 1.0)

        dt = t - self._t_anterior
        if dt <= 0.0:
            return self._x.y
        self._t_anterior = t

        # Derivada bruta, ela mesma suavizada antes de virar controle do corte.
        # Sem essa suavizacao o proprio ruido do sinal inflaria a velocidade
        # estimada e abriria o filtro justamente quando ele deveria fechar.
        dx = (x - self._x_anterior) / dt
        self._x_anterior = x
        dx_suave = self._dx.filtrar(dx, _alpha(self.d_cutoff, dt))

        cutoff = self.min_cutoff + self.beta * abs(dx_suave)
        return self._x.filtrar(x, _alpha(cutoff, dt))


class OneEuro3D:
    """Tres One Euro independentes, um por eixo. X, Y e Z nao se falam."""

    def __init__(self, min_cutoff, beta, d_cutoff):
        self.eixos = [OneEuro(min_cutoff, beta, d_cutoff) for _ in range(3)]

    def __call__(self, v, t):
        return [self.eixos[i](v[i], t) for i in range(3)]

    def ajustar(self, min_cutoff=None, beta=None):
        for eixo in self.eixos:
            if min_cutoff is not None:
                eixo.min_cutoff = min_cutoff
            if beta is not None:
                eixo.beta = beta

    def reset(self):
        for eixo in self.eixos:
            eixo.reset()
