import os
from flask import Flask, render_template, redirect, url_for, request, session, flash
from datetime import datetime
import requests

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback-key")

# Telegram Bot Settings
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Domain for redirects
YOUR_DOMAIN = os.getenv("YOUR_DOMAIN", "http://localhost:5000")

# ----------------------------
# Demo Plans (no DB needed)
# ----------------------------
PLANS = [
    {"id": 1, "name": "Netflix Premium", "price": 199, "stock": 10, "logo": "netflix.png", "desc": "4K UHD • 4 Screens • 30 Days"},
    {"id": 2, "name": "Amazon Prime Video", "price": 149, "stock": 8, "logo": "prime.png", "desc": "Full HD • All Devices • 30 Days"},
    {"id": 3, "name": "Disney+ Hotstar", "price": 299, "stock": 5, "logo": "hotstar.png", "desc": "Sports + Movies + Web Series"},
    {"id": 4, "name": "Sony LIV Premium", "price": 129, "stock": 12, "logo": "sonyliv.png", "desc": "Full HD • Originals • TV Shows"},
]


def get_plan(plan_id):
    return next((p for p in PLANS if p["id"] == plan_id), None)


# ----------------------------
# Home Page
# ----------------------------
@app.route("/")
def home():
    return render_template("index.html", plans=PLANS)


# ----------------------------
# Plans Page
# ----------------------------
@app.route("/plans")
def plans_page():
    return render_template("plans.html", plans=PLANS)


# ----------------------------
# Plan Details Page
# ----------------------------
@app.route("/plan/<int:plan_id>")
def plan_details(plan_id):
    plan = get_plan(plan_id)
    if not plan:
        return "Plan Not Found", 404
    return render_template("plan-details.html", plan=plan)


# ----------------------------
# Cart System
# ----------------------------
@app.route("/add-to-cart/<int:plan_id>")
def add_to_cart(plan_id):
    if "cart" not in session:
        session["cart"] = []
    if plan_id not in session["cart"]:
        session["cart"].append(plan_id)
        session.modified = True
    return redirect(url_for("cart_page"))


@app.route("/cart")
def cart_page():
    cart_items = [get_plan(pid) for pid in session.get("cart", [])]
    cart_items = [c for c in cart_items if c]
    total = sum(item["price"] for item in cart_items)
    return render_template("cart.html", cart=cart_items, total=total)


@app.route("/cart/remove/<int:plan_id>")
def remove_cart(plan_id):
    if "cart" in session and plan_id in session["cart"]:
        session["cart"].remove(plan_id)
        session.modified = True
    return redirect(url_for("cart_page"))


# ----------------------------
# CHECKOUT PAGE (select payment)
# ----------------------------
@app.route("/checkout")
def checkout():
    cart_items = [get_plan(pid) for pid in session.get("cart", [])]
    cart_items = [c for c in cart_items if c]
    if not cart_items:
        flash("Cart is Empty!", "warning")
        return redirect(url_for("plans_page"))

    total = sum(item["price"] for item in cart_items)
    return render_template("checkout.html", cart=cart_items, total=total)


# -------------------------------------
# NEW: QR PAYMENT PAGE (GET ONLY)
# -------------------------------------
@app.route("/checkout/qr")
def checkout_qr():
    cart = session.get("cart", [])
    cart_items = [get_plan(pid) for pid in cart]
    cart_items = [c for c in cart_items if c]

    if not cart_items:
        flash("Cart is empty.", "info")
        return redirect(url_for("plans_page"))

    total = sum(item["price"] for item in cart_items)
    qr_path = url_for('static', filename='img/qr.png')

    return render_template("pay_manual_cart.html", cart=cart_items, total=total, qr_path=qr_path)


# -------------------------------------
# HANDLE UTR SUBMISSION (QR PAYMENT)
# -------------------------------------
@app.route("/submit-utr", methods=["POST"])
def submit_utr():
    utr = request.form.get("utr")
    if not utr:
        flash("UTR is required!", "danger")
        return redirect(url_for("checkout_qr"))

    cart = session.get("cart", [])
    cart_items = [get_plan(pid) for pid in cart]
    cart_items = [c for c in cart_items if c]

    total = sum(item["price"] for item in cart_items)
    items_text = ", ".join([item["name"] for item in cart_items])

    # Telegram Notification
    if BOT_TOKEN and CHAT_ID:
        msg = f"""
🟢 *New Payment Request*  
----------------------------------
📦 *Items*: {items_text}  
💰 *Total*: ₹{total}  
🔢 *UTR Code*: `{utr}`  
⏳ Pending Confirmation
"""
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        )

    session.pop("cart", None)
    return render_template("success.html")


# ----------------------------
# Contact Page
# ----------------------------
@app.route("/contact")
def contact_page():
    return render_template("contact.html")


# ----------------------------
# Admin Login (Simple Demo)
# ----------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_pass = os.getenv("ADMIN_PASS", "123")

    if request.method == "POST":
        if request.form["username"] == admin_user and request.form["password"] == admin_pass:
            session["admin"] = True
            return redirect("/admin/dashboard")
        return render_template("admin.html", error=True)

    return render_template("admin.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect("/admin")
    return render_template("dashboard.html", plans=PLANS)


# ----------------------------
# Run App
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
