from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from homefeast_data import (
    db_first_meal_name,
    get_admin_stats,
    get_all_cooks,
    get_cook_by_id,
    get_cook_menu_items,
    get_db,
    get_user_by_email,
    get_user_by_id,
    get_user_orders,
    get_user_subscriptions,
    haversine_km,
    init_db,
)


APP_TITLE = "HomeFeast"
ADMIN_EMAIL = "anirudh.ravichander16@gmail.com"

app = Flask(__name__)
app.secret_key = "homefeast-secret-key"


def current_user():
    user_id = session.get("user_id")
    return get_user_by_id(user_id) if user_id else None


def inject_user():
    return {"user": current_user()}


app.context_processor(inject_user)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or not user["is_admin"]:
            flash("Admin access required.", "error")
            return redirect(url_for("home"))
        return view(*args, **kwargs)

    return wrapped


def is_admin(user):
    return bool(user and user["is_admin"])


def current_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    if 17 <= hour < 22:
        return "Good evening"
    return "Good night"


def format_money(value):
    return f"Rs. {int(value):,}"


def get_filtered_cooks(q="", meal_type="", cuisine="", lat=None, lon=None, radius_km=5):
    cooks = list(get_all_cooks())

    if q:
        q_lower = q.lower()
        cooks = [
            c for c in cooks
            if q_lower in (c["name"] or "").lower()
            or q_lower in (c["cuisines"] or "").lower()
            or q_lower in (c["location"] or "").lower()
        ]

    if meal_type:
        cooks = [c for c in cooks if (c["meal_types"] or "").strip().lower() == meal_type.lower()]

    if cuisine:
        cooks = [c for c in cooks if cuisine.lower() in (c["cuisines"] or "").lower()]

    if lat not in (None, "") and lon not in (None, ""):
        try:
            latf = float(lat)
            lonf = float(lon)
        except ValueError:
            return []
        nearby = []
        for c in cooks:
            if c["lat"] is None or c["lon"] is None:
                continue
            try:
                d = haversine_km(latf, lonf, float(c["lat"]), float(c["lon"]))
            except Exception:
                continue
            if d <= float(radius_km):
                nearby.append(c)
        cooks = nearby

    return cooks


