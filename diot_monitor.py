import argparse
import logging
from pathlib import Path

from diot import DIOTCrateManager, MonitoringSession
from diot.utils.ftdi_utils import find_serial_numbers

DEFAULT_START_CARD = 0
DEFAULT_N_CARDS = 9
DEFAULT_OT_SHUTDOWN = 85.0
DEFAULT_HYSTERESIS = 80.0

DEFAULT_DURATION_MIN = 10.0
DEFAULT_INTERVAL = 1.0

DEFAULT_RESULTS_DIR = "results"


def setup_logging(debug: bool = False, name: str | None = None) -> logging.Logger:
    console_level = logging.DEBUG if debug else logging.INFO
    logger = logging.getLogger()
    if name is None:
        name = "monitor_app"
    logger.name = name
    log_file = f"{name}.log"

    if Path(log_file).exists():
        # if {log_file}.old exists, it will be replaced silently
        Path(log_file).rename(f"{log_file}.old")

    logger.setLevel(logging.DEBUG)

    # TODO: add rotating file handler
    fh = logging.FileHandler(log_file, mode="w")
    fh.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(console_level)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.debug("Logging initialized")
    return logger


def list_available_cards():
    serial_numbers = sorted(find_serial_numbers(), key=lambda x: int(x[2:]))
    if not serial_numbers:
        return []

    print(f"Found {len(serial_numbers)} DIOT cards:")
    for sn in serial_numbers:
        print(f"  - {sn}")
    return serial_numbers


def query_card_status(crate_manager: DIOTCrateManager, card_serial: str | None = None):
    cards = {}
    if card_serial:
        if card_serial not in crate_manager.cards:
            print(f"Card {card_serial} not found in crate manager.")
            return
        cards[card_serial] = crate_manager.get_card(card_serial)
    else:
        cards = crate_manager.get_all_cards()

    for serial, card in cards.items():
        print(f"Card {serial}:")
        print(f"Voltage: {card.voltage:.2f} V")
        print(f"Current: {card.current:.2f} A")
        print("Temperatures:")

        # Last channel one on the card is the 3V3 load channel, so skip it
        for i, channel in enumerate(card.load_channels[:-1]):
            if i % 4 == 0 and i > 0:
                print()
            print(
                f"CH{i}: {channel.temperature:.1f}°C ({channel.load_power:.2f}W) ",
                end="",
            )
        print("\n")


def monitor_cards(crate_manager: DIOTCrateManager, args: argparse.Namespace):
    logger = logging.getLogger("monitor_app")
    duration = args.duration * 60  # Convert minutes to seconds

    power_str = str(args.card_power).replace(".", "W")
    session_name = args.session_name if args.session_name else f"monitor_{power_str}"

    monitor_session = MonitoringSession(
        crate_manager, save_dir=args.results_dir, session_name=session_name
    )

    serial_numbers = list(crate_manager.cards.keys())
    if args.start_card < len(serial_numbers) and args.n_cards > 0:
        serials_to_monitor = serial_numbers[
            args.start_card : args.start_card + args.n_cards
        ]
    else:
        logger.warning(
            f"Invalid start card index {args.start_card} or number of cards {args.n_cards}. Monitoring all available cards."
        )
        serials_to_monitor = serial_numbers

    crate_manager.set_cards_load_power(serials_to_monitor, args.card_power)
    logger.info(f"Set cards: {serials_to_monitor} power to: {args.card_power} W")

    try:
        # args.wait_for_steady overrides args.no_shutdown and will shut down all loads
        # after the first monitoring session and wait for steady state to be reached
        elapsed_time = monitor_session.monitor(
            duration=duration,
            interval=args.interval,
            shutdown_at_end=not args.no_shutdown or args.wait_for_steady,
            stop_on_steady_state=args.stop_on_steady,
            stop_on_ot=not args.continue_on_ot,
            save_every_iteration=True,
            serials_to_monitor=serials_to_monitor,
        )
        logger.info("Monitoring session completed successfully.")

        if args.wait_for_steady:
            logger.info(
                "Waiting for steady state to be reached after monitoring session..."
            )
            session_name = session_name + "_cooldown"
            monitor_session = MonitoringSession(
                crate_manager, save_dir=args.results_dir, session_name=session_name
            )
            # TODO: maybe add a new session name for the second monitoring session?
            # and add a new file to the results dir?
            monitor_session.monitor(
                duration=duration * 2,
                interval=args.interval,
                stop_on_steady_state=True,
                stop_on_ot=not args.continue_on_ot,
                save_every_iteration=True,
                serials_to_monitor=serials_to_monitor,
                start_time=elapsed_time,
            )
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
        if not args.no_shutdown:
            crate_manager.shutdown_all_loads()
            logger.info("All loads shut down")
    except Exception as e:
        logger.error(f"Error during monitoring: {e}", exc_info=True)
        if not args.no_shutdown:
            crate_manager.shutdown_all_loads()
            logger.info("All loads shut down due to error")
    finally:
        if args.no_shutdown:
            logger.info("Loads left running (--no-shutdown option)")
        else:
            crate_manager.shutdown_all_loads()
            logger.info("All loads shut down")


