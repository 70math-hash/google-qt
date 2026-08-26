#!/usr/bin/env python3
"""Puxa do Supabase o que o build_planilha_escaneamentos.py precisa.

Escreve no diretorio corrente:
  cliques.json     lista de {id, garcom, momento, ua}
  avaliacoes.json  lista de {review_id, nota, criado_em, atualizado_em, cliente, ...}
  perfil.json      {nota_exibida, total_avaliacoes, sincronizado_em}

Roda no GitHub Actions, que tem rede. O container da tarefa do Claude nao tem,
e por isso ela nao consegue mais fazer este passo (ver NOTAS, secao 10).

Os horarios saem em America/Sao_Paulo COM microssegundos. Truncar em segundo
faz o corte de repeticao acusar 19 descontados onde ha 16, porque intervalos
reais de 10,4s viram 10s.

Variaveis de ambiente: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import json, os, sys, datetime as dt, zoneinfo, urllib.parse
import urllib.request

SP = zoneinfo.ZoneInfo("America/Sao_Paulo")
URL = os.environ["SUPABASE_URL"].rstrip("/")
CHAVE = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PAGINA = 1000


def busca(tabela, colunas, ordem, filtro=""):
    """Le a tabela inteira, paginando. PostgREST corta em 1000 por padrao."""
    linhas, inicio = [], 0
    while True:
        q = urllib.parse.urlencode({"select": colunas, "order": ordem})
        endereco = f"{URL}/rest/v1/{tabela}?{q}{filtro}"
        req = urllib.request.Request(endereco, headers={
            "apikey": CHAVE,
            "Authorization": f"Bearer {CHAVE}",
            "Range-Unit": "items",
            "Range": f"{inicio}-{inicio + PAGINA - 1}",
        })
        with urllib.request.urlopen(req, timeout=60) as r:
            lote = json.load(r)
        linhas.extend(lote)
        if len(lote) < PAGINA:
            return linhas
        inicio += PAGINA


def em_sp(iso):
    """'2026-08-25T22:12:59.915066+00:00' -> datetime em Sao Paulo."""
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    return dt.datetime.fromisoformat(iso).astimezone(SP)


def carimbo(iso):
    return em_sp(iso).strftime("%Y-%m-%d %H:%M:%S.%f")


# ---- cliques
cru = busca("cliques_avaliacao", "id,garcom,criado_em,user_agent", "criado_em.asc")
cliques = [{"id": c["id"], "garcom": c["garcom"],
            "momento": carimbo(c["criado_em"]),
            "ua": c.get("user_agent") or ""} for c in cru]
if not cliques:
    print("AVISO: cliques_avaliacao voltou vazia", file=sys.stderr)

# ---- perfil e frescor da sincronizacao
sync = busca("avaliacoes_sync", "ok,executado_em,nota_exibida,total_api",
             "executado_em.desc", "&ok=is.true&limit=1")
perfil, fresca = {}, False
if sync:
    s = sync[0]
    quando = em_sp(s["executado_em"])
    fresca = quando.date() == dt.datetime.now(SP).date()
    perfil = {
        "nota_exibida": round(s["nota_exibida"], 1) if s.get("nota_exibida") is not None else None,
        "total_avaliacoes": s.get("total_api"),
        "sincronizado_em": quando.strftime("%Y-%m-%d %H:%M"),
        "sincronizacao_de_hoje": fresca,
    }

# ---- avaliacoes
# So faz sentido puxar avaliacao que pode parear com algum escaneamento, entao a
# janela comeca no primeiro clique da base. Puxar 120 dias trazia meses de
# avaliacao que nunca teria par e so engordava a planilha.
avaliacoes = []
if not fresca:
    print("AVISO: ultima sincronizacao bem-sucedida nao e de hoje. "
          "Rodando sem avaliacoes, como manda a regra de dado velho.", file=sys.stderr)
elif cliques:
    primeiro = min(c["momento"] for c in cliques)[:10]
    corte = (dt.date.fromisoformat(primeiro) - dt.timedelta(days=1)).isoformat()
    cru = busca("avaliacoes",
                "review_id,nota,criado_em,atualizado_em,cliente,tem_texto,respondida,nota_anterior",
                "criado_em.asc", f"&criado_em=gte.{corte}")
    for a in cru:
        avaliacoes.append({
            "review_id": a["review_id"], "nota": a["nota"],
            "criado_em": carimbo(a["criado_em"]),
            "atualizado_em": carimbo(a["atualizado_em"] or a["criado_em"]),
            "cliente": a.get("cliente") or "",
            "tem_texto": bool(a.get("tem_texto")),
            "respondida": bool(a.get("respondida")),
            "nota_anterior": a.get("nota_anterior"),
        })

for nome, dados in (("cliques.json", cliques),
                    ("avaliacoes.json", avaliacoes),
                    ("perfil.json", perfil)):
    with open(nome, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, ensure_ascii=False)

print(f"cliques.json {len(cliques)} | avaliacoes.json {len(avaliacoes)} | "
      f"sincronizacao de hoje: {fresca}")
