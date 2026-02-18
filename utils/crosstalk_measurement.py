from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time
import scope
import test_data
from diot.cards import DIOTCard

from matplotlib import pyplot as plt
import numpy as np

# Scope vertical scale presets (mV/div)
BASELINE_MVDIV_CH1 = 2.0
BASELINE_MVDIV_CH2 = 2.0

HEATING_MVDIV_CH1 = 5.0
HEATING_MVDIV_CH2 = 5.0

def format_card_label(serial: str) -> str:
    """
    Format DIOT card serial into 'DTxx (slot N)'.
    Assumes DT00 -> slot 1, DT01 -> slot 2, ...
    Falls back to raw serial if parsing fails.
    """
    if not isinstance(serial, str):
        return str(serial)

    s = serial.strip()

    # Expect something like "DT00", "DT01", ...
    if s.startswith("DT"):
        digits = s[2:]
        if digits.isdigit():
            slot = int(digits) + 1
            return f"{s} (slot {slot})"

    return s

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

def measure_crosstalk_vrms(
    heater_serial: str,
    victim_serial: str,
    power_levels=(1.0, 2.0),  # heating powers only (no 0.0 here)
    n_pairs: int = 10,
    settle_s: float = 1.0,
):
    print("\n==============================")
    print("CROSSTALK (VRMS) MEASUREMENT")
    print("==============================")
    print(f"Heater (noise source) card : {format_card_label(heater_serial)}")
    print(f"Victim card                : {format_card_label(victim_serial)}")
    print(f"Heater power levels        : {power_levels} W")
    print(f"Pairs per power (B+H)      : {n_pairs}")
    print(f"Settle time after switch   : {settle_s} s")
    print("")
    print("Scope connections:")
    print(f"  CH1 -> heater card {format_card_label(heater_serial)} (12 V probe connector)")
    print(f"  CH2 -> victim card {format_card_label(victim_serial)} (12 V probe connector)")
    print("Heater control: PWM16 (channel 16)")
    print("")
    input("Verify connections and press ENTER to start measurement...")
    print("")

    outdir = (
        Path("runs")
        / time.strftime("%Y%m%d_%H%M%S")
        / f"heater_{heater_serial}__victim_{victim_serial}"
    )
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"Saving to: {outdir}")

    card = None
    aux = None
    temp_ch = None
    xt_series = []

    try:
        # Initialize DIOT once (crate ON)
        input("\nSwitch ON the PSU crate, then press Enter to initialize DIOT and start...")
        card = DIOTCard(serial=heater_serial)
        aux = card.get_channel(16)
        temp_ch = card.get_channel(10)
        print("PWM frequency =", aux.frequency)

        # Choose V/div preset (single preset for both baseline+heating)
        # Prepare two V/div presets: baseline and heating
        vdiv_b_ch1 = BASELINE_MVDIV_CH1 / 1000.0
        vdiv_b_ch2 = BASELINE_MVDIV_CH2 / 1000.0
        vdiv_h_ch1 = HEATING_MVDIV_CH1 / 1000.0
        vdiv_h_ch2 = HEATING_MVDIV_CH2 / 1000.0

        print("\nScope vertical scale presets:")
        print(f"  BASELINE: CH1={BASELINE_MVDIV_CH1} mV/div, CH2={BASELINE_MVDIV_CH2} mV/div")
        print(f"  HEATING : CH1={HEATING_MVDIV_CH1} mV/div, CH2={HEATING_MVDIV_CH2} mV/div")

        for p in power_levels:
            print(f"\n=== measurement for P={p} W ===")
            print("Temp:", temp_ch.temperature_sensor.temperature)

            tag_h = f"p_{p}".replace(".", "p")         # heating
            tag_b = f"p_0p0__for_{tag_h}"   

            # Interleaved BH pairs
            for k in range(n_pairs):
                # --- B (heater OFF) ---
                aux.load_power = 0.0
                print(f"\n===  baseline measurement, load_power={aux.load_power:.3f} W set ===")
                time.sleep(settle_s)

                run_tag_b = f"{tag_b}_run{k:02d}"
                scope.test_scope(
                    scope.ip,
                    outdir=outdir,
                    base_name=run_tag_b,
                    vertical_scale_ch1=vdiv_b_ch1,
                    vertical_scale_ch2=vdiv_b_ch2,
                )
                test_data.process_single_run_vrms_only(outdir, run_tag_b)

                # --- H (heater ON) ---
                aux.load_power = float(p)
                print(f"\n===  heating measurement, load_power={aux.load_power:.3f} W set ===")
                time.sleep(settle_s)

                run_tag_h = f"{tag_h}_run{k:02d}"
                scope.test_scope(
                    scope.ip,
                    outdir=outdir,
                    base_name=run_tag_h,
                    vertical_scale_ch1=vdiv_h_ch1,
                    vertical_scale_ch2=vdiv_h_ch2,
                )
                test_data.process_single_run_vrms_only(outdir, run_tag_h)

            # Always finish with heating OFF
            aux.load_power = 0.0
            print("\n=== heating OFF after this power level ===")

            # VRMS crosstalk: heating vs its local baseline
            test_data.compute_vrms_crosstalk(
                outdir,
                tag_on=tag_h,
                tag_base=tag_b,
                source_label="Ch1",
                victim_label="Ch2",
            )
            df_xt = test_data.compute_vrms_crosstalk_table(
                outdir, tag_on=tag_h, tag_base=tag_b,
                source_label="Ch1", victim_label="Ch2"
            )
            xt_db = df_xt["xt_db"].median()
            print(f"[XT] {tag_h} vs {tag_b}: {xt_db:.2f} dB")

            df_xt = df_xt.copy()
            df_xt["run_idx"] = df_xt["run"].map(extract_run_idx)
            df_xt["power_w"] = float(p)
            xt_series.append(df_xt)
            
         # --- Plot: crosstalk vs run index for each heating power ---
        if xt_series:
            fig, ax = plt.subplots(figsize=(10, 6))

            median_lines = []  # text lines to show on the right side

            for dfp in xt_series:
                p = dfp["power_w"].iloc[0]
                dfp = dfp.sort_values("run_idx")

                x = dfp["run_idx"].to_numpy()
                y = dfp["xt_db"].to_numpy()

                # main curve (grab its color)
                (line,) = ax.plot(x, y, marker="o", label=f"P={p:g} W")
                color = line.get_color()

                # median line in the same color
                y_med = float(np.nanmedian(y))
                ax.axhline(
                    y=y_med,
                    linestyle="--",
                    linewidth=1.2,
                    alpha=0.9,
                    color=color,
                )

                # collect side description
                median_lines.append(f"P={p:g} W: median = {y_med:.2f} dB")

            ax.margins(x=0.15)
            ax.set_xlabel("Run number")
            ax.set_xticks(np.arange(0, n_pairs, 1))
            ax.set_ylabel("Crosstalk [dB]")
            ax.set_title(
            f"VRMS crosstalk per run (interleaved B/H)\n"
            f"Source: {format_card_label(heater_serial)}  →  Victim: {format_card_label(victim_serial)}"
            )
            ax.grid(True, alpha=0.3)
            ax.legend(loc="best")

            # --- Put median descriptions on the right side (outside axes) ---
            side_text = "Medians:\n" + "\n".join(median_lines)
            fig.text(
                0.92, 0.5, side_text,
                ha="left", va="center",
                fontsize=10,
            )

            out_png = outdir / "vrms_crosstalk_vs_run_idx.png"

            # leave space on the right for the text block
            fig.tight_layout(rect=[0.0, 0.0, 0.9, 1.0])

            plt.savefig(out_png, bbox_inches="tight")
            plt.close(fig)

            print(f"[XT] per-run plot saved -> {out_png}")



    except KeyboardInterrupt:
        print("\n!!! MEASUREMENT INTERRUPTED BY USER (Ctrl+C) !!!")

    finally:
        if aux is not None:
            aux.load_power = 0.0
        if temp_ch is not None:
            print("Temp:", temp_ch.temperature_sensor.temperature)
        print("\nHeating OFF")

    return outdir

def main():
    measure_crosstalk_vrms(
        heater_serial="DT00",
        victim_serial="DT01",
        power_levels=(0.5, 0.75, 1, 1.25, 1.5, 1.75, 2),       
        n_pairs=10,
        settle_s=1.0,
    )

if __name__ == "__main__":
    main()
