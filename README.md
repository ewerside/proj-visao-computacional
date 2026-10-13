# Head-Coupled Perspective — Visão Computacional

Projeto da disciplina **Visão Computacional** do **Ibmec Barra**, ministrada pelo professor **Rigel Fernandes**.

**Integrantes do grupo:** Ewerton Arrais, Miguel Veiga e Emilly Fernandes.

Este repositório contém a **primeira parte** do projeto (AP1). A segunda parte (AP2) está descrita na seção [Objetivo futuro](#objetivo-futuro-ap2).

---

## O que é o projeto

Usando apenas a **webcam** do notebook, o programa acompanha a posição dos seus olhos e **muda a perspectiva da imagem na tela de acordo com a posição da sua cabeça**. O resultado é uma ilusão de 3D: a tela deixa de parecer uma imagem plana e passa a parecer uma *janela* para dentro de uma caixa. Se você move a cabeça para a direita, enxerga mais o lado esquerdo do interior da caixa; se chega mais perto, a cena se amplia, como em uma janela de verdade. Essa técnica é conhecida como *head-coupled perspective*.

## Como funciona (resumo)

1. **Detecção dos olhos.** O MediaPipe (*Face Landmarker*) encontra 478 pontos do rosto em cada frame da webcam. Usamos o centro das duas íris.
2. **Posição 3D da cabeça.** Com o modelo de câmera *pinhole*, a distância entre as íris (em pixels) revela a distância da cabeça à câmera: quanto menor a distância em pixels, mais longe você está. Isso dá X, Y e Z em metros. A distância focal da webcam é obtida uma única vez numa **calibração** (`calibrate.py`).
3. **Suavização.** A posição estimada treme um pouco. Um **One Euro Filter** remove o tremor quando a cabeça está parada e deixa passar o movimento rápido sem atraso.
4. **Projeção off-axis.** A tela é tratada como um plano físico (com tamanho real em metros). Cada ponto 3D da cena é projetado nesse plano a partir da posição atual do olho, e o resultado é desenhado em tela cheia.

**Tecnologias:** Python, OpenCV, MediaPipe e NumPy.

**Técnicas:** detecção de *landmarks* faciais, modelo de câmera pinhole e calibração de distância focal, filtragem de sinais (One Euro Filter) e projeção em perspectiva assimétrica.

## Como rodar

Os programas foram desenvolvidos e testados em **Windows** (a captura usa o backend MSMF e a janela usa chamadas do Windows) com Python 3.14.

```bash
pip install opencv-python mediapipe numpy
cd head_coupled

# 1. Ajuste as medidas da sua tela e webcam em config.py (valores em metros)
# 2. Calibre a webcam uma vez (sente-se a uma distância conhecida da lente)
python calibrate.py

# 3. Rode o programa principal (q ou ESC para sair)
python main.py
```

## Estrutura

| Arquivo | Função |
|---|---|
| `main.py` | Loop principal: webcam → posição da cabeça → render em tela cheia |
| `tracking.py` | Detecção das íris e cálculo da posição 3D da cabeça |
| `calibrate.py` | Calibração da distância focal da webcam |
| `filters.py` | One Euro Filter |
| `scene.py` | Geometria das cenas e projeção |
| `config.py` | Medidas físicas e parâmetros |

## Funcionalidades extras (em desenvolvimento)

Além do núcleo descrito acima, o código já traz alguns testes e recursos experimentais que ainda estão em desenvolvimento e podem mudar:

- Vários cenários para trocar durante a execução (caixa, corredor, miniatura, barras).
- **Modo anaglifo** vermelho-ciano (estereoscopia para óculos 3D de papelão), com diferentes algoritmos de composição e ajustes de conforto.
- Compensação da inclinação lateral da cabeça (*roll*).
- Overlay de debug e ajuste ao vivo do filtro por teclado (as teclas estão listadas no cabeçalho do `main.py`).

## Objetivo futuro (AP2)

> **TODO (grupo):** o texto do artigo não foi passado a quem escreveu este README. Substituir este parágrafo por 2–3 linhas resumindo o objetivo descrito no artigo.

O projeto descrito no artigo da disciplina é o objetivo final do grupo e será desenvolvido como trabalho da **AP2**. O que está neste repositório é a base inicial para ele.
