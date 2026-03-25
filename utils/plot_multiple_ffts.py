from pathlib import Path
import pandas as pd
import numpy as np
from matplotlib import pyplot as plt

def export_multi_fft_plot(
    csv_list: list[str | Path],
    out_png: str | Path,
    *,
    labels: list[str] | None = None,
    freq_col: str = "freq_hz",
    dbv_col: str = "avg_dbv",
    atol_hz: float = 0.0,
    drop_dc_for_plot: bool = True,
    y_limits: tuple[float, float] | None = (-160, -40),
    title: str | None = None,
) -> Path:
    """
    Plot FFT spectra from multiple CSV files on one figure and export to PNG.

    All CSV files must share identical (or atol-compatible) frequency grids.
    """

    if len(csv_list) == 0:
        raise ValueError("csv_list cannot be empty.")

    if labels is not None and len(labels) != len(csv_list):
        raise ValueError("Length of labels must match csv_list.")

    csv_list = [Path(p) for p in csv_list]
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)

    # --- Load first file as frequency reference ---
    df_ref = pd.read_csv(csv_list[0])

    required = {freq_col, dbv_col}
    if not required.issubset(df_ref.columns):
        raise ValueError(f"{csv_list[0]} missing columns: {required - set(df_ref.columns)}")

    f_ref = df_ref[freq_col].to_numpy()

    if drop_dc_for_plot:
        mask = f_ref > 0.0
        f_plot = f_ref[mask]
    else:
        mask = slice(None)
        f_plot = f_ref

    plt.figure(figsize=(12, 5))

    # --- Loop over all CSVs ---
    for idx, csv_path in reversed(list(enumerate(csv_list))):
        df = pd.read_csv(csv_path)

        if not required.issubset(df.columns):
            raise ValueError(f"{csv_path} missing columns: {required - set(df.columns)}")

        f = df[freq_col].to_numpy()

        if len(f) != len(f_ref):
            raise ValueError(f"{csv_path} has different number of frequency bins.")

        if atol_hz == 0.0:
            if not np.array_equal(f, f_ref):
                raise ValueError(f"{csv_path} frequency grid mismatch.")
        else:
            if not np.allclose(f, f_ref, atol=atol_hz, rtol=0.0):
                raise ValueError(f"{csv_path} frequency grid mismatch (tolerance).")

        y = df[dbv_col].to_numpy()
        y_plot = y[mask]

        label = labels[idx] if labels is not None else csv_path.stem
        plt.semilogx(f_plot, y_plot, label=label)

    if y_limits is not None:
        plt.ylim(y_limits)

    plt.xlabel("Frequency [Hz]")
    plt.ylabel("Amplitude [dBV] (peak)")

    if title is not None:
        plt.title(title)

    plt.legend()
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()

    return out_png


def export_two_fft_plot(
    csv_a: str | Path,
    csv_b: str | Path,
    out_png: str | Path,
    *,
    label_a: str = "FFT A",
    label_b: str = "FFT B",
    freq_col: str = "freq_hz",
    dbv_col: str = "avg_dbv",
    atol_hz: float = 0.0,
    drop_dc_for_plot: bool = True,
    y_limits: tuple[float, float] | None = (-160, -40),
    title: str | None = None,
) -> Path:
    """
    Plot FFT spectra from two CSV files on one figure and export to PNG.

    Expected input CSV columns:
        freq_hz, avg_amp_v, avg_dbv

    Notes:
    - Requires identical frequency grids (or within atol_hz if provided).
    - Uses dBV column by default.
    """

    csv_a = Path(csv_a)
    csv_b = Path(csv_b)
    out_png = Path(out_png)

    out_png.parent.mkdir(parents=True, exist_ok=True)

    df_a = pd.read_csv(csv_a)
    df_b = pd.read_csv(csv_b)

    required = {freq_col, dbv_col}
    if not required.issubset(df_a.columns):
        raise ValueError(f"{csv_a} missing columns: {required - set(df_a.columns)}")
    if not required.issubset(df_b.columns):
        raise ValueError(f"{csv_b} missing columns: {required - set(df_b.columns)}")

    f_a = df_a[freq_col].to_numpy()
    f_b = df_b[freq_col].to_numpy()

    if len(f_a) != len(f_b):
        raise ValueError("Different number of frequency bins.")

    if atol_hz == 0.0:
        if not np.array_equal(f_a, f_b):
            raise ValueError("Frequency grids are not identical.")
    else:
        if not np.allclose(f_a, f_b, atol=atol_hz, rtol=0.0):
            raise ValueError("Frequency grids differ beyond tolerance.")

    y_a = df_a[dbv_col].to_numpy()
    y_b = df_b[dbv_col].to_numpy()

    if drop_dc_for_plot:
        mask = f_a > 0.0
        f = f_a[mask]
        y_a = y_a[mask]
        y_b = y_b[mask]
    else:
        f = f_a

    plt.figure()
    plt.semilogx(f, y_a, label=label_a)
    plt.semilogx(f, y_b, label=label_b)

    if y_limits is not None:
        plt.ylim(y_limits)

    plt.xlabel("Frequency [Hz]")
    plt.ylabel("Amplitude [dBV] (peak)")

    if title is not None:
        plt.title(title)

    plt.legend()
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()

    return out_png


csv_files = [
    "/home/knorowski/diot-tester/manual_dump/20260317_120155/manual_dump_20260317_120155_chan1.csv"
]

labels = [
    "spectrum",
]

out_png = "/home/knorowski/diot-tester/fft_overlay_multi.png"

export_multi_fft_plot(
    csv_list=csv_files,
    out_png=out_png,
    labels=labels,
    y_limits=(-140, -40),
    title="FFT overlay (Ch1)",
)

print(f"output file exported to {out_png}")