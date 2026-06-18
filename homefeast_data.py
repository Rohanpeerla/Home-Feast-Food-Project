from datetime import datetime, timedelta
import math
import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "homefeast.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(db, table_name, column_name):
    columns = db.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column["name"] == column_name for column in columns)


def ensure_column(db, table_name, column_name, column_ddl):
    if not column_exists(db, table_name, column_name):
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}")


def init_db():
    db = get_db()
    try:
        with db:
            main_admin_email = "anirudh.ravichander16@gmail.com"
            legacy_admin_email = "demo@homefeast.com"

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL,
                    phone TEXT,
                    address TEXT,
                    gender TEXT,
                    meal_pref TEXT,
                    cuisine_pref TEXT,
                    is_admin INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            ensure_column(db, "users", "gender", "TEXT")
            ensure_column(db, "users", "is_admin", "INTEGER NOT NULL DEFAULT 0")

            admin_user = db.execute("SELECT id FROM users WHERE email = ?", (main_admin_email,)).fetchone()
            legacy_admin = db.execute("SELECT id FROM users WHERE email = ?", (legacy_admin_email,)).fetchone()

            if admin_user and legacy_admin and admin_user["id"] != legacy_admin["id"]:
                legacy_id = legacy_admin["id"]
                admin_id = admin_user["id"]
                for table in ("orders", "subscriptions", "reviews"):
                    db.execute(f"UPDATE {table} SET user_id = ? WHERE user_id = ?", (admin_id, legacy_id))
                db.execute("DELETE FROM users WHERE id = ?", (legacy_id,))
            elif not admin_user and legacy_admin:
                db.execute("UPDATE users SET email = ? WHERE id = ?", (main_admin_email, legacy_admin["id"]))
                admin_user = db.execute("SELECT id FROM users WHERE email = ?", (main_admin_email,)).fetchone()

            if not admin_user:
                db.execute(
                    """
                    INSERT INTO users (name, email, password, phone, address, gender, meal_pref, cuisine_pref, is_admin)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "Anirudh Ravichander",
                        main_admin_email,
                        generate_password_hash("demo123"),
                        "+91 98765 43210",
                        "Flat 4B, Prestige Heights, Banjara Hills, Hyderabad 500034",
                        "Male",
                        "Vegetarian",
                        "South Indian",
                        1,
                    ),
                )
            else:
                db.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (main_admin_email,))

            for admin_contact_email in (
                "sairohanpeerla@gmail.com",
                "manaswinibalemarthy@gmail.com",
            ):
                db.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (admin_contact_email,))

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS cooks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    phone TEXT,
                    location TEXT,
                    cuisines TEXT,
                    meal_types TEXT,
                    price_from INTEGER,
                    lat REAL,
                    lon REAL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'approved',
                    service_area TEXT,
                    delivery_times TEXT,
                    plan_notes TEXT,
                    earnings_total INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            ensure_column(db, "cooks", "status", "TEXT NOT NULL DEFAULT 'approved'")
            ensure_column(db, "cooks", "service_area", "TEXT")
            ensure_column(db, "cooks", "delivery_times", "TEXT")
            ensure_column(db, "cooks", "plan_notes", "TEXT")
            ensure_column(db, "cooks", "earnings_total", "INTEGER NOT NULL DEFAULT 0")

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS meals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cook_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    price INTEGER NOT NULL,
                    meal_type TEXT,
                    FOREIGN KEY(cook_id) REFERENCES cooks(id)
                )
                """
            )

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    cook_id INTEGER NOT NULL,
                    plan TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    start_date TEXT,
                    next_delivery TEXT,
                    price_per_meal INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(cook_id) REFERENCES cooks(id)
                )
                """
            )

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    cook_id INTEGER NOT NULL,
                    meal_name TEXT NOT NULL,
                    meal_type TEXT,
                    amount INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    scheduled_for TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(cook_id) REFERENCES cooks(id)
                )
                """
            )

            db.execute(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    cook_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL,
                    comment TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(cook_id) REFERENCES cooks(id)
                )
                """
            )

            if not db.execute("SELECT id FROM cooks WHERE email = ?", ("priya@homefeast.com",)).fetchone():
                db.execute(
                    """
                    INSERT INTO cooks (
                        name, email, phone, location, cuisines, meal_types, price_from,
                        lat, lon, description, status, service_area, delivery_times, plan_notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "Priya Reddy",
                        "priya@homefeast.com",
                        "+91 90000 11111",
                        "Banjara Hills, Hyderabad",
                        "Andhra",
                        "Veg",
                        55,
                        17.4189,
                        78.4121,
                        "Homestyle Andhra thali and tiffin services",
                        "approved",
                        "Banjara Hills, Jubilee Hills, Gachibowli",
                        "Lunch 12 PM - 2 PM, Dinner 7 PM - 9 PM",
                        "Daily, weekly, and monthly plans",
                    ),
                )

            if not db.execute("SELECT id FROM cooks WHERE email = ?", ("sumathi@homefeast.com",)).fetchone():
                db.execute(
                    """
                    INSERT INTO cooks (
                        name, email, phone, location, cuisines, meal_types, price_from,
                        lat, lon, description, status, service_area, delivery_times, plan_notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "Sumathi Iyer",
                        "sumathi@homefeast.com",
                        "+91 91111 22222",
                        "Kukatpally, Hyderabad",
                        "South Indian",
                        "Veg",
                        50,
                        17.4948,
                        78.3996,
                        "Home-style South Indian breakfast and dinner boxes",
                        "approved",
                        "Kukatpally, Miyapur, Hitech City",
                        "Breakfast 7 AM - 10 AM, Dinner 7 PM - 9 PM",
                        "Daily, weekly, and monthly plans",
                    ),
                )

            if not db.execute("SELECT id FROM cooks WHERE email = ?", ("ananya@homefeast.com",)).fetchone():
                db.execute(
                    """
                    INSERT INTO cooks (
                        name, email, phone, location, cuisines, meal_types, price_from,
                        lat, lon, description, status, service_area, delivery_times, plan_notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "Ananya Sharma",
                        "ananya@homefeast.com",
                        "+91 93333 44444",
                        "Ameerpet, Hyderabad",
                        "Healthy / Diet",
                        "Veg",
                        65,
                        17.4375,
                        78.4483,
                        "Light, balanced meals for working professionals",
                        "pending",
                        "Ameerpet, Begumpet, Somajiguda",
                        "Lunch 12 PM - 2 PM",
                        "Daily and weekly plans",
                    ),
                )

            for cook_email, dishes in [
                (
                    "priya@homefeast.com",
                    [
                        ("Dal Makhani Thali", "Homestyle dal makhani with rice and salad", 85, "Lunch"),
                        ("Rajma Chawal Box", "Rajma with steamed rice and achar", 80, "Lunch"),
                        ("Aloo Paratha Set", "Stuffed parathas with curd and pickle", 65, "Breakfast"),
                    ],
                ),
                (
                    "sumathi@homefeast.com",
                    [
                        ("Idli Sambar Combo", "Steamed idli with sambar and chutney", 55, "Breakfast"),
                        ("Masala Dosa Set", "Crisp dosa with potato filling and chutneys", 60, "Breakfast"),
                        ("Curd Rice Box", "Curd rice with pickle and fryums", 50, "Dinner"),
                    ],
                ),
            ]:
                cook = db.execute("SELECT id FROM cooks WHERE email = ?", (cook_email,)).fetchone()
                if cook and not db.execute("SELECT id FROM meals WHERE cook_id = ? LIMIT 1", (cook["id"],)).fetchone():
                    db.executemany(
                        "INSERT INTO meals (cook_id, name, description, price, meal_type) VALUES (?, ?, ?, ?, ?)",
                        [(cook["id"], name, desc, price, meal_type) for name, desc, price, meal_type in dishes],
                    )

            demo_user = db.execute("SELECT id FROM users WHERE email = ?", (main_admin_email,)).fetchone()
            priya = db.execute("SELECT id FROM cooks WHERE email = ?", ("priya@homefeast.com",)).fetchone()
            sumathi = db.execute("SELECT id FROM cooks WHERE email = ?", ("sumathi@homefeast.com",)).fetchone()
            if demo_user and priya and sumathi and not db.execute("SELECT id FROM subscriptions WHERE user_id = ?", (demo_user["id"],)).fetchone():
                today = datetime.utcnow().date()
                db.executemany(
                    """
                    INSERT INTO subscriptions (user_id, cook_id, plan, status, start_date, next_delivery, price_per_meal)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (demo_user["id"], priya["id"], "monthly", "active", str(today), str(today + timedelta(days=1)), 55),
                        (demo_user["id"], sumathi["id"], "weekly", "active", str(today), str(today + timedelta(days=1)), 50),
                    ],
                )

                db.executemany(
                    """
                    INSERT INTO orders (user_id, cook_id, meal_name, meal_type, amount, status, scheduled_for)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (demo_user["id"], priya["id"], "Dal Makhani Thali", "Lunch", 85, "delivered", str(today)),
                        (demo_user["id"], sumathi["id"], "Masala Dosa Set", "Breakfast", 60, "delivered", str(today - timedelta(days=1))),
                        (demo_user["id"], priya["id"], "Rajma Chawal Box", "Lunch", 80, "pending", str(today + timedelta(days=1))),
                    ],
                )
    finally:
        db.close()


