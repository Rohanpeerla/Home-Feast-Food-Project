from datetime import date, datetime, timedelta
import random

import streamlit as st
from werkzeug.security import check_password_hash, generate_password_hash

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


APP_TITLE = "HomeFeast"
ADMIN_EMAIL = "anirudh.ravichander16@gmail.com"


st.set_page_config(page_title=APP_TITLE, page_icon="HF", layout="wide")


def apply_styles():
    st.markdown(
        """
        <style>
          .block-container { padding-top: 1.1rem; padding-bottom: 2rem; }
          [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #fffaf4 0%, #fff5ea 100%);
            border-right: 1px solid rgba(196, 120, 58, 0.18);
          }
          .hf-brand {
            font-size: 2rem;
            font-weight: 800;
            color: #8d3a14;
            margin-bottom: 0.2rem;
          }
          .hf-sub {
            color: #6f5d50;
            margin-bottom: 1rem;
          }
          .hf-card {
            background: white;
            border: 1px solid rgba(0,0,0,0.08);
            border-radius: 16px;
            padding: 1rem 1.1rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.04);
            margin-bottom: 0.9rem;
          }
          .hf-pill {
            display: inline-block;
            padding: 0.25rem 0.7rem;
            border-radius: 999px;
            background: #fff1e6;
            color: #a64d1d;
            font-size: 0.8rem;
            margin-right: 0.35rem;
            margin-bottom: 0.35rem;
          }
          .hf-muted { color: #7a6a5f; }
          .hf-title { margin-bottom: 0.35rem; }
          .hf-row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def ensure_state():
    st.session_state.setdefault("page", "Home")
    st.session_state.setdefault("flash", None)
    st.session_state.setdefault("nav_page", "Home")


def flash(message, kind="success"):
    st.session_state.flash = {"message": message, "kind": kind}


def show_flash():
    payload = st.session_state.get("flash")
    if not payload:
        return
    st.session_state.flash = None
    kind = payload.get("kind", "success")
    message = payload.get("message", "")
    if kind == "success":
        st.success(message)
    elif kind == "error":
        st.error(message)
    else:
        st.info(message)


def current_user():
    user_id = st.session_state.get("user_id")
    return get_user_by_id(user_id) if user_id else None


def is_admin(user):
    return bool(user and user["is_admin"])


def set_page(page):
    st.session_state.page = page
    st.session_state.nav_page = page


def logout():
    st.session_state.pop("user_id", None)
    set_page("Home")
    flash("You have been logged out.", "success")


def login_user(user):
    st.session_state["user_id"] = user["id"]
    set_page("Home")
    flash(f"Welcome back, {user['name']}!", "success")


def format_money(value):
    return f"Rs. {int(value):,}"


def get_filtered_cooks(q="", meal_type="", cuisine="", lat=None, lon=None, radius_km=5.0):
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

    if lat is not None and lon is not None and lat != "" and lon != "":
        try:
            latf = float(lat)
            lonf = float(lon)
        except ValueError:
            cooks = []
        else:
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


def create_subscription(user_id, cook, plan):
    multiplier = {"daily": 1, "weekly": 7, "monthly": 25}.get(plan, 7)
    amount = int(cook["price_from"]) * multiplier
    today = date.today()
    meal_name = db_first_meal_name(cook["id"]) or f"{cook['name']} meal plan"

    db = get_db()
    try:
        with db:
            db.execute(
                """
                INSERT INTO subscriptions (user_id, cook_id, plan, status, start_date, next_delivery, price_per_meal)
                VALUES (?, ?, ?, 'active', ?, ?, ?)
                """,
                (user_id, cook["id"], plan, str(today), str(today + timedelta(days=1)), int(cook["price_from"])),
            )
            db.execute(
                """
                INSERT INTO orders (user_id, cook_id, meal_name, meal_type, amount, status, scheduled_for)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (user_id, cook["id"], meal_name, plan.capitalize(), amount, str(today + timedelta(days=1))),
            )
            db.execute("UPDATE cooks SET earnings_total = earnings_total + ? WHERE id = ?", (amount, cook["id"]))
    finally:
        db.close()

    return amount, str(today + timedelta(days=1))


