import pandas as pd
import matplotlib.pyplot as plt

# ==========================================
# 1. CARREGAR OS DADOS
# ==========================================
input_filename = r"C:\Users\paulo\OneDrive\Desktop\TCC\Programação\medias_gold_diff_com_deltas.csv"

try:
    df = pd.read_csv(input_filename)
except FileNotFoundError:
    print(f"Erro: O arquivo '{input_filename}' não foi encontrado.")
    exit()

# ==========================================
# 2. GRÁFICO 1: EVOLUÇÃO ABSOLUTA (Ouro Acumulado)
# ==========================================
plt.figure(figsize=(10, 6), dpi=300)

plt.plot(df['minute'], df['avg_gold_diff_vitoria'], 
         color='#2ca02c', linewidth=2, label='Vitórias')

plt.plot(df['minute'], df['avg_gold_diff_derrota'], 
         color='#d62728', linewidth=2, label='Derrotas')

plt.axvspan(15, 20, color='gray', alpha=0.1, label='Janela Crítica (15-20 min)')
plt.axhline(0, color='black', linewidth=0.8, linestyle='--', alpha=0.7)

plt.title('Diferença Média de Ouro vs Oponente (ADC)', fontsize=14)
plt.xlabel('Minuto', fontsize=11)
plt.ylabel('Gold Diff Acumulado', fontsize=11)

min_max = int(df['minute'].max())
plt.xticks(range(0, min_max + 1, 5))
plt.grid(True, linestyle=':', alpha=0.5)
plt.legend()
plt.tight_layout()

# Salva o primeiro gráfico
output_image1 = "grafico_evolucao_ouro_tcc.png"
plt.savefig(output_image1)
print(f"Gráfico 1 gerado com sucesso: {output_image1}")

# Limpa a tela de desenho para criarmos o segundo gráfico
plt.close()

# ==========================================
# 3. GRÁFICO 2: DELTA (Variação Minuto a Minuto)
# ==========================================
plt.figure(figsize=(10, 6), dpi=300)

# Para Deltas, adicionar marcadores ('o') ajuda a ver a oscilação de cada minuto
plt.plot(df['minute'], df['delta_gold_diff_vitoria'], 
         color='#2ca02c', linewidth=1.5, marker='o', markersize=4, label='Delta Vitórias')

plt.plot(df['minute'], df['delta_gold_diff_derrota'], 
         color='#d62728', linewidth=1.5, marker='o', markersize=4, label='Delta Derrotas')

plt.axvspan(15, 20, color='gray', alpha=0.1)
plt.axhline(0, color='black', linewidth=1, linestyle='--', alpha=0.8) # Linha zero mais forte

plt.title('Variação de Ouro por Minuto (Delta Gold Diff)', fontsize=14)
plt.xlabel('Minuto', fontsize=11)
plt.ylabel('Ganho / Perda de Ouro no Minuto', fontsize=11)

plt.xticks(range(0, min_max + 1, 5))
plt.grid(True, linestyle=':', alpha=0.5)
plt.legend()
plt.tight_layout()

# Salva o segundo gráfico
output_image2 = "grafico_delta_ouro_tcc.png"
plt.savefig(output_image2)
print(f"Gráfico 2 gerado com sucesso: {output_image2}")

# Se estiver rodando no Jupyter Notebook ou IDE compatível, mostra na tela
plt.show()