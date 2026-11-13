# Parallax — Head-Coupled Perspective em duas telas

Projeto da disciplina **Visão Computacional (IBM3131)** do **Ibmec Barra**, ministrada pelo professor **Rigel Fernandes**.

**Integrantes do grupo:** Ewerton Arrais, Miguel Veiga e Emilly Fernandes.

**Artigo:** *Smartphone-Assisted Calibration of Multi-Screen Display Geometry for Head-Coupled Perspective Rendering* (modelo SBrT 2027).

---

![Menu do Parallax](docs/imagens/menu/menu_inicio.png)

## Como usar

Dois cliques em **`Parallax.bat`**, na raiz do repositório (Windows). Tudo é feito pelo menu, com o mouse:

| Botão | O que faz |
|---|---|
| **Uma tela** | Quatro cenas no notebook: Cubos, Corredor, Vila e Asteroides. Uma chave liga o 3D anáglifo (óculos vermelho-ciano), que só existe com uma tela e sempre começa com a menor separação entre as imagens; `[` e `]` ajustam. |
| **Duas telas** | Trem e Planeta, o mesmo mundo visto pelo notebook e pelo monitor. Só abre depois da calibração e com o monitor ligado. |
| **Calibrar telas** | Mostra os padrões nas duas telas e um QR code. O celular abre uma página, tira as fotos e manda direto; a página confere cada foto, mostra o progresso e, no fim, a posição das telas. |
| **Configurações** | Medidas da tela do notebook, diagonal do monitor, conexão do celular e calibração da webcam. O padrão é o notebook do projeto (tela de 15,6 pol); só mude se o seu equipamento for outro. |

Dentro de uma cena: `Esc` volta ao menu, `N` troca de cena, `Espaço` congela o olho, `D` mostra os detalhes (posição do olho, fps).

Na primeira vez, prepare o ambiente (Python 3.12 ou mais novo):

