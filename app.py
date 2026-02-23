import sqlite3
import os
import random
import functools
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Flask, render_template, request, jsonify, session, g, redirect, url_for
)

app = Flask(__name__)
app.secret_key = os.urandom(24)

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pinpoint.db")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            address TEXT,
            phone TEXT,
            image_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            user_id INTEGER,
            reviewer_name TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (business_id) REFERENCES businesses(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            discount_text TEXT,
            coupon_code TEXT,
            expiry_date TEXT,
            FOREIGN KEY (business_id) REFERENCES businesses(id)
        );
        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            business_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (business_id) REFERENCES businesses(id),
            UNIQUE(user_id, business_id)
        );
    """)
    db.commit()


def seed_db():
    db = get_db()

    # Seed demo user
    demo = db.execute("SELECT id FROM users WHERE username = 'demo'").fetchone()
    if not demo:
        db.execute(
            "INSERT INTO users (username, display_name, password_hash) VALUES (?, ?, ?)",
            ("demo", "Demo User", generate_password_hash("demo123")),
        )
        db.commit()

    count = db.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
    if count > 0:
        return

    businesses = [
        ("The Golden Fork", "food", "Farm-to-table brunch cafe with locally sourced ingredients and artisan coffee.", "142 Maple St", "(555) 234-5678", "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600"),
        ("Sunrise Bakery", "food", "Family-owned bakery specializing in sourdough breads, pastries, and custom cakes.", "87 Oak Ave", "(555) 345-6789", "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600"),
        ("Bella Trattoria", "food", "Authentic Italian dining with handmade pasta and wood-fired pizzas.", "201 Vine Blvd", "(555) 456-7890", "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=600"),
        ("Elm Street Books", "retail", "Independent bookstore with curated selections, author events, and a cozy reading nook.", "55 Elm St", "(555) 567-8901", "https://images.unsplash.com/photo-1526243741027-444d633d7365?w=600"),
        ("The Vintage Loft", "retail", "Curated vintage clothing and accessories from the 60s through the 90s.", "310 Main St", "(555) 678-9012", "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=600"),
        ("Green Thumb Garden Co.", "retail", "Local plant nursery offering houseplants, succulents, and gardening workshops.", "78 Cedar Ln", "(555) 789-0123", "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600"),
        ("Precision Auto Care", "services", "Trusted neighborhood mechanic providing honest diagnostics and quality repairs.", "425 Industrial Pkwy", "(555) 890-1234", "https://images.unsplash.com/photo-1486262715619-67b85e0b08d3?w=600"),
        ("Bright Smile Dental", "health", "Gentle family dentistry with modern technology and a welcoming atmosphere.", "190 Wellness Dr", "(555) 901-2345", "https://images.unsplash.com/photo-1629909613654-28e377c37b09?w=600"),
        ("FitCore Studio", "health", "Boutique fitness studio offering yoga, pilates, and strength training classes.", "62 Park Ave", "(555) 012-3456", "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600"),
        ("Pixel & Frame Photography", "services", "Creative photography studio for portraits, events, and small business branding.", "118 Art District Rd", "(555) 123-4567", "https://images.unsplash.com/photo-1554048612-b6a482bc67e5?w=600"),
        ("Encore Music Academy", "entertainment", "Music lessons for all ages and skill levels, from piano to guitar to drums.", "233 Harmony St", "(555) 234-6780", "https://images.unsplash.com/photo-1511379938547-c1f69419868d?w=600"),
        ("Escape Room Central", "entertainment", "Immersive puzzle rooms with themes ranging from mystery to sci-fi adventure.", "505 Fun Blvd", "(555) 345-7891", "https://images.unsplash.com/photo-1590664216212-62e528e26e30?w=600"),
    ]

    for b in businesses:
        db.execute(
            "INSERT INTO businesses (name, category, description, address, phone, image_url) VALUES (?,?,?,?,?,?)",
            b,
        )

    reviews_data = [
        (1, "Alice M.", 5, "Incredible brunch! The avocado toast is a must-try."),
        (1, "Bob T.", 4, "Great atmosphere and food. A bit pricey but worth it."),
        (2, "Carla R.", 5, "Best croissants in town, hands down."),
        (2, "Derek S.", 4, "Love their sourdough. Always fresh."),
        (2, "Emma L.", 5, "The custom birthday cake they made was beautiful and delicious."),
        (3, "Frank W.", 5, "The carbonara is absolutely authentic. Transported me to Rome!"),
        (3, "Grace K.", 4, "Cozy ambiance and great wine selection."),
        (4, "Hannah J.", 5, "A hidden gem for book lovers. Their recommendations are spot-on."),
        (4, "Ian P.", 4, "Love the author events they host. Great community space."),
        (5, "Julia N.", 5, "Found an amazing vintage denim jacket. Prices are fair."),
        (6, "Kevin B.", 4, "Wide selection of plants. Staff is very knowledgeable."),
        (6, "Lisa D.", 5, "Their succulent workshop was so fun! Highly recommend."),
        (7, "Mike H.", 5, "Honest and affordable. They explained everything clearly."),
        (7, "Nancy C.", 4, "Quick turnaround on my brake repair. Fair pricing."),
        (8, "Oscar F.", 5, "Dr. Chen is amazing. Painless cleaning and very thorough."),
        (9, "Paula G.", 5, "The yoga classes here changed my life. Incredible instructors."),
        (9, "Quinn A.", 4, "Great variety of classes. Wish they had more evening slots."),
        (10, "Rachel E.", 5, "They did our family portraits and they turned out beautifully."),
        (11, "Sam V.", 4, "My daughter loves her piano lessons here. Patient teachers."),
        (12, "Tina Z.", 5, "The sci-fi room was incredible! We had a blast."),
        (12, "Umar Y.", 4, "Fun experience for a group outing. Challenging but doable."),
    ]

    for r in reviews_data:
        db.execute(
            "INSERT INTO reviews (business_id, reviewer_name, rating, comment) VALUES (?,?,?,?)",
            r,
        )

    today = datetime.now()
    deals_data = [
        (1, "Brunch for Two Special", "Enjoy two brunch entrees and two drinks at a discounted price.", "20% Off", "BRUNCH20", (today + timedelta(days=30)).strftime("%Y-%m-%d")),
        (2, "Fresh Bread Friday", "Get a free pastry with any loaf purchase on Fridays.", "Free Pastry", "BREADFRI", (today + timedelta(days=45)).strftime("%Y-%m-%d")),
        (3, "Date Night Deal", "Two pasta entrees and a bottle of house wine.", "25% Off", "PASTA25", (today + timedelta(days=20)).strftime("%Y-%m-%d")),
        (4, "Book Club Bundle", "Buy 3 books and get the 4th free from the staff picks shelf.", "Buy 3 Get 1", "READ4FREE", (today + timedelta(days=60)).strftime("%Y-%m-%d")),
        (5, "Vintage Vault Sale", "Storewide discount on all vintage accessories.", "15% Off", "VINTAGE15", (today + timedelta(days=14)).strftime("%Y-%m-%d")),
        (6, "Plant Parent Pack", "Two medium houseplants bundled together at a special price.", "$10 Off", "PLANTS10", (today + timedelta(days=25)).strftime("%Y-%m-%d")),
        (9, "New Member Offer", "First month of unlimited classes at a reduced rate.", "50% Off First Month", "FIT50", (today + timedelta(days=35)).strftime("%Y-%m-%d")),
        (12, "Group Adventure", "Book a room for 6+ people and save.", "30% Off Groups", "ESCAPE30", (today + timedelta(days=40)).strftime("%Y-%m-%d")),
    ]

    for d in deals_data:
        db.execute(
            "INSERT INTO deals (business_id, title, description, discount_text, coupon_code, expiry_date) VALUES (?,?,?,?,?,?)",
            d,
        )

    db.commit()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def login_required_api(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Login required.", "login_required": True}), 401
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_user():
    user = get_current_user()
    return {"current_user": user}


# ---------------------------------------------------------------------------
# Captcha helpers
# ---------------------------------------------------------------------------

def generate_captcha():
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    ops = [("+", a + b), ("-", abs(a - b))]
    if random.random() < 0.3:
        a, b = random.randint(1, 10), random.randint(1, 10)
        ops.append(("x", a * b))
    op_symbol, answer = random.choice(ops)
    if op_symbol == "-" and a < b:
        a, b = b, a
        answer = a - b
    session["captcha_answer"] = str(answer)
    return f"{a} {op_symbol} {b}"


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/business/<int:business_id>")
def business_detail(business_id):
    captcha_question = generate_captcha()
    return render_template("business.html", business_id=business_id, captcha_question=captcha_question)


@app.route("/bookmarks")
def bookmarks_page():
    if not session.get("user_id"):
        return redirect(url_for("login_page", next="/bookmarks"))
    return render_template("bookmarks.html")


@app.route("/deals")
def deals_page():
    return render_template("deals.html")


@app.route("/login")
def login_page():
    if session.get("user_id"):
        return redirect("/")
    return render_template("login.html")


@app.route("/signup")
def signup_page():
    if session.get("user_id"):
        return redirect("/")
    return render_template("signup.html")


# ---------------------------------------------------------------------------
# Auth API routes
# ---------------------------------------------------------------------------

@app.route("/api/auth/signup", methods=["POST"])
def api_signup():
    data = request.get_json(force=True)
    username = data.get("username", "").strip().lower()
    display_name = data.get("display_name", "").strip()
    password = data.get("password", "")

    if not username or not display_name or not password:
        return jsonify({"error": "All fields are required."}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        return jsonify({"error": "Username already taken."}), 409

    pw_hash = generate_password_hash(password)
    cursor = db.execute(
        "INSERT INTO users (username, display_name, password_hash) VALUES (?, ?, ?)",
        (username, display_name, pw_hash),
    )
    db.commit()

    session["user_id"] = cursor.lastrowid
    session["display_name"] = display_name
    return jsonify({"success": True, "display_name": display_name}), 201


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password."}), 401

    session["user_id"] = user["id"]
    session["display_name"] = user["display_name"]
    return jsonify({"success": True, "display_name": user["display_name"]})


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/auth/me")
def api_me():
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False})
    return jsonify({
        "authenticated": True,
        "user_id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
    })


# ---------------------------------------------------------------------------
# Bookmark API routes
# ---------------------------------------------------------------------------

@app.route("/api/bookmarks")
@login_required_api
def api_get_bookmarks():
    db = get_db()
    rows = db.execute(
        "SELECT business_id FROM bookmarks WHERE user_id = ?",
        (session["user_id"],),
    ).fetchall()
    return jsonify([r["business_id"] for r in rows])


@app.route("/api/bookmarks", methods=["POST"])
@login_required_api
def api_add_bookmark():
    data = request.get_json(force=True)
    business_id = data.get("business_id")
    if not business_id:
        return jsonify({"error": "business_id required."}), 400

    db = get_db()
    try:
        db.execute(
            "INSERT INTO bookmarks (user_id, business_id) VALUES (?, ?)",
            (session["user_id"], business_id),
        )
        db.commit()
    except sqlite3.IntegrityError:
        pass
    return jsonify({"success": True, "bookmarked": True})


@app.route("/api/bookmarks/<int:business_id>", methods=["DELETE"])
@login_required_api
def api_remove_bookmark(business_id):
    db = get_db()
    db.execute(
        "DELETE FROM bookmarks WHERE user_id = ? AND business_id = ?",
        (session["user_id"], business_id),
    )
    db.commit()
    return jsonify({"success": True, "bookmarked": False})


# ---------------------------------------------------------------------------
# Business & Review API routes
# ---------------------------------------------------------------------------

@app.route("/api/businesses")
def api_businesses():
    db = get_db()
    category = request.args.get("category", "")
    sort = request.args.get("sort", "newest")
    ids_param = request.args.get("ids", "")

    base_query = """
        SELECT b.*,
               COALESCE(AVG(r.rating), 0) AS avg_rating,
               COUNT(r.id) AS review_count
        FROM businesses b
        LEFT JOIN reviews r ON r.business_id = b.id
    """
    conditions = []
    params = []

    if ids_param:
        id_list = [int(x) for x in ids_param.split(",") if x.strip().isdigit()]
        if id_list:
            placeholders = ",".join("?" * len(id_list))
            conditions.append(f"b.id IN ({placeholders})")
            params.extend(id_list)

    if category and category != "all":
        conditions.append("b.category = ?")
        params.append(category)

    where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    group_clause = " GROUP BY b.id"

    if sort == "rating":
        order_clause = " ORDER BY avg_rating DESC, review_count DESC"
    elif sort == "reviews":
        order_clause = " ORDER BY review_count DESC, avg_rating DESC"
    else:
        order_clause = " ORDER BY b.created_at DESC"

    rows = db.execute(base_query + where_clause + group_clause + order_clause, params).fetchall()
    businesses = []
    for row in rows:
        businesses.append({
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "description": row["description"],
            "address": row["address"],
            "phone": row["phone"],
            "image_url": row["image_url"],
            "avg_rating": round(row["avg_rating"], 1),
            "review_count": row["review_count"],
        })
    return jsonify(businesses)


@app.route("/api/businesses/<int:business_id>")
def api_business_detail(business_id):
    db = get_db()
    row = db.execute("""
        SELECT b.*,
               COALESCE(AVG(r.rating), 0) AS avg_rating,
               COUNT(r.id) AS review_count
        FROM businesses b
        LEFT JOIN reviews r ON r.business_id = b.id
        WHERE b.id = ?
        GROUP BY b.id
    """, (business_id,)).fetchone()
    if not row:
        return jsonify({"error": "Business not found"}), 404
    return jsonify({
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "address": row["address"],
        "phone": row["phone"],
        "image_url": row["image_url"],
        "avg_rating": round(row["avg_rating"], 1),
        "review_count": row["review_count"],
    })


@app.route("/api/businesses/<int:business_id>/reviews")
def api_reviews(business_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM reviews WHERE business_id = ? ORDER BY created_at DESC",
        (business_id,),
    ).fetchall()
    return jsonify([{
        "id": r["id"],
        "reviewer_name": r["reviewer_name"],
        "rating": r["rating"],
        "comment": r["comment"],
        "created_at": r["created_at"],
    } for r in rows])


@app.route("/api/reviews", methods=["POST"])
@login_required_api
def api_create_review():
    data = request.get_json(force=True)

    captcha_answer = data.get("captcha_answer", "").strip()
    expected = session.get("captcha_answer", "")
    if captcha_answer != expected:
        new_q = generate_captcha()
        return jsonify({"error": "Incorrect captcha answer. Please try again.", "new_captcha": new_q}), 400

    business_id = data.get("business_id")
    rating = data.get("rating")
    comment = data.get("comment", "").strip()

    user = get_current_user()
    reviewer_name = user["display_name"]

    if not business_id or not rating:
        return jsonify({"error": "Rating and business are required."}), 400

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Rating must be between 1 and 5."}), 400

    db = get_db()
    db.execute(
        "INSERT INTO reviews (business_id, user_id, reviewer_name, rating, comment) VALUES (?,?,?,?,?)",
        (business_id, session["user_id"], reviewer_name, rating, comment),
    )
    db.commit()

    new_q = generate_captcha()
    return jsonify({"success": True, "new_captcha": new_q}), 201


@app.route("/api/captcha")
def api_captcha():
    question = generate_captcha()
    return jsonify({"question": question})


@app.route("/api/deals")
def api_deals():
    db = get_db()
    active = request.args.get("active", "")
    query = """
        SELECT d.*, b.name AS business_name, b.category AS business_category
        FROM deals d
        JOIN businesses b ON b.id = d.business_id
    """
    if active == "true":
        query += " WHERE d.expiry_date >= date('now')"
    query += " ORDER BY d.expiry_date ASC"
    rows = db.execute(query).fetchall()
    return jsonify([{
        "id": r["id"],
        "business_id": r["business_id"],
        "business_name": r["business_name"],
        "business_category": r["business_category"],
        "title": r["title"],
        "description": r["description"],
        "discount_text": r["discount_text"],
        "coupon_code": r["coupon_code"],
        "expiry_date": r["expiry_date"],
    } for r in rows])


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

with app.app_context():
    init_db()
    seed_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
