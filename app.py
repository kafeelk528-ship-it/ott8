import os
from flask import Flask, render_template, redirect, url_for, request, session, flash
import requests

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "tempkey123")

# Telegram ENV
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

# ----------------------------
# Product List
# ----------------------------
PLANS = [
    {"id": 1, "name": "Netflix Premium", "price": 199, "logo": "netflix.png", "desc": "4K UHD • 30 Days", "stock": 10},
    {"id": 2, "name": "Amazon Prime Video", "price": 149, "logo": "prime.png", "desc": "HD • 30 Days", "stock": 12},
    {"id": 3, "name": "Disney+ Hotstar", "price": 299, "logo": "hotstar.png", "desc": "Sports + Movies", "stock": 8},
    {"id": 4, "name": "Sony LIV Premium", "price": 129, "logo": "sonyliv.png", "desc": "TV Shows + Movies", "stock": 15},
    {"id": 5, "name": "Zee5 Premium", "price": 99, "logo": "zee5.png", "desc": "HD Content", "stock": 20},
]

# ----------------------------
# Home
# ----------------------------
@app.route("/")
def home():
    return render_template("index.html", plans=PLANS)

@app.route("/plans")
def plans_page():
    return render_template("plans.html", plans=PLANS)

@app.route("/plan/<int:plan_id>")
def plan_details(plan_id):
    item = next((p for p in PLANS if p["id"] == plan_id), None)
    if not item:
        return "Not Found", 404
    return render_template("plan-details.html", plan=item)

# ----------------------------
# Cart
# ----------------------------
@app.route("/add-to-cart/<int:plan_id>")
def add_to_cart(plan_id):
    session.setdefault("cart", [])

    if plan_id not in session["cart"]:
        session["cart"].append(plan_id)
    session.modified = True
    flash("Added to cart!")
    return redirect(url_for("cart_page"))

@app.route("/cart")
def cart_page():
    items = [p for p in PLANS if p["id"] in session.get("cart", [])]
    total = sum(i["price"] for i in items)
    return render_template("cart.html", cart=items, total=total)

@app.route("/remove/<int:plan_id>")
def remove(plan_id):
    if "cart" in session and plan_id in session["cart"]:
        session["cart"].remove(plan_id)
    return redirect(url_for("cart_page"))

# ----------------------------
# Payment Page
# ----------------------------
@app.route("/payment")
def payment_page():
    return render_template("payment.html")

# ----------------------------
# UTR Submission
# ----------------------------
@app.route("/submit_utr", methods=["POST"])
def submit_utr():
    utr = request.form.get("utr")
    name = request.form.get("name")
    phone = request.form.get("phone")

    msg = f"📢 *New Payment UTR Received*\n\n👤 Name: {name}\n📞 Phone: {phone}\n💳 UTR: {utr}"

    if BOT_TOKEN and CHAT_ID:
        requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            params={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        )

    session.pop("cart", None)
    return render_template("success.html")

# ----------------------------
# Admin
# ----------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["username"] == os.getenv("ADMIN_USER") and request.form["password"] == os.getenv("ADMIN_PASS"):
            session["admin"] = True
            return redirect("/admin/dashboard")
        return render_template("admin.html", error=True)
    return render_template("admin.html")

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect("/admin")
    return render_template("dashboard.html", plans=PLANS)

if __name__ == "__main__":
    app.run(debug=True)
