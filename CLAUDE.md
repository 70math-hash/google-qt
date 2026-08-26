# QT Pizza Bar — Programa de Avaliações

Contexto para o Claude Code. Leia inteiro antes de escrever qualquer linha.

---

## 1. O que é isto

A QT Pizza Bar (Jardins, São Paulo) tem um programa em que garçons pedem avaliação
no Google. Cada garçom tem um QR code próprio apontando para
`avalie.qtpizzabar.com.br/<slug>`, que registra o clique no Supabase e redireciona
para a página de avaliação do Google.

Garçons ativos: `clara`, `thalia`, `alexandre`, `rafa`.

Pagamento: **R$ 2,00 por avaliação publicada** e **R$ 50,00 a cada lote de 40**.
Lote incompleto não gera bônus e não acumula entre garçons nem entre meses.

**Dono do projeto:** Matheus Ramos. Ele é técnico, mede tudo, e prefere número
medido a estimativa. Se um parâmetro for chute, diga que é chute.

---

## 2. Objetivo desta fase

A tarefa agendada diária do Claude hoje reporta **apenas escaneamentos**. Ela deve
passar a reportar **escaneamentos e conversões**, ou seja, quantos daqueles scans
viraram avaliação publicada no Google.

Isso exige três coisas, nesta ordem de dependência:

1. Dados de avaliação disponíveis no Supabase antes das 08h00 (**bloqueado**, ver §4)
2. `build.py` v2 fazendo o pareamento scan ↔ avaliação (ver §6)
3. Prompt da tarefa diária reportando os dois números (já escrito, ver §7)

---

## 3. O que já funciona. Não quebre.

**Tarefa agendada diária**, no app do Claude, seção Programado, "Escaneamentos QT —
relatório e planilha 08:00". Roda todo dia às 08h00 desde 07/08/2026, sem falhar.
Puxa `cliques_avaliacao` do Supabase, baixa `build.py` do Drive, gera a planilha,
sobe no Drive, escreve o relatório e dispara PushNotification.

**`build_planilha_escaneamentos.py`** no Drive, id `11dfk2ukTHgW1bEN2m7iapYUsT2h_QuB8` (v2.1, desde 26/08/2026).
A tarefa diária acha o arquivo **pelo título**, não pelo id, então trocar de versão não exige
mexer no prompt. Só pode existir um arquivo com esse título exato; as versões velhas ficam
renomeadas com sufixo.
É a definição oficial da planilha. Abas: Diário, Matriz, Pareamento, Atendentes, Pagamento, Base, Leitura.
Reconstrói tudo a cada execução, nunca acrescenta linha. Matriz e Atendentes são
fórmulas sobre Diário.

**Deduplicação, já implementada e correta.** `JANELA_S = 10` segundos, com chave
`(garcom, user_agent)`. Dois cliques do mesmo garçom **no mesmo aparelho** dentro de
10s contam como um. Usar aparelho na chave é melhor que só tempo, porque dois
clientes diferentes na mesma mesa não são fundidos. **Não troque essa regra.**

**Tabelas no Supabase**, projeto `helinoirdizwrluydkzp`:
- `cliques_avaliacao` — `id`, `garcom`, `criado_em` (timestamptz), `user_agent`, `referrer`
- `avaliacoes` — criada em 25/08, vazia, esperando quem escreva nela
- `avaliacoes_sync` — log de sincronização, uma linha por execução

Ambas com RLS e `revoke all` para `anon` e `authenticated`.

---

## 4. O que NÃO funciona. Leia antes de tentar.

Estas três coisas foram testadas e falharam em 25/08/2026. Não repita.

### 4.1 Edge Function do Supabase em us-east-1

O endpoint `reviews.list` v4 responde **HTTP 200 com 69 bytes**, contendo apenas
`averageRating` e `totalReviewCount`, sem `reviews` e sem `nextPageToken`.

Testado e descartado: `pageSize` 5/50/200, sem parâmetro, `orderBy`, cabeçalhos
`Accept`, `Accept-Encoding: identity`, `Referer`, `Origin`, sete `User-Agent`
diferentes. Todas as sete variações: 69 bytes.

