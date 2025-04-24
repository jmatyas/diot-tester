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
