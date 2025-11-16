# app.py - Updated for upgraded UI, admin, cart, UTR + Telegram
import os
import json
import requests
from datetime import datetime
from flask import (
    Flask, render_template, redirect, url_for, request,
    session, flash, send_from_directory, abort
)
from functools import wraps

# ---------- Config ----------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

DATA_DIR = os.path.dirname(__file__)
PLANS_FILE = os.path.join(DATA_DIR, "plans.json")
SUBMISSIONS_FILE = os.path.join(DATA_DIR, "submissions.json")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "12345")
YOUR_DOMAIN = os.getenv("YOUR_DOMAIN", "").rstrip("/")

# ---------- Utilities ----------
def load_plans():
    # Try to load persisted plans, fallback to default if missing
    if os.path.exists(PLANS_FILE):
        try:
            with open(PLANS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            app.logger.warning("Failed loading plans.json: %s", e)
    # default demo plans (will only be used if plans.json not available)
    return [
        {"id": 1, "name": "Netflix Premium", "price": 199, "logo": "netflix.png", "desc": "4K UHD • 4 Screens • 30 Days", "available": 10},
        {"id": 2, "name": "Amazon Prime Video", "price": 149, "logo": "prime.png", "desc": "Full HD • All Devices • 30 Days", "available": 12},
        {"id": 3, "name": "Disney+ Hotstar", "price": 299, "logo": "hotstar.png", "desc": "Sports + Movies + Web Series", "available": 6},
        {"id": 4, "name": "Sony LIV Premium", "price": 129, "logo": "sonyliv.png", "desc": "Full HD • Originals • TV Shows", "available": 9},
    ]

def save_plans(plans):
    try:
        with open(PLANS_FILE, "w", encoding="utf-8") as f:
            json.dump(plans, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        app.logger.exception("Failed to save plans.json: %s", e)
        return False

def get_plan(plan_id):
    plans = app.config.get("PLANS")
    return next((p for p in plans if int(p.get("id")) == int(plan_id)), None)

def next_plan_id():
    plans = app.config.get("PLANS")
    if not plans:
        return 1
    return max(int(p["id"]) for p in plans) + 1

# load plans into memory on startup
app.config["PLANS"] = load_plans()

# ---------- Telegram helper ----------
def send_telegram_notification(text: str) -> bool:
    token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID
    if not token or not chat_id:
        app.logger.debug("Telegram not configured.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            app.logger.info("Telegram sent ok.")
            return True
        app.logger.error("Telegram API error: %s", data)
        return False
    except Exception as e:
        app.logger.exception("Failed to send Telegram message: %s", e)
        return False

# ---------- Auth decorators ----------
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return decorated

# ---------- Routes - Public ----------
@app.route("/")
def home():
    plans = app.config["PLANS"]
    return render_template("index.html", plans=plans)

@app.route("/plans")
def plans_page():
    plans = app.config["PLANS"]
    return render_template("plans.html", plans=plans)

@app.route("/plan/<int:plan_id>")
def plan_details(plan_id):
    p = get_plan(plan_id)
    if not p:
        abort(404)
    return render_template("plan-details.html", plan=p)

# ---------- Cart ----------
@app.route("/add-to-cart/<int:plan_id>")
def add_to_cart(plan_id):
    p = get_plan(plan_id)
    if not p:
        flash("Invalid plan", "danger")
        return redirect(url_for("plans_page"))

    if p.get("available", 0) <= 0:
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
    total = sum(int(item.get("price",0)) for item in cart_items)
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

# ---------- Checkout & QR ----------
@app.route("/payment")
def payment_page():
    cart_items = [get_plan(pid) for pid in session.get("cart", [])]
    cart_items = [c for c in cart_items if c]
    if not cart_items:
        flash("Cart is empty", "info")
        return redirect(url_for("plans_page"))
    total = sum(int(i.get("price",0)) for i in cart_items)
    qr_url = url_for('static', filename='qr.png')
    return render_template("payment.html", cart=cart_items, total=total, qr_url=qr_url)

# ---------- Submit UTR (robust) ----------
@app.route("/submit_utr", methods=["POST"])
def submit_utr():
    try:
        utr = (request.form.get("utr") or "").strip()
        buyer_name = (request.form.get("buyer_name") or "").strip()
        buyer_email = (request.form.get("buyer_email") or "").strip()

        if not utr:
            flash("Please enter a UTR number.", "danger")
            return redirect(url_for("payment_page"))

        cart = session.get("cart", [])
        cart_items = [get_plan(pid) for pid in cart]
        cart_items = [c for c in cart_items if c]
        if not cart_items:
            flash("Your cart is empty.", "info")
            return redirect(url_for("plans_page"))

        total = sum(int(item.get("price",0)) for item in cart_items)
        items_text = ", ".join([item.get("name","-") for item in cart_items])

        text = (
            f"*Payment Submission*\n"
            f"Items: {items_text}\n"
            f"Amount: ₹{total}\n"
            f"UTR: `{utr}`\n"
            f"Buyer: {buyer_name or '-'} ({buyer_email or '-'})\n"
            f"Time: {datetime.utcnow().isoformat()} UTC"
        )

        telegram_ok = send_telegram_notification(text)

        # persist submission
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
            app.logger.exception("Failed to save submission: %s", e)

        # Optionally reduce availability in admin workflow (we leave stock changes to admin after verification)
        session.pop("cart", None)
        flash("UTR submitted — owner will verify and deliver.", "success")
        return render_template("success.html", utr=utr)

    except Exception as e:
        app.logger.exception("submit_utr failed: %s", e)
        flash("Server error while submitting payment. Owner notified.", "danger")
        try:
            send_telegram_notification(f"⚠️ submit_utr error: {str(e)}")
        except:
            pass
        return redirect(url_for("payment_page"))

# ---------- Contact ----------
@app.route("/contact")
def contact_page():
    return render_template("contact.html")

# ---------- Admin (simple) ----------
@app.route("/admin", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USER and request.form.get("password") == ADMIN_PASS:
            session["admin"] = True
            flash("Admin logged in", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials", "danger")
        return render_template("admin.html", error=True)
    return render_template("admin.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    flash("Logged out", "info")
    return redirect(url_for("home"))

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    plans = app.config["PLANS"]
    return render_template("dashboard.html", plans=plans)

@app.route("/admin/plan/add", methods=["POST"])
@admin_required
def admin_add_plan():
    name = request.form.get("name","").strip()
    logo = request.form.get("logo","").strip()
    desc = request.form.get("desc","").strip()
    try:
        price = int(request.form.get("price",0))
    except:
        price = 0
    try:
        available = int(request.form.get("available",0))
    except:
        available = 0

    if not name:
        flash("Name required", "danger")
        return redirect(url_for("admin_dashboard"))

    new_id = next_plan_id()
    new_plan = {"id": new_id, "name": name, "price": price, "logo": logo, "desc": desc, "available": available}
    app.config["PLANS"].append(new_plan)
    save_plans(app.config["PLANS"])
    flash("Plan added", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/plan/<int:plan_id>/update", methods=["POST"])
@admin_required
def admin_update_plan(plan_id):
    p = get_plan(plan_id)
    if not p:
        flash("Plan not found", "danger")
        return redirect(url_for("admin_dashboard"))
    p["name"] = request.form.get("name", p.get("name"))
    p["logo"] = request.form.get("logo", p.get("logo"))
    p["desc"] = request.form.get("desc", p.get("desc"))
    try:
        p["price"] = int(request.form.get("price", p.get("price",0)))
    except:
        pass
    try:
        p["available"] = int(request.form.get("available", p.get("available",0)))
    except:
        pass
    save_plans(app.config["PLANS"])
    flash("Plan updated", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/plan/<int:plan_id>/delete", methods=["POST"])
@admin_required
def admin_delete_plan(plan_id):
    plans = app.config["PLANS"]
    app.config["PLANS"] = [x for x in plans if int(x.get("id")) != int(plan_id)]
    save_plans(app.config["PLANS"])
    flash("Plan deleted", "info")
    return redirect(url_for("admin_dashboard"))

# ---------- Debug route for telegram ----------
@app.route("/_debug/telegram-test")
def telegram_test():
    token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return {"ok": False, "error": "Telegram not configured"}, 400
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": "🧪 Test message from OTT app", "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        try:
            data = resp.json()
            return data
        except:
            return {"status_code": resp.status_code, "raw": resp.text}
    except Exception as e:
        app.logger.exception("Telegram test error: %s", e)
        return {"ok": False, "error": str(e)}, 500

# ---------- Serve static JSON debug (optional) ----------
@app.route("/_debug/plans.json")
@admin_required
def debug_plans_json():
    return {"plans": app.config["PLANS"]}

# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "").lower() != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
