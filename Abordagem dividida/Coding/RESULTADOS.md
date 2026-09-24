# Resultados consolidados — TCC Paulo Adriano

Conjunto de referência para a redação do trabalho. Todo número citado no texto
do TCC deve sair daqui. Última atualização: 16/09/2026.

Para regenerar tudo em um comando, a partir da pasta `Coding`:

```
py gerar_resultados.py
```

Ele reescreve `outputs/metricas_modelos.csv`, `outputs/auc_estabilidade.csv`,
`outputs/importancias_shap.csv`, as três figuras e
`outputs/resultados_consolidados.txt`. Os dois experimentos de fronteira e o
método de comparação têm scripts próprios, indicados adiante.

---

## 1. Inventário dos arquivos

### Use estes

| Arquivo | Conteúdo | Produzido por |
|---|---|---|
| `dataset/dataset_congelado_16_17.csv` | Conjunto final, 2.045 partidas | `rebuild_dataset.py` + congelamento |
| `dataset/dataset_congelado_16_17.json` | Metadados e hash de integridade | idem |
| `outputs/metricas_modelos.csv` | AUC por fase, baseline, tamanhos | `gerar_resultados.py` |
| `outputs/auc_estabilidade.csv` | AUC em 10 partições independentes | `gerar_resultados.py` |
| `outputs/importancias_shap.csv` | Importância normalizada por fase | `gerar_resultados.py` |
| `outputs/fig_importancia_por_fase.png` | Barras de importância, três painéis | `gerar_resultados.py` |
| `outputs/fig_evolucao_importancia.png` | Linhas de evolução entre fases | `gerar_resultados.py` |
| `outputs/fig_beeswarm_por_fase.png` | Direção e magnitude do impacto | `gerar_resultados.py` |
| `outputs/validacao_fronteiras.txt` | Validação das fronteiras, protocolo correto | `validacao_fronteiras.py` |
| `outputs/comparacao_exemplo.csv` e `.txt` | Método de comparação, estudo de caso | `comparacao.py` |

### Não use estes

| Arquivo | Por quê |
|---|---|
| `outputs/experimento_fronteiras_resumo.txt` | A etapa de validação treinava só com os 280 jogadores de validação, então as AUCs saíram deprimidas por tamanho de amostra. Serve apenas para a etapa de seleção. Os números finais estão em `validacao_fronteiras.txt`. |
| `outputs/experimento_fronteiras.csv` | Mesma execução. Guarde como registro da busca pelas 40 configurações, não cite as AUCs. |
| `outputs/comparacao_elos.csv` e `fig_comparacao_elos.png` | Comparação Ouro × Diamante com apenas 70 partidas de Diamante no patch. Preliminar, não vai para o texto. |
| `outputs/_features_configs.pkl` | Cache intermediário do experimento de fronteiras. Pode apagar. |

---

## 2. O conjunto de dados

**Como foi obtido.** Busca em largura a partir de um jogador semente, com o
`League of Legends Data Collection Script` modificado (`lol_pipeline/data/spider.py`).
Cada partida processada enfileira seus dez participantes; apenas jogadores da
rota do meio, elo Ouro, fila ranqueada solo/duo da região BR1 entram no
conjunto. Dados dos endpoints MATCH-V5 e LEAGUE-V4.

| | |
|---|---|
| Partidas visitadas | 12.000 |
| Jogadores verificados | 4.442 |
| Partidas após filtros | 2.182 |
| Remakes excluídos | 137 (6,28%) |
| **Conjunto final** | **2.045 partidas, 933 jogadores** |
| Patch | 16.17 |
| Taxa de vitória | 49,63% |
| Duração média | 28,9 min |
| Campeões distintos | 113 (os dez mais jogados somam 43,7%) |
| Partidas sem fase final | 318 (15,5%) |
| Média de partidas por jogador | 2,2 |

**Partidas por fase**

