
import os
import time
import pandas as pd

from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, URL, text


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data" / "raw"

load_dotenv(ROOT_DIR / ".env")

MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

if not all([
    MYSQL_HOST,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE
]):
    raise ValueError(
        "Missing MySQL configuration in .env"
    )

connection_url = URL.create(
    drivername="mysql+pymysql",
    username=MYSQL_USER,
    password=MYSQL_PASSWORD,
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    database=MYSQL_DATABASE
)

engine = create_engine(
    connection_url,
    pool_pre_ping=True,
    pool_recycle=3600
)

TABLES = [
    {
        "file": "product_category_name_translation.csv",
        "table": "category_translation",
        "dates": [],
        "rename": {}
    },
    {
        "file": "olist_customers_dataset.csv",
        "table": "customers",
        "dates": [],
        "rename": {}
    },
    {
        "file": "olist_sellers_dataset.csv",
        "table": "sellers",
        "dates": [],
        "rename": {}
    },
    {
        "file": "olist_products_dataset.csv",
        "table": "products",
        "dates": [],
        "rename": {
            "product_name_lenght": "product_name_length",
            "product_description_lenght":
                "product_description_length"
        }
    },
    {
        "file": "olist_orders_dataset.csv",
        "table": "orders",
        "dates": [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date"
        ],
        "rename": {}
    },
    {
        "file": "olist_order_items_dataset.csv",
        "table": "order_items",
        "dates": [
            "shipping_limit_date"
        ],
        "rename": {}
    },
    {
        "file": "olist_order_payments_dataset.csv",
        "table": "order_payments",
        "dates": [],
        "rename": {}
    },
    {
        "file": "olist_order_reviews_dataset.csv",
        "table": "order_reviews",
        "dates": [
            "review_creation_date",
            "review_answer_timestamp"
        ],
        "rename": {}
    }
]

def check_database():

    print("\n" + "=" * 65)
    print("DATABASE CONNECTION CHECK")
    print("=" * 65)

    with engine.connect() as conn:

        database = conn.execute(
            text("SELECT DATABASE()")
        ).scalar()

        version = conn.execute(
            text("SELECT VERSION()")
        ).scalar()

    print(f"Connected database : {database}")
    print(f"MySQL version      : {version}")

    if database != MYSQL_DATABASE:
        raise RuntimeError(
            f"Database mismatch! "
            f"Expected {MYSQL_DATABASE}, got {database}"
        )

    print("Connection successful!")

def get_table_count(table_name):

    with engine.connect() as conn:

        result = conn.execute(
            text(
                f"SELECT COUNT(*) FROM `{table_name}`"
            )
        ).scalar()

    return result


def load_table(config):

    filename = config["file"]
    table_name = config["table"]

    file_path = DATA_DIR / filename

    print("\n" + "=" * 65)
    print(f"TABLE: {table_name}")
    print("=" * 65)

    if not file_path.exists():

        raise FileNotFoundError(
            f"Dataset not found: {file_path}"
        )

    print("Reading CSV...")

    df = pd.read_csv(
        file_path,
        low_memory=False
    )

    original_rows = len(df)

    print(f"Source rows: {original_rows:,}")

    if config["rename"]:

        df.rename(
            columns=config["rename"],
            inplace=True
        )


    for column in config["dates"]:

        if column not in df.columns:

            raise ValueError(
                f"Missing date column: {column}"
            )

        df[column] = pd.to_datetime(
            df[column],
            errors="coerce"
        )

    existing_rows = get_table_count(table_name)

    print(f"Existing rows: {existing_rows:,}")


    if existing_rows == original_rows:

        print(
            f"SKIPPED: {table_name} "
            "already imported completely."
        )

        return {
            "table": table_name,
            "rows": existing_rows,
            "seconds": 0,
            "status": "SKIPPED"
        }


    if existing_rows > 0:

        raise RuntimeError(
            f"\nTable '{table_name}' contains partial data!\n"
            f"Existing rows: {existing_rows:,}\n"
            f"Expected rows: {original_rows:,}\n"
            f"Please TRUNCATE this table before retrying."
        )


    print("Importing data into MySQL...")

    start_time = time.perf_counter()

    df.to_sql(
        name=table_name,
        con=engine,
        if_exists="append",
        index=False,
        chunksize=1000,
        method=None
    )

    elapsed = time.perf_counter() - start_time

    imported_rows = get_table_count(table_name)

    print(f"Imported rows: {imported_rows:,}")
    print(f"Import time  : {elapsed:.3f} seconds")

    if imported_rows != original_rows:

        raise RuntimeError(
            f"Row count mismatch in {table_name}!\n"
            f"Expected: {original_rows}\n"
            f"Actual: {imported_rows}"
        )

    print(f"SUCCESS: {table_name}")

    return {
        "table": table_name,
        "rows": imported_rows,
        "seconds": elapsed,
        "status": "SUCCESS"
    }


def main():

    check_database()

    results = []

    pipeline_start = time.perf_counter()

    print("\n")
    print("#" * 65)
    print("OLIST DATASET -> MYSQL IMPORT PIPELINE")
    print("#" * 65)

    try:

        for config in TABLES:

            result = load_table(config)

            results.append(result)

    except Exception as error:

        print("\n" + "!" * 65)
        print("PIPELINE FAILED")
        print("!" * 65)

        print(f"Error: {error}")

        print(
            "\nPlease fix the problem before continuing."
        )

        raise

    finally:

        engine.dispose()

    total_elapsed = time.perf_counter() - pipeline_start

    print("\n")
    print("=" * 85)
    print("MYSQL IMPORT REPORT")
    print("=" * 85)

    print(
        f"{'TABLE':25s}"
        f"{'ROWS':>15s}"
        f"{'TIME (s)':>15s}"
        f"{'STATUS':>20s}"
    )

    print("-" * 85)

    total_rows = 0

    for result in results:

        total_rows += result["rows"]

        print(
            f"{result['table']:25s}"
            f"{result['rows']:>15,}"
            f"{result['seconds']:>15.3f}"
            f"{result['status']:>20s}"
        )

    print("-" * 85)

    print(f"Total records : {total_rows:,}")
    print(f"Total time    : {total_elapsed:.3f} seconds")

    successful = sum(
        1 for r in results
        if r["status"] == "SUCCESS"
    )

    skipped = sum(
        1 for r in results
        if r["status"] == "SKIPPED"
    )

    print(f"Imported tables: {successful}")
    print(f"Skipped tables : {skipped}")

    print("\nPIPELINE COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
