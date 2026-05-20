import pandas as pd

# 1. Carregar o ficheiro mestre gerado no passo anterior
input_filename = "analise_focada_main_adc.csv"
output_filename = "medias_completas_por_minuto.csv"

try:
    df = pd.read_csv(input_filename)
except FileNotFoundError:
    print(f"Erro: O ficheiro '{input_filename}' não foi encontrado.")
    exit()

# 2. Isolar apenas as colunas numéricas
cols_numericas = df.select_dtypes(include=['number']).columns.tolist()
if 'minute' in cols_numericas:
    cols_numericas.remove('minute')

# 3. Agrupar pelo Minuto e pelo Resultado, e calcular a média
df_medias = df.groupby(['minute', 'result'])[cols_numericas].mean().reset_index()

# 4. Ordenar para garantir que o tempo avança de forma correta dentro de cada resultado
df_medias = df_medias.sort_values(by=['result', 'minute'])

# 5. Adicionar os DELTAS (Variação) das médias principais
# Calcula quanto a vantagem cresceu ou diminuiu em relação ao minuto anterior
df_medias['gold_diff_delta'] = df_medias.groupby('result')['gold_diff'].diff().fillna(0)
df_medias['xp_diff_delta']   = df_medias.groupby('result')['xp_diff'].diff().fillna(0)
df_medias['cs_diff_delta']   = df_medias.groupby('result')['cs_diff'].diff().fillna(0)

# 6. Arredondar os valores para 2 casas decimais
df_medias = df_medias.round(2)

# 7. Guardar o ficheiro final
df_medias.to_csv(output_filename, index=False)

print(f"Sucesso! O ficheiro '{output_filename}' foi gerado.")
print("As colunas 'gold_diff_delta', 'xp_diff_delta' e 'cs_diff_delta' foram adicionadas.")