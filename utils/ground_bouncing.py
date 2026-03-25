from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import time
import scope
import test_data
import subprocess

# Scope vertical scale presets for baseline and active states (mV/div)
ARTIQ_OFF_MVDIV_CH1 = 10.0
ARTIQ_OFF_MVDIV_CH2 = 2.0

ARTIQ_ON_MVDIV_CH1 = 500.0
ARTIQ_ON_MVDIV_CH2 = 2.0


# Legacy condition tags used by downstream analysis code.
# Keep these values unchanged, because they define output filenames.
ARTIQ_OFF_TAG = "p_0p0"
ARTIQ_ON_TAG = "p_1p0"

def print_measurement_intro(
    fastino_a_serial: str,
    fastino_b_serial: str,
    victim_serial: str,
    baseline_n_runs: int,
    active_n_runs: int,
):
    """
    Print the experiment summary and confirm manual scope connections before acquisition.
    """
    print("\n==============================")
    print("GROUND BOUNCE MEASUREMENT")
    print("==============================")
    print(f"Fastino A card            : {fastino_a_serial}")
    print(f"Fastino B card            : {fastino_b_serial}")
    print(f"Victim card               : {victim_serial}")
    print(f"Baseline runs             : {baseline_n_runs}")
    print(f"Active runs               : {active_n_runs}")
    print("FFT averaging method      :", getattr(test_data, "FFT_AVG_METHOD", "unknown"))
    print("")
    print("Scope connections:")
    print(f"  CH1 -> differential GND noise: {fastino_a_serial} vs {fastino_b_serial}")
    print(f"  CH2 -> ground-to-chassis noise on victim card {victim_serial} via J2")
    print("")
    input("Verify connections and press ENTER to start measurement...")
    print("")

def create_output_directory(
    fastino_a_serial: str,
    fastino_b_serial: str,
    victim_serial: str,
) -> Path:
    """
    Create the output directory for this measurement run.
    """
    outdir = (
        Path("runs")
        / time.strftime("%Y%m%d_%H%M%S")
        / f"fastino_{fastino_a_serial}_{fastino_b_serial}__victim_{victim_serial}"
    )
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"Saving to: {outdir}")
    return outdir    

def confirm_artiq_off_ready():
    """
    Ask the operator to confirm that the ARTIQ OFF baseline condition is ready.
    """
    input(
        "\nARTIQ OFF measurement (baseline): make sure the ARTIQ experiment is NOT running, then press Enter..."
    )

def prepare_artiq_on_state():
    """
    Configure the hardware for the active ARTIQ ON measurement state.
    """
    subprocess.run(
        [
            "nix",
            "develop",
            "-c",
            "python",
            "/home/knorowski/diot-tester/kasli_diot_utils.py",
        ],
        check=True,
    )

    print("\nFastino outputs configured for ARTIQ ON measurement.")

def get_scope_scale_preset(is_baseline: bool) -> tuple[float, float]:
    """
    Return CH1 and CH2 vertical scale presets in mV/div for the current state.
    """
    if is_baseline:
        return ARTIQ_OFF_MVDIV_CH1, ARTIQ_OFF_MVDIV_CH2

    return ARTIQ_ON_MVDIV_CH1, ARTIQ_ON_MVDIV_CH2

def convert_mvdiv_to_vdiv(mvdiv_ch1: float, mvdiv_ch2: float) -> tuple[float, float]:
    """
    Convert scope vertical scale values from mV/div to V/div.
    """
    return mvdiv_ch1 / 1000.0, mvdiv_ch2 / 1000.0    


def acquire_state_waveforms(
    outdir: Path,
    tag: str,
    runs_this_state: int,
    vdiv_ch1: float,
    vdiv_ch2: float,
):
    """
    Acquire oscilloscope waveforms for all runs in one measurement state.
    """
    for run_idx in range(runs_this_state):
        run_tag = f"{tag}_run{run_idx:02d}"
        scope.test_scope(
            scope.ip,
            outdir=outdir,
            base_name=run_tag,
            vertical_scale_ch1=vdiv_ch1,
            vertical_scale_ch2=vdiv_ch2,
        )
        time.sleep(3.0)

def process_active_state(
    outdir: Path,
    tag: str,
    active_n_runs: int,
):
    """
    Process all active-state runs, compute the average spectrum,
    and compare it to the baseline average.
    """
    for run_idx in range(active_n_runs):
        run_tag = f"{tag}_run{run_idx:02d}"
        test_data.process_single_run(outdir, run_tag=run_tag)

    test_data.average_fft_runs(outdir, tag=tag, n_runs=active_n_runs)
    test_data.plot_ratio_avg_to_avg(outdir, tag_num=tag, tag_den=ARTIQ_OFF_TAG)
    
