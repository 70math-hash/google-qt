# Adendo ao Brief do Worker de Conciliação — QT Pizza Bar
**Data:** 25 de agosto de 2026
**Status:** substitui e corrige pontos do brief original (`QT-Worker-Conciliacao-Brief.md`)

Este adendo registra o que foi medido com dados reais depois que o acesso à Google Business
Profile API foi liberado. Quatro parâmetros do brief original foram calibrados no chute e
agora têm número. **Dois deles quebrariam o worker se implementados como estão.**

Leia este documento antes do brief original. Onde houver conflito, este prevalece.

---

## 0. O gate abriu

O brief estava condicionado à cota da Business Profile API sair de 0 para 300 QPM.

- Caso de suporte: `9-7776000041281` — **aprovado em 25/08/2026**
- Project Number: `685524545181`
- Project ID: `qt-avaliacoes-api`
- APIs habilitadas: Google My Business (v4, reviews), My Business Account Management,
  My Business Business Information, Business Profile Performance
- Account ID: `104587987562013333438`
- Location ID: `13329139313132354988`
- Endpoint de avaliações:
  `mybusiness.googleapis.com/v4/accounts/{acc}/locations/{loc}/reviews?pageSize=50`

**Armadilha de implementação:** `locations.list` devolve o nome como `locations/{id}`.
A v4 espera só o número. Concatenar direto produz `locations/locations/{id}` e retorna 404
sem mensagem útil.

**OAuth:** a tela de consentimento está em modo *Testing*, o que faz o refresh token
**expirar a cada 7 dias**. Antes de subir o worker em produção, publicar o app como
*Em Produção*, senão haverá `invalid_grant` semanal com sintoma de bug de código.

---

## 1. CORREÇÃO CRÍTICA — Janela de atribuição: 45 min → **10 min**

O brief especifica uma janela de 45 minutos antes da publicação. **Está sete vezes larga
demais.**

Defasagem real medida entre o scan e o envio da avaliação (126 avaliações, 05 a 24/ago):

| Defasagem | Avaliações |
|---|---|
| 0 a 5 min | 115 |
| 5 a 10 min | 5 |
| 10 a 20 min | 1 |
| 20 a 60 min | **0** |
| mais de 60 min | 5 |

- Mediana: **54 segundos**
- p90: 3,6 min · p95: 6,4 min
- Defasagem média dos pares fechados: 1,33 min

A distribuição é **bimodal**: ou a avaliação sai em menos de 10 minutos, ou não veio de scan
nenhum. Entre 20 e 60 minutos não existe uma única ocorrência. A janela de 45 minutos varre
um vazio e arrasta scans de outros garçons para dentro do rateio.

Efeito na precisão da atribuição:

| Janela | Determinística | Em rateio | Órfãs |
|---|---|---|---|
| 5 min | 86,1% | 16 | 11 |
| **10 min** | **74,2%** | **31** | **6** |
| 20 min | 54,5% | 55 | 5 |
| 45 min (brief) | 43,8% | 68 | 5 |

**Adotar 10 minutos.** Apertar a janela não perde avaliação, só corta ambiguidade.

---

## 2. CORREÇÃO CRÍTICA — Deduplicação: 10 min por garçom → **2 segundos**

O brief propõe deduplicar scans do mesmo garçom dentro de 10 minutos. **Essa regra destrói
dado legítimo.** Numa sexta-feira a Clara atende várias mesas dentro de dez minutos; a regra
colapsaria 179 scans limpos em 101.

A regra correta é **2 segundos**, que é o único intervalo em que só cabe toque duplo no
mesmo aparelho.

Em agosto: **196 scans brutos → 17 toques duplos → 179 limpos** (Clara 14 duplos, Thalia 3).

### 2.1 Precisão e método
- Deduplicar sobre o `criado_em` **timestamptz com microssegundos**, nunca sobre export
  truncado em segundos. Truncar em segundo perdeu 3 dos 17 duplicados (gaps reais de 1,520s,
  1,948s e 1,827s aparecem como "2s").
- Comparar com a **linha anterior bruta** (`lag()`), não com o último registro mantido.
  Num toque triplo a 1,8s de intervalo, comparar com o último mantido preserva
  incorretamente o terceiro toque.

---

## 3. CONFIRMADO — `createTime` é hora de envio, não de indexação

Teste: das 129 avaliações de agosto, **123 caem entre 18h e meia-noite (SP)**, exatamente a
janela de serviço. Se o carimbo fosse de indexação, o horário estaria espalhado pela manhã.

A arquitetura de atribuição temporal está validada. O worker pode confiar no `createTime`
como âncora.

Converter sempre de UTC para `America/Sao_Paulo` antes de comparar com `cliques_avaliacao`.

---

## 4. NOVO — Avaliações editadas

`updateTime` difere de `createTime` em **135 das 934** avaliações (14,5%).

O brief não trata isso. Uma nota 5 que o cliente edita para 2 depois do pagamento muda a
média e o valor devido, e passa despercebida se o worker só olha `createTime`.

**Requisito:** persistir `starRating` e `updateTime` a cada execução e disparar alerta quando
o `starRating` de um `reviewId` já conhecido mudar. Estado sugerido: `NOTA_ALTERADA`.

---

## 5. NOVO — Formato do relatório diário

Gravar uma linha por dia, por garçom, mais o consolidado do dia:

