import os
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import Rbf, griddata
import seaborn as sns
import matplotlib
from matplotlib import ticker

# Constants
FANS_SETUP = "SCHROFF"

RESULTS_DIR = r"C:\Users\Konrad Norowski\Desktop\Nowy folder\260525\results\SCHROFF"
HEATMAPS_DIR = r"C:\Users\Konrad Norowski\Desktop\Nowy folder\260525\plots_heatmaps"
TRANSIENTS_DIR = r"C:\Users\Konrad Norowski\Desktop\Nowy folder\260525\plots_transients"

COLORBAR_MIN_TEMP = 20.0
COLORBAR_MAX_TEMP = 80.0

PCB_WIDTH = 220  # mm
PCB_HEIGHT = 100  # mm

# Channel positions [(X,Y) in millimeters]
# Origin at lower left vertex in Altium file, near channel 12
CHANNEL_POSITIONS = {
    # IC11A - Thermometer designator in Altium file
    0: (20 + 0 * 49, 12 + 3 * 26.5),
    1: (20 + 1 * 49, 12 + 3 * 26.5),
    2: (20 + 2 * 49, 12 + 3 * 26.5),
    3: (20 + 3 * 49, 12 + 3 * 26.5),
    # IC11E
    4: (20 + 0 * 49, 12 + 2 * 26.5),
    5: (20 + 1 * 49, 12 + 2 * 26.5),
    6: (20 + 2 * 49, 12 + 2 * 26.5),
    7: (20 + 3 * 49, 12 + 2 * 26.5),
    # IC11I
    8: (20 + 0 * 49, 12 + 1 * 26.5),
    9: (20 + 1 * 49, 12 + 1 * 26.5),
    10: (20 + 2 * 49, 12 + 1 * 26.5),
    11: (20 + 3 * 49, 12 + 1 * 26.5),
    # IC11I
    12: (20 + 0 * 49, 12 + 0 * 26.5),
    13: (20 + 1 * 49, 12 + 0 * 26.5),
    14: (20 + 2 * 49, 12 + 0 * 26.5),
    15: (20 + 3 * 49, 12 + 0 * 26.5),
    # Additional ICs
    16: (87, 52.5),  # IC33
    17: (212.5, 77.0),  # IC21
    18: (208.5, 18),  # IC22
}


def load_data(file_path: str) -> "tuple[pd.DataFrame, pd.DataFrame, float, float]":
    """Load and preprocess measurement data from CSV file.

    Args:
        file_path: Path to the CSV file with measurement data

    Returns:
        Tuple containing:
        - DataFrame with measurements at last timestamp
        - DataFrame with relevant measurements (channel <= 18)
        - Global minimum temperature
        - Global maximum temperature
    """
    df = pd.read_csv(file_path)

    # Data from last timestamp (steady state)
    last_time = df["elapsed_time"].max()
    df_steady = df[df["elapsed_time"] == last_time]

    # Filter relevant channels and get global temperature range
    df_relevant = df_steady[df_steady["channel"] <= 18]
    global_min_temp = df_relevant["temperature"].min()
    global_max_temp = df_relevant["temperature"].max()

    return df_steady, df_relevant, global_min_temp, global_max_temp


