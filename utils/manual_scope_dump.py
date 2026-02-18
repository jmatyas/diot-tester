from pathlib import Path
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt

from scope import dump_current_scope_to_csv

"""
Manual waveform dump utility.

This script does NOT configure, reset, or trigger the oscilloscope.
It only connects to the instrument and downloads the currently
acquired/displayed waveform as-is.

The acquisition and triggering must be performed manually
from the oscilloscope front panel before running this script.
"""

IP = "192.168.95.106"

def plot_dump(folder: Path, base_name_with_ts: str, channels: tuple[int, ...]) -> Path:
    fig = plt.figure()
    ax = fig.add_subplot(111)

    for ch in channels:
        csv_path = folder / f"{base_name_with_ts}_chan{ch}.csv"
        df = pd.read_csv(csv_path)

        ax.plot(df["time"], df["voltage"], label=f"CH{ch}")

    ax.set_xlabel("time (s)")
    ax.set_ylabel("voltage (V)")
    ax.grid(True)
    ax.legend()

    out_png = folder / f"{base_name_with_ts}_all_channels.png"
    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"=> saved {out_png}")
    return out_png


def main():
    base_folder = Path("manual_dump")
    channels = (1, 2)

    # One timestamp for folder + filenames
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    measurement_folder = base_folder / ts
    measurement_folder.mkdir(parents=True, exist_ok=True)

    base_name_with_ts = f"manual_dump_{ts}"

    dump_current_scope_to_csv(
        identifier=IP,
        outdir=measurement_folder,
        base_name=base_name_with_ts,
        channels=channels,
    )

    plot_dump(
        folder=measurement_folder,
        base_name_with_ts=base_name_with_ts,
        channels=channels,
    )


if __name__ == "__main__":
    main()
