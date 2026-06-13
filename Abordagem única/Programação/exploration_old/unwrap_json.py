import pandas as pd, json

try:
    with open('timeline_data.json','r') as file:
        data = json.load(file)
except FileNotFoundError:
    print("file not found")
    exit()

# Assume 'data' is the JSON you got from the API
frames = data['info']['frames']
all_rows = []

# Loop through each minute (frame)
for minute_idx, frame in enumerate(frames):
    p_frames = frame['participantFrames']
    
    for pid, stats in p_frames.items():
        all_rows.append({
            'minute': minute_idx,
            'player': pid,
            'x': stats['position']['x'],
            'y': stats['position']['y'],
            'gold': stats['totalGold']
        })


# Create the table
df = pd.DataFrame(all_rows)

df.to_csv('league_project_data.csv', index=False)

# Now you can see the first 10 rows!
print(df.head(10))