import pandas as pd
import json

# ==========================================
# 1. CARREGAR OS DADOS
# ==========================================
try:
    with open('match_data.json', 'r', encoding='utf-8') as f_match:
        match_data = json.load(f_match)
    with open('timeline_data.json', 'r', encoding='utf-8') as f_timeline:
        timeline_data = json.load(f_timeline)
except FileNotFoundError:
    print("Arquivos JSON não encontrados. Verifique os nomes e o diretório.")
    exit()

# ==========================================
# 2. DESCOBRIR QUEM É QUEM (ENDPOINT MATCH)
# ==========================================
# Substitua pelo PUUID do jogador que você quer analisar. 
# (Se não souber, você pode adaptar para buscar por summonerName ou riotIdGameName)
TARGET_PUUID = "coloque_seu_puuid_aqui" 

target_id = None
target_team = None
target_position = None
opponent_id = None

participants = match_data['info']['participants']

# Passo A: Encontrar o Jogador Alvo
for p in participants:
    # Como fallback para teste, se TARGET_PUUID estiver vazio, pegamos o primeiro jogador do arquivo
    if p['puuid'] == TARGET_PUUID or TARGET_PUUID == "coloque_seu_puuid_aqui":
        target_id = str(p['participantId']) # Timeline usa string nas chaves
        target_team = p['teamId']
        target_position = p['teamPosition'] # Ex: "MIDDLE", "TOP"
        break

# Passo B: Encontrar o Oponente Direto
for p in participants:
    if p['teamPosition'] == target_position and p['teamId'] != target_team:
        opponent_id = str(p['participantId'])
        break

print(f"Alvo ID: {target_id} | Oponente ID: {opponent_id} | Rota: {target_position}")

# ==========================================
# 3. EXTRAÇÃO TEMPORAL (ENDPOINT TIMELINE)
# ==========================================
frames = timeline_data['info']['frames']
all_rows = []

for minute_idx, frame in enumerate(frames):
    p_frames = frame['participantFrames']
    
    # Extrair status momentâneo do Alvo
    target_stats = p_frames[target_id]
    t_gold = target_stats['totalGold']
    t_xp = target_stats['xp']
    t_cs = target_stats['minionsKilled'] + target_stats['jungleMinionsKilled']
    
    # Extrair status momentâneo do Oponente
    opp_stats = p_frames[opponent_id]
    o_gold = opp_stats['totalGold']
    o_xp = opp_stats['xp']
    o_cs = opp_stats['minionsKilled'] + opp_stats['jungleMinionsKilled']
    
    # Adicionar à nossa tabela
    all_rows.append({
        'minute': minute_idx,
        'target_gold': t_gold,
        'opp_gold': o_gold,
        'gold_diff': t_gold - o_gold,  # Positivo = Vantagem nossa
        'xp_diff': t_xp - o_xp,
        'cs_diff': t_cs - o_cs
    })

# ==========================================
# 4. PROCESSAMENTO COM PANDAS
# ==========================================
df = pd.DataFrame(all_rows)

# O TRUQUE PARA O SEU FEEDBACK:
# A função .diff() do Pandas pega o valor da linha atual e subtrai da linha anterior.
# Isso nos diz "Quanto de VANTAGEM DE OURO ele ganhou ou perdeu APENAS neste minuto?"
df['gold_diff_variation'] = df['gold_diff'].diff().fillna(0)

# Salvar para visualizar depois (ou usar no Dashboard)
df.to_csv('lane_phase_analysis.csv', index=False)

# Imprimir um recorte interessante (ex: minutos 10 a 20)
print("\nEvolução da Vantagem (Minutos 10 ao 20):")
# Pegamos do minuto 10 ao 20, se o jogo durou isso tudo
print(df[df['minute'].between(10, 20)][['minute', 'gold_diff', 'gold_diff_variation']])