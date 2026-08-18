#!/usr/bin/env python3
"""Generate tiny Olist-shaped fixtures for offline tests (handoff NOC)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "data" / "fixtures"


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    rows = []
    items = []
    payments = []
    start = datetime(2018, 1, 1, 10, 0, 0)
    for i in range(40):
        oid = f"o{i:03d}"
        cid = f"c{i % 8:03d}"
        sid = f"s{i % 5:03d}"
        purchase_dt = start + timedelta(days=i)
        approved_dt = purchase_dt + timedelta(hours=1)
        bucket = i % 10
        if bucket == 0:
            # P0: first scan after the promise
            estimated_dt = (approved_dt + timedelta(days=2)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            carrier_dt = approved_dt + timedelta(days=3)
            delivered_dt = carrier_dt + timedelta(days=4)
            shipping_limit = approved_dt + timedelta(days=1)
        elif bucket in (1, 2):
            # Upgrade window: remaining ~3–5 days
            estimated_dt = (approved_dt + timedelta(days=8)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            carrier_dt = approved_dt + timedelta(days=4)
            miss = i % 3 == 0
            delivered_dt = estimated_dt + timedelta(days=3 if miss else -2)
            shipping_limit = approved_dt + timedelta(days=5)
        elif bucket in (3, 4, 5):
            # Longer remaining (~11 days)
            estimated_dt = (approved_dt + timedelta(days=12)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            carrier_dt = approved_dt + timedelta(hours=12)
            miss = i % 3 == 0
            delivered_dt = estimated_dt + timedelta(days=2 if miss else -4)
            shipping_limit = estimated_dt
        else:
            # Mid remaining (~6 days)
            estimated_dt = (approved_dt + timedelta(days=10)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            carrier_dt = approved_dt + timedelta(days=4)
            miss = i % 4 == 0
            delivered_dt = estimated_dt + timedelta(days=1 if miss else -3)
            shipping_limit = approved_dt + timedelta(days=3 if i % 2 else 10)
        rows.append(
            {
                "order_id": oid,
                "customer_id": cid,
                "order_status": "delivered",
                "order_purchase_timestamp": purchase_dt.isoformat(timespec="seconds"),
                "order_approved_at": approved_dt.isoformat(timespec="seconds"),
                "order_delivered_carrier_date": carrier_dt.isoformat(timespec="seconds"),
                "order_delivered_customer_date": delivered_dt.isoformat(timespec="seconds"),
                "order_estimated_delivery_date": estimated_dt.isoformat(timespec="seconds"),
            }
        )
        items.append(
            {
                "order_id": oid,
                "order_item_id": 1,
                "product_id": f"p{i % 6:03d}",
                "seller_id": sid,
                "shipping_limit_date": shipping_limit.isoformat(timespec="seconds"),
                "price": 50 + i,
                "freight_value": 10 + (i % 5) * 8,
            }
        )
        payments.append(
            {
                "order_id": oid,
                "payment_sequential": 1,
                "payment_type": "credit_card" if i % 2 == 0 else "boleto",
                "payment_installments": 1 + (i % 3),
                "payment_value": 60 + i,
            }
        )

    pd.DataFrame(rows).to_csv(ROOT / "olist_orders_dataset.csv", index=False)
    pd.DataFrame(items).to_csv(ROOT / "olist_order_items_dataset.csv", index=False)
    pd.DataFrame(payments).to_csv(ROOT / "olist_order_payments_dataset.csv", index=False)

    customers = pd.DataFrame(
        {
            "customer_id": [f"c{i:03d}" for i in range(8)],
            "customer_unique_id": [f"cu{i:03d}" for i in range(8)],
            "customer_zip_code_prefix": [1000 + i for i in range(8)],
            "customer_city": ["sao paulo"] * 8,
            "customer_state": ["SP", "RJ", "MG", "SP", "RS", "PR", "BA", "PE"],
        }
    )
    customers.to_csv(ROOT / "olist_customers_dataset.csv", index=False)

    sellers = pd.DataFrame(
        {
            "seller_id": [f"s{i:03d}" for i in range(5)],
            "seller_zip_code_prefix": [2000 + i for i in range(5)],
            "seller_city": ["campinas"] * 5,
            "seller_state": ["SP", "RJ", "MG", "PR", "RS"],
        }
    )
    sellers.to_csv(ROOT / "olist_sellers_dataset.csv", index=False)

    products = pd.DataFrame(
        {
            "product_id": [f"p{i:03d}" for i in range(6)],
            "product_category_name": ["beleza", "cama", "esporte", "beleza", "casa", "toys"],
            "product_name_lenght": [10] * 6,
            "product_description_lenght": [100] * 6,
            "product_photos_qty": [1] * 6,
            "product_weight_g": [500] * 6,
            "product_length_cm": [20] * 6,
            "product_height_cm": [10] * 6,
            "product_width_cm": [15] * 6,
        }
    )
    products.to_csv(ROOT / "olist_products_dataset.csv", index=False)

    geo_rows = []
    customer_coords = [
        (1000, -23.55, -46.63),
        (1001, -22.90, -43.17),
        (1002, -19.92, -43.94),
        (1003, -23.50, -46.60),
        (1004, -30.03, -51.23),
        (1005, -25.43, -49.27),
        (1006, -12.97, -38.50),
        (1007, -8.05, -34.90),
    ]
    seller_coords = [
        (2000, -23.18, -46.90),
        (2001, -22.90, -43.20),
        (2002, -19.90, -43.90),
        (2003, -25.40, -49.25),
        (2004, -30.03, -51.20),
    ]
    for z, lat, lng in customer_coords + seller_coords:
        geo_rows.append(
            {
                "geolocation_zip_code_prefix": z,
                "geolocation_lat": lat,
                "geolocation_lng": lng,
                "geolocation_city": "city",
                "geolocation_state": "SP",
            }
        )
    pd.DataFrame(geo_rows).to_csv(ROOT / "olist_geolocation_dataset.csv", index=False)

    pd.DataFrame(
        {
            "product_category_name": ["beleza", "cama", "esporte", "casa", "toys"],
            "product_category_name_english": ["beauty", "bed", "sports", "home", "toys"],
        }
    ).to_csv(ROOT / "product_category_name_translation.csv", index=False)

    print(f"Wrote fixtures to {ROOT}")


if __name__ == "__main__":
    main()
