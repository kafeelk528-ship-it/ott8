import os
from flask import Flask, render_template, redirect, request, session, url_for, flash
import requests

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "test123")

# Telegram Settings
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# -----------------------------
# PRODUCT LIST
# -----------------------------
PLANS = [
    {
        "id": 1,
        "name": "Netflix Premium",
        "price": 199,
        "logo": "img/netflix.png",
        "desc": "4K UHD • 4 Screens • 30 Days",
        "available": 10
    },
    {
        "id": 2,
        "name": "Amazon Prime Video",
        "price": 149,
        "logo": "img/prime.png",
        "desc": "Full HD • All Devices • 30 Days",
        "available": 12
    },
    {
        "id": 3,
        "name": "Disney+ Hotstar",
        "price": 299,
        "logo": "img/hotstar.png",
        "desc": "Sports + Movies + Web Series",
        "available": 5
    },
    {
        "id": 4,
        "name": "Sony LIV Premium",
        "price": 129,
        "logo": "img/sonyliv.png",
        "desc": "Full HD • Originals • TV Shows",
        "available": 9
    }
]


# ---------------------------------
# HOME
# ---------------------------------
@app.route("/")
def home():
    return render_template("index.html", plans=PLANS)


# ---------------------------------
# PLANS PAGE
# ---------------------------------
@app.route("/plans")
def plans_page():
    return render_template("plans.html", plans=PLANS)


# ---------------------------------
# PLAN DETAILS
# ---------------------------------
@app.route("/plan/<int:plan_id>")
def plan_details(plan_id):
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        return "Plan Not Found", 404
    return render_template("plan-details.html", plan=plan)


# ---------------------------------
# ADD TO CART
# ---------------------------------
@app.route("/add-to-cart/<int:plan_id>")
def add_to_cart(plan_id):
    if "cart" not in session:
        session["cart"] = []

    if plan_id not in session["cart"]:
        session["cart"].append(plan_id)

    session.modified = True
    flash("Added to cart")
    return redirect("/cart")


# ---------------------------------
# CART PAGE
# ---------------------------------
@app.route("/cart")
def cart_page():
    cart_items = [p for p in PLANS if p["id"] in session.get("cart", [])]
    total = sum(item["price"] for item in cart_items)
    return render_template("cart.html", cart=cart_items, total=total)


# ---------------------------------
# REMOVE ITEM
# ---------------------------------
@app.route("/cart/remove/<int:plan_id>")
def remove_cart(plan_id):
    if "cart" in session and plan_id in session["cart"]:
        session["cart"].remove(plan_id)
        session.modified = True
    return redirect("/cart")


# ---------------------------------
# PAYMENT PAGE (SHOW QR + UTR FORM)
# ---------------------------------
@app.route("/payment")
def payment_page():
    return render_template("payment.html")


# ---------------------------------
# UTR SUBMIT
# ---------------------------------
@app.route("/submit-utr", methods=["POST"])
def submit_utr():
    utr = request.form.get("utr")
    name = request.form.get("name")

    message = f"📢 *New Payment Submitted*\n\n👤 Name: {name}\n💳 UTR: `{utr}`"

    if BOT_TOKEN and CHAT_ID:
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
        )

    session.pop("cart", None)
    return render_template("success.html")


# ---------------------------------
# CONTACT PAGE
# ---------------------------------
@app.route("/contact")
def contact_page():
    return render_template("contact.html")


# ---------------------------------
# ADMIN LOGIN
# ---------------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_page():
    return render_template("admin.html")


if __name__ == "__main__":
    app.run(debug=True)