def create_single_heatmap(
    ax: plt.Axes,
    df_card: pd.DataFrame,
    card: str,
    global_min_temp: float,
    global_max_temp: float,
    show_xlabel: bool,
    show_ylabel: bool,
    row: int,
    col: int,
) -> plt.Artist:
    """Create a heatmap for a single card in the given subplot.

    Args:
        ax: Matplotlib axes to plot on
        df_card: DataFrame with measurements for specific card
        card: Card serial number
        global_min_temp: Minimum temperature across all cards
        global_max_temp: Maximum temperature across all cards
        show_xlabel: Whether to show x-axis label
        show_ylabel: Whether to show y-axis label
        row: Row index in the subplot grid
        col: Column index in the subplot grid
    """
    # Prepare measurement data
    df_card["x"] = df_card["channel"].map(lambda ch: CHANNEL_POSITIONS[ch][0])
    df_card["y"] = df_card["channel"].map(lambda ch: CHANNEL_POSITIONS[ch][1])

    x_meas = df_card["x"].values
    y_meas = df_card["y"].values
    z_meas = df_card["temperature"].values

    # Interpolation using RBF
    rbf = Rbf(x_meas, y_meas, z_meas, function="linear")
    grid_x, grid_y = np.mgrid[0:PCB_WIDTH:300j, 0:PCB_HEIGHT:200j]
    grid_z = rbf(grid_x, grid_y)

    # Linear or nearest neighbor interpolation
    # grid_x, grid_y = np.mgrid[0:PCB_WIDTH:300j, 0:PCB_HEIGHT:200j]
    # points = np.column_stack((x_meas, y_meas))
    # grid_z = griddata(points, z_meas, (grid_x, grid_y), method="linear") #method=linear or nearest

    # Create heatmap
    c = ax.imshow(
        grid_z.T,
        extent=(0, PCB_WIDTH, 0, PCB_HEIGHT),
        origin="lower",
        cmap="coolwarm",
        aspect="equal",
        vmin=COLORBAR_MIN_TEMP,
        vmax=COLORBAR_MAX_TEMP,
    )

    # Add measurement points
    ax.scatter(x_meas, y_meas, c=z_meas, cmap='coolwarm',
               vmin=COLORBAR_MIN_TEMP, vmax=COLORBAR_MAX_TEMP,
               s=40, edgecolors='black')

    # Add labels and title
    ax.set_title(f"Card: {card}", pad=1)

    if show_xlabel:
        ax.set_xlabel("Width [mm]")
    if show_ylabel:
        ax.set_ylabel("Height [mm]")

    # Add power and temperature information

    power = df_card["load_power"].sum()
    last_time = df_card['elapsed_time'].max()
    df_card_steady = df_card[df_card['elapsed_time'] == last_time]
    df_card_relevant = df_card_steady[df_card_steady['channel'] <= 16]
    min_temp = df_card_relevant['temperature'].min()
    max_temp = df_card_relevant['temperature'].max()
    delta_t = max_temp - min_temp

    txt_y_base = PCB_HEIGHT + 1
    ax.text(
        0,
        txt_y_base,
        f"Power: {power:.1f}W\n"
        f"ΔT: {delta_t:.1f}°C\n"
        f"({max_temp:.1f}°C - {min_temp:.1f}°C)",
        fontsize=8,
        ha="left",
        va="bottom",
    )

    # Add board orientation labels only on edge plots
    if col == 0:  # Leftmost plots
        ax.text(
            -20,
            PCB_HEIGHT / 2,
            "FRONT",
            fontsize=8,
            rotation="vertical",
            va="center",
            ha="right",
        )
    if row == 0:  # Top row plots
        ax.text(
            PCB_WIDTH - 20, PCB_HEIGHT + 8, "TOP", fontsize=8, ha="center", va="bottom"
        )

    return c