def save_user_profile(user_id, name, email, phone, address, gender, meal_pref, cuisine_pref):
    db = get_db()
    try:
        existing = db.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id)).fetchone()
        if existing:
            return False, "That email is already registered."
        with db:
            db.execute(
                """
                UPDATE users
                SET name = ?, email = ?, phone = ?, address = ?, gender = ?, meal_pref = ?, cuisine_pref = ?
                WHERE id = ?
                """,
                (name, email, phone, address, gender, meal_pref, cuisine_pref, user_id),
            )
        return True, "Profile saved successfully."
    finally:
        db.close()


def add_cook_registration(name, email, phone, location, cuisines, meal_types, price_from, description, service_area, delivery_times, plan_notes, lat, lon):
    db = get_db()
    try:
        if db.execute("SELECT id FROM cooks WHERE email = ?", (email,)).fetchone():
            return False, "That cook email is already registered."
        try:
            latv = float(lat) if lat else None
        except Exception:
            latv = None
        try:
            lonv = float(lon) if lon else None
        except Exception:
            lonv = None
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
                    int(price_from or 0),
                    latv,
                    lonv,
                    description,
                    service_area,
                    delivery_times,
                    plan_notes,
                ),
            )
        return True, "Cook registration submitted. Admin approval is pending."
    finally:
        db.close()


def render_sidebar(user):
    pages = ["Home", "Discover Cooks", "Subscriptions", "Orders", "Profile", "Notifications", "Settings", "Reviews"]
    if is_admin(user):
        pages.append("Admin")

    if user:
        st.sidebar.markdown(f"### {APP_TITLE}")
        st.sidebar.caption(f"Logged in as {user['name']}")
        if st.sidebar.button("Logout"):
            logout()
            st.rerun()
    else:
        st.sidebar.markdown(f"### {APP_TITLE}")
        st.sidebar.caption("Browse, register, or log in")

    current = st.session_state.get("nav_page", "Home")
    if current not in pages:
        current = "Home"

    choice = st.sidebar.radio("Navigate", pages, index=pages.index(current), key="nav_page")
    st.session_state.page = choice
    return choice


def render_home(user):
    st.markdown(f"<div class='hf-brand'>{APP_TITLE}</div>", unsafe_allow_html=True)
    st.markdown("<div class='hf-sub'>Home-cooked meals, subscriptions, and cook discovery in one place.</div>", unsafe_allow_html=True)

    if user:
        subscriptions = get_user_subscriptions(user["id"])
        orders = get_user_orders(user["id"])
        active = [s for s in subscriptions if s["status"] == "active"]
        cols = st.columns(4)
        cols[0].metric("Active subscriptions", len(active))
        cols[1].metric("Orders", len(orders))
        cols[2].metric("Spent", format_money(sum(o["amount"] for o in orders)))
        cols[3].metric("Next delivery", active[0]["next_delivery"] if active else "None")
    else:
        cols = st.columns(3)
        cols[0].metric("Approved cooks", len(get_all_cooks()))
        cols[1].metric("Ready to order", "Yes")
        cols[2].metric("Login required", "No")

    st.subheader("Featured cooks")
    cooks = list(get_all_cooks())[:3]
    for cook in cooks:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"### {cook['name']}")
                st.caption(f"{cook['cuisines']} | {cook['location']} | {cook['meal_types']}")
                st.write(cook["description"] or "No description provided.")
            with c2:
                st.metric("From", format_money(cook["price_from"]))
                st.write(f"Menu items: {len(get_cook_meals_map([cook])[cook['id']])}")


def render_discover(user):
    st.subheader("Discover Cooks")
    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        q = st.text_input("Search", placeholder="Search by name, cuisine, or location")
    with f2:
        meal_type = st.selectbox("Meal type", ["", "Veg", "Non-Veg"])
    with f3:
        cuisine = st.selectbox("Cuisine", ["", "Andhra", "South Indian", "North Indian", "Healthy / Diet", "Chinese"])

    g1, g2, g3 = st.columns(3)
    with g1:
        lat = st.text_input("Latitude (optional)")
    with g2:
        lon = st.text_input("Longitude (optional)")
    with g3:
        radius_km = st.number_input("Radius km", min_value=1.0, max_value=50.0, value=5.0, step=1.0)

    plan = st.selectbox("Default plan", ["weekly", "daily", "monthly"])
    cooks = get_filtered_cooks(q=q, meal_type=meal_type, cuisine=cuisine, lat=lat, lon=lon, radius_km=radius_km)

    if not cooks:
        st.info("No cooks found matching your filters.")
        return

    for cook in cooks:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.markdown(f"### {cook['name']}")
                st.caption(f"{cook['cuisines']} | {cook['location']} | {cook['meal_types']}")
                st.write(cook["description"] or "No description provided.")
                st.markdown(f"<span class='hf-pill'>{cook['status'].title()}</span>", unsafe_allow_html=True)
            with right:
                st.metric("From", format_money(cook["price_from"]))
                st.write(f"Meals: {cook['meal_types'] or 'All'}")
                if user:
                    if st.button(f"Subscribe {plan}", key=f"sub_{cook['id']}"):
                        amount, first_delivery = create_subscription(user["id"], cook, plan)
                        flash(f"Subscription created. First delivery: {first_delivery}. Amount: {format_money(amount)}.")
                        st.rerun()
                else:
                    st.caption("Log in to subscribe.")


