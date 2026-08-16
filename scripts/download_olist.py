#!/usr/bin/env python3
"""Download public Olist Brazilian E-Commerce CSVs into data/raw."""

from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path
from urllib.request import urlopen

from olist_ml.data.loaders import REQUIRED_FILES

# Community mirrors of the Kaggle olistbr/brazilian-ecommerce dataset.
CANDIDATE_URLS = [
    # Zenodo mirror commonly used in tutorials (may change; try in order).
    "https://github.com/mpluisferreira/olist-ecommerce/raw/master/data/brazilian-ecommerce.zip",
]


def _looks_complete(directory: Path) -> bool:
    return all((directory / name).exists() for name in REQUIRED_FILES.values())


def download_olist(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    if _looks_complete(dest):
        print(f"Olist files already present in {dest}")
        return dest

    last_error: Exception | None = None
    for url in CANDIDATE_URLS:
        try:
            print(f"Downloading {url}")
            with urlopen(url, timeout=120) as resp:
                payload = resp.read()
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                zf.extractall(dest)
            # Some zips nest a folder — flatten known CSVs.
            for path in dest.rglob("*.csv"):
                target = dest / path.name
                if path.resolve() != target.resolve():
                    target.write_bytes(path.read_bytes())
            if _looks_complete(dest):
                print(f"Downloaded Olist to {dest}")
                return dest
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"Failed {url}: {exc}")

    raise RuntimeError(
        "Could not download Olist automatically. "
        "Place the Kaggle brazilian-ecommerce CSVs into data/raw manually. "
        f"Last error: {last_error}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    download_olist(args.dest)


if __name__ == "__main__":
    main()
