# Plano da AP2: perspectiva acoplada à cabeça em duas telas

O notebook, cuja webcam faz o rastreamento dos olhos, e um monitor externo ligado a ele em modo "Estender", em qualquer ângulo, mostram o mesmo mundo 3D. Um celular Android tira fotos das duas telas exibindo padrões ChArUco, e o programa calcula onde o monitor está em relação ao notebook. A partir daí as duas imagens mudam juntas, em tempo real, com a posição dos olhos.

O código está implementado e testado sem hardware (`python head_coupled/testes/rodar_testes.py`) e já rodou no notebook com um monitor externo. O passo a passo está no guia [`TESTE_AP2.md`](TESTE_AP2.md).

## Fluxo de uso

1. `python calibrar_telas.py mostrar`: cada tela mostra o seu padrão, com o nome dela por cima.
2. Tirar 10 a 15 fotos das duas telas, de lugares diferentes, com o app de câmera normal.
3. Copiar as fotos originais para `head_coupled/fotos/`.
4. `python calibrar_telas.py calcular`: gera o `telas.json`, um resumo em cm e graus, e uma vista de cima.
5. `python main.py`: duas telas. Sem `telas.json`, ou com `--uma-tela`, é a AP1.

## Decisões

| Questão | Decisão | Motivo |
|---|---|---|
| App no celular? | **Não.** Câmera padrão do Android | Melhor foto e zero desenvolvimento mobile |
| Fotos ou vídeo? | **Fotos** | No vídeo, a estabilização digital muda a "lente" a cada quadro, além de borrão e compressão |
| Transferência | Cabo USB, Quick Share ou Drive → `fotos/` | Mantém o arquivo original, sem servidor nem rede. WhatsApp só "como documento" |
| Padrão | ChArUco 13×7, `DICT_5X5_250`, IDs 0–44 no notebook e 45–89 no monitor | Funciona com tela parcial, cantos subpixel, IDs dizem qual tela é qual; nenhum marcador falso em 200 fotos simuladas (o 4×4 leu 4) |
| Tamanho físico | Tamanho da tela ÷ resolução; o do monitor é **estimado** pelas fotos | Só o notebook precisa de régua; do monitor basta a diagonal nominal |
| Câmera do celular | Calibrada com as mesmas fotos | Sem etapa extra |
| Pose do monitor | PnP por foto → média robusta → ajuste de feixes (`scipy`) | Simulação: ~0,2 mm típico, ≤ 2,3 mm no pior caso |
| Referencial | Tela do notebook, o mesmo da AP1 | O rastreamento da AP1 não muda |
| Desenho | Um programa, uma janela em tela cheia por monitor, uma ordem de pintura para as duas | Oclusão e cor iguais dos dois lados da junção |
| Cenas | Cenas da AP1 com uma caixa por tela + `janelas`, `sala` e `alinhamento` (mundo compartilhado, recorte pelo plano de cada tela) | A primeira funciona de cara; a segunda mostra se a calibração está certa |
| Guinada | Correção pela rotação da cabeça do MediaPipe (tecla `y`) | Sem correção: +5 a +12 cm de erro em Z ao olhar o monitor |
| Windows | DPI Per-Monitor v2 antes de qualquer janela; monitores via `ctypes` | Com escala de 125%/150% as janelas saíam com tamanho errado e esticadas |
| Dependências | `requirements.txt` sem `opencv-python` | O mediapipe já traz o `opencv-contrib-python`; dois OpenCV na mesma pasta quebram |
| Anáglifo | Funciona nas duas telas, como bônus | Dobra o custo de desenho |

## O que os testes de viabilidade mostraram (simulação)

- **Calibração** (~3.000 fotos sintéticas de 12 MP, com borrão, ruído, moiré, reflexo e JPEG):
  - posição do monitor com erro típico de 0,2 mm; ângulo com erro < 0,1°;
  - tamanho do monitor recuperado com 0,1% de erro, partindo de um chute 7% errado;
  - variar o ponto de vista importa mais que o número de fotos.
- **Maior fonte de erro real:** o tamanho da tela do notebook. Cada 1 mm de erro nele vira 1 a 3 mm no monitor. Meça com régua.
- **Sensibilidade:** 2 mm de erro na altura do monitor dão um degrau de ~7 px na junção. A meta é ~1–2 mm e ~0,5°.
- **Desenho:** o modo de uma tela é idêntico à AP1, quadro a quadro. Com duas telas, o custo é o dobro de uma (`caixa` ~10 ms, `sala` ~6 ms por quadro).
- **Guinada:** com a correção, o erro médio de distância cai de 9% para ~2% (de +7–14 cm para +0,2–4 cm a 30°).

