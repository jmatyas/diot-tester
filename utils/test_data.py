import pandas as pd
from matplotlib import pyplot as plt
import numpy as np
from datetime import datetime
from pathlib import Path
from utils.ac_noise_plotting import plot_avg_spectrum_dbV
from utils.ac_noise_plotting import plot_ratio_db
from utils.ac_noise_plotting import plot_fft_amp_dbv

FFT_DB_LIMITS = (-140, -40)
IDENT = "tektronix_mso4104_c020807"
CHANNELS = [1, 2]
SPECTRA_DIR = Path("spectra")
SPECTRA_CSV_DIR = Path("spectra_csv")
TIMESTAMP_FMT = "%Y%m%d_%H%M%S"
WAVEFORM_PNG_TEMPLATE = "waveforms_{timestamp}.png"
FFT_PNG_TEMPLATE = "spectrum_{label}{ptag}_{timestamp}.png"
WAVEFORMS_DIR = Path("waveforms")
FFT_AVG_METHOD = "mean"  # "mean" or "median"


def extract_run_idx(run_name: str) -> int:
    """
    Extract run index from strings like:
      'p_2p0_run03' or 'p_0p0__for_p_2p0_run03'
    Returns -1 if not found.
    """
    if not isinstance(run_name, str):
        return -1
    if "_run" not in run_name:
        return -1
    try:
        return int(run_name.rsplit("_run", 1)[1])
    except ValueError:
        return -1
    
def amplitude_v_to_dbv(amp_v, floor=1e-30):
    """Convert amplitude in volts to dBV: 20*log10(V / 1V)."""
    amp_v = np.maximum(np.asarray(amp_v), floor)
    return 20 * np.log10(amp_v)

def compute_avg_from_fft_csv(files, value_col, method=None):
    if method is None:
        method = FFT_AVG_METHOD

    """
    Analysis-only:
    Read multiple FFT CSVs and return (freq_hz, avg_values).

    Expects each CSV has:
      - freq_hz
      - value_col (e.g. "amp_v")

    Assumes identical freq grid in all files.
    """
    values = []
    freq = None

    for f in files:
        df = pd.read_csv(f)
        if freq is None:
            freq = df["freq_hz"].to_numpy()
        values.append(df[value_col].to_numpy())

    stack = np.vstack(values)

    if method == "mean":
        avg_values = np.mean(stack, axis=0)
    elif method == "median":
        avg_values = np.median(stack, axis=0)
    else:
        raise ValueError("method must be 'mean' or 'median'")

    return freq, avg_values

def save_fft_amp_csv(freq_hz, amp_v, out_csv):
    """
    IO-only: save FFT amplitude spectrum to CSV.
    Expects freq_hz [Hz], amp_v [V].
    """
    out_csv = Path(out_csv)
    pd.DataFrame({
        "freq_hz": np.asarray(freq_hz),
        "amp_v": np.asarray(amp_v),
    }).to_csv(out_csv, index=False)
    print(f"Saved FFT CSV to {out_csv}")

def spectrum_to_amplitude_v(spectrum):
    """
    Convert rFFT (complex) -> single-sided amplitude spectrum in volts [V].
    Includes normalization by N.

    Assumes spectrum comes from np.fft.rfft(x) of a real signal x.
    """
    spectrum = np.asarray(spectrum)
    
    
    amp = np.abs(spectrum)

    if len(amp) > 1:
        amp[1:-1] *= 2.0  # works for both even/odd N with rfft output
    return amp

def compute_fft_amplitude_spectrum(df, label, dt):
    v = df[df["label"] == label]["voltage"].to_numpy()
    
    freq, spectrum = compute_fft(v, dt)      # spectrum is already /N
    amp_v = spectrum_to_amplitude_v(spectrum)  # only single-sided scaling
    return freq, amp_v


def compute_vrms_ac(v):
    """
    AC RMS (DC removed).
    v: numpy array in volts
    returns: VRMS_AC in volts
    """
    v = np.asarray(v)
    v_ac = v - np.mean(v)  # DC out
    return float(np.sqrt(np.mean(v_ac * v_ac)))

def save_vrms_csv(df, out_csv, extra_cols=None):
    """
    Save AC VRMS per label to CSV.
    extra_cols: dict with extra columns to add (e.g. {"run_tag": run_tag})
    """
    if extra_cols is None:
        extra_cols = {}

    rows = []
    for label, g in df.groupby("label"):
        v = g["voltage"].to_numpy()  # volts
        mean_v = float(np.mean(v))   # raw mean (DC)
        row = {
            "label": label,
            "n_samples": len(v),
            "mean_v": mean_v,
            "vrms_ac_v": compute_vrms_ac(v),
        }
        row.update(extra_cols)
        rows.append(row)

    out_df = pd.DataFrame(rows)
    out_df.to_csv(out_csv, index=False)
    print(f"[VRMS] saved -> {out_csv}")

