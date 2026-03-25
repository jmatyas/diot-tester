from matplotlib import pyplot as plt
from pathlib import Path
import seaborn as sns

import numpy as np

def amplitude_v_to_dbv(amp_v, floor=1e-30):
    """Convert amplitude in volts to dBV: 20*log10(V / 1V)."""
    amp_v = np.maximum(np.asarray(amp_v), floor)
    return 20 * np.log10(amp_v)


FFT_DB_LIMITS = (-180, -40)

def plot_avg_spectrum_dbV(freq, y_db, out_png, title, y_limits=FFT_DB_LIMITS, ylabel=""):
    """
    Plot-only:
    Save a semilog-x plot of averaged spectrum in dB.
    """
    plt.figure()
    plt.semilogx(freq, y_db)
    plt.ylim(y_limits)
    plt.xlabel("Frequency [Hz]")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()
    print(f"Saved average plot to {out_png}")

def plot_ratio_db(freq_hz, ratio_db, out_png, title=None, y_limits=None):
    """
    Plot-only: plot ratio in dB and save to PNG.
    """
    out_png = Path(out_png)

    plt.figure()
    plt.semilogx(freq_hz, ratio_db)
    plt.xlabel("Frequency [Hz]")
    plt.ylabel("Ratio [dB]")
    if y_limits is not None:
        plt.ylim(y_limits)
    if title:
        plt.title(title)
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()
    print(f"Saved ratio plot to {out_png}")
    
def plot_fft_amp_dbv(freq_hz, amp_v, out_png, y_limits=FFT_DB_LIMITS, title=None):
    """
    Plot-only: plot amplitude spectrum in dBV and save to PNG.
    """
    out_png = Path(out_png)

    mag_dbv = amplitude_v_to_dbv(amp_v)

    plt.figure()
    plt.semilogx(freq_hz, mag_dbv)
    plt.ylim(y_limits)
    plt.xlabel("Frequency [Hz]")
    plt.ylabel("Amplitude [dBV] (peak)")
    if title:
        plt.title(title)
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()
    print(f"Saved FFT plot to {out_png}")

def plot_waveforms(df, out_file):
    plt.figure()
    sns.lineplot(data=df, x="time", y="voltage", hue="label")
    plt.savefig(out_file)
    plt.close()
    print(f"Saved waveform plot to {out_file}")