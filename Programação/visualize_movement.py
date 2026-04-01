import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.animation import FuncAnimation

# 1. Load data
df = pd.read_csv('league_project_data.csv')
target_player = 1
player_data = df[df['player'] == target_player].reset_index(drop=True)

# 2. Setup the Figure and Background
fig, ax = plt.subplots(figsize=(8, 8))

# Load your minimap image
# Replace 'minimap.png' with your actual filename
img = mpimg.imread('images/minimap_3.png')

# The 'extent' maps the image pixels to your data coordinates [x_min, x_max, y_min, y_max]
# Standard LoL coordinates are roughly 0 to 15000
ax.imshow(img, extent=[0, 15000, 0, 15000])

# 3. Initialize plot elements
# 'ln' is the path trail, 'pnt' is the current position dot
ln, = ax.plot([], [], 'r-', alpha=0.6, linewidth=1) 
pnt, = ax.plot([], [], 'ro', markersize=8, label=f'Player {target_player}')
time_text = ax.text(500, 14000, '', color='white', fontsize=12, fontweight='bold')

ax.set_title(f"Player {target_player} Movement")
ax.legend(loc='upper right')

# 4. Animation Functions
def init():
    ax.set_xlim(0, 15000)
    ax.set_ylim(0, 15000)
    return ln, pnt, time_text

def update(frame):
    # 1. Handle the "Frame 0" case to avoid KeyError: -1
    # We only want to update data if we are actually at frame 1 or further
    if frame == 0:
        return ln, pnt, time_text

    # 2. Get data up to the current frame
    # Since frame 1 is our first 'real' data point, we use frame-1 for 0-based indexing
    idx = frame - 1
    
    xdata = player_data['x'][:frame]
    ydata = player_data['y'][:frame]
    
    # Update trail and current point
    ln.set_data(xdata, ydata)
    pnt.set_data([player_data['x'][idx]], [player_data['y'][idx]])
    
    # Update timestamp
    minute = player_data['minute'][idx]
    time_text.set_text(f"Minute: {minute}")
    
    return ln, pnt, time_text

# 5. Run Animation
# frames=len(player_data) tells it how many steps to take
# interval=500 means 500ms between frames (2 frames per second)
ani = FuncAnimation(fig, update, frames=len(player_data) + 1,
                    init_func=init, blit=True, interval=500)

try:
    ani.save('images/player_movement.gif', writer='pillow')
except Exception as e:
    print(f"Error saving animation: {e}")

plt.show()

# To save the animation (requires ffmpeg or pillow installed):