def load_run(run_dir, run_tag, verbose=True):
    run_dir = Path(run_dir)
    files = [
        run_dir / f"{run_tag}_chan1.csv",
        run_dir / f"{run_tag}_chan2.csv",
    ]
    dfs = [pd.read_csv(f) for f in files]
    if verbose:
        print("Loaded files:", ", ".join(f.name for f in files))
    return pd.concat(dfs, ignore_index=True)

def average_fft_runs(run_dir, tag, n_runs=10):
    """
    Glue-only:
    - collects per-run FFT CSVs
    - analysis: averages them in linear amplitude (amp_v)
    - IO: writes avg CSV
    - plot: writes avg PNG in dBV
    """
    run_dir = Path(run_dir)

    # Infer labels from the waveform labels in run00
    df0 = load_run(run_dir, f"{tag}_run00", verbose=False)
    labels = sorted(df0["label"].unique())

    for label in labels:
        files = [run_dir / f"fft_{tag}_run{run_idx:02d}_{label}.csv" for run_idx in range(n_runs)]

        # --- analysis-only ---
        freq, avg_amp_v = compute_avg_from_fft_csv(files, value_col="amp_v",method=FFT_AVG_METHOD)
        avg_dbv = amplitude_v_to_dbv(avg_amp_v)

        # --- IO-only ---
        out_avg = run_dir / f"fft_{tag}_avg_{label}.csv"
        pd.DataFrame({
            "freq_hz": freq,
            "avg_amp_v": avg_amp_v,
            "avg_dbv": avg_dbv,
        }).to_csv(out_avg, index=False)
        print(f"Saved average FFT CSV to {out_avg}")

        # --- plot-only ---
        out_png = run_dir / f"fft_{tag}_avg_{label}.png"
        title = f"Average FFT amplitude ({tag}) - {label}  (N={n_runs})"
        plot_avg_spectrum_dbV(freq, avg_dbv, out_png, title, ylabel="Amplitude [dBV (peak)]")


def load_data(ident, channels, verbose=True):
    files = [f"{ident}_chan{ch}.csv" for ch in channels]
    dfs = [pd.read_csv(fname) for fname in files]
    if verbose:
        print("Loaded files:", ", ".join(files))
    df = pd.concat(dfs, ignore_index=True)
    return df


def summarize_waveforms(df):
    print("Waveform statistics:")
    for label, g in df.groupby("label"):
        v = g["voltage"].to_numpy() * 1e3  # V -> mV
        mean = v.mean()
        rms = np.sqrt(np.mean(v**2))
        vmin = v.min()
        vmax = v.max()
        print(
            f"{label}: "
            f"N={len(v)}, "
            f"mean={mean:7.3f} mV, "
            f"rms={rms:7.3f} mV, "
            f"min={vmin:7.3f} mV, "
            f"max={vmax:7.3f} mV"
        )

def get_sampling_dt(df):
    t = df["time"].to_numpy()
    dt = t[1] - t[0]
    print(f"Sampling interval dt = {dt * 1e9:.3f} ns")
    return dt

def compute_fft(v, dt):
    """
    Compute windowed rFFT of signal v sampled with interval dt.
    Returns: freq (Hz), spectrum (complex)
    """
    v = v - v.mean()
    N = len(v)

    window = np.hanning(N)
    coherent_gain = window.mean()  # coherent gain (amplitude correction for Hann window)
    v_win = v * window / coherent_gain

    #v_win=v #uncomment to have trace wihout the window

    spectrum = np.fft.rfft(v_win) / N
    freq = np.fft.rfftfreq(N, d=dt)
    return freq, spectrum
   
def plot_fft(df, label, dt, out_file, out_csv=None):
    # Analysis-only
    freq, amp_v = compute_fft_amplitude_spectrum(df, label, dt)

    # IO-only (optional)
    if out_csv is not None:
        save_fft_amp_csv(freq, amp_v, out_csv)

    # Plot-only
    plot_fft_amp_dbv(freq, amp_v, out_file, y_limits=FFT_DB_LIMITS, title=None)

def save_ratio_csv(freq_hz, ratio_db, out_csv):
    """
    IO-only: save ratio spectrum to CSV.
    """
    out_csv = Path(out_csv)
    pd.DataFrame({
        "freq_hz": np.asarray(freq_hz),
        "ratio_db": np.asarray(ratio_db),
    }).to_csv(out_csv, index=False)
    print(f"Saved ratio CSV to {out_csv}")

