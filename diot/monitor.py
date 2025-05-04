import csv
import datetime
import logging
import time
from pathlib import Path

from diot.manager import DIOTCrateManager

SLEEP_TIME = 0.1  # seconds

logger = logging.getLogger(__name__)


class MonitoringSession:
    def __init__(
        self,
        crate_manager: DIOTCrateManager,
        save_dir: str | None = None,
        session_name: str | None = None,
    ) -> None:
        self.crate_manager = crate_manager

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_name = (
            f"{session_name}_{timestamp}" if session_name else f"monitoring_{timestamp}"
        )

        save_dir = Path(save_dir) if save_dir else Path.cwd() / "diot_data"
        if not save_dir.exists():
            save_dir.mkdir(parents=True)
        self.save_dir = save_dir
        self.session_name = session_name
        self.file_path = save_dir / f"{session_name}.csv"

        self._file_initialized = False
        # Track if steady state has been reached for reporting to user
        self._steady_state_reached = {}

    def _initialize_csv(self, fieldnames=None):  # TODO: add fieldnames
        if not self._file_initialized:
            if fieldnames is None:
                fieldnames = [
                    "elapsed_time",
                    "card_serial",
                    "channel",
                    "temperature",
                    "load_power",
                    "ot_shutdown_t",
                    "ot_ev",
                    "voltage",
                    "current",
                    "steady_state",
                    "temp_rate_per_min",
                ]

            # Newline is recommended for csv:
            # https://docs.python.org/3/library/csv.html#id4
            with open(self.file_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
            self._file_initialized = True
        else:
            raise RuntimeError(
                "CSV file already initialized. Aborting so no data is lost."
            )

    def _write_measurements(self, measurements: list[dict]):
        if not measurements:
            logger.info("No measurements to write.")
            return

        if not self._file_initialized:
            logger.debug("Initializing CSV file with headers.")
            self._initialize_csv(fieldnames=measurements[0].keys())

        with open(self.file_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=measurements[0].keys())
            writer.writerows(measurements)
            logger.debug(
                f"Wrote {len(measurements)} measurements to CSV {self.file_path}."
            )

    def monitor(
        self,
        duration: float,
        interval: float,
        shutdown_card_on_ot: bool = True,
        stop_on_ot: bool = False,
        stop_on_steady_state: bool = False,
        shutdown_at_end: bool = True,
        save_every_iteration: bool = True,
        serials_to_monitor: list[str] | None = None,
    ):
        """Monitor temperature and other parameters of DIOT cards.

        Args:
            duration: Monitoring duration in seconds
            interval: Sampling interval in seconds
            shutdown_card_on_ot: Whether to shut down cards on over-temperature events
            stop_on_ot: Whether to stop monitoring on over-temperature events
            stop_on_steady_state: Whether to stop monitoring when all cards reach steady state
            shutdown_at_end: Whether to shut down all loads at the end
            save_every_iteration: Whether to save measurements after each iteration
            serials_to_monitor: List of card serial numbers to monitor
        """
        logger.info(f"Monitoring session '{self.session_name}' started...")
        logger.info(f"\tSerials to monitor: {serials_to_monitor}")
        logger.info(f"\tMonitoring duration: {duration:.2f} s")
        logger.info(f"\tSampling interval: {interval:.2f} s")
        logger.info(f"\tShutdown card on OT: {shutdown_card_on_ot}")
        logger.info(f"\tStop on OT: {stop_on_ot}")
        logger.info(f"\tStop on steady state: {stop_on_steady_state}")
        logger.info(f"\tShutdown at end: {shutdown_at_end}")

        self.measurements = []
        t0 = time.monotonic()
        t = t0
        prev_t = t

        try:
            while time.monotonic() - t0 < duration:
                t = time.monotonic()
                elapsed_time = t - t0

                since_prev_t = t - prev_t

                # prev_t == t0 should be true only for the first iteration
                if since_prev_t >= interval or prev_t == t0:
                    soft_ot_status, measurements, steady_states = (
                        self.crate_manager.report_cards(
                            shutdown_card_on_ot, elapsed_time, serials_to_monitor
                        )
                    )
                    # pprint.pprint(measurements)
                    ot_ev_detected = any(soft_ot_status)
                    self.measurements.extend(measurements)

                    # Check for newly reached steady states
                    all_steady = True
                    for card_id, state_info in steady_states.items():
                        all_steady = all_steady and state_info["is_steady"]

                        # Report when card first reaches steady state
                        if (
                            state_info["is_steady"]
                            and not self._steady_state_reached.get(
                                card_id, (False, 0.0)
                            )[0]
                        ):
                            self._steady_state_reached[card_id] = (True, elapsed_time)
                            logger.info(
                                f"Card {card_id} has reached steady state (temperature change ≤ 1K/minute) at {elapsed_time:.2f} seconds"
                            )

                            logger.debug("  Temperature rates (K/min):")
                            for ch_idx, rate in state_info["temp_rates"].items():
                                logger.debug(f"    Channel {ch_idx}: {rate:.4f} K/min")

                    if save_every_iteration:
                        self._write_measurements(measurements)

                    # Check if we should stop monitoring based on events
                    if ot_ev_detected and stop_on_ot:
                        logger.warning("OT event detected. Stopping monitoring.")
                        break

                    if all_steady and stop_on_steady_state:
                        logger.info(
                            f"All cards have reached steady state. Stopping monitoring after {elapsed_time:02f} seconds."
                        )
                        break

                    prev_t = t
                else:
                    time.sleep(min(interval - since_prev_t, SLEEP_TIME))
        finally:
            if not save_every_iteration:
                self._write_measurements(self.measurements)

            if shutdown_at_end:
                logger.info("Shutting down all loads at the end of monitoring.")
                self.crate_manager.shutdown_all_loads()
            logger.info(
                f"Monitoring session '{self.session_name}' finished after {elapsed_time:.2f} seconds"
            )
            logger.info(f"Data saved to {self.file_path}")

            if self._steady_state_reached:
                logger.info("Steady state reached for the following cards:")
                for card_id, (
                    reached_steady,
                    elapsed_time,
                ) in self._steady_state_reached.items():
                    if reached_steady:
                        logger.info(
                            f"  Card {card_id}: Steady state reached after {elapsed_time:.2f} seconds"
                        )
                    else:
                        logger.info(f"  Card {card_id}: Steady state NOT reached")
