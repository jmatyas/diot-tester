# DIOT Tester

Thermal and electrical testing framework for DIOT PCB cards, with ground-bouncing
test support via ARTIQ on Kasli-DIOT + Fastino hardware.

## Prerequisites

- [Nix](https://nixos.org/download/) with flakes enabled

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

## Hardware descriptor

The default Kasli-DIOT variant is described in `desc/kasli_diot_fastino.json`
(8× Fastino in DIOT slots 0–7).
