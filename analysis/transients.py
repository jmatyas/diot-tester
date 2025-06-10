from pathlib import Path

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


def summarise(df: pd.DataFrame):
    # get only the last measurement; silently assume that the last measurement
    # should be the steady state; but this is determined by the actual measurement
    # situation (scenario step)
    df_last = df[df["elapsed_time"] == df["elapsed_time"].max()]

    # use for summary only the first 17 - other two are located near the backplane
    # and they are significantly cooler than the others (empirically determined)
    grouped = df_last[df_last["channel"] <= 16].groupby("card_serial")
    cardwise_Tmax, cardwise_Tmin = (
        grouped["temperature"].max(),
        grouped["temperature"].min(),
    )
    overall_Tmax, overall_Tmax_card = cardwise_Tmax.max(), cardwise_Tmax.idxmax()
    overall_Tmin, overall_Tmin_card = cardwise_Tmin.min(), cardwise_Tmin.idxmin()

    # DT - delta temperature
    cardwise_DT = cardwise_Tmax - cardwise_Tmin

    highest_DT, highest_DT_card = cardwise_DT.max(), cardwise_DT.idxmax()

    highest_DT_card_Tmin = cardwise_Tmin[highest_DT_card]
    highest_DT_card_Tmax = cardwise_Tmax[highest_DT_card]

    summary = (
        f"Max ΔT = {highest_DT:.1f} °C (Tmax = {highest_DT_card_Tmax:.1f} °C, "
        f"Tmin = {highest_DT_card_Tmin:.1f} °C) on card {highest_DT_card}    |    "
        f"Overall Max T = {overall_Tmax:.1f} °C on card {overall_Tmax_card}    |    "
        f"Overall Min T = {overall_Tmin:.1f} °C on card {overall_Tmin_card}"
    )

    return summary


def create_temperature_plots(df: pd.DataFrame, output_path: Path) -> None:
    """Create a grid of temperature vs time plots.

    Args:
        df: DataFrame containing temperature measurements
        output_path: Path where the plot will be saved
    """
    sns.set_theme(style="darkgrid", palette="colorblind")

    summary = summarise(df)

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
    g.figure.text(0.7, 0.03, summary, ha="center", fontsize=10)

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

    output_path.parent.mkdir(parents=True, exist_ok=True)

    g.savefig(output_path, bbox_inches="tight")
    plt.close()
    print(f"Transient plots generated for '{output_path.name}'")


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
        choices=[
            "schroff",
            "80",
            "100",
            "backplane",
            "backplane_guided",
            "backplane_guided_front_coverless",
        ],
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
        "backplane": "BACKPLANE",
        "backplane_guided": "BACKPLANE_GUIDED",
        "backplane_guided_front_coverless": "BACKPLANE_GUIDED_FRONT_COVERLESS",
    }[args.fans]

    src_dir = Path.cwd() / args.data_dir / fan_str
    dest_dir = Path.cwd() / args.output_dir / fan_str / "transients"

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

        create_temperature_plots(df, out_path)


if __name__ == "__main__":
    main()
