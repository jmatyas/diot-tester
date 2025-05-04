import logging
import re
from collections import defaultdict, deque

from diot.cards import DIOTCard
from diot.utils.ftdi_utils import find_serial_numbers

logger = logging.getLogger(__name__)


class DIOTCrateManager:
    """Manager for multiple DIOT cards in a crate."""

    def __init__(
        self,
        serial_numbers: list[str] | None = None,
        frequency: int = 100000,
        ot_shutdown: float = 80,
        hysteresis: float = 75,
    ) -> None:
        """Initialize the DIOTCrateManager with a list of DIOT card serial numbers.

        Args:
            serial_numbers: List of FTDI serial numbers in format "DTxx" where xx is 0-8
            frequency: I2C bus frequency
            ot_shutdown: Default over-temperature shutdown threshold
            hysteresis: Default hysteresis value

        """
        self.cards = {}
        if serial_numbers:
            if not all(
                isinstance(serial, str) and re.match(r"^DT0[0-8]$", serial)
                for serial in serial_numbers
            ):
                raise ValueError("Serial numbers must be in the format 'DTxx'")

            serial_numbers = sorted(serial_numbers, key=lambda x: int(x[2:]))
        else:
            logger.info("Serial numbers not provided. Searching for available cards...")
            discovered = find_serial_numbers()
            if not discovered:
                logger.warning("No DIOT cards (with DTxx serial numbers) found.")
                return
            serial_numbers = sorted(discovered, key=lambda x: int(x[2:]))

        self._temp_history = defaultdict(
            lambda: defaultdict(
                lambda: deque(maxlen=60)
            )  # Store up to 60 readings (for 1 minute)
        )
        self._steady_state_threshold = 1.0  # K per minute
        self._min_history_duration = 60.0  # seconds

        for serial in serial_numbers:
            self.add_card(serial, frequency, ot_shutdown, hysteresis)

    def add_card(
        self,
        serial: str,
        frequency: int = 100000,
        ot_shutdown: float = 80,
        hysteresis: float = 75,
    ) -> None:
        try:
            card = DIOTCard(
                serial=serial,
                frequency=frequency,
                ot_shutdown=ot_shutdown,
                hysteresis=hysteresis,
            )
            self.cards[serial] = card
            logger.info(f"Card {serial} connected successfully")
        except (
            Exception
        ) as e:  # TODO: specify only one exception type - probably I2CNACK
            logger.error(f"Failed to connect to card {serial}: {str(e)}")

    def get_card(self, serial: str) -> DIOTCard:
        """Get a specific card by serial number"""
        if serial not in self.cards:
            raise KeyError(f"Card with serial {serial} not found")
        return self.cards[serial]

    def get_all_cards(self) -> dict[str, DIOTCard]:
        """Get all connected cards"""
        return self.cards

    def shutdown_all_loads(self) -> None:
        """Turn off all loads on all cards"""
        for card in self.cards.values():
            card.shutdown_all_loads()

    def _set_single_card_load_power(self, serial: str, power: float):
        if serial not in self.cards:
            raise KeyError(f"Card with serial {serial} not found")
        card = self.cards[serial]
        if power > card.max_load_power:
            logger.warning(
                f"Power {power} W exceeds maximum load power {card.max_load_power} W"
            )
            logger.warning(
                f"Setting load power to maximum {card.max_load_power} W instead"
            )
            # raise ValueError(
            #     f"Power {power} W exceeds maximum load power {card.max_load_power} W"
            # )
            power = card.max_load_power
        power_per_channel = power / len(card.load_channels)
        card.set_all_load_power(power_per_channel)

    def set_cards_load_power(self, serial: list[str] | str, power: list[float] | float):
        if isinstance(serial, str):
            serial = [serial]
        if isinstance(power, int):
            power = [float(power)] * len(serial)
        if isinstance(power, float):
            power = [power] * len(serial)
        if len(serial) != len(power):
            raise ValueError("Serial numbers and power lists must have the same length")

        logger.debug(f"Setting load power for cards: {serial} to {power}")

        for s, p in zip(serial, power, strict=True):
            self._set_single_card_load_power(s, p)

    def _check_steady_state(
        self, card_id: str, elapsed_time: float
    ) -> tuple[bool, dict[int, float]]:
        """Check if all channels on a card have reached steady state.

        Returns:
            Tuple of (is_steady, rates_dict) where:
                - is_steady is True if all channels are in steady state
                - rates_dict contains temperature change rates for each channel
        """
        if card_id not in self._temp_history:
            return False, {}

        card_history = self._temp_history[card_id]

        # _temp_history = {
        #     "DT0": {                    # Card ID
        #         0: deque([(t1, T1),     # Channel 0
        #                 (t2, T2),
        #                 ...]),        # Up to 60 readings
        #         1: deque([(t1, T1),     # Channel 1
        #                 (t2, T2),
        #                 ...]),
        #         # ...more channels...
        #     },
        #     "DT1": {                    # Another card
        #         # ...channels...
        #     }
        # }
        history_complete = all(
            len(ch_history) >= 2
            and ch_history[-1][0] - ch_history[0][0] >= self._min_history_duration
            for ch_history in card_history.values()
        )

        if not history_complete:
            return False, {}

        # AVERAGE temperature change rate (K per minute) for each channel during
        # the last minute
        rates = {}
        # print(f"Card {card_id} temperature history:")
        for ch_idx, ch_history in card_history.items():
            latest_time = ch_history[-1][0]
            window_start_time = latest_time - self._min_history_duration

            # TODO: don't need to calculate this for all channels, since we know
            # that each channel was measured at the same time
            window_start_idx = 0
            for i, (t, _) in enumerate(ch_history):
                if t >= window_start_time:
                    window_start_idx = i
                    break

            first_time, first_temp = ch_history[window_start_idx]
            last_time, last_temp = ch_history[-1]
            time_diff = last_time - first_time

            if time_diff <= 0:
                continue

            temp_change = last_temp - first_temp
            rate_per_minute = temp_change * (60.0 / time_diff)
            if ch_idx == 0:
                logger.debug(f"Card {card_id} channel {ch_idx}:")
                logger.debug(f"\ttemperature change rate = {rate_per_minute:.2f} K/min")
                logger.debug(f"\tnewest_temp = {last_temp:.2f} K")
                logger.debug(f"\toldest_temp = {first_temp:.2f} K")
                logger.debug(f"\ttime_diff = {time_diff:.2f} s")
                logger.debug(f"\tsince_start = {elapsed_time:.2f} s")
            rates[ch_idx] = rate_per_minute

        # Check if all channels are in steady state
        is_steady = all(
            abs(rate) <= self._steady_state_threshold for rate in rates.values()
        )

        return is_steady, rates

    def report_cards(
        self,
        shutdown_card_on_ot: bool,
        elapsed_time: float | None = None,
        serials: list[str] | None = None,
    ):
        # Don't move to numpy yet, as numpy arrays are less efficient for
        # appending data than lists. Even though we theoretically know the
        # number of measurements (duration / interval), we don't know how many
        # measurements will be taken before the shutdown event occurs (which
        # will break the loop). Moreove, we don't know how long will it take
        # to enumerate the cards and get the measurements, so we the number of
        # measurements is not known in advance.
        # See: https://github.com/numpy/numpy/issues/17090#issuecomment-674421168
        measurements = []
        steady_states = {}
        if serials is None:
            serials = self.cards.keys()
        # it looks like getting report from a single card takes just above 1 seconds
        # after all it's 18 temp channels and 2 ADCs using I2C over USB
        combined_results = [self.cards[serial].report() for serial in serials]
        ot_per_card = []

        for report in combined_results:
            card_id = report["card_serial"]
            card_ot_ev = any([ch["ot_ev"] for ch in report["channels"]])
            ot_per_card.append(card_ot_ev)
            voltage = report["voltage"]
            current = report["current"]

            # TODO: add a check if the card has been already shut down
            # and skip the shutdown if it has
            if shutdown_card_on_ot and card_ot_ev:
                self.cards[card_id].shutdown_all_loads()
                logger.warning(f"Card {card_id} shutdown due to over-temperature")

            # Update temperature history for steady state detection
            if elapsed_time is not None:
                for ch_ix, ch_data in enumerate(report["channels"]):
                    temp = ch_data["temperature"]
                    self._temp_history[card_id][ch_ix].append((elapsed_time, temp))

            # Check for steady state
            is_steady, temp_rates = self._check_steady_state(card_id, elapsed_time)
            steady_states[card_id] = {"is_steady": is_steady, "temp_rates": temp_rates}

            # if is_steady:
            #     print(
            #         f"Card {card_id} has reached steady state (temperature change ≤ 1K/minute)"
            #     )

            for ch_ix, ch_data in enumerate(report["channels"]):
                row = {
                    "elapsed_time": elapsed_time,
                    "card_serial": card_id,
                    "channel": ch_ix,
                    "temperature": ch_data["temperature"],
                    "load_power": ch_data["load_power"],
                    "ot_shutdown_t": ch_data["ot_shutdown"],
                    "ot_ev": ch_data["ot_ev"],
                    "voltage": voltage,
                    "current": current,
                    "steady_state": is_steady,
                    "temp_rate_per_min": temp_rates.get(ch_ix, None),
                }
                measurements.append(row)

        return ot_per_card, measurements, steady_states
