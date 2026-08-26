Gere o relatório diário de escaneamentos e avaliações da QT Pizza Bar e a planilha do período. Entregue o relatório como texto direto na conversa e a planilha no Google Drive.

Carregue as ferramentas antes de usar, numa única chamada:
ToolSearch `select:mcp__Supabase__execute_sql,
mcp__Google_Drive__search_files,
mcp__Google_Drive__get_file_metadata,
mcp__Google_Drive__download_file_content,
mcp__Google_Drive__create_file,
mcp__Google_Drive__update_file`

Use SOMENTE essas ferramentas. Se precisar de qualquer outra, pare e registre a falha no relatório em vez de solicitá-la.

## 1. Puxar a base de cliques

Projeto Supabase `helinoirdizwrluydkzp`:

    select coalesce(json_agg(t order by t.criado_em), '[]'::json) as dados from (
      select id, garcom,
             to_char(criado_em at time zone 'America/Sao_Paulo','YYYY-MM-DD HH24:MI:SS.US') as momento,
             coalesce(user_agent,'') as ua, criado_em
      from cliques_avaliacao
    ) t;

Grave o array retornado em `cliques.json`, no diretório de trabalho, exatamente como veio, com as chaves `id`, `garcom`, `momento` e `ua`.

**Os microssegundos no `momento` não são enfeite.** O corte de repetição compara intervalos de até 10 segundos. Truncado em segundo, o mesmo agosto acusa 19 repetições onde há 16, porque um intervalo real de 10,4s aparece como 10s e o clique é descontado sem ser repetição. O `.US` no `to_char` é obrigatório.

## 2. Puxar as avaliações publicadas

São dois SELECT no mesmo projeto. A sincronização com o Google **não roda mais aqui**: quem busca as avaliações é a Edge Function `sincroniza-avaliacoes`, agendada no próprio Supabase (`cron.job` `sincroniza-avaliacoes-diario`, 10h00 UTC, que é 07h00 de São Paulo). Esta tarefa só lê o resultado.

    select coalesce(json_agg(t order by t.criado_em), '[]'::json) as dados from (
      select review_id, nota,
             to_char(criado_em at time zone 'America/Sao_Paulo','YYYY-MM-DD HH24:MI:SS.US') as criado_em,
             to_char(atualizado_em at time zone 'America/Sao_Paulo','YYYY-MM-DD HH24:MI:SS.US') as atualizado_em,
             coalesce(cliente,'') as cliente, tem_texto, respondida, nota_anterior
      from avaliacoes
      where criado_em >= now() - interval '120 days'
    ) t;

Grave em `avaliacoes.json`.

    select json_build_object(
      'nota_exibida', round(nota_exibida::numeric, 1),
      'total_avaliacoes', total_api,
      'sincronizado_em', to_char(executado_em at time zone 'America/Sao_Paulo','YYYY-MM-DD HH24:MI')
    ) as perfil
    from avaliacoes_sync
    where ok order by executado_em desc limit 1;

Grave o objeto retornado em `perfil.json`.

**Confira a data de `sincronizado_em`.** Se a última sincronização bem-sucedida não for de hoje, os dados de avaliação estão velhos: grave `avaliacoes.json` como `[]`, siga para o passo 3 e registre no relatório que a sincronização não rodou, com a data da última que rodou.

**Se qualquer um dos SELECT falhar**, não interrompa a rodada. Grave `avaliacoes.json` como `[]`, siga para o passo 3, e registre a falha no relatório e na notificação. O relatório de escaneamentos sozinho continua tendo valor; o de avaliações é acréscimo.

Para nomear a causa em vez de dizer só "erro", olhe a última linha de `avaliacoes_sync`:

    select ok, executado_em, baixadas, inseridas, alteradas, left(erro, 300) as erro
    from avaliacoes_sync order by executado_em desc limit 3;

`invalid_grant` no campo `erro` significa refresh token expirado. Enquanto a tela de consentimento OAuth estiver em modo *Testing*, o token morre a cada 7 dias e isso vai acontecer toda semana; não é bug de código. `403` significa API desabilitada no projeto `685524545181`. `LISTAGEM VAZIA` com `n_reviews=0` significa que a função rodou fora da região `sa-east-1`: de us-east-1 o Google devolve 200 com 69 bytes e nenhuma avaliação.

## 3. Baixar o script e gerar a planilha

