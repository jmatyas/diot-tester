#!/usr/bin/env python3
"""DIOT Lab - User-friendly interface for DIOT crate testing
---------------------------------------------------------

This module provides simplified interfaces for to use DIOT crates for testing.

Example usage:

    # Basic usage
    from diot_lab import DIOTLab

    # Initialize and connect to all available cards
    lab = DIOTLab()

    # Set up a test
    lab.setup_test("thermal_interference_test",
                   description="Testing thermal interference between channels")

    # Set loads on specific channels
    lab.set_channel_power("DT01", 3, 2.5)  # Card DT01, Channel 3, 2.5W
    lab.set_channel_power("DT01", 4, 2.5)  # Card DT01, Channel 4, 2.5W

    # Monitor for 5 minutes, logging data every 10 seconds
    lab.monitor(duration_minutes=5, interval_seconds=10)

    # Analyze results
    lab.show_temperature_plot()

    # Shutdown all loads when done
    lab.shutdown_all()
"""

import csv
import datetime
import json
import os
import time

from diot import DIOTCrateManager
from diot.utils.ftdi_utils import find_serial_numbers


class DIOTLab:
    """User-friendly interface for DIOT crate testing designed for physicists."""

    def __init__(self, card_serials: list[str] | None = None):
        """Initialize the DIOT Lab interface.

        Args:
            card_serials: Optional list of card serials to connect to.
                         If None, will auto-detect all available cards.

        """
        if card_serials is None:
            card_serials = find_serial_numbers()
        if not card_serials:
            print("No DIOT cards detected. Please check connections.")
            return
        self.crate = DIOTCrateManager(card_serials) if card_serials else None
        self.test_name = None
        self.test_description = None
        self.test_start_time = None
        self.log_data = []
        self.log_file = None
        self._create_output_directory()

    def _create_output_directory(self):
        """Create directory for storing test results if it doesn't exist"""
        self.output_dir = os.path.join(os.getcwd(), "diot_test_results")
        os.makedirs(self.output_dir, exist_ok=True)

    def setup_test(self, name: str, description: str = ""):
        """Set up a new test session with a name and description.

        Args:
            name: Name of the test (used for organizing data files)
            description: Optional description of the test purpose

        """
        self.test_name = name
        self.test_description = description
        self.test_start_time = datetime.datetime.now()
        timestamp = self.test_start_time.strftime("%Y%m%d_%H%M%S")

        # Create test directory and files
        test_dir = os.path.join(self.output_dir, f"{timestamp}_{name}")
        os.makedirs(test_dir, exist_ok=True)

        # Create CSV log file
        self.log_file = os.path.join(test_dir, "measurements.csv")
        with open(self.log_file, "w", newline="") as f:
            writer = csv.writer(f)
            header = [
                "timestamp",
                "card",
                "channel",
                "temperature",
                "load_power",
                "hysteresis",
                "ot_shutdown",
                "voltage",
                "current",
            ]
            writer.writerow(header)

        # Save test metadata
        metadata_file = os.path.join(test_dir, "test_info.json")
        metadata = {
            "test_name": name,
            "description": description,
            "start_time": timestamp,
            "cards": list(self.crate.get_all_cards().keys()) if self.crate else [],
        }
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        print(f"Test '{name}' set up. Data will be saved to {test_dir}")
        self.test_dir = test_dir
        return test_dir

    def set_channel_power(self, card_serial: str, channel: int, power: float) -> bool:
        """Set the load power for a specific channel on a specific card.

        Args:
            card_serial: Serial number of the card (e.g., "DT01")
            channel: Channel number (0-16)
            power: Power in Watts

        Returns:
            True if successful, False otherwise

        """
        if not self.crate:
            print("No DIOT cards are connected. Cannot set power.")
            return False

        try:
            card = self.crate.get_card(card_serial)
            ch = card.get_channel(channel)
            ch.load_power = power
            print(f"Set card {card_serial}, channel {channel} to {power}W")
            return True
        except Exception as e:
            print(f"Failed to set power: {e}")
            return False

    def set_card_power(self, card_serial: str, power: float) -> bool:
        """Set the same load power for all channels on a specific card.

        Args:
            card_serial: Serial number of the card (e.g., "DT01")
            power: Power in Watts for all channels

        Returns:
            True if successful, False otherwise

        """
        if not self.crate:
            print("No DIOT cards are connected. Cannot set power.")
            return False

        try:
            card = self.crate.get_card(card_serial)
            card.set_all_load_power(power)
            print(f"Set all channels on card {card_serial} to {power}W")
            return True
        except Exception as e:
            print(f"Failed to set power: {e}")
            return False

    def set_gradient_power(
        self, card_serial: str, start_power: float, end_power: float
    ) -> bool:
        """Set a power gradient across all channels of a card.

        Args:
            card_serial: Serial number of the card (e.g., "DT01")
            start_power: Power for the first channel
            end_power: Power for the last channel

        Returns:
            True if successful, False otherwise

        """
        if not self.crate:
            print("No DIOT cards are connected. Cannot set power.")
            return False

        try:
            card = self.crate.get_card(card_serial)
            num_channels = len(card.load_channels)

            # Calculate power step between channels
            power_step = (
                (end_power - start_power) / (num_channels - 1)
                if num_channels > 1
                else 0
            )

            # Set power for each channel
            for i in range(num_channels):
                channel_power = start_power + (i * power_step)
                card.get_channel(i).load_power = channel_power

            print(
                f"Set power gradient on card {card_serial} from {start_power}W to {end_power}W"
            )
            return True
        except Exception as e:
            print(f"Failed to set power gradient: {e}")
            return False

    def shutdown_all(self) -> None:
        """Turn off all loads on all cards"""
        if self.crate:
            self.crate.shutdown_all_loads()
            print("All loads shut down.")

    def get_temperatures(self, card_serial: str = None) -> dict[str, list[float]]:
        """Get current temperature readings for all channels on specified card(s).

        Args:
            card_serial: Optional card serial to get temps from. If None, get from all cards.

        Returns:
            Dictionary mapping card serials to lists of channel temperatures

        """
        temps = {}

        if self.crate:
            if card_serial:
                cards = {card_serial: self.crate.get_card(card_serial)}
            else:
                cards = self.crate.get_all_cards()

            for serial, card in cards.items():
                temps[serial] = [ch.temperature for ch in card.load_channels]

        return temps

    def log_measurements(self) -> None:
        """Log a snapshot of all measurements to the CSV file."""
        if not self.log_file or not self.crate:
            print("Cannot log measurements: No active test or no connected cards.")
            return

        timestamp = datetime.datetime.now().isoformat()
        measurements = []

        for card_serial, card in self.crate.get_all_cards().items():
            voltage = card.voltage
            current = card.current

            for i, channel in enumerate(card.load_channels):
                row = {
                    "timestamp": timestamp,
                    "card": card_serial,
                    "channel": i,
                    "temperature": channel.temperature,
                    "load_power": channel.load_power,
                    "hysteresis": channel.hysteresis,
                    "ot_shutdown": channel.ot_shutdown,
                    "voltage": voltage,
                    "current": current,
                }
                measurements.append(row)

                # Append to CSV
                with open(self.log_file, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            timestamp,
                            card_serial,
                            i,
                            channel.temperature,
                            channel.load_power,
                            channel.hysteresis,
                            channel.ot_shutdown,
                            voltage,
                            current,
                        ]
                    )

        self.log_data.extend(measurements)
        return measurements

    def monitor(
        self,
        duration_minutes: float | None = None,
        interval_seconds: float = 5.0,
        max_temp: float = 75.0,
        display_output: bool = True,
    ) -> None:
        """Monitor the DIOT crate, logging measurements for a specified duration.

        Args:
            duration_minutes: How long to monitor (minutes). If None, runs until Ctrl+C.
            interval_seconds: Time between measurements (seconds)
            max_temp: Maximum safe temperature (will shutdown channel if exceeded)
            display_output: Whether to display readings in the terminal

        """
        if not self.crate:
            print("No DIOT cards connected. Cannot monitor.")
            return

        start_time = time.time()
        end_time = start_time + (duration_minutes * 60) if duration_minutes else None

        try:
            print(
                f"Starting monitoring{f' for {duration_minutes} minutes' if duration_minutes else ''}..."
            )
            print("Press Ctrl+C to stop.")

            iteration = 0
            while True:
                iteration += 1
                current_time = time.time()

                # Log data
                self.log_measurements()

                # Display current status if requested
                if display_output:
                    os.system("cls" if os.name == "nt" else "clear")
                    elapsed = current_time - start_time
                    print(f"DIOT Crate Monitoring - Test: {self.test_name}")
                    print(f"Elapsed: {int(elapsed // 60)}m {int(elapsed % 60):02d}s")
                    print("-" * 60)

                    for serial, card in self.crate.get_all_cards().items():
                        print(
                            f"\nCard: {serial}  |  V: {card.voltage:.2f}V  |  I: {card.current:.3f}A"
                        )
                        print("-" * 60)
                        print("CH |  Temp   |  Power  | Status")
                        print("-" * 30)

                        for i, channel in enumerate(card.load_channels):
                            temp = channel.temperature
                            status = "OK"
                            if temp > max_temp:
                                status = "HOT!"
                                # Shut down if over maximum temperature
                                channel.load_power = 0

                            print(
                                f"{i:2d} | {temp:6.1f}°C | {channel.load_power:5.2f}W | {status}"
                            )

                            if i == 15:  # Add separator before aux channel
                                print("-" * 30)

                # Check if we've reached the duration
                if end_time and current_time >= end_time:
                    print("\nMonitoring duration completed.")
                    break

                # Sleep until next interval
                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")

    def show_temperature_plot(
        self, card_serial: str = None, channels: list[int] | None = None
    ) -> None:
        """Display a plot of temperature over time from the logged data.

        Args:
            card_serial: Optional specific card to plot. If None, plots all cards.
            channels: Optional list of specific channels to plot. If None, plots all.

        """
        if not self.log_data:
            print("No data available to plot.")
            return

        try:
            import matplotlib.pyplot as plt

            # Filter data if needed
            filtered_data = self.log_data
            if card_serial:
                filtered_data = [
                    row for row in filtered_data if row["card"] == card_serial
                ]

            if channels:
                filtered_data = [
                    row for row in filtered_data if row["channel"] in channels
                ]

            # Group by card and channel
            data_by_card_channel = {}
            for row in filtered_data:
                card = row["card"]
                channel = row["channel"]
                key = f"{card}-CH{channel}"

                if key not in data_by_card_channel:
                    data_by_card_channel[key] = {
                        "timestamps": [],
                        "temperatures": [],
                        "powers": [],
                    }

                # Convert ISO timestamp to datetime
                ts = datetime.datetime.fromisoformat(row["timestamp"])
                data_by_card_channel[key]["timestamps"].append(ts)
                data_by_card_channel[key]["temperatures"].append(row["temperature"])
                data_by_card_channel[key]["powers"].append(row["load_power"])

            # Create plot with two y-axes
            fig, ax1 = plt.subplots(figsize=(12, 6))
            ax2 = ax1.twinx()

            # Plot temperatures on left y-axis
            for key, data in data_by_card_channel.items():
                ax1.plot(
                    data["timestamps"],
                    data["temperatures"],
                    "-",
                    label=f"{key} Temperature",
                )

            # Plot powers on right y-axis
            for key, data in data_by_card_channel.items():
                ax2.plot(
                    data["timestamps"],
                    data["powers"],
                    "--",
                    alpha=0.7,
                    label=f"{key} Power",
                )

            # Add labels and legend
            ax1.set_xlabel("Time")
            ax1.set_ylabel("Temperature (°C)")
            ax2.set_ylabel("Power (W)")

            ax1.legend(loc="upper left")
            ax2.legend(loc="upper right")

            plt.title(f"DIOT Crate Test: {self.test_name}")
            plt.grid(True)

            # Save plot
            if self.test_dir:
                plot_file = os.path.join(self.test_dir, "temperature_plot.png")
                plt.savefig(plot_file)
                print(f"Plot saved to {plot_file}")

            plt.show()

        except ImportError:
            print(
                "Matplotlib is required for plotting. Install with: pip install matplotlib"
            )

    def export_data(self, format: str = "csv") -> str:
        """Export the current test data to a file.

        Args:
            format: Format to export ("csv" or "json")

        Returns:
            Path to the exported file

        """
        if not self.log_data or not self.test_dir:
            print("No data available to export or no active test.")
            return None

        if format.lower() == "json":
            export_file = os.path.join(self.test_dir, "measurements.json")
            with open(export_file, "w") as f:
                json.dump(self.log_data, f, indent=2)
        else:
            # CSV is already being written during logging
            export_file = self.log_file

        print(f"Data exported to {export_file}")
        return export_file


