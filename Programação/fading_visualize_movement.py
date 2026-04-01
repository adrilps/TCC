import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.animation import FuncAnimation
from matplotlib.collections import LineCollection
import numpy as np
import os

# 1. Load data
df = pd.read_csv('league_project_data.csv')
target_player = 4 # The player you want to visualize, (1-10)
player_data = df[df['player'] == target_player].reset_index(drop=True)

# 2. Setup Figure
fig, ax = plt.subplots(figsize=(8, 8))
img = mpimg.imread('images/minimap.jpg')
ax.imshow(img, extent=[0, 15000, 0, 15000])

# 3. Initialization
pnt, = ax.plot([], [], 'ro', markersize=8, zorder=5)
time_text = ax.text(500, 14000, '', color='white', fontsize=12, fontweight='bold')

# Create an empty LineCollection for the fading trail
lc = LineCollection([], cmap='viridis', alpha=0.6)
ax.add_collection(lc)

trail_length = 10  # How many previous steps to show

def init():
    ax.set_xlim(0, 15000)
    ax.set_ylim(0, 15000)
    return lc, pnt, time_text

def update(frame):
    if frame == 0:
        return lc, pnt, time_text

    idx = frame - 1
    
    # --- FADING LOGIC ---
    # We take a slice of the last 'trail_length' coordinates
    start_idx = max(0, frame - trail_length)
    x = player_data['x'][start_idx:frame].values
    y = player_data['y'][start_idx:frame].values
    
    if len(x) > 1:
        # Create segments for LineCollection: [(x0, y0), (x1, y1)], [(x1, y1), (x2, y2)]...
        points = np.array([x, y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        lc.set_segments(segments)
        
        # Create an alpha array that fades out (0.1 to 1.0)
        alphas = np.linspace(0.1, 1.0, len(segments))
        lc.set_alpha(alphas)
        lc.set_color('yellow') # You can also map this to a colormap
    
    # Update current position and text
    pnt.set_data([player_data['x'][idx]], [player_data['y'][idx]])
    time_text.set_text(f"Minute: {player_data['minute'][idx]}")
    
    return lc, pnt, time_text

def get_unique_filename(base_name, extension):
    counter = 1
    # Start with something like "player_movement_1.gif"
    filename = f"{base_name}_{counter}.{extension}"
    
    # Keep incrementing while the file exists
    while os.path.exists(filename):
        counter += 1
        filename = f"{base_name}_{counter}.{extension}"
    
    return filename

# 4. Create Animation
ani = FuncAnimation(fig, update, frames=len(player_data) + 1,
                    init_func=init, blit=True, interval=600)

# 5. SAVE THE GIF
# Note: You need the 'pillow' library installed (pip install pillow)
print("Saving animation...")
base = "images/fading_player_movement"
ext = "gif"
unique_name = get_unique_filename(base, ext)

print(f"Saving animation as: {unique_name}")
ani.save(unique_name, writer='pillow', fps=5)
print("Save complete!")

plt.show()