def process_baseline(run_dir, tag="p_0p0", n_runs=10):
    """
    Full baseline procedure:
    1) For run00..run(N-1): load waveform CSVs, compute FFT, save per-run FFT CSV/PNG
    2) Average FFT amplitude over runs, save avg CSV + avg PNG
    """
    run_dir = Path(run_dir)

    labels = None

    # 1) Per-run FFT export
    for run_idx in range(n_runs):
        run_tag = f"{tag}_run{run_idx:02d}"

        df = load_run(run_dir, run_tag)
        dt = get_sampling_dt(df)

        save_vrms_csv(
           df,
            run_dir / f"vrms_{run_tag}.csv",
            extra_cols={"tag": tag, "run_idx": run_idx, "run_tag": run_tag},
        )


        if labels is None:
            labels = sorted(df["label"].unique())

        for label in labels:
            out_png = run_dir / f"fft_{run_tag}_{label}.png"
            out_csv = run_dir / f"fft_{run_tag}_{label}.csv"
            plot_fft(df, label, dt, out_png, out_csv=out_csv)

    #2) Average FFT amplitude over runs, save avg CSV + avg PNG (in dBV)
    for label in labels:
        files = [run_dir / f"fft_{tag}_run{run_idx:02d}_{label}.csv" for run_idx in range(n_runs)]
        freq, avg_amp_v = compute_avg_from_fft_csv(files, value_col="amp_v",method=FFT_AVG_METHOD)
        avg_db = amplitude_v_to_dbv(avg_amp_v)

        out_avg = run_dir / f"fft_{tag}_avg_{label}.csv"
        pd.DataFrame({
            "freq_hz": freq,
            "avg_amp_v": avg_amp_v,
            "avg_db": avg_db
        }).to_csv(out_avg, index=False)

        print(f"Saved baseline average to {out_avg}")


        out_png = run_dir / f"fft_{tag}_avg_{label}.png"
        title = f"Baseline average ({tag}) - {label}"
        plot_avg_spectrum_dbV(freq, avg_db, out_png, title, y_limits=FFT_DB_LIMITS, ylabel="FFT magnitude [dB]")
        print(f"Saved baseline average plot to {out_png}")
   
def compute_ratio_avg_to_avg_from_csv(num_avg_csv, den_avg_csv):
    df_num = pd.read_csv(num_avg_csv)
    freq = df_num["freq_hz"].to_numpy()
    a_num = df_num["avg_amp_v"].to_numpy()

    df_den = pd.read_csv(den_avg_csv)
    a_den = df_den["avg_amp_v"].to_numpy()

    ratio_db = 20 * np.log10(
        np.maximum(a_num, 1e-30) / np.maximum(a_den, 1e-30)
    )
    return freq, ratio_db

def compute_ratio_to_baseline_from_csv(run_fft_csv, baseline_avg_csv):
    df_run = pd.read_csv(run_fft_csv)
    freq = df_run["freq_hz"].to_numpy()
    a_run = df_run["amp_v"].to_numpy()

    df_base = pd.read_csv(baseline_avg_csv)
    a_base = df_base["avg_amp_v"].to_numpy()

    ratio_db = 20 * np.log10(
        np.maximum(a_run, 1e-30) / np.maximum(a_base, 1e-30)
    )
    return freq, ratio_db

def plot_ratio_to_baseline(run_dir, run_tag, baseline_tag="p_0p0"):
    """
    Glue-only:
    - finds per-run FFT CSVs for run_tag
    - analysis: computes ratio_db vs baseline avg
    - IO: saves ratio CSV
    - plot: saves ratio PNG
    """
    run_dir = Path(run_dir)

    run_fft_files = sorted(run_dir.glob(f"fft_{run_tag}_*.csv"))
    if not run_fft_files:
        raise FileNotFoundError(f"No run FFT CSV files found for fft_{run_tag}_*.csv in {run_dir}")

    for run_fft in run_fft_files:
        label = run_fft.stem.replace(f"fft_{run_tag}_", "")  # e.g. "Ch1"

        baseline_avg = run_dir / f"fft_{baseline_tag}_avg_{label}.csv"

        # --- analysis-only ---
        freq, ratio_db = compute_ratio_to_baseline_from_csv(run_fft, baseline_avg)

        # --- IO-only ---
        out_csv = run_dir / f"fft_ratio_{run_tag}_vs_{baseline_tag}_{label}.csv"
        save_ratio_csv(freq, ratio_db, out_csv)

        # --- plot-only ---
        title = f"{run_tag} / baseline {baseline_tag} ({label})"

        out_png = run_dir / f"fft_ratio_{run_tag}_vs_{baseline_tag}_{label}.png"
        plot_ratio_db(freq, ratio_db, out_png, title=title)

