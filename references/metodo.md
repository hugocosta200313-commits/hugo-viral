# Como a nota de forma é calculada

Tudo vem do próprio arquivo: quadros a 10 fps reduzidos para 96×96 em cinza, áudio mono 16 kHz e
transcrição com tempos por palavra (faster-whisper, `pt`).

## Medidas

- **Movimento**: diferença média entre quadros seguidos.
- **Cortes/mudanças bruscas**: histograma de brilho muda > 0,30 **e** movimento > 0,07 (mín. 0,3 s entre cortes).
- **Flashes**: brilho sobe > 0,18 em relação aos dois vizinhos.
- **Áudio**: dBFS em janelas de 100 ms.
- **Fala**: palavras transcritas (ou, com `--sem-transcricao`, trechos acima de -35 dBFS).
- **Curva de estímulo** (janelas de 0,5 s, suavizada): `0,35·movimento + 0,25·volume + 0,30·fala + 0,25·mudança`.
- **Trecho plano**: ≥ 1,5 s com pouco movimento, sem mudança e sem fala.
- **Sustentação**: média da curva depois dos 3 s ÷ média nos 3 s.

## Pontos (total 100)

| Item | Máx. | Regra |
|---|---|---|
| Início imediato | 25 | 1ª fala (ou 1º som) em ≤ 0,3 s = 25; ≥ 1,5 s = 0 |
| Fala no gancho | 15 | 6–13 palavras nos 3 s = 15; menos cai linearmente; mais que 13 perde até 5 |
| Visual no gancho | 20 | 12 pelo movimento nos 3 s + 8 se houver corte/flash nos 2 s |
| Áudio no gancho | 15 | -40 dBFS = 0 a -20 dBFS = 15; ×0,6 se o gancho estiver 6 dB abaixo do resto |
| Sem trechos planos | 15 | 15 × (1 − 2,5 × fração plana) |
| Ritmo visual | 10 | 6 pela taxa de mudanças (alvo 1 a cada 3 s) + 4 pelo movimento médio |
| Penalidade de efeitos | até −15 | flashes acima de 1 a cada 3 s |

## Limites conhecidos

- Não lê texto na tela, não reconhece rosto nem julga beleza: isso é a análise visual dos quadros.
- Zoom lento e movimento de câmera suave contam pouco como "mudança".
- Música alta sem fala conta como áudio forte, mas não como fala.
- A nota mede forma, não a ideia. Dois vídeos com a mesma nota podem ter resultados muito diferentes.
