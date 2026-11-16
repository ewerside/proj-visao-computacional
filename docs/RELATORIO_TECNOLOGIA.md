# Relatório de tecnologia do Parallax

Tudo o que o projeto usa de visão computacional e de matemática, na ordem em que os dados passam pelo sistema: do rosto na webcam até a imagem nas duas telas. Cada técnica aparece três vezes: em uma frase, explicada, e em detalhe, com o lugar no código.

No fim estão as referências que o projeto realmente usa, dizendo como cada uma entra, e as que estavam na bibliografia antiga e não foram usadas.

## O sistema em uma página

O programa faz duas coisas diferentes, em momentos diferentes.

**Uma vez, na calibração:** descobre onde o monitor externo está em relação ao notebook.

1. Cada tela mostra um tabuleiro ChArUco.
2. O celular tira cerca de 12 fotos das duas telas.
3. O programa acha os cantos dos tabuleiros em cada foto.
4. Com esses cantos, calibra a câmera do celular e calcula a posição de cada tela em cada foto.
5. Um ajuste de feixes junta todas as fotos e devolve uma única posição do monitor, com o tamanho real dele.

**O tempo todo, na exibição:** desenha a cena do ponto de vista de quem olha.

1. A webcam filma o rosto e o MediaPipe acha as íris.
2. A distância entre as íris na imagem dá a posição 3D da cabeça.
3. Um filtro tira o tremor.
4. Cada ponto da cena é projetado na tela pela reta que vai do olho até ele.
5. Com duas telas, a conta é a mesma, feita no referencial de cada tela.

---

## Parte 1: rastreamento do rosto

### 1.1 Pontos do rosto e íris

**Em uma frase:** uma rede neural acha 478 pontos do rosto em cada quadro da webcam, entre eles o centro de cada íris.

**Explicando:** não detectamos o olho com processamento de imagem clássico. Usamos o Face Landmarker do MediaPipe, um modelo pronto que devolve a malha do rosto. Dos 478 pontos, usamos dois, os centros das íris, e a matriz de rotação da cabeça que o modelo também estima.

**Em detalhe:**
- Os pontos 468 e 473 são os centros das íris (`tracking.IRIS_L` e `IRIS_R`).
- O modelo vem do arquivo `face_landmarker.task`, de terceiros.
- O quadro é espelhado antes (`FLIP_FRAME`), para a imagem reagir como um espelho.
- Código: `tracking.py`, funções `make_landmarker` e `find_landmarks_pose`.

### 1.2 Posição 3D da cabeça pelo modelo pinhole

**Em uma frase:** quanto mais longe a pessoa está, mais perto uma íris fica da outra na imagem, e essa relação dá a distância.

**Explicando:** a distância real entre as pupilas de um adulto varia pouco; assumimos 64 mm. Uma câmera ideal (modelo *pinhole*) projeta um segmento de tamanho conhecido com um tamanho em pixels inversamente proporcional à distância. Medindo os pixels, sai a distância. Com a distância, a posição do ponto na imagem dá X e Y.

**Em detalhe:**

```
Z = f · IPD / ipd_px
X = (u − cx) · Z / f
Y = −(v − cy) · Z / f
```

- `f` é a distância focal da webcam em pixels, `ipd_px` a distância entre as íris em pixels, `(u, v)` o ponto médio entre elas e `(cx, cy)` o centro da imagem.
- O ponto calculado é o meio entre os olhos, o "olho ciclópico", que é o centro de projeção certo para uma imagem só.
- O resultado está no referencial da câmera. Para o referencial da tela soma-se o deslocamento da lente em relação ao centro da tela (`eye_in_screen_coords`).
- Código: `tracking.head_position`.

### 1.3 Calibração da distância focal da webcam

**Em uma frase:** a pessoa senta a uma distância conhecida e o programa calcula a "lente" da webcam.

**Explicando:** é a mesma fórmula de cima, resolvida para `f`. A 60 cm, mede-se `ipd_px` em 90 quadros e usa-se a mediana, que não é afetada por quadros em que o ponto pulou.

