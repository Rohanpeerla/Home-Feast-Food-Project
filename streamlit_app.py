from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from werkzeug.security import check_password_hash, generate_password_hash

from homefeast_data import (
    get_all_cooks,
    get_cook_by_id,
    get_db,
    get_user_by_email,
    get_user_by_id,
    get_user_orders,
    get_user_subscriptions,
    init_db,
)


APP_TITLE = "HomeFeast"


def apply_styles():
    st.markdown(
        """
        <style>
          .stApp {
            background: linear-gradient(180deg, #fff8ef 0%, #fffdf9 36%, #ffffff 100%);
            color: #2b211b;
          }
          .block-container {
            padding-top: 1.35rem;
            padding-bottom: 2rem;
            max-width: 1200px;
          }
          section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #fffaf4 0%, #fff4e9 100%);
            border-right: 1px solid rgba(200, 85, 45, 0.14);
          }
          .hf-hero {
            background: rgba(255, 255, 255, 0.84);
            border: 1px solid rgba(200, 85, 45, 0.12);
            border-radius: 22px;
            padding: 1.4rem 1.5rem;
            box-shadow: 0 14px 40px rgba(0, 0, 0, 0.05);
            margin-bottom: 1.2rem;
          }
          .hf-brand {
            font-size: 2rem;
            font-weight: 800;
            color: #c8552d;
            margin-bottom: 0.25rem;
          }
          .hf-sub {
            color: #6f5d50;
          }
          .hf-card {
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid rgba(200, 85, 45, 0.12);
            border-radius: 18px;
            padding: 1rem 1.05rem;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.04);
            margin-bottom: 1rem;
          }
          .hf-pill {
            display: inline-block;
            background: #fff1e6;
            color: #a64d1d;
            border-radius: 999px;
            padding: 0.25rem 0.7rem;
            font-size: 0.8rem;
            margin-right: 0.35rem;
            margin-bottom: 0.35rem;
          }
          .cook-card {
            background: #fff;
            border: 1px solid rgba(200, 85, 45, 0.12);
            border-radius: 18px;
            padding: 1rem 1.1rem;
            box-shadow: 0 10px 26px rgba(0, 0, 0, 0.04);
            margin-bottom: 1rem;
          }
          .cook-title {
            font-size: 1.1rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
          }
          .cook-meta {
            color: #7a6c61;
            margin-bottom: 0.5rem;
          }
          .stButton > button {
            background: #c8552d;
            color: white;
            border: 1px solid #c8552d;
            border-radius: 12px;
            padding: 0.55rem 1rem;
            font-weight: 600;
          }
          .stButton > button:hover {
            background: #9b3e20;
            border-color: #9b3e20;
            color: white;
          }
          .stMetric {
            background: white;
            border: 1px solid rgba(200, 85, 45, 0.1);
            border-radius: 18px;
            padding: 0.75rem 0.9rem;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.03);
          }
          #MainMenu, footer, header {
            visibility: hidden;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def current_user():
    user_id = st.session_state.get("user_id")
    return get_user_by_id(user_id) if user_id else None


def current_datetime():
    try:
        return datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        return datetime.now()


def greeting():
    hour = current_datetime().hour
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    if 17 <= hour < 22:
        return "Good evening"
    return "Good night"


def format_money(value):
    return f"Rs. {int(value):,}"


def create_subscription(user_id, cook_id, plan):
    cook = get_cook_by_id(cook_id)
    if not cook:
        return False, "Cook not found."

    plan = plan or "weekly"
    multiplier = {"daily": 1, "weekly": 7, "monthly": 25}.get(plan, 7)
    amount = int(cook["price_from"] or 0) * multiplier
    today = current_datetime().date()
    meal_name = f"{cook['name']} meal plan"

    db = get_db()
    try:
        with db:
            db.execute(
                """
                INSERT INTO subscriptions (user_id, cook_id, plan, status, start_date, next_delivery, price_per_meal)
                VALUES (?, ?, ?, 'active', ?, ?, ?)
                """,
                (user_id, cook_id, plan, str(today), str(today), int(cook["price_from"] or 0)),
            )
            db.execute(
                """
                INSERT INTO orders (user_id, cook_id, meal_name, meal_type, amount, status, scheduled_for)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (user_id, cook_id, meal_name, plan.capitalize(), amount, str(today)),
            )
            db.execute("UPDATE cooks SET earnings_total = earnings_total + ? WHERE id = ?", (amount, cook_id))
    finally:
        db.close()

    return True, f"Payment successful. Subscription created for {cook['name']}."


