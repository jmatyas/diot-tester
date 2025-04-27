from diot.cards import DIOTCard
from diot.utils.ftdi_utils import find_serial_numbers


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
            # TODO:use regular expression to check if serial numbers are in the format "DTxx"
            # where xx is 0-8
            if not all(
                isinstance(serial, str) and serial.startswith("DT")
                for serial in serial_numbers
            ):
                raise ValueError("Serial numbers must be in the format 'DTxx'")

            serial_numbers = sorted(serial_numbers, key=lambda x: int(x[2:]))
        else:
            print("Serial numbers not provided. Searching for available cards...")
            discovered = find_serial_numbers()
            if not discovered:
                print("No DIOT cards (with DTxx serial numbers) found.")
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
            print(f"Card {serial} connected successfully")
        except (
            Exception
        ) as e:  # TODO: specify only one exception type - probably I2CNACK
            print(f"Failed to connect to card {serial}: {str(e)}")

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

    def set_card_load_power(self, serial: str, power: float):
        """Set the load power for a specific card evenly across all channels"""
        if serial not in self.cards:
            raise KeyError(f"Card with serial {serial} not found")
        card = self.cards[serial]
        if power > card.max_load_power:
            print(
                f"Power {power} W exceeds maximum load power {card.max_load_power} W"
            )
            print(
                f"Setting load power to maximum {card.max_load_power} W instead"
            )
            # raise ValueError(
            #     f"Power {power} W exceeds maximum load power {card.max_load_power} W"
            # )
            power = card.max_load_power
        power_per_channel = power / len(card.load_channels)
        card.set_all_load_power(power_per_channel)

    def report_cards(
        self, shutdown_card_on_ot: bool, elapsed_time: float | None = None
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
        combined_results = [
            card.report() for card in self.cards.values()
        ]
        soft_ot_status_per_card = [(report["card_serial"], report["ot_ev"]) for report in combined_results]

        for report in combined_results:
            card_id = report["card_serial"]
            card_ot_ev = report["ot_ev"]
            voltage = report["voltage"]
            current = report["current"]

            # TODO: add a check if the card has been already shut down
            # and skip the shutdown if it has
            # TODO: maybe use threading to add actual ot monitoring in software?
            if shutdown_card_on_ot and card_ot_ev:
                self.cards[card_id].shutdown_all_loads()
                print(f"Card {card_id} shutdown due to over-temperature")

            for ch_ix, ch_data in enumerate(report["channels"]):
                row = {
                    "elapsed_time": elapsed_time,
                    "card_serial": card_id,
                    "channel": ch_ix,
                    "temperature": ch_data["temperature"],
                    "load_power": ch_data["load_power"],
                    "ot_shutdown_t": ch_data["ot_shutdown"],
                    "ot_ev": card_ot_ev,
                    "voltage": voltage,
                    "current": current,
                }
                measurements.append(row)
        return soft_ot_status_per_card, measurements
