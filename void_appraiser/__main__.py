import argparse
import sys
from pathlib import Path


def selftest(image: Path) -> int:
    """Test the recognition on a screenshot without a window (also for built packages)."""
    import numpy as np
    from PIL import Image

    from .data import RelicDB
    from .recognize import (
        CARDS_REGION,
        DIALOG_REGION,
        HEADER_LINE,
        SCREEN_REWARDS,
        NameMatcher,
        Recognizer,
        classify_header,
        crop,
        match_reward_cards,
        parse_equip_dialog,
    )

    frame = np.asarray(Image.open(image).convert("RGB"))
    rec = Recognizer()
    screen = classify_header([rec.read_line(crop(frame, HEADER_LINE))])
    print("Screen:", screen)
    if screen == SCREEN_REWARDS:
        cards = match_reward_cards(rec.read(crop(frame, CARDS_REGION)), NameMatcher(RelicDB.load().reward_names()))
        print("Cards:", [c.name for c in cards])
        return 0 if cards else 1
    relic = parse_equip_dialog(rec.read(crop(frame, DIALOG_REGION)))
    print("Dialog:", relic)
    return 0 if relic else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="void-appraiser", description="Shows the value of Warframe void relic rewards")
    parser.add_argument("--log", type=Path, help="path to EE.log (searched automatically otherwise)")
    parser.add_argument("--selftest", type=Path, metavar="IMAGE", help="test the recognition on a screenshot and exit")
    args = parser.parse_args()

    if args.selftest:
        return selftest(args.selftest)

    from .gui import run

    return run(args.log)


if __name__ == "__main__":
    sys.exit(main())