## Arquitetura

| Arquivo | Papel |
|---|---|
| `monitores.py` | DPI, lista de monitores (`ctypes`), escolha do monitor do notebook, janela em tela cheia num monitor |
| `testar_monitores.py` | Teste de 15 min no hardware: moldura de 1 px, xadrez de 1 px, teclas, qual é o notebook |
| `telas.py` | `Tela` com pose `x_notebook = R @ x_tela + t`, `telas.json`, projeção, recorte pelo plano da tela, desenho em lote |
| `sala.py`, `janelas.py` | Cenas de mundo compartilhado (`janelas`, `sala`, `alinhamento`) |
| `avaliar.py` | Avaliação quantitativa: compara os estimadores em fotos simuladas e reais |
| `scene.py` | Cenas da AP1 parametrizadas pelo tamanho da tela; guarda contra coordenadas absurdas |
| `main.py` | Laço principal: uma janela por tela, `--uma-tela`, `--telas` |
| `tracking.py` | Correção de guinada (`fator_escorco`) |
| `calibrar_telas.py` | `mostrar`, `calcular` e `manual` |
| `padroes.py` / `detectar.py` / `calibracao.py` | Padrões ChArUco e `padroes.json`; detecção nas fotos; intrínsecos, PnP e ajuste de feixes |
| `simular.py` | Fotos sintéticas com resposta conhecida |
| `testes/` | Testes automáticos sem hardware |

### Formato do `telas.json`

```json
{
  "versao": 1,
  "referencial": "tela do notebook: origem no centro da area acesa, X direita, Y cima, Z saindo da tela para o rosto, metros. Para cada tela: x_notebook = R @ x_tela + t",
  "telas": [
    {"nome": "notebook", "monitor": {"dispositivo": "\\\\.\\DISPLAY1", "x": 0, "y": 0, "largura_px": 1920, "altura_px": 1080},
     "resolucao_px": [1920, 1080], "tamanho_m": [0.345, 0.194],
     "R": [[1,0,0],[0,1,0],[0,0,1]], "t": [0, 0, 0]},
    {"nome": "monitor", "monitor": {"dispositivo": "\\\\.\\DISPLAY2", "x": 1920, "y": 0, "largura_px": 1920, "altura_px": 1080},
     "resolucao_px": [1920, 1080], "tamanho_m": [0.5312, 0.2988],
     "R": [[0.819,0,-0.574],[0,1,0],[0.574,0,0.819]], "t": [0.42, 0.08, 0.15]}
  ],
  "qualidade": {"rms_reproj_px": 0.4, "dispersao_entre_fotos": {"rot_graus": 0.03, "trans_mm": 0.3}},
  "resumo": {"lado": "direita", "angulo_entre_telas_graus": 35.0, "folga_bordas_internas_cm": 3.0}
}
```

O `main.py` lê só `monitor`, `resolucao_px`, `tamanho_m`, `R` e `t`. O notebook vem sempre primeiro, com a pose identidade. O resto é relatório da calibração.

## Riscos e plano B

| Risco | Plano B |
|---|---|
| A janela não fica em tela cheia no segundo monitor | `testar_monitores.py` mostra na hora; alternativa: janela sem borda via `SetWindowPos` |
| Escala de tela diferente nos monitores | DPI Per-Monitor v2 no início; em último caso, 100% nos dois |
| Fotos reais falham (moiré, reflexo) | Mais perto (0,6–0,8 m), outro ângulo; as miniaturas em `dbg/` mostram o que foi achado |
| Calibração real pior que a simulada | Fotos mais variadas, régua no notebook, overscan desligado. Emergência: `calibrar_telas.py manual` |
| Correção de guinada falha em rosto real | Monitor a no máximo ~35° de quem assiste; a tecla `y` desliga |
| Alguém mexe na tampa ou no monitor | Recalibrar (~3 min) |

## Para o artigo

- **Figuras:**
  - a foto "do olho" com as retas contínuas na junção (cena `alinhamento`);
  - `dbg/planta.png`;
  - uma miniatura com os cantos detectados.
- **Tabelas:**
  - erro da calibração simulada por número de fotos (`simular.py` + `calcular`);
  - repetibilidade de 3 calibrações reais;
  - comparação com a trena;
  - distância com e sem a correção de guinada (`teste_guinada.py`);
  - fps.

**Fora do escopo:** app no celular, vídeo, espelho, ajuste manual por teclado e mais de duas telas (o desenho já aceita N telas; a calibração faz duas).