**Em detalhe:** `f = ipd_px · D / IPD`. Um efeito útil: como o mesmo IPD entra na calibração e no uso, ele se cancela na conta do Z. Errar o IPD da pessoa não muda a distância estimada, só o ganho lateral. Código: `calibrate.py`.

### 1.4 Correção de guinada

**Em uma frase:** quando a pessoa vira a cabeça para olhar o monitor do lado, as íris parecem mais próximas, e o programa desconta isso.

**Explicando:** virar a cabeça encurta o segmento entre os olhos visto pela câmera, como uma régua vista de lado. Sem correção, o programa acharia que a pessoa se afastou: a 30° o erro é de cerca de 15%, 9 cm a 60 cm. Com uma tela isso quase não acontece. Com duas, olhar para o monitor é exatamente virar a cabeça.

**Em detalhe:**
- A matriz de rotação da cabeça do MediaPipe dá a direção 3D da reta que liga os olhos, o `eixo`.
- O fator de encurtamento é `k = | eixo_xy − eixo_z · n |`, onde `n` é o ponto médio das íris na imagem, em coordenadas normalizadas.
- Para uma guinada pura `ψ` com a cabeça no eixo da câmera, `k = cos ψ`. Com a cabeça fora do eixo por um ângulo `φ`, `k = cos(ψ + φ) / cos φ`.
- A posição inteira é multiplicada por `k`. Para o Z a fórmula é exata, conferida em 2000 poses no teste `teste_guinada_formula.py`.
- Só a rotação do MediaPipe é usada. A translação dele supõe outra lente e sairia errada.
- Código: `tracking.eixo_interocular` e `tracking.fator_escorco`.

### 1.5 Filtro One Euro

**Em uma frase:** um filtro que tira o tremor quando a cabeça está parada e quase não atrasa quando ela se move.

**Explicando:** os pontos do rosto tremem um pouco a cada quadro, e a cena tremeria junto. Um filtro passa-baixa comum resolveria o tremor mas deixaria a imagem atrasada. O One Euro muda a força do filtro conforme a velocidade: devagar filtra muito, rápido filtra pouco.

**Em detalhe:** é um passa-baixa exponencial cuja frequência de corte é `fc = min_cutoff + β · |velocidade|`, com a velocidade também filtrada. Usamos `min_cutoff = 1,0`, `β = 0,007`. Há um filtro para a posição (três eixos) e outros para a inclinação e para o eixo dos olhos. A implementação é nossa: `filters.py`.

---

## Parte 2: desenho com perspectiva acoplada à cabeça

### 2.1 Projeção off-axis

**Em uma frase:** cada ponto da cena é desenhado onde a reta entre o olho e ele fura a tela.

**Explicando:** a tela é tratada como uma janela de verdade, com tamanho em metros. Se o olho se move, a reta até cada ponto muda e o ponto aparece em outro lugar da tela. Objetos mais fundos se deslocam mais que os próximos. Essa diferença é a paralaxe de movimento, e é ela que dá a sensação de profundidade.

**Em detalhe:** com a tela no plano `z = 0` e o olho em `(ex, ey, ez)`:

```
t = ez / (ez − Pz)
x_tela = ex + t · (Px − ex)
y_tela = ey + t · (Py − ey)
```

- É a interseção de uma reta com um plano. O resultado é o mesmo do frustum assimétrico da computação gráfica, sem matriz de projeção.
- Um ponto com `0 < Pz < ez` está entre a tela e o rosto: `t > 1` e o objeto "sai" da tela.
- A boca de toda cena de caixa tem o tamanho exato da tela, então projeta em si mesma para qualquer posição do olho. A moldura física vira a moldura da janela.
- Código: `scene.project`.

### 2.2 Algoritmo do pintor, descarte de faces e sombreamento

**Em uma frase:** as faces são desenhadas da mais distante para a mais próxima, pulando as que estão de costas.

