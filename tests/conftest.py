import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prevision.spot import Spot  # noqa: E402

DEBUT = int(datetime(2026, 10, 10, tzinfo=timezone.utc).timestamp())


@pytest.fixture
def debut():
    return DEBUT


def fabriquer_spot(**modifs) -> Spot:
    base = dict(
        id="test", nom="Spot de test", lat=47.9, lon=-4.4, region="atlantique",
        orientation_deg=270, ouverture_deg=80, profondeur_m=6, fond="sable",
    )
    base.update(modifs)
    return Spot(**base)


@pytest.fixture
def spot_sable():
    return fabriquer_spot()