def render_subscriptions(user):
    st.subheader("My Subscriptions")
    if not user:
        st.info("Please log in to view your subscriptions.")
        return

    subs = get_user_subscriptions(user["id"])
    active_subs = [s for s in subs if s["status"] == "active"]
    past_subs = [s for s in subs if s["status"] != "active"]

    st.write(f"Active: {len(active_subs)} | Past: {len(past_subs)}")
    st.markdown("#### Active plans")
    if active_subs:
        for sub in active_subs:
            with st.container(border=True):
                st.markdown(f"**{sub['cook_name']}**")
                st.caption(f"{sub['plan'].title()} plan | Next delivery: {sub['next_delivery'] or 'Soon'}")
                st.write(f"Location: {sub['cook_location'] or 'Not set'}")
                st.write(f"Price per meal: {format_money(sub['price_per_meal'])}")
    else:
        st.info("You do not have any active subscriptions yet.")

    st.markdown("#### Past plans")
    if past_subs:
        for sub in past_subs:
            with st.container(border=True):
                st.markdown(f"**{sub['cook_name']}**")
                st.caption(f"{sub['plan'].title()} plan | Status: {sub['status'].title()}")
                st.write(f"Price per meal: {format_money(sub['price_per_meal'])}")
    else:
        st.info("No past subscriptions yet.")


def render_orders(user):
    st.subheader("Order History")
    if not user:
        st.info("Please log in to view your orders.")
        return

    orders = get_user_orders(user["id"])
    if not orders:
        st.info("No orders yet.")
        return

    for order in orders:
        with st.container(border=True):
            st.markdown(f"**{order['meal_name']}**")
            st.caption(f"{order['cook_name']} | {order['meal_type'] or 'Meal'} | {order['status'].title()}")
            st.write(f"Scheduled for: {order['scheduled_for'] or 'N/A'}")
            st.write(f"Amount: {format_money(order['amount'])}")


def render_profile(user):
    st.subheader("My Profile")
    if not user:
        st.info("Please log in to manage your profile.")
        return

    with st.form("profile_form"):
        name = st.text_input("Full name", value=user["name"] or "")
        email = st.text_input("Email", value=user["email"] or "")
        phone = st.text_input("Phone", value=user["phone"] or "")
        address = st.text_input("Address", value=user["address"] or "")
        gender = st.selectbox("Gender", ["Male", "Female", "Other", "Prefer not to say"], index=["Male", "Female", "Other", "Prefer not to say"].index(user["gender"] or "Male") if (user["gender"] or "Male") in ["Male", "Female", "Other", "Prefer not to say"] else 0)
        meal_pref = st.selectbox("Meal preference", ["Vegetarian", "Non-Vegetarian", "Both"], index=["Vegetarian", "Non-Vegetarian", "Both"].index(user["meal_pref"] or "Vegetarian") if (user["meal_pref"] or "Vegetarian") in ["Vegetarian", "Non-Vegetarian", "Both"] else 0)
        cuisine_pref = st.selectbox("Cuisine preference", ["South Indian", "North Indian", "Any"], index=["South Indian", "North Indian", "Any"].index(user["cuisine_pref"] or "Any") if (user["cuisine_pref"] or "Any") in ["South Indian", "North Indian", "Any"] else 2)
        submitted = st.form_submit_button("Save profile")

    if submitted:
        ok, msg = save_user_profile(user["id"], name, email, phone, address, gender, meal_pref, cuisine_pref)
        flash(msg, "success" if ok else "error")
        if ok:
            if email != user["email"]:
                st.session_state["user_id"] = get_user_by_email(email)["id"]
            st.rerun()


