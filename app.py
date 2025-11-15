# app.py - Updated with admin edit/add/delete + plans persistence (plans.json)
import os
import json
from datetime import datetime
from flask import (
    Flask, render_template, redirect, url_for, request,
    session, flash, send_from_directory
)
import requests

# ---------- App config ----------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")
DATA_FILE = os.path.join(os.path.dirname(__file__), "plans.json")

# Telegram config (optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Admin credentials from env (fallback defaults)
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "12345")

# Domain (optional)
YOUR_DOMAIN = os.getenv("YOUR_DOMAIN", "").rstrip("/")

# ---------- Default demo plans ----------
DEFAULT_PLANS = [
    {"id": 1, "name": "Netflix Premium", "price": 199, "stock": 10, "logo": "netflix.png", "desc": "4K UHD • 4 Screens • 30 Days"},
    {"id": 2, "name": "Amazon Prime Video", "price": 149, "stock": 8, "logo": "prime.png", "desc": "Full HD • All Devices • 30 Days"},
    {"id": 3, "name": "Disney+ Hotstar", "price": 299, "stock": 5, "logo": "hotstar.png", "desc": "Sports + Movies + Web Series"},
    {"id": 4, "name": "Sony LIV Premium", "price": 129, "stock": 12, "logo": "sonyliv.png", "desc": "Full HD • Originals • TV Shows"},
]

# ---------- Load / Save plans ----------
def load_plans():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Validate it is a list of dicts
                if isinstance(data, list):
                    return data
        except Exception as e:
            app.logger.warning("Failed to load plans.json: %s", e)
    # fallback to default
    return DEFAULT_PLANS.copy()

