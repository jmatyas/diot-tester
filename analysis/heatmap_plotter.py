import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import Rbf

DIRECTORY = "results"
MAP_DIRECTORY = "heatmaps"

files = [
    "test_20.csv",
    "test_25.csv",
    "test_30.csv",
    "test_35.csv",
    "test_40.csv",
]
file = files[-1]
file_example = "example_measurement.csv"

path = f"{file_example}" if file == "" else f"{DIRECTORY}/{file}"
# === 1. Data loading ===
fileaddress = path
df = pd.read_csv(fileaddress)
filename = os.path.splitext(os.path.basename(fileaddress))[0]

if not os.path.exists(MAP_DIRECTORY):
    os.makedirs(MAP_DIRECTORY)

# data from last time signature defined as a measurement in steady state
last_time = df['elapsed_time'].max()
df_steady = df[df['elapsed_time'] == last_time]

# global max and min temperature, from all boards
df_relevant = df_steady[df_steady['channel'] <= 18]
global_min_temp = df_relevant['temperature'].min()
global_max_temp = df_relevant['temperature'].max()

# === 2. PCB geometry parameters ===
pcb_width = 220     # mm
pcb_height = 100    # mm

# === 3. Canal positions [(X,Y) in milimeters]- (origin of the coordinate system is anchored at the vertex closest to the channel 12, "the lower left vertex" in ALtium file)
kanał_xy_mm = {
    # IC11A -Thermometer designator in Altium file
    0: (20 + 0*49, 12 + 3*26.5),
    1: (20 + 1*49, 12 + 3*26.5),
    2: (20 + 2*49, 12 + 3*26.5),
    3: (20 + 3*49, 12 + 3*26.5),

    4: (20 + 0*49, 12 + 2*26.5),  # IC11E
    5: (20 + 1*49, 12 + 2*26.5),
    6: (20 + 2*49, 12 + 2*26.5),
    7: (20 + 3*49, 12 + 2*26.5),

    8: (20 + 0*49, 12 + 1*26.5),  # IC11I
    9: (20 + 1*49, 12 + 1*26.5),
    10: (20 + 2*49, 12 + 1*26.5),
    11: (20 + 3*49, 12 + 1*26.5),

    12: (20 + 0*49, 12 + 0*26.5),  # IC11I
    13: (20 + 1*49, 12 + 0*26.5),
    14: (20 + 2*49, 12 + 0*26.5),
    15: (20 + 3*49, 12 + 0*26.5),

    16: (87, 52.5),  # IC33
    17: (212.5, 77.0),  # IC21
    18: (208.5, 18),  # IC22

}

# === 4. Iteration by boards (cards) ===
for card in df_steady['card_serial'].unique()[:3]:
    df_card = df_steady[(df_steady['card_serial'] == card)
                        & (df_steady['channel'] <= 18)].copy()

    # Assigning positions to channels
    df_card['x'] = df_card['channel'].map(lambda ch: kanał_xy_mm[ch][0])
    df_card['y'] = df_card['channel'].map(lambda ch: kanał_xy_mm[ch][1])

    x_meas = df_card['x'].values
    y_meas = df_card['y'].values
    z_meas = df_card['temperature'].values

    # Interpolation and extrapolation (RBF)
    rbf = Rbf(x_meas, y_meas, z_meas, function='cubic')
    grid_x, grid_y = np.mgrid[0:pcb_width:300j, 0:pcb_height:200j]
    grid_z = rbf(grid_x, grid_y)

    # === 5. Plotting the heatmap ===
    plt.figure(figsize=(12, 5))
    c = plt.imshow(
        grid_z.T,
        extent=(0, pcb_width, 0, pcb_height),
        origin='lower',
        cmap='coolwarm',
        aspect='equal',
        vmin=global_min_temp,
        vmax=global_max_temp
    )

    plt.scatter(x_meas, y_meas, c='black', s=40, label='Measurement points')
    plt.colorbar(c, label='Temperature [°C]')
    plt.title(f'Heatmap – {card}')
    plt.xlabel(' X Axis (PCB width) [mm]')
    plt.ylabel(' Y Axis (PCB height) [mm]')
    plt.legend(loc='upper left', bbox_to_anchor=(0.8, 1.075), frameon=False)

    # Overall power
    power = df_card['load_power'].sum()
    plt.text(0, pcb_height,
             f'Overall power: {power:.2f} W', fontsize=10, ha='left', va='bottom')

    # ΔT - measured difference between Tmax and Tmin for a specific board - it does not take extrapolated points into account
    delta_T = z_meas.max() - z_meas.min()
    plt.text(0, pcb_height + 9,
             f'Max T measured on a board {card}: {z_meas.max():.2f} °C', fontsize=10, ha='left', va='bottom')
    plt.text(0, pcb_height + 6,
             f'Min T measured on a board {card}: {z_meas.min():.2f} °C', fontsize=10, ha='left', va='bottom')
    plt.text(0, pcb_height + 3,
             f'Max T-Min T on board {card}= {delta_T:.2f} °C', fontsize=10, ha='left', va='bottom')
    plt.text(
        -15, pcb_height / 2,
        'board front',
        fontsize=11,
        rotation='vertical',
        va='center',
        ha='right')

    plt.text(
        pcb_width / 2, pcb_height + 6,
        'board top',
        fontsize=11,
        ha='center',
        va='bottom')

    plt.tight_layout()
    plt.savefig(f'{MAP_DIRECTORY}/interpolated_map_{filename}_{card}.png')
    plt.close()
    print(f'Map {card} generated.')

print("All maps generated.")
