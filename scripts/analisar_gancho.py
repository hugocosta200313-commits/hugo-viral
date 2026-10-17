#!/usr/bin/env python
"""Analisador de gancho e retenção para vídeos curtos (Reels, Shorts, TikTok).

Mede a FORMA do vídeo de graça, no próprio computador (ffmpeg + faster-whisper):
quando a fala começa, quantas palavras entram no gancho, cortes, movimento,
flashes, energia do áudio, trechos planos e uma curva de estímulo. Também tira
quadros-chave e uma folha de contato para a análise visual feita pelo agente.

Uso:
    python analisar_gancho.py video.mp4 [outro.mp4 ...] [--saida pasta]
                              [--modelo small] [--sem-transcricao]

Com vários vídeos, gera também um comparativo (útil para testar aberturas).
A nota NÃO mede se a ideia é boa: isso fica para a análise de conteúdo.
"""
import argparse
import html
import json
import os
import subprocess
import sys

import numpy as np

FPS = 10            # quadros analisados por segundo
LADO = 96           # lado do quadro reduzido usado nas medições
BIN = 0.5           # resolução da curva de estímulo (s)
GANCHO = 3.0        # duração do gancho (s)
FONTE = "C\\:/Windows/Fonts/arial.ttf" if os.name == "nt" else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def rodar(cmd, binario=False):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-800:])
    return r.stdout if binario else r.stdout.decode("utf-8", "replace")


def sondar(caminho):
    info = json.loads(rodar(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration:stream=codec_type,width,height",
                             "-of", "json", caminho]))
    dur = float(info["format"]["duration"])
    tem_audio = any(s.get("codec_type") == "audio" for s in info["streams"])
    vid = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
    return dur, tem_audio, vid.get("width"), vid.get("height")


def ler_quadros(caminho, dur):
    bruto = rodar(["ffmpeg", "-v", "error", "-t", f"{dur:.3f}", "-i", caminho,
                   "-vf", f"fps={FPS},scale={LADO}:{LADO},format=gray",
                   "-f", "rawvideo", "-pix_fmt", "gray", "-"], binario=True)
    q = np.frombuffer(bruto, np.uint8)
    n = len(q) // (LADO * LADO)
    return q[: n * LADO * LADO].reshape(n, LADO, LADO).astype(np.float32)