def save_plans(plans):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(plans, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        app.logger.exception("Failed to save plans.json: %s", e)
        return False

PLANS = load_plans()

def get_plan(plan_id):
    return next((p for p in PLANS if int(p.get("id")) == int(plan_id)), None)

def next_plan_id():
    if not PLANS:
        return 1
    return max(int(p["id"]) for p in PLANS) + 1

# ---------- Telegram notification ----------
def send_telegram_notification(text):
    token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID
    if not token or not chat_id:
        app.logger.debug("Telegram not configured; skipping.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text})
        resp.raise_for_status()
        return True
    except Exception as e:
        app.logger.exception("Telegram notify failed: %s", e)
        return False

# ---------- Routes - public ----------
@app.route("/")
def home():
    return render_template("index.html", plans=PLANS)

@app.route("/plans")
def plans_page():
    return render_template("plans.html", plans=PLANS)

@app.route("/plan/<int:plan_id>")
def plan_details(plan_id):
    plan = get_plan(plan_id)
    if not plan:
        return "Plan Not Found", 404
    return render_template("plan-details.html", plan=plan)

# ---------- Cart ----------
@app.route("/add-to-cart/<int:plan_id>")
def add_to_cart(plan_id):
    plan = get_plan(plan_id)
    if not plan:
        flash("Invalid plan", "danger")
        return redirect(url_for("plans_page"))

    if int(plan.get("stock", 0)) <= 0:
        flash("Item out of stock", "danger")
        return redirect(url_for("plans_page"))

    cart = session.get("cart", [])
    if plan_id not in cart:
        cart.append(plan_id)
        session["cart"] = cart
        session.modified = True
        flash("Added to cart", "success")
    else:
        flash("Already in cart", "info")
    return redirect(url_for("cart_page"))

@app.route("/cart")
def cart_page():
    cart_items = [get_plan(pid) for pid in session.get("cart", [])]
    cart_items = [c for c in cart_items if c]
    total = sum(int(item.get("price", 0)) for item in cart_items)
    return render_template("cart.html", cart=cart_items, total=total)

@app.route("/cart/remove/<int:plan_id>")
def remove_cart(plan_id):
    cart = session.get("cart", [])
    if plan_id in cart:
        cart.remove(plan_id)
        session["cart"] = cart
        session.modified = True
        flash("Removed from cart", "info")
    return redirect(url_for("cart_page"))

# ---------- Checkout selection ----------
@app.route("/checkout")
def checkout():
    cart_items = [get_plan(pid) for pid in session.get("cart", [])]
    cart_items = [c for c in cart_items if c]
    if not cart_items:
        flash("Cart is empty", "info")
        return redirect(url_for("plans_page"))
    total = sum(int(item.get("price", 0)) for item in cart_items)
    return render_template("checkout.html", cart=cart_items, total=total)

# ---------- Dedicated QR checkout page (GET) ----------
@app.route("/checkout/qr")
def checkout_qr():
    cart = session.get("cart", [])
    cart_items = [get_plan(pid) for pid in cart]
    cart_items = [c for c in cart_items if c]
    if not cart_items:
        flash("Cart is empty.", "info")
        return redirect(url_for("plans_page"))
    total = sum(int(item.get("price", 0)) for item in cart_items)
    # expects static/img/qr.png exists
    qr_path = url_for('static', filename='img/qr.png')
    return render_template("pay_manual_cart.html", cart=cart_items, total=total, qr_path=qr_path)

# ---------- Submit UTR (QR payment) ----------
@app.route("/submit-utr", methods=["POST"])
def submit_utr():
    utr = request.form.get("utr", "").strip()
    buyer_name = request.form.get("buyer_name", "").strip()
    buyer_email = request.form.get("buyer_email", "").strip()

    if not utr:
        flash("Please enter UTR number", "danger")
        return redirect(url_for("checkout_qr"))

    cart = session.get("cart", [])
    cart_items = [get_plan(pid) for pid in cart]
    cart_items = [c for c in cart_items if c]
    total = sum(int(item.get("price", 0)) for item in cart_items)
    items_text = ", ".join([item.get("name", "") for item in cart_items])

    # Notify via Telegram
    text = (
        f"📥 New Manual Payment Submission\n"
        f"Items: {items_text}\n"
        f"Amount: ₹{total}\n"
        f"UTR: {utr}\n"
        f"Buyer: {buyer_name or '-'} ({buyer_email or '-'})\n"
        f"Time: {datetime.utcnow().isoformat()} UTC\n"
    )
    send_telegram_notification = send_telegram_notification = send_telegram_notification if 'send_telegram_notification' in globals() else None
    # Use the helper function above (if configured)
    send_telegram_notification(text) if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID else app.logger.debug("Telegram not configured")

    # Clear cart and show success
    session.pop("cart", None)
    flash("UTR submitted for verification. Owner will verify and deliver.", "success")
    return render_template("success.html")

# ---------- Contact ----------
@app.route("/contact")
def contact_page():
    return render_template("contact.html")

# ---------- Admin simple auth ----------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USER and request.form.get("password") == ADMIN_PASS:
            session["admin"] = True
            flash("Logged in as admin", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials", "danger")
        return render_template("admin.html", error=True)
    return render_template("admin.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    flash("Logged out", "info")
    return redirect(url_for("home"))

def admin_required_redirect():
    if not session.get("admin"):
        flash("Login required", "info")
        return redirect(url_for("admin_login"))
    return None

# ---------- Admin dashboard ----------
@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    return render_template("dashboard.html", plans=PLANS)

# ---------- Admin: update plan ----------
@app.route("/admin/plan/<int:plan_id>/update", methods=["POST"])
def admin_update_plan(plan_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    plan = get_plan(plan_id)
    if not plan:
        flash("Plan not found", "danger")
        return redirect(url_for("admin_dashboard"))

    # Extract and validate form values
    name = request.form.get("name") or plan.get("name")
    logo = request.form.get("logo") or plan.get("logo", "")
    desc = request.form.get("description") or request.form.get("desc") or plan.get("desc", plan.get("description", ""))
    try:
        price = int(request.form.get("price", plan.get("price", 0)))
    except:
        price = plan.get("price", 0)
    try:
        stock = int(request.form.get("stock", plan.get("stock", 0)))
    except:
        stock = plan.get("stock", 0)

    # Update plan object
    plan.update({
        "name": name,
        "logo": logo,
        "desc": desc,
        "price": price,
        "stock": stock
    })

    # Persist
    save_plans(PLANS)
    flash("Plan updated", "success")
    return redirect(url_for("admin_dashboard"))

# ---------- Admin: add plan ----------
@app.route("/admin/plan/add", methods=["POST"])
def admin_add_plan():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    name = request.form.get("name", "").strip()
    logo = request.form.get("logo", "").strip()
    desc = request.form.get("description", "").strip()
    try:
        price = int(request.form.get("price", 0))
    except:
        price = 0
    try:
        stock = int(request.form.get("stock", 0))
    except:
        stock = 0

    if not name:
        flash("Name required", "danger")
        return redirect(url_for("admin_dashboard"))

    new_id = next_plan_id()
    new_plan = {"id": new_id, "name": name, "price": price, "stock": stock, "logo": logo, "desc": desc}
    PLANS.append(new_plan)
    save_plans(PLANS)
    flash("Plan added", "success")
    return redirect(url_for("admin_dashboard"))

# ---------- Admin: delete plan ----------
@app.route("/admin/plan/<int:plan_id>/delete", methods=["POST"])
def admin_delete_plan(plan_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    global PLANS
    PLANS = [p for p in PLANS if int(p.get("id")) != int(plan_id)]
    save_plans(PLANS)
    flash("Plan deleted", "info")
    return redirect(url_for("admin_dashboard"))

# ---------- Optional: serve plans.json (debug) ----------
@app.route("/_debug/plans.json")
def debug_plans_file():
    # Only allow if admin logged in to avoid exposing editing endpoint widely
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    if os.path.exists(DATA_FILE):
        return send_from_directory(os.path.dirname(DATA_FILE), os.path.basename(DATA_FILE))
    return {"plans": PLANS}

# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "").lower() != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