def get_user_by_email(email):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    db.close()
    return user


def get_user_by_id(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()
    return user


def get_cook_by_email(email):
    db = get_db()
    cook = db.execute("SELECT * FROM cooks WHERE email = ?", (email,)).fetchone()
    db.close()
    return cook


def get_cook_by_id(cook_id):
    db = get_db()
    cook = db.execute("SELECT * FROM cooks WHERE id = ?", (cook_id,)).fetchone()
    db.close()
    return cook


def get_all_cooks(include_pending=False):
    db = get_db()
    if include_pending:
        cooks = db.execute("SELECT * FROM cooks ORDER BY id DESC").fetchall()
    else:
        cooks = db.execute("SELECT * FROM cooks WHERE status = 'approved' ORDER BY id DESC").fetchall()
    db.close()
    return cooks


def get_user_orders(user_id):
    db = get_db()
    rows = db.execute(
        """
        SELECT o.*, c.name AS cook_name, c.location AS cook_location
        FROM orders o
        JOIN cooks c ON c.id = o.cook_id
        WHERE o.user_id = ?
        ORDER BY o.created_at DESC, o.id DESC
        """,
        (user_id,),
    ).fetchall()
    db.close()
    return rows


def get_user_subscriptions(user_id):
    db = get_db()
    rows = db.execute(
        """
        SELECT s.*, c.name AS cook_name, c.location AS cook_location, c.cuisines, c.meal_types
        FROM subscriptions s
        JOIN cooks c ON c.id = s.cook_id
        WHERE s.user_id = ?
        ORDER BY s.created_at DESC, s.id DESC
        """,
        (user_id,),
    ).fetchall()
    db.close()
    return rows


def get_cook_meals_map(cooks):
    db = get_db()
    try:
        cook_meals = {}
        for cook in cooks:
            cook_meals[cook["id"]] = db.execute(
                "SELECT name, price, meal_type FROM meals WHERE cook_id = ? ORDER BY id LIMIT 3",
                (cook["id"],),
            ).fetchall()
        return cook_meals
    finally:
        db.close()


def get_cook_menu_items(cook_id):
    db = get_db()
    try:
        return db.execute("SELECT * FROM meals WHERE cook_id = ? ORDER BY id DESC", (cook_id,)).fetchall()
    finally:
        db.close()


def get_admin_stats():
    db = get_db()
    stats = {
        "users": db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"],
        "cooks": db.execute("SELECT COUNT(*) AS count FROM cooks WHERE status = 'approved'").fetchone()["count"],
        "pending_cooks": db.execute("SELECT COUNT(*) AS count FROM cooks WHERE status = 'pending'").fetchone()["count"],
        "orders": db.execute("SELECT COUNT(*) AS count FROM orders").fetchone()["count"],
        "subscriptions": db.execute("SELECT COUNT(*) AS count FROM subscriptions WHERE status = 'active'").fetchone()["count"],
    }
    db.close()
    return stats


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def db_first_meal_name(cook_id):
    db = get_db()
    meal = db.execute("SELECT name FROM meals WHERE cook_id = ? ORDER BY id LIMIT 1", (cook_id,)).fetchone()
    db.close()
    return meal["name"] if meal else None
