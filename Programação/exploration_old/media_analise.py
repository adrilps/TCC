import pandas as pd

# 1. Carregar os dados
input_filename = "analise_focada_main_adc.csv"
output_filename = "medias_gold_diff_com_deltas.csv"

try:
    df = pd.read_csv(input_filename)
except FileNotFoundError:
    print(f"Erro: O arquivo '{input_filename}' não foi encontrado.")
    exit()

print("Calculando médias e formatando em colunas...")

# 2. Agrupar por minuto e resultado, calculando a média apenas do gold_diff
df_medias = df.groupby(['minute', 'result'])['gold_diff'].mean().reset_index()

# 3. Transformar (Pivotar) Vitória e Derrota em colunas
df_pivot = df_medias.pivot(index='minute', columns='result', values='gold_diff').reset_index()

# Garantir que as colunas existam (prevenção caso a sua amostra só tenha um dos dois resultados)
if 'Derrota' not in df_pivot.columns: df_pivot['Derrota'] = 0
if 'Vitória' not in df_pivot.columns: df_pivot['Vitória'] = 0

# Renomear as colunas para o formato que você gostou
df_pivot = df_pivot.rename(columns={
    'Derrota': 'avg_gold_diff_derrota', 
    'Vitória': 'avg_gold_diff_vitoria'
})

# Reorganizar a ordem para garantir que fique bonito e preencher vazios
df_pivot = df_pivot[['minute', 'avg_gold_diff_derrota', 'avg_gold_diff_vitoria']]
df_pivot = df_pivot.fillna(0)

# ==========================================
# 4. ADICIONAR OS DELTAS (VARIAÇÃO MINUTO A MINUTO)
# ==========================================
df_pivot['delta_gold_diff_derrota'] = df_pivot['avg_gold_diff_derrota'].diff().fillna(0)
df_pivot['delta_gold_diff_vitoria'] = df_pivot['avg_gold_diff_vitoria'].diff().fillna(0)

# Arredondar para duas casas decimais
df_pivot = df_pivot.round(2)

# 5. Salvar o arquivo
df_pivot.to_csv(output_filename, index=False)

print(f"Sucesso! Arquivo exportado: {output_filename}")
print("\nO seu CSV agora tem as seguintes colunas:")
print(list(df_pivot.columns))