def ler_audio(caminho, dur, tem_audio):
    if not tem_audio:
        return np.zeros(int(dur * 16000), np.float32)
    bruto = rodar(["ffmpeg", "-v", "error", "-t", f"{dur:.3f}", "-i", caminho,
                   "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], binario=True)
    return np.frombuffer(bruto, np.int16).astype(np.float32) / 32768.0


def deslocamento(a, b, maximo=12):
    """Translação global entre dois quadros (correlação de fase). Retorna (dy, dx) que leva a em b."""
    fa = np.fft.fft2(a - a.mean())
    fb = np.fft.fft2(b - b.mean())
    r = fb * np.conj(fa)
    r /= np.abs(r) + 1e-9
    c = np.real(np.fft.ifft2(r))
    dy, dx = np.unravel_index(np.argmax(c), c.shape)
    dy = dy - LADO if dy > LADO // 2 else dy
    dx = dx - LADO if dx > LADO // 2 else dx
    if abs(dy) > maximo or abs(dx) > maximo:
        return 0, 0
    return int(dy), int(dx)


def medir_visual(q):
    """Movimento, mudanças bruscas (cortes/transições), eventos visuais e flashes por quadro.

    `mud` = fração dos pixels que mudou em 0,5 s. Funciona melhor que a diferença média em
    motion design de fundo escuro, onde os elementos animados são pequenos."""
    n = len(q)
    meio = FPS // 2
    mud = np.zeros(n)
    m = 8  # borda ignorada depois do alinhamento
    for i in range(n):
        ant = q[max(0, i - meio)]
        dy, dx = deslocamento(ant, q[i])
        ant = np.roll(ant, (dy, dx), axis=(0, 1))  # compensa câmera na mão / panorâmica
        mud[i] = (np.abs(q[i] - ant)[m:-m, m:-m] > 12).mean()
    mov = np.zeros(n)
    hist_d = np.zeros(n)
    brilho = q.mean(axis=(1, 2)) / 255.0
    hists = np.stack([np.histogram(f, bins=16, range=(0, 256))[0] for f in q]).astype(np.float32)
    hists /= hists.sum(axis=1, keepdims=True)
    for i in range(1, n):
        mov[i] = np.abs(q[i] - q[i - 1]).mean() / 255.0
        hist_d[i] = np.abs(hists[i] - hists[i - 1]).sum() / 2.0
    # salto entre quadros seguidos, já descontando a câmera na mão
    salto = np.zeros(n)
    for i in range(1, n):
        dy, dx = deslocamento(q[i - 1], q[i])
        ant = np.roll(q[i - 1], (dy, dx), axis=(0, 1))
        salto[i] = (np.abs(q[i] - ant)[m:-m, m:-m] > 20).mean()
    cortes = []
    for i in range(1, n):
        base = np.median(salto[max(0, i - FPS): i + FPS])
        seco = hist_d[i] > 0.30 and mov[i] > 0.07
        pico = salto[i] > 0.55 and salto[i] > 2.5 * base + 0.1 and salto[i] >= salto[i - 1] and (i + 1 >= n or salto[i] >= salto[i + 1])
        if (seco or pico) and (not cortes or i - cortes[-1] >= 3):
            cortes.append(i)
    flashes = []
    for i in range(1, n - 1):
        if brilho[i] - min(brilho[i - 1], brilho[i + 1]) > 0.18:
            flashes.append(i)
    # eventos: picos de mudança (elemento novo, transição animada, texto entrando), 1 por segundo no máx.
    eventos = []
    for i in range(1, n - 1):
        viz = mud[max(0, i - 3 * FPS): i + 3 * FPS]
        base = np.median(viz)  # movimento contínuo (gesto, câmera na mão) não é evento
        if (mud[i] > 0.25 and mud[i] > 2 * base + 0.08 and mud[i] >= mud[i - 1] and mud[i] >= mud[i + 1]
                and (not eventos or i - eventos[-1] >= FPS)):
            eventos.append(i)
    return mud, brilho, [c / FPS for c in cortes], [f / FPS for f in flashes], [e / FPS for e in eventos]


def db_por_janela(audio, passo=0.1):
    tam = int(16000 * passo)
    n = len(audio) // tam
    if n == 0:
        return np.array([-90.0])
    j = audio[: n * tam].reshape(n, tam)
    rms = np.sqrt((j ** 2).mean(axis=1)) + 1e-9
    return 20 * np.log10(rms)


def transcrever(audio, modelo):
    from faster_whisper import WhisperModel
    m = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio, language="pt", word_timestamps=True, vad_filter=True,
                           condition_on_previous_text=False)
    palavras = []
    for s in segs:
        for w in s.words or []:
            palavras.append({"inicio": round(w.start, 2), "fim": round(w.end, 2), "texto": w.word.strip()})
    return palavras


def fala_por_energia(db):
    """Aproximação sem transcrição: janelas de 100 ms acima de -35 dBFS."""
    ativo = db > -35
    palavras, i = [], 0
    while i < len(ativo):
        if ativo[i]:
            j = i
            while j < len(ativo) and ativo[j]:
                j += 1
            if j - i >= 2:
                palavras.append({"inicio": i * 0.1, "fim": j * 0.1, "texto": "~"})
            i = j
        else:
            i += 1
    return palavras


def lim(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def analisar(caminho, args):
    dur, tem_audio, larg, alt = sondar(caminho)
    if not larg:
        raise ValueError("o arquivo não tem imagem (só áudio); esta skill analisa vídeos")
    dur_a = min(dur, args.max_segundos)
    q = ler_quadros(caminho, dur_a)
    audio = ler_audio(caminho, dur_a, tem_audio)
    mov, brilho, cortes, flashes, eventos = medir_visual(q)
    db = db_por_janela(audio)

    if args.sem_transcricao or not tem_audio:
        palavras, transcrito = fala_por_energia(db), False
    else:
        palavras, transcrito = transcrever(audio, args.modelo), True

    # ---- curva de estímulo (0..1) em janelas de BIN segundos
    nb = max(1, int(np.ceil(dur_a / BIN)))
    vis, aud, fal, mud = np.zeros(nb), np.zeros(nb), np.zeros(nb), np.zeros(nb)
    for b in range(nb):
        a, z = b * BIN, (b + 1) * BIN
        fm = mov[int(a * FPS): int(z * FPS)]
        vis[b] = lim((fm.mean() if len(fm) else 0) / 0.15)
        fa = db[int(a * 10): int(z * 10)]
        aud[b] = lim(((fa.mean() if len(fa) else -90) + 45) / 30)
        cob = sum(max(0, min(z, w["fim"]) - max(a, w["inicio"])) for w in palavras)
        fal[b] = lim(cob / BIN)
        mud[b] = 1.0 if any(a <= t < z for t in cortes + flashes + eventos) else 0.0
    curva = np.clip(0.35 * vis + 0.25 * aud + 0.30 * fal + 0.25 * mud, 0, 1)
    if nb >= 3:
        curva = np.convolve(np.pad(curva, 1, mode="edge"), np.ones(3) / 3, mode="valid")

    # ---- trechos planos: pouco movimento, sem mudança e sem fala por >= 1.5 s
    planos, ini = [], None
    for b in range(nb + 1):
        plano = b < nb and vis[b] < 0.25 and mud[b] == 0 and fal[b] < 0.2
        if plano and ini is None:
            ini = b
        elif not plano and ini is not None:
            if (b - ini) * BIN >= 1.5:
                planos.append([round(ini * BIN, 1), round(b * BIN, 1)])
            ini = None
    frac_plano = sum(z - a for a, z in planos) / dur_a

    # ---- pausas na fala (> 0.7 s entre palavras)
    pausas = []
    for w1, w2 in zip(palavras, palavras[1:]):
        if w2["inicio"] - w1["fim"] > 0.7:
            pausas.append([round(w1["fim"], 2), round(w2["inicio"], 2)])

    # ---- gancho
    tem_fala = len(palavras) > 0
    t0_fala = palavras[0]["inicio"] if tem_fala else None
    som = np.where(db > -30)[0]
    t0_som = som[0] * 0.1 if len(som) else None
    t0 = t0_fala if t0_fala is not None else (t0_som if t0_som is not None else 99)
    pal_gancho = [w for w in palavras if w["inicio"] < GANCHO]
    mov_g = mov[: int(GANCHO * FPS)].mean() if len(mov) else 0
    mud_2s = any(0.2 <= t < 2.0 for t in cortes + flashes + eventos)
    db_g = db[: int(GANCHO * 10)]
    db_resto = db[int(GANCHO * 10):]
    db_g_m = float(np.mean(db_g[db_g > -60])) if (db_g > -60).any() else -90.0
    db_r_m = float(np.mean(db_resto[db_resto > -60])) if (db_resto > -60).any() else db_g_m

    pts = {}
    pts["inicio_imediato"] = (25 * lim((1.5 - t0) / 1.2), 25)
    n = len(pal_gancho)
    if not tem_fala:
        f = 7.5
    elif n <= 6:
        f = 15 * n / 6
    elif n <= 13:
        f = 15
    else:
        f = 15 - min(5, (n - 13) * 0.7)
    pts["fala_no_gancho"] = (f, 15)
    pts["visual_no_gancho"] = (12 * lim(mov_g / 0.12) + 8 * mud_2s, 20)
    a = 15 * lim((db_g_m + 40) / 20)
    if db_g_m < db_r_m - 6:
        a *= 0.6
    pts["audio_no_gancho"] = (a, 15)
    pts["sem_trechos_planos"] = (15 * lim(1 - 2.5 * frac_plano), 15)
    # flashes contam como mudança só até 1 a cada 3 s; acima disso viram ruído
    flashes_uteis = min(len(flashes), dur_a / 3)
    mudancas = sorted(set(round(t) for t in cortes + eventos))
    taxa = (len(mudancas) + flashes_uteis) / dur_a
    pts["ritmo_visual"] = (6 * lim(taxa / 0.33) + 4 * lim(mov.mean() / 0.10), 10)
    excesso = max(0.0, len(flashes) / dur_a - 1 / 3)  # flashes por segundo acima do saudável
    penal = -min(15.0, excesso * 25)
    nota = round(max(0, sum(v for v, _ in pts.values()) + penal))
    pts["excesso_de_efeitos"] = (penal, 0)

    pico = int(np.argmax(curva[: max(1, int(GANCHO * 2 / BIN))]))  # pico dentro dos 6 s iniciais
    g = curva[: int(GANCHO / BIN)]
    r = curva[int(GANCHO / BIN):]
    sustenta = float(r.mean() / g.mean()) if len(r) and g.mean() > 0 else 1.0
    wpm = 60 * len(palavras) / max(0.1, palavras[-1]["fim"] - palavras[0]["inicio"]) if len(palavras) > 1 and transcrito else None

    return {
        "arquivo": os.path.abspath(caminho),
        "duracao_s": round(dur, 2),
        "analisado_s": round(dur_a, 2),
        "resolucao": f"{larg}x{alt}",
        "vertical": bool(larg and alt and alt > larg),
        "nota_forma": nota,
        "pontos": {k: [round(v, 1), m] for k, (v, m) in pts.items()},
        "gancho": {
            "primeira_fala_s": t0_fala,
            "primeiro_som_s": None if t0_som is None else round(t0_som, 1),
            "palavras_3s": n,
            "texto_3s": " ".join(w["texto"] for w in pal_gancho) if transcrito else None,
            "mudanca_visual_2s": mud_2s,
            "audio_gancho_db": round(db_g_m, 1),
            "audio_resto_db": round(db_r_m, 1),
            "pico_s": round(pico * BIN, 1),
        },
        "sustentacao": round(sustenta, 2),
        "palavras_por_minuto": None if wpm is None else round(wpm),
        "primeiro_quadro_escuro": bool(len(brilho) and brilho[0] < 0.06),
        "cortes_s": [round(t, 1) for t in cortes],
        "eventos_visuais_s": [round(t, 1) for t in eventos],
        "flashes_s": [round(t, 1) for t in flashes],
        "trechos_planos_s": planos,
        "pausas_fala_s": pausas,
        "curva": [round(float(c), 3) for c in curva],
        "transcricao": " ".join(w["texto"] for w in palavras) if transcrito else None,
        "palavras": palavras if transcrito else [],
        "transcrito": transcrito,
    }


def instantes_quadros(r, maximo=16):
    """Momentos para a folha de contato: gancho denso + cortes + amostras regulares."""
    d = r["analisado_s"]
    ts = [0.0, 0.5, 1.0, 2.0, 3.0]
    ts += [t + 0.15 for t in r["cortes_s"]]
    ts += [(a + z) / 2 for a, z in r["trechos_planos_s"]]
    passo = max(1.0, d / 8)
    t = 4.0
    while t < d:
        ts.append(t)
        t += passo
    ts.append(max(0, d - 0.6))
    ts = sorted({round(min(max(0, x), max(0, d - 0.4)), 1) for x in ts})
    # reduz mantendo o gancho e espalhando o resto
    if len(ts) > maximo:
        fixos = [x for x in ts if x <= 3.0]
        resto = [x for x in ts if x > 3.0]
        k = maximo - len(fixos)
        idx = np.linspace(0, len(resto) - 1, k).round().astype(int)
        ts = fixos + [resto[i] for i in sorted(set(idx))]
    return ts


def extrair_quadros(caminho, r, pasta):
    os.makedirs(pasta, exist_ok=True)
    feitos = []
    for i, t in enumerate(instantes_quadros(r)):
        saida = os.path.join(pasta, f"q{i:02d}_{t:05.1f}s.jpg")
        rot = f"drawtext=fontfile='{FONTE}':text='{t:.1f}s':x=12:y=12:fontsize=34:fontcolor=yellow:box=1:boxcolor=black@0.6:boxborderw=6"
        base = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", caminho, "-frames:v", "1"]
        try:
            rodar(base + ["-vf", f"scale=540:-2,{rot}", "-q:v", "3", saida])
        except RuntimeError:
            try:
                rodar(base + ["-vf", "scale=540:-2", "-q:v", "3", saida])
            except RuntimeError:
                continue
        if os.path.exists(saida):
            feitos.append(saida)
    folha = os.path.join(pasta, "folha.jpg")
    if not feitos:
        return feitos, None
    try:
        colunas = 4
        linhas = int(np.ceil(len(feitos) / colunas))
        rodar(["ffmpeg", "-v", "error", "-y"] + sum([["-i", f] for f in feitos], []) +
              ["-filter_complex",
               "".join(f"[{i}:v]scale=270:-2,setsar=1[v{i}];" for i in range(len(feitos))) +
               "".join(f"[v{i}]" for i in range(len(feitos))) +
               f"concat=n={len(feitos)}:v=1:a=0,tile={colunas}x{linhas}:padding=4:color=black",
               "-frames:v", "1", "-q:v", "3", folha])
    except RuntimeError:
        folha = None
    return feitos, folha


def fmt(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def sugestoes(r):
    s = []
    g, p = r["gancho"], r["pontos"]
    if g["primeira_fala_s"] is not None and g["primeira_fala_s"] > 0.4:
        s.append(f"A fala só começa em {g['primeira_fala_s']:.1f}s: corte o início para a primeira palavra cair antes de 0,3s.")
    if r["primeiro_quadro_escuro"]:
        s.append("O primeiro quadro é preto/escuro (entra com fade): é a primeira impressão no feed. Comece já com a imagem cheia.")
    if g["primeira_fala_s"] is None and p["visual_no_gancho"][0] < 12:
        s.append("Sem fala e com pouco movimento no início: abra com texto grande na tela ou uma ação já acontecendo.")
    if r["transcrito"] and g["palavras_3s"] < 5:
        s.append(f"Só {g['palavras_3s']} palavras nos 3 primeiros segundos: diga a promessa mais cedo ou acelere a abertura.")
    if g["palavras_3s"] > 15:
        s.append("Gancho atropelado: muitas palavras em 3s; corte para uma frase de impacto.")
    if not g["mudanca_visual_2s"] and p["visual_no_gancho"][0] < 14:
        s.append("Nenhuma mudança visual nos 2 primeiros segundos: ponha um zoom, um corte ou um texto entrando por volta de 1s.")
    if g["audio_gancho_db"] < g["audio_resto_db"] - 6:
        s.append("O áudio do gancho está bem mais baixo que o resto: suba o volume da abertura.")
    for a, z in r["trechos_planos_s"]:
        s.append(f"Trecho plano em {fmt(a)}–{fmt(z)}: corte, acelere, ou cubra com B-roll/zoom/texto.")
    for a, z in r["pausas_fala_s"][:8]:
        s.append(f"Pausa de {z - a:.1f}s na fala em {fmt(a)}: aperte para até 0,3s.")
    if r["sustentacao"] < 0.7:
        s.append("O vídeo perde muita energia depois do gancho: distribua mudanças visuais e falas de impacto pelo meio.")
    if len(r["flashes_s"]) > r["analisado_s"] / 3:
        s.append(f"{len(r['flashes_s'])} flashes em {r['analisado_s']:.0f}s: efeito saturado, guarde para os momentos-chave.")
    if r["palavras_por_minuto"] and r["palavras_por_minuto"] < 140:
        s.append(f"Ritmo de fala lento ({r['palavras_por_minuto']} ppm): apertar pausas ou acelerar 1,1x ajuda no Reels.")
    if not r["vertical"]:
        s.append("Vídeo não é vertical: para Reels/Shorts, reenquadre em 9:16.")
    return s


def svg_curva(r, w=640, h=140):
    c = r["curva"]
    n = len(c)
    if n < 2:
        return ""
    pts = " ".join(f"{i * w / (n - 1):.1f},{h - v * (h - 10) - 5:.1f}" for i, v in enumerate(c))
    d = r["analisado_s"]
    marcas = "".join(f'<line x1="{t / d * w:.1f}" y1="0" x2="{t / d * w:.1f}" y2="{h}" class="corte"/>' for t in r["cortes_s"])
    planos = "".join(f'<rect x="{a / d * w:.1f}" y="0" width="{(z - a) / d * w:.1f}" height="{h}" class="plano"/>' for a, z in r["trechos_planos_s"])
    gancho = f'<rect x="0" y="0" width="{min(1, GANCHO / d) * w:.1f}" height="{h}" class="gancho"/>'
    return (f'<svg viewBox="0 0 {w} {h}" class="curva" role="img" aria-label="Curva de estímulo">{gancho}{planos}{marcas}'
            f'<polyline points="{pts}" class="linha"/></svg>')


CSS = """
:root{--bg:#0f1115;--fg:#e8e8ea;--muted:#9aa0aa;--card:#181b22;--acc:#4ade80;--warn:#f59e0b;--bad:#ef4444;--line:#2a2f3a}
@media (prefers-color-scheme: light){:root{--bg:#f7f7f8;--fg:#15171c;--muted:#5b616c;--card:#fff;--line:#e3e5ea}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,sans-serif;margin:0;padding:24px 16px}
main{max-width:980px;margin:auto}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
.nota{font-size:56px;font-weight:700;line-height:1}.muted{color:var(--muted)}
.barra{height:8px;background:var(--line);border-radius:4px;overflow:hidden}.barra i{display:block;height:100%;background:var(--acc)}
table{width:100%;border-collapse:collapse}td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
.curva{width:100%;height:auto}.linha{fill:none;stroke:var(--acc);stroke-width:2}.corte{stroke:var(--warn);stroke-width:1;opacity:.6}
.plano{fill:var(--bad);opacity:.18}.gancho{fill:var(--acc);opacity:.08}img{max-width:100%;border-radius:8px}
li{margin:4px 0}
"""

NOMES = {"inicio_imediato": "Início imediato", "fala_no_gancho": "Fala no gancho (3 s)",
         "visual_no_gancho": "Visual no gancho", "audio_no_gancho": "Áudio no gancho",
         "sem_trechos_planos": "Sem trechos planos", "ritmo_visual": "Ritmo visual",
         "excesso_de_efeitos": "Penalidade: efeitos em excesso"}


def html_relatorio(r, folha_rel):
    linhas = "".join(
        f"<tr><td>{NOMES[k]}</td><td style='width:45%'><div class='barra'><i style='width:{(v / m * 100) if m else 0:.0f}%'></i></div></td>"
        f"<td>{v:.0f}{'/' + str(m) if m else ''}</td></tr>" for k, (v, m) in r["pontos"].items() if m or v)
    sug = "".join(f"<li>{html.escape(x)}</li>" for x in r["sugestoes"]) or "<li>Nada grave na forma.</li>"
    g = r["gancho"]
    texto = html.escape(g["texto_3s"] or "(sem transcrição)")
    folha = f"<h2>Quadros-chave</h2><img src='{html.escape(folha_rel)}' alt='Folha de contato'>" if folha_rel else ""
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Análise de gancho</title><style>{CSS}</style></head><body><main>
<h1>{html.escape(os.path.basename(r['arquivo']))}</h1><div class="muted">{r['duracao_s']}s · {r['resolucao']}</div>
<div class="card"><div class="nota">{r['nota_forma']}<span class="muted" style="font-size:20px">/100</span></div>
<div class="muted">Nota de forma (medições). Não avalia se a ideia é boa.</div></div>
<div class="card"><table>{linhas}</table></div>
<div class="card"><b>Gancho:</b> “{texto}”<br>
<span class="muted">1ª fala {g['primeira_fala_s']}s · {g['palavras_3s']} palavras em 3s · pico de estímulo {g['pico_s']}s · sustentação {r['sustentacao']}</span></div>
<h2>Curva de estímulo</h2><div class="card">{svg_curva(r)}
<div class="muted">verde claro = gancho · vermelho = trecho plano · laranja = corte/mudança</div></div>
<h2>Sugestões automáticas</h2><div class="card"><ul>{sug}</ul></div>{folha}
</main></body></html>"""


def html_comparativo(rs):
    rs = sorted(rs, key=lambda r: -r["nota_forma"])
    cab = "".join(f"<th>{NOMES[k]}</th>" for k in NOMES)
    lin = "".join(
        f"<tr><td>{i + 1}</td><td>{html.escape(os.path.basename(r['arquivo']))}</td><td><b>{r['nota_forma']}</b></td>"
        + "".join(f"<td>{r['pontos'][k][0]:.0f}</td>" for k in NOMES) + "</tr>" for i, r in enumerate(rs))
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Comparativo de ganchos</title><style>{CSS}</style></head><body><main><h1>Comparativo</h1>
<div class="card" style="overflow-x:auto"><table><tr><th>#</th><th>Vídeo</th><th>Nota</th>{cab}</tr>{lin}</table></div></main></body></html>"""


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--saida", default="analise_gancho")
    ap.add_argument("--modelo", default="small", help="modelo do faster-whisper (tiny, base, small, medium)")
    ap.add_argument("--sem-transcricao", action="store_true", help="detecta fala só pela energia do áudio")
    ap.add_argument("--max-segundos", type=float, default=180.0, help="analisa no máximo estes segundos")
    ap.add_argument("--sem-quadros", action="store_true", help="não extrai quadros-chave")
    args = ap.parse_args()

    os.makedirs(args.saida, exist_ok=True)
    resultados = []
    for v in args.videos:
        nome = os.path.splitext(os.path.basename(v))[0]
        print(f"→ analisando {nome} ...", file=sys.stderr)
        try:
            r = analisar(v, args)
        except (ValueError, RuntimeError) as e:
            print(f"\n## {nome} — pulado: {e}")
            continue
        r["sugestoes"] = sugestoes(r)
        folha_rel = None
        if not args.sem_quadros:
            quadros, folha = extrair_quadros(v, r, os.path.join(args.saida, nome + "_quadros"))
            r["quadros"] = [os.path.abspath(q) for q in quadros]
            r["folha"] = os.path.abspath(folha) if folha else None
            folha_rel = os.path.relpath(folha, args.saida).replace("\\", "/") if folha else None
        with open(os.path.join(args.saida, nome + ".json"), "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
        with open(os.path.join(args.saida, nome + ".html"), "w", encoding="utf-8") as f:
            f.write(html_relatorio(r, folha_rel))
        resultados.append(r)

        g = r["gancho"]
        print(f"\n## {nome} — nota de forma {r['nota_forma']}/100")
        for k, (val, m) in r["pontos"].items():
            if m or val:
                print(f"- {NOMES[k]}: {val:.0f}" + (f"/{m}" if m else ""))
        print(f"- Gancho: “{g['texto_3s'] or '—'}” (1ª fala {g['primeira_fala_s']}s, {g['palavras_3s']} palavras em 3s)")
        print(f"- Cortes: {len(r['cortes_s'])} · eventos visuais: {len(r['eventos_visuais_s'])} · flashes: {len(r['flashes_s'])} · trechos planos: {len(r['trechos_planos_s'])}"
              f" · pausas >0,7s: {len(r['pausas_fala_s'])} · sustentação {r['sustentacao']}")
        for x in r["sugestoes"]:
            print(f"  • {x}")
        if r.get("folha"):
            print(f"- Folha de contato: {r['folha']}")

    if len(resultados) > 1:
        with open(os.path.join(args.saida, "comparativo.html"), "w", encoding="utf-8") as f:
            f.write(html_comparativo(resultados))
        print("\n## Ranking")
        for i, r in enumerate(sorted(resultados, key=lambda r: -r["nota_forma"])):
            print(f"{i + 1}. {os.path.basename(r['arquivo'])}: {r['nota_forma']}")
    print(f"\nRelatórios em: {os.path.abspath(args.saida)}")


if __name__ == "__main__":
    main()
