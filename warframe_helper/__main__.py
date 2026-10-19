import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="warframe-helper", description="Wert von Void-Relikt-Belohnungen anzeigen")
    parser.add_argument("--log", type=Path, help="Pfad zur EE.log (sonst automatisch gesucht)")
    args = parser.parse_args()

    from .gui import run

    return run(args.log)


if __name__ == "__main__":
    sys.exit(main())
