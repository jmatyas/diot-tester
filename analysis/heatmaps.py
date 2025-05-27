from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import Rbf, griddata

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


def preprocess(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float, float]:
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
    ax.scatter(
        x_meas,
        y_meas,
        c=z_meas,
        cmap="coolwarm",
        vmin=COLORBAR_MIN_TEMP,
        vmax=COLORBAR_MAX_TEMP,
        s=40,
        edgecolors="black",
    )

    # Add labels and title
    ax.set_title(f"Card: {card}", pad=1)

    if show_xlabel:
        ax.set_xlabel("Width [mm]")
    if show_ylabel:
        ax.set_ylabel("Height [mm]")

    # Add power and temperature information

    power = df_card["load_power"].sum()
    last_time = df_card["elapsed_time"].max()
    df_card_steady = df_card[df_card["elapsed_time"] == last_time]
    df_card_relevant = df_card_steady[df_card_steady["channel"] <= 16]
    min_temp = df_card_relevant["temperature"].min()
    max_temp = df_card_relevant["temperature"].max()
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


def generate_heatmap_grid(df: pd.DataFrame, output_path: Path) -> None:
    """Generate a grid of heatmaps for all cards in the input file.

    Args:
        input_file: Path to the input CSV file with measurements
    """
    # Create output directory if needed

    # Load and process data
    df_steady, df_relevant, global_min_temp, global_max_temp = preprocess(df)
    card_serials = df_steady["card_serial"].unique()
    pwr = df_steady.loc[df_steady["card_serial"] == card_serials[0], "load_power"].sum()

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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"Heatmap grid generated for '{output_path.name}'")


def main() -> None:
    """Main function to process data and generate plots."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Process temperature data and generate transient plots."
    )

    parser.add_argument(
        "--data-dir",
        type=str,
        default="results",
        help="Directory containing the CSV files to process (default: 'results'). Fan setup will be appended to the directory.",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Directory to put the transient images (default: 'results'). Fan setup will be appended to the directory.",
    )
    parser.add_argument(
        "fans",
        choices=["schroff", "80", "100"],
        help="Fan setup to use for the analysis.",
    )
    parser.add_argument(
        "--overwrite",
        "-f",
        action="store_true",
        help="Overwrite existing output files.",
    )

    args = parser.parse_args()

    fan_str = {
        "schroff": "SCHROFF",
        "80": "CUSTOM_80",
        "100": "CUSTOM_100",
    }[args.fans]

    src_dir = Path.cwd() / args.data_dir / fan_str
    dest_dir = Path.cwd() / args.output_dir / fan_str / "heatmaps"

    if not src_dir.exists():
        print(f"Source directory {src_dir} does not exist.")
        return

    print(f"Looking for files in '{src_dir}'...")

    files = sorted([f for f in src_dir.iterdir() if f.suffix == ".csv"])

    if files:
        print(f"Found {len(files)} files:")
        for i, file in enumerate(files):
            print(f"\t{i}: {file.name}")
        print()
    else:
        print("No CSV files found in the directory.")
        print("\tusing example file...")
        files = ["example_measurement.csv"]

    print(f"Output will be saved to '{dest_dir}'.")

    # files = files[-1:]  # Process only the last file for demonstration
    for fpath in files:
        print(f"Processing file: '{fpath.name}'")
        base_name = fpath.stem

        df = pd.read_csv(fpath)

        out_path = dest_dir / f"{base_name}.png"
        if out_path.exists() and not args.overwrite:
            print(
                f"Output file '{out_path.name}' already exists. Use --overwrite to overwrite."
            )
            continue

        generate_heatmap_grid(df, out_path)


if __name__ == "__main__":
    main()