| Campo | Origem |
|---|---|
| `data` | data de serviço (SP) |
| `garcom` | slug de `cliques_avaliacao` |
| `scans_brutos` | contagem sem dedup |
| `scans_limpos` | após corte de 2s |
| `scans_teste` | scans antes das 18h, fora do serviço |
| `viraram_nota` | pareados 1:1 na janela de 10 min |
| `perdidos` | limpos menos pareados |
| `conversao` | pareados / limpos |
| `media_notas` | média das notas pareadas |
| `orfas` | avaliações do dia sem scan compatível |

Consolidado do dia: soma dos scans limpos, soma dos pareados, conversão e média.

**Execução às 08h00 de SP**, após a janela de estabilização. A linha do dia anterior só é
marcada como fechada depois de 72 horas.

O layout de referência está na aba **Diário** de `QT-scans-x-avaliacoes-agosto.xlsx`.

---

## 6. NOVO — Pareamento 1:1 substitui o rateio

O brief usa rateio proporcional quando dois garçons têm scan na janela. Com a janela de 10
minutos isso deixa de ser necessário na maioria dos casos.

**Algoritmo:**
1. Ordenar avaliações do dia por `createTime`.
2. Para cada avaliação, buscar scans **ainda não consumidos** na janela `[t − 10min, t]`.
3. Atribuir o **mais próximo**; marcar o scan como consumido.
4. Sem candidato → avaliação **órfã**.
5. Scan que termina o dia não consumido → **perdido**.

Cada linha vira um par único e auditável, sem crédito fracionado.

Resultado de agosto: **109 pares, 17 órfãs, 70 scans perdidos**.

---

## 7. NOVO — Marcar scans de teste

Scans antes das 18h são teste da equipe, não cliente. Em 05/08 houve dois às 17h27 e 17h30,
antes da abertura. Contá-los como perda distorce a conversão.

**Requisito:** flag `scans_teste` para registros fora do horário de serviço, excluídos do
denominador da conversão.

---

## 8. Pagamento — parâmetros vigentes

| Parâmetro | Valor |
|---|---|
| Por avaliação publicada | R$ 2,00 |
| Bônus por lote | R$ 50,00 |
| Avaliações por lote | 40 |

Regras: só entram no cálculo avaliações **pareadas 1:1**. Órfãs não são creditadas a ninguém.
Lote incompleto não gera bônus, não acumula entre garçons nem entre meses.

**Fechamento de agosto de 2026:**

| Garçom | Limpos | Notas | Conversão | Média | Variável | Bônus | Total |
|---|---|---|---|---|---|---|---|
| Clara | 101 | 67 | 66,3% | 4,85 | R$ 134 | R$ 50 | R$ 184 |
| Thalia | 74 | 42 | 56,8% | 4,98 | R$ 84 | R$ 50 | R$ 134 |
| Alexandre | 2 | 0 | 0% | — | — | — | — |
| Rafa | 2 | 0 | 0% | — | — | — | — |
| **Total** | **179** | **109** | **60,9%** | **4,90** | **R$ 218** | **R$ 100** | **R$ 318** |

Custo por avaliação publicada: **R$ 2,92**.

**Ponto aberto para decisão do Matheus:** o degrau de 40 concentra o incentivo de forma
desigual. A Clara está a 13 avaliações do próximo lote (ganho marginal de R$ 5,85 por
avaliação), a Thalia a 38 (R$ 2,00). A alternativa é bônus proporcional de R$ 1,25 por
avaliação acima do lote fechado, que dá o mesmo total no mês sem efeito de precipício.

---

## 9. Caso de calibração — REVISAR ANTES DE USAR

O brief define como teste obrigatório o episódio de 05/08: 11 avaliações notificadas por
e-mail, 7 visíveis às 22h35, 4 aparecendo na manhã seguinte. O worker deve mantê-las em
`NOTIFICADA` sem disparar alerta e resolvê-las para `VISIVEL` na execução da manhã.

**Problema:** não existe nenhuma avaliação com `createTime` em 05/08. As 12 daquela sequência
estão todas em 06/08, entre 18h20 e 22h36.

Ou as datas do registro original estão deslocadas em um dia, ou o episódio foi na noite de
06/08. **Confirmar com o Matheus antes de usar como caso de teste**, porque uma calibração
com data errada valida o worker contra um evento que não existe.

---

## 10. Resumo do que mudou

| # | Item | Brief original | Corrigido |
|---|---|---|---|
| 1 | Janela de atribuição | 45 min | **10 min** |
| 2 | Deduplicação | 10 min por garçom | **2 segundos, microssegundos** |
| 3 | `createTime` | assumido | **confirmado como hora de envio** |
| 4 | Avaliações editadas | não tratado | **novo estado `NOTA_ALTERADA`** |
| 5 | Relatório diário | não especificado | **10 campos definidos** |
| 6 | Atribuição | rateio proporcional | **pareamento 1:1** |
| 7 | Scans de teste | não tratado | **flag antes das 18h** |
| 9 | Caso de calibração | 05/08 | **revisar data** |

Mantidos do brief original: máquina de cinco estados, janela de estabilização de 72 horas,
execução às 08h00 SP, minimização LGPD (primeiro nome mais inicial do sobrenome, sem texto
da avaliação, sem acesso `anon` a tabelas com nomes).
