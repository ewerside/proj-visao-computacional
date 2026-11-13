# Como testar a AP2 (passo a passo)

Este guia leva você do código recém-baixado até a demonstração com as duas telas. Na primeira vez, conte com cerca de 1 hora.

Os passos estão em ordem: cada um confirma uma parte antes da próxima. Se algo falhar, pare e veja a seção [Se algo der errado](#se-algo-der-errado).

> **O que só você pode fazer.** Estes passos precisam de você e do hardware. Nada disso pode ser feito pela nuvem.
> 1. Medir com régua a área acesa da tela do notebook (passo 3).
> 2. Informar a diagonal do monitor externo (passo 7).
> 3. Conferir as janelas no notebook e no monitor (passo 4).
> 4. Fazer o teste de girar a cabeça (passo 6).
> 5. Tirar as fotos com o celular e copiá-las para o PC (passo 8).
> 6. Olhar as duas telas e dizer se a ilusão funciona (passo 9).

Os comandos são para o **PowerShell** do Windows.

---

## 0. Preparar o notebook e baixar o projeto (15 min, só na primeira vez)

### 0.1 Abrir o PowerShell na sua pasta
No Explorador de Arquivos, entre na pasta que você criou. Clique na barra de endereço, apague o que estiver escrito, digite `powershell` e aperte Enter. Abre um terminal já dentro dessa pasta.

### 0.2 Conferir o Git e o Python
```bash
git --version
```
Se der erro, instale o Git em git-scm.com (botão Download for Windows, opções padrão), feche e abra o PowerShell de novo.

```bash
py --version
```
Precisa ser 3.12 ou mais nova (a AP1 usou a 3.14). Se der erro, instale o Python em python.org. No instalador, marque **"Add python.exe to PATH"**. Feche e abra o PowerShell de novo.

### 0.3 Baixar o projeto
```bash
git clone https://github.com/ewerside/proj-visao-computacional.git
```
Isso cria a subpasta `proj-visao-computacional`, já com a AP2 (branch `main`). Se abrir uma janela de login do GitHub, entre com a conta que tem acesso ao repositório.

```bash
cd proj-visao-computacional
```

### 0.4 Criar um ambiente Python só para o projeto
O ambiente isolado (`.venv`) evita a mistura de dois OpenCV que já aconteceu na AP1.
```bash
py -m venv .venv
```
```bash
.venv\Scripts\Activate.ps1
```
O início da linha do terminal passa a mostrar `(.venv)`.

Se aparecer "a execução de scripts foi desabilitada neste sistema", rode o comando abaixo, responda `S` e repita o `Activate.ps1`:
```bash
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**Toda vez que abrir um terminal novo** para o projeto, entre em `proj-visao-computacional` e rode `.venv\Scripts\Activate.ps1` de novo.

### 0.5 Instalar as dependências (uns 5 min)
```bash
python -m pip install --upgrade pip
```
```bash
pip install -r requirements.txt
```
Instala mediapipe, OpenCV (o `opencv-contrib-python`, que o mediapipe já pede), numpy e scipy, só dentro do `.venv`.

### 0.6 Entrar na pasta do código
```bash
cd head_coupled
```
Todos os comandos daqui para a frente rodam **dentro de `head_coupled`**, com o `(.venv)` ativo.

### Já tinha um clone da AP1?
Em vez do `git clone`, entre nele e rode `git fetch origin` e depois `git checkout main` e `git pull`. Se o checkout reclamar de arquivos que seriam sobrescritos:
- **Em `head_coupled/__pycache__`:** são arquivos gerados que a AP1 tinha versionado por engano. Rode `git restore head_coupled/__pycache__` e repita o checkout.
- **No `config.py`:** você tem medidas editadas lá. Anote os valores, rode `git stash`, faça o checkout e digite os valores no `config.py` novo.

## 1. Webcam: o focal.json (2 min, se precisar)

O `focal.json` do repositório é a calibração da webcam do notebook usado na AP1. **Se este for o mesmo notebook**, pule este passo. Se for outro notebook, ou se mais adiante o `main.py` reclamar de calibração, rode:
```bash
python calibrate.py
```
Sente-se a 60 cm da lente, medidos com trena (ou ajuste `CALIB_DISTANCE` no `config.py`), olhe reto para a câmera e aperte ESPAÇO.

## 2. Testes automáticos (1 min)

```bash
python testes/rodar_testes.py
```

O esperado é `5/5 testes OK`. Esses testes rodam sem webcam, sem monitor e sem celular, porque o hardware é simulado. Eles conferem que:
- o modo de uma tela desenha igual à AP1;
- as duas janelas abrem nos monitores certos;
- a calibração acerta a posição do monitor em fotos sintéticas;
- a fórmula da correção de guinada está certa.

Se algum falhar, me mande a saída inteira.

## 3. VOCÊ: medir a tela do notebook com régua (5 min)

Esta medida é a régua de todo o sistema. Cada 1 mm de erro aqui vira 1 a 3 mm de erro na posição calculada do monitor.

1. Rode `python testar_monitores.py`. Aparece uma moldura branca de 1 px exatamente na borda da área acesa.
2. Meça com régua a **largura** e a **altura** dessa área acesa, sem a moldura preta de plástico, em milímetros.
3. Em `config.py`, troque `SCREEN_W` e `SCREEN_H` pelos valores medidos, em **metros**. Exemplo: 344,5 mm vira `0.3445`.

O padrão do `config.py` é uma tela de 15,6 pol 16:9: 0,3454 × 0,1943 m, com incerteza de ~1 mm. Se a sua tela for outra, troque.

## 4. VOCÊ: teste dos monitores (5 min)

1. Ligue o monitor externo. No Windows, aperte **Win+P** e escolha **Estender**.
2. Rode:

   ```bash
   python testar_monitores.py
   ```

3. Confira, uma linha de cada vez:

| O que olhar | Se der errado |
|---|---|
| Há uma janela em tela cheia em **cada** monitor | Me mande a lista de monitores que o script imprime |
| A moldura branca de 1 px aparece **inteira nos 4 lados** dos dois monitores | Na TV, ative "Ajustar à tela" ou "Just Scan" (overscan) |
| O xadrez do canto inferior direito está nítido | Imagem esticada: confira a escala do Windows (ver abaixo) |
| A linha "janela … monitor …" diz **OK** nas duas telas | Escala do Windows: ponha 100% naquele monitor e rode de novo |
| A barra de tarefas não cobre o monitor externo | Me avise |
| Clicando em cada janela e apertando uma tecla, ela aparece nas duas | Me avise |
| A palavra **NOTEBOOK** está no notebook | Aperte `t` até ficar certo. Ao sair, o script mostra uma linha `MONITOR_NOTEBOOK = ...`. **Copie essa linha para o `config.py` antes de seguir.** O `--uma-tela` e o `manual` dependem dela |

4. Saia com `q`.

## 5. A AP1 continua igual (2 min)

```bash
python main.py --uma-tela
```

Deve ser exatamente a demonstração da AP1. A única diferença é uma tecla nova, `y`, que liga e desliga a correção de guinada.

Se aparecer erro de calibração da webcam, rode de novo `python calibrate.py` (ele grava o `focal.json`). Saia com `q`.

## 6. VOCÊ: correção de guinada (10 min)

Ao olhar para o monitor do lado, você gira a cabeça. Sem correção, a distância medida pela webcam erra de 5 a 12 cm. O `teste_guinada.py` mede a diferença com e sem a correção:

```bash
python teste_guinada.py
```

Siga o protocolo escrito no topo do arquivo `teste_guinada.py` (`python teste_guinada.py --help` mostra o texto). Resumo:
1. **Clique na janela "teste de guinada"** antes de usar as teclas. Senão elas vão para o terminal.
2. Sente-se a ~60 cm da tela.
3. Cole post-its a 22 cm e a 35 cm do centro da tela, dos dois lados.
4. Aperte ESPAÇO para começar a gravar.
5. Comece com o nariz **reto para a frente**, perpendicular à tela, por 2 s.
6. Aponte o **nariz** para cada post-it, segurando 2 s em cada um, e volte reto para a frente.
7. Aperte ESPAÇO de novo: o script imprime a tabela e grava um CSV.
8. Repita com a cadeira ~15 cm para o lado, também começando e terminando reto para a frente (perpendicular à tela, não apontando para o centro dela).

**Aprovado:** o veredito da tabela é "OK", ou seja, a correção removeu 60% ou mais do erro.

Se sair "corrige demais", "PARCIAL" ou "FALHOU":
1. Olhando reto para a frente, aperte `m`: o eixo deve sair perto de `(1, 0, 0)` ou `(-1, 0, 0)`.
2. Me mande essa saída, a tabela e o CSV.
3. Enquanto isso, a correção pode ser desligada com a tecla `y`.

Teste rápido alternativo: no `main.py`, aperte `d` para ver o painel. A linha `guinada … k … correcao ON` mostra o ângulo da cabeça. Gire a cabeça, compare o `Z` com `y` ligado e desligado, e veja que com a correção ele varia bem menos.

## 7. Duas telas com medidas de trena: o plano B (10 min, recomendado)

Isto ainda não usa o celular. Serve para ver as duas telas funcionando e é o plano de emergência se a calibração por fotos falhar.

1. **VOCÊ:** em `config.py`, ponha a diagonal do monitor externo em `MONITOR_DIAGONAL_POL`, em polegadas. É a que está na etiqueta ou na caixa, por exemplo `24.0`.
2. **VOCÊ:** meça com trena:
   - `--angulo`: quantos graus o monitor está virado para você. Na dúvida, estime.
   - `--folga`: a distância, em metros, entre a borda acesa do notebook e a borda acesa do monitor que ficam lado a lado, medida **na horizontal, ao longo da borda de baixo do notebook**.
   - `--base`: a altura da borda de baixo da área acesa do monitor menos a do notebook, as duas medidas a partir da mesa, em metros.
   - `--recuo`: quanto o canto de baixo do monitor, do lado do notebook, está **atrás** da linha da borda de baixo do notebook, em metros. Positivo quer dizer mais longe de você; o pé do monitor costuma deixá-lo uns centímetros atrás.
   - `--inclinacao`: quantos graus a tampa do notebook está inclinada para trás em relação à vertical. Um app de nível no celular mede isso.
3. Rode, com os seus números:

   ```bash
   python calibrar_telas.py manual --angulo 30 --folga 0.03 --base 0.05 --recuo 0.04 --inclinacao 15
   ```

   - Se o monitor estiver à esquerda, acrescente `--lado esquerda`.
   - O comando mostra `notebook = ...  monitor = ...`. Se estiver trocado, rode de novo com `--notebook` seguido do nome que ele mostra (ou ajuste `MONITOR_NOTEBOOK` no `config.py`).
4. Rode:

   ```bash
   python main.py
   ```

   As duas telas devem reagir ao movimento da cabeça. A tecla `n` troca de cena: primeiro as da AP1, com uma caixa em cada tela; depois `janelas`, `sala` e `alinhamento`, um mundo só visto pelas duas telas. Como a trena é imprecisa, é normal haver um pequeno degrau nas retas que cruzam a junção.

## 8. VOCÊ: calibração com o celular (15 min)

> **Atalho:** `python calibrar_telas.py celular` faz os passos 8.1, 8.4 e 8.5 sozinho. Ele mostra um QR code no notebook; o celular abre a página, tira as fotos pela câmera dele e manda direto, e o botão "Calcular" da página grava o `telas.json`. As dicas de 8.2 e 8.3 continuam valendo. Celular e notebook na mesma rede.

### 8.1 Mostrar os padrões

```bash
python calibrar_telas.py mostrar
```

1. Confira o rótulo grande: **NOTEBOOK** tem de estar no notebook. Se não estiver, aperte `t`.
2. Aperte **ESPAÇO** para esconder o rótulo.
3. Tire o mouse de cima dos padrões, levando-o para um canto.
4. **Não feche ainda:** os padrões têm de ficar na tela durante as fotos.

### 8.2 Ajustar o celular Android

- Use o app de câmera normal, no modo **Foto**, com a lente **1×**, sem zoom e sem modo retrato ou noturno.
- **Samsung:** em Configurações da câmera, desligue "Fotos de alta eficiência" (senão sai HEIC, que o programa não lê). Desligue também a troca automática de lentes e o "foco macro", se existirem.
- Use a mesma resolução e a mesma proporção em todas as fotos (de preferência 4:3).

### 8.3 Tirar as fotos

- Tire **10 a 15 fotos**, com o celular **sempre deitado** (paisagem).
- Em todas, as **duas telas aparecem inteiras** no quadro.
- Fotografe de **lugares diferentes**: da esquerda, do centro, da direita, mais alto, mais baixo, de 0,6 a 1,2 m. Em algumas, gire um pouco o celular. **Não tire todas do mesmo lugar**, porque isso dobra o erro.
- Toque na tela do celular para focar e evite reflexo de lâmpada ou janela nas telas.
- **Não mexa** na tampa do notebook nem no monitor depois das fotos. Se mexer, refaça a calibração.

### 8.4 Passar as fotos para o PC

- Copie os **arquivos originais** para a pasta `head_coupled/fotos/` (crie a pasta).
- Pode ser por cabo USB, com o celular em "Transferência de arquivos", por Quick Share ou pelo Google Drive.
- **Não use o WhatsApp**, que reduz e recomprime as fotos. Se for usar, envie "como documento".
- Feche os padrões: clique numa das janelas do padrão e aperte `q`.

### 8.5 Calcular

```bash
python calibrar_telas.py calcular
```

1. Leia o resumo:
   - lado do monitor;
   - ângulo entre as telas;
   - folga entre as bordas;
   - tamanho estimado do monitor;
   - erro de reprojeção.
2. **Bons sinais:**
   - reprojeção abaixo de ~1 px;
   - nenhum `AVISO`;
   - o tamanho do monitor bate com a diagonal da etiqueta (alguns % de diferença é normal: monitores de "24 pol" costumam ter 23,8);
   - a folga e o ângulo batem com a trena (alguns mm, ~1–2°).
3. Abra `dbg/planta.png`, a vista de cima com as duas telas e de onde cada foto foi tirada, e confira se o desenho se parece com a sua mesa.
4. As miniaturas em `dbg/` mostram os cantos encontrados: amarelo no notebook, azul no monitor.

## 9. VOCÊ: as duas telas com a calibração (10 min)

```bash
python main.py
```

| Tecla | O que faz |
|---|---|
| `n` | troca de cena (caixas da AP1 em cada tela → `janelas` → `sala` → `alinhamento`) |
| `d` | painel de debug, só no notebook: posição do olho, fps, guinada |
| `y` | liga/desliga a correção de guinada |
| `ESPAÇO` | congela a posição do olho |
| `f` | liga/desliga o filtro One Euro |
| `3` | anáglifo vermelho-ciano (bônus; mais pesado) |
| `q` / `ESC` | sai |

Como saber se está certo:
1. **Cena `alinhamento`:** sente-se parado, aperte **ESPAÇO** e olhe as varetas que cruzam a junção entre as telas. Elas devem continuar sem degrau de uma tela para a outra. Um degrau visível indica erro de calibração. A altura é o que mais pesa: 2 mm de erro dão ~7 px de degrau.
2. **Cena `sala`:** descongele (ESPAÇO de novo) e mexa a cabeça. A sala deve parecer vista por duas janelas, com objetos atravessando a junção sem se partir.
3. **Cenas da AP1:** cada tela mostra a sua caixa, presa à moldura daquela tela.
4. No painel (`d`), o fps deve ficar perto do da webcam (~20).

## Se algo der errado

Para eu ajudar, me mande:
1. O texto completo do terminal: copie e cole.
2. Para a calibração: o `telas.json`, o `dbg/planta.png` e duas ou três miniaturas de `dbg/`.
3. Para as janelas: uma foto das duas telas tirada com o celular.

| Sintoma | Causa provável e o que fazer |
|---|---|
| `nao achei o monitor da tela 'monitor'` | O monitor foi desligado, mudou de porta ou o Windows o renumerou. Rode de novo o `calibrar_telas.py mostrar` + `calcular`, ou use `python main.py --uma-tela` |
| `--telas ...: arquivo nao existe` | Caminho do `telas.json` digitado errado |
| Painel `d` diz `SEM MATRIZ do MediaPipe` | A versão do mediapipe não entrega a rotação da cabeça, e a correção de guinada fica desligada. Me mande a saída de `pip show mediapipe` |
| `So ha 1 monitor` | Win+P → Estender |
| Janela do monitor aparece no notebook | Me mande a saída do `testar_monitores.py` |
| `so N foto(s) mostram as DUAS telas` | Veja as miniaturas em `dbg/`: chegue mais perto (0,6–0,8 m), evite reflexo, confira que os padrões estavam na tela |
| Fotos "ignoradas" por tamanho diferente | Foram tiradas com lentes ou modos diferentes, ou em pé e deitado misturados. Use só a lente 1×, deitado |
| HEIC ignorado | Celular salvando em HEIF. Desligue "Fotos de alta eficiência" e fotografe de novo |
| `AVISO: erro de reprojecao alto` | Fotos tremidas ou algo mexeu entre as fotos. Refaça com o celular firme |
| O monitor sai com diagonal muito diferente | Confira `MONITOR_DIAGONAL_POL` e tire fotos de pontos de vista mais variados |
| Degrau nas varetas do `alinhamento` | Refaça a calibração com fotos mais variadas e mais perto. Confira a régua do passo 3 |
| A cena do monitor "escorrega" quando você vira a cabeça | Confira a correção de guinada (passo 6) e o painel `d` |

Recalibrar é rápido: `mostrar` → fotos → `calcular`, uns 3 minutos. Ensaie isso antes da apresentação.
