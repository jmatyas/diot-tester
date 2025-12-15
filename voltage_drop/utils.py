from voltage_drop.config import SLOT_OFFSET, SUPPLY_VOLTAGE, VOLTAGE_DIVIDER_RATIO


def slot_to_serial(slot: int, offset: int = SLOT_OFFSET) -> str:
    """Convert slot number to serial number.

    Args:
        slot: Slot number (1-8 typically)
        offset: Offset to apply (default 1 means slot 1 = DT01)

    Returns:
        Serial number string (e.g., "DT01")
    """
    serial_num = slot - 1 + offset
    if not 0 <= serial_num <= 8:
        raise ValueError(f"Slot {slot} with offset {offset} results in invalid serial")
    return f"DT0{serial_num}"


def serial_to_slot(serial: str, offset: int = SLOT_OFFSET) -> int:
    """Convert serial number to slot number.

    Args:
        serial: Serial number (e.g., "DT01")
        offset: Offset to apply

    Returns:
        Slot number
    """
    serial_num = int(serial[2:])
    return serial_num - offset + 1


def calculate_power_from_current(
    current_per_channel: float, voltage: float = SUPPLY_VOLTAGE
) -> float:
    """Calculate power per channel from current.

    Args:
        current_per_channel: Current in amperes
        voltage: Supply voltage in volts

    Returns:
        Power in watts
    """
    return voltage * current_per_channel


def calculate_current_from_power(
    power_per_channel: float, voltage: float = SUPPLY_VOLTAGE
) -> float:
    """Calculate current per channel from power.

    Args:
        power_per_channel: Power in watts
        voltage: Supply voltage in volts

    Returns:
        Current in amperes
    """
    return power_per_channel / voltage


def j3_to_rail_voltage(j3_voltage: float) -> float:
    """Convert J3 connector voltage reading to actual power rail voltage.

    Args:
        j3_voltage: Voltage measured at J3 connector

    Returns:
        Actual power rail voltage
    """
    return j3_voltage * VOLTAGE_DIVIDER_RATIO


def wait_for_user_confirmation(message: str) -> bool:
    """Display message and wait for user to press Enter.

    Args:
        message: Message to display

    Returns:
        True if user continued, False if cancelled
    """
    print("\n" + "=" * 80)
    print(message)
    print("=" * 80)
    try:
        input("Press Enter to continue (or Ctrl+C to abort)... ")
        return True
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.")
        return False
