#!/usr/bin/env python3
"""Sobe a planilha no Drive e registra a rodada em public.relatorio_diario.

    python3 acoes/subir_drive.py QT_escaneamentos_2026-08-26.xlsx resumo.json

Sobe por upload multipart da API do Drive, com os bytes indo como binario. E a
diferenca que importa: a tarefa do Claude precisava passar o arquivo inteiro em
base64 dentro de um parametro de ferramenta, e com 55 mil caracteres o conteudo
era truncado sem aviso (ver NOTAS, secao 10).

Confere o tamanho que o Drive devolve contra o local, e tenta de novo uma vez se
divergir. Grava a linha em relatorio_diario mesmo quando falha, porque e de la
que a tarefa diaria tira o que escrever, inclusive a mensagem de erro.

Env: GBP_CLIENT_ID, GBP_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN, DRIVE_PASTA_ID,
     SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import json, os, sys, uuid, datetime as dt, zoneinfo
import urllib.request, urllib.error, urllib.parse

SP = zoneinfo.ZoneInfo("America/Sao_Paulo")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SUPA = os.environ["SUPABASE_URL"].rstrip("/")
CHAVE = os.environ["SUPABASE_SERVICE_ROLE_KEY"]


def token_de_acesso():
    corpo = urllib.parse.urlencode({
        "client_id": os.environ["GBP_CLIENT_ID"],
        "client_secret": os.environ["GBP_CLIENT_SECRET"],
        "refresh_token": os.environ["GDRIVE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=corpo,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["access_token"]


def sobe(caminho, nome, pasta, token):
    """Upload multipart. Os bytes vao como binario, nunca como texto."""
    dados = open(caminho, "rb").read()
    limite = uuid.uuid4().hex
    meta = json.dumps({"name": nome, "parents": [pasta]}).encode()
    corpo = (
        f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
        + meta
        + f"\r\n--{limite}\r\nContent-Type: {XLSX}\r\n\r\n".encode()
        + dados
        + f"\r\n--{limite}--\r\n".encode()
    )
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/drive/v3/files"
        "?uploadType=multipart&fields=id,name,size,webViewLink",
        data=corpo,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": f"multipart/related; boundary={limite}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def registra(linha):
    corpo = json.dumps(linha, ensure_ascii=False).encode()
    req = urllib.request.Request(
        f"{SUPA}/rest/v1/relatorio_diario", data=corpo,
        headers={"apikey": CHAVE, "Authorization": f"Bearer {CHAVE}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"})
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()


def main():
    caminho, resumo_json = sys.argv[1], sys.argv[2]
    nome = os.path.basename(caminho)
    local = os.path.getsize(caminho)
    resumo = json.load(open(resumo_json, encoding="utf-8"))
    # o mesmo "ontem" que o build usa, sem passar por string: montar a data a
    # partir de "25/08" mais o ano corrente erra na virada do ano.
    data_ref = dt.datetime.now(SP).date() - dt.timedelta(days=1)

    erro, arquivo = None, None
    for tentativa in (1, 2):
        try:
            token = token_de_acesso()
            arquivo = sobe(caminho, nome, os.environ["DRIVE_PASTA_ID"], token)
            remoto = int(arquivo.get("size") or 0)
            if remoto == local:
                erro = None
                break
            erro = (f"tamanho divergente na tentativa {tentativa}: "
                    f"local {local}, Drive {remoto}")
            print(erro, file=sys.stderr)
            arquivo = None
        except urllib.error.HTTPError as e:
            erro = f"HTTP {e.code} na tentativa {tentativa}: {e.read()[:300].decode('utf-8', 'replace')}"
            print(erro, file=sys.stderr)
        except Exception as e:                                  # noqa: BLE001
            erro = f"falha na tentativa {tentativa}: {e}"
            print(erro, file=sys.stderr)

    registra({
        "data_ref": data_ref.isoformat(),
        "ok": arquivo is not None,
        "resumo": resumo,
        "planilha_url": (arquivo or {}).get("webViewLink"),
        "planilha_nome": nome if arquivo else None,
        "planilha_bytes": local,
        "erro": erro,
    })

    if arquivo is None:
        print(f"FALHA no upload: {erro}", file=sys.stderr)
        sys.exit(1)
    print(f"subiu {nome}, {local} bytes, conferido: {arquivo['webViewLink']}")


if __name__ == "__main__":
    main()