def plot_ratio_avg_to_avg(run_dir, tag_num, tag_den="p_0p0"):
    """
    Glue-only:
    - finds avg spectra for tag_num
    - analysis: computes FFT amplitude ratio in dB between two averaged spectra
    - IO: saves ratio CSV
    - plot: saves ratio PNG
    """
    run_dir = Path(run_dir)

    num_files = sorted(run_dir.glob(f"fft_{tag_num}_avg_*.csv"))
    if not num_files:
        raise FileNotFoundError(f"No averaged files found: fft_{tag_num}_avg_*.csv in {run_dir}")

    for fnum in num_files:
        label = fnum.stem.replace(f"fft_{tag_num}_avg_", "")

        fden = run_dir / f"fft_{tag_den}_avg_{label}.csv"
        if not fden.exists():
            continue

        # --- analysis-only ---
        freq, ratio_db = compute_ratio_avg_to_avg_from_csv(fnum, fden)

        # --- IO-only ---
        out_csv = run_dir / f"fft_ratio_avg_{tag_num}_vs_{tag_den}_{label}.csv"
        save_ratio_csv(freq, ratio_db, out_csv)

        # --- plot-only ---
        roles = "CH1: noise source | CH2: victim"
        title = f"{roles} | AVG active / AVG baseline ({label})"

        out_png = run_dir / f"fft_ratio_avg_{tag_num}_vs_{tag_den}_{label}.png"
        plot_ratio_db(freq, ratio_db, out_png, title=title)

def process_single_run(run_dir, run_tag):
    """
    Load waveform CSVs for one run (run_tag_chan1.csv, run_tag_chan2.csv),
    compute FFT for each label, save per-run FFT CSV/PNG into run_dir.
    """
    run_dir = Path(run_dir)
    df = load_run(run_dir, run_tag)
    dt = get_sampling_dt(df)
    labels = sorted(df["label"].unique())

    # NEW: AC VRMS export
    #save_vrms_csv(df, run_dir / f"vrms_{run_tag}.csv", extra_cols={"run_tag": run_tag})

    for label in labels:
        out_png = run_dir / f"fft_{run_tag}_{label}.png"
        out_csv = run_dir / f"fft_{run_tag}_{label}.csv"
        plot_fft(df, label, dt, out_png, out_csv=out_csv)

def compute_vrms_crosstalk_table(
    run_dir,
    tag_on,
    tag_base="p_0p0",
    source_label="Ch1",
    victim_label="Ch2",
):

    run_dir = Path(run_dir)

    # --- baseline: median VRMS per channel ---
    base_files = run_dir.glob(f"vrms_{tag_base}_run*.csv")
    df_base = pd.concat(pd.read_csv(f) for f in base_files)
    base = df_base.groupby("label")["vrms_ac_v"].median()

    # --- active runs ---
    rows = []
    for f in run_dir.glob(f"vrms_{tag_on}_run*.csv"):
        df = pd.read_csv(f)
        v = df.set_index("label")["vrms_ac_v"]

        dv_src = np.sqrt(max(v[source_label] ** 2 - base[source_label] ** 2, 0.0))
        dv_vic = np.sqrt(max(v[victim_label] ** 2 - base[victim_label] ** 2, 0.0))

        xt = dv_vic / dv_src if dv_src > 0 else np.nan
        xt_db = 20 * np.log10(xt) if xt > 0 else np.nan

        rows.append(
            {
                "run": f.stem.replace("vrms_", ""),
                "dv_source_v": dv_src,
                "dv_victim_v": dv_vic,
                "xt": xt,
                "xt_db": xt_db,
            }
        )

    df_out = pd.DataFrame(rows)
    df_out["run_idx"] = df_out["run"].map(extract_run_idx)  # jeśli nie masz tu helpera, patrz niżej
    df_out = df_out.sort_values("run_idx").reset_index(drop=True)
    return df_out

def compute_vrms_crosstalk(
    run_dir,
    tag_on,
    tag_base="p_0p0",
    source_label="Ch1",
    victim_label="Ch2",
):
    run_dir = Path(run_dir)

    df_out = compute_vrms_crosstalk_table(
        run_dir,
        tag_on=tag_on,
        tag_base=tag_base,
        source_label=source_label,
        victim_label=victim_label,
    )

    out_csv = run_dir / f"vrms_crosstalk_{tag_on}_vs_{tag_base}.csv"
    df_out.to_csv(out_csv, index=False)
    print(f"[XT] VRMS crosstalk saved -> {out_csv}")


