from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import time
import scope
import test_data
from diot.cards import DIOTCard

# Scope vertical scale presets (mV/div)
BASELINE_MVDIV_CH1 = 5.0
BASELINE_MVDIV_CH2 = 5.0

HEATING_MVDIV_CH1 = 5.0
HEATING_MVDIV_CH2 = 5.0

def measure_power_rail_noise(
    heater_serial: str,
    victim_serial: str,
    power_levels=(0.0, 2.0), #default values
    baseline_n_runs: int = 3,
    heating_n_runs: int = 3,
):
    
    """
    Full measurement sequence for one heater card:
    - baseline (p=0): acquire waveforms, compute FFT+VRMS per run, compute baseline avg FFT
    - heating (p>0): acquire waveforms, compute FFT+VRMS per run, compute avg FFT, ratio, VRMS crosstalk

    heater_serial: e.g. "DT00", "DT03"
    """
    print("\n==============================")
    print("POWER RAIL NOISE MEASUREMENT")
    print("==============================")
    print(f"Heater (noise source) card : {heater_serial}")
    print(f"Victim card                : {victim_serial}")
    print(f"Heater power levels       : {power_levels} W")
    print(f"Baseline runs             : {baseline_n_runs}")
    print(f"Heating runs              : {heating_n_runs}")
    print("FFT averaging method      :", getattr(test_data, "FFT_AVG_METHOD", "unknown"))
    print("")
    print("Scope connections:")
    print(f"  CH1 -> heater card {heater_serial} (12 V probe connector)")
    print(f"  CH2 -> victim card {victim_serial} (12 V probe connector)")
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

    try:
        for p in power_levels:
            is_baseline = (p == 0.0)

            if is_baseline:
                input(
                "\nBASELINE measurement (P=0): press Enter to continue..."
                )
            else:
            #    input(
            # f"\nMeasurement for P={p}: switch ON the PSU crate, then press Enter to continue..."
            #    )

                if card is None:# DIOT is initialized ONLY when crate is ON
                    card = DIOTCard(serial=heater_serial)
                    aux = card.get_channel(16)
                    temp_ch = card.get_channel(10)
                    print("PWM frequency =", aux.frequency)

                aux.load_power = float(p)
                print(f"\n=== load_power = {p} ===")
                print("Temp:", temp_ch.temperature_sensor.temperature)

            tag = f"p_{p}".replace(".", "p")
            time.sleep(1.0)

            runs_this_power = baseline_n_runs if is_baseline else heating_n_runs
            
            if is_baseline:
                print("\nNOTE: baseline mode (P=0). Crate should be OFF (no load power applied).")
                mvdiv_ch1 = BASELINE_MVDIV_CH1
                mvdiv_ch2 = BASELINE_MVDIV_CH2
            else:
                print(f"\nNOTE: heating mode. load_power={p} W is ALREADY applied while you set V/div.")
                mvdiv_ch1 = HEATING_MVDIV_CH1
                mvdiv_ch2 = HEATING_MVDIV_CH2

            print(f"\nScope vertical scale preset for {tag}: CH1={mvdiv_ch1} mV/div, CH2={mvdiv_ch2} mV/div")

            vdiv_ch1 = mvdiv_ch1 / 1000.0
            vdiv_ch2 = mvdiv_ch2 / 1000.0
            print(f"Using: CH1={mvdiv_ch1} mV/div, CH2={mvdiv_ch2} mV/div\n")

            # Acquire waveforms
            for run_idx in range(runs_this_power):
                run_tag = f"{tag}_run{run_idx:02d}"
                scope.test_scope(scope.ip, outdir=outdir, base_name=run_tag, vertical_scale_ch1=vdiv_ch1, vertical_scale_ch2=vdiv_ch2)


            if not is_baseline and aux is not None:
                aux.load_power = 0.0

            if is_baseline:
                # This already computes per-run FFT+VRMS and baseline avg FFT
                test_data.process_baseline(outdir, tag=tag, n_runs=baseline_n_runs)
            else:
                # Per-run FFT+VRMS for heating runs
                for run_idx in range(heating_n_runs):
                    run_tag = f"{tag}_run{run_idx:02d}"
                    test_data.process_single_run(outdir, run_tag=run_tag)

            # Avg FFT for this tag (baseline OR heating)
            test_data.average_fft_runs(outdir, tag=tag, n_runs=runs_this_power)

            if not is_baseline:
                # Ratio: AVG FFT amplitude (heating) / AVG FFT amplitude (baseline)
                test_data.plot_ratio_avg_to_avg(outdir, tag_num=tag, tag_den="p_0p0")

                # VRMS crosstalk (heating vs baseline)
                test_data.compute_vrms_crosstalk(
                    outdir,
                    tag_on=tag,
                    tag_base="p_0p0",
                    source_label="Ch1",
                    victim_label="Ch2",
                )
    
        test_data.plot_ratio_avg_comparison(
            outdir,
            baseline_tag="p_0p0",
            card_labels=(heater_serial, victim_serial),
            y_limits=(-40, 60), # FFT amplitude ratio [dB]
        )
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
    measure_power_rail_noise(
    heater_serial="DT00",
    victim_serial="DT01",
    power_levels=(0.0, 2),
    baseline_n_runs=10,
    heating_n_runs=10,
    )

if __name__ == "__main__":
    
    main()