| Fase | n | % do total | Jogadores | Treino / teste | Jogadores tr/te |
|---|---|---|---|---|---|
| Inicial | 2.045 | 100,0% | 933 | 1.633 / 412 | 746 / 187 |
| Intermediária | 2.020 | 98,8% | 931 | 1.604 / 416 | 744 / 187 |
| Final | 1.727 | 84,4% | 877 | 1.390 / 337 | 701 / 176 |

**Duração das fases (min)**

| Fase | Média | Desvio-padrão | Q1 | Mediana | Q3 |
|---|---|---|---|---|---|
| Inicial | 13,01 | 1,31 | 12,34 | 13,60 | 14,00 |
| Intermediária | 10,55 | 2,37 | 9,81 | 11,00 | 11,77 |
| Final | 8,73 | 5,53 | 4,45 | 8,03 | 11,94 |

**Filtros aplicados e por quê.** Remakes (partidas com menos de cinco minutos)
foram excluídos por não possuírem fases reais. As fronteiras de fase são
limitadas ao instante final da partida — sem esse teto, jogos encerrados antes
do fallback produziam fase intermediária medida sobre janela maior que o
próprio jogo e fase final com duração negativa. Partidas sem determinada fase
são excluídas do modelo daquela fase, não imputadas.

---

## 3. Variáveis

Oito métricas, idênticas nas três fases, para que as importâncias sejam
comparáveis entre elas: CS por minuto, visão (wards por minuto), mortes por
minuto, abates solo, dano a campeões por minuto, participação em trocas letais
por minuto, presença em combates por minuto e proximidade de objetivos.

**Descartadas, com o motivo medido:**

| Variável | Correlação com vitória | Motivo |
|---|---|---|
| Participação em abates (razão) | +0,01 | Razão cujo denominador é do time; a normalização elimina o sinal |
| Parcela de dano da equipe (razão) | +0,00 | Mesmo defeito |
| Participações em abates por minuto | +0,21 a +0,41 | Conta abates consumados: mede o desfecho da luta, não a ação |
| Abates da equipe por minuto | +0,35 | Preditor mais forte do conjunto, mas resultado coletivo — fora por construção |

Sobre a última: a taxa de vitória vai de 26% no quartil inferior a 73% no
superior. Ela está extraída no dataset e serve ao argumento de que o desfecho
coletivo explica muito mais que a ação individual, mas não entra no modelo.

**Correlação marginal com vitória, por fase (inicial / intermediária / final):**

| Métrica | Correlação |
|---|---|
| Mortes/min | −0,17 / −0,29 / −0,37 |
| Participação em trocas/min | +0,08 / +0,17 / +0,25 |
| Dano a campeões/min | +0,15 / +0,19 / +0,15 |
| Abates solo | +0,15 / +0,15 / +0,09 |
| CS/min | +0,12 / +0,08 / +0,04 |
| Proximidade de objetivos | +0,05 / +0,04 / +0,08 |
| Visão/min | −0,01 / +0,00 / +0,02 |
| Presença em combates/min | −0,00 / −0,05 / −0,08 |

As duas últimas não apresentam associação marginal com o resultado.

---

## 4. Desempenho preditivo

**Como foi obtido.** Um classificador XGBoost por fase, treinado apenas com as
métricas daquela fase, tendo a vitória como variável resposta. Partição
treino/teste por jogador via `GroupShuffleSplit` sobre o PUUID, com 20% de
teste. Baseline de regressão logística com imputação pela mediana e
padronização, sobre a mesma partição. Hiperparâmetros: 200 árvores,
profundidade máxima 4, taxa de aprendizado 0,05, subamostragem de 0,8 em linhas
e colunas, `base_score` fixado em 0,5. Software: XGBoost 2.1.4, scikit-learn,
shap 0.4x.

**Partição principal (semente 42)** — `outputs/metricas_modelos.csv`

