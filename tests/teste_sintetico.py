"""Testes com vídeos sintéticos: confere se a nota reage na direção certa.

Gera com ffmpeg (sem baixar nada) cinco vídeos de 8 s:
  dinamico   - movimento, cortes a cada 2 s, som desde 0 s
  parado     - imagem fixa, 2 s de silêncio no início
  buraco     - dinâmico, mas com 3 s parados e mudos no meio
  flashes    - dinâmico, com 12 flashes brancos
  tremido    - uma cena só, com câmera balançando (não pode virar "corte")
e roda o analisador sem transcrição (rápido). Uso: python tests/teste_sintetico.py
"""
import json
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(AQUI, "..", "scripts", "analisar_gancho.py")
VID = "-c:v libx264 -pix_fmt yuv420p -r 30 -c:a aac -ar 48000 -ac 1 -shortest".split()


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def gerar(pasta):
    p = lambda n: os.path.join(pasta, n + ".mp4")
    tom = "sine=frequency=220:sample_rate=48000,volume=0.5"
    # dinâmico: 4 blocos de 2 s com padrões diferentes (cortes), som contínuo
    fontes = ["testsrc2=s=540x960:r=30", "mandelbrot=s=540x960:r=30", "life=s=540x960:r=30:mold=10:ratio=0.1",
              "testsrc=s=540x960:r=30"]
    entradas = sum([["-f", "lavfi", "-t", "2", "-i", f] for f in fontes], [])
    ff(*entradas, "-f", "lavfi", "-t", "8", "-i", tom, "-filter_complex",
       "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0,format=yuv420p[v]", "-map", "[v]", "-map", "4:a", *VID, p("dinamico"))
    # parado: cor fixa, 2 s de silêncio, depois tom
    ff("-f", "lavfi", "-t", "8", "-i", "color=c=gray:s=540x960:r=30", "-f", "lavfi", "-t", "8", "-i", tom,
       "-af", "volume='if(lt(t,2),0,1)':eval=frame", *VID, p("parado"))
    # buraco: dinâmico com 3 s congelados e mudos de 3 a 6 s
    ff("-i", p("dinamico"), "-filter_complex",
       "[0:v]trim=0:3,setpts=PTS-STARTPTS[a];[0:v]trim=3:3.04,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=3[b];"
       "[0:v]trim=6:8,setpts=PTS-STARTPTS[c];[a][b][c]concat=n=3:v=1:a=0[v]",
       "-map", "[v]", "-map", "0:a", "-af", "volume='if(between(t,3,6),0,1)':eval=frame", *VID, p("buraco"))
    # flashes: brilho estoura 12 vezes (1 quadro a cada ~0,66 s)
    ff("-i", p("dinamico"), "-vf", "eq=brightness='if(lt(mod(t,0.66),0.07),0.6,0)':eval=frame", "-c:a", "copy",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", p("flashes"))
    # tremido: mesma cena sem cortes, câmera balançando como celular na mão
    ff("-f", "lavfi", "-t", "8", "-i", "testsrc2=s=700x1200:r=30", "-f", "lavfi", "-t", "8", "-i", tom,
       "-vf", "crop=540:960:80+40*sin(t*7)+25*sin(t*13):120+40*cos(t*5)+20*sin(t*17)", *VID, p("tremido"))
    return {n: p(n) for n in ["dinamico", "parado", "buraco", "flashes", "tremido"]}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    with tempfile.TemporaryDirectory() as pasta:
        vids = gerar(pasta)
        saida = os.path.join(pasta, "saida")
        subprocess.run([sys.executable, SCRIPT, *vids.values(), "--saida", saida, "--sem-transcricao"],
                       check=False, capture_output=False, stdout=subprocess.DEVNULL)
        r = {n: json.load(open(os.path.join(saida, n + ".json"), encoding="utf-8")) for n in vids}

    notas = {n: x["nota_forma"] for n, x in r.items()}
    print("notas:", notas)
    falhas = []

    def checar(cond, msg):
        print(("ok    " if cond else "FALHA ") + msg)
        if not cond:
            falhas.append(msg)

    checar(notas["dinamico"] >= notas["parado"] + 30, "dinâmico tem nota bem maior que parado")
    checar(notas["dinamico"] > notas["buraco"], "buraco no meio derruba a nota")
    checar(len(r["dinamico"]["cortes_s"]) >= 2, f"detecta cortes do dinâmico ({r['dinamico']['cortes_s']})")
    checar(r["parado"]["cortes_s"] == [], "não inventa cortes em imagem fixa")
    checar(r["tremido"]["cortes_s"] == [], f"câmera na mão não vira corte ({r['tremido']['cortes_s']})")
    checar(len(r["tremido"]["eventos_visuais_s"]) <= 2, f"tremor contínuo não vira evento ({r['tremido']['eventos_visuais_s']})")
    checar(any("começa" in s or "movimento no início" in s for s in r["parado"]["sugestoes"]),
           "parado recebe sugestão sobre o início")
    checar(any(a <= 3.5 and z >= 5.5 for a, z in r["buraco"]["trechos_planos_s"]),
           f"acha o trecho plano de 3–6 s ({r['buraco']['trechos_planos_s']})")
    checar(len(r["flashes"]["flashes_s"]) >= 8, f"conta os flashes ({len(r['flashes']['flashes_s'])})")
    checar(any("flashes" in s for s in r["flashes"]["sugestoes"]), "avisa excesso de flashes")
    checar(notas["flashes"] < notas["dinamico"], "flashes em excesso tiram nota em vez de somar")
    checar(all(os.path.basename(x["folha"] or "") == "folha.jpg" for x in r.values()), "gera folha de contato")
    print("\nTODOS OS TESTES PASSARAM" if not falhas else f"\n{len(falhas)} FALHA(S)")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
