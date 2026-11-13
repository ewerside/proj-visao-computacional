# Guia para montar os slides da AP2

Para quem vai montar a apresentação sem ter acompanhado o desenvolvimento. O professor pede, nesta ordem: motivação, problema, esforços de desenvolvimento (com as dificuldades), resultados com a comparação de dois métodos, conclusões e trabalhos futuros, e depois a demonstração.

Todas as imagens citadas estão em [`docs/imagens/`](imagens/). O conteúdo técnico vem do [relatório de tecnologia](RELATORIO_TECNOLOGIA.md) e do artigo em `artigo/`.

## Regras gerais

- **10 slides de conteúdo**, para cerca de 10 minutos, mais a demonstração.
- Uma ideia por slide. Frase curta no título, imagem grande, pouco texto.
- Fundo escuro combina com as imagens do projeto (as cenas têm fundo preto).
- Números sempre com unidade e com o que foi medido: "0,4 mm de variação entre subconjuntos de fotos", não "erro de 0,4 mm".
- Nada de espelho, alinhamento por teclado ou "várias telas": isso não foi feito. O projeto calibra **duas** telas.
- **Reserve um slide inteiro para o vídeo** (slide 8). O vídeo será gravado depois; deixe o espaço pronto.

## Roteiro

### Slide 1: título
- **Título:** Parallax: a tela como janela 3D, em duas telas
- **Subtítulo:** Calibração da geometria de duas telas com fotos de celular
- **Rodapé:** Visão Computacional (IBM3131), Ibmec, Prof. Rigel Fernandes. Ewerton Arrais, Miguel Veiga e Emilly Fernandes.
- **Imagem:** `menu/menu_inicio.png` ou `cenas/duas_telas_planeta_tipico.png`.

### Slide 2: motivação
- **Mensagem:** uma tela comum mostra sempre a mesma imagem, não importa de onde você olha. Se a imagem acompanhar a cabeça, a tela vira uma janela.
- **Imagem:** as três vistas da mesma cena lado a lado: `cenas/uma_tela_cubos_esquerda.png`, `..._centro.png`, `..._direita.png`.
- **Falar:** só com a webcam do notebook, sem óculos e sem equipamento especial.

### Slide 3: o problema
- **Mensagem:** com duas telas, o programa precisa saber onde uma está em relação à outra, com precisão de milímetros. Poucos milímetros de erro viram um degrau na junção.
- **Imagem:** `montagem/duas_telas_com_qr_code.jpg` (as duas telas na mesa).
- **Falar:** medir com trena é impreciso e trabalhoso; o objetivo é descobrir a posição com o celular que todo mundo tem.

### Slide 4: como funciona, em uma figura
- **Mensagem:** dois momentos. Uma vez: calibrar. O tempo todo: rastrear o olho e desenhar.
- **Imagem:** refazer o diagrama do artigo (Fig. 1) com oito caixas: tabuleiro nas telas → fotos do celular → cantos e calibração da câmera → posição por foto → ajuste de feixes → arquivo de calibração → webcam e posição do olho → projeção nas duas telas.
- **Falar:** as próprias telas são o padrão de calibração; nada é impresso.

### Slide 5: desenvolvimento, parte 1 (rastreamento e desenho)
- **Mensagem:** da íris até o pixel.
- **Tópicos curtos:**
  - MediaPipe acha as íris; a distância entre elas dá a distância da cabeça.
  - Filtro One Euro tira o tremor sem atrasar.
  - Cada ponto é desenhado onde a reta olho–ponto fura a tela.
- **Dificuldade para contar:** ao virar a cabeça para o monitor, as íris parecem mais próximas e o programa achava que a pessoa tinha se afastado (15% de erro a 30°). Solução: usar a rotação da cabeça para corrigir.

### Slide 6: desenvolvimento, parte 2 (calibração pelo celular)
- **Mensagem:** 12 fotos, alguns segundos de cálculo.
- **Imagens:** `calibracao_cantos/cantos_detectados_foto_01.png` e `celular/pagina_fotografando.jpg` lado a lado.
- **Dificuldades para contar** (escolher duas):
  - A escala de 125% do Windows deformava o tabuleiro: foi preciso controlar o DPI de cada monitor.
  - O tamanho real do monitor não era conhecido: o ajuste de feixes passou a estimá-lo.
  - O celular não conseguia abrir a página do notebook pelo roteador do próprio celular: a solução foi um túnel pela internet.
  - As primeiras fotos, tiradas todas do mesmo lugar, deram uma calibração ruim: a página agora orienta de onde tirar cada foto.

