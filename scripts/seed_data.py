"""Synchronize the real imported catalog into the API read model."""

import sys
from pathlib import Path

api_dir = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(api_dir))

from src.seed.sync_catalog_products import main  # noqa: E402

if __name__ == "__main__":
    main()
