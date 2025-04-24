import datetime
import time

import csv

from diot.manager import DIOTCrateManager
from pathlib import Path

SLEEP_TIME = 0.5  # seconds


class MonitoringSession:
    def __init__(
        self,
        crate_manager: DIOTCrateManager,
        card_serials: list | None = None,
        save_dir: str | None = None,
        session_name: str | None = None,
    ) -> None:
        self.crate_manager = crate_manager

        if card_serials is None:
            card_serials = list(crate_manager.cards.keys())
        self.card_serials = card_serials

        self.cards = [crate_manager.cards[serial] for serial in card_serials]

        self.ot_events = [False] * len(self.cards)

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

    def _initialize_csv(self):  # TODO: add fieldnames
        if not self._file_initialized:
            # Newline is recommended for csv:
            # https://docs.python.org/3/library/csv.html#id4
            with open(self.file_path, "w", newline="") as f:
                header = [
                    "elapsed_time",
                    "card_serial",
                    "channel",
                    "temperature",
                    "load_power",
                    "ot_shutdown",
                    "voltage",
                    "current",
                ]
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()
            self._file_initialized = True
        else:
            raise RuntimeError(
                "CSV file already initialized. Aborting so no data is lost."
            )

    def _write_measurements(self, measurements: list[dict]):
        if not self._file_initialized:
            self._initialize_csv()

        with open(self.file_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=measurements[0].keys())
            writer.writerows(measurements)

    def collect_measurements(
        self, elapsed_time: float, shutdown_card_on_ot: bool = True
    ):
        self.ot_events, card_reports = zip(
            *[card.report() for card in self.cards], strict=True
        )

        # Don't move to numpy yet, as numpy arrays are less efficient for
        # appending data than lists. Even though we theoretically know the
        # number of measurements (duration / interval), we don't know how many
        # measurements will be taken before the shutdown event occurs (which
        # will break the loop). Moreove, we don't know how long will it take
        # to enumerate the cards and get the measurements, so we the number of
        # measurements is not known in advance.
        # See: https://github.com/numpy/numpy/issues/17090#issuecomment-674421168
        measurements = []
        for ix, (card, report) in enumerate(zip(self.cards, card_reports, strict=True)):
            card_serial = card.card_id
            voltage = report["voltage"]
            current = report["current"]

            for ch_ix, ch_data in enumerate(report["channels"]):
                row = {
                    "elapsed_time": elapsed_time,
                    "card_serial": card_serial,
                    "channel": ch_ix,
                    "temperature": ch_data["temperature"],
                    "load_power": ch_data["load_power"],
                    "ot_shutdown": ch_data["ot_shutdown"],
                    "voltage": voltage,
                    "current": current,
                }
                measurements.append(row)

            if shutdown_card_on_ot and self.ot_events[ix]:
                print(
                    f"OT on card {card_serial} detected... shutting down card's loads."
                )
                # TODO: add storing the state of the card
                #  -> possibly move this to another thread, so we have actually
                #     monitoring capability
                card.shutdown_all_loads()

        return any(self.ot_events), measurements

    def get_ot_cards(self):
        return [
            card.card_id
            for card, ot in zip(self.cards, self.ot_events, strict=True)
            if ot
        ]

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
                    ot_ev_detected, measurements = self.collect_measurements(
                        elapsed_time, shutdown_card_on_ot
                    )
                    self.measurements.extend(measurements)

                    if save_every_iteration:
                        self._write_measurements(measurements)

                    if ot_ev_detected and stop_on_ot:
                        break
                    prev_t = t
        finally:
            if not save_every_iteration:
                self._write_measurements(self.measurements)

            if shutdown_at_end:
                for card in self.cards:
                    card.shutdown_all_loads()
