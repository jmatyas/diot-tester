# =============================================================================
# Configuration Constants
# =============================================================================

# Slot to Serial Number Mapping
# By default: Slot 1 = DT01, Slot 2 = DT02, ..., Slot 8 = DT08
# Slot 0 (DT00) is typically the controller and not included in measurements
SLOT_OFFSET = 1  # Set to 0 if Slot 1 should be DT00

# Load Configuration
# Each card has 16 channels, each channel max ~5W from 12V
# Power = V * I, so I = P / V
# For 12V: 0.125A → ~1.5W per channel, 0.25A → 3W per channel
CHANNEL_COUNT = 16  # Number of load channels per card (excluding auxiliary)
SUPPLY_VOLTAGE = 12.0  # Nominal supply voltage in volts

# Load currents to test (per channel)
LOAD_CURRENT_2A = 0.125  # Amperes per channel (2A total)
LOAD_CURRENT_4A = 0.25  # Amperes per channel (4A total)

# Calculated powers (P = V * I)
LOAD_POWER_2A = SUPPLY_VOLTAGE * LOAD_CURRENT_2A  # ~1.5W per channel
LOAD_POWER_4A = SUPPLY_VOLTAGE * LOAD_CURRENT_4A  # ~3.0W per channel

# DMM Configuration
DMM_VOLTAGE_RANGE = 10.0
DMM_NPLC = 1.0  # Integration time in power line cycles
DMM_AVERAGE_COUNT = 10  # Number of measurements to average
DMM_TIMEOUT = 10  # Seconds

# Timing Configuration
SETTLING_TIME = 0.5  # Seconds to wait after applying load before measurement

# Test Matrix: Slot pairs to test (slot_A, slot_B)
# slot_A will have loads applied, slot_B monitors crosstalk
TEST_SLOT_PAIRS = [
    (1, 2),
    (2, 3),
    (3, 4),
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 8),  # Adjacent pairs
    (1, 4),
    (1, 8),
    (4, 8),  # Non-adjacent pairs
]

# J3 Voltage Divider Ratio
# J3 measures power rail via 1kΩ/10.1kΩ divider
# V_J3 = V_rail * (1.0 / 11.1)
VOLTAGE_DIVIDER_RATIO = 11.1  # Converts J3 reading to actual rail voltage
