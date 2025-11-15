from flask import Flask, render_template, redirect, url_for, request, session

app = Flask(__name__)
app.secret_key = "supersecretkey123"   # change later

# ----------------------------
# Demo Plans (No Database Needed)
# ----------------------------
PLANS = [
    {
        "id": 1,
        "name": "Netflix Premium",
        "price": 199,
        "logo": "netflix.png",
        "desc": "4K UHD • 4 Screens • 30 Days"
    },
    {
        "id": 2,
        "name": "Amazon Prime Video",
        "price": 149,
        "logo": "prime.png",
        "desc": "Full HD • All Devices • 30 Days"
    },
    {
        "id": 3,
        "name": "Disney+ Hotstar",
        "price": 299,
        "logo": "hotstar.png",
        "desc": "Sports + Movies + Web Series"
    },
    {
        "id": 4,
        "name": "Sony LIV Premium",
        "price": 129,
        "logo": "sonyliv.png",
        "desc": "Full HD • Originals • TV Shows"
    }
]


# ----------------------------
# Home Page
# ----------------------------
@app.route("/")
def home():
    return render_template("index.html", plans=PLANS)


# ----------------------------
# Plans Page
# ----------------------------
@app.route("/plans")
def plans_page():
    return render_template("plans.html", plans=PLANS)


# ----------------------------
# Plan Details Page
# ----------------------------
@app.route("/plan/<int:plan_id>")
def plan_details(plan_id):
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        return "Plan Not Found", 404
    return render_template("plan-details.html", plan=plan)


# ----------------------------
# Cart System
# ----------------------------
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
    cart_items = [p for p in PLANS if p["id"] in session.get("cart", [])]
    total = sum(item["price"] for item in cart_items)
    return render_template("cart.html", cart=cart_items, total=total)


@app.route("/cart/remove/<int:plan_id>")
def remove_cart(plan_id):
    if "cart" in session and plan_id in session["cart"]:
        session["cart"].remove(plan_id)
        session.modified = True
    return redirect(url_for("cart_page"))


# ----------------------------
# Checkout (dummy)
# ----------------------------
@app.route("/checkout")
def checkout():
    session.pop("cart", None)
    return render_template("success.html")


# ----------------------------
# Contact Page
# ----------------------------
@app.route("/contact")
def contact_page():
    return render_template("contact.html")


# ----------------------------
# Admin Login (Demo Only)
# ----------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "123":
            session["admin"] = True
            return redirect("/admin/dashboard")
        return render_template("admin.html", error=True)
    return render_template("admin.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect("/admin")
    return render_template("dashboard.html", plans=PLANS)



# ----------------------------
# Start
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
