from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def extract_slot_temperatures(df):
    """
    Extract max temperature and delta T per slot (up to 9 slots).
    Returns lists: slotnumber, maxtemp_on_slot, delta_t_on_slot, power
    """
    last_time = df["elapsed_time"].max()
    df_steady = df[df["elapsed_time"] == last_time]
    card_serials = df_steady["card_serial"].unique()

    slotnumber = []
    maxtemp_on_slot = []
    delta_t_on_slot = []

    for idx, card in enumerate(card_serials):
        if idx >= 9:
            break

        df_card = df_steady[
            (df_steady["card_serial"] == card) & (df_steady["channel"] <= 18)
        ]
        df_card_relevant = df_card[
            df_card["channel"] <= 16
        ]  # exclude backplane thermometers
        min_temp = df_card_relevant["temperature"].min()
        max_temp = df_card_relevant["temperature"].max()
        delta_t = max_temp - min_temp

        slotnumber.append(idx)
        maxtemp_on_slot.append(max_temp)
        delta_t_on_slot.append(delta_t)

    power = df_card["load_power"].sum()
    return slotnumber, maxtemp_on_slot, delta_t_on_slot, power


def plot_temperature_metrics(filelist, labels=None, output_path: Path = None):
    """
    Plot two charts (max temperature and ΔT per slot) for multiple CSV files.
    Each line corresponds to one file.
    """
    if labels is None:
        labels = [Path(f).stem for f in filelist]

    plt.figure(figsize=(10, 5))
    for fpath, label in zip(filelist, labels):
        print(f"Processing file: {fpath} with label: {label}")
        df = pd.read_csv(fpath)
        slotnumber, maxtemp_on_slot, delta_t_on_slot, power = extract_slot_temperatures(
            df
        )
        plt.plot(
            slotnumber, maxtemp_on_slot, marker="o", label=f"{label} ({power:.1f}W)"
        )
    plt.xlabel("DIOT slot number")
    plt.ylabel("Max temperature [°C]")
    name = "max_temp_per_slot.png"
    out_file = name if output_path is None else output_path / name
    plt.title("Max temperature per slot")
    plt.grid(True)
    plt.legend()
    plt.savefig(out_file)
    plt.close()

    plt.figure(figsize=(10, 5))
    for fpath, label in zip(filelist, labels):
        df = pd.read_csv(fpath)
        slotnumber, maxtemp_on_slot, delta_t_on_slot, power = extract_slot_temperatures(
            df
        )
        plt.plot(
            slotnumber, delta_t_on_slot, marker="o", label=f"{label} ({power:.1f}W)"
        )
    plt.xlabel("DIOT slot number")
    plt.ylabel("ΔT [°C]")
    plt.title("ΔT per slot")
    plt.grid(True)
    plt.legend()
    name = "deltaT_per_slot.png"
    out_file = name if output_path is None else output_path / name

    plt.savefig(out_file)
    plt.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Distribution of tempearture and temperature differences across setups"
    )

    parser.add_argument(
        "--data-dir",
        type=str,
        default="results",
        help="Directory containing the CSV files to process (default: 'results').",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Directory to put the images (default: 'results').",
    )

    parser.add_argument(
        "--overwrite",
        "-f",
        action="store_true",
        help="Overwrite existing output files.",
    )

    args = parser.parse_args()

    src_dir = Path.cwd() / args.data_dir
    dest_dir = Path.cwd() / args.output_dir

    setups = sorted([d for d in src_dir.iterdir() if d.is_dir()])

    src_file_prefix = "step_0_20W0"
    if not setups:
        print("No setups found.")
        return

    labels = [l.name for l in setups]

    print("Following setups were found:")
    for i, label in enumerate(labels):
        print(f"\t{i}: {label}")
    print()

    found_src_files = []
    for d in setups:
        found_src_files.append(
            sorted(
                [
                    f
                    for f in src_dir.joinpath(d).iterdir()
                    if f.name.startswith(src_file_prefix)
                ]
            )[0]
        )

    filelist = found_src_files
    plot_temperature_metrics(filelist, labels, dest_dir)


if __name__ == "__main__":
    main()
