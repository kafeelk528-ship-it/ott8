import os
import requests
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)

# Secret key from environment
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")

# Telegram Bot Credentials (from environment)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =============================
#           DEMO PRODUCTS
# =============================
PLANS = [
    {"id": 1, "name": "Netflix Premium", "price": 199, "logo": "netflix.png",
     "desc": "4K UHD • 4 Screens • 30 Days", "available": 12},
    {"id": 2, "name": "Amazon Prime Video", "price": 149, "logo": "prime.png",
     "desc": "Full HD • All Devices • 30 Days", "available": 19},
    {"id": 3, "name": "Disney+ Hotstar", "price": 299, "logo": "hotstar.png",
     "desc": "Sports + Movies + Web Series", "available": 5},
    {"id": 4, "name": "Sony LIV Premium", "price": 129, "logo": "sonyliv.png",
     "desc": "Full HD • Originals • TV Shows", "available": 9},
]


def get_plan(plan_id):
    return next((p for p in PLANS if p["id"] == plan_id), None)


# =============================
#           ROUTES
# =============================

@app.route("/")
def home():
    return render_template("index.html", plans=PLANS)


@app.route("/plans")
def plans_page():
    return render_template("plans.html", plans=PLANS)


@app.route("/plan/<int:plan_id>")
def plan_details(plan_id):
    p = get_plan(plan_id)
    if not p:
        return "Plan not found", 404
    return render_template("plan-details.html", plan=p)


# =============================
#           CART
# =============================
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
    total = sum(item["price"] for item in cart_items)
    return render_template("cart.html", cart=cart_items, total=total)


@app.route("/cart/remove/<int:plan_id>")
def remove_cart(plan_id):
    if "cart" in session and plan_id in session["cart"]:
        session["cart"].remove(plan_id)
        session.modified = True
    return redirect(url_for("cart_page"))


# =============================
#         UTR PAYMENT
# =============================
@app.route("/payment")
def payment_page():
    total = 0
    cart_items = []

    if "cart" in session:
        cart_items = [get_plan(pid) for pid in session["cart"]]
        total = sum(item["price"] for item in cart_items)

    return render_template("payment.html", total=total)


@app.route("/submit_utr", methods=["POST"])
def submit_utr():
    utr = request.form.get("utr")
    total = request.form.get("total")
    cart_items = [get_plan(pid) for pid in session.get("cart", [])]

    # Build message
    text = "📢 *New Payment Submitted*\n\n"
    text += f"💰 *Amount:* ₹{total}\n"
    text += f"🔢 *UTR:* {utr}\n"
    text += "🛒 *Items:*\n"

    for item in cart_items:
        text += f"• {item['name']} — ₹{item['price']}\n"

    text += "\nPlease verify manually."

    # Send Telegram Notification
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram error:", e)

    # Clear cart after submission
    session.pop("cart", None)

    return render_template("success.html")


# =============================
#       CONTACT PAGE
# =============================
@app.route("/contact")
def contact_page():
    return render_template("contact.html")


# =============================
#     ADMIN LOGIN & PORTAL
# =============================
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["username"] == os.getenv("ADMIN_USER") \
                and request.form["password"] == os.getenv("ADMIN_PASS"):
            session["admin"] = True
            return redirect("/admin/dashboard")
        return render_template("admin.html", error=True)

    return render_template("admin.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect("/admin")
    return render_template("dashboard.html", plans=PLANS)


@app.route("/admin/update/<int:plan_id>", methods=["POST"])
def admin_update(plan_id):
    if not session.get("admin"):
        return redirect("/admin")

    p = get_plan(plan_id)
    if p:
        p["price"] = int(request.form.get("price"))
        p["available"] = int(request.form.get("available"))

    return redirect("/admin/dashboard")


# =============================
#       TELEGRAM DEBUG ROUTE
# =============================
@app.route("/_debug/telegram-test")
def telegram_test():
    token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID

    if not token or not chat_id:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN or CHAT_ID missing"}, 400

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": "Test message from OTT App Debug Route!",
        "parse_mode": "Markdown"
    })

    try:
        return resp.json()
    except:
        return {"raw": resp.text}


# =============================
#         MAIN
# =============================
if __name__ == "__main__":
    app.run(debug=True)