def annotate_31k8_harmonics(ax, base_hz: float = 31_800, harmonics: int = 5):
    """
    Draw vertical lines for 31.8 kHz and its harmonics.
    """

    for k in range(1, harmonics + 1):
        freq = k * base_hz

        if k == 1:
            label = f"ARTIQ {base_hz/1e3:.1f} kHz"
        else:
            label = f"{k}×"

        ax.axvline(freq, linestyle=":", linewidth=1.0)
        ax.text(
            freq, 1.02, label,
            transform=ax.get_xaxis_transform(),
            rotation=90,
            va="bottom",
            ha="center",
            fontsize=8,
            clip_on=False,
        )


def plot_ratio_avg_comparison(
    run_dir,
    baseline_tag="p_0p0",
    labels=("Ch1", "Ch2"),
    fastino_a_serial=None,
    fastino_b_serial=None,
    victim_serial=None,
    out_png=None,
    y_limits=(-40, 40),
):
    """
    Plot comparison of ratio spectra (AVG tag / AVG baseline) for all measured tags.

    Expects CSVs created by plot_ratio_avg_to_avg():
        fft_ratio_avg_<tag_num>_vs_<baseline_tag>_<label>.csv
    Each CSV has columns: freq_hz, ratio_db

    Ch1: ground difference between two Fastino cards
    Ch2: J2 measurement on the victim DIOT card
    """
    run_dir = Path(run_dir)

    if fastino_a_serial is None or fastino_b_serial is None or victim_serial is None:
        raise ValueError(
            "Please provide fastino_a_serial, fastino_b_serial, and victim_serial"
        )

    # Find all ratio-avg CSV files for the first label, infer tag_num list from filenames
    pattern = f"fft_ratio_avg_*_vs_{baseline_tag}_{labels[0]}.csv"
    files = sorted(run_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files matching {pattern} in {run_dir}")

    # Extract tag_num from filename:
    # fft_ratio_avg_{tag_num}_vs_{baseline}_{label}.csv
    tag_nums = []
    for f in files:
        stem = f.stem  # without .csv
        prefix = "fft_ratio_avg_"
        mid = f"_vs_{baseline_tag}_{labels[0]}"
        if not (stem.startswith(prefix) and stem.endswith(mid)):
            continue
        tag_num = stem[len(prefix) : -len(mid)]
        tag_nums.append(tag_num)

    # Unique + lexical sort of tags
    tag_nums = sorted(set(tag_nums))

    # Default output filename
    if out_png is None:
        out_png = run_dir / f"fft_ratio_avg_comparison_vs_{baseline_tag}.png"
    else:
        out_png = Path(out_png)

    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(10, 8), sharex=True)

    panel_labels = (
        f"ΔGND: {fastino_a_serial} vs {fastino_b_serial}",
        f"J2 on DIOT tester victim: {victim_serial}",
    )

    for ax, label, panel in zip(axes, labels, panel_labels):
        for tag_num in reversed(tag_nums):
            fcsv = run_dir / f"fft_ratio_avg_{tag_num}_vs_{baseline_tag}_{label}.csv"
            if not fcsv.exists():
                # If a label is missing for some reason, just skip it
                continue

            df = pd.read_csv(fcsv)
            freq = df["freq_hz"].to_numpy()
            ratio_db = df["ratio_db"].to_numpy()

                                   

            ax.semilogx(freq, ratio_db)

        ax.set_ylabel(f"{panel}\nFFT ratio [dB]")
        ax.set_ylim(y_limits)
        ax.grid(True, which="both", alpha=0.2)
        

        annotate_31k8_harmonics(ax, base_hz=31800, harmonics=5)

    axes[-1].set_xlabel("Frequency [Hz]")

    fig.suptitle(
        rf"Fastino pair: {fastino_a_serial}, {fastino_b_serial} |  DIOT tester victim: {victim_serial}|FFT ratio [dB] = $dBV_{{ARTIQ\ ON}} - dBV_{{ARTIQ\ OFF}}$"
       
    )

    fig.subplots_adjust(hspace=0.43, top=0.85)

    plt.savefig(out_png)
    plt.close(fig)
    print(f"Saved ratio comparison plot to {out_png}")

def process_single_run_vrms_only(run_dir, run_tag):
    run_dir = Path(run_dir)
    df = load_run(run_dir, run_tag)
    save_vrms_csv(df, run_dir / f"vrms_{run_tag}.csv", extra_cols={"run_tag": run_tag})    