def create_subscription(user_id, cook_id, plan):
    cook = get_cook_by_id(cook_id)
    if not cook:
        return False, "Cook not found."
    multiplier = {"daily": 1, "weekly": 7, "monthly": 25}.get(plan, 7)
    amount = int(cook["price_from"]) * multiplier
    today = date.today()
    meal_name = db_first_meal_name(cook_id) or f"{cook['name']} meal plan"
    db = get_db()
    try:
        with db:
            db.execute(
                """
                INSERT INTO subscriptions (user_id, cook_id, plan, status, start_date, next_delivery, price_per_meal)
                VALUES (?, ?, ?, 'active', ?, ?, ?)
                """,
                (user_id, cook_id, plan, str(today), str(today + timedelta(days=1)), int(cook["price_from"])),
            )
            db.execute(
                """
                INSERT INTO orders (user_id, cook_id, meal_name, meal_type, amount, status, scheduled_for)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (user_id, cook_id, meal_name, plan.capitalize(), amount, str(today + timedelta(days=1))),
            )
            db.execute("UPDATE cooks SET earnings_total = earnings_total + ? WHERE id = ?", (amount, cook_id))
    finally:
        db.close()
    return True, f"Subscription created for {cook['name']}."


def render_dashboard_page(initial_page="discover"):
    user = current_user()
    if not user:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))
    subscriptions = get_user_subscriptions(user["id"])
    active_subscriptions = [s for s in subscriptions if s["status"] == "active"]
    orders = get_user_orders(user["id"])
    dashboard_stats = {
        "active_subscriptions": len(active_subscriptions),
        "orders_count": len(orders),
        "spent": sum(o["amount"] for o in orders),
        "next_delivery": active_subscriptions[0]["next_delivery"] if active_subscriptions else None,
    }
    return render_template(
        "dashboard.html",
        initial_page=initial_page,
        greeting=current_greeting(),
        today=datetime.now().strftime("%A, %d %B %Y"),
        current_time=datetime.now().strftime("%I:%M %p"),
        active_subscriptions=active_subscriptions,
        subscriptions=subscriptions,
        past_subscriptions=[s for s in subscriptions if s["status"] != "active"],
        orders=orders,
        notifications_count=len([o for o in orders if (o["status"] or "").lower() == "pending"]),
        stats=dashboard_stats,
        admin_stats=get_admin_stats() if user["is_admin"] else None,
    )


@app.route("/")
def home():
    return render_template(
        "home.html",
        greeting=current_greeting(),
        featured_cooks=get_all_cooks()[:6],
    )


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
            return redirect(url_for("dashboard"))
    return render_template("login.html")


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
        meal_pref = request.form.get("meal_pref", "").strip()
        cuisine_pref = request.form.get("cuisine_pref", "").strip()
        if not name or not email or not password or not confirm:
            flash("Please complete all required fields.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif get_user_by_email(email):
            flash("That email is already registered.", "error")
        else:
            db = get_db()
            try:
                with db:
                    db.execute(
                        """
                        INSERT INTO users (name, email, password, phone, address, gender, meal_pref, cuisine_pref)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (name, email, generate_password_hash(password), phone, address, gender, meal_pref, cuisine_pref),
                    )
                flash("Registration successful. Please log in.", "success")
                return redirect(url_for("login"))
            finally:
                db.close()
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/cooks")
def cooks():
    q = request.args.get("q", "").strip()
    meal_type = request.args.get("meal_type", "").strip()
    cuisine = request.args.get("cuisine", "").strip()
    lat = request.args.get("lat", "").strip()
    lon = request.args.get("lon", "").strip()
    radius_km = request.args.get("radius_km", 5)
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 9)), 3), 24)
    cooks_list = get_filtered_cooks(q, meal_type, cuisine, lat, lon, radius_km)
    total = len(cooks_list)
    start = (page - 1) * per_page
    end = start + per_page
    return render_template(
        "cooks.html",
        cooks=cooks_list[start:end],
        q=q,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=max((total + per_page - 1) // per_page, 1),
        has_prev=page > 1,
        has_next=end < total,
        cuisine=cuisine,
    )


@app.route("/cook/register", methods=["GET", "POST"])
def cook_register():
    if request.method == "POST":
        db = get_db()
        try:
            with db:
                db.execute(
                    """
                    INSERT INTO cooks (name, email, phone, location, cuisines, meal_types, price_from, lat, lon, description, status, service_area, delivery_times, plan_notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                    """,
                    (
                        request.form.get("name", "").strip(),
                        request.form.get("email", "").strip().lower(),
                        request.form.get("phone", "").strip(),
                        request.form.get("location", "").strip(),
                        request.form.get("cuisines", "").strip(),
                        request.form.get("meal_types", "").strip(),
                        int(request.form.get("price_from") or 0),
                        request.form.get("lat") or None,
                        request.form.get("lon") or None,
                        request.form.get("description", "").strip(),
                        request.form.get("service_area", "").strip(),
                        request.form.get("delivery_times", "").strip(),
                        request.form.get("plan_notes", "").strip(),
                    ),
                )
            flash("Cook registration submitted for approval.", "success")
            return redirect(url_for("home"))
        finally:
            db.close()
    return render_template("cook_register.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_dashboard_page("home")


@app.route("/discover")
@login_required
def discover_page():
    return render_dashboard_page("discover")


@app.route("/subscriptions")
@login_required
def subscriptions_page():
    return render_dashboard_page("subscriptions")


@app.route("/orders")
@login_required
def orders_page():
    return render_dashboard_page("orders")


@app.route("/profile")
@login_required
def profile_page():
    return render_dashboard_page("profile")


@app.route("/notifications")
@login_required
def notifications_page():
    return render_dashboard_page("notifications")


@app.route("/settings")
@login_required
def settings_page():
    return render_dashboard_page("settings")


@app.route("/reviews")
@login_required
def reviews_page():
    return render_dashboard_page("reviews")


@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html", stats=get_admin_stats())


@app.route("/approve_cook/<int:cook_id>", methods=["POST"])
@admin_required
def approve_cook(cook_id):
    db = get_db()
    try:
        with db:
            db.execute("UPDATE cooks SET status = 'approved' WHERE id = ?", (cook_id,))
    finally:
        db.close()
    flash("Cook approved.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/reject_cook/<int:cook_id>", methods=["POST"])
@admin_required
def reject_cook(cook_id):
    db = get_db()
    try:
        with db:
            db.execute("UPDATE cooks SET status = 'rejected' WHERE id = ?", (cook_id,))
    finally:
        db.close()
    flash("Cook rejected.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/cook/<int:cook_id>")
def cook_dashboard(cook_id):
    cook = get_cook_by_id(cook_id)
    if not cook:
        flash("Cook not found.", "error")
        return redirect(url_for("cooks"))
    return render_template("cook_dashboard.html", cook=cook, meals=get_cook_menu_items(cook_id))


@app.route("/payment/<int:cook_id>")
@login_required
def payment(cook_id):
    cook = get_cook_by_id(cook_id)
    if not cook:
        flash("Cook not found.", "error")
        return redirect(url_for("cooks"))
    plan = request.args.get("plan", "weekly")
    return render_template("payment.html", cook=cook, plan=plan)


@app.route("/payment/<int:cook_id>/confirm", methods=["POST"])
@login_required
def confirm_payment(cook_id):
    plan = request.form.get("plan", "weekly")
    ok, msg = create_subscription(current_user()["id"], cook_id, plan)
    flash(msg, "success" if ok else "error")
    return redirect(url_for("payment_successful"))


@app.route("/payment/success")
@login_required
def payment_successful():
    return render_template("payment_successful.html")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
