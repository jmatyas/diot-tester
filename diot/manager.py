from diot.cards import DIOTCard


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
            for serial in serial_numbers:
                self.add_card(serial, frequency, ot_shutdown, hysteresis)

    def add_card(
        self,
        serial: str,
        frequency: int = 100000,
        ot_shutdown: float = 80,
        hysteresis: float = 75,
    ) -> None:
        """Add a card to the mangager by serial number"""
        if not serial.startswith("DT"):
            raise ValueError("Serial number must start with 'DT'")

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

    def get_all_measurements(self) -> dict[str, dict]:
        """Get measurements from all cards"""
        measurements = {}
        for serial, card in self.cards.items():
            measurements[serial] = card.get_measurements()
        return measurements
