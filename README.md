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

> **Note:** Gateware compilation (`build_kasli_diot`) is **not** supported in the
> Nix shell due to Rust toolchain constraints. Use the submodule environment for
> that (see below).

### Gateware build environment (submodules + direnv)

```bash
direnv allow        # adds submodule paths to PYTHONPATH (run once after cloning)
./build_kasli_diot  # compile gateware + kernels
./flash_kasli_diot  # full erase + flash
./load_kasli_diot   # fast reload (no erase)
```

## Python loader

`kasli_diot_utils.load()` wraps `load_kasli_diot` so a scenario script can
programmatically reload gateware between measurements:

```python
from kasli_diot_utils import load

load()                              # default variant: diot-tester-fastino
load(variant="my-custom-variant")   # override variant
```

This is equivalent to running `./load_kasli_diot` from the shell and raises
`subprocess.CalledProcessError` on failure.

## Hardware descriptor

The default Kasli-DIOT variant is described in `desc/kasli_diot_fastino.json`
(8× Fastino in DIOT slots 0–7).
