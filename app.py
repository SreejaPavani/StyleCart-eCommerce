import os
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    send_from_directory,
)
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector

app = Flask(__name__)

# Secret key for session signing
app.secret_key = os.getenv("SECRET_KEY", "stylecart_super_secret_dev_key_2026")


def get_db_connection():
    """Establishes database connection using environment variables or local fallbacks."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "Sree@8794"),
        database=os.getenv("DB_NAME", "stylecart"),
        port=int(os.getenv("DB_PORT", 3306)),
    )


# --- Access Control Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in first.", "warning")
            return redirect(url_for("login", next=request.url))
        if session.get("role") != "admin":
            flash("Administrator clearance required.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated_function


# Explicit image routing fallback
@app.route("/static/images/<path:filename>")
def serve_image(filename):
    image_dir = os.path.join(app.root_path, "static", "images")
    return send_from_directory(image_dir, filename)


# --- Authentication Routes ---
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please fill in all fields.", "warning")
            return render_template("register.html")

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                flash("An account with this email already exists.", "danger")
                return render_template("register.html")

            # Check if this is the first user; if so, make them admin
            cursor.execute("SELECT COUNT(*) AS count FROM users")
            user_count = cursor.fetchone()["count"]
            role = "admin" if user_count == 0 else "user"

            cursor.execute(
                "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                (name, email, hashed_password, role),
            )
            conn.commit()

            flash("Account created! Please sign in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            conn.rollback()
            flash(f"Registration error: {str(e)}", "danger")
        finally:
            cursor.close()
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        # Supports both hashed passwords and legacy plain text passwords during migration
        valid_password = False
        if user:
            user_pw = user.get("password", "")
            if user_pw.startswith("scrypt:") or user_pw.startswith("pbkdf2:"):
                valid_password = check_password_hash(user_pw, password)
            else:
                valid_password = (user_pw == password)

        if user and valid_password:
            session["user_id"] = user["user_id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]
            session["role"] = user.get("role", "user")
            session.modified = True

            flash(f"Welcome back, {user['name']}!", "success")
            if session["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("home"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


# --- Storefront Routes ---
@app.route("/")
def home():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products ORDER BY product_id ASC")
    products_list = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("index.html", products=products_list)


@app.route("/products")
def products():
    category = request.args.get("category")
    search = request.args.get("search")
    sort = request.args.get("sort")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if category:
        query += " AND category = %s"
        params.append(category)

    if search:
        query += " AND (name LIKE %s OR description LIKE %s OR brand LIKE %s)"
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param])

    if sort == "low":
        query += " ORDER BY price ASC"
    elif sort == "high":
        query += " ORDER BY price DESC"
    elif sort == "rating":
        query += " ORDER BY rating DESC"
    else:
        query += " ORDER BY product_id ASC"

    cursor.execute(query, tuple(params))
    items = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template(
        "products.html",
        products=items,
        category=category,
        search=search,
        sort=sort,
    )


@app.route("/product/<int:product_id>")
def product_details(product_id):
    if "recently_viewed" not in session:
        session["recently_viewed"] = []

    viewed = list(session.get("recently_viewed", []))
    if product_id in viewed:
        viewed.remove(product_id)
    viewed.insert(0, product_id)
    session["recently_viewed"] = viewed[:5]
    session.modified = True

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "UPDATE products SET view_count = COALESCE(view_count, 0) + 1 WHERE product_id = %s",
            (product_id,),
        )
        conn.commit()
    except Exception:
        conn.rollback()

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
    product = cursor.fetchone()

    if not product:
        cursor.close()
        conn.close()
        return "Product not found", 404

    reviews = []
    try:
        cursor.execute(
            """
            SELECT r.*, u.name AS reviewer_name 
            FROM reviews r 
            JOIN users u ON r.user_id = u.user_id 
            WHERE r.product_id = %s 
            ORDER BY r.review_date DESC
            """,
            (product_id,),
        )
        reviews = cursor.fetchall()
    except Exception:
        pass

    similar_products = []
    try:
        cursor.execute(
            """
            SELECT * FROM products 
            WHERE category = %s AND product_id != %s 
            ORDER BY rating DESC 
            LIMIT 4
            """,
            (product.get("category"), product_id),
        )
        similar_products = cursor.fetchall()
    except Exception:
        pass

    also_bought = []
    try:
        cursor.execute(
            """
            SELECT DISTINCT p.* 
            FROM order_items oi1
            JOIN order_items oi2 ON oi1.order_id = oi2.order_id
            JOIN products p ON oi2.product_id = p.product_id
            WHERE oi1.product_id = %s AND oi2.product_id != %s 
            LIMIT 4
            """,
            (product_id, product_id),
        )
        also_bought = cursor.fetchall()
    except Exception:
        pass

    cursor.close()
    conn.close()
    return render_template(
        "product_details.html",
        product=product,
        reviews=reviews,
        similar_products=similar_products,
        also_bought=also_bought,
    )


# --- Shopping Cart ---
@app.route("/cart")
def view_cart():
    cart = session.get("cart", {})
    cart_items = []
    subtotal = 0.0

    if cart:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        format_strings = ",".join(["%s"] * len(cart))
        cursor.execute(
            f"SELECT * FROM products WHERE product_id IN ({format_strings})",
            tuple(cart.keys()),
        )
        db_items = cursor.fetchall()
        cursor.close()
        conn.close()

        for item in db_items:
            p_id = str(item["product_id"])
            item_data = cart[p_id]
            qty = item_data.get("quantity", 1)
            line_total = float(item["price"]) * qty
            subtotal += line_total
            cart_items.append(
                {
                    "product_id": item["product_id"],
                    "name": item["name"],
                    "price": item["price"],
                    "image": item["image"],
                    "size": item_data.get("size", "Standard"),
                    "quantity": qty,
                    "total": line_total,
                }
            )

    tax = subtotal * 0.05
    grand_total = subtotal + tax
    return render_template(
        "cart.html",
        cart_items=cart_items,
        subtotal=subtotal,
        tax=tax,
        grand_total=grand_total,
    )


@app.route("/cart/add/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    quantity = int(request.form.get("quantity", 1))
    size = request.form.get("size", "M")

    if "cart" not in session:
        session["cart"] = {}

    cart = session["cart"]
    p_id = str(product_id)

    if p_id in cart:
        cart[p_id]["quantity"] += quantity
    else:
        cart[p_id] = {"quantity": quantity, "size": size}

    session["cart"] = cart
    session.modified = True
    flash("Item added to cart!", "success")
    return redirect(request.referrer or url_for("home"))


@app.route("/cart/remove/<int:product_id>")
def remove_from_cart(product_id):
    cart = session.get("cart", {})
    p_id = str(product_id)
    if p_id in cart:
        del cart[p_id]
        session["cart"] = cart
        session.modified = True
        flash("Item removed from cart.", "info")
    return redirect(url_for("view_cart"))


@app.route("/review/add/<int:product_id>", methods=["POST"])
@login_required
def add_review(product_id):
    user_id = session.get("user_id")
    rating = int(request.form.get("rating", 5))
    review_text = request.form.get("review_text", "").strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO reviews (user_id, product_id, rating, review_text) VALUES (%s, %s, %s, %s)",
            (user_id, product_id, rating, review_text),
        )
        conn.commit()
        flash("Review submitted!", "success")
    except Exception:
        conn.rollback()
        flash("Could not submit review.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("product_details", product_id=product_id))


# --- Admin Dashboard & Operations ---
@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS count FROM users")
    total_users = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM products")
    total_products = cursor.fetchone()["count"]

    total_orders = 0
    revenue = 0.0
    recent_orders = []

    try:
        cursor.execute("SELECT COUNT(*) AS count, COALESCE(SUM(total_amount), 0) AS rev FROM orders")
        res = cursor.fetchone()
        total_orders = res["count"]
        revenue = float(res["rev"])

        cursor.execute("""
            SELECT o.order_id AS id, u.name AS customer_name, o.total_amount AS amount, o.order_status AS status
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            ORDER BY o.order_date DESC
            LIMIT 5
        """)
        recent_orders = cursor.fetchall()
    except Exception:
        pass

    cursor.close()
    conn.close()

    return render_template(
        "dashboard.html",
        total_users=total_users,
        total_products=total_products,
        total_orders=total_orders,
        revenue=revenue,
        recent_orders=recent_orders,
        chart_labels=["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
        chart_data=[0, 0, 0, 0, 0, revenue],
    )


@app.route("/admin/api/analytics")
@admin_required
def admin_analytics_api():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    categories, category_sales = [], []
    try:
        cursor.execute("SELECT category, COUNT(*) as cnt FROM products GROUP BY category")
        for row in cursor.fetchall():
            categories.append(row["category"])
            category_sales.append(row["cnt"])
    except Exception:
        pass

    top_names, top_units = [], []
    try:
        cursor.execute("SELECT name, COALESCE(stock, 10) as units FROM products ORDER BY rating DESC LIMIT 5")
        for row in cursor.fetchall():
            top_names.append(row["name"])
            top_units.append(row["units"])
    except Exception:
        pass

    cursor.close()
    conn.close()

    return jsonify({
        "categories": categories,
        "category_sales": category_sales,
        "top_product_names": top_names,
        "top_product_units": top_units,
    })


@app.route("/admin/products")
@admin_required
def admin_products():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products ORDER BY product_id DESC")
    catalog = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("products.html", products=catalog)


@app.route("/admin/products/add", methods=["GET", "POST"])
@admin_required
def admin_add_product():
    if request.method == "POST":
        name = request.form.get("name")
        brand = request.form.get("brand")
        category = request.form.get("category")
        subcategory = request.form.get("subcategory", "")
        price = float(request.form.get("price", 0))
        stock = int(request.form.get("stock", 0))
        color = request.form.get("color", "")
        sizes = request.form.get("sizes", "S,M,L,XL")
        image = request.form.get("image")
        description = request.form.get("description", "")

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO products (name, brand, category, subcategory, price, stock, color, sizes, image, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (name, brand, category, subcategory, price, stock, color, sizes, image, description),
            )
            conn.commit()
            flash("Product published successfully!", "success")
            return redirect(url_for("admin_products"))
        except Exception as e:
            conn.rollback()
            flash(f"Error saving product: {str(e)}", "danger")
        finally:
            cursor.close()
            conn.close()

    return render_template("add_product.html")


@app.route("/admin/products/edit/<int:product_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form.get("name")
        brand = request.form.get("brand")
        category = request.form.get("category")
        subcategory = request.form.get("subcategory", "")
        price = float(request.form.get("price", 0))
        stock = int(request.form.get("stock", 0))
        color = request.form.get("color", "")
        sizes = request.form.get("sizes", "")
        image = request.form.get("image")
        description = request.form.get("description", "")

        try:
            cursor.execute(
                """
                UPDATE products 
                SET name=%s, brand=%s, category=%s, subcategory=%s, price=%s, stock=%s, color=%s, sizes=%s, image=%s, description=%s
                WHERE product_id=%s
                """,
                (name, brand, category, subcategory, price, stock, color, sizes, image, description, product_id),
            )
            conn.commit()
            flash("Product updated successfully!", "success")
            return redirect(url_for("admin_products"))
        except Exception as e:
            conn.rollback()
            flash(f"Update failed: {str(e)}", "danger")

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()

    if not product:
        flash("Product not found.", "warning")
        return redirect(url_for("admin_products"))

    return render_template("edit_product.html", product=product)


@app.route("/admin/products/delete/<int:product_id>", methods=["POST"])
@admin_required
def admin_delete_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM products WHERE product_id = %s", (product_id,))
        conn.commit()
        flash("Product deleted.", "info")
    except Exception as e:
        conn.rollback()
        flash(f"Could not delete product: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_products"))


@app.route("/admin/orders")
@admin_required
def admin_orders():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    orders_list = []
    try:
        cursor.execute("""
            SELECT o.*, u.name AS customer_name
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.user_id
            ORDER BY o.order_date DESC
        """)
        orders_list = cursor.fetchall()
    except Exception:
        pass
    finally:
        cursor.close()
        conn.close()

    return render_template("orders.html", orders=orders_list)


@app.route("/admin/orders/update-status", methods=["POST"])
@admin_required
def admin_update_order_status():
    order_id = request.form.get("order_id")
    order_status = request.form.get("order_status")
    tracking_number = request.form.get("tracking_number", "").strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE orders SET order_status = %s, tracking_number = %s WHERE order_id = %s",
            (order_status, tracking_number, order_id),
        )
        conn.commit()
        flash(f"Order #{order_id} status updated!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error updating order: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_orders"))


@app.route("/admin/users")
@admin_required
def admin_users():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    users_list = []
    try:
        cursor.execute("""
            SELECT u.*, COUNT(o.order_id) AS order_count
            FROM users u
            LEFT JOIN orders o ON u.user_id = o.user_id
            GROUP BY u.user_id
            ORDER BY u.user_id DESC
        """)
        users_list = cursor.fetchall()
    except Exception:
        cursor.execute("SELECT *, 0 AS order_count FROM users ORDER BY user_id DESC")
        users_list = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return render_template("users.html", users=users_list)


@app.route("/admin/users/update-role", methods=["POST"])
@admin_required
def admin_update_user_role():
    target_user_id = request.form.get("user_id")
    new_role = request.form.get("new_role")

    if str(target_user_id) == str(session.get("user_id")):
        flash("You cannot change your own administrative permissions.", "warning")
        return redirect(url_for("admin_users"))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET role = %s WHERE user_id = %s", (new_role, target_user_id))
        conn.commit()
        flash("User role updated successfully.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Could not update role: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_users"))


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
