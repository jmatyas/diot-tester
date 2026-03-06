# DIOT Tester

Thermal and electrical testing framework for DIOT PCB cards, with ground-bouncing
test support via ARTIQ on Kasli-DIOT + Fastino hardware.

## Prerequisites

- [Nix](https://nixos.org/download/) with flakes enabled

## Important files and locations

All of the built files are located in `build/diot-tester-fastino` directory. You can find there:
  - `gateware` directory with compiled binary file
  - `software` directory with compiled firmware and software files
  - `device_db.py` - the one that is automatically generated from `desc/kasli_diot_fastino.json`; it's a file used by ARTIQ that contains system setup description (one can think of it as a sort of "device tree" - but it's an giant simplification)
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
make build          # full build: gateware + device_db + kernels + storage image
make build-storage  # compile kernels + storage image only (needs existing device_db.py)
make flash          # erase and flash gateware + firmware + storage, then load
make flash-storage  # erase and flash storage partition only, then load
make load           # load bitstream to FPGA over USB (no flash write)
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

Once you confirmed that it works and does what you expected of it, then you can embed it in the KasliDIOT's flash:

```bash
make build-storage
make flash-storage
```
After that, KasliDIOT will take some time (around 10-15 s) to boot and start your experiment.

> *It is advised to embed ARTIQ experiment in the device's flash, to avoid having to run it by hand every time*

## Hardware descriptor

The default Kasli-DIOT variant is described in `desc/kasli_diot_fastino.json`
(8× Fastino in DIOT slots 0–7).