def generate_heatmap_grid(input_file: str) -> None:
    """Generate a grid of heatmaps for all cards in the input file.

    Args:
        input_file: Path to the input CSV file with measurements
    """
    # Create output directory if needed
    if not os.path.exists(HEATMAPS_DIR):
        os.makedirs(HEATMAPS_DIR)

    # Get base filename for output
    filename = os.path.splitext(os.path.basename(input_file))[0]

    # Load and process data
    df_steady, df_relevant, global_min_temp, global_max_temp = load_data(
        input_file)
    card_serials = df_steady["card_serial"].unique()
    pwr = df_steady.loc[df_steady["card_serial"]
                        == card_serials[0], "load_power"].sum()

    # Create figure with 3x3 grid
    fig = plt.figure(figsize=(14, 8))
    fig.suptitle(
        f"Temperature Distribution - {pwr:.2f} W per card", fontsize=16, y=0.98
    )

    # Create subplot grid with shared axes and minimal spacing
    gs = plt.GridSpec(3, 3, figure=fig)  # , hspace=0.02, wspace=0.05)

    # Generate heatmap for each card
    colorbar = None
    for idx, card in enumerate(card_serials):
        if idx >= 9:  # Only process first 9 cards
            break

        # Calculate grid position
        row = idx // 3
        col = idx % 3

        # Create subplot and share axes appropriately
        ax = fig.add_subplot(gs[row, col])

        # Show labels only for leftmost and bottom plots
        show_xlabel = row == 2  # Bottom row
        show_ylabel = col == 0  # Leftmost column

        # Prepare data for this card
        df_card = df_steady[
            (df_steady["card_serial"] == card) & (df_steady["channel"] <= 18)
        ].copy()

        # Create heatmap in this subplot
        colorbar = create_single_heatmap(
            ax,
            df_card,
            card,
            global_min_temp,
            global_max_temp,
            show_xlabel,
            show_ylabel,
            row,
            col,
        )

        # Hide tick labels for non-edge plots
        if not show_xlabel:
            ax.set_xticklabels([])
        if not show_ylabel:
            ax.set_yticklabels([])

    # Add a horizontal colorbar at the bottom
    cbar_ax = fig.add_axes([0.15, 0.05, 0.7, 0.02])
    fig.colorbar(
        colorbar, cax=cbar_ax, orientation="horizontal", label="Temperature [°C]"
    )

    # Save the figure
    output_path = os.path.join(HEATMAPS_DIR, f"{filename}_heatmap_grid.png")
    fig.savefig(output_path, bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"Heatmap grid generated for {filename}")


def setup_axis(ax: plt.Axes) -> None:
    """Configure axis ticks and formatting for temperature plots.

    Args:
        ax: The matplotlib axis to configure
    """
    ax.xaxis.set_major_locator(ticker.MultipleLocator(60.00))
    ax.xaxis.set_minor_locator(ticker.MultipleLocator(20.0))
    ax.xaxis.set_major_formatter(
        ticker.FuncFormatter(lambda x, _: f"{x / 60:.0f}"))
    ax.xaxis.set_ticks_position("bottom")
    ax.yaxis.set_major_locator(ticker.MultipleLocator(10.0))
    ax.yaxis.set_minor_locator(ticker.MultipleLocator(5.0))
    ax.tick_params(which="major", width=1.00, length=5)
    ax.tick_params(which="minor", width=0.75, length=2.5, labelsize=5)
    ax.xaxis.set_tick_params(labelsize=10)