**Explicando:** o OpenCV só desenha em 2D, sem buffer de profundidade. Para a oclusão sair certa, ordenamos os polígonos pela distância ao olho e pintamos de trás para a frente. Faces de um sólido que apontam para longe do olho não são desenhadas.

**Em detalhe:**
- Ordenação pela distância média dos vértices ao olho, não pelo `z`: com o olho fora do eixo as duas discordam.
- Descarte de face traseira: `n · (olho − centro) ≤ 0`.
- Sombreamento plano de Lambert: `cor · (0,34 + 0,66 · max(0, n · luz))`, uma multiplicação por face.
- Objetos longos são divididos em pedaços para a ordenação funcionar ao longo deles.
- Código: `scene.order_faces`, `scene.desenhar`, `scene.sombrear`.

### 2.3 Estereoscopia em anáglifo

**Em uma frase:** a cena é desenhada duas vezes, uma para cada olho, e as duas imagens são misturadas em vermelho e ciano.

**Explicando:** com óculos vermelho-ciano, cada olho vê uma das imagens. A diferença entre elas (a disparidade) dá profundidade mesmo com a cabeça parada. No Parallax o anáglifo só existe com uma tela e começa sempre com a menor separação, para não cansar a vista.

**Em detalhe:**
- Os dois olhos ficam a `± IPD/2 · escala` do olho ciclópico, ao longo do eixo real da cabeça.
- A ordenação das faces é calculada uma vez e serve aos dois olhos. Se cada olho ordenasse por conta própria, as imagens poderiam discordar sobre o que está na frente.
- Três modos de composição: `gray`, `true` e `dubois`. O último usa matrizes otimizadas por mínimos quadrados para os filtros dos óculos.
- A paleta é trocada por tons neutros, porque cor saturada aparece em um olho só.
- A escala automática limita a disparidade a 1° de ângulo visual.
- Código: `anaglyph.py`, `scene.stereo_eyes`, `scene.escala_confortavel`.

---

## Parte 3: calibração das duas telas pelo celular

### 3.1 Tabuleiro ChArUco mostrado na própria tela

**Em uma frase:** cada tela mostra um xadrez com marcadores, e o tamanho de cada quadrado em milímetros é conhecido.

**Explicando:** calibrar exige um padrão de medidas conhecidas. Em vez de imprimir, usamos a tela. Sabendo o tamanho da tela em metros e a resolução, sabe-se o tamanho de um pixel, e portanto de cada quadrado. O ChArUco junta duas coisas: os cantos do xadrez, que são localizados com precisão de fração de pixel, e marcadores ArUco dentro dos quadrados brancos, cada um com um número, que dizem qual canto é qual mesmo com parte do tabuleiro escondida.

**Em detalhe:**
- Tabuleiro 13×7, dicionário `DICT_5X5_250`. Marcadores 0 a 44 no notebook e 45 a 89 no monitor: o número diz de qual tela é o canto.
- 72 cantos internos por tela.
- O tabuleiro é desenhado pixel a pixel. O programa se declara ciente do DPI por monitor no Windows, senão a escala de 125% reamostraria a imagem.
- A régua do sistema é o tamanho da tela do notebook. O do monitor entra só como chute inicial.
- Código: `padroes.py`, `monitores.py`.

### 3.2 Detecção dos cantos nas fotos

**Em uma frase:** o programa acha os marcadores em cada foto e, a partir deles, os cantos do xadrez.

**Explicando:** primeiro acha quadriláteros escuros e lê o código de cada um. Depois interpola onde os cantos do xadrez devem estar e refina cada um até fração de pixel. Por fim joga fora cantos que não combinam com os outros.

**Em detalhe:**
- Detector ArUco do OpenCV com limiar adaptativo em várias janelas (3 a 53 px), ajustado para fotos de 12 MP.
- Refinamento subpixel dos cantos.
- Filtro de consistência: ajusta-se uma homografia tela → foto com RANSAC e descartam-se os cantos fora dela.
- Uma tela só conta numa foto se tiver pelo menos 12 cantos.
- A orientação EXIF é ignorada, para todas as fotos ficarem na orientação do sensor.
- Código: `detectar.py`.

