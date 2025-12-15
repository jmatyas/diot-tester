from dataclasses import dataclass, field


@dataclass
class MeasurementPoint:
    """Single voltage measurement with metadata."""

    voltage: float  # raw DMM reading from J3
    voltage_rail: float  # calculated power rail voltage
    std_dev: float  # Standard deviation of averaged measurement
    load_condition: str  # "no_load", "2A", "4A"
    dmm_id: str  # "DMM1" or "DMM2"


@dataclass
class SlotPairMeasurement:
    """Complete measurement set for a slot pair."""

    slot_a: int
    slot_b: int
    serial_a: str
    serial_b: str
    timestamp: str

    # DMM1 measurements (on slot_a)
    dmm1_baseline: MeasurementPoint | None = None
    dmm1_2a_load: MeasurementPoint | None = None
    dmm1_4a_load: MeasurementPoint | None = None

    # DMM2 measurements (on slot_b)
    dmm2_baseline: MeasurementPoint | None = None
    dmm2_2a_load: MeasurementPoint | None = None
    dmm2_4a_load: MeasurementPoint | None = None

    # Calculated results
    voltage_drop_2a: float | None = None  # V_baseline - V_2A on slot_a
    voltage_drop_4a: float | None = None  # V_baseline - V_4A on slot_a
    rail_resistance_2a: float | None = None  # ΔV / ΔI for 2A
    rail_resistance_4a: float | None = None  # ΔV / ΔI for 4A
    crosstalk_2a: float | None = None  # Voltage change on slot_b when slot_a at 2A
    crosstalk_4a: float | None = None  # Voltage change on slot_b when slot_a at 4A

    # Status flags
    success: bool = True
    error_message: str | None = None


@dataclass
class TestResults:
    """Complete test results for all slot pairs."""

    test_name: str
    start_time: str
    end_time: str | None = None
    configuration: dict = field(default_factory=dict)
    measurements: list[SlotPairMeasurement] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
