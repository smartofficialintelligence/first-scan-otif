#!/usr/bin/env python3
"""Download public Olist Brazilian E-Commerce CSVs into data/raw."""

from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from olist_ml.data.loaders import REQUIRED_FILES

# Community mirrors of the Kaggle olistbr/brazilian-ecommerce dataset (CC BY-NC-SA 4.0).
# Prefer zip mirrors; fall back to per-file raw GitHub paths.
ZIP_URLS = [
    "https://github.com/0PeterAdel/Brazilian-ECommerce/raw/main/0.DataSet/DataSet.zip",
]

RAW_BASE_URLS = [
    "https://raw.githubusercontent.com/Kaaykun/OlistAnalysis/master/data/csv",
    "https://raw.githubusercontent.com/0PeterAdel/Brazilian-ECommerce/main/0.DataSet",
]

UA = "olist-ml-demo/0.1 (portfolio; respectful fetch)"


def _looks_complete(directory: Path) -> bool:
    return all((directory / name).exists() and (directory / name).stat().st_size > 0 for name in REQUIRED_FILES.values())


def _fetch(url: str, timeout: int = 600) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _download_zip(url: str, dest: Path) -> bool:
    print(f"Downloading zip {url}")
    payload = _fetch(url)
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        zf.extractall(dest)
    for path in dest.rglob("*.csv"):
        target = dest / path.name
        if path.resolve() != target.resolve():
            target.write_bytes(path.read_bytes())
    return _looks_complete(dest)


def _download_raw_files(base: str, dest: Path) -> bool:
    print(f"Downloading CSVs from {base}")
    for name in REQUIRED_FILES.values():
        url = f"{base.rstrip('/')}/{name}"
        print(f"  -> {name}")
        data = _fetch(url)
        (dest / name).write_bytes(data)
    return _looks_complete(dest)


def download_olist(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    if _looks_complete(dest):
        print(f"Olist files already present in {dest}")
        return dest

    last_error: Exception | None = None
    for url in ZIP_URLS:
        try:
            if _download_zip(url, dest):
                print(f"Downloaded Olist to {dest}")
                return dest
            print(f"Zip extracted but required files incomplete from {url}")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"Failed zip {url}: {exc}")

    for base in RAW_BASE_URLS:
        try:
            if _download_raw_files(base, dest):
                print(f"Downloaded Olist to {dest}")
                return dest
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"Failed raw base {base}: {exc}")

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