### 3.3 Calibração da câmera do celular

**Em uma frase:** as mesmas fotos servem para descobrir a lente do celular.

**Explicando:** não se sabe a distância focal nem a distorção da câmera do celular. O método de Zhang descobre isso a partir de várias vistas de um padrão plano. Cada par (foto, tela) é uma vista.

**Em detalhe:**
- `cv2.calibrateCamera`, com cada (foto, tela) como vista separada.
- Estimam-se `fx`, `fy`, `cx`, `cy` e duas distorções radiais, `k1` e `k2`. A distorção tangencial e `k3` ficam em zero.
- Código: `calibracao.calibrar_intrinsecos`.

### 3.4 Pose de cada tela em cada foto (PnP)

**Em uma frase:** sabendo onde os cantos estão na tela e na foto, calcula-se onde a tela estava em relação à câmera.

**Explicando:** é o problema *Perspective-n-Point*. Para um alvo plano existe uma solução fechada específica, a IPPE, que lida com a ambiguidade típica de planos vistos de longe. O resultado é refinado minimizando o erro de reprojeção.

**Em detalhe:** `cv2.solvePnP` com `SOLVEPNP_IPPE`, seguido de `solvePnPRefineLM` (Levenberg–Marquardt). Código: `calibracao.pose_pnp`.

### 3.5 Pose relativa e média robusta (o método de comparação)

**Em uma frase:** em cada foto que mostra as duas telas, a posição de uma em relação à outra não depende de onde o celular estava.

**Explicando:** se a foto dá a pose do notebook e a do monitor em relação à câmera, compondo uma com a inversa da outra a câmera se cancela. Cada foto dá uma estimativa da pose do monitor. Juntamos todas com uma média que ignora as discrepantes. Este é o estimador "PnP + média" das tabelas.

**Em detalhe:**
- `T_notebook←monitor = inv(T_câmera←notebook) · T_câmera←monitor`.
- Rotação: média cordal, a rotação mais próxima da soma das matrizes, por SVD.
- Translação: mediana por coordenada.
- Descarte iterativo: sai a foto cujo ângulo ou distância até a média passa de 3 vezes a mediana.
- Código: `calibracao.poses_relativas`, `media_robusta`.

### 3.6 Ajuste de feixes (o método proposto)

**Em uma frase:** uma única otimização acha a posição do monitor, a de cada foto e a lente do celular que melhor explicam todos os cantos de todas as fotos ao mesmo tempo.

**Explicando:** a média do passo anterior trata as fotos em separado. O ajuste de feixes usa o fato de que as duas telas não se mexeram entre as fotos: existe uma só pose do monitor, e todas as fotos têm de concordar com ela. Ele também estima o tamanho real do monitor, porque fotos de pontos de vista diferentes desfazem a ambiguidade entre "maior e mais longe" e "menor e mais perto".

**Em detalhe:**
- Parâmetros: 6 da lente (`fx, fy, cx, cy, k1, k2`), 6 da pose do monitor, 1 da escala do monitor e 6 por foto.
- Função minimizada: a soma dos erros de reprojeção de todos os cantos.
- `scipy.optimize.least_squares`, método `trf`, com a estrutura esparsa do jacobiano informada.
- Duas etapas: mínimos quadrados puros, depois perda de Huber para diminuir o peso de cantos ruins. Sem a primeira etapa, um chute ruim do tamanho do monitor faz a perda robusta tratar tudo como discrepante.
- A incerteza sai da covariância aproximada `(JᵀJ)⁻¹ · s²`.
- Código: `calibracao.ajuste_feixes`.

### 3.7 Simulador de fotos

**Em uma frase:** um gerador de fotos falsas, com resposta conhecida, para medir o erro da calibração.

**Explicando:** em fotos reais não se sabe a posição verdadeira do monitor. O simulador desenha as duas telas como uma câmera de celular veria e estraga a imagem como a vida real estraga.

