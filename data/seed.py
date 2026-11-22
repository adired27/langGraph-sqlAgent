"""Build the sample store database at data/shop.db.  Run: python data/seed.py"""
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "shop.db"

SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    signup_date TEXT NOT NULL
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    total REAL NOT NULL,
    status TEXT NOT NULL,  -- 'completed', 'shipped', 'cancelled'
    order_date TEXT NOT NULL
);
"""

NAMES = ["Ana", "Ben", "Chen", "Diya", "Eli", "Fatima", "Gabe", "Hana", "Ivan", "Jade",
         "Kofi", "Lena", "Mateo", "Nia", "Omar", "Priya", "Quinn", "Rosa", "Sam", "Tara"]
CITIES = ["Tempe", "Phoenix", "Mesa", "Scottsdale", "Chandler", "Tucson"]
PRODUCTS = [
    ("Wireless Mouse", "Electronics", 24.99), ("Mechanical Keyboard", "Electronics", 89.00),
    ("USB-C Hub", "Electronics", 39.50), ("Headphones", "Electronics", 199.00),
    ("Monitor", "Electronics", 249.99), ("Desk Lamp", "Office", 32.00),
    ("Office Chair", "Office", 329.00), ("Notebook", "Office", 12.50),
    ("Backpack", "Lifestyle", 64.00), ("Water Bottle", "Lifestyle", 18.00),
    ("Hoodie", "Apparel", 55.00), ("Running Shoes", "Apparel", 119.00),
]
STATUSES = ["completed"] * 7 + ["shipped"] * 2 + ["cancelled"]


def build(path=DB_PATH):
    rng = random.Random(42)  # fixed seed: same data every time
    Path(path).unlink(missing_ok=True)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)

    start = date(2025, 1, 1)
    customers = [
        (i, NAMES[i - 1], rng.choice(CITIES), (start + timedelta(days=rng.randint(0, 300))).isoformat())
        for i in range(1, len(NAMES) + 1)
    ]
    db.executemany("INSERT INTO customers VALUES (?,?,?,?)", customers)
    db.executemany("INSERT INTO products VALUES (?,?,?,?)",
                   [(i, *p) for i, p in enumerate(PRODUCTS, start=1)])

    for oid in range(1, 301):
        cid, _, _, signup = rng.choice(customers)
        pid = rng.randint(1, len(PRODUCTS))
        qty = rng.randint(1, 3)
        day = date.fromisoformat(signup) + timedelta(days=rng.randint(0, 600))
        db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?)",
                   (oid, cid, pid, qty, round(PRODUCTS[pid - 1][2] * qty, 2),
                    rng.choice(STATUSES), day.isoformat()))

    db.commit()
    db.close()


if __name__ == "__main__":
    build()
    print(f"Built {DB_PATH}")
