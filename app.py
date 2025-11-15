import os
import sqlite3
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, abort, jsonify
)
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

DB_PATH = os.path.join(os.path.dirname(__file__), "ott.db")

# -------------------------
# Database helpers
# -------------------------
def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
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
    conn.commit()

    # seed if empty
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
# Admin auth
# -------------------------
def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return wrapped

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "12345")

# -------------------------
# Plan helpers
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
    row = cur.fetchone()
    return dict(row) if row else None

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
# Public routes
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

# CART (simple)
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

    # allow multiple of same? for simplicity use single-item per product
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

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    # On POST perform checkout and reduce qty
    if request.method == "POST":
        cart = session.get("cart", [])
        if not cart:
            flash("Cart is empty", "info")
            return redirect(url_for("plans_page"))

        conn = get_db()
        cur = conn.cursor()
        # verify stock availability first
        for pid in cart:
            cur.execute("SELECT qty FROM plans WHERE id=?", (pid,))
            r = cur.fetchone()
            if not r or r["qty"] <= 0:
                flash("Some items are out of stock. Please update your cart.", "danger")
                return redirect(url_for("cart_page"))

        # reduce qty for each item (one unit each)
        for pid in cart:
            cur.execute("UPDATE plans SET qty = qty - 1 WHERE id=? AND qty > 0", (pid,))
        conn.commit()

        session.pop("cart", None)
        flash("Checkout successful — stock updated (demo).", "success")
        return render_template("success.html")

    # GET shows summary/checkout page
    cart_items = [get_plan(pid) for pid in session.get("cart", [])]
    cart_items = [c for c in cart_items if c]
    total = sum(item["price"] for item in cart_items)
    return render_template("checkout.html", cart=cart_items, total=total)

@app.route("/contact")
def contact_page():
    return render_template("contact.html")

# -------------------------
# Admin routes (login + dashboard + edit API)
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
    return render_template("admin_dashboard.html", plans=plans)

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

@app.route("/admin/plan/<int:plan_id>/json")
@admin_required
def admin_plan_json(plan_id):
    p = get_plan(plan_id)
    if not p:
        return jsonify({"error": "Not found"}), 404
    return jsonify(p)

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)
