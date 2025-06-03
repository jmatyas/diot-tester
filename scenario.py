import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from analysis.transients import create_temperature_plots
from analysis.heatmaps import generate_heatmap_grid
from diot import DIOTCrateManager, MonitoringSession
from diot_monitor import list_available_cards, setup_logging
from rs_power_supply import MAX_I, MAX_V, MIN_I, MIN_V, RSPowerSupply

PSU_IP = "10.42.0.245"
FAN_CHANNEL = 1
OT_SHUTDOWN = 85.0  # degrees Celsius
HYSTERESIS = 80.0  # degrees Celsius
MAX_STEP_DURATION_MINUTES = 20.0
DEFAULT_POWER_PER_CARD = 20.0  # W

RESULTS_DIR = "results"


@dataclass
class StepParams:
    """Parameters for a scenario step.

    Attributes:
        power (float): Power to set for the load per card (in Watts)
        fan_voltage (float): Voltage to set for the fan (in Volts)
        save_dir (str): Directory to save the monitoring data
        step_no (int): Step number in the scenario
        serials_to_set_power (list[str] | None): List of serial numbers to set power
    """

    power: float
    fan_voltage: float
    save_dir: str
    step_no: int
    serials_to_set_power: list[str] | None = None


def set_fan_voltage(voltage: float, current: float, enable: bool = True):
    """Set the fan voltage of the power supply.

    Args:
        voltage (float): Voltage to set (between 0 and 12 V)
        current (float): Current to set (between 0 and 2 A)
        enable (bool): Whether to enable the output
    """
    if not (MIN_V <= voltage <= MAX_V):
        raise ValueError(f"Voltage must be between {MIN_V} and {MAX_V} V")
    if not (MIN_I <= current <= MAX_I):
        raise ValueError(f"Current must be between {MIN_I} and {MAX_I} A")

    try:
        psu = RSPowerSupply(PSU_IP)
        psu.select_channel(FAN_CHANNEL)
        psu.set_voltage(voltage)
        psu.set_current(current)
        psu.set_output_state(enable)

    except Exception as e:
        print(f"Error setting fan voltage: {e}")
    finally:
        if psu:
            psu.disconnect()


def plot_step_data(file_path: str):
    """Plot the data from the monitoring session.

    Args:
        file_path (str): Path to the CSV file containing the monitoring data
    """
    file_path = Path(file_path)
    base_name = file_path.stem
    output_dir = file_path.parent

    output_transients = output_dir / "transients"
    output_heatmaps = output_dir / "heatmaps"
    df = pd.read_csv(file_path)

    output_transients.mkdir(parents=True, exist_ok=True)
    output_heatmaps.mkdir(parents=True, exist_ok=True)

    create_temperature_plots(df, output_transients / f"{base_name}.png")
    generate_heatmap_grid(df, output_heatmaps / f"{base_name}.png")


def scenario_step(
    crate_manager: DIOTCrateManager, step_params: StepParams
) -> tuple[bool, float]:
    """Run a scenario step.

    Args:
        crate_manager (DIOTCrateManager): The crate manager instance
        step_params (StepParams): The parameters for the step

    Returns:
        tuple: A tuple containing:
            - bool: True if the step reached steady state, False otherwise
            - float: Elapsed time of the monitoring session
    """
    logger = logging.getLogger("scenario")
    logger.debug("Starting scenario step")
    power = step_params.power
    save_dir = step_params.save_dir
    step_no = step_params.step_no
    fan_voltage = step_params.fan_voltage
    serials_to_set_power = step_params.serials_to_set_power
    if serials_to_set_power is None:
        serials_to_set_power = list(crate_manager.cards.keys())

    available_cards = list(crate_manager.cards.keys())
    power_str = str(power).replace(".", "W")
    monitor_session = MonitoringSession(
        crate_manager=crate_manager,
        save_dir=save_dir,
        session_name=f"step_{step_no}_{power_str}",
    )

    logger.info("Step parameters:")
    logger.info(f"  - Power: {power} W")
    logger.info(f"  - Fan voltage: {fan_voltage} V")
    logger.info(f"  - Save directory: {save_dir}")
    logger.info(f"  - Step number: {step_no}")
    logger.info(f"  - Serial numbers to set power: {serials_to_set_power}")
    logger.info(f"  - Available cards: {available_cards}")
    logger.info(f"  - Monitoring session: {monitor_session.session_name}")
    logger.info(f"  - Monitoring session file path: {monitor_session.file_path}")

    set_fan_voltage(fan_voltage, 2.0, enable=True)

    # zero output power for all cards
    crate_manager.set_cards_load_power(
        serial=available_cards,
        power=0.0,
    )

    # set power only for the specified cards
    crate_manager.set_cards_load_power(
        serial=serials_to_set_power,
        power=power,
    )

    try:
        elapsed_time = monitor_session.monitor(
            duration=MAX_STEP_DURATION_MINUTES * 60,
            interval=1.0,
            shutdown_at_end=False,
            shutdown_card_on_ot=True,
            stop_on_steady_state=True,
            stop_on_ot=True,
            save_every_iteration=True,
            serials_to_monitor=available_cards,
        )
    except KeyboardInterrupt:
        logger.info("Monitoring interrupted by user.")
        crate_manager.shutdown_all_loads()
    except Exception as e:
        logger.error(f"Error during monitoring: {e}", exc_info=True)
        crate_manager.shutdown_all_loads()
        raise Exception from e
    finally:
        plot_step_data(monitor_session.file_path)
        logger.info("Monitoring session finished.")

    if not monitor_session.all_steady:
        logger.warning("Monitoring session did not reach steady state.")
        crate_manager.shutdown_all_loads()
        return False, elapsed_time

    return True, elapsed_time


