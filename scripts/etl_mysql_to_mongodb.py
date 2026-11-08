import os
from collections import defaultdict
from decimal import Decimal

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from pymongo import MongoClient, ReplaceOne
from bson.decimal128 import Decimal128


# =========================================================
# 1. LOAD CONFIGURATION
# =========================================================

load_dotenv()

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "ecommerce_olist")

BATCH_SIZE = 1000

mysql_url = URL.create(
    "mysql+pymysql",
    username=MYSQL_USER,
    password=MYSQL_PASSWORD,
    host=MYSQL_HOST,
    port=int(MYSQL_PORT),
    database=MYSQL_DATABASE,
)

engine = create_engine(mysql_url)

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DATABASE]


# =========================================================
# 2. HELPER FUNCTIONS
# =========================================================

def load_table(table_name):
    """Read a complete MySQL table into a DataFrame."""
    print(f"Reading MySQL table: {table_name}")

    return pd.read_sql_table(
        table_name,
        con=engine
    )


def clean_value(value):
    """
    Convert Pandas/Python values into BSON-compatible values.
    """
    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.to_pydatetime()

    if isinstance(value, Decimal):
        return Decimal128(value)

    if isinstance(value, (list, dict)):
        return value

    # Handle NaN, NaT and pandas missing values
    try:
        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return None
    except (TypeError, ValueError):
        pass

    # Convert NumPy scalar to native Python scalar
    if hasattr(value, "item"):
        return value.item()

    return value


def clean_record(record):
    """Clean every field in a dictionary."""
    return {
        key: clean_value(value)
        for key, value in record.items()
    }


def group_records_by_order(dataframe):
    """
    Group child records by order_id.

    Result:
    {
        order_id_1: [record1, record2],
        order_id_2: [record1]
    }
    """
    result = defaultdict(list)

    for record in dataframe.to_dict(orient="records"):
        order_id = record.pop("order_id")

        # The order_id is already the parent document's _id.
        result[order_id].append(clean_record(record))

    return result


def bulk_replace(collection, documents, key="_id"):
    """
    Upsert documents in batches.

    Re-running the ETL replaces existing documents instead
    of creating duplicates.
    """
    if not documents:
        return

    operations = []

    for document in documents:
        document = clean_record(document)

        document_id = document[key]

        operations.append(
            ReplaceOne(
                {"_id": document_id},
                {
                    **document,
                    "_id": document_id
                },
                upsert=True
            )
        )

        if len(operations) >= BATCH_SIZE:
            collection.bulk_write(operations, ordered=False)
            operations = []

    if operations:
        collection.bulk_write(operations, ordered=False)


# =========================================================
# 3. EXTRACT: READ DATA FROM MYSQL
# =========================================================

customers_df = load_table("customers")
sellers_df = load_table("sellers")
products_df = load_table("products")
categories_df = load_table("category_translation")

orders_df = load_table("orders")
items_df = load_table("order_items")
payments_df = load_table("order_payments")
reviews_df = load_table("order_reviews")


# =========================================================
# 4. TRANSFORM: BUILD EMBEDDED DOCUMENTS
# =========================================================

print("\nTransforming child tables...")

items_by_order = group_records_by_order(items_df)
payments_by_order = group_records_by_order(payments_df)
reviews_by_order = group_records_by_order(reviews_df)


print("Building order documents...")

order_documents = []

for order in orders_df.to_dict(orient="records"):

    order_id = order["order_id"]

    document = clean_record(order)

    document["_id"] = order_id

    # Embed one-to-many relationships
    document["items"] = items_by_order.get(order_id, [])
    document["payments"] = payments_by_order.get(order_id, [])
    document["reviews"] = reviews_by_order.get(order_id, [])

    order_documents.append(document)


# =========================================================
# 5. TRANSFORM: BUILD OTHER COLLECTIONS
# =========================================================

def build_documents(dataframe, primary_key):
    documents = []

    for record in dataframe.to_dict(orient="records"):
        document = clean_record(record)

        document["_id"] = document.pop(primary_key)

        documents.append(document)

    return documents


customer_documents = build_documents(
    customers_df,
    "customer_id"
)

seller_documents = build_documents(
    sellers_df,
    "seller_id"
)

product_documents = build_documents(
    products_df,
    "product_id"
)

category_documents = build_documents(
    categories_df,
    "product_category_name"
)

# Exclude categories without a valid key
category_documents = [
    doc for doc in category_documents
    if doc["_id"] is not None
]


# =========================================================
# 6. LOAD: WRITE DATA INTO MONGODB
# =========================================================

print("\nLoading data into MongoDB...")

collections = {
    "orders": order_documents,
    "customers": customer_documents,
    "products": product_documents,
    "sellers": seller_documents,
    "categories": category_documents
}

for collection_name, documents in collections.items():

    collection = mongo_db[collection_name]

    bulk_replace(collection, documents)

    print(
        f"{collection_name}: "
        f"{collection.count_documents({}):,} documents"
    )


# =========================================================
# 7. CREATE INDEXES
# =========================================================

print("\nCreating indexes...")

mongo_db.orders.create_index("customer_id")
mongo_db.orders.create_index("order_status")
mongo_db.orders.create_index("order_purchase_timestamp")

mongo_db.orders.create_index("items.product_id")
mongo_db.orders.create_index("items.seller_id")

mongo_db.customers.create_index("customer_unique_id")

mongo_db.products.create_index("product_category_name")

print("Indexes created successfully!")


# =========================================================
# 8. VERIFY
# =========================================================

print("\n========== ETL SUMMARY ==========")

for collection_name in collections:
    count = mongo_db[collection_name].count_documents({})

    print(f"{collection_name}: {count:,}")

print("\nETL COMPLETED!")

mongo_client.close()
engine.dispose()
