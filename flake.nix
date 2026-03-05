{
  inputs = {
    artiq = {
      url = "git+https://github.com/elhep/artiq.git?ref=kasli-diot";
      # Override ARTIQ's default upstream misoc/migen with elhep forks that carry
      # Kasli-DIOT platform support (misoc.targets.kasli_diot etc.)
      inputs.src-misoc.follows = "src-misoc";
      inputs.src-migen.follows = "src-migen";
    };

    # Use the same nixpkgs commit that ARTIQ is built against (ensures ABI compatibility)
    nixpkgs.follows = "artiq/nixpkgs";

    # elhep misoc fork — adds misoc/targets/kasli_diot.py needed by ARTIQ gateware
    src-misoc = {
      url = "git+https://github.com/elhep/misoc.git?ref=kasli_diot&submodules=1";
      flake = false;
    };

    # elhep migen fork — Kasli-DIOT patches
    src-migen = {
      url = "git+https://github.com/elhep/migen.git?ref=kasli-diot";
      flake = false;
    };
  };

  outputs =
    {
      self,
      artiq,
      nixpkgs,
      ...
    }:
    let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
      python = pkgs.python3;
      pythonPackages = pkgs.python3Packages;

      buildInputs = [
        (pkgs.python3.withPackages (ps: [
          artiq.packages.x86_64-linux.artiq
          artiq.packages.x86_64-linux.misoc
          artiq.packages.x86_64-linux.migen
          ps.matplotlib # plotting
          ps.pyvisa # PyVISA core
          ps.pyvisa-py # pure-Python VISA backend
          ps.pyftdi # FTDI USB-to-I2C/SPI
        ]))
      ]
      ++ (with artiq.packages.x86_64-linux; [
        vivado
        openocd-bscanspi
      ]);

    in
    {
      devShells = {
        x86_64-linux.default = pkgs.mkShell {
          name = "artiq-env";
          buildInputs = buildInputs;
          shellHook = ''
            export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
            export PYTHONPATH=$(pwd):${self}:$PYTHONPATH
          '';
        };
      };
    };
  # Binary caches from M-Labs (avoids recompiling ARTIQ/Migen/MiSoC from source)
  nixConfig = {
    extra-trusted-public-keys = "nixbld.m-labs.hk-1:5aSRVA5b320xbNvu30tqxVPXpld73bhtOeH6uAjRyHc=";
    extra-substituters = "https://nixbld.m-labs.hk";
  };
}