def create_temperature_plots(input_file) -> None:
    """Create a grid of temperature vs time plots.

    Args:
        df: DataFrame containing temperature measurements
        output_path: Path where the plot will be saved
    """
    sns.set_theme(
        style="darkgrid",
        palette="colorblind",
    )
    df = pd.read_csv(input_file)

    last_time = df['elapsed_time'].max()
    df_steady = df[df['elapsed_time'] == last_time]

    grouped = df_steady[df_steady['channel'] <= 16].groupby('card_serial')
    Tmax_per_card = grouped['temperature'].max()
    Tmin_per_card = grouped['temperature'].min()
    deltaT_per_card = Tmax_per_card - Tmin_per_card
    max_deltaT = deltaT_per_card.max()
    card_deltaT = deltaT_per_card.idxmax()
    Tmin_on_card = Tmin_per_card[card_deltaT]
    Tmax_on_card = Tmax_per_card[card_deltaT]
    max_T = Tmax_per_card.max()
    card_Tmax = Tmax_per_card.idxmax()
    min_T = Tmin_per_card.min()
    card_Tmin = Tmin_per_card.idxmin()

    filename = os.path.splitext(os.path.basename(input_file))[0]

    card_serials = df["card_serial"].unique()
    timestamps = df["elapsed_time"].unique()
    pwr = df.loc[
        (df["elapsed_time"] == timestamps[0]) & (
            df["card_serial"] == card_serials[0]),
        "load_power",
    ].sum()

    g = sns.relplot(
        data=df,
        x="elapsed_time",
        y="temperature",
        hue="channel",
        palette="colorblind",
        kind="line",
        col="card_serial",
        col_order=card_serials,
        col_wrap=3,
        height=5,
        aspect=1,
    )

    sns.despine(top=True, right=True)
    g.map(plt.axhline, y=80, color="r", linestyle="--", label="OT: 80 °C")
    g.figure.set_size_inches(14, 11)
    g.figure.set_dpi(300)
    g.figure.suptitle(
        f"Temperature vs Time\n{pwr:.2f} W per card", fontsize=16)
    g.figure.subplots_adjust(
        top=0.92, bottom=0.1, hspace=0.18
    )  # Adjust the top space for the title
    g.set_axis_labels("Time [min]", "Temperature [°C]")
    g.set_titles(col_template="Card: {col_name}")

    # Restore axis labels and tick labels only for bottom row and left column
    n_cols = g._ncol
    n_axes = len(g.axes.flat)
    for i, ax in enumerate(g.axes.flat):
        if i >= n_axes - n_cols:  # bottom row
            ax.set_xlabel("Time [min]")
            ax.tick_params(axis="x", labelbottom=True)  # show x tick labels
        if i % n_cols == 0:  # left column
            ax.set_ylabel("Temperature [°C]")
            ax.tick_params(axis="y", labelleft=True)    # show y tick labels

    g.set(ylim=(20, 85))

    summary = (
        f"Max ΔT = {max_deltaT:.1f} °C (Tmax = {Tmax_on_card:.1f} °C, "
        f"Tmin = {Tmin_on_card:.1f} °C) on card {card_deltaT}    |    "
        f"Max T = {max_T:.1f} °C on card {card_Tmax}    |    "
        f"Min T = {min_T:.1f} °C on card {card_Tmin}"
    )

    g.fig.text(0.7, 0.03, summary, ha='center', fontsize=10)

    axes = g.axes.flatten()
    if len(axes) != len(card_serials):
        raise ValueError(
            "Length mismatch between number of axes and card_serials")

    # Identify bottom row and left column axes

    # Identify bottom row and left column axes
    bottom_row_axes = (
        g.axes[-1] if isinstance(g.axes[-1], list) else [g.axes[-1]]
    )
    left_col_axes = [row[0] for row in g.axes if isinstance(row, list)]

    for ax, card_id in zip(axes, card_serials):
        df_card = df[df["card_serial"] == card_id]
        ss_achieved = df_card.loc[
            df_card["elapsed_time"] == df_card["elapsed_time"].max(), "steady_state"
        ].all()
        ss_text = "Steady State achieved!" if ss_achieved else "Not Steady"
        plt.text(
            0.02,
            0.99,
            ss_text,
            transform=ax.transAxes,
            fontsize=10,
            color="green" if ss_achieved else "red",
            verticalalignment="top",
        )

        plt.text(
            0.75,
            0.99,
            "OT: 80 °C",
            transform=ax.transAxes,
            fontsize=10,
            color="red",
            verticalalignment="top",
        )

        setup_axis(ax)

        # Hide X tick labels for all but the bottom row

    output_path = Path(TRANSIENTS_DIR) / f"{filename}_transients.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    g.savefig(output_path, bbox_inches="tight")
    plt.close()
    print(f"Transient plots generated for {filename}")


def main() -> None:
    """Main function to process data files and generate heatmaps and transients."""
    print(f"Root directory: {os.getcwd()}")

    # Get list of data files
    files = [f for f in os.listdir(RESULTS_DIR) if f.endswith(".csv")]

    if files:
        print("Available files:")
        for i, file in enumerate(files):
            print(f"{i}: {file}")
    else:
        print("No CSV files found in the directory.")
        print("\tusing example file...")
        files = ["example_measurement.csv"]

    # Process each file
    for file in files:
        print(f"Processing file: {file}")
        file_path = os.path.join(RESULTS_DIR, file)
        generate_heatmap_grid(file_path)
        create_temperature_plots(file_path)

    print("All heatmaps generated.")
    print("All transients generated.")


if __name__ == "__main__":
    main()
