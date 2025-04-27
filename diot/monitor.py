import datetime
import time

import pprint
import csv

from diot.manager import DIOTCrateManager
from pathlib import Path

SLEEP_TIME = 0.1  # seconds


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

    def _initialize_csv(self, fieldnames = None):  # TODO: add fieldnames
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
            print("No measurements to write.")
            return
        
        if not self._file_initialized:
            self._initialize_csv(fieldnames=measurements[0].keys())

        with open(self.file_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=measurements[0].keys())
            writer.writerows(measurements)

    def monitor(
        self,
        duration: float,
        interval: float,
        shutdown_card_on_ot: bool = True,
        stop_on_ot: bool = False,
        shutdown_at_end: bool = True,
        save_every_iteration: bool = True,
    ):
        self.measurements = []
        t0 = time.monotonic()
        t = t0
        prev_t = t

        try:
            while time.monotonic() - t0 < duration:
                t = time.monotonic()
                elapsed_time = t - t0

                since_prev_t = t - prev_t
                if since_prev_t < interval:
                    time.sleep(min(interval - since_prev_t, SLEEP_TIME))
                else:
                    soft_ot_status, measurements = self.crate_manager.report_cards(
                        shutdown_card_on_ot, elapsed_time
                    )
                    pprint.pprint(measurements)
                    ot_ev_detected = any(
                        [status for _, status in soft_ot_status]
                    )
                    self.measurements.extend(measurements)

                    if save_every_iteration:
                        print("Writing measurements to file...")
                        self._write_measurements(measurements)

                    if ot_ev_detected and stop_on_ot:
                        print("OT event detected. Stopping monitoring.")
                        break
                    prev_t = t
        finally:
            if not save_every_iteration:
                self._write_measurements(self.measurements)

            if shutdown_at_end:
                self.crate_manager.shutdown_all_loads()
                print("All loads shut down")
            print(f"Monitoring session {self.session_name} finished")
            print(f"Data saved to {self.file_path}")
