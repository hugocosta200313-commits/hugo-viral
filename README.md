# Hugo Viral — skill grátis para Claude Code

Analisa um Reels, Short ou TikTok **pronto** e diz:

- se o **conteúdo** está bom (gancho, promessa, clareza, progressão, recompensa, chamada final);
- a **faixa de potencial** de viralizar (baixo / médio / bom / alto) e o que faria subir de faixa;
- o que **melhorar no visual**: efeitos (remover, encurtar, trocar ou mover), texto na tela, zonas seguras do 9:16,
  enquadramento, cor e ritmo;
- um **plano de edição por minutagem**, separando o que é **só cortar**, **ajustar efeito**, **adicionar** ou **regravar**;
- qual **abertura** é melhor quando você grava várias versões.

Roda **no seu computador e de graça**: ffmpeg + faster-whisper medem a forma (quando a fala começa, palavras no
gancho, cortes, movimento, flashes, volume, trechos parados, pausas) e o Claude olha os quadros-chave e lê a
transcrição para julgar conteúdo e visual. Sem API paga, sem créditos, sem enviar o vídeo para lugar nenhum.

> Nenhuma ferramenta prevê viralização de verdade: distribuição, conta, horário e tendência não estão no arquivo.
> A skill dá uma faixa honesta e, principalmente, **o que mudar**.

## Instalar

1. Tenha `ffmpeg` no PATH e Python 3.9+.
2. `pip install numpy faster-whisper`
3. Copie esta pasta para `~/.claude/skills/hugo-viral/`:

```bash
git clone https://github.com/hugocosta200313-commits/hugo-viral ~/.claude/skills/hugo-viral
```

## Usar

No Claude Code, é só pedir:

> analisa esse reels: C:/videos/meu_reels.mp4

> qual dessas 4 aberturas é melhor? abertura1.mp4 abertura2.mp4 abertura3.mp4 abertura4.mp4

Ou rode só a medição:

```bash
python scripts/hugo_viral.py video.mp4 --saida hugo_viral
```

Sai um `video.html` com a nota de forma, a curva de estímulo (gancho, cortes e trechos planos marcados), as
sugestões automáticas e a folha de quadros-chave, além de um `video.json` com todas as medidas.

## Testes

```bash
python tests/teste_sintetico.py
```

Gera vídeos sintéticos (dinâmico, parado, com buraco no meio, com flashes demais) e confere se a nota e as
sugestões reagem na direção certa.

## Como funciona

Veja [references/metodo.md](references/metodo.md) (nota de forma), [references/rubrica-visual.md](references/rubrica-visual.md)
e [references/rubrica-conteudo.md](references/rubrica-conteudo.md).

## Licença

MIT