| Fase | AUC XGBoost | AUC baseline |
|---|---|---|
| Inicial | 0,667 | 0,677 |
| Intermediária | 0,733 | 0,742 |
| Final | 0,809 | 0,815 |

**Dez partições independentes** — `outputs/auc_estabilidade.csv`

| Fase | AUC média | Desvio-padrão | Intervalo | Baseline médio | Atinge 0,65 |
|---|---|---|---|---|---|
| Inicial | 0,627 | 0,031 | 0,585 – 0,667 | 0,653 | 3 de 10 |
| Intermediária | 0,713 | 0,018 | 0,682 – 0,736 | 0,735 | 10 de 10 |
| Final | 0,836 | 0,015 | 0,809 – 0,855 | 0,847 | 10 de 10 |

**Validação externa independente.** No experimento de fronteiras, treinando com
653 jogadores e testando em 280 disjuntos que nunca participaram de nenhuma
escolha, a configuração adotada obteve 0,622, 0,704 e 0,813. São praticamente
os mesmos valores das dez partições, o que confirma os resultados principais
por um protocolo completamente distinto.

**Dois pontos a registrar no texto.** A fase inicial fica abaixo do limiar de
0,65 de forma consistente. E a regressão logística iguala ou supera o XGBoost
nas três fases: o ganho preditivo do modelo não linear não se materializou, e
o XGBoost se justifica por viabilizar o TreeSHAP exato.

---

## 5. Importância das métricas

**Como foi obtido.** TreeSHAP (`shap.TreeExplainer`) sobre cada modelo de fase.
A média dos valores absolutos de SHAP no conjunto de teste é a importância
empírica; os valores são normalizados dentro de cada fase, somando um. As
comparações são restritas ao escopo intra-fase.

`outputs/importancias_shap.csv`

| Métrica | Inicial | Intermediária | Final |
|---|---|---|---|
| Mortes/min | 0,258 | 0,355 | 0,405 |
| Participação em trocas/min | 0,186 | 0,205 | 0,286 |
| Visão (wards/min) | 0,140 | 0,091 | 0,055 |
| Dano a campeões/min | 0,139 | 0,087 | 0,050 |
| Farm (CS/min) | 0,116 | 0,092 | 0,062 |
| Presença em combates/min | 0,080 | 0,072 | 0,076 |
| Abates solo | 0,044 | 0,051 | 0,013 |
| Proximidade de objetivos | 0,036 | 0,047 | 0,052 |

Duas métricas sobem ao longo da partida e seis descem. A importância das mortes
por minuto cresce 57% entre a primeira e a última fase.

---

## 6. Validação das fronteiras de fase

**Como foi obtido.** Duas etapas, em `experimento_fronteiras.py` e
`validacao_fronteiras.py`.

Na primeira, 40 configurações foram avaliadas: cinco limiares para a fase
inicial (10, 12, 14, 16 e 18 min) combinados com quatro para a intermediária
(22, 25, 28 e 31 min), nos modos híbrido (evento com fallback) e puramente
temporal. Os 933 jogadores foram divididos em 653 para seleção e 280 para
validação, disjuntos, com semente fixa. A comparação entre configurações
ocorreu apenas na seleção.

Na segunda, as configurações escolhidas foram reavaliadas com o protocolo
correto: treino com todos os jogadores de seleção, teste com todos os de
validação. Intervalos de confiança por bootstrap com mil reamostragens sobre os
**jogadores** do conjunto de validação, e diferenças pareadas sobre a mesma
reamostragem.

`outputs/validacao_fronteiras.txt`

| Configuração | Inicial | Intermediária | Final | Média |
|---|---|---|---|---|
| Híbrida 14/25 (adotada) | 0,622 | 0,704 | 0,813 | 0,713 |
| Híbrida 16/31 | 0,639 | 0,726 | 0,809 | 0,724 |
| Temporal 14/28 | 0,647 | 0,737 | 0,814 | 0,733 |