**Em detalhe:** projeção com distorção de lente, desfoque, ruído do sensor, moiré, reflexo, compressão JPEG, variação da focal com o foco e fotos tremidas, em três níveis de severidade. Código: `simular.py`.

---

## Parte 4: exibição em duas telas

### 4.1 Mudança de referencial

**Em uma frase:** o mundo é o referencial do notebook, e cada tela enxerga esse mundo do seu próprio ponto de vista.

**Em detalhe:** a calibração dá `x_notebook = R · x_monitor + t`. Para desenhar no monitor, o olho e a cena são levados ao referencial dele, `x_local = Rᵀ · (x − t)`, e a projeção da seção 2.1 é aplicada sem mudança. No notebook `R` é a identidade, e o modo de uma tela continua igual. Código: `telas.py`.

### 4.2 Recorte pelo plano da tela

**Em uma frase:** cada tela mostra só o que está atrás dela, como uma janela.

**Em detalhe:** polígonos que cruzam o plano de uma tela são cortados nesse plano antes de projetar, pelo algoritmo de recorte de polígono por um semiespaço. Sem isso, um objeto na frente do monitor girado apareceria projetado ao contrário. Código: `telas.recortar`.

### 4.3 Uma ordenação para as duas telas

**Em uma frase:** a ordem de pintura é calculada uma vez, no mundo, e vale para as duas telas.

**Em detalhe:** distância e produto escalar não mudam com a troca de referencial. Usando a mesma ordem, a oclusão concorda dos dois lados da junção. Código: `telas.ordenar_mundo`.

### 4.4 Vertical da cena pela gravidade

**Em uma frase:** as cenas de duas telas descobrem onde é "para cima" na mesa de verdade.

**Em detalhe:** a tampa do notebook fica inclinada, então o eixo Y da tela não é a vertical. As bordas de baixo das duas telas são horizontais; o produto vetorial entre elas dá a vertical. O chão das cenas Trem e Planeta usa essa direção. Código: `janelas.base_sala`.

---

## Avaliação

Três estimadores da pose do monitor foram comparados (`avaliar.py`):

- **PnP + média:** seções 3.4 e 3.5.
- **Ajuste de feixes:** seção 3.6, com o tamanho do monitor dado.
- **Ajuste de feixes + tamanho:** seção 3.6, estimando o tamanho.

| Onde | Métrica | PnP + média | Ajuste de feixes | Ajuste + tamanho |
|---|---|---|---|---|
| Simulação, fotos típicas, 10 fotos | pior quina, mediana | 0,21 mm | 0,11 mm | 0,23 mm |
| Simulação, fotos ruins, 10 fotos | pior quina, mediana | 0,47 mm | 0,16 mm | 0,22 mm |
| Fotos reais, sessão 1 (monitor de 23 pol), 30 subconjuntos de 10 | desvio padrão das quinas | 2,5 mm | 0,7 mm | 0,4 mm |
| Fotos reais, sessão 2 (monitor de 21 pol), 30 subconjuntos de 10 | desvio padrão das quinas | 5,0 mm | 1,8 mm | 1,1 mm |

Nas fotos reais não há posição verdadeira para comparar. O que se mede é a repetibilidade: quanto a resposta muda quando se trocam as fotos.

---

## Referências realmente usadas

