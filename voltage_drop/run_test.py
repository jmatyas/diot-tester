import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from const import KEYSIGHT_DMM_IP_HIGH, KEYSIGHT_DMM_IP_LOW
from diot import DIOTCrateManager
from utils.keysight_dmm import Keysight34461A, MeasurementMode
from voltage_drop.config import (
    CHANNEL_COUNT,
    DMM_AVERAGE_COUNT,
    DMM_NPLC,
    DMM_TIMEOUT,
    DMM_VOLTAGE_RANGE,
    LOAD_CURRENT_2A,
    LOAD_CURRENT_4A,
    LOAD_POWER_2A,
    LOAD_POWER_4A,
    SETTLING_TIME,
    SLOT_OFFSET,
    SUPPLY_VOLTAGE,
    TEST_SLOT_PAIRS,
    VOLTAGE_DIVIDER_RATIO,
)
from voltage_drop.data_structs import MeasurementPoint, SlotPairMeasurement, TestResults
from voltage_drop.utils import (
    calculate_power_from_current,
    j3_to_rail_voltage,
    slot_to_serial,
    wait_for_user_confirmation,
)


def configure_dmm(dmm: Keysight34461A, dmm_id: str):
    """Configure DMM for J3 voltage measurements.

    Args:
        dmm: DMM instance
        dmm_id: Identifier for logging
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Configuring {dmm_id} for J3 voltage measurements")

    dmm.configure(
        mode=MeasurementMode.VOLT_DC,
        range_value=DMM_VOLTAGE_RANGE,
    )

    # Set integration time for noise reduction
    dmm.set_nplc(DMM_NPLC)

    logger.info(f"{dmm_id} configured: Range={DMM_VOLTAGE_RANGE}V, NPLC={DMM_NPLC}")


def take_dmm_measurement(
    dmm: Keysight34461A,
    dmm_id: str,
    load_condition: str,
    average_count: int = DMM_AVERAGE_COUNT,
) -> MeasurementPoint:
    """Take averaged DMM measurement.

    Args:
        dmm: DMM instance
        dmm_id: DMM identifier
        load_condition: Description of load condition
        average_count: Number of measurements to average

    Returns:
        MeasurementPoint with averaged result
    """
    logger = logging.getLogger(__name__)

    try:
        avg_voltage, std_dev = dmm.measure_average(count=average_count)
        rail_voltage = j3_to_rail_voltage(avg_voltage)

        measurement = MeasurementPoint(
            voltage=avg_voltage,
            voltage_rail=rail_voltage,
            std_dev=std_dev,
            load_condition=load_condition,
            dmm_id=dmm_id,
        )

        logger.debug(
            f"{dmm_id} {load_condition}: J3={avg_voltage:.6f}V ± {std_dev:.6f}V, "
            f"Rail={rail_voltage:.4f}V"
        )

        return measurement

    except Exception as e:
        logger.error(f"Failed to take {dmm_id} measurement: {e}", exc_info=True)
        raise


# =============================================================================
# Load Control Functions
# =============================================================================


def set_card_load(
    crate_manager: DIOTCrateManager,
    serial: str,
    power_per_channel: float,
    slot: int | None = None,
):
    """Set load power on a specific card.

    Args:
        crate_manager: DIOT crate manager instance
        serial: Card serial number
        power_per_channel: Power in watts per channel
        slot: Slot number for logging (optional)
    """
    logger = logging.getLogger(__name__)

    slot_str = f"Slot {slot} " if slot else ""
    logger.info(
        f"Setting {slot_str}({serial}) load: {power_per_channel:.2f}W per channel, "
        f"Total: {power_per_channel * CHANNEL_COUNT:.1f}W"
    )

    try:
        card = crate_manager.get_card(serial)
        card.set_all_load_power(power_per_channel)

        # Verify setting (read back from one channel)
        actual_power = card.load_channels[0].load_power
        logger.debug(
            f"Load set successfully. Readback: {actual_power:.3f}W per channel"
        )

    except Exception as e:
        logger.error(f"Failed to set load on {serial}: {e}", exc_info=True)
        raise


def shutdown_card_load(
    crate_manager: DIOTCrateManager, serial: str, slot: int | None = None
):
    """Shutdown all loads on a card.

    Args:
        crate_manager: DIOT crate manager instance
        serial: Card serial number
        slot: Slot number for logging (optional)
    """
    logger = logging.getLogger(__name__)

    slot_str = f"Slot {slot} " if slot else ""
    logger.info(f"Shutting down {slot_str}({serial}) loads")

    try:
        card = crate_manager.get_card(serial)
        card.shutdown_all_loads()
        logger.debug(f"Loads shutdown successfully on {serial}")
    except Exception as e:
        logger.error(f"Failed to shutdown loads on {serial}: {e}", exc_info=True)
        raise


# =============================================================================
# Measurement Sequence
# =============================================================================


def measure_slot_pair(
    crate_manager: DIOTCrateManager,
    dmm1: Keysight34461A,
    dmm2: Keysight34461A,
    slot_a: int,
    slot_b: int,
    use_power: bool = True,
) -> SlotPairMeasurement:
    """Execute complete measurement sequence for a slot pair.

    Args:
        crate_manager: DIOT crate manager
        dmm1: DMM connected to slot_a J3
        dmm2: DMM connected to slot_b J3
        slot_a: Slot number for loaded card
        slot_b: Slot number for monitoring card
        use_power: If True, set load by power; if False, calculate from current

    Returns:
        SlotPairMeasurement with all results
    """
    logger = logging.getLogger(__name__)

    serial_a = slot_to_serial(slot_a)
    serial_b = slot_to_serial(slot_b)

    logger.info(f"\n{'=' * 80}")
    logger.info(f"Measuring Slot Pair: ({slot_a}, {slot_b}) = ({serial_a}, {serial_b})")
    logger.info(f"{'=' * 80}")

    measurement = SlotPairMeasurement(
        slot_a=slot_a,
        slot_b=slot_b,
        serial_a=serial_a,
        serial_b=serial_b,
        timestamp=datetime.now().isoformat(),
    )

    try:
        # =====================================================================
        # Step 1: User Instructions
        # =====================================================================
        message = (
            f"\n SETUP INSTRUCTIONS:\n"
            f"   1. Connect DMM1 to J3 connector of SLOT {slot_a} ({serial_a})\n"
            f"   2. Connect DMM2 to J3 connector of SLOT {slot_b} ({serial_b})\n"
            f"   3. Verify connections are secure\n"
        )

        if not wait_for_user_confirmation(message):
            measurement.success = False
            measurement.error_message = "User cancelled during setup"
            return measurement

        # Ensure loads are off before starting
        shutdown_card_load(crate_manager, serial_a, slot_a)
        time.sleep(SETTLING_TIME)

        # =====================================================================
        # Step 2: Baseline Measurement (No Load)
        # =====================================================================
        logger.info("Step 2: Baseline measurement (no load)")

        measurement.dmm1_baseline = take_dmm_measurement(dmm1, "DMM1", "no_load")
        measurement.dmm2_baseline = take_dmm_measurement(dmm2, "DMM2", "no_load")

        logger.info(
            f"  Baseline: DMM1={measurement.dmm1_baseline.voltage:.6f}V, "
            f"DMM2={measurement.dmm2_baseline.voltage:.6f}V"
        )

        # =====================================================================
        # Step 3: Apply 2A Load to Slot A
        # =====================================================================
        logger.info(f"Step 3: Applying 2A load to Slot {slot_a}")

        if use_power:
            power_2a = LOAD_POWER_2A
        else:
            power_2a = calculate_power_from_current(LOAD_CURRENT_2A)

        set_card_load(crate_manager, serial_a, power_2a, slot_a)

        logger.debug(f"Waiting {SETTLING_TIME}s for settling...")
        time.sleep(SETTLING_TIME)

        measurement.dmm1_2a_load = take_dmm_measurement(dmm1, "DMM1", "2A")
        measurement.dmm2_2a_load = take_dmm_measurement(dmm2, "DMM2", "2A")

        logger.info(
            f"  2A Load: DMM1={measurement.dmm1_2a_load.voltage:.6f}V, "
            f"DMM2={measurement.dmm2_2a_load.voltage:.6f}V"
        )

        # =====================================================================
        # Step 4: Apply 4A Load to Slot A
        # =====================================================================
        logger.info(f"Step 4: Applying 4A load to Slot {slot_a}")

        if use_power:
            power_4a = LOAD_POWER_4A
        else:
            power_4a = calculate_power_from_current(LOAD_CURRENT_4A)

        set_card_load(crate_manager, serial_a, power_4a, slot_a)

        logger.debug(f"Waiting {SETTLING_TIME}s for settling...")
        time.sleep(SETTLING_TIME)

        measurement.dmm1_4a_load = take_dmm_measurement(dmm1, "DMM1", "4A")
        measurement.dmm2_4a_load = take_dmm_measurement(dmm2, "DMM2", "4A")

        logger.info(
            f"  4A Load: DMM1={measurement.dmm1_4a_load.voltage:.6f}V, "
            f"DMM2={measurement.dmm2_4a_load.voltage:.6f}V"
        )

        # =====================================================================
        # Step 5: Shutdown Loads
        # =====================================================================
        logger.info(f"Step 5: Shutting down loads on Slot {slot_a}")
        shutdown_card_load(crate_manager, serial_a, slot_a)

        # =====================================================================
        # Step 6: Calculate Results
        # =====================================================================
        calculate_results(measurement)

        measurement.success = True
        logger.info("✓ Slot pair measurement completed successfully")

    except Exception as e:
        logger.error(f"✗ Slot pair measurement failed: {e}", exc_info=True)
        measurement.success = False
        measurement.error_message = str(e)

        # Attempt to shutdown loads on error
        try:
            shutdown_card_load(crate_manager, serial_a, slot_a)
        except Exception:
            logger.error("Failed to shutdown loads on error", exc_info=True)

    return measurement


def calculate_results(measurement: SlotPairMeasurement):
    """Calculate voltage drops, rail resistance, and crosstalk from measurements.

    Args:
        measurement: SlotPairMeasurement instance to update with calculations
    """
    logger = logging.getLogger(__name__)
    logger.info("Calculating results...")

    try:
        # Use rail voltages for calculations (actual power rail, not J3 reading)
        v_baseline_a = measurement.dmm1_baseline.voltage_rail
        v_2a_a = measurement.dmm1_2a_load.voltage_rail
        v_4a_a = measurement.dmm1_4a_load.voltage_rail

        v_baseline_b = measurement.dmm2_baseline.voltage_rail
        v_2a_b = measurement.dmm2_2a_load.voltage_rail
        v_4a_b = measurement.dmm2_4a_load.voltage_rail

        # Voltage drops on slot A (loaded slot)
        measurement.voltage_drop_2a = v_baseline_a - v_2a_a
        measurement.voltage_drop_4a = v_baseline_a - v_4a_a

        # Rail resistance: R = ΔV / ΔI
        # ΔI for 2A condition: 2A - 0A = 2A
        # ΔI for 4A condition: 4A - 0A = 4A
        delta_i_2a = 2.0
        delta_i_4a = 4.0

        if delta_i_2a > 0:
            measurement.rail_resistance_2a = measurement.voltage_drop_2a / delta_i_2a

        if delta_i_4a > 0:
            measurement.rail_resistance_4a = measurement.voltage_drop_4a / delta_i_4a

        # Crosstalk: voltage change on slot B when slot A is loaded
        measurement.crosstalk_2a = v_baseline_b - v_2a_b
        measurement.crosstalk_4a = v_baseline_b - v_4a_b

        logger.info("Calculated Results:")
        logger.info(f"  Voltage Drop (2A): {measurement.voltage_drop_2a:.6f}V")
        logger.info(f"  Voltage Drop (4A): {measurement.voltage_drop_4a:.6f}V")
        logger.info(f"  Rail Resistance (2A): {measurement.rail_resistance_2a:.6f}Ω")
        logger.info(f"  Rail Resistance (4A): {measurement.rail_resistance_4a:.6f}Ω")
        logger.info(f"  Crosstalk (2A): {measurement.crosstalk_2a:.6f}V")
        logger.info(f"  Crosstalk (4A): {measurement.crosstalk_4a:.6f}V")

    except Exception as e:
        logger.error(f"Failed to calculate results: {e}", exc_info=True)
        raise


# =============================================================================
# Main Test Execution
# =============================================================================


def run_voltage_drop_test(
    dmm1_address: str = KEYSIGHT_DMM_IP_LOW,
    dmm2_address: str = KEYSIGHT_DMM_IP_HIGH,
    slot_pairs: list[tuple[int, int]] = TEST_SLOT_PAIRS,
    slot_offset: int = SLOT_OFFSET,
    use_power: bool = True,
    output_dir: str = ".",
) -> TestResults:
    """Execute complete voltage drop and crosstalk test.

    Args:
        dmm1_address: DMM1 IP address or VISA resource
        dmm2_address: DMM2 IP address or VISA resource
        slot_pairs: List of (slot_a, slot_b) tuples to test
        slot_offset: Offset for slot to serial conversion
        use_power: Use power (True) or current (False) for load setting
        output_dir: Directory for output files

    Returns:
        TestResults object with all measurements
    """
    logger = logging.getLogger(__name__)

    # Update global slot offset
    global SLOT_OFFSET
    SLOT_OFFSET = slot_offset

    # Initialize results
    results = TestResults(
        test_name="DIOT Voltage Drop and Crosstalk Test",
        start_time=datetime.now().isoformat(),
        configuration={
            "slot_offset": slot_offset,
            "channel_count": CHANNEL_COUNT,
            "supply_voltage": SUPPLY_VOLTAGE,
            "load_current_2a": LOAD_CURRENT_2A,
            "load_current_4a": LOAD_CURRENT_4A,
            "load_power_2a": LOAD_POWER_2A,
            "load_power_4a": LOAD_POWER_4A,
            "dmm_voltage_range": DMM_VOLTAGE_RANGE,
            "dmm_nplc": DMM_NPLC,
            "dmm_average_count": DMM_AVERAGE_COUNT,
            "settling_time": SETTLING_TIME,
            "voltage_divider_ratio": VOLTAGE_DIVIDER_RATIO,
            "use_power": use_power,
        },
    )

    logger.info(f"Starting {results.test_name}")
    logger.info(f"Configuration: {results.configuration}")

    try:
        # =====================================================================
        # Initialize Hardware
        # =====================================================================
        logger.info("Initializing hardware...")

        logger.info(f"Connecting to DMM1 at {dmm1_address}...")
        dmm1 = Keysight34461A(dmm1_address, timeout_s=DMM_TIMEOUT)
        configure_dmm(dmm1, "DMM1")

        logger.info(f"Connecting to DMM2 at {dmm2_address}...")
        dmm2 = Keysight34461A(dmm2_address, timeout_s=DMM_TIMEOUT)
        configure_dmm(dmm2, "DMM2")

        logger.info("Initializing DIOT crate manager...")
        crate_manager = DIOTCrateManager()

        # Ensure all loads are off at start
        logger.info("Ensuring all loads are off...")
        crate_manager.shutdown_all_loads()
        time.sleep(1.0)

        logger.info(f"Connected cards: {list(crate_manager.cards.keys())}")

        # =====================================================================
        # Execute Test Sequence
        # =====================================================================
        logger.info(f"\nTesting {len(slot_pairs)} slot pairs...")

        for idx, (slot_a, slot_b) in enumerate(slot_pairs, 1):
            logger.info(f"\n{'#' * 80}")
            logger.info(f"Test {idx}/{len(slot_pairs)}: Slot Pair ({slot_a}, {slot_b})")
            logger.info(f"{'#' * 80}")

            try:
                measurement = measure_slot_pair(
                    crate_manager=crate_manager,
                    dmm1=dmm1,
                    dmm2=dmm2,
                    slot_a=slot_a,
                    slot_b=slot_b,
                    use_power=use_power,
                )
                results.measurements.append(measurement)

                if not measurement.success:
                    logger.warning(
                        f"Measurement failed for slot pair ({slot_a}, {slot_b})"
                    )

                    try:
                        response = input(
                            "\nContinue with remaining tests? (y/n): "
                        ).lower()
                        if response != "y":
                            logger.info("Test sequence aborted by user")
                            break
                    except KeyboardInterrupt:
                        logger.info("Test sequence interrupted")
                        break

            except KeyboardInterrupt:
                logger.info("\nTest interrupted by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error during test: {e}", exc_info=True)
                # Continue with next pair

        # =====================================================================
        # Cleanup
        # =====================================================================
        logger.info("\nCleaning up...")
        crate_manager.shutdown_all_loads()
        dmm1.disconnect()
        dmm2.disconnect()

        # =====================================================================
        # Generate Summary
        # =====================================================================
        results.end_time = datetime.now().isoformat()

        successful = sum(1 for m in results.measurements if m.success)
        failed = len(results.measurements) - successful

        results.summary = {
            "total_tests": len(slot_pairs),
            "completed": len(results.measurements),
            "successful": successful,
            "failed": failed,
        }

        logger.info("\n" + "=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total Tests: {results.summary['total_tests']}")
        logger.info(f"Completed: {results.summary['completed']}")
        logger.info(f"Successful: {results.summary['successful']}")
        logger.info(f"Failed: {results.summary['failed']}")

        # =====================================================================
        # Save Results
        # =====================================================================
        save_results(results, output_dir)

    except Exception as e:
        logger.error(f"Test execution failed: {e}", exc_info=True)
        results.end_time = datetime.now().isoformat()
        results.summary["error"] = str(e)
        raise
    finally:
        logger.info("\nCleaning up...")
        if crate_manager is not None:
            try:
                crate_manager.shutdown_all_loads()
            except Exception as cleanup_err:
                logger.error(f"Failed to shutdown loads during cleanup: {cleanup_err}")
        if dmm1 is not None:
            try:
                dmm1.disconnect()
            except Exception as cleanup_err:
                logger.error(f"Failed to disconnect DMM1: {cleanup_err}")
        if dmm2 is not None:
            try:
                dmm2.disconnect()
            except Exception as cleanup_err:
                logger.error(f"Failed to disconnect DMM2: {cleanup_err}")

    return results


def save_results(results: TestResults, output_dir: str = "."):
    """Save test results to JSON and CSV files.

    Args:
        results: TestResults object
        output_dir: Directory to save files
    """
    logger = logging.getLogger(__name__)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # =========================================================================
    # Save JSON (complete data)
    # =========================================================================
    json_file = output_path / f"voltage_drop_test_{timestamp}.json"

    try:
        # Convert dataclasses to dictionaries for JSON serialization
        results_dict = asdict(results)

        with open(json_file, "w") as f:
            json.dump(results_dict, f, indent=2)

        logger.info(f"Results saved to JSON: {json_file}")
    except Exception as e:
        logger.error(f"Failed to save JSON results: {e}", exc_info=True)

    # =========================================================================
    # Save CSV (summary data for easy analysis)
    # =========================================================================
    csv_file = output_path / f"voltage_drop_test_{timestamp}.csv"

    try:
        import csv

        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow(
                [
                    "Slot_A",
                    "Slot_B",
                    "Serial_A",
                    "Serial_B",
                    "V_Baseline_A",
                    "V_2A_A",
                    "V_4A_A",
                    "V_Baseline_B",
                    "V_2A_B",
                    "V_4A_B",
                    "Voltage_Drop_2A",
                    "Voltage_Drop_4A",
                    "Rail_Resistance_2A",
                    "Rail_Resistance_4A",
                    "Crosstalk_2A",
                    "Crosstalk_4A",
                    "Success",
                    "Error",
                ]
            )

            # Data rows
            for m in results.measurements:
                writer.writerow(
                    [
                        m.slot_a,
                        m.slot_b,
                        m.serial_a,
                        m.serial_b,
                        m.dmm1_baseline.voltage_rail if m.dmm1_baseline else None,
                        m.dmm1_2a_load.voltage_rail if m.dmm1_2a_load else None,
                        m.dmm1_4a_load.voltage_rail if m.dmm1_4a_load else None,
                        m.dmm2_baseline.voltage_rail if m.dmm2_baseline else None,
                        m.dmm2_2a_load.voltage_rail if m.dmm2_2a_load else None,
                        m.dmm2_4a_load.voltage_rail if m.dmm2_4a_load else None,
                        m.voltage_drop_2a,
                        m.voltage_drop_4a,
                        m.rail_resistance_2a,
                        m.rail_resistance_4a,
                        m.crosstalk_2a,
                        m.crosstalk_4a,
                        m.success,
                        m.error_message or "",
                    ]
                )

        logger.info(f"Results saved to CSV: {csv_file}")
    except Exception as e:
        logger.error(f"Failed to save CSV results: {e}", exc_info=True)


# =============================================================================
# Command Line Interface
# =============================================================================


def main():
    """Command line interface for voltage drop test."""
    parser = argparse.ArgumentParser(
        description="DIOT Crate Voltage Drop and Crosstalk Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run test with default DMM addresses (from const.py)
  python voltage_drop_test.py
  
  # Run test with custom DMM addresses
  python voltage_drop_test.py --dmm1 192.168.1.100 --dmm2 192.168.1.101
  
  # Use slot 1 = DT00 instead of DT01
  python voltage_drop_test.py --slot-offset 0
  
  # Test only specific slot pairs
  python voltage_drop_test.py --pairs 1,2 2,3 3,4
        """,
    )

    parser.add_argument(
        "--dmm1",
        dest="dmm1_address",
        default=KEYSIGHT_DMM_IP_LOW,
        help=f"DMM1 IP address or VISA resource name (default: {KEYSIGHT_DMM_IP_LOW})",
    )
    parser.add_argument(
        "--dmm2",
        dest="dmm2_address",
        default=KEYSIGHT_DMM_IP_HIGH,
        help=f"DMM2 IP address or VISA resource name (default: {KEYSIGHT_DMM_IP_HIGH})",
    )
    parser.add_argument(
        "--slot-offset",
        type=int,
        default=SLOT_OFFSET,
        help=f"Slot to serial offset (default: {SLOT_OFFSET}, meaning Slot 1 = DT01)",
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        help="Slot pairs to test (e.g., '1,2 2,3 3,4'). Default: all pairs",
    )
    parser.add_argument(
        "--use-current",
        action="store_true",
        help="Calculate load from current instead of using power directly",
    )
    parser.add_argument(
        "--output-dir",
        default="test_results",
        help="Directory for output files (default: test_results)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--log-file", help="Log file path (default: voltage_drop_test_TIMESTAMP.log)"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    handlers = [logging.StreamHandler(sys.stdout)]

    if args.log_file:
        log_file = args.log_file
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"voltage_drop_test_{timestamp}.log"

    handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(level=log_level, format=log_format, handlers=handlers)

    # Suppress noisy library loggers
    logging.getLogger("pyvisa").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)

    # Parse slot pairs if provided
    if args.pairs:
        try:
            slot_pairs = []
            for pair_str in args.pairs:
                slot_a, slot_b = map(int, pair_str.split(","))
                slot_pairs.append((slot_a, slot_b))
        except Exception as e:
            logger.error(f"Invalid slot pairs format: {e}")
            return 1
    else:
        slot_pairs = TEST_SLOT_PAIRS

    logger.info(f"Log file: {log_file}")
    logger.info(f"Testing slot pairs: {slot_pairs}")

    try:
        results = run_voltage_drop_test(
            dmm1_address=args.dmm1_address,
            dmm2_address=args.dmm2_address,
            slot_pairs=slot_pairs,
            slot_offset=args.slot_offset,
            use_power=not args.use_current,
            output_dir=args.output_dir,
        )

        if results.summary.get("failed", 0) > 0:
            logger.warning("Test completed with failures")
            return 1

        logger.info("Test completed successfully")
        return 0

    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