O token está correto (`tokeninfo` confirma escopo `business.manage` e o client certo),
os IDs estão corretos, e a mesma chamada com o mesmo token **funciona do IP
residencial em São Paulo**. IP de saída do Supabase: `3.231.204.175` (AWS us-east-1).

**É filtro de rede, não de permissão.**

### 4.2 Container da tarefa agendada do Claude

Sem egress de rede. DNS resolve, mas `curl` retorna código 56, `http=000`, e nem
`api.ipify.org` responde. A tarefa agendada **não pode chamar a API do Google**.
Só alcança o que vem por MCP (Supabase, Google Drive).

### 4.3 Mac Mini com launchd

Funciona tecnicamente, mas **a máquina não fica ligada**. Descartado como host.

---

## 5. A primeira coisa a testar

Supabase permite escolher a região da execução por cabeçalho, sem mexer no projeto.
Se `sa-east-1` (São Paulo) devolver as avaliações, o bloqueio de §4.1 acaba e não
é preciso host nenhum.

```bash
curl -s -X POST \
  -H "Authorization: Bearer $SUPABASE_ANON_KEY" \
  -H "x-region: sa-east-1" \
  https://helinoirdizwrluydkzp.supabase.co/functions/v1/sonda-reviews | head -c 600
```

A função `sonda-reviews` já está publicada e faz o teste sozinha. Procure por
`n=5` na saída. Se aparecer, funcionou.

**Se não funcionar**, aí é filtro por datacenter e a decisão passa a ser de
hospedagem: VPS brasileiro barato rodando um cron. Levar a decisão ao Matheus antes
de construir, não decidir sozinho.

---

## 6. Parâmetros medidos. Não são chutes.

### Janela de atribuição: 10 minutos

Medida sobre 126 avaliações e 180 scans de agosto:

| Defasagem entre scan e avaliação | Ocorrências |
|---|---|
| 0 a 5 min | 115 |
| 5 a 10 min | 5 |
| 10 a 20 min | 1 |
| 20 a 60 min | **0** |
| mais de 60 min | 5 |

Mediana **54 segundos**, p90 3,6 min, p95 6,4 min. A distribuição é bimodal: ou sai
em menos de 10 minutos, ou é orgânica e não veio de scan. Uma versão anterior do
brief dizia 45 minutos; **isso está errado** e derruba a atribuição determinística
de 74% para 44%.

### `createTime` é hora de envio, não de indexação

123 das 129 avaliações de agosto caem entre 18h e meia-noite (SP), exatamente a
janela de serviço da casa. Confirmado empiricamente. Converter de UTC para
`America/Sao_Paulo` antes de comparar com `cliques_avaliacao`.

### Pareamento 1 para 1

1. Avaliações do dia em ordem de `createTime`
2. Para cada uma, scans **ainda não consumidos** na janela `[t − 10min, t]`
3. Atribuir o **mais próximo**; marcar o scan como consumido
4. Sem candidato → avaliação **órfã**
5. Scan não consumido ao fim do dia → **perdido**

Substitui o rateio proporcional de versões anteriores. Cada linha vira um par único
e auditável, sem crédito fracionado.

### Avaliações editadas

`updateTime` difere de `createTime` em **135 das 934** (14,5%). Uma nota 5 que vira 2
depois do pagamento passa despercebida se só olhar `createTime`. Persistir `nota` e
`atualizado_em` por `review_id` e alertar quando a nota de um id conhecido mudar.

### Scans de teste

Scan antes das 18h é teste da equipe, não cliente. Em 05/08 houve dois, às 17h27 e
17h30, antes da abertura. Marcar com flag e excluir do denominador da conversão.

---

## 7. O que construir, em ordem

### 7.1 Sincronização de avaliações

Um script que busca `reviews.list` e faz upsert em `public.avaliacoes`, detectando
mudança de nota. **Onde ele roda depende de §5.** Existe uma versão de referência,
`fetch_reviews.py`, no Drive (id `1rTd34qEBdfqyVhKgNAeHAOJiHJ-la53E`), e uma Edge
Function `sincroniza-avaliacoes` já publicada com a lógica de upsert e detecção de
nota alterada. Reaproveite a lógica, o problema é só o host.

