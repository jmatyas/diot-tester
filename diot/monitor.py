import csv
import datetime
import logging
import time
from collections import defaultdict, deque
from pathlib import Path

from diot.manager import SECONDS_PER_BOARD, DIOTCrateManager

SLEEP_TIME = 0.1  # seconds

logger = logging.getLogger(__name__)


class MonitoringSession:
    def __init__(
        self,
        crate_manager: DIOTCrateManager,
        ss_threshlod: float = 1.0,
        ss_window_duration: float = 1.5,
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

        self.ss_threshold = ss_threshlod
        self.ss_window_duration_s = ss_window_duration * 60
        self.steady_registry = {}

        self.measurements = []

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

    def set_history_buffer(self, n_cards: int):
        """Set the history buffer for steady state detection.

        This function initializes a history buffer for each card to store
        temperature measurements. The buffer structure is as follows:

        _temp_history = {
            "DT0": {                    # Card ID
                0: deque([(t1, T1),     # Channel 0
                        (t2, T2),
                        ...]),        # Up to N readings
                1: deque([(t1, T1),     # Channel 1
                        (t2, T2),
                        ...]),
                # ...more channels...
            },
            "DT1": {                    # Another card
                # ...channels...
            }
        }

        Args:
            n_cards(int): Number of cards to monitor.
        """
        history_depth = (
            int(self.ss_window_duration_s * (SECONDS_PER_BOARD / n_cards)) + 1
        )

        if hasattr(self, "_temp_history"):
            logger.debug("History buffer already exists... Clearing...")
            self._temp_history.clear()
        else:
            logger.debug(
                f"Setting history buffer for {n_cards} cards with depth {history_depth}."
            )
            self._temp_history = defaultdict(
                lambda: defaultdict(lambda: deque(maxlen=history_depth))
            )

    def _find_window_start_idx(self, card_id: str) -> None | int:
        """Find the start index of the window in the history buffer."""
        if card_id not in self._temp_history:
            logger.warning(f"Card {card_id} not found in history buffer.")
            return None

        # we assume all channels were sampled at the same time
        ch_history = self._temp_history[card_id][0]
        oldest_time, newest_time = ch_history[0][0], ch_history[-1][0]

        enough_data = (
            len(ch_history) >= 2
            and newest_time - oldest_time >= self.ss_window_duration_s
        )
        if not enough_data:
            logger.warning(
                f"Card {card_id} has not enough history to check steady state"
                f" after {newest_time:.2f} s."
            )
            debug_info = (
                f"\tlength of history (on single channel): {len(ch_history)}\n"
                f"\tnewest_time - oldest_time: "
                f"{newest_time - oldest_time:.2f} seconds\n"
                f"\tmin history duration: {self.ss_window_duration_s:.2f} seconds"
            )

            logger.debug(debug_info)
            return None

        window_start_idx = 0
        window_start_time = newest_time - self.ss_window_duration_s
        for i, (t, _) in enumerate(ch_history):
            if t >= window_start_time:
                window_start_idx = i
                logger.debug(
                    f"Window start index for {card_id} is {window_start_idx} "
                    f"with time {t:.2f} seconds."
                )
                break
        return window_start_idx

    def _check_ch_steady_state(
        self, card_id: str, ch_idx: int, window_start_idx: int | None = None
    ) -> tuple[float | None, bool]:
        """Check if a channel has reached steady state.

        Args:
            card_id (str): Card ID.
            ch_idx (int): Channel index.

        Returns:
            bool: True if the channel has reached steady state, False otherwise.
        """
        rate = None
        ch_history = self._temp_history[card_id][ch_idx]
        if window_start_idx is None:
            return rate, False

        # check if all temperatures in the window are within the threshold
        first_time, first_temp = ch_history[window_start_idx]
        last_time, last_temp = ch_history[-1]
        time_diff = last_time - first_time
        if time_diff <= 0:
            msg = (
                f"Time difference for {card_id} channel {ch_idx} is zero "
                f"or negative: {time_diff:.2f} s. Cannot check steady state."
            )
            logger.warning(msg)
            return rate, False

        rate = (last_temp - first_temp) * (60.0 / time_diff)  # K/min
        logger.debug(
            f"dT/dt for {card_id} channel {ch_idx}: {rate:.4f} K/min\n"
            f"dt: {time_diff:.2f} s dT: {last_temp - first_temp:.2f} K\n"
            f"\tt1: {first_time:.2f} s, t2: {last_time:.2f} s\n"
            f"\tT1: {first_temp:.2f} K, T2: {last_temp:.2f} K\n"
        )
        is_channel_steady = abs(rate) <= self.ss_threshold
        return rate, is_channel_steady

    def modify_ss_registry(
        self, card_id: str, is_steady: bool, elapsed_time: float
    ) -> bool:
        """Modify registry containing info about cards' steady state.

        Function returns True if the card has has just reached steady state
        and was added to the registry. It returns False otherwise.

        This function updates the registry for a specific card based on its
        steady state status. If the card has just reached steady state, it is
        added to the registry with the elapsed time. If the card has left
        steady state, it is removed from the registry. The function also logs
        the changes in the registry.

        Args:
            card_id (str): Card ID.
            is_steady (bool): Whether the card is in steady state.
            elapsed_time (float): Elapsed time since monitoring started.
        """
        card_in_registry = card_id in self.steady_registry

        if is_steady and not card_in_registry:
            self.steady_registry[card_id] = (True, elapsed_time)
            logger.info(
                f"Card {card_id} has first reached steady state after {elapsed_time:.2f} s."
            )
            return True

        if card_in_registry:
            if is_steady and not self.steady_registry[card_id][0]:
                self.steady_registry[card_id] = (True, elapsed_time)
                logger.info(
                    f"Card {card_id} has reached steady state again after {elapsed_time:.2f} s."
                )
                return False
            if not is_steady and self.steady_registry[card_id][0]:
                self.steady_registry[card_id] = (False, elapsed_time)
                logger.warning(
                    f"Card {card_id} left steady state after {elapsed_time:.2f} s."
                )
                return False

        return False

    def process_card_report(self, report: dict, elapsed_time: float):
        measurements = []
        card_id = report["card_serial"]
        card_ot_ev = any([ch["ot_ev"] for ch in report["channels"]])
        voltage = report["voltage"]
        current = report["current"]

        ss_per_ch = {}
        rate_per_ch = {}
        window_start_idx = self._find_window_start_idx(card_id)

        for ch_idx, ch_data in enumerate(report["channels"]):
            self._temp_history[card_id][ch_idx].append(
                (elapsed_time, ch_data["temperature"])
            )
            ch_temp_rate, ch_steady_state = self._check_ch_steady_state(
                card_id, ch_idx, window_start_idx
            )
            ss_per_ch[ch_idx] = ch_steady_state
            rate_per_ch[ch_idx] = ch_temp_rate

            row = {
                "elapsed_time": elapsed_time,
                "card_serial": card_id,
                "channel": ch_idx,
                "temperature": ch_data["temperature"],
                "load_power": ch_data["load_power"],
                "ot_shutdown_t": ch_data["ot_shutdown"],
                "ot_ev": ch_data["ot_ev"],
                "voltage": voltage,
                "current": current,
                "steady_state": ch_steady_state,
                "temp_rate_per_min": ch_temp_rate,
            }
            measurements.append(row)
        is_steady = all(ss_per_ch.values())
        logger.debug(
            f"Card {card_id} steady state: {is_steady}, "
            f"\tsteady state per channel: {ss_per_ch}"
        )
        added_to_registry = self.modify_ss_registry(card_id, is_steady, elapsed_time)
        if added_to_registry:
            logger.debug("  Temperature rates (K/min):")
            for ch_idx, rate in rate_per_ch.items():
                logger.debug(f"    Channel {ch_idx}: {rate:.4f} K/min")

        return card_ot_ev, measurements, is_steady

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
        start_time: float | None = None,
    ):
        """Monitor temperature and other parameters of DIOT cards.

        Args:
            duration (float): Duration of the monitoring session in seconds.
            interval (float): Sampling interval in seconds.
            shutdown_card_on_ot (bool): Whether to shut down the card on OT event.
                Use with caution, as it may cause the card to shut down unexpectedly
                if the temperature exceeds the threshold and that kind of exceptions
                are not handled in the code. Default is True.
            stop_on_ot (bool): Whether to stop monitoring on OT event. Default is False.
            stop_on_steady_state (bool): Whether to stop monitoring on steady state.
                Default is False.
            shutdown_at_end (bool): Whether to shut down all loads at the end of monitoring.
                Default is True.
            save_every_iteration (bool): Whether to save measurements every iteration.
                Default is True.
            serials_to_monitor (list[str]): List of card serials to monitor.
                If None, all cards available in DIOTCrateManager are monitored.
            start_time (float | None): Start time for the monitoring session.
                If None, current time is used.

        Returns:
            elapsed_time (float): Elapsed time since the start of the monitoring session.
        """
        logger.info(f"Monitoring session '{self.session_name}' started...")
        logger.info(f"\tSerials to monitor: {serials_to_monitor}")
        logger.info(f"\tMonitoring duration: {duration:.2f} s")
        logger.info(f"\tSampling interval: {interval:.2f} s")
        logger.info(f"\tShutdown card on OT: {shutdown_card_on_ot}")
        logger.info(f"\tStop on OT: {stop_on_ot}")
        logger.info(f"\tStop on steady state: {stop_on_steady_state}")
        logger.info(f"\tShutdown at end: {shutdown_at_end}")

        self.set_history_buffer(
            len(serials_to_monitor)
            if serials_to_monitor
            else len(self.crate_manager.cards)
        )

        self.steady_registry = {}
        _state_info = {}
        ot_ev_detected = False

        offset_t = start_time if start_time else 0.0
        elapsed_time = 0.0

        t0 = time.monotonic()
        t = t0
        prev_t = t

        try:
            while time.monotonic() - t0 < duration:
                t = time.monotonic()
                elapsed_time = t - t0 + offset_t

                since_prev_t = t - prev_t

                # prev_t == t0 should be true only for the first iteration
                if since_prev_t >= interval or prev_t == t0:
                    crate_measurements = []
                    reports = self.crate_manager.report_cards(
                        shutdown_card_on_ot, serials_to_monitor
                    )
                    for report in reports:
                        card_ot_ev, measurements, is_card_steady = (
                            self.process_card_report(report, elapsed_time)
                        )
                        ot_ev_detected |= card_ot_ev
                        _state_info[report["card_serial"]] = is_card_steady
                        crate_measurements.extend(measurements)
                    self.measurements.extend(crate_measurements)

                    all_steady = all(_state_info.values())
                    if all_steady:
                        logger.info(
                            f"All cards have reached steady state after {elapsed_time:.2f} seconds."
                        )

                    if save_every_iteration:
                        self._write_measurements(crate_measurements)

                    if ot_ev_detected and stop_on_ot:
                        logger.warning("OT event detected. Stopping monitoring.")
                        break

                    if all_steady and stop_on_steady_state:
                        logger.info(
                            f"All cards have reached steady state. Stopping monitoring after {elapsed_time:.2f} seconds."
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

            if self.steady_registry:
                logger.info("Steady state reached for the following cards:")
                for card_id, (
                    reached_steady,
                    elapsed_time,
                ) in self.steady_registry.items():
                    if reached_steady:
                        logger.info(
                            f"  Card {card_id}: Steady state reached after {elapsed_time:.2f} seconds"
                        )
                    else:
                        logger.info(f"  Card {card_id}: Steady state NOT reached")

        avg_time_needed = (
            SECONDS_PER_BOARD * len(serials_to_monitor)
            if serials_to_monitor
            else len(self.crate_manager.cards)
        )

        return elapsed_time + avg_time_needed