def login_form():
    st.markdown('<div class="hf-card"><h2>Login</h2></div>', unsafe_allow_html=True)
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        user = get_user_by_email(email.strip().lower())
        if not user or not check_password_hash(user["password"], password):
            st.error("Invalid email or password.")
        else:
            st.session_state["user_id"] = user["id"]
            st.success(f"Welcome back, {user['name']}!")
            st.rerun()


def register_form():
    st.markdown('<div class="hf-card"><h2>Register</h2></div>', unsafe_allow_html=True)
    with st.form("register_form"):
        name = st.text_input("Full name")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password")
        gender = st.selectbox("Gender", ["Male", "Female", "Other", "Prefer not to say"])
        phone = st.text_input("Phone")
        address = st.text_input("Address")
        meal_pref = st.selectbox("Meal preference", ["Vegetarian", "Non-Vegetarian", "Both"])
        cuisine_pref = st.selectbox("Cuisine preference", ["South Indian", "North Indian", "Any"])
        submitted = st.form_submit_button("Create account")

    if submitted:
        if not name or not email or not password or not confirm:
            st.error("Please complete all required fields.")
        elif password != confirm:
            st.error("Passwords do not match.")
        elif get_user_by_email(email.strip().lower()):
            st.error("That email is already registered.")
        else:
            db = get_db()
            try:
                with db:
                    db.execute(
                        """
                        INSERT INTO users (name, email, password, phone, address, gender, meal_pref, cuisine_pref)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            name.strip(),
                            email.strip().lower(),
                            generate_password_hash(password),
                            phone,
                            address,
                            gender,
                            meal_pref,
                            cuisine_pref,
                        ),
                    )
                st.success("Registration successful. Please log in.")
            finally:
                db.close()


def profile_section(user):
    st.markdown('<div class="hf-card"><h2>My Profile</h2></div>', unsafe_allow_html=True)
    if not user:
        st.info("Please log in to manage your profile.")
        return

    with st.form("profile_form"):
        name = st.text_input("Full name", value=user["name"] or "")
        email = st.text_input("Email", value=user["email"] or "")
        phone = st.text_input("Phone", value=user["phone"] or "")
        address = st.text_input("Address", value=user["address"] or "")
        genders = ["Male", "Female", "Other", "Prefer not to say"]
        meal_prefs = ["Vegetarian", "Non-Vegetarian", "Both"]
        cuisine_prefs = ["South Indian", "North Indian", "Any"]
        gender = st.selectbox("Gender", genders, index=genders.index(user["gender"]) if user["gender"] in genders else 0)
        meal_pref = st.selectbox("Meal preference", meal_prefs, index=meal_prefs.index(user["meal_pref"]) if user["meal_pref"] in meal_prefs else 0)
        cuisine_pref = st.selectbox("Cuisine preference", cuisine_prefs, index=cuisine_prefs.index(user["cuisine_pref"]) if user["cuisine_pref"] in cuisine_prefs else 2)
        submitted = st.form_submit_button("Save profile")

    if submitted:
        db = get_db()
        try:
            with db:
                db.execute(
                    """
                    UPDATE users
                    SET name = ?, email = ?, phone = ?, address = ?, gender = ?, meal_pref = ?, cuisine_pref = ?
                    WHERE id = ?
                    """,
                    (name, email, phone, address, gender, meal_pref, cuisine_pref, user["id"]),
                )
            st.success("Profile saved successfully.")
            st.rerun()
        finally:
            db.close()


def subscriptions_section(user):
    st.markdown('<div class="hf-card"><h2>My Subscriptions</h2></div>', unsafe_allow_html=True)
    if not user:
        st.info("Please log in to view your subscriptions.")
        return

    subs = get_user_subscriptions(user["id"])
    active = [s for s in subs if s["status"] == "active"]
    past = [s for s in subs if s["status"] != "active"]
    st.write(f"Active: {len(active)} | Past: {len(past)}")
    for sub in active:
        with st.container(border=True):
            st.markdown(f"### {sub['cook_name']}")
            st.caption(f"{sub['plan'].title()} plan | Next delivery: {sub['next_delivery'] or 'Soon'}")
            st.write(f"Price per meal: {format_money(sub['price_per_meal'])}")


def orders_section(user):
    st.markdown('<div class="hf-card"><h2>Order History</h2></div>', unsafe_allow_html=True)
    if not user:
        st.info("Please log in to view your orders.")
        return

    orders = get_user_orders(user["id"])
    if not orders:
        st.info("No orders yet.")
        return

    for order in orders:
        with st.container(border=True):
            st.markdown(f"### {order['meal_name']}")
            st.caption(f"{order['cook_name']} | {order['meal_type'] or 'Meal'} | {order['status'].title()}")
            st.write(f"Scheduled for: {order['scheduled_for'] or 'N/A'}")
            st.write(f"Amount: {format_money(order['amount'])}")


def discover_section(user):
    st.markdown(
        """
        <div class="hf-card">
          <h2>Discover Cooks</h2>
          <div class="hf-sub">Verified home cooks near Hyderabad</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    q = st.text_input("Search cooks", placeholder="Search by name, cuisine, or location")
    meal_type = st.selectbox("Meal type", ["", "Veg", "Non-Veg"])
    cuisine = st.selectbox("Cuisine", ["", "Andhra", "South Indian", "North Indian", "Healthy / Diet", "Chinese"])

    if st.button("Filter"):
        cooks = list(get_all_cooks())
        if q:
            cooks = [
                c for c in cooks
                if q.lower() in (c["name"] or "").lower()
                or q.lower() in (c["cuisines"] or "").lower()
                or q.lower() in (c["location"] or "").lower()
            ]
        if meal_type:
            cooks = [c for c in cooks if (c["meal_types"] or "").lower() == meal_type.lower()]
        if cuisine:
            cooks = [c for c in cooks if cuisine.lower() in (c["cuisines"] or "").lower()]
        st.session_state["filtered_cooks"] = cooks

    cooks = st.session_state.get("filtered_cooks", list(get_all_cooks()))
    for cook in cooks:
        st.markdown(
            f"""
            <div class="cook-card">
              <div class="cook-title">{cook['name']}</div>
              <div class="cook-meta">{cook['cuisines']} | {cook['location']} | {cook['meal_types']}</div>
              <div>{cook['description'] or 'No description provided.'}</div>
              <div style="margin-top:0.65rem;"><strong>From {format_money(cook['price_from'])}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        if col1.button("View Profile", key=f"view_{cook['id']}"):
            st.session_state["selected_cook_id"] = cook["id"]
            st.session_state["page"] = "Cook Profile"
            st.rerun()
        if col2.button("Subscribe", key=f"pay_{cook['id']}"):
            st.session_state["selected_cook_id"] = cook["id"]
            st.session_state["page"] = "Payment"
            st.rerun()


def cook_profile_section():
    cook_id = st.session_state.get("selected_cook_id")
    cook = get_cook_by_id(cook_id) if cook_id else None
    st.markdown('<div class="hf-card"><h2>Cook Profile</h2></div>', unsafe_allow_html=True)
    if not cook:
        st.info("Select a cook from Discover Cooks to view the profile.")
        return

    st.markdown(
        f"""
        <div class="cook-card">
          <div class="cook-title">{cook['name']}</div>
          <div class="cook-meta">{cook['cuisines']} | {cook['location']} | {cook['meal_types']}</div>
          <p>{cook['description'] or 'No description provided.'}</p>
          <p><strong>Service area:</strong> {cook['service_area'] or 'Not specified'}</p>
          <p><strong>Delivery times:</strong> {cook['delivery_times'] or 'Not specified'}</p>
          <p><strong>Plan notes:</strong> {cook['plan_notes'] or 'Not specified'}</p>
          <p><strong>Starting price:</strong> {format_money(cook['price_from'])}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    if col1.button("Back to Discover"):
        st.session_state["page"] = "Discover Cooks"
        st.rerun()
    if col2.button("Pay / Subscribe now"):
        st.session_state["page"] = "Payment"
        st.rerun()


def payment_section(user):
    st.markdown('<div class="hf-card"><h2>Payment</h2></div>', unsafe_allow_html=True)
    if not user:
        st.info("Please log in to continue with payment.")
        return

    cook_id = st.session_state.get("selected_cook_id")
    cook = get_cook_by_id(cook_id) if cook_id else None
    if not cook:
        st.info("Select a cook first from Discover Cooks.")
        return

    st.markdown(
        f"""
        <div class="cook-card">
          <div class="cook-title">{cook['name']}</div>
          <div class="cook-meta">{cook['cuisines']} | {cook['location']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    plan = st.selectbox("Choose plan", ["daily", "weekly", "monthly"], index=1)
    payment_method = st.radio("Payment method", ["UPI", "Card", "Wallet"], horizontal=True)
    multiplier = {"daily": 1, "weekly": 7, "monthly": 25}.get(plan, 7)
    total_amount = int(cook["price_from"] or 0) * multiplier

    st.write(f"Price per meal: {format_money(cook['price_from'])}")
    st.write(f"Estimated total: {format_money(total_amount)}")

    with st.form("payment_form"):
        card_name = ""
        expiry = ""
        cvv = ""
        if payment_method == "UPI":
            payment_ref = st.text_input("UPI ID", placeholder="name@upi")
        elif payment_method == "Card":
            payment_ref = st.text_input("Card number", placeholder="1234 5678 9012 3456")
            card_name = st.text_input("Card holder name")
            expiry = st.text_input("Expiry", placeholder="MM/YY")
            cvv = st.text_input("CVV", type="password")
        else:
            payment_ref = st.selectbox("Select wallet", ["Paytm", "PhonePe", "Google Pay", "Amazon Pay"])
        submitted = st.form_submit_button("Pay Now")

    if submitted:
        if payment_method == "UPI" and not payment_ref:
            st.error("Please enter your UPI ID.")
            return
        if payment_method == "Card" and not payment_ref:
            st.error("Please enter your card number.")
            return
        if payment_method == "Card" and (not card_name or not expiry or not cvv):
            st.error("Please complete the card details.")
            return
        ok, msg = create_subscription(user["id"], cook["id"], plan)
        if ok:
            st.success("Payment successful.")
            st.success("Transaction successful.")
            st.success(msg)
            st.session_state["page"] = "Subscriptions"
            st.rerun()
        else:
            st.error(msg)

    if st.button("Back to Discover", key="payment_back"):
        st.session_state["page"] = "Discover Cooks"
        st.rerun()


def home_section(user):
    now = current_datetime()
    st.markdown(
        f"""
        <div class="hf-hero">
          <div class="hf-brand">{APP_TITLE}</div>
          <div class="hf-sub">{greeting()}{', ' + user['name'] if user else ''}</div>
          <div style="margin-top:0.3rem;color:#8a7d73;">{now.strftime("%A, %d %B %Y · %I:%M %p")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if user:
        subs = get_user_subscriptions(user["id"])
        orders = get_user_orders(user["id"])
        active = [s for s in subs if s["status"] == "active"]
        spent = sum(o["amount"] for o in orders)
        next_delivery = active[0]["next_delivery"] if active else "None"
        cols = st.columns(4)
        cols[0].metric("Active subscriptions", len(active))
        cols[1].metric("Meals this month", len(orders))
        cols[2].metric("Total spent", format_money(spent))
        cols[3].metric("Next delivery", next_delivery)
    else:
        cols = st.columns(3)
        cols[0].metric("Approved cooks", len(get_all_cooks()))
        cols[1].metric("Ready to order", "Yes")
        cols[2].metric("Login required", "No")


def main():
    init_db()
    st.set_page_config(page_title=APP_TITLE, page_icon="🍱", layout="wide")
    apply_styles()

    if "page" not in st.session_state:
        st.session_state["page"] = "Home"

    user = current_user()
    pages = [
        "Home",
        "Discover Cooks",
        "Cook Profile",
        "Payment",
        "Subscriptions",
        "Orders",
        "Profile",
        "Login",
        "Register",
    ]

    with st.sidebar:
        st.markdown(f'<div class="hf-brand" style="font-size:1.6rem;">{APP_TITLE}</div>', unsafe_allow_html=True)
        st.write(f"{greeting()}{', ' + user['name'] if user else ''}")
        st.caption(current_datetime().strftime("%A, %d %B %Y · %I:%M %p"))
        st.session_state["page"] = st.radio(
            "Navigate",
            pages,
            index=pages.index(st.session_state["page"]) if st.session_state["page"] in pages else 0,
        )

    user = current_user()
    page = st.session_state["page"]
    if page == "Home":
        home_section(user)
    elif page == "Discover Cooks":
        discover_section(user)
    elif page == "Cook Profile":
        cook_profile_section()
    elif page == "Payment":
        payment_section(user)
    elif page == "Subscriptions":
        subscriptions_section(user)
    elif page == "Orders":
        orders_section(user)
    elif page == "Profile":
        profile_section(user)
    elif page == "Login":
        login_form()
    elif page == "Register":
        register_form()


if __name__ == "__main__":
    main()
