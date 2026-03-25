"""Utility helpers for Kasli-DIOT hardware management."""

import subprocess


def load(variant: str = "diot-tester-fastino") -> None:
    """Load pre-built ARTIQ artifacts onto Kasli-DIOT (no erase)."""
    subprocess.run(
        ["artiq_flash", "-t", "kasli_diot", "--srcbuild", "-d", f"build/{variant}", "load"],
        check=True,
    )


if __name__ == "__main__":
    load()