Baixe com `download_file_content` o arquivo de id `1cel_jwKuzsJeB9LOktB6KegKYnN1bpvp`, decodifique o base64 e salve como `build.py`. Esse script é a definição oficial da planilha, não reescreva nem improvise uma versão própria.

    python3 build.py QT_escaneamentos_AAAA-MM-DD.xlsx

Use a data de hoje em São Paulo no nome. Depois recalcule, passo obrigatório, senão as fórmulas chegam sem valor em cache e a planilha abre com células vazias:

    python3 /root/.claude/skills/xlsx/scripts/recalc.py QT_escaneamentos_AAAA-MM-DD.xlsx

O recalc precisa terminar com `"status": "success"` e `"total_errors": 0`. Se acusar erro, relate e não suba o arquivo.

O `build.py` imprime um JSON no final. É dele que sai todo o texto do relatório. Não recalcule nada por fora: o script já aplica o desconto de repetição e o pareamento, e usar outra fonte faria o texto discordar da planilha.

## 4. Subir para o Drive

Leia o .xlsx em base64 e envie com `create_file`:

- `parentId`: `14Iv1VAMACSXY100eKp4g495OYPTsGgS0`
- `contentMimeType`: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- `disableConversionToGoogleType`: `true`
- `title`: o mesmo nome do arquivo

Guarde o `viewUrl` que a resposta devolve, para citar no relatório.

## 5. Escrever o relatório

Use o bloco `relatorio` do JSON impresso pelo script.

1. Título com `dia_semana_ontem` e `data_ontem`.
2. **Ontem por atendente**: uma linha por pessoa a partir de `ontem_por_atendente`, na ordem em que vier, incluindo quem está em zero. Cada linha traz **escaneamentos** e, entre parênteses, **quantos viraram avaliação publicada**.
3. **Total da casa**: os cinco valores de `totais_da_casa`, rotulados como hoje, ontem, últimos 7 dias (inclui hoje), mês corrente e total acumulado.
4. **Conversão de ontem**: `conversao_ontem`, escaneamentos que viraram avaliação, e a média das notas em `media_notas_ontem`.
5. **Nota da casa no Google**: `nota_exibida` e `total_avaliacoes` de `perfil_google`.
6. Uma linha com `ultimo_escaneamento`, nome e horário.
7. Uma linha com o link da planilha no Drive.
8. Se `descontados` for maior que zero, uma linha dizendo quantos cliques foram descontados como toque repetido.
9. Se `orfas_ontem` for maior que zero, uma linha dizendo quantas avaliações entraram sem escaneamento correspondente.
10. Se `notas_alteradas` não estiver vazio, uma linha por avaliação cuja nota mudou desde a última rodada, com a nota antiga e a nova.

O campo `regra_do_zero` decide o fecho, e ele já vem resolvido pelo script:

- `normal`: relatório completo, sem comentário extra.
- `sem_historico`: escreva que a série ainda não tem histórico e que a primeira leitura comparável sai no relatório seguinte. Sem alarme.
- `segunda_fechada`: escreva apenas que não houve escaneamento na véspera porque a casa fecha na segunda. Sem alarme.
- `zero_operacao`: registre que zerou num dia de operação e sinalize para conferir os QR codes nas mesas e a página de destino.
- `vazio`: diga que a base não retornou registro nenhum e que vale checar.
- `sem_avaliacoes`: o passo 2 não trouxe avaliação. Escreva o relatório de escaneamentos normalmente e registre numa linha que os dados de avaliação não entraram nesta rodada, nomeando a causa.

O campo `avaliacoes_ausentes` vem separado de propósito: numa segunda-feira sem escaneamento e sem sincronização, `regra_do_zero` é `segunda_fechada` e `avaliacoes_ausentes` é `true`. Registre as duas coisas.

### Regras de redação, obrigatórias

São **três números diferentes** e cada um tem nome próprio. Nunca use um no lugar do outro, e nunca deixe um sozinho representando os três:

| Termo | O que é |
|---|---|
| **escaneamento** | QR code lido, líquido de repetição |
| **avaliação publicada** | avaliação que apareceu no perfil do Google |
| **nota da casa** | média exibida no Google, sobre toda a base histórica |

O cliente pode ler o código e não escrever nada, então escaneamento nunca vira sinônimo de avaliação. E a nota da casa se move devagar sobre centenas de avaliações antigas, então não a apresente como resultado do dia.

Linguagem técnica e direta, sem emoji, sem elogio, sem recomendação que o dado não sustente. Nunca atribua uma nota baixa a um atendente específico: o pareamento serve para creditar, não para culpar, e cliente insatisfeito costuma avaliar fora da janela.