### Slide 7: resultados, a comparação de dois métodos
- **Mensagem:** juntar todas as fotos numa otimização só (ajuste de feixes) é seis vezes mais estável do que calcular foto a foto e tirar a média.
- **Imagem:** `graficos/repetibilidade_fotos_reais.png`.
- **Números para destacar:** 2,5 mm (PnP + média) contra 0,4 mm (ajuste de feixes com tamanho), em 12 fotos reais.
- **Falar:** em simulação, onde se conhece a resposta certa, o erro máximo caiu de 1,0 mm para 0,2 mm (`graficos/erro_simulado_por_fotos.png`, se couber). O ajuste também descobriu que o monitor era de 23 pol, não de 24 como tinha sido informado, e o valor bateu com o que o próprio monitor informa ao Windows.

### Slide 8: VÍDEO (espaço reservado)
- **Deixar o slide inteiro para o vídeo**, em tela cheia, sem texto por cima. Título pequeno: "Demonstração".
- O vídeo será gravado pelo Ewerton e inserido depois. Enquanto não chega, pôr uma imagem de espera: `cenas/duas_telas_trem_tipico.png`.
- Proporção 16:9. Se o programa de slides permitir, marcar para iniciar ao clicar.

### Slide 9: o programa
- **Mensagem:** tudo pelo menu, sem linha de comando.
- **Imagens:** `menu/menu_inicio.png`, `menu/menu_uma.png`, `menu/menu_duas.png` (escolher duas).
- **Falar:** quatro cenas de uma tela, com 3D anáglifo opcional; duas cenas de duas telas; calibração guiada pelo celular.

### Slide 10: conclusões e trabalhos futuros
- **Conclusões:**
  - Duas telas calibradas só com um celular comum, em cerca de três minutos.
  - O ajuste de feixes deu 0,4 mm de variação nas fotos reais.
  - Sistema completo rodando num notebook com a webcam embutida.
- **Limitações, ditas com clareza:** a calibração não foi comparada com trena; a correção de guinada foi conferida em simulação, não medida em rosto real.
- **Trabalhos futuros:** comparar com medidas físicas, medir a correção de guinada em pessoas, mais de duas telas, telas fora da vista do celular.

## A demonstração ao vivo (3 a 5 minutos)

1. Antes de entrar: monitor ligado em **Estender** (Win+P), notebook na tomada, celular com internet.
2. Abrir `Parallax.bat`. Se a posição das telas mudou desde a última calibração, **Calibrar telas** de novo (cerca de três minutos; ensaiar antes).
3. **Uma tela → Cubos:** mexer a cabeça para os lados e para perto. É a cena mais fácil de entender.
4. **Uma tela → Corredor:** mostra profundidade.
5. **Duas telas → Trem:** o trem passa de uma tela para a outra.
6. **Duas telas → Planeta:** a esfera e os anéis continuam de uma tela para a outra.
7. Se houver óculos vermelho-ciano: **Uma tela → Asteroides** com o anáglifo ligado.

**Plano B:** se o monitor ou a calibração falharem, mostrar só **Uma tela** e o vídeo do slide 8.

## Perguntas prováveis e respostas curtas

| Pergunta | Resposta |
|---|---|
| Como o programa sabe a distância da cabeça? | Pela distância entre as íris na imagem: quanto mais longe, mais próximas elas aparecem. Assume 64 mm entre as pupilas. |
| De onde vem a medida em milímetros na calibração? | Do tamanho da tela do notebook, que é conhecido. O do monitor é estimado pelas fotos. |
| Por que ChArUco? | Os marcadores têm número, então o programa sabe de qual tela é cada canto, mesmo com parte do tabuleiro escondida. |
| O que é o ajuste de feixes? | Uma otimização que acha a posição do monitor, a de cada foto e a lente do celular que melhor explicam todos os cantos de todas as fotos ao mesmo tempo. |
| Quais são os dois métodos comparados? | Calcular a posição foto a foto e tirar a média robusta, contra o ajuste de feixes. |
| O que é de biblioteca e o que é do grupo? | Biblioteca: detecção dos pontos do rosto, detecção dos marcadores, calibração de câmera e o otimizador. Do grupo: posição do olho, correção de guinada, projeção e desenho, cenas, ajuste de feixes, simulador, página do celular e menu. |
| Qual a limitação principal? | Não comparamos a calibração com uma medida física; medimos repetibilidade. |
| Precisa de óculos? | Não. O anáglifo é um extra, só no modo de uma tela. |

## Divisão sugerida entre três pessoas

- **Pessoa 1:** slides 1 a 4 (motivação, problema, visão geral).
- **Pessoa 2:** slides 5 e 6 (desenvolvimento e dificuldades).
- **Pessoa 3:** slides 7 a 10 e a demonstração.

A nota é individual e depende das respostas. Vale cada um ler o relatório de tecnologia inteiro, não só a sua parte.