| Referência | Como entra no projeto |
|---|---|
| Ware, Arthur e Booth, *Fish Tank Virtual Reality*, CHI 1993 | A ideia central: perspectiva acoplada à cabeça num monitor comum. É a motivação do projeto. |
| Kooima, *Generalized Perspective Projection*, 2009 | A projeção off-axis para uma tela em posição arbitrária. Nossa projeção (2.1) é a mesma geometria, escrita como interseção de reta com plano; a extensão para a tela girada (4.1) segue a formulação dele. |
| Zhang, *A Flexible New Technique for Camera Calibration*, TPAMI 2000 | Calibração da câmera do celular com vistas de um padrão plano (3.3). É o método dentro do `cv2.calibrateCamera`. |
| Garrido-Jurado et al., *Automatic generation and detection of highly reliable fiducial markers under occlusion*, Pattern Recognition 2014 | Os marcadores ArUco dos tabuleiros e o detector do OpenCV (3.1 e 3.2). |
| Collins e Bartoli, *Infinitesimal Plane-Based Pose Estimation*, IJCV 2014 | O solver IPPE da pose de alvo plano (3.4), `SOLVEPNP_IPPE`. |
| Triggs, McLauchlan, Hartley e Fitzgibbon, *Bundle Adjustment — A Modern Synthesis*, 2000 | O ajuste de feixes (3.6): formulação, perda robusta e uso da esparsidade. |
| Casiez, Roussel e Vogel, *1€ Filter*, CHI 2012 | O filtro da posição da cabeça (1.5), reimplementado por nós. |
| Grishchenko et al., *Attention Mesh*, 2020 | O modelo de malha facial com íris por trás do MediaPipe Face Landmarker (1.1). |
| Bradski, *The OpenCV Library*, 2000 | A biblioteca de captura, detecção, calibração e desenho. |
| Virtanen et al., *SciPy 1.0*, Nature Methods 2020 | O otimizador do ajuste de feixes. |
| Dubois, *A projection method to generate anaglyph stereo images*, ICASSP 2001 | As matrizes do modo `dubois` do anáglifo (2.3). |

**Usadas como contexto, não como técnica:**

| Referência | Papel |
|---|---|
| Fafard et al., *Calibration Methods for Effective Fish Tank VR in Multi-screen Displays*, CHI EA 2017 | Mostra que calibrar a geometria é o obstáculo das telas múltiplas. É o problema que atacamos. |
| Wagemakers, Fafard e Stavness, *Interactive Visual Calibration of Volumetric Head-Tracked 3D Displays*, CHI 2017 | Calibração visual por padrões que devem parecer contínuos na junção. Inspirou a cena de conferência `alinhamento`, que só mostra; não ajusta nada. |
| Assumpção et al., SBrT 2025, e Saldanha da Gama et al., SBrT 2025 (trabalhos do Ibmec) | Outros sistemas de baixo custo com pontos faciais e câmera comum. Contexto do rastreamento. |

## Referências que estavam na bibliografia e não foram usadas

| Referência | Por que saiu |
|---|---|
| Berral-Soler et al., *DeepArUco++*, 2024 | Detector de marcadores por rede neural. Usamos o detector clássico do OpenCV, que achou 72 de 72 cantos na maioria das fotos reais. |
| Kim, Bong e Jeong, *Enhancing Pose Estimation Using Multiple Graphical Markers...*, 2024 | Fusão de vários marcadores com filtros espacial e temporal. Usamos tabuleiro ChArUco e ajuste de feixes. |
| Zhou et al., *Automatic Calibration of a Multiple-Projector Spherical Fish Tank VR Display*, WACV 2017 | Tela esférica com projetores e câmera já calibrada. Outro tipo de equipamento. |
| Pham et al., *Real-Time 3D Light-Field Viewing with Eye-Tracking on Conventional Displays*, 2025 | Trabalho parecido com a nossa parte de uma tela, mas nenhuma técnica dele foi usada. |
| Sturm e Bonfort, *How to Compute the Pose of an Object Without a Direct View*, ACCV 2006 | Calibração por espelho. A etapa do espelho não foi implementada. |
| García-Ruiz et al., *Fiducial Objects*, 2023; Shao et al., *N-euro Predictor*, 2023; Liu et al., revisão de rastreamento do olhar, 2024 | Estavam no `refs.bib` e nunca foram citadas nem usadas. |

**Técnicas descritas no artigo antigo e que não existem no projeto:** calibração assistida por espelho, alinhamento perceptual ajustado pelo teclado, grafo de poses para mais de duas telas e sessão separada de calibração da câmera do celular.

Os dados bibliográficos acima vêm do `refs.bib` do projeto e do nosso conhecimento dos trabalhos. O conteúdo de cada um não foi relido para este relatório: antes de citar um número de outro artigo, confira no original.
