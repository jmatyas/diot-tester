import os

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib import ticker


def setup_axis(ax: plt.Axes) -> None:
    """Configure axis ticks and formatting for temperature plots.

    Args:
        ax: The matplotlib axis to configure
    """
    ax.xaxis.set_major_locator(ticker.MultipleLocator(60.00))
    ax.xaxis.set_minor_locator(ticker.MultipleLocator(20.0))
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x / 60:.0f}"))
    ax.xaxis.set_ticks_position("bottom")
    ax.yaxis.set_major_locator(ticker.MultipleLocator(10.0))
    ax.yaxis.set_minor_locator(ticker.MultipleLocator(5.0))
    ax.tick_params(which="major", width=1.00, length=5)
    ax.tick_params(which="minor", width=0.75, length=2.5, labelsize=5)
    ax.xaxis.set_tick_params(labelsize=10)


def create_temperature_plots(df: pd.DataFrame, output_path: str) -> None:
    """Create a grid of temperature vs time plots.

    Args:
        df: DataFrame containing temperature measurements
        output_path: Path where the plot will be saved
    """
    sns.set_theme(style="ticks", palette="colorblind")

    card_serials = df["card_serial"].unique()
    timestamps = df["elapsed_time"].unique()
    pwr = df.loc[
        (df["elapsed_time"] == timestamps[0]) & (df["card_serial"] == card_serials[0]),
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
    g.figure.set_size_inches(14, 12)
    g.figure.set_dpi(300)
    g.figure.suptitle(f"Temperature vs Time\n{pwr:.2f} W per card", fontsize=16)
    g.figure.subplots_adjust(
        top=0.92, bottom=0.1, hspace=0.18
    )  # Adjust the top space for the title
    g.set_axis_labels("Time [min]", "Temperature [°C]")
    g.set_titles(col_template="Card: {col_name}")
    g.set(ylim=(20, 85))

    axes = g.axes.flatten()
    for ax, card_id in zip(axes, card_serials, strict=True):
        card_df = df[df["card_serial"] == card_id]
        ss_achieved = card_df.loc[
            card_df["elapsed_time"] == card_df["elapsed_time"].max(), "steady_state"
        ].all()
        ss_text = "Steady State ✓" if ss_achieved else "Not Steady"
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

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    g.savefig(output_path, bbox_inches="tight")
    plt.close()


def main() -> None:
    """Main function to process data and generate plots."""
    DIRECTORY = "results"
    ROOT_DIR = os.getcwd()
    print(f"Root directory: {ROOT_DIR}")

    files = [f for f in os.listdir(DIRECTORY) if f.endswith(".csv")]
    if files:
        print("Available files:")
        for i, file in enumerate(files):
            print(f"{i}: {file}")
    else:
        print("No CSV files found in the directory.")
        print("\tusing example file...")
        files = ["example_measurement.csv"]

    # files = files[-1:]  # Process only the last file for demonstration
    for fname in files:
        print(f"Processing file: {fname}")
        path = os.path.join(DIRECTORY, fname)
        base_name = os.path.splitext(fname)[0]

        df = pd.read_csv(path)

        output_path = f"{ROOT_DIR}/plots/{base_name}_temperature.png"
        create_temperature_plots(df, output_path)
        print(f"Temperature plots generated: {output_path}")


if __name__ == "__main__":
    main()
