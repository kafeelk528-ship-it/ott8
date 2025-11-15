# app.py - full updated (persistence + robust submit_utr + telegram)
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
SUBMISSIONS_FILE = os.path.join(os.path.dirname(__file__), "submissions.json")

# Telegram config (optional)
TELEGRAM_BOT_TOKEN = os.getenv("8162787624:AAGlBqWs32zSKFd76PNXjBT-e66Y9mh0nY4", "")
TELEGRAM_CHAT_ID = os.getenv("946189130", "")

# Admin credentials from env (fallback defaults)
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "12345")

# Domain (optional)
YOUR_DOMAIN = os.getenv("https://ott8-3.onrender.com", "").rstrip("/")

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
                if isinstance(data, list):
                    return data
        except Exception as e:
            app.logger.warning("Failed to load plans.json: %s", e)
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

# ---------- Telegram notification (robust) ----------
def send_telegram_notification(text: str) -> bool:
    """
    Send a message to configured Telegram bot/chat. Returns True on success.
    Robust to network failures and logs exceptions.
    """
    token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID
    if not token or not chat_id:
        app.logger.debug("Telegram not configured (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing).")
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        app.logger.info("Telegram notification sent.")
        return True
    except Exception as e:
        app.logger.exception("Failed to send Telegram notification: %s", e)
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
    qr_path = url_for('static', filename='img/qr.png')
    return render_template("pay_manual_cart.html", cart=cart_items, total=total, qr_path=qr_path)

# ---------- Submit UTR (robust) ----------
@app.route("/submit-utr", methods=["POST"])
def submit_utr():
    try:
        # Validate data
        utr = (request.form.get("utr") or "").strip()
        buyer_name = (request.form.get("buyer_name") or "").strip()
        buyer_email = (request.form.get("buyer_email") or "").strip()

        if not utr:
            flash("Please enter a UTR number.", "danger")
            return redirect(url_for("checkout_qr"))

        # Gather cart info
        cart = session.get("cart", [])
        cart_items = [get_plan(pid) for pid in cart]
        cart_items = [c for c in cart_items if c]
        if not cart_items:
            flash("Your cart is empty.", "info")
            return redirect(url_for("plans_page"))

        total = sum(int(item.get("price", 0)) for item in cart_items)
        items_text = ", ".join([item.get("name", "-") for item in cart_items])

        # Build message for Telegram / logs
        text = (
            f"*New Payment Submission*\n"
            f"Items: {items_text}\n"
            f"Amount: ₹{total}\n"
            f"UTR: `{utr}`\n"
            f"Buyer: {buyer_name or '-'} ({buyer_email or '-'})\n"
            f"Time: {datetime.utcnow().isoformat()} UTC"
        )

        # Try to notify via Telegram (if configured)
        telegram_ok = False
        try:
            telegram_ok = send_telegram_notification(text)
        except Exception as e:
            app.logger.exception("Telegram notify failed inside submit_utr: %s", e)

        # Persist submission to submissions.json for audit
        submission = {
            "utr": utr,
            "buyer_name": buyer_name,
            "buyer_email": buyer_email,
            "items": [{"id": i.get("id"), "name": i.get("name"), "price": i.get("price")} for i in cart_items],
            "total": total,
            "telegram_sent": bool(telegram_ok),
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            existing = []
            if os.path.exists(SUBMISSIONS_FILE):
                with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f) or []
            existing.append(submission)
            with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            app.logger.exception("Failed to persist submission to submissions.json: %s", e)

        # Clear cart and show success
        session.pop("cart", None)
        flash("UTR submitted for verification. Owner will verify and deliver.", "success")
        return render_template("success.html")

    except Exception as e:
        # Log full traceback
        app.logger.exception("submit_utr failed: %s", e)
        flash("An unexpected server error occurred while submitting your payment. The owner has been notified.", "danger")
        # Try to notify owner via telegram about the error (safe)
        try:
            err_text = f"⚠️ submit_utr failed on server:\n{str(e)}\nTime: {datetime.utcnow().isoformat()}"
            send_telegram_notification(err_text)
        except Exception:
            app.logger.debug("Failed to send error notification to Telegram.")
        return redirect(url_for("checkout_qr"))

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

    plan.update({
        "name": name,
        "logo": logo,
        "desc": desc,
        "price": price,
        "stock": stock
    })

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

