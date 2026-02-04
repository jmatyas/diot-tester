from pathlib import Path
import pandas as pd
import numpy as np
from matplotlib import pyplot as plt


def export_fft_ratio_csv(
    num_csv: str | Path,
    den_csv: str | Path,
    out_csv: str | Path,
    *,
    freq_col: str = "freq_hz",
    dbv_col: str = "avg_dbv",
    atol_hz: float = 0.0,
) -> Path:
    """
    Load two FFT CSVs and export ratio in dB (numerator - denominator).

    Input CSV columns (expected):
        freq_hz, avg_amp_v, avg_dbv

    Output CSV columns:
        freq_hz, num_dbv, den_dbv, ratio_db
    """

    num_csv = Path(num_csv)
    den_csv = Path(den_csv)
    out_csv = Path(out_csv)

    out_csv.parent.mkdir(parents=True, exist_ok=True)

    df_num = pd.read_csv(num_csv)
    df_den = pd.read_csv(den_csv)

    required = {freq_col, dbv_col}
    if not required.issubset(df_num.columns):
        raise ValueError(f"{num_csv} missing columns: {required - set(df_num.columns)}")
    if not required.issubset(df_den.columns):
        raise ValueError(f"{den_csv} missing columns: {required - set(df_den.columns)}")

    f_num = df_num[freq_col].to_numpy()
    f_den = df_den[freq_col].to_numpy()

    if len(f_num) != len(f_den):
        raise ValueError("Different number of frequency bins.")

    if atol_hz == 0.0:
        if not np.array_equal(f_num, f_den):
            raise ValueError("Frequency grids are not identical.")
    else:
        if not np.allclose(f_num, f_den, atol=atol_hz, rtol=0.0):
            raise ValueError("Frequency grids differ beyond tolerance.")

    out = pd.DataFrame(
        {
            "freq_hz": f_num,
            "num_dbv": df_num[dbv_col].to_numpy(),
            "den_dbv": df_den[dbv_col].to_numpy(),
        }
    )
    out["ratio_db"] = out["num_dbv"] - out["den_dbv"]

    out.to_csv(out_csv, index=False)
    return out_csv


def export_fft_ratio_plot(
    ratio_csv: str | Path,
    out_png: str | Path,
    *,
    title: str | None = None,
    y_limits: tuple[float, float] = (-20, 60),
    drop_dc_for_plot: bool = True,
) -> Path:
    """
    Plot FFT ratio spectrum from a ratio CSV and export to PNG.
    """

    ratio_csv = Path(ratio_csv)
    out_png = Path(out_png)

    out_png.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(ratio_csv)

    if drop_dc_for_plot:
        df = df[df["freq_hz"] > 0.0]

    freq = df["freq_hz"].to_numpy()
    ratio_db = df["ratio_db"].to_numpy()

    plt.figure()
    plt.semilogx(freq, ratio_db)
    plt.ylim(y_limits)
    plt.xlabel("Frequency [Hz]")
    plt.ylabel("Amplitude [dBV] (peak)")
    title = (
    r"FFT ratio [dB] (ON/OFF) = $dBV_{FANTRAY~\mathrm{ON}} - dBV_{FANTRAY~\mathrm{OFF}}$"
    )
    if title:
        plt.title(title)
    plt.tight_layout()   
    plt.savefig(out_png)
    plt.close()

    return out_png

num_csv = Path(
    "/home/knorowski/diot-tester/12_V_AC_NOISE PERFORMANCE/20260203_120112/heater_DT00__victim_DT01_PSU_ON_FANTRAY_ON/fft_p_0p0_avg_Ch1.csv"
)
den_csv = Path(
    "/home/knorowski/diot-tester/12_V_AC_NOISE PERFORMANCE/20260203_114335/heater_DT00__victim_DT01_PSU_ON_FANTRAY_OFF/fft_p_0p0_avg_Ch1.csv"
)

out_dir = Path("/home/knorowski/diot-tester")
out_base = out_dir / "fft_ratio_p_0p0_FANTRAY_ON_vs_OFF_Ch1"

out_csv = out_base.with_suffix(".csv")
out_png = out_base.with_suffix(".png")

export_fft_ratio_csv(
    num_csv=num_csv,
    den_csv=den_csv,
    out_csv=out_csv,
)

export_fft_ratio_plot(
    ratio_csv=out_csv,
    out_png=out_png,
)