#!/usr/bin/env python3
"""Generate tiny Olist-shaped fixtures for offline tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "data" / "fixtures"


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    # 40 orders across time for temporal splits + both classes
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
        # ~30% long delivery (>14 days from approval)
        long = i % 3 == 0
        delivered_dt = approved_dt + timedelta(days=(18 if long else 5), hours=4)
        estimated_dt = (approved_dt + timedelta(days=12)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        rows.append(
            {
                "order_id": oid,
                "customer_id": cid,
                "order_status": "delivered",
                "order_purchase_timestamp": purchase_dt.isoformat(timespec="seconds"),
                "order_approved_at": approved_dt.isoformat(timespec="seconds"),
                "order_delivered_carrier_date": (approved_dt + timedelta(hours=7)).isoformat(
                    timespec="seconds"
                ),
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
                "shipping_limit_date": estimated_dt.isoformat(timespec="seconds"),
                "price": 50 + i,
                "freight_value": 10 + (i % 5),
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
    for z, lat, lng in [(1000 + i, -23.5 - i * 0.01, -46.6 - i * 0.01) for i in range(8)] + [
        (2000 + i, -22.9 - i * 0.01, -47.0 - i * 0.01) for i in range(5)
    ]:
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
