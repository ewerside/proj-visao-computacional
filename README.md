# Head-Coupled Perspective — Visão Computacional

Projeto da disciplina **Visão Computacional** do **Ibmec Barra**, ministrada pelo professor **Rigel Fernandes**.

**Integrantes do grupo:** Ewerton Arrais, Miguel Veiga e Emilly Fernandes.

Este repositório contém as duas partes do projeto:

- **AP1:** *head-coupled perspective* numa tela só, a do notebook.
- **AP2:** duas telas (o notebook e um monitor externo em qualquer ângulo), com a posição do monitor calibrada por fotos de celular. Veja a seção [AP2: duas telas](#ap2-duas-telas).

---

## O que é o projeto

Usando apenas a **webcam** do notebook, o programa acompanha a posição dos seus olhos e **muda a perspectiva da imagem na tela de acordo com a posição da sua cabeça**. O resultado é uma ilusão de 3D: a tela deixa de parecer uma imagem plana e passa a parecer uma *janela* para dentro de uma caixa. Se você move a cabeça para a direita, enxerga mais o lado esquerdo do interior da caixa; se chega mais perto da tela, enxerga uma parte maior do interior da caixa, como em uma janela de verdade. Essa técnica é conhecida como *head-coupled perspective*.

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
pip install -r requirements.txt     # NAO instale opencv-python junto (ver requirements.txt)
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
| `monitores.py` | AP2: escala de tela do Windows, lista de monitores, janela em tela cheia em cada monitor |
| `testar_monitores.py` | AP2: teste rápido dos dois monitores (moldura de 1 px, teclas, qual é o notebook) |
| `telas.py` | AP2: pose de cada tela no referencial do notebook, leitura do `telas.json`, projeção e recorte por tela |
| `sala.py` | AP2: cenas de mundo compartilhado, vistas pelas duas telas (`sala`, `alinhamento`) |
| `calibrar_telas.py` | AP2: calibração com o celular (`mostrar`, `calcular`) e plano B por trena (`manual`) |
| `padroes.py`, `detectar.py`, `calibracao.py` | AP2: padrões ChArUco, detecção nas fotos, cálculo da pose (ajuste de feixes) |
| `simular.py` | AP2: fotos sintéticas com resposta conhecida, para testar sem celular |
| `teste_guinada.py` | AP2: protocolo de 10 min da correção de guinada na webcam real |
| `testes/` | AP2: testes automáticos sem hardware (`python testes/rodar_testes.py`) |

## Funcionalidades extras (em desenvolvimento)

Além do núcleo descrito acima, o código já traz alguns testes e recursos experimentais que ainda estão em desenvolvimento e podem mudar:

- Vários cenários para trocar durante a execução (caixa, corredor, miniatura, barras).
- **Modo anaglifo** vermelho-ciano (estereoscopia para óculos 3D de papelão), com diferentes algoritmos de composição e ajustes de conforto.
- Compensação da inclinação lateral da cabeça (*roll*).
- Overlay de debug e ajuste ao vivo do filtro por teclado (as teclas estão listadas no cabeçalho do `main.py`).

## AP2: duas telas

O notebook e um monitor externo, lado a lado e em qualquer ângulo, viram duas janelas para o mesmo mundo 3D. A webcam do notebook continua fazendo o rastreamento dos olhos, e as duas imagens mudam juntas em tempo real.

**Como funciona:**

1. **Calibração pelo celular.** Cada tela mostra um tabuleiro ChArUco com marcadores diferentes. Com o app de câmera normal, você tira de 10 a 15 fotos das duas telas, de lugares diferentes.
   - O tamanho físico dos quadrados sai do tamanho da tela e da resolução, então nada é impresso.
   - O programa calibra a câmera do celular com as próprias fotos e acha a pose de cada tela em cada foto.
   - Um ajuste de feixes (*bundle adjustment*) com todas as fotos juntas dá a posição e a orientação do monitor no referencial do notebook. Ele também estima o tamanho real do monitor: basta informar a diagonal nominal.
   - Em simulação, o erro ficou em ~0,2 mm.
2. **Desenho nas duas telas.**
   - Cada tela recebe a sua projeção off-axis, com o olho levado para o referencial dela.
   - A ordem de pintura é a mesma para as duas, para a oclusão concordar na junção.
   - Cada tela só mostra o que está atrás do seu próprio plano, como uma janela de verdade.
3. **Correção de guinada.** Ao olhar para o monitor do lado, a cabeça gira e a distância entre as íris encolhe na imagem. Sem correção, isso faz a distância estimada errar de 5 a 12 cm. A rotação da cabeça, que o MediaPipe já calcula, corrige isso.

**Como rodar** (passo a passo completo em [`docs/TESTE_AP2.md`](docs/TESTE_AP2.md)):

```bash
cd head_coupled
python testar_monitores.py              # 1. confere os dois monitores (Win+P > Estender)
python calibrar_telas.py mostrar        # 2. padrões nas telas; tire as fotos com o celular
python calibrar_telas.py calcular       # 3. fotos em head_coupled/fotos/ -> telas.json
python main.py                          # 4. duas telas (sem telas.json, ou com --uma-tela, é a AP1)
```

O plano e as decisões de projeto estão em [`docs/PLANO_AP2.md`](docs/PLANO_AP2.md).

## Objetivo do artigo

O objetivo final do grupo é o artigo *"Smartphone-Assisted Calibration of Multi-Screen Display Geometry for Head-Coupled Perspective Rendering"* (formato SBrT 2026). A ideia é estender a *head-coupled perspective* de uma tela para **várias telas lado a lado**, o que exige conhecer a posição de cada tela, em milímetros, num referencial comum. Para isso, propomos calibrar tudo automaticamente usando apenas um **smartphone comum**:

- marcadores **ChArUco** exibidos em cada tela, com tamanho físico calculado a partir da densidade de pixels do painel (implementado na AP2);
- um **alinhamento perceptual** (colinearidade de linhas através da junção entre telas) para conferir o resultado: é a cena `alinhamento` do `main.py` (implementada na AP2);
- um **espelho plano** para recuperar telas fora do campo de visão da câmera (fora do escopo da AP2: com duas telas lado a lado, o celular enxerga as duas).