def print_state_note(is_baseline: bool):
    """
    Print an operator note for the current measurement state.
    """
    if is_baseline:
        print("\nNOTE: baseline mode (ARTIQ OFF). Do NOT run the ARTIQ experiment.")
    else:
        print("\nNOTE: ARTIQ ON mode. Make sure the ARTIQ experiment is running.")            

def plot_final_ratio_comparison(
    outdir: Path,
    fastino_a_serial: str,
    fastino_b_serial: str,
    victim_serial: str,
):
    """
    Plot the final comparison of average spectra ratios for the measured setup.
    """
    test_data.plot_ratio_avg_comparison(
        outdir,
        baseline_tag=ARTIQ_OFF_TAG,
        fastino_a_serial=fastino_a_serial,
        fastino_b_serial=fastino_b_serial,
        victim_serial=victim_serial,
        y_limits=(-50, 110),
    )        

def measure_ground_bounce_and_chassis_noise(
    fastino_a_serial: str,
    fastino_b_serial: str,
    victim_serial: str,
    baseline_n_runs: int = 10, #baseline - ARTIQ OFF
    active_n_runs: int = 10, #active - ARTIQ ON
):
    
    """
    Run the full ground-bounce measurement for one hardware setup.

    The experiment compares two states:
    - ARTIQ OFF: baseline acquisition
    - ARTIQ ON: active acquisition

    CH1 measures differential GND noise between fastino_a_serial and fastino_b_serial.
    CH2 measures ground-to-chassis noise on the victim card via J2.
    """
    print_measurement_intro(
        fastino_a_serial=fastino_a_serial,
        fastino_b_serial=fastino_b_serial,
        victim_serial=victim_serial,
        baseline_n_runs=baseline_n_runs,
        active_n_runs=active_n_runs,
    )

    outdir = create_output_directory(
        fastino_a_serial=fastino_a_serial,
        fastino_b_serial=fastino_b_serial,
        victim_serial=victim_serial,
    )

    try:

        for tag in (ARTIQ_OFF_TAG, ARTIQ_ON_TAG):
            is_baseline = (tag == ARTIQ_OFF_TAG)
            state_name = "ARTIQ OFF" if is_baseline else "ARTIQ ON"
            if is_baseline:
                confirm_artiq_off_ready()
            else:
                prepare_artiq_on_state()

            time.sleep(10.0)

            runs_this_state = baseline_n_runs if is_baseline else active_n_runs
            
            print_state_note(is_baseline)

            mvdiv_ch1, mvdiv_ch2 = get_scope_scale_preset(is_baseline)

            print(f"\nScope vertical scale preset for {state_name} ({tag}): CH1={mvdiv_ch1} mV/div, CH2={mvdiv_ch2} mV/div")

            vdiv_ch1, vdiv_ch2 = convert_mvdiv_to_vdiv(mvdiv_ch1, mvdiv_ch2)
            print(f"Using: CH1={mvdiv_ch1} mV/div, CH2={mvdiv_ch2} mV/div\n")

            acquire_state_waveforms(
                outdir=outdir,
                tag=tag,
                runs_this_state=runs_this_state,
                vdiv_ch1=vdiv_ch1,
                vdiv_ch2=vdiv_ch2,
            )

            if is_baseline:
                # Baseline processing computes per-run FFT/VRMS and the baseline average spectrum.
                test_data.process_baseline(outdir, tag=tag, n_runs=baseline_n_runs)
            else:
                process_active_state(
                    outdir=outdir,
                    tag=tag,
                    active_n_runs=active_n_runs,
                )
    
        plot_final_ratio_comparison(
            outdir=outdir,
            fastino_a_serial=fastino_a_serial,
            fastino_b_serial=fastino_b_serial,
            victim_serial=victim_serial,
        )

    except KeyboardInterrupt:
        print("\n!!! MEASUREMENT INTERRUPTED BY USER (Ctrl+C) !!!")

    return outdir

def main():
    measure_ground_bounce_and_chassis_noise(
        fastino_a_serial="DT01",
        fastino_b_serial="DT02",
        victim_serial="DT04",
        baseline_n_runs=20,
        active_n_runs=20,
    )

if __name__ == "__main__":
        main()