import os
import json
import pandas as pd
from collections import Counter

# ==========================================
# 1. CONFIGURAÇÕES INICIAIS
# ==========================================
TARGET_PUUID = "7AgGA9LTylxhg3FITJz7MVsA5O-UQS2Mn_CFJ9MPzl23d-ig6yOZ1MQdNPkbFJUgSk73DHZzStaDbA" 
base_folder = "adc_matches"
output_filename = "analise_focada_main_adc.csv"

if not os.path.exists(base_folder):
    print(f"Erro: A pasta '{base_folder}' não foi encontrada.")
    exit()

print("Iniciando pipeline de processamento...\n")

# ==========================================
# PASSO 1: DESCOBRIR O CAMPEÃO MAIS JOGADO
# ==========================================
print(">> PASSO 1: Analisando histórico de campeões...")
champion_counts = Counter()
valid_matches_for_pass_2 = []

for match_id in os.listdir(base_folder):
    match_folder = os.path.join(base_folder, match_id)
    if not os.path.isdir(match_folder): continue
        
    match_file = os.path.join(match_folder, "match_data.json")
    if not os.path.exists(match_file): continue

    with open(match_file, 'r', encoding='utf-8') as f:
        match_data = json.load(f)

    # Verifica se é Ranqueada
    queue_id = match_data['info'].get('queueId')
    if queue_id not in [420, 440]: continue

    # Encontra o jogador e verifica a Role (BOTTOM)
    for p in match_data['info']['participants']:
        if p['puuid'] == TARGET_PUUID:
            if p['teamPosition'] == "BOTTOM":
                champ_name = p['championName']
                champion_counts[champ_name] += 1
                valid_matches_for_pass_2.append(match_id)
            break

if not champion_counts:
    print("Nenhuma partida ranqueada jogada como BOTTOM foi encontrada para este PUUID.")
    exit()

main_champion = champion_counts.most_common(1)[0][0]
main_champ_count = champion_counts.most_common(1)[0][1]

print(f"-> Sucesso! Campeão mais jogado como ADC: {main_champion} ({main_champ_count} partidas registradas).\n")

# ==========================================
# PASSO 2: EXTRAÇÃO TEMPORAL (MAIN CHAMPION)
# ==========================================
print(f">> PASSO 2: Extraindo métricas e resultado final para {main_champion}...")
all_rows = []

for match_id in valid_matches_for_pass_2:
    match_folder = os.path.join(base_folder, match_id)
    match_file = os.path.join(match_folder, "match_data.json")
    timeline_file = os.path.join(match_folder, "timeline_data.json")
    
    if not os.path.exists(timeline_file): continue

    with open(match_file, 'r', encoding='utf-8') as f:
        match_data = json.load(f)
    with open(timeline_file, 'r', encoding='utf-8') as f:
        timeline_data = json.load(f)

    target_id, target_team, target_win = None, None, None
    opp_id = None
    
    participants = match_data['info']['participants']
    
    # Valida o Main Champ e pega o Resultado da Partida (Win/Loss)
    played_main = False
    for p in participants:
        if p['puuid'] == TARGET_PUUID:
            if p['championName'] == main_champion:
                target_id = p['participantId'] 
                target_team = p['teamId']
                # Extraindo a Vitória/Derrota aqui!
                target_win = "Vitória" if p['win'] else "Derrota" 
                played_main = True
            break
            
    if not played_main:
        continue
        
    # Encontra o Oponente
    for p in participants:
        if p['teamPosition'] == "BOTTOM" and p['teamId'] != target_team:
            opp_id = p['participantId']
            break
            
    if not opp_id: continue

    # --- EXTRAÇÃO FRAME A FRAME ---
    frames = timeline_data['info']['frames']
    t_kills, t_deaths = 0, 0
    o_kills, o_deaths = 0, 0
    
    for minute_idx, frame in enumerate(frames):
        # Eventos (Kills/Deaths)
        events = frame.get('events', [])
        for event in events:
            if event.get('type') == 'CHAMPION_KILL':
                killer = event.get('killerId')
                victim = event.get('victimId')
                
                if killer == target_id: t_kills += 1
                if victim == target_id: t_deaths += 1
                if killer == opp_id: o_kills += 1
                if victim == opp_id: o_deaths += 1
        
        # Variáveis de Estado
        p_frames = frame['participantFrames']
        t_stats = p_frames[str(target_id)]
        o_stats = p_frames[str(opp_id)]
        
        t_gold, o_gold = t_stats['totalGold'], o_stats['totalGold']
        t_xp, o_xp = t_stats['xp'], o_stats['xp']
        t_cs = t_stats['minionsKilled'] + t_stats['jungleMinionsKilled']
        o_cs = o_stats['minionsKilled'] + o_stats['jungleMinionsKilled']
        
        all_rows.append({
            'match_id': match_id,
            'champion': main_champion,
            'result': target_win,      # <--- ADICIONADO AQUI
            'minute': minute_idx,
            
            # Alvo
            'target_gold': t_gold, 'target_xp': t_xp, 'target_cs': t_cs,
            'target_kills': t_kills, 'target_deaths': t_deaths,
            
            # Oponente
            'opp_gold': o_gold, 'opp_xp': o_xp, 'opp_cs': o_cs,
            'opp_kills': o_kills, 'opp_deaths': o_deaths,
            
            # Vantagens (Positivo = A favor do Alvo)
            'gold_diff': t_gold - o_gold,
            'xp_diff': t_xp - o_xp,
            'cs_diff': t_cs - o_cs
        })

print(f"Extração concluída. Gerando CSV...")

# ==========================================
# PASSO 3: PANDAS (CÁLCULO DOS DELTAS)
# ==========================================
df = pd.DataFrame(all_rows)

if not df.empty:
    df = df.sort_values(by=['match_id', 'minute'])
    
    # Deltas
    df['gold_diff_variation'] = df.groupby('match_id')['gold_diff'].diff().fillna(0)
    df['xp_diff_variation']   = df.groupby('match_id')['xp_diff'].diff().fillna(0)
    df['cs_diff_variation']   = df.groupby('match_id')['cs_diff'].diff().fillna(0)

    df.to_csv(output_filename, index=False)
    print(f">> SUCESSO! Arquivo exportado: '{output_filename}'.")
    print(f">> Dados consolidados baseados em {main_champ_count} partidas jogando de {main_champion}.")
else:
    print("Erro: Falha ao gerar dataframe final.")