### 7.2 `build.py` v2

Mantidos: `JANELA_S = 10` com chave `(garcom, ua)`, reconstrução integral, as cinco
abas, a identidade visual, o JSON de saída.

Acréscimos:
1. Ler `avaliacoes.json` se existir. Ausente ou vazio → roda como hoje e devolve
   `regra_do_zero = "sem_avaliacoes"`. **A rodada degradada tem que continuar valendo.**
2. Pareamento 1:1 do §6, sobre a lista já líquida de repetições
3. Colunas novas em Diário e Atendentes: `viraram_nota`, `perdidos`, `conversao`,
   `media_notas`
4. Aba **Pareamento**: uma linha por par, com atendente, hora do scan, hora da
   avaliação, defasagem, nota, se tem texto. É a aba de auditoria de pagamento.
5. Aba **Pagamento**: parâmetros em células editáveis (R$ 2,00 / R$ 50,00 / lote 40),
   cálculo em fórmula, nunca número fixo
6. Flag `scans_teste` para scan antes das 18h
7. Campos novos no JSON: `conversao_ontem`, `media_notas_ontem`, `orfas_ontem`,
   `notas_alteradas`, `perfil_google` (`nota_exibida`, `total_avaliacoes`), e
   `viraram_nota` dentro de cada item de `ontem_por_atendente`

Layout de referência: `QT-scans-x-avaliacoes-agosto.xlsx`, abas Diário, Pareamento
e Pagamento.

### 7.3 Prompt da tarefa diária

Já escrito em `QT-prompt-diario-v2.md`. Precisa de um ajuste conforme §5: se a
sincronização passar a rodar fora da tarefa, o passo 2 vira **mais um SELECT** ao
lado do que já existe, e some a etapa de baixar e rodar script. Isso é melhor também
porque não introduz tipo de ação novo, e a tarefa não vai pedir autorização nova.

---

## 8. Números para validar a implementação

Agosto de 2026, período de 05 a 24:

| Medida | Valor |
|---|---|
| Cliques brutos | 196 |
| Descontados como repetição | 16 |
| Scans limpos | 180 |
| Avaliações no período | 126 |
| Pares 1:1 | 112 |
| Órfãs | 14 |
| Scans perdidos | 68 |
| Conversão | 62,2% |
| Defasagem média dos pares | 1,33 min |

Por garçom:

| Garçom | Limpos | Notas | Conversão | Média | A pagar |
|---|---|---|---|---|---|
| clara | 104 | 71 | 68,3% | 4,86 | R$ 192 |
| thalia | 72 | 41 | 56,9% | 4,98 | R$ 132 |
| alexandre | 2 | 0 | 0% | — | — |
| rafa | 2 | 0 | 0% | — | — |
| **Total** | **180** | **112** | **62,2%** | **4,90** | **R$ 324** |

Custo por avaliação publicada: R$ 2,89.

Perfil em 25/08: **943 avaliações, nota exibida 4,2**, média real 4,1617 na leitura
de 934. Distribuição em 934: 563 cincos, 161 quatros, 90 três, 38 dois, 82 uns.

Se a sua implementação não reproduzir estes números com os mesmos dados, ela está
errada.

---

## 9. Credenciais e infraestrutura

**Google Cloud**
- Project ID `qt-avaliacoes-api`, Project Number `685524545181`
- APIs habilitadas: Google My Business (v4, reviews), My Business Account Management,
  My Business Business Information, Business Profile Performance
- Acesso aprovado em 25/08/2026, caso `9-7776000041281`, cota 300 QPM
- Account ID `104587987562013333438`, Location ID `13329139313132354988`

**Armadilha:** `locations.list` devolve `locations/{id}`. A v4 espera só o número.
Concatenar direto vira `locations/locations/{id}` e retorna 404 sem mensagem útil.

**OAuth — resolvido em 26/08/2026**

O app está **Em Produção** e a marca foi verificada. O prazo de 7 dias acabou: a
resposta do grant `refresh_token` não traz mais `refresh_token_expires_in`, medido
pela Edge Function `sonda-reviews`. Não há mais `invalid_grant` semanal a esperar.

