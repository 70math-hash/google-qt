#!/usr/bin/env python3
"""Testa o puxar_dados.py sem tocar na rede.

Monta respostas do PostgREST a partir dos fixtures de agosto, no mesmo formato
que a API devolve de verdade (deslocamento -03:00 e zeros a direita cortados nos
microssegundos), serve essas respostas no lugar do urlopen, e confere que o
cliques.json que sai e identico ao que o fixtures/gerar.py produz.

    python3 acoes/teste_puxar_dados.py
"""
import csv, io, json, os, pathlib, subprocess, sys, tempfile, datetime as dt
import urllib.request, urllib.parse

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FIX = RAIZ / "fixtures"


def canonico(ts):
    """Imita o PostgREST: -03:00 e sem zeros a direita na fracao."""
    frac = ts.strftime("%f").rstrip("0")
    base = ts.strftime("%Y-%m-%dT%H:%M:%S")
    return f"{base}.{frac}-03:00" if frac else f"{base}-03:00"


uas = dict(l.split("\t", 1) for l in (FIX / "ua_map.txt").read_text(encoding="utf-8").splitlines() if l.strip())
frac = dict(p.split(":") for p in (FIX / "microssegundos.txt").read_text().split())

cliques_api = []
with open(FIX / "cliques_raw.csv", encoding="utf-8") as fh:
    for cid, garcom, momento, idx in csv.reader(fh):
        ts = dt.datetime.strptime(f"{momento}.{frac[cid]}", "%Y-%m-%d %H:%M:%S.%f")
        cliques_api.append({"id": int(cid), "garcom": garcom,
                            "criado_em": canonico(ts), "user_agent": uas[idx]})

agora = dt.datetime.now()
sync_api = [{"ok": True, "executado_em": canonico(agora.replace(hour=7, minute=0, second=0, microsecond=0)),
             "nota_exibida": 4.199999809265137, "total_api": 946}]
avaliacoes_api = [{"review_id": "r1", "nota": 5,
                   "criado_em": canonico(dt.datetime(2026, 8, 6, 18, 20, 20, 287841)),
                   "atualizado_em": None, "cliente": "Clara S.",
                   "tem_texto": False, "respondida": False, "nota_anterior": None}]

RESPOSTAS = {"cliques_avaliacao": cliques_api,
             "avaliacoes_sync": sync_api,
             "avaliacoes": avaliacoes_api}


class FalsaResposta(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def falso_urlopen(req, timeout=None):
    caminho = urllib.parse.urlparse(req.full_url).path
    tabela = caminho.rsplit("/", 1)[-1]
    inicio = int(req.headers.get("Range", "0-999").split("-")[0])
    dados = RESPOSTAS[tabela][inicio:inicio + 1000]
    return FalsaResposta(json.dumps(dados).encode())


def main():
    urllib.request.urlopen = falso_urlopen
    trabalho = pathlib.Path(tempfile.mkdtemp(prefix="qt-puxar-"))
    os.environ.setdefault("SUPABASE_URL", "https://exemplo.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "chave-de-teste")
    anterior = os.getcwd()
    os.chdir(trabalho)
    try:
        codigo = (RAIZ / "acoes" / "puxar_dados.py").read_text(encoding="utf-8")
        exec(compile(codigo, "puxar_dados.py", "exec"), {"__name__": "__main__"})
    finally:
        os.chdir(anterior)

    obtido = json.loads((trabalho / "cliques.json").read_text(encoding="utf-8"))

    esperado_dir = pathlib.Path(tempfile.mkdtemp(prefix="qt-esperado-"))
    subprocess.run([sys.executable, str(FIX / "gerar.py"), str(esperado_dir)],
                   check=True, capture_output=True)
    esperado = json.loads((esperado_dir / "cliques.json").read_text(encoding="utf-8"))
    # o gerar.py corta em 24/08; o puxar_dados le a base toda
    por_id = {c["id"]: c for c in obtido}
    falhas = []
    for e in esperado:
        o = por_id.get(e["id"])
        if o is None:
            falhas.append(f"clique {e['id']} nao veio")
        elif o != e:
            falhas.append(f"clique {e['id']}: esperado {e}, obtido {o}")

    print(f"cliques lidos pelo puxar_dados: {len(obtido)}")
    print(f"cliques conferidos contra o fixture: {len(esperado)}")
    print(f"perfil.json: {(trabalho / 'perfil.json').read_text(encoding='utf-8')[:120]}")
    if falhas:
        print(f"\n{len(falhas)} divergencia(s):")
        for f in falhas[:5]:
            print("  -", f)
        return 1
    print("\nTudo bate: momento, microssegundos, garcom e user agent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
