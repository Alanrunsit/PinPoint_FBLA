import sqlite3
import os
import logging
import random
import functools
import atexit
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Flask, render_template, request, jsonify, session, g, redirect, url_for
)
from apscheduler.schedulers.background import BackgroundScheduler

from scraper import run_scraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
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
            website_url TEXT,
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
            source TEXT NOT NULL DEFAULT 'seed',
            active INTEGER NOT NULL DEFAULT 1,
            scraped_at TIMESTAMP,
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

    for col, definition in [
        ("source", "TEXT NOT NULL DEFAULT 'seed'"),
        ("active", "INTEGER NOT NULL DEFAULT 1"),
        ("scraped_at", "TIMESTAMP"),
    ]:
        try:
            db.execute(f"ALTER TABLE deals ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass

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
        ("Pasquale Brick Pizza", "food", "Experience the finest Italian flavors at Pasquale Brick Oven, Milltown’s premier destination for authentic Italian cuisine.", "120 Ryders Ln", "(732) 846-2222", "https://www.pasqualebrickoven.com/", "https://www.pasqualebrickoven.com/wp-content/uploads/2025/06/ADaSGRG.jpg"),
        ("Stage Left Steak", "food", "Enjoy classic steakhouse dining at Stage left steak, a New Brunswick landmark known for premium steaks and an impressive wine selection.", "5 Livingston Ave", "(732) 828-4444", "https://www.stageleft.com/", "https://tb-static.uber.com/prod/image-proc/processed_images/742c8939ee58d6da5635870e91166146/268ee1a1296808aa6eae11eb597de84d.jpeg"),
        ("The Edison Automat", "food", "Offers modern comfort food in the Edison Automat, a trendy spot near Piscataway. It's known for creative burgers, fresh salads, and a fun, casual atmosphere.", "1963 Oak Tree Rd", "(732) 548-7676", "https://www.theedisonautomat.com/", "https://images.squarespace-cdn.com/content/v1/5ce40695cd24900001e0b9d0/1771602506563-VD0MSG6V0DVWZ1NDDRVK/IMG_2145.jpg?format=2500w"),
        ("Jay and Silent Bob’s Secret Stash", "retail", "Explore pop culture collectibles at Jay and Silent Bob's secret stash, a famous comic book shop in Red Bank Nj owned by Kevin Smith (film maker). Featuring comics, action figures, and movie memorabilia.", "65 Broad st", "(555) 567-8901", "https://www.elmstreetbooks.com", "https://upload.wikimedia.org/wikipedia/commons/4/4c/7.9.12SecretStashByLuigiNovi1.jpg"),
        ("Kanibal & Co ", "retail ", "A stylish independent boutique in downtown Jersey City offering curated home goods, artisan gifts, candles, jewelry, and locally inspired finds with a modern-urban aesthetic.", "197 Montgomery St", "(201) 360-9688", "https://www.shopkanibal.com/", "https://www.shopkanibal.com/cdn/shop/files/KanibalCo_Summit_Interiors-27.jpg?v=1767379601&width=2400"),
        ("Just Jersey", "retail", "Shop locally made products at Just Jersey, a specialty store that sells New Jersey-themed gifts, food items, and handmade goods from local businesses.", "163 South St", "(973) 590-2820", "https://www.justjerseygoods.com/?srsltid=AfmBOopbz89fn7wTZMORdkLbQWBleNujiXDR9uU1q6bXh0FZogjOVrn1", "https://www.justjerseygoods.com/cdn/shop/files/storefront_909b8cd8-6d3e-435c-85d6-ab611dd44776.jpg?v=1689023554&width=5184"),
        ("PALS Learning Center", "services", "Support academic growth at PALS learning center in East Brunswick NJ, a local tutoring center that provides personalized instruction in reading, math, and test preparation for students of all ages.", "B2 Brier Hill Ct", "(732) 307-7243", "https://palseastbrunswick.com/", "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQOdJ2YlnIadG6TxgBu3e4WwN5rKmqbNwJ_Yw&s"),
       ("Natural Care Holistic Center", "health", "A community-centric holistic health practitioner center offering personalized care that blends mind-body approaches, nutrition support, and natural therapies to help people improve overall wellness beyond standard medical treatments.", "35 W Main St", "(201) 428-7474", "https://naturalcarecenternj.com/", "https://naturalcarecenternj.com/wp-content/uploads/2024/04/Colonic-Room-2.jpeg"),
       ("Lewis Holistic Healing Institute", "health", "A holistic health and functional medicine practice where a naturopathic doctor blends natural medicine, acupuncture, and Chinese herbal therapy to treat chronic conditions by finding and addressing the root cause of illness rather than just symptoms.", "340 E Northfield Rd Suite 2E", "(973) 486-0148", "https://drlisalewis.com/", "https://s3-media0.fl.yelpcdn.com/bphoto/R73z_0wEUfrBGYRbCopYOw/348s.jpg"),
       ("Revolution Barber Company", "services", "A small, local barber shop where the owner blends old-school barbershop traditions with modern precision fades and hot towel shaves in a relaxed, community-focused atmosphere.", "10 N Black Horse Pike", "(856) 360-0660", "https://www.revbarberco.com/", "https://s3-media0.fl.yelpcdn.com/bphoto/_-piQnqTNcbeS7qiaAw2Hw/348s.jpg"),
       ("The Dubliner Pub and Music Hall", "entertainment", "A lively Irish pub with a cozy, below-the-surface feel that features live music, open mic nights, and a fun crowd — perfect for casual nights out or catching local bands.", "30 Monmouth St", "(732) 747-6699", "https://www.thedublinhouse.co/", "https://s3-media0.fl.yelpcdn.com/bphoto/O9neZ5DfE_7JeBqs-gPrnQ/258s.jpg"),
       ("The Stress Factory Comedy Club", "entertainment", "A classic underground-style comedy club where up-and-coming and well-known comedians perform in an intimate space that feels authentic and up close.", "90 Church St", "(732) 545-4242", "https://newbrunswick.stressfactory.com/", "https://www.newbrunswick.com/images/listing/upload/fullsize/1491416230-4-stressfactorystage11.jpg"),
   ]

    for b in businesses:
        db.execute(
            "INSERT INTO businesses (name, category, description, address, phone, website_url, image_url) VALUES (?,?,?,?,?,?,?)",
            b,
        )

    reviews_data = [
        (1, "Louis.", 5, "Fresh food served quickly, much better flavor and quality."),
       (1, "R A.", 4, "Pasquale’s is a great place for very good pizza. The food, from entrees to soups, is always delicious."),
       (2, "Anthony.", 5, "This is easily one of the best steakhouses in the area, with high quality cuts of meat, incredible flavor, and a wine list that pairs perfectly with every single meal."),
       (2, "L.P.", 5, "The food is consistently excellent, the staff is professional and friendly, and every visit feels like a true 5 star experience."),
       (2, "Gloria.", 5, "So good that we had our wedding here!!"),
       (3, "Jasmine.", 5, "The food is always very neat, fresh, and flavorful, and the portions are generous!"),
       (3, "Chris.", 4, "Their menu has something for literally everyone, from creative sandwiches to lighter options."),
       (4, "Mike.", 5, "Even if you’re just browsing, it’s a really fun place to visit, especially if you’re a fan of movies, superheroes, or pop culture."),
       (4, "Lauren.", 4, "The store has an amazing selection of comics and collectibles, and the staff is super knowledgeable and friendly."),
       (5, "Emily R.", 4, "Chic little shop with perfectly curated gifts and great vibe."),
       (6, "Amanda.", 4, "I love that everything in the store is made in New Jersey, and it’s the perfect place to find gifts."),
       (6, "Steve.", 5, "The store is well organized, the products are high quality, and it’s a great way to support local businesses."),
       (7, "Priya P.", 5, "The tutors are patient and knowledgeable, and we saw a noticeable improvement in my child’s confidence and grades."),
       (7, "Micheal.", 4, "They create individualized learning plans that really focus on each student’s needs, and the staff communicates clearly with parents about progress and goals."),
       (8, "David L.", 5, "The practitioners take time to really listen and offer tailored plans that help me feel more balanced physically."),
       (9, "Rohan S.", 5, "Dr. Lewis has a unique approach that combines natural therapies with traditional principles, making each session feel both powerful and supportive."),
       (9, "Ty L.", 4, "The healing here doesn’t feel like a regular doctor visit — it’s restorative and personalized, focusing on wellness."),
       (10, "Brady V.", 5, "Courtney and the crew take their time with every cut, making sure you leave looking your best."),
       (11, "Ben C.", 4, "Great drinks and a laid-back vibe make this a must-visit spot for anyone who loves live performances and good times."),
       (12, "Arya P.", 5, "Amazing energy, great drinks, and nonstop laughs."),
       (12, "Omar P.", 4, "The comedians are hilarious and the small room makes every set feel personal."),
    ]

    for r in reviews_data:
        db.execute(
            "INSERT INTO reviews (business_id, reviewer_name, rating, comment) VALUES (?,?,?,?)",
            r,
        )

    today = datetime.now()
    deals_data = [
        (1, "Pizza Night Special", "Get a free appetizer with any large pizza order.", "Free Appetizer", "PIZZA1", (today + timedelta(days=30)).strftime("%Y-%m-%d")),
        (2, "Date Night Deal", "Two steakhouse entrees and a bottle of house wine.", "20% Off", "STEAK25", (today + timedelta(days=45)).strftime("%Y-%m-%d")),
        (3, "Burger & Brew Combo", "Any burger with a craft beer or shake at a special price.", "$5 Off", "BURGER5", (today + timedelta(days=20)).strftime("%Y-%m-%d")),
        (4, "Comic Collector Bundle", "Buy 3 comics and get the 4th free from the staff picks wall.", "Buy 3 Get 1", "COMIC4FREE", (today + timedelta(days=60)).strftime("%Y-%m-%d")),
        (5, "Gift Box Special", "Curated gift box with candle, jewelry, and home goods.", "15% Off", "KANIBAL15", (today + timedelta(days=14)).strftime("%Y-%m-%d")),
        (6, "Jersey Pride Pack", "Bundle any three locally made products at a discount.", "$10 Off", "JERSEY10", (today + timedelta(days=25)).strftime("%Y-%m-%d")),
        (9, "First Visit Wellness", "First holistic consultation and treatment plan at a reduced rate.", "50% Off First Visit", "HEAL50", (today + timedelta(days=35)).strftime("%Y-%m-%d")),
        (12, "Group Laugh Night", "Book a table for 6+ people and save on tickets.", "30% Off Groups", "LAUGH30", (today + timedelta(days=40)).strftime("%Y-%m-%d")),
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

    q = request.args.get("q", "").strip()
    if q:
        conditions.append("(b.name LIKE ? OR b.category LIKE ? OR b.description LIKE ? OR b.address LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like, like])

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
            "website_url": row["website_url"],
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
        "website_url": row["website_url"],
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
    conditions = []
    if active == "true":
        conditions.append("d.expiry_date >= date('now')")
        conditions.append("d.active = 1")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
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
        "source": r["source"],
    } for r in rows])


# ---------------------------------------------------------------------------
# Scraper API
# ---------------------------------------------------------------------------

@app.route("/api/scraper/run", methods=["POST"])
def api_run_scraper():
    """Manually trigger the deal scraper."""
    count = run_scraper(DATABASE)
    return jsonify({"success": True, "deals_scraped": count})


@app.route("/api/scraper/status")
def api_scraper_status():
    """Return info about the next scheduled scrape."""
    job = scheduler.get_job("deal_scraper") if scheduler.running else None
    if job and job.next_run_time:
        return jsonify({
            "scheduler_running": True,
            "next_run": job.next_run_time.isoformat(),
        })
    return jsonify({"scheduler_running": False, "next_run": None})


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

with app.app_context():
    init_db()
    seed_db()

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(
    func=lambda: run_scraper(DATABASE),
    trigger="interval",
    hours=12,
    id="deal_scraper",
    name="Scrape business websites for deals",
    misfire_grace_time=3600,
)

if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))

if __name__ == "__main__":
    app.run(debug=True, port=5000)