```bash
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## O que é o projeto

Usando apenas a **webcam** do notebook, o programa acompanha a posição dos olhos de quem assiste e **muda a perspectiva da imagem de acordo com a posição da cabeça**. A tela deixa de parecer uma imagem plana e passa a parecer uma *janela* para um espaço 3D. Essa técnica é conhecida como *head-coupled perspective* ou *fish tank VR*.

O projeto tem duas partes:

- **AP1:** uma tela só, a do notebook.
- **AP2:** o notebook e um monitor externo, lado a lado e em qualquer ângulo, viram duas janelas para o mesmo mundo 3D. Para isso o programa precisa saber, em milímetros, onde o monitor está em relação ao notebook. Essa posição é calculada a partir de **fotos tiradas com um celular comum**.

## Como funciona

### Rastreamento e desenho (AP1)

1. **Detecção dos olhos.** O MediaPipe Face Landmarker encontra 478 pontos do rosto em cada quadro da webcam. Usamos o centro das duas íris.
2. **Posição 3D da cabeça.** Com o modelo de câmera *pinhole*, a distância entre as íris em pixels dá a distância da cabeça à câmera, e daí saem X, Y e Z em metros. A distância focal da webcam é medida uma vez (`calibrate.py`).
3. **Suavização.** Um filtro One Euro remove o tremor com a cabeça parada e deixa passar o movimento rápido.
4. **Projeção off-axis.** A tela é tratada como um retângulo físico, com tamanho em metros. Cada ponto 3D da cena é projetado nesse retângulo a partir da posição do olho.

### Duas telas (AP2)

1. **Padrões nas telas.** Cada tela mostra um tabuleiro ChArUco com marcadores diferentes (`calibrar_telas.py mostrar`). O tamanho físico dos quadrados sai do tamanho da tela e da resolução, então nada é impresso.
2. **Fotos.** Com o app de câmera normal, tiram-se de 10 a 15 fotos das duas telas, de lugares diferentes.
3. **Calibração** (`calibrar_telas.py calcular`):
   - detecta os cantos dos tabuleiros em cada foto;
   - calibra a câmera do celular com as próprias fotos;
   - acha a pose de cada tela em cada foto (PnP) e combina as fotos por uma média robusta;
   - refina tudo junto com um **ajuste de feixes** (*bundle adjustment*), que também estima o tamanho real do monitor;
   - grava o `telas.json` com a pose do monitor no referencial do notebook.
4. **Desenho nas duas telas** (`main.py`). Cada tela recebe a sua projeção off-axis. A ordem de pintura é calculada uma vez para o mundo todo, e cada tela só mostra o que está atrás do seu próprio plano.
5. **Correção de guinada.** Ao olhar para o monitor do lado, a cabeça gira e a distância entre as íris encolhe na imagem, o que faria a distância estimada crescer. A rotação da cabeça dada pelo MediaPipe corrige esse erro.

## Software utilizado e implementações do grupo

### Software de terceiros

| Software | Versão testada | Para que é usado |
|---|---|---|
| Python | 3.14 | linguagem |
| OpenCV (`opencv-contrib-python`) | 5.0 | captura da webcam, janelas, desenho 2D, detecção dos marcadores ArUco/ChArUco, `calibrateCamera` e `solvePnP` |
| MediaPipe (Face Landmarker, `face_landmarker.task`) | 1.2 | 478 pontos do rosto, centro das íris e rotação da cabeça |
| Pillow | 13.0 | texto com fonte TrueType no menu do Parallax |
| NumPy | 2.5 | geometria e álgebra linear |
| SciPy | 1.18 | `least_squares` (otimizador do ajuste de feixes) e rotações |

Nenhum código de terceiros foi copiado para o repositório. O único arquivo de terceiros é o modelo `face_landmarker.task`, do MediaPipe.

### O que o grupo implementou (customizações)

As bibliotecas acima entregam peças soltas: pontos do rosto, cantos de marcadores, um otimizador genérico. Tudo o que transforma essas peças no sistema foi escrito pelo grupo, em Python, na pasta `head_coupled/`.

| Módulo | O que o grupo implementou | Por que foi preciso |
|---|---|---|
| `tracking.py` | Posição 3D da cabeça pela distância entre as íris; correção de guinada (`fator_escorco`) | O MediaPipe devolve pontos na imagem, não a posição do olho em metros. Sem a correção, virar a cabeça 30° faz a distância errar ~15% |
| `calibrate.py` | Calibração da distância focal da webcam com a própria pessoa a uma distância conhecida | Evita tabuleiro impresso para a webcam |
| `filters.py` | Filtro One Euro | Implementação própria do filtro publicado; não usamos pacote pronto |
| `scene.py`, `telas.py` | Projeção off-axis, recorte pelo plano da tela, ordenação e desenho em lote das cenas 3D; cenas Cubos, Corredor, Vila e Asteroides | O OpenCV só desenha em 2D. Não usamos OpenGL nem motor gráfico |
| `parallax.py` | Menu do programa: seletores de cenas com prévia, calibração com status, configurações | Uso na apresentação sem linha de comando |
| `sala.py`, `janelas.py`, `planeta.py` | Cenas de mundo compartilhado: Trem (maquete com trem que passa de uma tela para a outra), Planeta (gigante gasoso com anéis e luas atrás da junção), `sala` e `alinhamento` | Mostram o mesmo mundo pelas duas telas; a `alinhamento` serve para conferir a calibração a olho |
| `monitores.py` | Lista de monitores, escala de tela (DPI por monitor) e janela em tela cheia em cada monitor, via `ctypes` | Com escala de 125% ou 150% do Windows as janelas do OpenCV saíam com tamanho errado |
| `padroes.py` | Tabuleiros ChArUco desenhados pixel a pixel na tela, com IDs diferentes por tela e tamanho físico derivado do painel | O padrão de calibração é a própria tela, não um papel impresso |
| `detectar.py` | Detecção dos cantos nas fotos de 12 MP e descarte de detecções inconsistentes | Fotos de tela têm moiré, reflexo e marcadores parciais |
| `calibracao.py` | Média robusta de poses e **ajuste de feixes** próprio (jacobiano esparso, perda de Huber, estimativa do tamanho do monitor e da incerteza) | O OpenCV calibra uma câmera, mas não impõe que as duas telas estão paradas uma em relação à outra |
| `calibrar_telas.py` | Fluxo completo `mostrar` / `calcular` / `manual`, avisos de qualidade e vista de cima (`dbg/planta.png`) | Uso em poucos minutos, sem app no celular |
| `celular.py` | Servidor local e página web para o celular: QR code na tela, foto pela câmera nativa, conferência imediata dos cantos, barra de progresso, cálculo pelo celular e prévia da posição das telas; túnel `ssh` para quando os aparelhos não se enxergam na rede | Elimina a cópia manual das fotos e avisa na hora se uma foto não serve |
| `simular.py` | Simulador de fotos de celular (desfoque, ruído, moiré, reflexo, JPEG) com resposta conhecida | Permite medir o erro da calibração sem hardware |
| `avaliar.py` | Avaliação quantitativa: compara os estimadores em fotos simuladas e em fotos reais | É a comparação de métodos do artigo |
| `anaglyph.py` | Modo anáglifo vermelho-ciano (bônus) | Estereoscopia com óculos de papelão |
| `testes/` | Testes automáticos sem hardware (webcam, monitores e fotos simulados) | Garante que a AP1 continua idêntica e que a calibração acerta |

## Avaliação quantitativa

O script `avaliar.py` compara três estimadores da pose do monitor: **PnP+média** (PnP por foto e média robusta), **BA** (ajuste de feixes) e **BA+tam** (ajuste de feixes estimando também o tamanho do monitor).

```bash
python avaliar.py simulado      # erro contra a verdade em fotos sintéticas
python avaliar.py real          # repetibilidade nas fotos reais em head_coupled/fotos/
```

**Fotos simuladas, 10 fotos, pior quina do monitor, mediana (máximo):**

| Fotos | PnP+média | BA | BA+tam |
|---|---|---|---|
| Limpas | 0,02 (0,04) mm | 0,01 (0,04) mm | — |
| Típicas | 0,21 (0,53) mm | 0,11 (0,16) mm | 0,23 (0,32) mm |
| Ruins | 0,47 (1,01) mm | 0,16 (0,21) mm | 0,22 (0,26) mm |

**Fotos reais (duas sessões de 12 fotos de um Pixel 7 Pro, enviadas pela página do celular; 30 subconjuntos de 10 fotos):** quanto as quinas do monitor mudam de um subconjunto para outro, em desvio padrão (máximo).

| Estimador | Sessão 1: monitor de 23 pol | Sessão 2: monitor de 21 pol |
|---|---|---|
| PnP+média | 2,5 mm (5,5) | 5,0 mm (9,0) |
| BA | 0,7 mm (2,3) | 1,8 mm (5,1) |
| BA+tam | 0,4 mm (1,2) | 1,1 mm (2,9) |

![Repetibilidade nas fotos reais](docs/imagens/graficos/repetibilidade_fotos_reais.png)

Nas duas sessões o ajuste de feixes que estima o tamanho é de quatro a seis vezes mais estável que a média por foto. Na sessão 1, o tamanho estimado do monitor (51,0 × 28,7 cm, 23,0 pol) coincide com o que o próprio monitor informa ao Windows (509 × 286 mm). Erro de reprojeção: 1,13 px na sessão 1 e 2,66 px na sessão 2, cujas fotos foram tiradas com uma lente mais aberta. As fotos da sessão 2 estão em [`docs/imagens/calibracao_fotos/`](docs/imagens/calibracao_fotos/).

## Linha de comando (opcional)

O menu cobre tudo. Os comandos abaixo são os mesmos programas, para quem quiser rodar por partes. Desenvolvido e testado em **Windows**; o passo a passo do zero está em [`docs/TESTE_AP2.md`](docs/TESTE_AP2.md).

```bash
pip install -r requirements.txt     # NAO instale opencv-python junto (ver requirements.txt)
cd head_coupled

