Escreva o relatório diário de escaneamentos e avaliações da QT Pizza Bar, como texto direto na conversa, e dispare a notificação.

Carregue a ferramenta antes de usar:
ToolSearch `select:mcp__Supabase__execute_sql`

Use SOMENTE essa ferramenta. **Você não gera planilha nem sobe arquivo.** Isso passou a ser feito por um workflow do GitHub Actions, `planilha-diaria`, que roda às 07h20 de São Paulo e deposita o resultado numa tabela. Se precisar de qualquer outra ferramenta, pare e registre a falha no relatório em vez de solicitá-la.

## 1. Ler a rodada do dia

Projeto Supabase `helinoirdizwrluydkzp`:

    select
      to_char(gerado_em at time zone 'America/Sao_Paulo','YYYY-MM-DD HH24:MI') as gerado_em,
      (gerado_em at time zone 'America/Sao_Paulo')::date
        = (now() at time zone 'America/Sao_Paulo')::date as e_de_hoje,
      ok, planilha_url, planilha_nome, planilha_bytes, erro, resumo
    from relatorio_diario
    order by gerado_em desc
    limit 1;

Todo o texto do relatório sai do campo `resumo`, que é o JSON impresso pelo `build_planilha_escaneamentos.py`. Não recalcule nada por fora: quem apurou foi o script, e usar outra fonte faria o texto discordar da planilha.

**Se não vier linha nenhuma, ou se `e_de_hoje` for falso**, o workflow não rodou hoje. Escreva um relatório curto dizendo isso, com a data da última rodada que existe, e dispare a notificação de falha. Não invente número, e não tente gerar a planilha você mesmo: você não consegue, e é assim de propósito.

**Se `ok` for falso**, o workflow rodou e apurou tudo, mas a planilha não subiu. O `resumo` está completo: escreva o relatório inteiro normalmente e acrescente uma linha dizendo que a planilha não subiu, com o texto de `erro`.

## 2. Escrever o relatório

Use o bloco `relatorio` de dentro do `resumo`.

1. Título com `dia_semana_ontem` e `data_ontem`.
2. **Ontem por atendente**: uma linha por pessoa a partir de `ontem_por_atendente`, na ordem em que vier, incluindo quem está em zero. Cada linha traz **escaneamentos** e, entre parênteses, **quantos viraram avaliação publicada**.
3. **Total da casa**: os cinco valores de `totais_da_casa`, rotulados como hoje, ontem, últimos 7 dias (inclui hoje), mês corrente e total acumulado.
4. **Conversão de ontem**: `conversao_ontem`, escaneamentos que viraram avaliação, e a média das notas em `media_notas_ontem`.
5. **Nota da casa no Google**: `nota_exibida` e `total_avaliacoes` de `perfil_google`.
6. Uma linha com `ultimo_escaneamento`, nome e horário.
7. Uma linha com `planilha_url`, se `ok` for verdadeiro.
8. Se `descontados` for maior que zero, uma linha dizendo quantos cliques foram descontados como toque repetido.
9. Se `orfas_ontem` for maior que zero, uma linha dizendo quantas avaliações entraram sem escaneamento correspondente.
10. Se `notas_alteradas` não estiver vazio, uma linha por avaliação cuja nota mudou desde a última rodada, com a nota antiga e a nova.

O campo `regra_do_zero` decide o fecho, e ele já vem resolvido pelo script:

- `normal`: relatório completo, sem comentário extra.
- `sem_historico`: escreva que a série ainda não tem histórico e que a primeira leitura comparável sai no relatório seguinte. Sem alarme.
- `segunda_fechada`: escreva apenas que não houve escaneamento na véspera porque a casa fecha na segunda. Sem alarme.
- `zero_operacao`: registre que zerou num dia de operação e sinalize para conferir os QR codes nas mesas e a página de destino.
- `vazio`: diga que a base não retornou registro nenhum e que vale checar.
- `sem_avaliacoes`: a sincronização com o Google não trouxe avaliação nesta rodada. Escreva o relatório de escaneamentos normalmente e registre numa linha que os dados de avaliação não entraram.

