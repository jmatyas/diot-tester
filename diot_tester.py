import argparse
import os
import time
from diot import DIOTCrateManager
from diot.utils.ftdi_utils import find_serial_numbers


def main():
    """Simple command-line interface for DIOT crate testing.
    Designed to be easy to use for physicists with minimal programming knowledge.
    """
    # Create argument parser for command line interface
    parser = argparse.ArgumentParser(description="DIOT Crate Testing Tool")

    # Basic commands
    parser.add_argument(
        "--list-cards", action="store_true", help="List all available DIOT cards"
    )
    parser.add_argument(
        "--monitor", action="store_true", help="Monitor temperatures and voltages"
    )
    parser.add_argument(
        "--set-load",
        nargs=3,
        metavar=("CARD", "CHANNEL", "POWER"),
        help="Set load power for a specific channel (e.g., DT01 5 1.5)",
    )
    parser.add_argument(
        "--set-all",
        nargs=2,
        metavar=("CARD", "POWER"),
        help="Set same load power for all channels on a card (e.g., DT01 1.5)",
    )
    parser.add_argument("--shutdown", action="store_true", help="Shutdown all loads")
    parser.add_argument(
        "--set-ot-threshold",
        nargs=3,
        metavar=("CARD", "CHANNEL", "TEMP"),
        help="Set over-temperature threshold for a channel (e.g., DT01 5 85)",
    )
    parser.add_argument(
        "--set-hysteresis",
        nargs=3,
        metavar=("CARD", "CHANNEL", "TEMP"),
        help="Set temperature hysteresis for a channel (e.g., DT01 5 75)",
    )

    args = parser.parse_args()

    # Default to list if no args provided
    if len(os.sys.argv) == 1:
        print("DIOT Crate Testing Tool")
        print("----------------------")
        print("Available commands:")
        print("  --list-cards           : List all available DIOT cards")
        print("  --monitor              : Monitor temperatures and voltages")
        print("  --set-load CARD CH POW : Set load power for a specific channel")
        print("  --set-all CARD POW     : Set same load power for all channels")
        print("  --shutdown             : Shutdown all loads")
        print("  --set-ot-threshold CARD CH TEMP : Set over-temperature threshold")
        print("  --set-hysteresis CARD CH TEMP   : Set temperature hysteresis")
        print("\nFor more detailed information, run: python diot_tester.py --help")
        return

    available_cards = find_serial_numbers()
    if not available_cards:
        print("No DIOT cards (with DTxx serial numbers) found.")
        return
    available_cards = sorted(available_cards, key=lambda x: int(x[2:]))

    # List cards if requested
    if args.list_cards:
        print(f"Found {len(available_cards)} DIOT cards:")
        for serial in available_cards:
            print(f"  - Card: {serial}")
        return

    # Create the crate manager with all available cards
    crate = DIOTCrateManager(available_cards)

    # Set load power for a specific channel
    if args.set_load:
        card_serial, channel_str, power_str = args.set_load
        try:
            channel = int(channel_str)
            power = float(power_str)
            card = crate.get_card(card_serial)
            channel_obj = card.get_channel(channel)
            channel_obj.load_power = power
            print(
                f"Set load power for card {card_serial}, channel {channel} to {power} W"
            )
        except Exception as e: # FIXME
            print(f"Error setting load power: {str(e)}")

    # Set load power for all channels on a card
    if args.set_all:
        card_serial, power_str = args.set_all
        try:
            power = float(power_str)
            card = crate.get_card(card_serial)
            card.set_all_load_power(power)
            print(f"Set all channels on card {card_serial} to {power} W")
        except Exception as e: # FIXME
            print(f"Error setting load power: {str(e)}")

    # Shutdown all loads
    if args.shutdown:
        crate.shutdown_all_loads()
        print("All loads shut down.")

    # Set over-temperature threshold
    if args.set_ot_threshold:
        card_serial, channel_str, temp_str = args.set_ot_threshold
        try:
            channel = int(channel_str)
            temp = float(temp_str)
            card = crate.get_card(card_serial)
            channel_obj = card.get_channel(channel)
            channel_obj.ot_shutdown = temp
            print(
                f"Set OT threshold for card {card_serial}, channel {channel} to {temp}°C"
            )
        except Exception as e: # FIXME
            print(f"Error setting OT threshold: {str(e)}")

    # Set temperature hysteresis
    if args.set_hysteresis:
        card_serial, channel_str, temp_str = args.set_hysteresis
        try:
            channel = int(channel_str)
            temp = float(temp_str)
            card = crate.get_card(card_serial)
            channel_obj = card.get_channel(channel)
            channel_obj.hysteresis = temp
            print(
                f"Set hysteresis for card {card_serial}, channel {channel} to {temp}°C"
            )
        except Exception as e: # FIXME
            print(f"Error setting hysteresis: {str(e)}")

    # Monitor temperatures and voltages
    if args.monitor:
        try:
            print("Monitoring DIOT crate. Press Ctrl+C to stop.")
            print("---------------------------------------")
            while True:
                for serial, card in crate.get_all_cards().items():
                    print(f"\nCard: {serial}")
                    print(f"Voltage: {card.voltage:.3f} V")
                    print(f"Current: {card.current:.3f} A")
                    print("Temperatures:")

                    for i, channel in enumerate(card.load_channels):
                        if i % 4 == 0 and i > 0:
                            print()  # Add newline every 4 channels for readability
                        print(
                            f"CH{i}: {channel.temperature:.1f}°C ({channel.load_power:.2f}W) ",
                            end="",
                        )
                    print("\n")

                time.sleep(1)
                # Clear screen for next update
                print("\033c", end="")
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")


if __name__ == "__main__":
    main()
