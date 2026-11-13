# Imagens para o artigo e os slides

Tudo o que serve de figura está aqui. As fotos são reais; os renders saem do mesmo código que desenha as cenas, com a calibração real de 13/11/2026.

| Pasta | O que tem | De onde veio |
|---|---|---|
| `montagem/` | Foto do notebook e do monitor mostrando os padrões e o QR code | Foto do grupo, 13/11/2026 |
| `calibracao_fotos/` | As 12 fotos originais (Pixel 7 Pro, 4080×3072) usadas na calibração real | Enviadas pela página do celular |
| `calibracao_cantos/` | Fotos com os cantos detectados (amarelo: notebook; azul: monitor), a vista de cima (`vista_de_cima.png`), o padrão ChArUco, o padrão com QR code, uma foto simulada e o `telas_13nov.json` | `calibrar_telas.py calcular` e `simular.py` |
| `cenas/` | Renders das cenas de uma tela (olho no centro, à direita e à esquerda), da cena de asteroides em anáglifo e das cenas de duas telas (notebook e monitor lado a lado) | `scene.py`, `sala.py`, `planeta.py`, `janelas.py` |
| `menu/` | As seis telas do Parallax | `parallax.py` |
| `celular/` | A página do celular fotografando e mostrando o resultado com a prévia das telas | `celular.py` |
| `graficos/` | Erro simulado por número de fotos e repetibilidade nas fotos reais, com os dados (`dados/`), as tabelas em CSV e o script que gera os dois | `avaliar.py` e `gerar_graficos.py` |

## Sugestão de uso

- **Artigo, foto do protótipo:** `montagem/duas_telas_com_qr_code.jpg`.
- **Artigo, resultado qualitativo:** `cenas/duas_telas_planeta_tipico.png` ou `cenas/duas_telas_trem_tipico.png`, e `calibracao_cantos/cantos_detectados_foto_01.png`.
- **Artigo, resultado quantitativo:** `graficos/repetibilidade_fotos_reais.png`.
- **Slides:** as três posições de olho de uma mesma cena em `cenas/uma_tela_*` mostram a paralaxe sem precisar de vídeo.

## Refazer os gráficos

```bash
python docs/imagens/graficos/gerar_graficos.py
```

Os números vêm de `python head_coupled/avaliar.py simulado --json ...` e `python head_coupled/avaliar.py real <pasta das fotos> --json ...`.

## Ainda falta (só com o equipamento montado)

- Foto das duas telas rodando uma cena, tirada da posição de quem assiste.
- Foto da junção na cena de alinhamento, com as varetas contínuas.
- O vídeo da demonstração.