## 6. Notificação, passo obrigatório

Chame PushNotification com `status` igual a `proactive` e uma linha de até 200 caracteres, sem markdown:

    QT 06/08: 16 escaneamentos, 11 viraram avaliacao (69%). clara 12/9, thalia 4/2, alexandre 0. Nota 4,2. Planilha no Drive.

Nos casos de exceção, use a linha curta equivalente:

    QT 10/08: zero escaneamentos, casa fechada na segunda.
    QT 12/08: zero escaneamentos num dia de operacao, conferir os QR nas mesas.
    QT 07/08: 23 escaneamentos. Dados de avaliacao fora nesta rodada, sincronizacao nao rodou.
    QT 09/08: falha ao gerar o relatorio, base ou Drive fora do ar.

Envie sempre, inclusive quando o total for zero e inclusive quando algo falhar. É o canal que alcança o Matheus fora do aplicativo, então rodada sem notificação é rodada perdida.

---

## Anexo — o que o `build.py` v2 já faz

Implementado e conferido contra agosto de 2026. Mantidos da v1: `JANELA_S = 10` com chave `(garcom, ua)`, a reconstrução integral a cada execução, as abas Diário, Matriz, Atendentes, Base e Leitura, e a identidade visual.

**Acrescentado:**

1. Lê `avaliacoes.json` e `perfil.json` se existirem. Ausentes ou vazios, o script roda como a v1 rodava e devolve `regra_do_zero = "sem_avaliacoes"` com `avaliacoes_ausentes = true`.

2. Pareamento 1 para 1 entre escaneamento e avaliação, sobre a lista já líquida de repetições:
   - avaliações do dia em ordem de `criado_em`;
   - para cada uma, os escaneamentos **ainda não consumidos** na janela `[t − 10 min, t]`;
   - atribuir o **mais próximo** e marcar o escaneamento como consumido;
   - sem candidato, a avaliação é **órfã**;
   - escaneamento não consumido ao fim do dia é **perdido**.

   A janela de 10 minutos foi medida, não arbitrada: mediana de 54 segundos entre o escaneamento e o envio, p95 em 6,4 minutos, e nenhuma ocorrência entre 20 e 60 minutos.

3. Colunas novas em Diário e Atendentes: `viraram_nota`, `perdidos`, `conversao`, `media_notas`. Matriz, Atendentes e Pagamento seguem sendo fórmulas sobre Diário e Pareamento.

4. Aba **Pareamento**, uma linha por par com atendente, hora do escaneamento, hora da avaliação, defasagem em minutos, nota e se tem texto. É a aba de auditoria de pagamento. As avaliações órfãs vão num bloco separado no pé da mesma aba.

5. Aba **Pagamento**, com os parâmetros em células editáveis (R$ 2,00 por avaliação, R$ 50,00 por lote de 40) e o cálculo por atendente em fórmula, nunca em número fixo.

6. `notas_alteradas` sai de duas fontes: a coluna `nota_anterior`, que a Edge Function grava quando a nota de um `review_id` conhecido muda, e um estado local `avaliacoes_estado.json`, útil quando o script roda em host que guarda arquivo. Em agosto, 135 das 944 avaliações têm `atualizado_em` diferente de `criado_em`.

7. Escaneamento antes das 18h fica marcado como `teste` na aba Base. O JSON traz `scans_teste` e `conversao_sem_teste` ao lado de `conversao`, porque os dois denominadores são defensáveis e a escolha é do Matheus, não do script.

8. Campos novos no JSON de saída: `conversao_ontem`, `media_notas_ontem`, `orfas_ontem`, `viraram_nota_ontem`, `scans_teste_ontem`, `notas_alteradas`, `perfil_google` (com `nota_exibida` e `total_avaliacoes`), `avaliacoes_ausentes`, o bloco `periodo`, e `viraram_nota` dentro de cada item de `ontem_por_atendente`.

**Referência de layout:** a planilha `QT-scans-x-avaliacoes-agosto.xlsx` tem as abas no formato esperado, já preenchidas com agosto de 2026.

**Validação:** `python3 validar.py` roda o build sobre os dados de agosto e confere contra os números medidos: 196 cliques brutos, 16 descontados, 180 contados, 126 avaliações, 112 pares, 14 órfãs, 68 perdidos, conversão de 62,2%, e a tabela por atendente com o total de R$ 324.