def get_parser():
    parser = argparse.ArgumentParser(description="DIOT Crate Monitoring Tool")
    subparsers = parser.add_subparsers(dest="command")

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging"
    )

    _list_parser = subparsers.add_parser(
        "list", parents=[parent_parser], help="List available DIOT cards"
    )

    status_parser = subparsers.add_parser(
        "status", parents=[parent_parser], help="Query status of DIOT cards"
    )
    status_parser.add_argument(
        "--card", type=str, help="Serial number of the card to query", default=None
    )

    monitor_parser = subparsers.add_parser(
        "monitor", parents=[parent_parser], help="Start monitoring session"
    )
    monitor_parser.add_argument(
        "--start-card",
        type=int,
        default=DEFAULT_START_CARD,
        help=f"Index of first card to monitor (default: {DEFAULT_START_CARD})",
    )
    monitor_parser.add_argument(
        "--n-cards",
        type=int,
        default=DEFAULT_N_CARDS,
        help=f"Number of cards to monitor (default: {DEFAULT_N_CARDS})",
    )
    monitor_parser.add_argument(
        "--ot-shutdown",
        type=float,
        default=DEFAULT_OT_SHUTDOWN,
        help=f"Over-temperature shutdown threshold in °C (default: {DEFAULT_OT_SHUTDOWN})",
    )
    monitor_parser.add_argument(
        "--hysteresis",
        type=float,
        default=DEFAULT_HYSTERESIS,
        help=f"Hysteresis temperature in °C (default: {DEFAULT_HYSTERESIS})",
    )
    monitor_parser.add_argument(
        "--card-power",
        type=float,
        default=0.0,
        help="Card power to set in W (default: 0.0 W)",
    )
    monitor_parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION_MIN,
        help=f"Monitoring duration in minutes (default: {DEFAULT_DURATION_MIN})",
    )
    monitor_parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"Monitoring interval in seconds (default: {DEFAULT_INTERVAL})",
    )
    monitor_parser.add_argument(
        "--results-dir",
        default=DEFAULT_RESULTS_DIR,
        help=f"Directory for saving results (default: {DEFAULT_RESULTS_DIR})",
    )
    monitor_parser.add_argument(
        "--session-name",
        default=None,
        help="Session name for result files (default: auto-generated based on timestamp)",
    )
    monitor_parser.add_argument(
        "--no-shutdown",
        action="store_true",
        help="Do not shut down loads when monitoring completes",
    )
    monitor_parser.add_argument(
        "--stop-on-steady",
        action="store_true",
        help="Stop monitoring when steady state is reached",
    )
    monitor_parser.add_argument(
        "--continue-on-ot",
        action="store_true",
        help="Stop monitoring on over-temperature event",
    )
    monitor_parser.add_argument(
        "--wait-for-steady",
        action="store_true",
        help=(
            "Wait for steady state AFTER the monitoring session - this overrides"
            " --no-shutdown option and will shut down all loads after the first"
            " monitoring session and wait for steady state to be reached"
        ),
    )

    set_load_power_parser = subparsers.add_parser(
        "set-load-power",
        parents=[parent_parser],
        help="Set load power for a card or channel",
    )
    set_load_power_parser.add_argument("card", help="Serial number of the card")
    set_load_power_parser.add_argument(
        "--channel", help="Channel number (omit to set on all channels)"
    )
    set_load_power_parser.add_argument("power", type=float, help="Load power in W")

    _shutdown_parser = subparsers.add_parser(
        "shutdown", parents=[parent_parser], help="Shutdown all cards"
    )

    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()

    logger = setup_logging(getattr(args, "debug", False))
    # logger = logging.getLogger("monitor_app")
    logger.info("Starting DIOT monitoring tool")
    logger.debug(f"Arguments: {args}")

    if not args.command:
        parser.print_help()
        return

    if args.command == "list":
        list_available_cards()
        return

    available_cards = list_available_cards()
    if not available_cards:
        logger.error("No DIOT cards found.")
        return

    if args.command == "monitor":
        crate_manager = DIOTCrateManager(
            serial_numbers=available_cards,
            ot_shutdown=args.ot_shutdown,
            hysteresis=args.hysteresis,
        )
    else:
        crate_manager = DIOTCrateManager(
            serial_numbers=available_cards,
            ot_shutdown=DEFAULT_OT_SHUTDOWN,
            hysteresis=DEFAULT_HYSTERESIS,
        )

    if args.command == "status":
        logger.info("Querying status of DIOT cards...")
        query_card_status(crate_manager, args.card)

    elif args.command == "monitor":
        monitor_cards(crate_manager, args)

    elif args.command == "set-load-power":
        try:
            card = crate_manager.get_card(args.card)
            if args.channel is not None:
                # Load power ONLY for a specific channel
                channel = int(args.channel)
                if channel < 0 or channel >= len(card.load_channels):
                    logger.error(f"Invalid channel number {channel}.")
                    return
                card.load_channels[channel].load_power = args.power
                logger.info(
                    f"Set load power of card {args.card} channel {channel} to {args.power} W"
                )
            else:
                # Load power for EACH channel on the card
                card.set_all_load_power(args.power)
                logger.info(f"Set card {args.card} channels power to {args.power} W")
        except Exception as e:
            logger.error(f"Error setting load power: {e}")

    elif args.command == "shutdown":
        logger.info("Shutting down all cards...")
        crate_manager.shutdown_all_loads()
        logger.info("All cards shut down.")


if __name__ == "__main__":
    main()
