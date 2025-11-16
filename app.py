from flask import (
    Flask, render_template, redirect, url_for,
    request, session, flash
)
import os
import requests

app = Flask(__name__)

# -------------------------------
# ENVIRONMENT VARIABLES
# -------------------------------
app.secret_key = os.environ.get("SECRET_KEY", "dev123")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# -------------------------------
# PRODUCTS (IN-MEMORY DATABASE)
# -------------------------------
PLANS = [
    {
        "id": 1,
        "name": "Netflix Premium",
        "price": 199,
        "logo": "netflix.png",
        "available": 10,
        "desc": "4K UHD • 30 Days"
    },
    {
        "id": 2,
        "name": "Amazon Prime Video",
        "price": 149,
        "logo": "prime.png",
        "available": 8,
        "desc": "All Devices • 30 Days"
    },
    {
        "id": 3,
        "name": "Disney+ Hotstar",
        "price": 299,
        "logo": "hotstar.png",
        "available": 12,
        "desc": "Movies + Sports + Web Series"
    }
]


# -------------------------------
# AUTH HELPERS
# -------------------------------
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def secure(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin")
        return f(*args, **kwargs)
    return secure


# -------------------------------
# ROUTES - PUBLIC
# -------------------------------
@app.route("/")
def home():
    return render_template("index.html", plans=PLANS)


@app.route("/plans")
def plans_page():
    return render_template("plans.html", plans=PLANS)


@app.route("/plan/<int:plan_id>")
def plan_details(plan_id):
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        return "Plan Not Found", 404
    return render_template("plan-details.html", plan=plan)


# -------------------------------
# CART SYSTEM
# -------------------------------
@app.route("/add-to-cart/<int:plan_id>")
def add_to_cart(plan_id):
    session.setdefault("cart", [])
    if plan_id not in session["cart"]:
        session["cart"].append(plan_id)
    session.modified = True
    return redirect("/cart")


@app.route("/cart")
def cart_page():
    cart_ids = session.get("cart", [])
    cart_items = [p for p in PLANS if p["id"] in cart_ids]
    total = sum(p["price"] for p in cart_items)
    return render_template("cart.html", cart=cart_items, total=total)


@app.route("/cart/remove/<int:plan_id>")
def remove_item(plan_id):
    if "cart" in session and plan_id in session["cart"]:
        session["cart"].remove(plan_id)
        session.modified = True
    return redirect("/cart")


# -------------------------------
# PAYMENT PAGE + UTR SUBMISSION
# -------------------------------
@app.route("/checkout")
def checkout():
    cart_ids = session.get("cart", [])
    cart_items = [p for p in PLANS if p["id"] in cart_ids]
    total = sum(p["price"] for p in cart_items)

    if total == 0:
        return redirect("/cart")

    return render_template("payment.html", total=total)


@app.route("/submit-utr", methods=["POST"])
def submit_utr():
    utr = request.form.get("utr")
    email = request.form.get("email")
    amount = request.form.get("amount")

    if not utr or not email:
        flash("Please enter UTR and Email", "danger")
        return redirect("/checkout")

    # Telegram message
    msg = f"""
📢 *New Payment Request*
-------------------------
💰 Amount: ₹{amount}
🔢 UTR Number: {utr}
📧 Email: {email}
🛒 Customer wants activation ✔️
"""

    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                         params={
                             "chat_id": TELEGRAM_CHAT_ID,
                             "text": msg,
                             "parse_mode": "Markdown"
                         })
        except:
            pass

    session.pop("cart", None)

    return render_template("success.html")


# -------------------------------
# CONTACT
# -------------------------------
@app.route("/contact")
def contact_page():
    return render_template("contact.html")


# -------------------------------
# ADMIN LOGIN
# -------------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["username"] == os.environ.get("ADMIN_USER", "admin") \
           and request.form["password"] == os.environ.get("ADMIN_PASS", "123"):
            session["admin"] = True
            return redirect("/admin/dashboard")
        return render_template("admin.html", error=True)
    return render_template("admin.html")


# -------------------------------
# ADMIN DASHBOARD
# -------------------------------
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template("dashboard.html", plans=PLANS)


@app.route("/admin/add-plan", methods=["POST"])
@admin_required
def admin_add_plan():
    new_id = max([p["id"] for p in PLANS]) + 1 if PLANS else 1
    PLANS.append({
        "id": new_id,
        "name": request.form.get("name"),
        "price": int(request.form.get("price")),
        "logo": request.form.get("logo"),
        "available": int(request.form.get("available")),
        "desc": request.form.get("desc")
    })
    return redirect("/admin/dashboard")


@app.route("/admin/delete-plan/<int:plan_id>", methods=["POST"])
@admin_required
def admin_delete_plan(plan_id):
    global PLANS
    PLANS = [p for p in PLANS if p["id"] != plan_id]
    return redirect("/admin/dashboard")


# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)