O campo `avaliacoes_ausentes` vem separado de propósito: numa segunda-feira sem escaneamento e sem sincronização, `regra_do_zero` é `segunda_fechada` e `avaliacoes_ausentes` é `true`. Registre as duas coisas.

Para nomear a causa quando faltarem avaliações, em vez de dizer só "erro":

    select ok, to_char(executado_em at time zone 'America/Sao_Paulo','DD/MM HH24:MI') as quando,
           baixadas, inseridas, alteradas, left(erro, 300) as erro
    from avaliacoes_sync order by executado_em desc limit 3;

`invalid_grant` significa refresh token morto: é preciso refazer o consentimento e trocar o secret `GBP_REFRESH_TOKEN`. `403` significa API desabilitada no projeto `685524545181`. `LISTAGEM VAZIA` com `n_reviews=0` significa que a função rodou fora da região `sa-east-1`.

### Regras de redação, obrigatórias

São **três números diferentes** e cada um tem nome próprio. Nunca use um no lugar do outro, e nunca deixe um sozinho representando os três:

| Termo | O que é |
|---|---|
| **escaneamento** | QR code lido, líquido de repetição |
| **avaliação publicada** | avaliação que apareceu no perfil do Google |
| **nota da casa** | média exibida no Google, sobre toda a base histórica |

O cliente pode ler o código e não escrever nada, então escaneamento nunca vira sinônimo de avaliação. E a nota da casa se move devagar sobre centenas de avaliações antigas, então não a apresente como resultado do dia.

Linguagem técnica e direta, sem emoji, sem elogio, sem recomendação que o dado não sustente. Nunca atribua uma nota baixa a um atendente específico: o pareamento serve para creditar, não para culpar, e cliente insatisfeito costuma avaliar fora da janela.

## 3. Notificação, passo obrigatório

Chame PushNotification com `status` igual a `proactive` e uma linha de até 200 caracteres, sem markdown:

    QT 06/08: 16 escaneamentos, 11 viraram avaliacao (69%). clara 12/9, thalia 4/2, alexandre 0. Nota 4,2. Planilha no Drive.

Nos casos de exceção, use a linha curta equivalente:

    QT 10/08: zero escaneamentos, casa fechada na segunda.
    QT 12/08: zero escaneamentos num dia de operacao, conferir os QR nas mesas.
    QT 07/08: 23 escaneamentos. Dados de avaliacao fora nesta rodada, sincronizacao nao rodou.
    QT 26/08: 22 escaneamentos, 11 viraram avaliacao (50%). Planilha nao subiu ao Drive.
    QT 09/08: o workflow planilha-diaria nao rodou hoje, sem dado para relatar.

Envie sempre, inclusive quando o total for zero e inclusive quando algo falhar. É o canal que alcança o Matheus fora do aplicativo, então rodada sem notificação é rodada perdida.

---

## Anexo — quem faz o quê

| Etapa | Onde roda | Quando |
|---|---|---|
| Busca as avaliações no Google e grava em `avaliacoes` | Edge Function `sincroniza-avaliacoes`, região `sa-east-1`, chamada por `cron.job` | 07h00 SP |
| Puxa os dados, gera a planilha, sobe no Drive, grava em `relatorio_diario` | GitHub Actions `planilha-diaria`, repositório `70math-hash/google-qt` | 07h20 SP |
| Lê `relatorio_diario`, escreve o relatório, notifica | Esta tarefa | 08h00 SP |

A geração da planilha saiu daqui em 26/08/2026 porque este container não tem egresso de rede: para subir o arquivo era preciso passá-lo inteiro em base64 dentro de um parâmetro de ferramenta, e com 55 mil caracteres o conteúdo era truncado sem aviso. O arquivo chegava ao Drive abrindo normalmente, com os nomes das abas certos e nenhuma célula dentro. O `build_planilha_escaneamentos.py` continua sendo a definição oficial da planilha, só que executado pelo Actions, que tem rede e move os bytes como binário.