def render_notifications(user):
    st.subheader("Notifications")
    if not user:
        st.info("Please log in to see notifications.")
        return

    orders = get_user_orders(user["id"])
    subs = get_user_subscriptions(user["id"])
    active_subs = [s for s in subs if s["status"] == "active"]
    order_requests = [o for o in orders if (o["status"] or "").lower() == "pending"]
    order_updates = [o for o in orders if (o["status"] or "").lower() != "pending"]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Order requests")
        if order_requests:
            for order in order_requests:
                with st.container(border=True):
                    st.markdown(f"**{order['meal_name']}**")
                    st.caption(f"{order['meal_type']} | {order['scheduled_for'] or 'Pending'}")
        else:
            st.info("No pending order requests.")

    with col2:
        st.markdown("#### Order updates")
        if order_updates:
            for order in order_updates[:6]:
                with st.container(border=True):
                    st.markdown(f"**{order['meal_name']}**")
                    st.caption(f"{order['meal_type']} | {order['status'].title()} | {format_money(order['amount'])}")
        else:
            st.info("No recent order updates.")

    st.markdown("#### Subscription alerts")
    if active_subs:
        for sub in active_subs:
            with st.container(border=True):
                st.markdown(f"**{sub['cook_name']}**")
                st.caption(f"{sub['plan'].title()} plan | Next delivery: {sub['next_delivery'] or 'Soon'}")
    else:
        st.info("No active subscription alerts.")


def render_settings(user):
    st.subheader("Settings")
    if not user:
        st.info("Please log in to manage settings.")
        return

    with st.form("settings_form"):
        language = st.selectbox("Language", ["English", "Hindi", "Telugu"])
        currency = st.selectbox("Currency", ["INR", "USD"])
        notify_orders = st.checkbox("Order updates", value=True)
        notify_subs = st.checkbox("Subscription reminders", value=True)
        submitted = st.form_submit_button("Save settings")

    if submitted:
        st.session_state["settings"] = {
            "language": language,
            "currency": currency,
            "notify_orders": notify_orders,
            "notify_subs": notify_subs,
        }
        flash("Settings saved successfully.")
        st.rerun()

    st.caption("These settings are stored in your browser session for now.")


def render_reviews(user):
    st.subheader("My Reviews")
    if not user:
        st.info("Please log in to leave or view reviews.")
        return

    db = get_db()
    try:
        reviews = db.execute(
            """
            SELECT r.*, c.name AS cook_name
            FROM reviews r
            JOIN cooks c ON c.id = r.cook_id
            WHERE r.user_id = ?
            ORDER BY r.created_at DESC, r.id DESC
            """,
            (user["id"],),
        ).fetchall()
    finally:
        db.close()

    with st.form("review_form"):
        cook_options = [f"{c['id']} - {c['name']}" for c in get_all_cooks()]
        selected = st.selectbox("Cook", cook_options if cook_options else ["No cooks available"])
        rating = st.slider("Rating", 1, 5, 5)
        comment = st.text_area("Comment")
        submitted = st.form_submit_button("Leave review")

    if submitted and cook_options:
        cook_id = int(selected.split(" - ", 1)[0])
        db = get_db()
        try:
            with db:
                db.execute(
                    "INSERT INTO reviews (user_id, cook_id, rating, comment) VALUES (?, ?, ?, ?)",
                    (user["id"], cook_id, rating, comment),
                )
            flash("Review saved successfully.")
            st.rerun()
        finally:
            db.close()

    st.markdown("#### Previous reviews")
    if reviews:
        for review in reviews:
            with st.container(border=True):
                st.markdown(f"**{review['cook_name']}**")
                st.caption(f"Rating: {review['rating']} / 5")
                st.write(review["comment"] or "")
    else:
        st.info("You have not posted any reviews yet.")


