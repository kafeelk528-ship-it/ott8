# app.py
# Updated full Flask app (fresh) with:
# - SQLite (plans + orders)
# - Cart + add/remove
# - Checkout page with choice: card (simulate) or QR (manual UTR)
# - Manual QR flow for single-plan or whole-cart (creates orders)
# - Telegram notification on UTR submission
# - Admin panel to CRUD plans and approve orders (sends email)
# - Reads secrets from environment variables

import os
import sqlite3
import requests
import smtplib
from email.message import EmailMessage
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, abort, jsonify
)

# -------------------------
# App config
# -------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
DB_PATH = os.path.join(os.path.dirname(__file__), "ott.db")

# -------------------------
# Database helpers
# -------------------------
def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price INTEGER NOT NULL DEFAULT 0,
        logo TEXT,
        description TEXT,
        qty INTEGER NOT NULL DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_id INTEGER NOT NULL,
        buyer_name TEXT,
        buyer_email TEXT,
        utr TEXT,
        amount INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now')),
        approved_at TEXT
    )
    """)
    conn.commit()

    # seed sample plans if empty
    cur.execute("SELECT COUNT(1) as cnt FROM plans")
    if cur.fetchone()["cnt"] == 0:
        default = [
            ("Netflix Premium", 199, "netflix.png", "4K UHD • 4 Screens • 30 Days", 10),
            ("Amazon Prime Video", 149, "prime.png", "Full HD • All Devices • 30 Days", 15),
            ("Disney+ Hotstar", 299, "hotstar.png", "Sports + Movies + Web Series", 8),
            ("Sony LIV Premium", 129, "sonyliv.png", "Full HD • Originals • TV Shows", 12),
            ("Zee5 Premium", 99, "zee5.png", "Regional content • 30 Days", 20),
        ]
        cur.executemany(
            "INSERT INTO plans (name, price, logo, description, qty) VALUES (?, ?, ?, ?, ?)",
            default
        )
        conn.commit()

with app.app_context():
    init_db()

# -------------------------
# Env + Admin config
# -------------------------
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "12345")
YOUR_DOMAIN = os.environ.get("YOUR_DOMAIN", "").rstrip("/")

def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return wrapped

# -------------------------
# Plans helpers
# -------------------------
def query_plans():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM plans ORDER BY id")
    rows = cur.fetchall()
    return [dict(r) for r in rows]

def get_plan(plan_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM plans WHERE id=?", (plan_id,))
    r = cur.fetchone()
    return dict(r) if r else None

def update_plan(plan_id, price=None, qty=None, name=None, desc=None, logo=None):
    conn = get_db()
    cur = conn.cursor()
    updates = []
    params = []
    if name is not None:
        updates.append("name=?"); params.append(name)
    if price is not None:
        updates.append("price=?"); params.append(int(price))
    if qty is not None:
        updates.append("qty=?"); params.append(int(qty))
    if desc is not None:
        updates.append("description=?"); params.append(desc)
    if logo is not None:
        updates.append("logo=?"); params.append(logo)
    if updates:
        sql = "UPDATE plans SET " + ", ".join(updates) + " WHERE id=?"
        params.append(plan_id)
        cur.execute(sql, params)
        conn.commit()
        return True
    return False

def add_plan(name, price, qty=0, logo=None, description=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO plans (name, price, logo, description, qty) VALUES (?, ?, ?, ?, ?)",
        (name, int(price), logo, description, int(qty))
    )
    conn.commit()
    return cur.lastrowid

def delete_plan(plan_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM plans WHERE id=?", (plan_id,))
    conn.commit()

# -------------------------
# Orders helpers
# -------------------------
def create_order(plan_id, buyer_name, buyer_email, utr, amount):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (plan_id, buyer_name, buyer_email, utr, amount) VALUES (?, ?, ?, ?, ?)",
        (plan_id, buyer_name, buyer_email, utr, amount)
    )
    conn.commit()
    return cur.lastrowid

def query_orders(status=None):
    conn = get_db()
    cur = conn.cursor()
    if status:
        cur.execute("SELECT * FROM orders WHERE status=? ORDER BY id DESC", (status,))
    else:
        cur.execute("SELECT * FROM orders ORDER BY id DESC")
    rows = cur.fetchall()
    return [dict(r) for r in rows]

def get_order(order_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id=?", (order_id,))
    r = cur.fetchone()
    return dict(r) if r else None

def set_order_status(order_id, status):
    conn = get_db()
    cur = conn.cursor()
    if status == "approved":
        cur.execute("UPDATE orders SET status=?, approved_at=? WHERE id=?", (status, datetime.utcnow().isoformat(), order_id))
    else:
        cur.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()

# Expose helpers to templates
app.jinja_env.globals.update(query_orders=query_orders, get_plan=get_plan)

# -------------------------
# Telegram notification
# -------------------------
def send_telegram_notification(order):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        app.logger.warning("Telegram creds not set; skipping notify.")
        return False

    plan = get_plan(order["plan_id"])
    approve_url = f"{YOUR_DOMAIN}/admin/order/{order['id']}/approve" if YOUR_DOMAIN else ""
    text = (
        f"📥 New Payment Submission\n"
        f"Order ID: {order['id']}\n"
        f"Plan: {plan['name']} (ID {plan['id']})\n"
        f"Amount: ₹{order['amount']}\n"
        f"Buyer: {order.get('buyer_name','-')} | {order.get('buyer_email','-')}\n"
        f"UTR: {order.get('utr','-')}\n"
        f"Status: {order.get('status')}\n"
        f"Time: {order.get('created_at')}\n\n"
        f"Approve: {approve_url}"
    )
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        resp = requests.post(url, json=payload, timeout=8)
        resp.raise_for_status()
        return True
    except Exception as e:
        app.logger.exception("Telegram notify failed: %s", e)
        return False

# -------------------------
# Email sender (SMTP)
# -------------------------
def send_plan_email(buyer_email, subject, body, attachments=None):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    email_from = os.environ.get("EMAIL_FROM", smtp_user)

    if not smtp_host or not smtp_user or not smtp_pass:
        app.logger.warning("SMTP not configured; cannot send email.")
        return False

    msg = EmailMessage()
    msg["From"] = email_from
    msg["To"] = buyer_email
    msg["Subject"] = subject
    msg.set_content(body, subtype="html")

    if attachments:
        for fname, data, mimetype in attachments:
            maintype, subtype = mimetype.split("/")
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname)

    try:
        s = smtplib.SMTP(smtp_host, smtp_port, timeout=20)
        s.starttls()
        s.login(smtp_user, smtp_pass)
        s.send_message(msg)
        s.quit()
        return True
    except Exception as e:
        app.logger.exception("Failed to send email: %s", e)
        return False

# -------------------------
# Routes - public
# -------------------------
@app.route("/")
def home():
    plans = query_plans()
    return render_template("index.html", plans=plans)

@app.route("/plans")
def plans_page():
    plans = query_plans()
    return render_template("plans.html", plans=plans)

@app.route("/plan/<int:plan_id>")
def plan_details(plan_id):
    p = get_plan(plan_id)
    if not p:
        abort(404)
    return render_template("plan-details.html", plan=p)

# -------------------------
# Cart routes
# -------------------------
@app.route("/add-to-cart/<int:plan_id>")
def add_to_cart(plan_id):
    plan = get_plan(plan_id)
    if not plan:
        flash("Invalid product", "danger")
        return redirect(url_for("plans_page"))

    if plan["qty"] <= 0:
        flash("Item is out of stock", "danger")
        return redirect(url_for("plans_page"))

    if "cart" not in session:
        session["cart"] = []
    if plan_id not in session["cart"]:
        session["cart"].append(plan_id)
        session.modified = True
        flash("Added to cart", "success")
    else:
        flash("Already in cart", "info")
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
        flash("Removed from cart", "info")
    return redirect(url_for("cart_page"))

# -------------------------
# Checkout (updated)
# -------------------------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    """
    GET -> show checkout page with payment method options
    POST -> depending on payment_method:
        - "card"  -> simulate immediate payment: reduce stock, clear cart, success
        - "qr"   -> show QR + UTR form for cart (does NOT reduce stock yet)
    """
    cart = session.get("cart", [])
    cart_items = [get_plan(pid) for pid in cart]
    cart_items = [c for c in cart_items if c]
    total = sum(item["price"] for item in cart_items)

    if request.method == "GET":
        return render_template("checkout.html", cart=cart_items, total=total)

    # POST
    method = request.form.get("payment_method", "card")
    if method == "card":
        if not cart_items:
            flash("Cart is empty", "info")
            return redirect(url_for("plans_page"))

        conn = get_db()
        cur = conn.cursor()
        for pid in cart:
            cur.execute("SELECT qty FROM plans WHERE id=?", (pid,))
            r = cur.fetchone()
            if not r or r["qty"] <= 0:
                flash("Some items are out of stock. Please update your cart.", "danger")
                return redirect(url_for("cart_page"))

        for pid in cart:
            cur.execute("UPDATE plans SET qty = qty - 1 WHERE id=? AND qty > 0", (pid,))
        conn.commit()
        session.pop("cart", None)
        flash("Checkout successful — stock updated (demo).", "success")
        return render_template("success.html")

    elif method == "qr":
        qr_path = url_for('static', filename='img/qr.png')
        return render_template("pay_manual_cart.html", cart=cart_items, total=total, qr_path=qr_path)

    else:
        flash("Unknown payment method", "danger")
        return redirect(url_for("checkout"))

@app.route("/contact")
def contact_page():
    return render_template("contact.html")

# -------------------------
# Manual bank/QR payment for single plan
# -------------------------
@app.route("/pay_manual/<int:plan_id>", methods=["GET"])
def pay_manual(plan_id):
    plan = get_plan(plan_id)
    if not plan:
        abort(404)
    qr_path = url_for('static', filename='img/qr.png')
    return render_template("pay_manual.html", plan=plan, qr_path=qr_path)

# -------------------------
# Submit UTR (single-plan or cart)
# -------------------------
@app.route("/submit-utr", methods=["POST"])
def submit_utr():
    """
    Handles UTR submission for either:
      - single-plan payment (form has plan_id)
      - cart payment (form has cart_mode=1) -> creates orders per cart item
    """
    cart_mode = request.form.get("cart_mode")
    buyer_name = request.form.get("buyer_name")
    buyer_email = request.form.get("buyer_email")
    utr = request.form.get("utr", "").strip()

    if cart_mode:
        cart = session.get("cart", [])
        if not cart:
            flash("Cart is empty.", "info")
            return redirect(url_for("plans_page"))

        created_orders = []
        for pid in cart:
            plan = get_plan(pid)
            if not plan:
                continue
            order_id = create_order(pid, buyer_name, buyer_email, utr, plan["price"])
            created_orders.append(order_id)

        if created_orders:
            first_order = get_order(created_orders[0])
            send_telegram_notification(first_order)

        flash("UTR submitted — owner will verify and approve shortly.", "success")
        return render_template("utr_submitted.html", order=get_order(created_orders[0]) if created_orders else None, plan=None)

    # single plan flow
    try:
        plan_id = int(request.form.get("plan_id"))
    except:
        flash("Invalid plan", "danger")
        return redirect(url_for("plans_page"))

    plan = get_plan(plan_id)
    if not plan:
        flash("Invalid plan", "danger")
        return redirect(url_for("plans_page"))

    order_id = create_order(plan_id, buyer_name, buyer_email, utr, plan["price"])
    order = get_order(order_id)
    send_telegram_notification(order)
    flash("UTR submitted — owner will check and approve shortly.", "success")
    return render_template("utr_submitted.html", order=order, plan=plan)

# -------------------------
# Admin routes
# -------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = request.form.get("username", "")
        pw = request.form.get("password", "")
        if user == ADMIN_USER and pw == ADMIN_PASS:
            session["is_admin"] = True
            flash("Logged in as admin", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid credentials", "danger")
            return render_template("admin.html", error=True)
    return render_template("admin.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Logged out", "info")
    return redirect(url_for("home"))

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    plans = query_plans()
    orders = query_orders()
    return render_template("admin_dashboard.html", plans=plans, orders=orders)

@app.route("/admin/plan/<int:plan_id>/update", methods=["POST"])
@admin_required
def admin_update_plan(plan_id):
    price = request.form.get("price")
    qty = request.form.get("qty")
    name = request.form.get("name")
    desc = request.form.get("description")
    logo = request.form.get("logo")
    update_plan(plan_id, price=price, qty=qty, name=name, desc=desc, logo=logo)
    flash("Plan updated", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/plan/add", methods=["POST"])
@admin_required
def admin_add_plan():
    name = request.form.get("name")
    price = request.form.get("price") or 0
    qty = request.form.get("qty") or 0
    logo = request.form.get("logo") or ""
    desc = request.form.get("description") or ""
    add_plan(name, price, qty=qty, logo=logo, description=desc)
    flash("Plan added", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/plan/<int:plan_id>/delete", methods=["POST"])
@admin_required
def admin_delete_plan(plan_id):
    delete_plan(plan_id)
    flash("Plan deleted", "info")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/order/<int:order_id>/approve", methods=["POST", "GET"])
@admin_required
def admin_approve_order(order_id):
    order = get_order(order_id)
    if not order:
        flash("Order not found", "danger")
        return redirect(url_for("admin_dashboard"))

    # mark approved
    set_order_status(order_id, "approved")

    # optionally reduce stock for that plan now (1 unit)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE plans SET qty = qty - 1 WHERE id=? AND qty > 0", (order["plan_id"],))
    conn.commit()

    # send plan by email to buyer
    plan = get_plan(order["plan_id"])
    subject = f"Your {plan['name']} — Access / Receipt"
    body = f"""
      <p>Hi {order['buyer_name'] or ''},</p>
      <p>Your payment (UTR: <strong>{order['utr']}</strong>) for <strong>{plan['name']}</strong> of ₹{order['amount']} has been approved.</p>
      <p>Plan details:</p>
      <ul>
        <li>Plan: {plan['name']}</li>
        <li>Price: ₹{plan['price']}</li>
        <li>Validity: Demo 30 days</li>
      </ul>
      <p>Thanks — OTT Store</p>
    """
    send_plan_email(order['buyer_email'], subject, body)

    flash("Order approved, stock updated and email sent to buyer.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/order/<int:order_id>/json")
@admin_required
def admin_order_json(order_id):
    o = get_order(order_id)
    if not o:
        return jsonify({"error": "not found"}), 404
    return jsonify(o)

# -------------------------
# Run server
# -------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
