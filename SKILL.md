---
name: analisador-gancho
description: Analisa um vídeo curto pronto (Reels, Shorts, TikTok) e diz se o conteúdo está bom, qual a chance de viralizar e exatamente como melhorar — gancho, ritmo, silêncios, trechos planos, efeitos visuais, texto na tela, zonas seguras e cor — com sugestões por minutagem (só cortar, ajustar efeito, adicionar ou regravar). Mede a forma de graça, no próprio computador (ffmpeg + faster-whisper), e faz a análise visual pelos quadros-chave. Compara várias aberturas do mesmo vídeo. Use quando o usuário perguntar "esse vídeo vai viralizar?", "analisa meu reels", "o gancho está bom?", "como melhorar esse vídeo", "os efeitos estão bons?", "qual abertura é melhor", ou mandar um vídeo pronto pedindo opinião.
---

# Analisador de gancho

Alternativa gratuita e local aos "preditores de viralidade". O script **mede** a forma do vídeo; você (o agente)
**olha** os quadros-chave e **lê** a transcrição para julgar conteúdo e visual. A resposta final junta os dois.

> Honestidade: nenhuma ferramenta prevê viralização. Distribuição, conta, horário, tendência e sorte não estão
> no arquivo. Dê uma **faixa de potencial** com motivos, nunca uma porcentagem com cara de certeza.

## Requisitos

- `ffmpeg` e `ffprobe` no PATH
- Python 3.9+ com `numpy` e `faster-whisper` (`pip install numpy faster-whisper`). Sem o whisper, use `--sem-transcricao`.

## Passo 1 — Medir

```bash
python <pasta-da-skill>/scripts/analisar_gancho.py VIDEO.mp4 --saida analise_gancho
```

- Várias aberturas do mesmo vídeo: passe todos os arquivos de uma vez; sai também `comparativo.html` e um ranking.
- `--modelo tiny|base|small|medium` (padrão `small`). `--max-segundos` (padrão 180).
- Saídas por vídeo em `--saida`: `NOME.json` (todas as medidas), `NOME.html` (relatório com curva) e
  `NOME_quadros/` (quadros-chave com o tempo escrito + `folha.jpg`).

O que o JSON traz: `nota_forma` (0–100) e `pontos` por item, `gancho` (1ª fala, palavras em 3 s, texto dos 3 s,
mudança visual em 2 s, volume do gancho × resto, pico), `sustentacao` (energia depois do gancho ÷ no gancho),
`cortes_s`, `flashes_s`, `trechos_planos_s`, `pausas_fala_s`, `palavras_por_minuto`, `transcricao` com tempos e
`sugestoes` automáticas. Como a nota é calculada: [references/metodo.md](references/metodo.md).

## Passo 2 — Olhar (análise visual)

Abra **`folha.jpg`** e depois os quadros individuais do gancho (0 s a 3 s) e de cada corte e trecho plano.
Avalie com [references/rubrica-visual.md](references/rubrica-visual.md):

- **Efeitos**: cada efeito marca uma ideia da fala ou é decoração? Entra no tempo da palavra ou atrasado? Repete o
  mesmo efeito até cansar? Algum atrapalha a leitura ou o rosto? Diga, para cada problema, se a solução é
  **remover**, **encurtar**, **trocar** ou **mover** — e o tempo exato.
- **Texto na tela**: legível no celular, poucas palavras, contraste, tempo para ler.
- **Zonas seguras 9:16**: nada importante nos ~14% de cima, ~22% de baixo e ~15% da direita (interface do app).
- **Enquadramento e rosto**, **cor e exposição**, **consistência de estilo**, **transições**, **legendas**.

Se a sua interface não lê imagens, diga isso e baseie-se só nas medidas.

As medidas são pistas, não verdade: o script não vê texto pequeno surgindo nem zoom lento. Se um quadro desmente uma
sugestão automática (ex.: "nenhuma mudança visual em 2 s" mas há um texto entrando em 0,5 s), corrija a sugestão.

## Passo 3 — Ler (análise de conteúdo)

Leia a transcrição (o whisper erra nomes próprios e marcas — ex.: "Claude" vira "Cloud"; não aponte isso como erro
do vídeo, confira na legenda dos quadros) e dê nota 0–10, com uma frase de motivo, para cada critério em
[references/rubrica-conteudo.md](references/rubrica-conteudo.md): gancho, promessa, clareza, novidade/valor,
progressão, recompensa, emoção/identificação e chamada final. Cite as frases reais do vídeo.

## Passo 4 — Potencial de viralizar

Combine: conteúdo (média da rubrica × 10) com peso **0,65** e `nota_forma` com peso **0,35**. Converta em faixa:

| Combinado | Faixa | Leitura |
|---|---|---|
| < 45 | Baixo | Perde a maioria nos primeiros segundos; refazer o gancho antes de postar |
| 45–64 | Médio | Segura quem já te segue; dificilmente sai da bolha |
| 65–79 | Bom | Estrutura de vídeo que se espalha; o tema e a distribuição decidem |
| ≥ 80 | Alto | Forma e conteúdo fortes; poste no melhor horário e teste capas |

Diga sempre **o que faria subir de faixa** (as 2–3 mudanças de maior impacto).

## Passo 5 — Entregar

Responda nesta ordem, em português, curto e direto:

1. **Veredito** em uma frase + faixa de potencial + nota de forma + nota de conteúdo.
2. **O que já está bom** (2–4 itens — o usuário precisa saber o que não mexer).
3. **Plano de melhoria priorizado** (até 8 itens), cada um com:
   `minutagem · o que fazer · por quê · tipo` onde tipo é **Só cortar**, **Ajustar efeito**, **Adicionar** ou
   **Regravar**. Ordene pelo impacto ÷ esforço: cortes primeiro, regravação por último.
4. **Gancho alternativo**: 2–3 novas primeiras frases e/ou primeira imagem, se o gancho não estiver forte.
5. Caminho do `NOME.html` para ver a curva e os quadros.

Comparando aberturas: aponte a vencedora, por que ela venceu e o que copiar das outras.

Se o projeto do vídeo estiver disponível (DaVinci Resolve, HyperFrames, Remotion, timeline FFmpeg), ofereça aplicar
os itens "Só cortar" e "Ajustar efeito" — não aplique sem o usuário pedir.

## Testes

`python tests/teste_sintetico.py` gera vídeos sintéticos (dinâmico, parado, com buraco no meio, com flashes demais) e
confere se a nota e as sugestões reagem na direção certa.
