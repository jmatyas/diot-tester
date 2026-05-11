# DIOT Tester

Thermal and electrical testing framework for DIOT PCB cards, with ground-bouncing
test support via ARTIQ on Kasli-DIOT + Fastino hardware.

## Prerequisites

- [Nix](https://nixos.org/download/) with flakes enabled

## Supported variants

The Makefile supports the following variants, selectable via `VARIANT=<name>` on the command line.
The default variant is `diot-tester-fastino`.

| VARIANT | Board | Description file | Fastino slots |
|---|---|---|---|
| `diot-tester-fastino` | Kasli-DIOT | `desc/kasli_diot_fastino.json` | DIOT slots 0–7 |
| `sinara-tester-fastino-low` | Kasli (Sinara) | `desc/kasli_fastino_low.json` | EEM ports 0, 1, 5, 6 |
| `sinara-tester-fastino-high` | Kasli (Sinara) | `desc/kasli_fastino_high.json` | EEM ports 1, 5, 6, 11 |

The two Sinara Kasli variants (`fastino-high` and `fastino-low`) exist because the full design with all Fastino cards did not fit into the FPGA on a standard Kasli board, so it was split across two separate builds covering different EEM port subsets.

> **Note:** Due tot he hardware bug on KasliDIOT, loading firmware (loading bitstream over USB without flashing) is only needed on **Kasli-DIOT** (`diot-tester-fastino`) once the board power is cycled. For the standard Sinara Kasli variants, the board must be fully reflashed using `make flash` once at the beginning of work, and does not need reloading every power cycle..

## Important files and locations

All of the built files are located in `build/<VARIANT>` directory (e.g. `build/diot-tester-fastino`). You can find there:
  - `gateware` directory with compiled binary file
  - `software` directory with compiled firmware and software files
  - `device_db.py` - automatically generated from the variant's descriptor file (e.g. `desc/kasli_diot_fastino.json` for the default variant); it's a file used by ARTIQ that contains system setup description (one can think of it as a sort of "device tree" - but it's a giant simplification)
  - `idle.elf` - a compiled `experiments/fastino_square.py` experiment that is put into the onboard flash memory; it is launched on Kasli whenever there is nothing else for it to do (i.e. no other experiment is taking place or scheduled to run)
  - `startup.elf` - it's similar to the `idle.elf`, but it's run only once and it's a hardware initialization procedure
  - `storage.img` - file containing some configs, such as device's IP address, `idle kernel` or `startup kernel`.
  - `experiments/fastino_square.py` - it's an ARTIQ experiment that can be launched on a KasliDIOT

## Environments

### Test / measurement environment (`nix develop`)

Provides Python with ARTIQ, matplotlib, PyVISA, and PyFTDI. Use this for running tests that require ARTIQ.

```bash
nix develop
python <scenario_that_relies_on_ARTIQ>
```

> **Note:** Gateware compilation (`make build`) is **not** supported in the
> Nix shell due to Rust toolchain constraints. Use the submodule environment for
> that (see below).

### Gateware build environment (submodules + direnv)

```bash
direnv allow        # adds submodule paths to PYTHONPATH (run once after cloning)
make build          # full build: gateware + device_db + kernels + storage image (default variant)
make build-storage  # compile kernels + storage image only (needs existing device_db.py)
make flash          # erase and flash gateware + firmware + storage, then load
make flash-storage  # erase and flash storage partition only, then load
make load           # load bitstream to FPGA over USB (no flash write)
```

All targets accept `VARIANT=<name>` to select a non-default variant:

```bash
make build          VARIANT=sinara-tester-fastino-high  # full build for the high variant
make build-storage  VARIANT=sinara-tester-fastino-high  # kernels + storage only
make flash          VARIANT=sinara-tester-fastino-high  # erase and flash gateware + firmware + storage, then load
make flash-storage  VARIANT=sinara-tester-fastino-high  # erase and flash storage partition only, then load
make load           VARIANT=sinara-tester-fastino-high  # load bitstream to FPGA over USB (no flash write)
```

## Python loader

`kasli_diot_utils.load()` wraps `artiq_flash` comamnds so a scenario script can
programmatically reload gateware between measurements:

```python
from kasli_diot_utils import load

load()                              # default variant: diot-tester-fastino
load(variant="my-custom-variant")   # override variant
```

This is equivalent to running `make load` from the shell and raises
`subprocess.CalledProcessError` on failure.

## Changes to the experiment

If one by any chance had to modify experiment (i.e. signal's amplitude or period), they can do that by modifying the `experiments/fastino_square.py` file. Important sections there are:
 - `self.half_period` - if one shortens it too much, a `RTIOUnderflow` exceptions is to be expected
 - `HIGH_VOLTAGE_VALUE` and `LOW_VOLTAGE_VALUE` variables

### Running experiment

Once you modify experiment, it's advised to test it before embedding it in the flash. To launch experiment, run:

```bash
artiq_run --device-db build/diot-tester-fastino/device_db.py experiments/fastino_square.py
```

Replace `diot-tester-fastino` with your chosen variant if needed.

Once you confirmed that it works and does what you expected of it, then you can embed it in the KasliDIOT's flash:

```bash
make build-storage
make flash-storage
```
After that, KasliDIOT will take some time (around 10-15 s) to boot and start your experiment.

> *It is advised to embed ARTIQ experiment in the device's flash, to avoid having to run it by hand every time*

## Hardware descriptor

Each variant has its own descriptor file in the `desc/` directory (see the table in [Supported variants](#supported-variants)).
The default (`diot-tester-fastino`) is described in `desc/kasli_diot_fastino.json`
(8× Fastino in DIOT slots 0–7).
