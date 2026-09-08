import os
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory,
)
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


# Explicit image routing fallback to handle cross-platform path resolution
@app.route("/static/images/<path:filename>")
def serve_image(filename):
    image_dir = os.path.join(app.root_path, "static", "images")
    return send_from_directory(image_dir, filename)


# Home Page
@app.route("/")
def home():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products ORDER BY rating DESC LIMIT 8")
    products = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("index.html", products=products)


# Catalog & Category Page
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
        query += " ORDER BY product_id DESC"

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


# Product Details Page
@app.route("/product/<int:product_id>")
def product_details(product_id):
    # Session-based recently viewed tracker
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

    # Safe view counter update
    try:
        cursor.execute(
            "UPDATE products SET view_count = COALESCE(view_count, 0) + 1 WHERE product_id = %s",
            (product_id,),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()

    # Main product fetch
    cursor.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
    product = cursor.fetchone()

    if not product:
        cursor.close()
        conn.close()
        return "Product not found", 404

    # Safe reviews fetch
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

    # Safe similar products fetch
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

    # Safe 'customers also bought' collaborative recommendation
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


# Shopping Cart Operations
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
    flash("Item added to cart successfully!", "success")
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


# Add Review Route
@app.route("/review/add/<int:product_id>", methods=["POST"])
def add_review(product_id):
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in to submit a review.", "warning")
        return redirect(url_for("product_details", product_id=product_id))

    rating = int(request.form.get("rating", 5))
    review_text = request.form.get("review_text", "").strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO reviews (user_id, product_id, rating, review_text) 
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, product_id, rating, review_text),
        )
        conn.commit()
        flash("Review submitted!", "success")
    except Exception as e:
        conn.rollback()
        flash("Could not submit review.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("product_details", product_id=product_id))


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)