def run_example_test():
    """Run a simple example test to demonstrate functionality"""
    print("Running example DIOT crate test...")

    # Initialize lab
    lab = DIOTLab()

    # Set up test
    lab.setup_test("example_test", "Demonstration of DIOT Lab functionality")

    # Get connected cards
    cards = lab.crate.get_all_cards() if lab.crate else {}

    if not cards:
        print("No cards detected. Cannot run example test.")
        return

    # Use the first card for demonstration
    card_serial = list(cards.keys())[0]
    print(f"Using card {card_serial} for demonstration")

    # Set up a gradient of power across channels
    for ch in range(3):
        lab.set_channel_power(card_serial, ch, 3.0)

        # Monitor for 1 minute
        lab.monitor(duration_minutes=0.25, interval_seconds=5)

        # Plot the results
        try:
            lab.show_temperature_plot()
        except Exception as e:
            print(f"Could not generate plot: {e}")

        # Shutdown all loads when done
        lab.shutdown_all()
    print("Example test complete!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="DIOT Lab - User-friendly interface for DIOT crate testing"
    )
    parser.add_argument("--example", action="store_true", help="Run an example test")
    parser.add_argument(
        "--interactive", action="store_true", help="Start interactive mode"
    )

    args = parser.parse_args()

    if args.example:
        run_example_test()
    elif args.interactive:
        # Simple interactive mode for physicists
        print("DIOT Lab Interactive Mode")
        print("-------------------------")
        lab = DIOTLab()

        # Find available cards
        cards = lab.crate.get_all_cards() if lab.crate else {}
        if not cards:
            print("No DIOT cards detected. Please check connections.")
            exit(1)

        print(f"Found {len(cards)} DIOT cards: {', '.join(cards.keys())}")

        # Get test name
        test_name = input("Enter a name for this test session: ")
        desc = input("Enter a description (optional): ")
        lab.setup_test(test_name, desc)

        while True:
            print("\nDIOT Lab Menu:")
            print("1. Set load power for a channel")
            print("2. Set same power for all channels")
            print("3. Create power gradient across channels")
            print("4. Monitor temperatures")
            print("5. Show temperature plot")
            print("6. Shutdown all loads")
            print("7. Exit")

            choice = input("\nEnter your choice (1-7): ")

            if choice == "1":
                card = input(f"Enter card serial ({', '.join(cards.keys())}): ")
                channel = int(input("Enter channel number (0-16): "))
                power = float(input("Enter power in Watts: "))
                lab.set_channel_power(card, channel, power)

            elif choice == "2":
                card = input(f"Enter card serial ({', '.join(cards.keys())}): ")
                power = float(input("Enter power in Watts: "))
                lab.set_card_power(card, power)

            elif choice == "3":
                card = input(f"Enter card serial ({', '.join(cards.keys())}): ")
                start = float(input("Enter starting power in Watts: "))
                end = float(input("Enter ending power in Watts: "))
                lab.set_gradient_power(card, start, end)

            elif choice == "4":
                duration = input(
                    "Enter monitoring duration in minutes (leave empty for continuous): "
                )
                interval = float(
                    input("Enter interval between readings in seconds (default 5): ")
                    or "5"
                )

                if duration.strip():
                    lab.monitor(
                        duration_minutes=float(duration), interval_seconds=interval
                    )
                else:
                    lab.monitor(duration_minutes=None, interval_seconds=interval)

            elif choice == "5":
                lab.show_temperature_plot()

            elif choice == "6":
                lab.shutdown_all()
                print("All loads shut down.")

            elif choice == "7":
                lab.shutdown_all()
                print("Exiting DIOT Lab. Goodbye!")
                break

            else:
                print("Invalid choice. Please enter a number between 1 and 7.")
    else:
        print("DIOT Lab - User-friendly interface for DIOT crate testing")
        print("Run with --example to see a demonstration")
        print("Run with --interactive to start interactive mode")