Diferenças pareadas em relação à adotada: +0,012 com IC 95% de [−0,001; +0,027]
para a melhor híbrida, e +0,020 com IC de [−0,001; +0,039] para a melhor
temporal. Ambos os intervalos contêm zero: as configurações não são
estatisticamente distinguíveis.

Cabe registrar que as duas alternativas foram escolhidas como as melhores entre
quarenta candidatas, ao passo que a adotada foi fixada previamente — a
comparação já as favorece por construção e ainda assim não produz diferença
significativa.

**Cobertura real dos eventos**

| Fase | Pelo evento | Pelo limite de tempo | Pelo fim da partida |
|---|---|---|---|
| Inicial (primeira torre) | 1.189 — 58,1% | 831 — 40,6% | 25 — 1,2% |
| Intermediária (Barão) | 622 — 30,4% | 1.105 — 54,0% | 318 — 15,6% |

As duas fronteiras vieram de evento em 393 partidas, 19,2% do conjunto. A menor
cobertura na fase intermediária decorre da janela de cinco minutos entre o
surgimento do Barão, aos vinte minutos, e o limite de vinte e cinco: quando o
objetivo é abatido antes desse limite, isso ocorre em mediana aos 23,0 minutos.

**As fronteiras não carregam o desfecho.** Correlação entre duração de fase e
vitória: +0,006, −0,019 e −0,016. Restrita às partidas em que a torre caiu antes
dos catorze minutos, a correlação entre o instante da queda e a vitória é
−0,018.

---

## 7. Método de comparação

**Como foi obtido.** `comparacao.py`. Para cada fase e métrica: percentil de
rank médio do jogador na população de referência, orientação derivada da
correlação entre valor da métrica e valor SHAP, lacuna contada apenas abaixo da
mediana, e ponderação pela importância SHAP normalizada intra-fase. Métricas com
|r| abaixo de 0,50 entre valor e SHAP não têm direção consistente e ficam fora
da priorização, sendo apenas descritas.

O percentil é de rank médio — a média entre a proporção estritamente menor e a
menor ou igual — porque métricas com muitos empates, como proximidade de
objetivos na fase inicial, com mais de 75% de zeros, colocariam no percentil
zero um jogador que está exatamente na mediana.

**Estudo de caso** (`outputs/comparacao_exemplo.txt`), jogador com mais
partidas no conjunto, perfil pela mediana de suas cinco partidas:

Escore de lacuna por fase: 0,165 na inicial, 0,137 na intermediária, 0,000 na
final.

| Prioridade | Métrica | Fase | Percentil | Peso | Lacuna ponderada |
|---|---|---|---|---|---|
| 1 | Participação em trocas/min | Intermediária | 26 | 0,205 | 0,0490 |
| 2 | Farm (CS/min) | Inicial | 12 | 0,116 | 0,0438 |
| 3 | Dano a campeões/min | Inicial | 25 | 0,139 | 0,0345 |
| 4 | Visão (wards/min) | Intermediária | 34 | 0,091 | 0,0149 |

Métricas sem direção consistente, portanto fora da priorização: visão, abates
solo e presença em combates na fase inicial; farm, abates solo e dano na
intermediária; farm, visão, abates solo, dano e proximidade de objetivos na
final.

---

## 8. Ordem em que os scripts devem ser executados

1. `collect.py` — coleta (já executada; só refazer para ampliar a amostra)
2. `rebuild_dataset.py` — reconstrói as features a partir do cache, sem API
3. congelamento do patch 16.17 em `dataset/dataset_congelado_16_17.csv`
4. `gerar_resultados.py` — métricas, estabilidade, importâncias e figuras
5. `experimento_fronteiras.py` — busca entre as 40 configurações (etapa lenta)
6. `validacao_fronteiras.py` — validação final das fronteiras
7. `comparacao.py` — método de comparação e estudo de caso
