"""Utility helpers for Kasli-DIOT hardware management."""

import subprocess


def load(variant: str = "diot-tester-fastino", target: str = "kasli_diot") -> None:
    """Load pre-built ARTIQ gateware onto Kasli/KasliDIOT (no erase)."""
    if target not in ("kasli", "kasli_diot"):
        raise ValueError(f"Supported targets are: 'kasli' and 'kasli_diot', not: {target}")
    
    subprocess.run(
        ["artiq_flash", "-t", f"{target}", "--srcbuild", "-d", f"build/{variant}", "load"],
        check=True,
    )


if __name__ == "__main__":
    load()