def render_admin(user):
    st.subheader("Admin Dashboard")
    if not is_admin(user):
        st.error("Admin access required.")
        return

    stats = get_admin_stats()
    cols = st.columns(4)
    cols[0].metric("Users", stats["users"])
    cols[1].metric("Approved cooks", stats["cooks"])
    cols[2].metric("Pending cooks", stats["pending_cooks"])
    cols[3].metric("Active subscriptions", stats["subscriptions"])

    db = get_db()
    try:
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
    finally:
        db.close()

    st.markdown("#### Pending cooks")
    if pending_cooks:
        for cook in pending_cooks:
            with st.container(border=True):
                st.markdown(f"**{cook['name']}**")
                st.caption(f"{cook['cuisines']} | {cook['location']}")
                a1, a2 = st.columns(2)
                if a1.button("Approve", key=f"approve_{cook['id']}"):
                    db = get_db()
                    try:
                        with db:
                            db.execute("UPDATE cooks SET status = 'approved' WHERE id = ?", (cook["id"],))
                        flash(f"Approved {cook['name']}.")
                        st.rerun()
                    finally:
                        db.close()
                if a2.button("Reject", key=f"reject_{cook['id']}"):
                    db = get_db()
                    try:
                        with db:
                            db.execute("UPDATE cooks SET status = 'rejected' WHERE id = ?", (cook["id"],))
                        flash(f"Rejected {cook['name']}.")
                        st.rerun()
                    finally:
                        db.close()
    else:
        st.info("No pending cooks right now.")

    st.markdown("#### Recent orders")
    for order in recent_orders:
        with st.container(border=True):
            st.markdown(f"**{order['meal_name']}**")
            st.caption(f"{order['user_name']} -> {order['cook_name']} | {order['status'].title()}")
            st.write(f"Amount: {format_money(order['amount'])}")


def render_login():
    st.subheader("Login")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        user = get_user_by_email(email.strip().lower())
        if not user or not check_password_hash(user["password"], password):
            flash("Invalid email or password.", "error")
        else:
            login_user(user)
            st.rerun()


def render_register():
    st.subheader("Register")
    with st.form("register_form"):
        name = st.text_input("Full name")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password")
        phone = st.text_input("Phone")
        address = st.text_input("Address")
        gender = st.selectbox("Gender", ["", "Male", "Female", "Other", "Prefer not to say"])
        meal_pref = st.selectbox("Meal preference", ["Vegetarian", "Non-Vegetarian", "Both"])
        cuisine_pref = st.selectbox("Cuisine preference", ["South Indian", "North Indian", "Any"])
        submitted = st.form_submit_button("Create account")

    if submitted:
        name = name.strip()
        email = email.strip().lower()
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
                        """
                        INSERT INTO users (name, email, password, phone, address, gender, meal_pref, cuisine_pref)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (name, email, generate_password_hash(password), phone, address, gender, meal_pref, cuisine_pref),
                    )
                flash("Registration successful. Please log in.")
                set_page("Login")
                st.rerun()
            finally:
                db.close()


def render_cook_register():
    st.subheader("Become a Cook")
    with st.form("cook_register_form"):
        name = st.text_input("Name")
        email = st.text_input("Email")
        phone = st.text_input("Phone")
        location = st.text_input("Location")
        cuisines = st.text_input("Cuisines")
        meal_types = st.text_input("Meal types")
        price_from = st.text_input("Starting price")
        description = st.text_area("Description")
        service_area = st.text_input("Service area")
        delivery_times = st.text_input("Delivery times")
        plan_notes = st.text_area("Plan notes")
        lat = st.text_input("Latitude (optional)")
        lon = st.text_input("Longitude (optional)")
        submitted = st.form_submit_button("Submit application")

    if submitted:
        ok, msg = add_cook_registration(
            name.strip(),
            email.strip().lower(),
            phone.strip(),
            location.strip(),
            cuisines.strip(),
            meal_types.strip(),
            price_from.strip(),
            description.strip(),
            service_area.strip(),
            delivery_times.strip(),
            plan_notes.strip(),
            lat.strip(),
            lon.strip(),
        )
        flash(msg, "success" if ok else "error")
        if ok:
            st.rerun()


def main():
    init_db()
    ensure_state()
    apply_styles()
    user = current_user()
    show_flash()

    selected = render_sidebar(user)

    if selected == "Home":
        render_home(user)
    elif selected == "Discover Cooks":
        render_discover(user)
    elif selected == "Subscriptions":
        render_subscriptions(user)
    elif selected == "Orders":
        render_orders(user)
    elif selected == "Profile":
        render_profile(user)
    elif selected == "Notifications":
        render_notifications(user)
    elif selected == "Settings":
        render_settings(user)
    elif selected == "Reviews":
        render_reviews(user)
    elif selected == "Admin":
        render_admin(user)
    elif selected == "Login":
        render_login()
    elif selected == "Register":
        render_register()
    elif selected == "Cook Register":
        render_cook_register()


if __name__ == "__main__":
    main()