python testes/rodar_testes.py       # testes automaticos, sem hardware

# Uma tela (AP1)
python calibrate.py                 # calibra a webcam uma vez
python main.py --uma-tela

# Duas telas (AP2)
python testar_monitores.py          # confere os dois monitores (Win+P > Estender)
python calibrar_telas.py mostrar    # padroes nas telas; tire as fotos com o celular
python calibrar_telas.py calcular   # fotos em head_coupled/fotos/ -> telas.json
python main.py --direto                      # duas telas
```

### Fotos direto do celular (sem copiar arquivos)

```bash
python calibrar_telas.py celular
```

As telas mostram os padrões e, no notebook, um **QR code**. O celular lê o QR e abre uma página servida pelo próprio notebook. Cada toque em "Tirar foto" abre a câmera do celular; a foto sobe em resolução total e a página responde na hora quantos cantos foram achados em cada tela e de onde tirar a próxima. O botão "Calcular" grava o `telas.json`. Não instala nada no celular.

- Celular e notebook precisam estar na **mesma rede**, e a rede precisa deixar um aparelho falar com o outro.
- **Sem a mesma rede:** `python calibrar_telas.py celular --tunel`. O notebook abre um túnel de saída por `ssh` até um serviço público (serveo.net) e o QR passa a apontar para um endereço `https` que o celular acessa pela internet (4G/5G). Serve para Wi‑Fi que isola os aparelhos e para o roteador do próprio celular. As fotos passam por esse serviço, e o endereço fica público enquanto o comando roda, protegido pelo código do QR.
- Na primeira vez o Windows pergunta se o Python pode receber conexões: permita.
- O servidor só existe enquanto o comando roda e só aceita pedidos com o código aleatório do QR. As fotos ficam em `head_coupled/fotos_celular/`.

Teclas principais do `main.py`: `n` troca de cena, `d` painel de debug (posição do olho, fps), `y` liga/desliga a correção de guinada, `ESPAÇO` congela o olho, `f` liga/desliga o filtro, `3` anáglifo, `q` sai. A lista completa está no cabeçalho do `main.py`.

## Estrutura

| Arquivo | Função |
|---|---|
| `parallax.py` (e `Parallax.bat`) | Menu do programa |
| `main.py` | Laço principal: webcam → posição da cabeça → desenho em uma ou duas telas |
| `tracking.py`, `filters.py`, `calibrate.py` | Rastreamento dos olhos, filtro e calibração da webcam |
| `scene.py`, `sala.py`, `janelas.py`, `planeta.py`, `anaglyph.py` | Cenas e projeção |
| `telas.py`, `monitores.py`, `testar_monitores.py` | Pose de cada tela, monitores do Windows e teste das janelas |
| `calibrar_telas.py`, `padroes.py`, `detectar.py`, `calibracao.py` | Calibração das duas telas pelas fotos do celular |
| `simular.py`, `avaliar.py`, `teste_guinada.py` | Simulador de fotos, avaliação quantitativa e teste da correção de guinada |
| `config.py` | Medidas físicas e parâmetros |
| `testes/` | Testes automáticos |
| `docs/` | Relatório de tecnologia, guia de teste, decisões de projeto e imagens |
| `artigo/` | Fonte LaTeX do artigo (modelo SBrT) |

## Documentos

- [`docs/RELATORIO_TECNOLOGIA.md`](docs/RELATORIO_TECNOLOGIA.md): todas as técnicas de visão computacional e de matemática do projeto, do rastreamento do rosto à exibição em duas telas, e as referências realmente usadas.
- [`docs/imagens/`](docs/imagens/): fotos, renders, telas e gráficos.
- [`artigo/`](artigo/): o artigo.

## Limitações e trabalhos futuros

- A calibração trata duas telas; o desenho já aceita mais.
- A régua do sistema é o tamanho da tela do notebook, informado no `config.py`.
- Um espelho plano, para telas fora do campo de visão do celular, e um ajuste fino manual pela junção ficaram fora do escopo.
