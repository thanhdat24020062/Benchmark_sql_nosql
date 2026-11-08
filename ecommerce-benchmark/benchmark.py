import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from bson.decimal128 import Decimal128
from dotenv import load_dotenv
from pymongo import MongoClient
from sqlalchemy import URL, bindparam, create_engine, text


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "results"

MYSQL_TABLES = (
    "customers",
    "sellers",
    "products",
    "category_translation",
    "orders",
    "order_items",
    "order_payments",
    "order_reviews",
)

MONGO_COLLECTIONS = (
    "orders",
    "customers",
    "products",
    "sellers",
    "categories",
)


def load_config():
    load_dotenv(ROOT_DIR / ".env")

    required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ValueError(
            "Missing MySQL settings in the project .env or environment: "
            + ", ".join(missing)
        )

    mysql_url = URL.create(
        "mysql+pymysql",
        username=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        host=os.environ["MYSQL_HOST"],
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.environ["MYSQL_DATABASE"],
    )
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    mongo_database = os.getenv("MONGO_DATABASE", "ecommerce_olist")
    return mysql_url, mongo_uri, mongo_database


def canonicalize(value):
    if isinstance(value, Decimal128):
        value = value.to_decimal()
    if isinstance(value, Decimal):
        return {"$decimal": format(value.normalize(), "f")}
    if isinstance(value, float):
        rounded = Decimal(str(value)).quantize(Decimal("0.01")).normalize()
        return {"$decimal": format(rounded, "f")}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat(timespec="microseconds")}
    if isinstance(value, dict):
        return {
            str(key): canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        items = [canonicalize(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, bytes):
        return value.hex()
    return value


def digest(value):
    payload = json.dumps(
        canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def result_size(value):
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        if "orders" in value and isinstance(value["orders"], list):
            return len(value["orders"])
        if "_id" in value:
            return 1
        return len(value)
    return 1


def fetch_mysql_order(connection, order_id):
    order = connection.execute(
        text("SELECT * FROM orders WHERE order_id = :order_id"),
        {"order_id": order_id},
    ).mappings().one()
    document = dict(order)
    document["_id"] = document["order_id"]

    child_tables = {
        "items": ("order_items", "order_item_id"),
        "payments": ("order_payments", "payment_sequential"),
        "reviews": ("order_reviews", "review_row_id"),
    }
    for field, (table, sort_column) in child_tables.items():
        rows = connection.execute(
            text(
                f"SELECT * FROM `{table}` "
                "WHERE order_id = :order_id "
                f"ORDER BY `{sort_column}`"
            ),
            {"order_id": order_id},
        ).mappings().all()
        document[field] = []
        for row in rows:
            child = dict(row)
            child.pop("order_id", None)
            document[field].append(child)
    return document


def fetch_mysql_customer_history(connection, customer_unique_id):
    order_rows = connection.execute(
        text(
            "SELECT o.* FROM orders AS o "
            "JOIN customers AS c ON c.customer_id = o.customer_id "
            "WHERE c.customer_unique_id = :customer_unique_id "
            "ORDER BY o.order_purchase_timestamp, o.order_id"
        ),
        {"customer_unique_id": customer_unique_id},
    ).mappings().all()
    documents = []
    order_ids = []
    for row in order_rows:
        document = dict(row)
        document["_id"] = document["order_id"]
        document.update({"items": [], "payments": [], "reviews": []})
        documents.append(document)
        order_ids.append(document["_id"])

    if not order_ids:
        return documents

    queries = (
        ("items", "order_items", "order_item_id"),
        ("payments", "order_payments", "payment_sequential"),
        ("reviews", "order_reviews", "review_row_id"),
    )
    order_positions = {order_id: index for index, order_id in enumerate(order_ids)}
    for field, table, sort_column in queries:
        statement = text(
            f"SELECT * FROM `{table}` WHERE order_id IN :order_ids "
            f"ORDER BY order_id, `{sort_column}`"
        ).bindparams(bindparam("order_ids", expanding=True))
        child_rows = connection.execute(
            statement, {"order_ids": order_ids}
        ).mappings().all()
        for row in child_rows:
            child = dict(row)
            order_id = child.pop("order_id")
            documents[order_positions[order_id]][field].append(child)
    return documents


def preflight(connection, mongo_db, skip_count_check):
    sql_counts = {
        table: connection.execute(
            text(f"SELECT COUNT(*) FROM `{table}`")
        ).scalar_one()
        for table in MYSQL_TABLES
    }
    mongo_counts = {
        "orders": mongo_db.orders.count_documents({}),
        "customers": mongo_db.customers.count_documents({}),
        "products": mongo_db.products.count_documents({}),
        "sellers": mongo_db.sellers.count_documents({}),
        "category_translation": mongo_db.categories.count_documents({}),
    }

    embedded_counts = mongo_db.orders.aggregate(
        [
            {
                "$group": {
                    "_id": None,
                    "order_items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
                    "order_payments": {
                        "$sum": {"$size": {"$ifNull": ["$payments", []]}}
                    },
                    "order_reviews": {
                        "$sum": {"$size": {"$ifNull": ["$reviews", []]}}
                    },
                }
            }
        ]
    )
    embedded_counts = next(embedded_counts, {})
    mongo_counts.update(
        {
            table: embedded_counts.get(table, 0)
            for table in ("order_items", "order_payments", "order_reviews")
        }
    )

    mismatches = {
        table: {"mysql": sql_count, "mongodb": mongo_counts[table]}
        for table, sql_count in sql_counts.items()
        if sql_count != mongo_counts.get(table)
    }
    if mismatches and not skip_count_check:
        details = "; ".join(
            f"{table}: MySQL={counts['mysql']:,}, "
            f"MongoDB={counts['mongodb']:,}"
            for table, counts in mismatches.items()
        )
        raise RuntimeError(
            "Record counts do not match; benchmark stopped to avoid "
            f"comparing different data. {details}. Use --skip-count-check "
            "only if this difference is intentional."
        )

    return {"mysql": sql_counts, "mongodb": mongo_counts, "mismatches": mismatches}


def build_cases(connection, mongo_db):
    parameters = {}
    parameters["order_id"] = connection.execute(
        text("SELECT order_id FROM orders ORDER BY order_id LIMIT 1")
    ).scalar_one()
    parameters["customer_unique_id"] = connection.execute(
        text(
            "SELECT c.customer_unique_id FROM orders AS o "
            "JOIN customers AS c ON c.customer_id = o.customer_id "
            "WHERE c.customer_unique_id IS NOT NULL "
            "GROUP BY c.customer_unique_id "
            "ORDER BY COUNT(*) DESC, c.customer_unique_id LIMIT 1"
        )
    ).scalar_one()
    parameters["status"] = connection.execute(
        text(
            "SELECT order_status FROM orders "
            "WHERE order_status IS NOT NULL "
            "GROUP BY order_status ORDER BY COUNT(*) DESC LIMIT 1"
        )
    ).scalar_one()
    date_range = connection.execute(
        text(
            "SELECT MIN(order_purchase_timestamp), "
            "MAX(order_purchase_timestamp) FROM orders"
        )
    ).one()
    if date_range[0] is None or date_range[1] is None:
        raise RuntimeError("The MySQL orders table contains no purchase dates.")
    parameters["start_date"] = date_range[0]
    parameters["end_date"] = date_range[1] + timedelta(seconds=1)

    def mysql_detail():
        return fetch_mysql_order(connection, parameters["order_id"])

    def mongo_detail():
        return mongo_db.orders.find_one({"_id": parameters["order_id"]})

    def mysql_history():
        return fetch_mysql_customer_history(
            connection, parameters["customer_unique_id"]
        )

    def mongo_history():
        customer_ids = [
            row["_id"]
            for row in mongo_db.customers.find(
                {"customer_unique_id": parameters["customer_unique_id"]},
                {"_id": 1},
            )
        ]
        if not customer_ids:
            return []
        return list(
            mongo_db.orders.find({"customer_id": {"$in": customer_ids}})
            .sort([("order_purchase_timestamp", 1), ("_id", 1)])
        )

    def mysql_status_page():
        rows = connection.execute(
            text(
                "SELECT order_id, customer_id, order_status, "
                "order_purchase_timestamp FROM orders "
                "WHERE order_status = :status "
                "AND order_purchase_timestamp >= :start_date "
                "AND order_purchase_timestamp < :end_date "
                "ORDER BY order_purchase_timestamp, order_id LIMIT 100"
            ),
            {
                "status": parameters["status"],
                "start_date": parameters["start_date"],
                "end_date": parameters["end_date"],
            },
        ).mappings().all()
        result = []
        for row in rows:
            document = dict(row)
            document["_id"] = document.pop("order_id")
            result.append(document)
        return result

    def mongo_status_page():
        return list(
            mongo_db.orders.find(
                {
                    "order_status": parameters["status"],
                    "order_purchase_timestamp": {
                        "$gte": parameters["start_date"],
                        "$lt": parameters["end_date"],
                    },
                },
                {
                    "_id": 1,
                    "customer_id": 1,
                    "order_status": 1,
                    "order_purchase_timestamp": 1,
                },
            )
            .sort([("order_purchase_timestamp", 1), ("_id", 1)])
            .limit(100)
        )

    def mysql_status_summary():
        rows = connection.execute(
            text(
                "SELECT order_status, COUNT(*) AS order_count "
                "FROM orders GROUP BY order_status"
            )
        ).mappings().all()
        return {row["order_status"]: row["order_count"] for row in rows}

    def mongo_status_summary():
        rows = mongo_db.orders.aggregate(
            [
                {"$group": {"_id": "$order_status", "order_count": {"$sum": 1}}},
            ]
        )
        return {row["_id"]: row["order_count"] for row in rows}

    def mysql_product_sales():
        rows = connection.execute(
            text(
                "SELECT oi.product_id, COUNT(*) AS item_count, "
                "SUM(oi.price) AS total_price "
                "FROM order_items AS oi "
                "JOIN orders AS o ON o.order_id = oi.order_id "
                "WHERE o.order_purchase_timestamp >= :start_date "
                "AND o.order_purchase_timestamp < :end_date "
                "GROUP BY oi.product_id"
            ),
            parameters,
        ).mappings().all()
        return {
            row["product_id"]: {
                "item_count": row["item_count"],
                "total_price": row["total_price"],
            }
            for row in rows
        }

    def mongo_product_sales():
        rows = mongo_db.orders.aggregate(
            [
                {
                    "$match": {
                        "order_purchase_timestamp": {
                            "$gte": parameters["start_date"],
                            "$lt": parameters["end_date"],
                        }
                    }
                },
                {"$unwind": "$items"},
                {
                    "$group": {
                        "_id": "$items.product_id",
                        "item_count": {"$sum": 1},
                        "total_price": {"$sum": "$items.price"},
                    }
                },
            ],
            allowDiskUse=True,
        )
        return {
            row["_id"]: {
                "item_count": row["item_count"],
                "total_price": row["total_price"],
            }
            for row in rows
        }

    return [
        ("order_detail", mysql_detail, mongo_detail),
        ("customer_order_history", mysql_history, mongo_history),
        ("filtered_orders_page", mysql_status_page, mongo_status_page),
        ("order_count_by_status", mysql_status_summary, mongo_status_summary),
        ("sales_by_product", mysql_product_sales, mongo_product_sales),
    ], parameters


def percentile(samples, quantile):
    ordered = sorted(samples)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def measure_pair(cases, warmup, iterations):
    results = []
    for name, mysql_fn, mongo_fn in cases:
        mysql_expected = mysql_fn()
        mongo_expected = mongo_fn()
        mysql_digest = digest(mysql_expected)
        mongo_digest = digest(mongo_expected)
        if mysql_digest != mongo_digest:
            raise RuntimeError(
                f"Result mismatch for '{name}'; timing was not started. "
                "Check that both databases contain equivalent data/schema."
            )

        for _ in range(warmup):
            mysql_fn()
            mongo_fn()

        mysql_samples = []
        mongo_samples = []
        for iteration in range(iterations):
            calls = (
                ((mysql_fn, mysql_samples), (mongo_fn, mongo_samples))
                if iteration % 2 == 0
                else ((mongo_fn, mongo_samples), (mysql_fn, mysql_samples))
            )
            for function, samples in calls:
                start = time.perf_counter_ns()
                function()
                samples.append((time.perf_counter_ns() - start) / 1_000_000)

        mysql_median = statistics.median(mysql_samples)
        mongo_median = statistics.median(mongo_samples)
        results.append(
            {
                "case": name,
                "result_rows": result_size(mysql_expected),
                "result_sha256": mysql_digest,
                "mysql_ms": {
                    "median": mysql_median,
                    "p95": percentile(mysql_samples, 0.95),
                    "min": min(mysql_samples),
                    "max": max(mysql_samples),
                },
                "mongodb_ms": {
                    "median": mongo_median,
                    "p95": percentile(mongo_samples, 0.95),
                    "min": min(mongo_samples),
                    "max": max(mongo_samples),
                },
                "median_speedup": (
                    mysql_median / mongo_median if mongo_median else None
                ),
            }
        )
    return results


def get_versions(connection, mongo_client):
    mysql_version = connection.execute(text("SELECT VERSION()")).scalar_one()
    mongo_version = mongo_client.server_info().get("version")
    return {"mysql": mysql_version, "mongodb": mongo_version}


def save_results(payload):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUTPUT_DIR / f"benchmark_{timestamp}.json"
    csv_path = OUTPUT_DIR / f"benchmark_{timestamp}.csv"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "case",
                "result_rows",
                "mysql_median_ms",
                "mysql_p95_ms",
                "mongodb_median_ms",
                "mongodb_p95_ms",
                "median_speedup_mysql_over_mongodb",
                "result_sha256",
            ]
        )
        for result in payload["results"]:
            writer.writerow(
                [
                    result["case"],
                    result["result_rows"],
                    result["mysql_ms"]["median"],
                    result["mysql_ms"]["p95"],
                    result["mongodb_ms"]["median"],
                    result["mongodb_ms"]["p95"],
                    result["median_speedup"],
                    result["result_sha256"],
                ]
            )
    return json_path, csv_path


def main():
    parser = argparse.ArgumentParser(
        description="Read-only, paired MySQL vs MongoDB benchmark for Olist."
    )
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument(
        "--skip-count-check",
        action="store_true",
        help="Continue despite record-count differences (not recommended).",
    )
    args = parser.parse_args()
    if args.iterations < 1 or args.warmup < 0:
        parser.error("--iterations must be positive and --warmup cannot be negative")

    mysql_url, mongo_uri, mongo_database = load_config()
    engine = create_engine(mysql_url, pool_pre_ping=True)
    mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        with engine.connect() as connection:
            mongo_client.admin.command("ping")
            mongo_db = mongo_client[mongo_database]

            print("Checking record counts...")
            counts = preflight(connection, mongo_db, args.skip_count_check)
            versions = get_versions(connection, mongo_client)
            cases, parameters = build_cases(connection, mongo_db)
            print(
                f"MySQL {versions['mysql']} | MongoDB {versions['mongodb']} | "
                f"database {mongo_database}"
            )
            print(
                f"Warm-up: {args.warmup} | measured iterations: {args.iterations}"
            )
            print("Checking query-result equivalence...")
            results = measure_pair(cases, args.warmup, args.iterations)

        payload = {
            "created_at": datetime.now().astimezone().isoformat(),
            "versions": versions,
            "database": mongo_database,
            "warmup": args.warmup,
            "iterations": args.iterations,
            "counts": counts,
            "parameters": {
                "status": parameters["status"],
                "start_date": parameters["start_date"],
                "end_date": parameters["end_date"],
            },
            "results": results,
        }
        json_path, csv_path = save_results(payload)
        print("\nBenchmark results (latency in milliseconds):")
        print(
            f"{'CASE':28} {'MYSQL MED':>12} {'MONGO MED':>12} "
            f"{'MYSQL P95':>12} {'MONGO P95':>12} {'MYSQL/MONGO':>13}"
        )
        for result in results:
            print(
                f"{result['case']:28} "
                f"{result['mysql_ms']['median']:12.3f} "
                f"{result['mongodb_ms']['median']:12.3f} "
                f"{result['mysql_ms']['p95']:12.3f} "
                f"{result['mongodb_ms']['p95']:12.3f} "
                f"{(result['median_speedup'] or 0):13.3f}x"
            )
        print(f"\nJSON: {json_path}")
        print(f"CSV : {csv_path}")
        print("No database writes were performed.")
    finally:
        mongo_client.close()
        engine.dispose()


if __name__ == "__main__":
    main()
