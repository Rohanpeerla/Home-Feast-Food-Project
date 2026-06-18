from datetime import datetime, timedelta

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import random
from homefeast_data import (
    db_first_meal_name,
    get_admin_stats,
    get_all_cooks,
    get_cook_by_email,
    get_cook_by_id,
    get_cook_meals_map,
    get_db,
    get_user_by_email,
    get_user_by_id,
    get_user_orders,
    get_user_subscriptions,
    haversine_km,
    init_db,
)


app = Flask(__name__)
app.secret_key = "homefeast-secret-key"
db_initialized = False


def get_current_user():
    user_id = session.get("user_id")
    return get_user_by_id(user_id) if user_id else None


def current_user_is_admin():
    user = get_current_user()
    return bool(user and user["is_admin"])


@app.before_request
def ensure_db_initialized():
    global db_initialized
    if not db_initialized:
        init_db()
        db_initialized = True


@app.route("/")
def home():
    return render_template("home.html", user=get_current_user())


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        gender = request.form.get("gender", "").strip()
        meal_pref = request.form.get("meal_pref", "")
        cuisine_pref = request.form.get("cuisine_pref", "")

        if not name or not email or not password or not confirm:
            flash("Please complete all required fields.", "error")
        elif "@" not in email:
            flash("Please enter a valid email address.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
        elif not gender:
            flash("Please select your gender.", "error")
        elif get_user_by_email(email):
            flash("That email is already registered.", "error")
        else:
            db = get_db()
            try:
                with db:
                    db.execute(
                        "INSERT INTO users (name, email, password, phone, address, gender, meal_pref, cuisine_pref) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (name, email, generate_password_hash(password), phone, address, gender, meal_pref, cuisine_pref),
                    )
            finally:
                db.close()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_user_by_email(email)

        if not user or not check_password_hash(user["password"], password):
            flash("Invalid email or password.", "error")
        else:
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("admin_dashboard" if user["is_admin"] else "dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():
    return render_dashboard("home")


def render_dashboard(initial_page="home"):
    user = get_current_user()
    if not user:
        flash("Please log in to access your dashboard.", "error")
        return redirect(url_for("login"))

    subscriptions = get_user_subscriptions(user["id"])
    active_subscriptions = [s for s in subscriptions if s["status"] == "active"]
    past_subscriptions = [s for s in subscriptions if s["status"] != "active"]
    orders = get_user_orders(user["id"])
    cooks = get_all_cooks()
    order_requests = [o for o in orders if (o["status"] or "").lower() == "pending"]
    order_updates = [o for o in orders if (o["status"] or "").lower() != "pending"][:6]
    notification_count = len(order_requests) + len(active_subscriptions)

    return render_template(
        "dashboard.html",
        user=user,
        cooks=cooks,
        cook_meals=get_cook_meals_map(cooks),
        subscriptions=subscriptions,
        active_subscriptions=active_subscriptions,
        past_subscriptions=past_subscriptions,
        orders=orders,
        order_requests=order_requests,
        order_updates=order_updates,
        notification_count=notification_count,
        initial_page=initial_page,
        stats={
            "active_subscriptions": len([s for s in subscriptions if s["status"] == "active"]),
            "orders_count": len(orders),
            "spent": sum(o["amount"] for o in orders),
            "next_delivery": active_subscriptions[0]["next_delivery"] if active_subscriptions else None,
        },
    )


@app.route("/dashboard/<page>")
def dashboard_page(page):
    allowed_pages = {"home", "discover", "subscriptions", "orders", "profile", "notifications", "settings", "reviews"}
    if page not in allowed_pages:
        abort(404)
    return render_dashboard(page)


@app.route("/discover")
def discover_page():
    return render_dashboard("discover")


@app.route("/subscriptions")
def subscriptions_page():
    return render_dashboard("subscriptions")


@app.route("/orders")
def orders_page():
    return render_dashboard("orders")


@app.route("/profile")
def profile_page():
    return render_dashboard("profile")


@app.route("/notifications")
def notifications_page():
    return render_dashboard("notifications")


@app.route("/settings")
def settings_page():
    return render_dashboard("settings")


@app.route("/reviews")
def reviews_page():
    return render_dashboard("reviews")


@app.route("/cook/register", methods=["GET", "POST"])
def cook_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        cuisines = request.form.get("cuisines", "").strip()
        meal_types = request.form.get("meal_types", "").strip()
        price_from = request.form.get("price_from", "").strip() or "0"
        description = request.form.get("description", "").strip()
        service_area = request.form.get("service_area", "").strip()
        delivery_times = request.form.get("delivery_times", "").strip()
        plan_notes = request.form.get("plan_notes", "").strip()

        if not name or not email:
            flash("Name and email are required for cook registration.", "error")
        elif "@" not in email:
            flash("Please enter a valid email address.", "error")
        elif not location:
            flash("Location is required so users can find you nearby.", "error")
        elif get_cook_by_email(email):
            flash("That cook email is already registered.", "error")
        else:
            lat = request.form.get("lat")
            lon = request.form.get("lon")
            try:
                latv = float(lat) if lat else None
            except Exception:
                latv = None
            try:
                lonv = float(lon) if lon else None
            except Exception:
                lonv = None

            db = get_db()
            try:
                with db:
                    db.execute(
                        """
                        INSERT INTO cooks (
                            name, email, phone, location, cuisines, meal_types, price_from,
                            lat, lon, description, status, service_area, delivery_times, plan_notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                        """,
                        (
                            name,
                            email,
                            phone,
                            location,
                            cuisines,
                            meal_types,
                            int(price_from),
                            latv,
                            lonv,
                            description,
                            service_area,
                            delivery_times,
                            plan_notes,
                        ),
                    )
            finally:
                db.close()

            flash("Cook registration submitted. Admin approval is pending.", "success")
            return redirect(url_for("home"))

    return render_template("cook_register.html")


@app.route("/cook/<int:cook_id>")
def cook_dashboard(cook_id):
    cook = get_cook_by_id(cook_id)
    if not cook:
        flash("Cook not found.", "error")
        return redirect(url_for("home"))

    db = get_db()
    meals = db.execute("SELECT * FROM meals WHERE cook_id = ? ORDER BY id DESC", (cook_id,)).fetchall()
    recent_orders = db.execute(
        "SELECT * FROM orders WHERE cook_id = ? ORDER BY created_at DESC, id DESC LIMIT 5",
        (cook_id,),
    ).fetchall()
    earnings = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM orders WHERE cook_id = ? AND status = 'delivered'",
        (cook_id,),
    ).fetchone()["total"]
    active_subscriptions = db.execute(
        "SELECT COUNT(*) AS count FROM subscriptions WHERE cook_id = ? AND status = 'active'",
        (cook_id,),
    ).fetchone()["count"]
    pending_orders = db.execute(
        "SELECT COUNT(*) AS count FROM orders WHERE cook_id = ? AND status = 'pending'",
        (cook_id,),
    ).fetchone()["count"]
    db.close()

    return render_template(
        "cook_dashboard.html",
        cook=cook,
        meals=meals,
        recent_orders=recent_orders,
        earnings=earnings,
        active_subscriptions=active_subscriptions,
        pending_orders=pending_orders,
    )


@app.route("/cook/<int:cook_id>/menu", methods=["POST"])
def add_cook_menu_item(cook_id):
    cook = get_cook_by_id(cook_id)
    if not cook:
        flash("Cook not found.", "error")
        return redirect(url_for("home"))

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    price = request.form.get("price", "").strip()
    meal_type = request.form.get("meal_type", "").strip()

    if not name or not price:
        flash("Menu item name and price are required.", "error")
        return redirect(url_for("cook_dashboard", cook_id=cook_id))

    db = get_db()
    try:
        with db:
            db.execute(
                "INSERT INTO meals (cook_id, name, description, price, meal_type) VALUES (?, ?, ?, ?, ?)",
                (cook_id, name, description, int(price), meal_type),
            )
    finally:
        db.close()

    flash("Menu item added successfully.", "success")
    return redirect(url_for("cook_dashboard", cook_id=cook_id))


@app.route("/cook/<int:cook_id>/menu/<int:meal_id>/update", methods=["POST"])
def update_cook_menu_item(cook_id, meal_id):
    cook = get_cook_by_id(cook_id)
    if not cook:
        flash("Cook not found.", "error")
        return redirect(url_for("home"))

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    price = request.form.get("price", "").strip()
    meal_type = request.form.get("meal_type", "").strip()

    if not name or not price:
        flash("Menu item name and price are required.", "error")
        return redirect(url_for("cook_dashboard", cook_id=cook_id))

    db = get_db()
    try:
        with db:
            db.execute(
                """
                UPDATE meals
                SET name = ?, description = ?, price = ?, meal_type = ?
                WHERE id = ? AND cook_id = ?
                """,
                (name, description, int(price), meal_type, meal_id, cook_id),
            )
    finally:
        db.close()

    flash("Menu item updated successfully.", "success")
    return redirect(url_for("cook_dashboard", cook_id=cook_id))


@app.route("/cook/<int:cook_id>/menu/<int:meal_id>/delete", methods=["POST"])
def delete_cook_menu_item(cook_id, meal_id):
    cook = get_cook_by_id(cook_id)
    if not cook:
        flash("Cook not found.", "error")
        return redirect(url_for("home"))

    db = get_db()
    try:
        with db:
            db.execute("DELETE FROM meals WHERE id = ? AND cook_id = ?", (meal_id, cook_id))
    finally:
        db.close()

    flash("Menu item removed.", "success")
    return redirect(url_for("cook_dashboard", cook_id=cook_id))


@app.route("/payment/<int:cook_id>")
def payment(cook_id):
    cook = get_cook_by_id(cook_id)
    if not cook or cook["status"] != "approved":
        flash("Cook not found.", "error")
        return redirect(url_for("home"))
    plan = request.args.get("plan", "weekly")
    return render_template("payment.html", cook=cook, plan=plan)


@app.route("/confirm_payment/<int:cook_id>", methods=["POST"])
def confirm_payment(cook_id):
    user = get_current_user()
    if not user:
        flash("Please log in to continue with payment.", "error")
        return redirect(url_for("login"))

    cook = get_cook_by_id(cook_id)
    if not cook or cook["status"] != "approved":
        flash("Cook not found.", "error")
        return redirect(url_for("home"))

    method = request.form.get("method", "upi")
    plan = request.form.get("plan", "weekly")
    multiplier = {"daily": 1, "weekly": 7, "monthly": 25}.get(plan, 7)
    amount = int(cook["price_from"]) * multiplier
    today = datetime.utcnow().date()
    meal_name = db_first_meal_name(cook_id) or f"{cook['name']} meal plan"

    db = get_db()
    try:
        with db:
            db.execute(
                """
                INSERT INTO subscriptions (user_id, cook_id, plan, status, start_date, next_delivery, price_per_meal)
                VALUES (?, ?, ?, 'active', ?, ?, ?)
                """,
                (user["id"], cook_id, plan, str(today), str(today + timedelta(days=1)), int(cook["price_from"])),
            )
            db.execute(
                """
                INSERT INTO orders (user_id, cook_id, meal_name, meal_type, amount, status, scheduled_for)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (user["id"], cook_id, meal_name, plan.capitalize(), amount, str(today + timedelta(days=1))),
            )
            db.execute("UPDATE cooks SET earnings_total = earnings_total + ? WHERE id = ?", (amount, cook_id))
    finally:
        db.close()
    transaction_id = "HF" + str(random.randint(100000, 999999))

    return render_template(
        "payment_successful.html",
        transaction_id=transaction_id,
        cook=cook,
        plan=plan,
        amount=amount,
        first_delivery=str(today + timedelta(days=1)),
    )

@app.route("/cooks")
def cooks():
    q = request.args.get("q", "").strip()
    meal_type = request.args.get("meal_type", "").strip()
    cuisine = request.args.get("cuisine", "").strip()
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    try:
        radius_km = float(request.args.get("radius_km", 5))
    except (TypeError, ValueError):
        radius_km = 5.0

    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1

    try:
        per_page = min(max(int(request.args.get("per_page", 9)), 3), 24)
    except (TypeError, ValueError):
        per_page = 9

    db = get_db()
    rows = db.execute("SELECT * FROM cooks WHERE status = 'approved' ORDER BY id DESC").fetchall()

    if q:
        q_lower = q.lower()
        rows = [
            c for c in rows
            if q_lower in (c["name"] or "").lower()
            or q_lower in (c["cuisines"] or "").lower()
            or q_lower in (c["location"] or "").lower()
        ]

    if meal_type:
        rows = [c for c in rows if (c["meal_types"] or "").strip().lower() == meal_type.lower()]

    if cuisine:
        rows = [c for c in rows if cuisine.lower() in (c["cuisines"] or "").lower()]

    if lat and lon:
        try:
            latf = float(lat)
            lonf = float(lon)
            nearby_rows = []
            for c in rows:
                if c["lat"] is None or c["lon"] is None:
                    continue
                try:
                    d = haversine_km(latf, lonf, float(c["lat"]), float(c["lon"]))
                except Exception:
                    continue
                if d <= radius_km:
                    nearby_rows.append(c)
            rows = nearby_rows
        except ValueError:
            rows = []

    total = len(rows)
    start = (page - 1) * per_page
    end = start + per_page
    page_rows = rows[start:end]
    db.close()

    return render_template(
        "cooks.html",
        cooks=page_rows,
        q=q,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=max((total + per_page - 1) // per_page, 1),
        has_prev=page > 1,
        has_next=end < total,
    )


@app.route("/admin")
def admin_dashboard():
    user = get_current_user()
    if not user or not user["is_admin"]:
        flash("Admin access required.", "error")
        return redirect(url_for("home"))

    db = get_db()
    pending_cooks = db.execute("SELECT * FROM cooks WHERE status = 'pending' ORDER BY id DESC").fetchall()
    recent_orders = db.execute(
        """
        SELECT o.*, c.name AS cook_name, u.name AS user_name
        FROM orders o
        JOIN cooks c ON c.id = o.cook_id
        JOIN users u ON u.id = o.user_id
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT 10
        """
    ).fetchall()
    users = db.execute("SELECT id, name, email, phone, meal_pref, cuisine_pref, is_admin FROM users ORDER BY id DESC").fetchall()
    db.close()

    return render_template(
        "admin_dashboard.html",
        user=user,
        stats=get_admin_stats(),
        pending_cooks=pending_cooks,
        recent_orders=recent_orders,
        users=users,
    )


@app.route("/admin/cooks/<int:cook_id>/approve", methods=["POST"])
def approve_cook(cook_id):
    user = get_current_user()
    if not user or not user["is_admin"]:
        flash("Admin access required.", "error")
        return redirect(url_for("home"))

    db = get_db()
    try:
        with db:
            db.execute("UPDATE cooks SET status = 'approved' WHERE id = ?", (cook_id,))
    finally:
        db.close()

    flash("Cook approved successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/cooks/<int:cook_id>/reject", methods=["POST"])
def reject_cook(cook_id):
    user = get_current_user()
    if not user or not user["is_admin"]:
        flash("Admin access required.", "error")
        return redirect(url_for("home"))

    db = get_db()
    try:
        with db:
            db.execute("UPDATE cooks SET status = 'rejected' WHERE id = ?", (cook_id,))
    finally:
        db.close()

    flash("Cook registration rejected.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/api/cooks")
def api_cooks():
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 9)), 3), 24)
    q = request.args.get("q", "").strip().lower()
    db = get_db()
    try:
        if q:
            rows = db.execute(
                """
                SELECT * FROM cooks
                WHERE status = 'approved'
                  AND (lower(name) LIKE ? OR lower(cuisines) LIKE ? OR lower(location) LIKE ?)
                ORDER BY id DESC
                """,
                (f"%{q}%", f"%{q}%", f"%{q}%"),
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM cooks WHERE status = 'approved' ORDER BY id DESC").fetchall()
        total = len(rows)
        start = (page - 1) * per_page
        end = start + per_page
        payload = [dict(row) for row in rows[start:end]]
        return jsonify(
            {
                "items": payload,
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": max((total + per_page - 1) // per_page, 1),
            }
        )
    finally:
        db.close()


@app.route("/api/cooks/<int:cook_id>/status", methods=["POST"])
def api_cook_status(cook_id):
    user = get_current_user()
    if not user or not user["is_admin"]:
        return jsonify({"ok": False, "error": "Admin access required."}), 403

    status = (request.json or {}).get("status", "").strip().lower()
    if status not in {"approved", "rejected", "pending"}:
        return jsonify({"ok": False, "error": "Invalid status."}), 400

    db = get_db()
    try:
        with db:
            db.execute("UPDATE cooks SET status = ? WHERE id = ?", (status, cook_id))
        return jsonify({"ok": True, "cook_id": cook_id, "status": status})
    finally:
        db.close()


@app.route("/api/meals/<int:meal_id>", methods=["PATCH", "DELETE"])
def api_meal_item(meal_id):
    user = get_current_user()
    if not user or not user["is_admin"]:
        return jsonify({"ok": False, "error": "Admin access required."}), 403

    db = get_db()
    try:
        meal = db.execute("SELECT * FROM meals WHERE id = ?", (meal_id,)).fetchone()
        if not meal:
            return jsonify({"ok": False, "error": "Meal not found."}), 404

        if request.method == "DELETE":
            with db:
                db.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
            return jsonify({"ok": True, "deleted": meal_id})

        payload = request.json or {}
        name = payload.get("name", meal["name"]).strip()
        description = payload.get("description", meal["description"] or "").strip()
        price = int(payload.get("price", meal["price"]))
        meal_type = payload.get("meal_type", meal["meal_type"] or "").strip()
        with db:
            db.execute(
                """
                UPDATE meals
                SET name = ?, description = ?, price = ?, meal_type = ?
                WHERE id = ?
                """,
                (name, description, price, meal_type, meal_id),
            )
        return jsonify({"ok": True, "meal_id": meal_id, "name": name, "price": price})
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
