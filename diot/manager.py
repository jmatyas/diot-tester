import logging
import re

from diot.cards import DIOTCard
from diot.utils.ftdi_utils import find_serial_numbers

logger = logging.getLogger(__name__)


SECONDS_PER_BOARD = 1.2


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
            logger.error(f"Failed to connect to card {serial}: {str(e)}", exc_info=True)

    def get_card(self, serial: str) -> DIOTCard:
        """Get a specific card by serial number."""
        if serial not in self.cards:
            raise KeyError(f"Card with serial {serial} not found")
        return self.cards[serial]

    def get_all_cards(self) -> dict[str, DIOTCard]:
        """Get all connected cards."""
        return self.cards

    def shutdown_all_loads(self) -> None:
        """Turn off all loads on all cards."""
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
            logger.warning(f"Card {card_id} not found in history")
            return False, {}, {}

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
            debug_info = (
                f"Card {card_id} has not enough history data to check steady state"
                f" after {elapsed_time:.2f} seconds\n"
                f"\tlength of history (on single channel): {len(card_history[0])}\n"
                f"\tch_history[-1][0] - ch_history[0][0]: "
                f"{card_history[0][-1][0] - card_history[0][0][0]:.2f} seconds\n"
                f"\tmin history duration: {self._min_history_duration:.2f} seconds"
            )

            logger.debug(debug_info)
            return False, {}, {}

        # AVERAGE temperature change rate (K per minute) for each channel during
        # the last minute
        rates = {}
        channels_steady_state = {}

        window_start_idx = 0
        for ch_idx, ch_history in card_history.items():
            if ch_idx == 0:
                # we need to calculate this only for one channel, since we know
                # that all channels were measured at roughly the same time
                latest_time = ch_history[-1][0]
                window_start_time = latest_time - self._min_history_duration

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

            is_channel_steady = abs(rate_per_minute) <= self._steady_state_threshold
            channels_steady_state[ch_idx] = is_channel_steady
        is_steady = all(channels_steady_state.values())

        logger.debug(f"Card: {card_id} is in steady state: {is_steady}")
        logger.debug(f"\tsteady state per channel: {channels_steady_state}")

        return is_steady, channels_steady_state, rates

    def report_cards(
        self, shutdown_card_on_ot: bool = True, serials: list[str] | None = None
    ):
        # Don't move to numpy yet, as numpy arrays are less efficient for
        # appending data than lists. Even though we theoretically know the
        # number of measurements (duration / interval), we don't know how many
        # measurements will be taken before the shutdown event occurs (which
        # will break the loop). Moreove, we don't know how long will it take
        # to enumerate the cards and get the measurements, so we the number of
        # measurements is not known in advance.
        # See: https://github.com/numpy/numpy/issues/17090#issuecomment-674421168
        reports = []
        if serials is None:
            logger.debug("No serial numbers provided. Reporting all cards.")
            serials = self.cards.keys()
            logger.debug(f"Serial numbers: {serials}")
        # it looks like getting report from a single card takes just above 1 seconds
        # after all it's 18 temp channels and 2 ADCs using I2C over USB
        for sn in serials:
            r = self.cards[sn].report()
            reports.append(r)
            card_id = r["card_serial"]
            card_ot_ev = any([ch["ot_ev"] for ch in r["channels"]])

            if shutdown_card_on_ot and card_ot_ev:
                logger.warning(f"Card {card_id} shutdown due to over-temperature!")
                self.cards[card_id].shutdown_all_loads()

        return reports