def setup_scenario_steps(results_dir: str) -> list[StepParams]:
    """Setup the scenario steps.

    Args:
        results_dir (str): Directory to save the monitoring data

    Returns:
        list: A list of StepParams objects representing the steps
    """
    steps = []
    # All cards will be set to the same power
    step = StepParams(
        power=DEFAULT_POWER_PER_CARD,
        fan_voltage=12.0,
        save_dir=results_dir,
        step_no=len(steps),
        serials_to_set_power=None,
    )
    steps.append(step)

    # # Every second board will be set to the same power
    # step = StepParams(
    #     power=DEFAULT_POWER_PER_CARD,
    #     fan_voltage=12.0,
    #     save_dir=results_dir,
    #     step_no=len(steps),
    #     serials_to_set_power=[f"DT{i:02d}" for i in range(0, 9, 2)],
    # )
    # steps.append(step)

    # # Every second bard but starting from the second one
    # step = StepParams(
    #     power=DEFAULT_POWER_PER_CARD,
    #     fan_voltage=12.0,
    #     save_dir=results_dir,
    #     step_no=len(steps),
    #     serials_to_set_power=[f"DT{i:02d}" for i in range(1, 9, 2)],
    # )
    # steps.append(step)

    # # Disable all loads and wait for the system to cool down
    # # before the next step
    # step = StepParams(
    #     power=0.0,
    #     fan_voltage=12.0,
    #     save_dir=results_dir,
    #     step_no=len(steps),
    #     serials_to_set_power=None,
    # )
    # steps.append(step)

    # # Next steps - gradually increase the power with disabled fans and wait for OT
    # # to be reached
    # fan_failure_powers = [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0]
    # len_steps = len(steps)
    # for idx, pwr in enumerate(fan_failure_powers):
    #     step = StepParams(
    #         power=pwr,
    #         fan_voltage=0.0,
    #         save_dir=results_dir,
    #         step_no=len_steps + idx,
    #         serials_to_set_power=None,
    #     )
    #     steps.append(step)
    
    # # Intermediate step to cool down the system
    # step = StepParams(
    #     power=0.0,
    #     fan_voltage=12.0,
    #     save_dir=results_dir,
    #     step_no=len(steps),
    #     serials_to_set_power=None,
    # )
    # steps.append(step)

    # fan_failure_voltages = [12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5, 8, 7.5, 7] 
    # len_steps = len(steps)
    # for idx, voltage in enumerate(fan_failure_voltages):
    #     step = StepParams(
    #         power=DEFAULT_POWER_PER_CARD,
    #         fan_voltage=voltage,
    #         save_dir=results_dir,
    #         step_no=len_steps + idx,
    #         serials_to_set_power=None,
    #     )
    #     steps.append(step)

    return steps


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run a scenario for the DIOT system.")
    parser.add_argument(
        "--results-dir",
        type=str,
        default=RESULTS_DIR,
        help="Directory to save the monitoring data (default: 'results'). Fan setup will be appended to the directory.",
    )
    parser.add_argument(
        "fans",
        choices=["schroff", "80", "100", "backplane", "backplane_guided"],
        help="Fan setup to use for the analysis.",
    )

    logger = setup_logging(name="scenario")

    # disable logging for pyvisa and matplotlib
    pyvisa_logger = logging.getLogger("pyvisa")
    pyvisa_logger.setLevel(logging.WARNING)
    matplotlib_logger = logging.getLogger("matplotlib")
    matplotlib_logger.setLevel(logging.WARNING)
    pil_logger = logging.getLogger("PIL")
    pil_logger.setLevel(logging.WARNING)

    logger.debug("Starting main function")

    args = parser.parse_args()

    fan_str = {
        "schroff": "SCHROFF",
        "80": "CUSTOM_80",
        "100": "CUSTOM_100",
        "backplane": "BACKPLANE",
        "backplane_guided": "BACKPLANE_GUIDED",
    }[args.fans]

    results_dir = f"{args.results_dir}/{fan_str}"
    scenario_steps = setup_scenario_steps(results_dir)

    availible_cards = list_available_cards()
    if not availible_cards:
        print("No DIOT cards found.")
        return

    try:
        crate_manager = DIOTCrateManager(
            serial_numbers=availible_cards,
            ot_shutdown=OT_SHUTDOWN,
            hysteresis=HYSTERESIS,
        )

        for step in scenario_steps:
            is_steady, elapsed_time = scenario_step(
                crate_manager=crate_manager,
                step_params=step,
            )
            if not is_steady:
                logger.warning(f"Step {step.step_no} did not reach steady state.")
                logger.warning("=== CONTINUING TO THE NEXT STEP REGARDLESS ===")
                # break
            logger.info(f"Step {step.step_no} completed successfully.")
            logger.info(f"Elapsed time: {elapsed_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error during monitoring: {e}", exc_info=True)
    else:
        logger.info("All steps completed successfully.")
    finally:
        crate_manager.shutdown_all_loads()


if __name__ == "__main__":
    main()
