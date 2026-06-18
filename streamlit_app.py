from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from werkzeug.security import check_password_hash, generate_password_hash

from homefeast_data import (
    get_all_cooks,
    get_db,
    get_user_by_email,
    get_user_by_id,
    get_user_orders,
    get_user_subscriptions,
    init_db,
)


APP_TITLE = "HomeFeast"


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


def login_form():
    st.subheader("Login")
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
    st.subheader("Register")
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
    st.subheader("My Profile")
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
    st.subheader("My Subscriptions")
    if not user:
        st.info("Please log in to view your subscriptions.")
        return

    subs = get_user_subscriptions(user["id"])
    active = [s for s in subs if s["status"] == "active"]
    past = [s for s in subs if s["status"] != "active"]
    st.write(f"Active: {len(active)} | Past: {len(past)}")
    for sub in active:
        st.markdown(f"**{sub['cook_name']}**")
        st.caption(f"{sub['plan'].title()} plan | Next delivery: {sub['next_delivery'] or 'Soon'}")
        st.write(f"Price per meal: {format_money(sub['price_per_meal'])}")
        st.divider()


def orders_section(user):
    st.subheader("Order History")
    if not user:
        st.info("Please log in to view your orders.")
        return

    orders = get_user_orders(user["id"])
    if not orders:
        st.info("No orders yet.")
        return

    for order in orders:
        st.markdown(f"**{order['meal_name']}**")
        st.caption(f"{order['cook_name']} | {order['meal_type'] or 'Meal'} | {order['status'].title()}")
        st.write(f"Scheduled for: {order['scheduled_for'] or 'N/A'}")
        st.write(f"Amount: {format_money(order['amount'])}")
        st.divider()


def discover_section(user):
    st.subheader("Discover Cooks")
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
        with st.container(border=True):
            st.markdown(f"### {cook['name']}")
            st.caption(f"{cook['cuisines']} | {cook['location']} | {cook['meal_types']}")
            st.write(cook["description"] or "No description provided.")
            st.write(f"From {format_money(cook['price_from'])}")


def home_section(user):
    now = current_datetime()
    st.title(APP_TITLE)
    st.subheader(f"{greeting()}{', ' + user['name'] if user else ''}")
    st.caption(now.strftime("%A, %d %B %Y · %I:%M %p"))

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

    if "page" not in st.session_state:
        st.session_state["page"] = "Home"

    user = current_user()
    with st.sidebar:
        st.title(APP_TITLE)
        st.write(f"{greeting()}{', ' + user['name'] if user else ''}")
        st.caption(current_datetime().strftime("%A, %d %B %Y · %I:%M %p"))
        page = st.radio(
            "Navigate",
            ["Home", "Discover Cooks", "Subscriptions", "Orders", "Profile", "Login", "Register"],
            index=["Home", "Discover Cooks", "Subscriptions", "Orders", "Profile", "Login", "Register"].index(st.session_state["page"]),
        )
        st.session_state["page"] = page

    user = current_user()
    if st.session_state["page"] == "Home":
        home_section(user)
    elif st.session_state["page"] == "Discover Cooks":
        discover_section(user)
    elif st.session_state["page"] == "Subscriptions":
        subscriptions_section(user)
    elif st.session_state["page"] == "Orders":
        orders_section(user)
    elif st.session_state["page"] == "Profile":
        profile_section(user)
    elif st.session_state["page"] == "Login":
        login_form()
    elif st.session_state["page"] == "Register":
        register_form()


if __name__ == "__main__":
    main()
