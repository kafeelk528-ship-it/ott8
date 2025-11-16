# app.py - fixed for ott8 (uses static/img/* and stable templates)
import os
import json
import requests
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, session, flash, abort
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Data (in-memory). Keep editable in admin (persisting optional)
PLANS = [
    {"id": 1, "name": "Netflix Premium", "price": 199, "logo": "img/netflix.png", "desc": "4K UHD • 4 Screens • 30 Days", "available": 10},
    {"id": 2, "name": "Amazon Prime Video", "price": 149, "logo": "img/prime.png", "desc": "Full HD • All Devices • 30 Days", "available": 12},
    {"id": 3, "name": "Disney+ Hotstar", "price": 299, "logo": "img/hotstar.png", "desc": "Sports + Movies + Web Series", "available": 5},
    {"id": 4, "name": "Sony LIV Premium", "price": 129, "logo": "img/sonyliv.png", "desc": "Full HD • Originals • TV Shows", "available": 9},
]

def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return wrapped

def get_plan(pid):
    return next((p for p in PLANS if int(p["id"]) == int(pid)), None)

def send_telegram(text: str):
    token = TELEGRAM_BOT_TOKEN
    chat = TELEGRAM_CHAT_ID
    if not token or not chat:
        app.logger.debug("Telegram not configured")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat, "text": text, "parse_mode": "Markdown"})
        r.raise_for_status()
        return r.json().get("ok", False)
    except Exception as e:
        app.logger.exception("Telegram send failed: %s", e)
        return False

# ----- Public routes -----
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
        abort(404)
    return render_template("plan-details.html", plan=plan)

# ----- Cart -----
@app.route("/add-to-cart/<int:plan_id>")
def add_to_cart(plan_id):
    plan = get_plan(plan_id)
    if not plan:
        flash("Invalid product", "danger")
        return redirect(url_for("plans_page"))
    if plan.get("available", 0) <= 0:
        flash("Product not available", "danger")
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
    total = sum(int(i["price"]) for i in cart_items)
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

# ----- Payment / UTR submit -----
@app.route("/payment")
def payment_page():
    cart_items = [get_plan(pid) for pid in session.get("cart", [])]
    cart_items = [c for c in cart_items if c]
    if not cart_items:
        flash("Cart is empty", "info")
        return redirect(url_for("plans_page"))
    total = sum(int(i["price"]) for i in cart_items)
    return render_template("payment.html", cart=cart_items, total=total)

@app.route("/submit_utr", methods=["POST"])
def submit_utr():
    utr = (request.form.get("utr") or "").strip()
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    cart_items = [get_plan(pid) for pid in session.get("cart", [])]
    cart_items = [c for c in cart_items if c]
    if not utr:
        flash("Enter UTR", "danger")
        return redirect(url_for("payment_page"))
    total = sum(int(i["price"]) for i in cart_items)
    items = ", ".join([i["name"] for i in cart_items])
    text = f"*New Payment*\nName: {name or '-'}\nEmail: {email or '-'}\nAmount: ₹{total}\nUTR: `{utr}`\nItems: {items}\nTime: {datetime.utcnow().isoformat()} UTC"
    send_telegram(text)
    # save submission locally (append json)
    try:
        subs_file = os.path.join(os.path.dirname(__file__), "submissions.json")
        existing = []
        if os.path.exists(subs_file):
            with open(subs_file, "r", encoding="utf-8") as fh:
                existing = json.load(fh) or []
        existing.append({"utr": utr, "name": name, "email": email, "items": cart_items, "total": total, "time": datetime.utcnow().isoformat()})
        with open(subs_file, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2, ensure_ascii=False)
    except Exception:
        app.logger.exception("Failed to save submission")
    # clear cart
    session.pop("cart", None)
    flash("UTR submitted. Owner will verify.", "success")
    return render_template("success.html")

# ----- Contact -----
@app.route("/contact")
def contact_page():
    return render_template("contact.html")

# ----- Admin (simple) -----
@app.route("/admin", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("username") == os.getenv("ADMIN_USER", "admin") and request.form.get("password") == os.getenv("ADMIN_PASS", "12345"):
            session["admin"] = True
            flash("Admin logged in", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials", "danger")
        return render_template("admin.html", error=True)
    return render_template("admin.html")

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template("dashboard.html", plans=PLANS)

@app.route("/admin/plan/<int:plan_id>/update", methods=["POST"])
@admin_required
def admin_update_plan(plan_id):
    p = get_plan(plan_id)
    if not p:
        flash("Plan not found", "danger")
        return redirect(url_for("admin_dashboard"))
    try:
        p["price"] = int(request.form.get("price", p["price"]))
    except:
        pass
    try:
        p["available"] = int(request.form.get("available", p.get("available",0)))
    except:
        pass
    # optional: update logo/name/desc
    p["name"] = request.form.get("name", p["name"])
    p["logo"] = request.form.get("logo", p["logo"])
    p["desc"] = request.form.get("desc", p["desc"])
    flash("Plan updated", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    flash("Logged out", "info")
    return redirect(url_for("home"))

# ----- Telegram debug -----
@app.route("/_debug/telegram-test")
def telegram_test():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"ok": False, "error": "telegram env missing"}, 400
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": "Test message from ott app", "parse_mode": "Markdown"})
    try:
        return r.json()
    except:
        return {"status": r.status_code, "text": r.text}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=(os.getenv("FLASK_ENV","")!="production"))
