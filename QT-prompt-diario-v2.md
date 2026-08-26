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

    select json_agg(t order by t.criado_em) as dados from (
      select id, garcom,
             to_char(criado_em at time zone 'America/Sao_Paulo','YYYY-MM-DD HH24:MI:SS') as momento,
             coalesce(user_agent,'') as ua, criado_em
      from cliques_avaliacao
    ) t;

Grave o array retornado em `cliques.json`, no diretório de trabalho, exatamente como veio, com as chaves `id`, `garcom`, `momento` e `ua`.

## 2. Puxar as avaliações publicadas

Baixe com `download_file_content` o arquivo de id `<ID_DO_FETCH_REVIEWS>`, decodifique o base64 e salve como `fetch_reviews.py`. Rode:

    python3 fetch_reviews.py

Ele lê as credenciais OAuth das variáveis de ambiente `GBP_CLIENT_ID`, `GBP_CLIENT_SECRET` e `GBP_REFRESH_TOKEN`, chama `reviews.list` da Google Business Profile API paginando de 50 em 50, e grava `avaliacoes.json` com uma entrada por avaliação: `reviewId`, `nota`, `criado_em`, `atualizado_em`, `cliente`, `tem_texto`, `respondida`.

**Se esta etapa falhar**, não interrompa a rodada. Grave `avaliacoes.json` como `[]`, siga para o passo 3, e registre a falha no relatório e na notificação. O relatório de escaneamentos sozinho continua tendo valor; o de avaliações é acréscimo.

Causas prováveis de falha, para nomear no relatório em vez de dizer só "erro": `401` significa token expirado, e se o app OAuth ainda estiver em modo *Testing* o refresh token morre a cada 7 dias. `403` significa API desabilitada no projeto `685524545181`.

## 3. Baixar o script e gerar a planilha

Baixe com `download_file_content` o arquivo de id `1AHv9xdMrcg__gE_V5bk61cYZ4wnYwkfj`, decodifique o base64 e salve como `build.py`. Esse script é a definição oficial da planilha, não reescreva nem improvise uma versão própria.

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
- `sem_avaliacoes`: a etapa 2 falhou. Escreva o relatório de escaneamentos normalmente e registre numa linha que os dados de avaliação não entraram nesta rodada, nomeando a causa.

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
    QT 07/08: 23 escaneamentos. Dados de avaliacao fora nesta rodada, token expirado.
    QT 09/08: falha ao gerar o relatorio, base ou Drive fora do ar.

Envie sempre, inclusive quando o total for zero e inclusive quando algo falhar. É o canal que alcança o Matheus fora do aplicativo, então rodada sem notificação é rodada perdida.

---

## Anexo — o que muda no `build.py`

O `build.py` atual só conhece `cliques.json`. Para esta versão do prompt funcionar, ele precisa passar a ler `avaliacoes.json` também. Mantidos: `JANELA_S = 10` com chave `(garcom, ua)`, a reconstrução integral a cada execução, as abas Diário, Matriz, Atendentes, Base e Leitura, e a identidade visual.

**Acréscimos:**

1. Ler `avaliacoes.json` se existir. Ausente ou vazio, o script roda como hoje e devolve `regra_do_zero = "sem_avaliacoes"`.

2. Pareamento 1 para 1 entre escaneamento e avaliação, sobre a lista já líquida de repetições:
   - avaliações do dia em ordem de `criado_em`;
   - para cada uma, os escaneamentos **ainda não consumidos** na janela `[t − 10 min, t]`;
   - atribuir o **mais próximo** e marcar o escaneamento como consumido;
   - sem candidato, a avaliação é **órfã**;
   - escaneamento não consumido ao fim do dia é **perdido**.

   A janela de 10 minutos foi medida, não arbitrada: mediana de 54 segundos entre o escaneamento e o envio, p95 em 6,4 minutos, e nenhuma ocorrência entre 20 e 60 minutos.

3. Colunas novas em Diário e Atendentes: `viraram_nota`, `perdidos`, `conversao`, `media_notas`. Matriz e Atendentes seguem sendo fórmulas sobre Diário.

4. Aba nova **Pareamento**, uma linha por par com atendente, hora do escaneamento, hora da avaliação, defasagem em minutos, nota e se tem texto. É a aba de auditoria de pagamento.

5. Aba nova **Pagamento**, com os parâmetros em células editáveis (R$ 2,00 por avaliação, R$ 50,00 por lote de 40) e o cálculo por atendente em fórmula, nunca em número fixo.

6. Guardar `nota` e `atualizado_em` por `reviewId` entre execuções, e emitir `notas_alteradas` quando a nota de um `reviewId` conhecido mudar. Em agosto, 135 das 934 avaliações têm `atualizado_em` diferente de `criado_em`, ou seja, foram editadas. Uma nota 5 que vira 2 depois do pagamento passa despercebida sem isso.

7. Marcar escaneamento antes das 18h como `teste`, fora do denominador da conversão. Em 05/08 houve dois, às 17h27 e 17h30, antes da abertura.

8. Campos novos no JSON de saída: `conversao_ontem`, `media_notas_ontem`, `orfas_ontem`, `notas_alteradas`, `perfil_google` (com `nota_exibida` e `total_avaliacoes`), e `viraram_nota` dentro de cada item de `ontem_por_atendente`.

**Referência de layout:** a planilha `QT-scans-x-avaliacoes-agosto.xlsx` tem as abas Diário, Pareamento e Pagamento no formato esperado, já preenchidas com agosto de 2026.

**Números de agosto de 2026 para validar a implementação:** 196 cliques brutos, 16 descontados, 180 contados, 112 pares, 14 órfãs, 68 perdidos, conversão de 62,2%.