O que foi preciso, na ordem: publicar `qtpizzabar.com.br/privacidade` e
`/termos` (com link no rodapé da home, que o revisor cobra), verificar o domínio no
Search Console por registro TXT, e renomear o app de "QT Avaliações" para
**"QT Pizza Bar"**, porque o Google exige que o nome da tela de consentimento bata
com o nome na página inicial.

**Armadilha, se algum dia voltar a Testing:** publicar o app **não conserta um token
já emitido**. O prazo fica gravado no token no momento da emissão, então é preciso
refazer o consentimento e trocar `GBP_REFRESH_TOKEN`. Medido: com o app já Em
Produção, o token antigo continuou reportando 6 dias de validade.

O escopo `business.manage` é confidencial e ainda não passou por revisão de escopo,
então a tela "App não verificado" aparece ao reautorizar. É esperado e inofensivo:
Avançado, e seguir. O limite de 100 usuários não incomoda, o app tem um.

**Segredos**

Nunca no repositório. O client secret já vazou em prints de conversa e **continua
pendente de rotação** em 26/08/2026: crie um secret novo no console (máximo dois por
client), migre, depois desabilite e apague o antigo. Trocar o secret não invalida
refresh token, porque o token é vinculado ao client ID.

Deixou de ser urgente quando o OAuth foi publicado, porque não há mais um prazo de
7 dias por cima. Continua sendo dívida: faça numa janela calma, com as duas chaves
vivas ao mesmo tempo, e só apague a antiga depois que a `sonda-reviews` passar.

**Supabase**
- Projeto `helinoirdizwrluydkzp`
- Edge Functions publicadas: `sincroniza-avaliacoes` (v3), `sonda-reviews` (v2)
- As duas são descartáveis se §5 falhar

**Google Drive**
- Pasta `14Iv1VAMACSXY100eKp4g495OYPTsGgS0`
- `build_planilha_escaneamentos.py` id `11dfk2ukTHgW1bEN2m7iapYUsT2h_QuB8` (v2.1). Procurar pelo título, não pelo id
- Rollback: `build_planilha_escaneamentos_v2.0_ate_2026-08-26.py` id `1cel_jwKuzsJeB9LOktB6KegKYnN1bpvp`, e `build_planilha_escaneamentos_v1_ate_2026-08-26.py` id `1AHv9xdMrcg__gE_V5bk61cYZ4wnYwkfj`
- `fetch_reviews.py` id `1rTd34qEBdfqyVhKgNAeHAOJiHJ-la53E`

---

## 10. Regras de redação do relatório

São **três números diferentes** e cada um tem nome próprio. Nunca use um no lugar do
outro, e nunca deixe um sozinho representando os três:

| Termo | O que é |
|---|---|
| escaneamento | QR code lido, líquido de repetição |
| avaliação publicada | avaliação que apareceu no perfil do Google |
| nota da casa | média exibida no Google, sobre toda a base histórica |

O cliente pode ler o código e não escrever nada, então escaneamento nunca vira
sinônimo de avaliação. A nota da casa se move devagar sobre centenas de avaliações
antigas, então não a apresente como resultado do dia.

Linguagem técnica e direta, sem emoji, sem elogio, sem recomendação que o dado não
sustente.

**Nunca atribua nota baixa a um garçom específico.** O pareamento serve para creditar,
não para culpar. Cliente insatisfeito costuma avaliar fora da janela, então a
atribuição de negativas é estatisticamente frágil. Se virar critério de avaliação de
pessoas, o incentivo se inverte e o garçom para de pedir avaliação nas mesas de risco,
que são justamente as que se quer identificar.

**LGPD:** na tabela persistente, guardar primeiro nome mais inicial do sobrenome, sem
o texto da avaliação. Nome completo só em relatório pontual para o dono.

---

## 11. Evite construir demais

Buscar avaliação, deduplicar, parear e calcular pagamento é **script determinístico**.
Não precisa de LLM na execução. O único lugar onde Claude faz sentido rodando é a
redação do relatório diário, que já funciona.

Escreva scripts. Não construa um agente para um problema que é um cron e um join.
