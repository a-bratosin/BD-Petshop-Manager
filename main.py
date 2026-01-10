# Route for creating a new customer
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from os import getenv
from dotenv import load_dotenv
from pyodbc import connect, Binary
import hashlib
import base64
import re
import uuid
from datetime import datetime, timedelta
# FORMAT: UID is the user, PWD is the password
load_dotenv()
conn = connect(getenv("SQL_CONNECTION_STRING"))

print("Connected!")


app = Flask(__name__)
app.config['SECRET_KEY'] = getenv("SESSION_KEY")
app.config['SERVER_INSTANCE_ID'] = uuid.uuid4().hex
MAX_IMAGE_BYTES = 5 * 1024 * 1024

@app.before_request
def enforce_server_session():
    server_id = app.config.get('SERVER_INSTANCE_ID')
    if session:
        session_server = session.get('server_instance')
        if session_server and session_server != server_id:
            session.clear()
        elif not session_server:
            session['server_instance'] = server_id

def fetch_categories(cursor):
    cursor.execute(
        """
        SELECT CategorieId, CategorieNume
        FROM dbo.Categorie
        ORDER BY CategorieNume
        """
    )
    categories = [
        {"id": row.CategorieId, "name": row.CategorieNume, "subcategories": []}
        for row in cursor.fetchall()
        if row.CategorieNume
    ]
    categories_by_id = {cat["id"]: cat for cat in categories}

    cursor.execute(
        """
        SELECT SubcategorieId, SubcategorieNume, CategorieId
        FROM dbo.Subcategorie
        ORDER BY SubcategorieNume
        """
    )
    for row in cursor.fetchall():
        if not row.SubcategorieNume:
            continue
        cat = categories_by_id.get(row.CategorieId)
        if cat is not None:
            cat["subcategories"].append({
                "id": row.SubcategorieId,
                "name": row.SubcategorieNume
            })

    return categories

def fetch_product_names(cursor):
    cursor.execute(
        """
        SELECT Descriere
        FROM dbo.Produs
        WHERE Descriere IS NOT NULL
        ORDER BY Descriere
        """
    )
    return [row.Descriere for row in cursor.fetchall()]

def build_products(rows):
    products = []
    for row in rows:
        image_base64 = None
        if row.Imagine:
            image_base64 = base64.b64encode(row.Imagine).decode('utf-8')
        products.append({
            "id": row.ProdusId,
            "image": image_base64,
            "stoc": int(row.Stoc) if row.Stoc is not None else 0,
            "pret": float(row.Pret) if row.Pret is not None else 0.0,
            "descriere": row.Descriere
        })
    return products

def is_customer_session():
    return session.get('loggedin') and session.get('role') == 'customer'

def allow_customer_or_guest():
    if session.get('loggedin'):
        return session.get('role') == 'customer'
    return True

@app.route("/")
def hello_world():
    return redirect(url_for('customer_shop'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    next_path = request.args.get('next') or request.form.get('next') or ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor = conn.cursor()
        # Așa trimite sanitizat inputul de la utilizator
        cursor.execute('SELECT UserId,Username,UserCategory FROM Utilizatori WHERE Username=? and Password=?', (username,password_hash))
        account = cursor.fetchone()
        if account:
            session['loggedin'] = True
            session['id'] = account[0]
            session['username'] = account[1].strip()
            session['role'] = account[2].strip()
            session['server_instance'] = app.config.get('SERVER_INSTANCE_ID')
            print(session)
            # Redirect employee to dashboard
            if session['role'] == 'employee':
                return redirect(url_for('employee_dashboard'))
            else:
                if next_path.startswith('/'):
                    return redirect(next_path)
                return redirect(url_for('customer_dashboard'))
        else:
            msg = 'Incorrect username/password!'
    return render_template('login.html', msg=msg, next=next_path)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('loggedin'):
        if session.get('role') == 'customer':
            return redirect(url_for('customer_shop'))
        return redirect(url_for('employee_dashboard'))

    if request.method == 'POST':
        nume = request.form.get('Nume')
        prenume = request.form.get('Prenume')
        email = request.form.get('Email')
        telefon = request.form.get('Telefon')
        strada = request.form.get('Strada')
        numar = request.form.get('Numar')
        oras = request.form.get('Oras')
        judet = request.form.get('Judet')
        password = request.form.get('Password')
        password_confirm = request.form.get('PasswordConfirm')

        if not (nume and prenume and email and telefon and strada and numar and oras and judet and password and password_confirm):
            flash("All fields are required.")
            return redirect(request.url)
        if password != password_confirm:
            flash("Passwords do not match.")
            return redirect(request.url)

        if not re.fullmatch(r'\d{10}', telefon):
            flash("Phone number must be exactly 10 digits.")
            return redirect(request.url)
        if not re.fullmatch(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            flash("Invalid email address format.")
            return redirect(request.url)

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM dbo.Client WHERE ClientTelefon = ?", (telefon,))
        exists = cursor.fetchone()[0]
        if exists:
            flash("A customer with this phone already exists.")
            return redirect(request.url)

        cursor.execute("SELECT COUNT(*) FROM dbo.Utilizatori WHERE Username = ?", (email,))
        user_exists = cursor.fetchone()[0]
        if user_exists:
            flash("A user with this address already exists.")
            return redirect(request.url)

        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            cursor.execute("""
                INSERT INTO dbo.Utilizatori (Username, Password, UserCategory)
                OUTPUT INSERTED.UserId
                VALUES (?, ?, ?)
            """, (email, password_hash, 'customer'))
            user_id = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO dbo.Client (UserId, ClientNume, ClientPrenume, ClientTelefon, ClientStrada, ClientNumar, ClientOras, ClientJudet)
                OUTPUT INSERTED.ClientId
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, nume, prenume, telefon, strada, numar, oras, judet))
            client_id = cursor.fetchone()[0]

            if request.form.get('CardFidelitate'):
                now = datetime.now()
                cursor.execute("""
                    INSERT INTO dbo.CardFidelitate (ClientId, DataInregistrarii)
                    VALUES (?, ?)
                """, (client_id, now))

            conn.commit()
            session['loggedin'] = True
            session['id'] = user_id
            session['username'] = email.strip()
            session['role'] = 'customer'
            session['server_instance'] = app.config.get('SERVER_INSTANCE_ID')
            flash("Registration successful! You're now logged in.")
            return redirect(url_for('customer_dashboard'))
        except Exception as e:
            conn.rollback()
            flash(f"An error occurred: {str(e)}")
            return redirect(request.url)

    return render_template('register.html')
# Employee dashboard route
@app.route('/employee-dashboard')
def employee_dashboard():
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))
    return render_template('employee_dashboard.html')


@app.route('/revenues-expenses', methods=['GET', 'POST'])
def revenues_expenses():
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    start_date_str = request.values.get('start_date', '').strip()
    end_date_str = request.values.get('end_date', '').strip()

    totals = None
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
            if end_date < start_date:
                flash("End date must be on or after start date.")
            else:
                end_date = end_date + timedelta(days=1) - timedelta(seconds=1)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT SUM(
                        (
                            SELECT SUM(pc.ProdusComandaCantitate * p.Pret)
                            FROM dbo.ProdusComanda pc
                            JOIN dbo.Produs p ON p.ProdusId = pc.ProdusId
                            WHERE pc.ComandaId = c.ComandaId
                        )
                    ) AS TotalRevenue
                    FROM dbo.Comanda c
                    WHERE c.ComandaData >= ? AND c.ComandaData <= ?
                    """,
                    (start_date, end_date)
                )
                revenue_row = cursor.fetchone()
                revenue = float(revenue_row[0]) if revenue_row and revenue_row[0] is not None else 0.0

                cursor.execute(
                    """
                    SELECT SUM(
                        (
                            SELECT SUM(pl.ProdusLivrareCantitate * p.Cost)
                            FROM dbo.ProdusLivrare pl
                            JOIN dbo.Produs p ON p.ProdusId = pl.ProdusId
                            WHERE pl.LivrareId = l.LivrareId
                        )
                    ) AS TotalExpense
                    FROM dbo.Livrare l
                    WHERE l.DataLivrare >= ? AND l.DataLivrare <= ?
                    """,
                    (start_date, end_date)
                )
                expense_row = cursor.fetchone()
                expense = float(expense_row[0]) if expense_row and expense_row[0] is not None else 0.0

                totals = {
                    "revenue": revenue,
                    "expenses": -expense,
                    "net": revenue - expense,
                }
        except ValueError:
            flash("Invalid date format.")
    elif start_date_str or end_date_str:
        flash("Please select both start and end dates.")

    return render_template(
        'revenues_expenses.html',
        totals=totals,
        start_date=start_date_str,
        end_date=end_date_str
    )



@app.route('/analytics')
def analytics():
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT TOP 1
            cl.ClientId,
            cl.ClientNume,
            cl.ClientPrenume,
            u.Username,
            COUNT(*) AS OrderCount
        FROM dbo.Comanda c
        JOIN dbo.Client cl ON cl.ClientId = c.ClientId
        JOIN dbo.Utilizatori u ON u.UserId = cl.UserId
        GROUP BY cl.ClientId, cl.ClientNume, cl.ClientPrenume, u.Username
        ORDER BY COUNT(*) DESC, cl.ClientId
        """
    )
    row = cursor.fetchone()
    prolific_by_orders = None
    if row:
        prolific_by_orders = {
            "name": f"{row.ClientNume} {row.ClientPrenume}",
            "email": row.Username,
            "count": int(row.OrderCount),
        }

    cursor.execute(
        """
        SELECT TOP 1
            cl.ClientId,
            cl.ClientNume,
            cl.ClientPrenume,
            u.Username,
            SUM(pc.ProdusComandaCantitate * p.Pret) AS TotalSpent
        FROM dbo.Comanda c
        JOIN dbo.ProdusComanda pc ON pc.ComandaId = c.ComandaId
        JOIN dbo.Produs p ON p.ProdusId = pc.ProdusId
        JOIN dbo.Client cl ON cl.ClientId = c.ClientId
        JOIN dbo.Utilizatori u ON u.UserId = cl.UserId
        GROUP BY cl.ClientId, cl.ClientNume, cl.ClientPrenume, u.Username
        ORDER BY SUM(pc.ProdusComandaCantitate * p.Pret) DESC, cl.ClientId
        """
    )
    row = cursor.fetchone()
    prolific_by_spend = None
    if row:
        prolific_by_spend = {
            "name": f"{row.ClientNume} {row.ClientPrenume}",
            "email": row.Username,
            "total": float(row.TotalSpent) if row.TotalSpent is not None else 0.0,
        }

    cursor.execute(
        """
        SELECT TOP 1
            d.DistribuitorId,
            d.DistribuitorNume,
            COUNT(l.LivrareId) AS DeliveryCount
        FROM dbo.Distribuitor d
        LEFT JOIN dbo.Livrare l ON l.DistribuitorId = d.DistribuitorId
        GROUP BY d.DistribuitorId, d.DistribuitorNume
        ORDER BY COUNT(l.LivrareId) DESC, d.DistribuitorId
        """
    )
    row = cursor.fetchone()
    prolific_distributor = None
    if row:
        prolific_distributor = {
            "name": row.DistribuitorNume,
            "count": int(row.DeliveryCount),
        }

    cursor.execute(
        """
        SELECT TOP 1
            d.DistribuitorId,
            d.DistribuitorNume,
            SUM(pl.ProdusLivrareCantitate) AS QuantityTotal
        FROM dbo.Distribuitor d
        LEFT JOIN dbo.Livrare l ON l.DistribuitorId = d.DistribuitorId
        LEFT JOIN dbo.ProdusLivrare pl ON pl.LivrareId = l.LivrareId
        GROUP BY d.DistribuitorId, d.DistribuitorNume
        ORDER BY SUM(pl.ProdusLivrareCantitate) DESC, d.DistribuitorId
        """
    )
    row = cursor.fetchone()
    prolific_distributor_qty = None
    if row and row.QuantityTotal is not None:
        prolific_distributor_qty = {
            "name": row.DistribuitorNume,
            "quantity": int(row.QuantityTotal),
        }

    cursor.execute(
        """
        SELECT TOP 5
            p.ProdusId,
            p.Descriere,
            SUM(pc.ProdusComandaCantitate * p.Pret) AS Revenue
        FROM dbo.Produs p
        JOIN dbo.ProdusComanda pc ON pc.ProdusId = p.ProdusId
        GROUP BY p.ProdusId, p.Descriere
        ORDER BY SUM(pc.ProdusComandaCantitate * p.Pret) DESC, p.ProdusId
        """
    )
    rows = cursor.fetchall()
    top_products = [
        {
            "id": row.ProdusId,
            "name": row.Descriere,
            "revenue": float(row.Revenue) if row.Revenue is not None else 0.0,
        }
        for row in rows
    ]

    return render_template(
        'analytics.html',
        prolific_by_orders=prolific_by_orders,
        prolific_by_spend=prolific_by_spend,
        prolific_distributor=prolific_distributor,
        prolific_distributor_qty=prolific_distributor_qty,
        top_products=top_products
    )

@app.route('/customer-dashboard')
def customer_dashboard():
    if not session.get('loggedin') or session.get('role') != 'customer':
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))
    cart_count = sum(int(qty) for qty in session.get('cart', {}).values())

    return render_template('customer_dashboard.html', cart_count=cart_count)

@app.route('/shop')
def customer_shop():
    if not allow_customer_or_guest():
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    if 'cart' not in session:
        session['cart'] = {}

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT TOP 12
            p.ProdusId,
            p.Imagine,
            p.Stoc,
            p.Pret,
            p.Descriere,
            sales.TotalSold
        FROM dbo.Produs p
        JOIN (
            SELECT
                pc.ProdusId,
                SUM(pc.ProdusComandaCantitate) AS TotalSold
            FROM dbo.ProdusComanda pc
            GROUP BY pc.ProdusId
        ) sales ON sales.ProdusId = p.ProdusId
        ORDER BY sales.TotalSold DESC, p.Descriere
        """
    )
    bestsellers = build_products(cursor.fetchall())

    cursor.execute(
        """
        SELECT TOP 1
            c.CategorieId,
            c.CategorieNume
        FROM dbo.Categorie c
        JOIN dbo.Subcategorie s ON s.CategorieId = c.CategorieId
        JOIN dbo.Produs p ON p.SubcategorieId = s.SubcategorieId
        GROUP BY c.CategorieId, c.CategorieNume
        ORDER BY NEWID()
        """
    )
    category_row = cursor.fetchone()
    random_category = None
    category_products = []
    if category_row:
        random_category = {
            "id": category_row.CategorieId,
            "name": category_row.CategorieNume
        }
        cursor.execute(
            """
            SELECT TOP 12
                p.ProdusId,
                p.Imagine,
                p.Stoc,
                p.Pret,
                p.Descriere
            FROM dbo.Produs p
            JOIN dbo.Subcategorie s ON s.SubcategorieId = p.SubcategorieId
            WHERE s.CategorieId = ?
            ORDER BY p.Descriere
            """,
            (category_row.CategorieId,)
        )
        category_products = build_products(cursor.fetchall())

    cursor.execute(
        """
        SELECT TOP 1
            s.SubcategorieId,
            s.SubcategorieNume
        FROM dbo.Subcategorie s
        JOIN dbo.Produs p ON p.SubcategorieId = s.SubcategorieId
        GROUP BY s.SubcategorieId, s.SubcategorieNume
        ORDER BY NEWID()
        """
    )
    subcategory_row = cursor.fetchone()
    random_subcategory = None
    subcategory_products = []
    if subcategory_row:
        random_subcategory = {
            "id": subcategory_row.SubcategorieId,
            "name": subcategory_row.SubcategorieNume
        }
        cursor.execute(
            """
        SELECT TOP 12
            p.ProdusId,
            p.Imagine,
            p.Stoc,
            p.Pret,
            p.Descriere
            FROM dbo.Produs p
            WHERE p.SubcategorieId = ?
            ORDER BY p.Descriere
            """,
            (subcategory_row.SubcategorieId,)
        )
        subcategory_products = build_products(cursor.fetchall())

    product_names = fetch_product_names(cursor)
    categories = fetch_categories(cursor)
    cart_count = sum(int(qty) for qty in session.get('cart', {}).values())
    is_guest = not session.get('loggedin')

    return render_template(
        'customer_shop.html',
        bestsellers=bestsellers,
        random_category=random_category,
        category_products=category_products,
        random_subcategory=random_subcategory,
        subcategory_products=subcategory_products,
        cart_count=cart_count,
        product_names=product_names,
        categories=categories,
        is_guest=is_guest
    )

@app.route('/shop/search')
def customer_shop_search():
    if not allow_customer_or_guest():
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    query = request.args.get('query', '').strip()
    if not query:
        return redirect(url_for('customer_shop'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            p.ProdusId,
            p.Imagine,
            p.Stoc,
            p.Pret,
            p.Descriere
        FROM dbo.Produs p
        WHERE p.Descriere LIKE ?
        ORDER BY p.Descriere
        """,
        (f"%{query}%",)
    )
    rows = cursor.fetchall()

    products = []
    for row in rows:
        image_base64 = None
        if row.Imagine:
            image_base64 = base64.b64encode(row.Imagine).decode('utf-8')
        products.append({
            "id": row.ProdusId,
            "image": image_base64,
            "stoc": int(row.Stoc) if row.Stoc is not None else 0,
            "pret": float(row.Pret) if row.Pret is not None else 0.0,
            "descriere": row.Descriere
        })

    product_names = fetch_product_names(cursor)
    categories = fetch_categories(cursor)

    cart_count = sum(int(qty) for qty in session.get('cart', {}).values())
    is_guest = not session.get('loggedin')

    return render_template(
        'customer_search.html',
        products=products,
        cart_count=cart_count,
        product_names=product_names,
        categories=categories,
        query=query,
        is_guest=is_guest
    )

@app.route('/shop/category/<int:category_id>')
def customer_category_view(category_id):
    if not allow_customer_or_guest():
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        "SELECT CategorieNume FROM dbo.Categorie WHERE CategorieId = ?",
        (category_id,)
    )
    category_row = cursor.fetchone()
    if not category_row:
        flash("Category not found.")
        return redirect(url_for('customer_shop'))

    cursor.execute(
        """
        SELECT
            p.ProdusId,
            p.Imagine,
            p.Stoc,
            p.Pret,
            p.Descriere
        FROM dbo.Produs p
        JOIN dbo.Subcategorie s ON s.SubcategorieId = p.SubcategorieId
        WHERE s.CategorieId = ?
        ORDER BY p.Descriere
        """,
        (category_id,)
    )
    rows = cursor.fetchall()

    products = []
    for row in rows:
        image_base64 = None
        if row.Imagine:
            image_base64 = base64.b64encode(row.Imagine).decode('utf-8')
        products.append({
            "id": row.ProdusId,
            "image": image_base64,
            "stoc": int(row.Stoc) if row.Stoc is not None else 0,
            "pret": float(row.Pret) if row.Pret is not None else 0.0,
            "descriere": row.Descriere
        })

    product_names = fetch_product_names(cursor)
    categories = fetch_categories(cursor)
    cart_count = sum(int(qty) for qty in session.get('cart', {}).values())
    is_guest = not session.get('loggedin')

    return render_template(
        'customer_category.html',
        products=products,
        cart_count=cart_count,
        product_names=product_names,
        categories=categories,
        heading=f"Category: {category_row.CategorieNume}",
        is_guest=is_guest
    )

@app.route('/shop/subcategory/<int:subcategory_id>')
def customer_subcategory_view(subcategory_id):
    if not allow_customer_or_guest():
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT SubcategorieNume
        FROM dbo.Subcategorie
        WHERE SubcategorieId = ?
        """,
        (subcategory_id,)
    )
    sub_row = cursor.fetchone()
    if not sub_row:
        flash("Subcategory not found.")
        return redirect(url_for('customer_shop'))

    cursor.execute(
        """
        SELECT
            p.ProdusId,
            p.Imagine,
            p.Stoc,
            p.Pret,
            p.Descriere
        FROM dbo.Produs p
        WHERE p.SubcategorieId = ?
        ORDER BY p.Descriere
        """,
        (subcategory_id,)
    )
    rows = cursor.fetchall()

    products = []
    for row in rows:
        image_base64 = None
        if row.Imagine:
            image_base64 = base64.b64encode(row.Imagine).decode('utf-8')
        products.append({
            "id": row.ProdusId,
            "image": image_base64,
            "stoc": int(row.Stoc) if row.Stoc is not None else 0,
            "pret": float(row.Pret) if row.Pret is not None else 0.0,
            "descriere": row.Descriere
        })

    product_names = fetch_product_names(cursor)
    categories = fetch_categories(cursor)
    cart_count = sum(int(qty) for qty in session.get('cart', {}).values())
    is_guest = not session.get('loggedin')

    return render_template(
        'customer_category.html',
        products=products,
        cart_count=cart_count,
        product_names=product_names,
        categories=categories,
        heading=f"Subcategory: {sub_row.SubcategorieNume}",
        is_guest=is_guest
    )

@app.route('/product/<int:product_id>')
def customer_product_details(product_id):
    if not allow_customer_or_guest():
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ProdusId, Imagine, Stoc, Pret, Descriere
        FROM dbo.Produs
        WHERE ProdusId = ?
        """,
        (product_id,)
    )
    row = cursor.fetchone()
    if not row:
        flash("Product not found.")
        return redirect(url_for('customer_shop'))

    image_base64 = None
    if row.Imagine:
        image_base64 = base64.b64encode(row.Imagine).decode('utf-8')

    product = {
        "id": row.ProdusId,
        "image": image_base64,
        "stoc": int(row.Stoc) if row.Stoc is not None else 0,
        "pret": float(row.Pret) if row.Pret is not None else 0.0,
        "descriere": row.Descriere
    }

    categories = fetch_categories(cursor)
    cart_count = sum(int(qty) for qty in session.get('cart', {}).values())
    is_guest = not session.get('loggedin')

    return render_template(
        'customer_product.html',
        product=product,
        cart_count=cart_count,
        categories=categories,
        is_guest=is_guest
    )

@app.route('/cart')
def customer_cart():
    if not allow_customer_or_guest():
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    cart = session.get('cart', {})
    cart_ids = [int(pid) for pid in cart.keys()] if cart else []
    items = []
    total = 0.0

    if cart_ids:
        placeholders = ",".join("?" for _ in cart_ids)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT ProdusId, Descriere, Pret, Imagine
            FROM dbo.Produs
            WHERE ProdusId IN ({placeholders})
            """,
            tuple(cart_ids)
        )
        rows = cursor.fetchall()
        for row in rows:
            qty = int(cart.get(str(row.ProdusId), 0))
            if qty <= 0:
                continue
            price = float(row.Pret) if row.Pret is not None else 0.0
            image_base64 = None
            if row.Imagine:
                image_base64 = base64.b64encode(row.Imagine).decode('utf-8')
            line_total = price * qty
            total += line_total
            items.append({
                "id": row.ProdusId,
                "descriere": row.Descriere,
                "price": price,
                "qty": qty,
                "line_total": line_total,
                "image": image_base64
            })

    cart_count = sum(int(qty) for qty in cart.values())

    is_guest = not session.get('loggedin')

    return render_template('customer_cart.html', items=items, total=total, cart_count=cart_count, is_guest=is_guest)

@app.route('/cart/add', methods=['POST'])
def customer_cart_add():
    if not allow_customer_or_guest():
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    product_id_raw = request.form.get('product_id', '').strip()
    if not product_id_raw.isdigit():
        flash("Invalid product selection.")
        return redirect(request.referrer or url_for('customer_shop'))

    quantity_raw = request.form.get('quantity', '1').strip()
    if not quantity_raw.isdigit():
        flash("Invalid quantity.")
        return redirect(request.referrer or url_for('customer_shop'))

    quantity = int(quantity_raw)
    if quantity <= 0:
        flash("Quantity must be at least 1.")
        return redirect(request.referrer or url_for('customer_shop'))

    product_id = int(product_id_raw)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ProdusId, Stoc, Descriere FROM dbo.Produs WHERE ProdusId = ?",
        (product_id,)
    )
    row = cursor.fetchone()
    if not row:
        flash("Product not found.")
        return redirect(request.referrer or url_for('customer_shop'))

    available_stock = int(row.Stoc) if row.Stoc is not None else 0
    if available_stock <= 0:
        flash("This product is currently out of stock.")
        return redirect(request.referrer or url_for('customer_shop'))

    cart = session.get('cart', {})
    current_qty = int(cart.get(str(product_id), 0))
    if current_qty + quantity > available_stock:
        flash("Not enough stock available for that quantity.")
        return redirect(request.referrer or url_for('customer_shop'))

    cart[str(product_id)] = current_qty + quantity
    session['cart'] = cart
    session.modified = True

    flash(f"Added '{row.Descriere}' to your cart.")
    return redirect(request.referrer or url_for('customer_shop'))

@app.route('/cart/clear', methods=['POST'])
def customer_cart_clear():
    if not allow_customer_or_guest():
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    session['cart'] = {}
    session.modified = True
    flash("Cart cleared.")
    return redirect(url_for('customer_cart'))

@app.route('/cart/remove', methods=['POST'])
def customer_cart_remove():
    if not allow_customer_or_guest():
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    product_id_raw = request.form.get('product_id', '').strip()
    if not product_id_raw.isdigit():
        flash("Invalid product selection.")
        return redirect(url_for('customer_cart'))

    product_id = int(product_id_raw)
    cart = session.get('cart', {})
    if str(product_id) in cart:
        del cart[str(product_id)]
        session['cart'] = cart
        session.modified = True
        flash("Item removed from your cart.")

    return redirect(url_for('customer_cart'))

@app.route('/cart/update', methods=['POST'])
def customer_cart_update():
    if not allow_customer_or_guest():
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    product_id_raw = request.form.get('product_id', '').strip()
    action = request.form.get('action', '').strip().lower()
    if not product_id_raw.isdigit() or action not in {'inc', 'dec'}:
        flash("Invalid cart update request.")
        return redirect(url_for('customer_cart'))

    product_id = int(product_id_raw)
    cart = session.get('cart', {})
    current_qty = int(cart.get(str(product_id), 0))

    if action == 'dec':
        if current_qty <= 0:
            return redirect(url_for('customer_cart'))
        new_qty = current_qty - 1
        if new_qty == 0:
            cart.pop(str(product_id), None)
        else:
            cart[str(product_id)] = new_qty
        session['cart'] = cart
        session.modified = True
        return redirect(url_for('customer_cart'))

    cursor = conn.cursor()
    cursor.execute("SELECT Stoc FROM dbo.Produs WHERE ProdusId = ?", (product_id,))
    row = cursor.fetchone()
    if not row:
        flash("Product not found.")
        return redirect(url_for('customer_cart'))

    available_stock = int(row.Stoc) if row.Stoc is not None else 0
    if current_qty + 1 > available_stock:
        flash("Not enough stock available for that quantity.")
        return redirect(url_for('customer_cart'))

    cart[str(product_id)] = current_qty + 1
    session['cart'] = cart
    session.modified = True

    return redirect(url_for('customer_cart'))

@app.route('/cart/confirm', methods=['POST'])
def customer_cart_confirm():
    if not session.get('loggedin'):
        flash("Please log in or register to place your order.")
        return redirect(url_for('customer_cart'))
    if session.get('role') != 'customer':
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    cart = session.get('cart', {})
    if not cart:
        flash("Your cart is empty.")
        return redirect(url_for('customer_cart'))

    requested = {}
    for pid, qty_raw in cart.items():
        try:
            qty = int(qty_raw)
        except (TypeError, ValueError):
            qty = 0
        if qty > 0:
            requested[int(pid)] = qty

    if not requested:
        flash("Your cart is empty.")
        return redirect(url_for('customer_cart'))

    cursor = conn.cursor()
    cursor.execute(
        "SELECT ClientId FROM dbo.Client WHERE UserId = ?",
        (session.get('id'),)
    )
    client_row = cursor.fetchone()
    if not client_row:
        flash("Customer record not found.")
        return redirect(url_for('customer_cart'))
    client_id = client_row[0]

    placeholders = ",".join("?" for _ in requested)
    cursor.execute(
        f"""
        SELECT ProdusId, Stoc
        FROM dbo.Produs
        WHERE ProdusId IN ({placeholders})
        """,
        tuple(requested.keys())
    )
    product_rows = cursor.fetchall()
    products_by_id = {row.ProdusId: int(row.Stoc) if row.Stoc is not None else 0 for row in product_rows}

    missing = [pid for pid in requested.keys() if pid not in products_by_id]
    if missing:
        flash("Some products no longer exist. Please reselect the items.")
        return redirect(url_for('customer_cart'))

    for pid, qty in requested.items():
        stock = products_by_id[pid]
        if qty > stock:
            flash("Insufficient stock for one or more items.")
            return redirect(url_for('customer_cart'))

    try:
        cursor.execute(
            """
            SELECT DataInregistrarii
            FROM dbo.CardFidelitate
            WHERE ClientId = ?
            """,
            (client_id,)
        )
        card_row = cursor.fetchone()

        now = datetime.now()
        discount_pct = None
        if card_row and card_row[0]:
            years_active = (now - card_row[0]).days / 365.25
            if years_active > 5:
                discount_pct = 7
            elif years_active > 2:
                discount_pct = 3

        cursor.execute(
            """
            INSERT INTO dbo.Comanda (ComandaData, ClientId, AngajatId, ReducereLoialitate)
            OUTPUT INSERTED.ComandaId
            VALUES (?, ?, ?, ?)
            """,
            (now, client_id, None, discount_pct)
        )
        comanda_id = cursor.fetchone()[0]

        for pid, qty in requested.items():
            cursor.execute(
                """
                INSERT INTO dbo.ProdusComanda (ProdusId, ComandaId, ProdusComandaCantitate)
                VALUES (?, ?, ?)
                """,
                (pid, comanda_id, qty)
            )
            cursor.execute(
                "UPDATE dbo.Produs SET Stoc = ? WHERE ProdusId = ?",
                (products_by_id[pid] - qty, pid)
            )

        conn.commit()
        session['cart'] = {}
        session.modified = True
        if discount_pct:
            flash(f"Loyalty discount applied: {discount_pct}%")
        flash("Order placed successfully!")
        return redirect(url_for('customer_orders'))
    except Exception as e:
        conn.rollback()
        flash(f"An error occurred: {str(e)}")
        return redirect(url_for('customer_cart'))


@app.route('/customer-orders')
def customer_orders():
    if not session.get('loggedin') or session.get('role') != 'customer':
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.ComandaId,
            c.ComandaData,
            c.ReducereLoialitate,
            SUM(pc.ProdusComandaCantitate * p.Pret) AS TotalPret
        FROM dbo.Comanda c
        JOIN dbo.Client cl ON cl.ClientId = c.ClientId
        LEFT JOIN dbo.ProdusComanda pc ON pc.ComandaId = c.ComandaId
        LEFT JOIN dbo.Produs p ON p.ProdusId = pc.ProdusId
        WHERE cl.UserId = ?
        GROUP BY c.ComandaId, c.ComandaData, c.ReducereLoialitate
        ORDER BY c.ComandaId DESC
        """,
        (session.get('id'),)
    )
    rows = cursor.fetchall()
    orders = [
        {
            "id": row.ComandaId,
            "date": row.ComandaData,
            "discount_pct": int(row.ReducereLoialitate) if row.ReducereLoialitate is not None else 0,
            "total_price": float(row.TotalPret) if row.TotalPret is not None else 0.0,
        }
        for row in rows
    ]

    return render_template('customer_order_history.html', orders=orders)

@app.route('/customer-order/<int:order_id>')
def customer_order_details(order_id):
    if not session.get('loggedin') or session.get('role') != 'customer':
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.ComandaId,
            c.ComandaData,
            c.ReducereLoialitate
        FROM dbo.Comanda c
        JOIN dbo.Client cl ON cl.ClientId = c.ClientId
        WHERE cl.UserId = ? AND c.ComandaId = ?
        """,
        (session.get('id'), order_id)
    )
    order_row = cursor.fetchone()
    if not order_row:
        flash("Order not found.")
        return redirect(url_for('customer_orders'))

    cursor.execute(
        """
        SELECT
            p.Descriere,
            pc.ProdusComandaCantitate,
            p.Pret
        FROM dbo.ProdusComanda pc
        JOIN dbo.Produs p ON p.ProdusId = pc.ProdusId
        WHERE pc.ComandaId = ?
        ORDER BY p.Descriere
        """,
        (order_id,)
    )
    item_rows = cursor.fetchall()
    items = [
        {
            "product": row.Descriere,
            "qty": row.ProdusComandaCantitate,
            "price": float(row.Pret),
            "line_total": float(row.Pret) * row.ProdusComandaCantitate,
        }
        for row in item_rows
    ]

    order = {
        "id": order_row.ComandaId,
        "date": order_row.ComandaData,
        "discount_pct": int(order_row.ReducereLoialitate) if order_row.ReducereLoialitate is not None else 0,
    }

    return render_template('customer_order_details.html', order=order, items=items)

@app.route('/customer-details')
def customer_details():
    if not session.get('loggedin') or session.get('role') != 'customer':
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.ClientId,
            c.ClientNume,
            c.ClientPrenume,
            c.ClientTelefon,
            c.ClientStrada,
            c.ClientNumar,
            c.ClientOras,
            c.ClientJudet,
            u.Username
        FROM dbo.Client c
        JOIN dbo.Utilizatori u ON u.UserId = c.UserId
        WHERE u.UserId = ?
        """,
        (session.get('id'),)
    )
    client_row = cursor.fetchone()
    if not client_row:
        flash("Customer record not found.")
        return redirect(url_for('customer_dashboard'))

    cursor.execute(
        """
        SELECT DataInregistrarii
        FROM dbo.CardFidelitate
        WHERE ClientId = ?
        """,
        (client_row.ClientId,)
    )
    card_row = cursor.fetchone()
    card_start = card_row[0] if card_row else None

    cursor.execute(
        """
        SELECT MIN(ComandaData)
        FROM dbo.Comanda
        WHERE ClientId = ?
        """,
        (client_row.ClientId,)
    )
    first_order_row = cursor.fetchone()
    first_order_date = first_order_row[0] if first_order_row else None

    from datetime import datetime, timedelta
    now = datetime.now()

    dates = [d for d in [card_start, first_order_date] if d]
    customer_since = min(dates) if dates else None
    customer_years = None
    if customer_since:
        customer_years = round((now - customer_since).days / 365.25, 2)

    loyalty_years = None
    loyalty_discount = 0
    if card_start:
        loyalty_years = round((now - card_start).days / 365.25, 2)
        if loyalty_years > 5:
            loyalty_discount = 7
        elif loyalty_years > 2:
            loyalty_discount = 3

    customer = {
        "name": f"{client_row.ClientNume} {client_row.ClientPrenume}",
        "phone": client_row.ClientTelefon,
        "email": client_row.Username,
        "address": f"{client_row.ClientStrada} {client_row.ClientNumar}, {client_row.ClientOras}, {client_row.ClientJudet}",
        "customer_since": customer_since,
        "customer_years": customer_years,
        "card_start": card_start,
        "loyalty_years": loyalty_years,
        "loyalty_discount": loyalty_discount,
    }

    return render_template('customer_details.html', customer=customer)


@app.route('/customer-edit-profile', methods=['GET', 'POST'])
def customer_edit_profile():
    if not session.get('loggedin') or session.get('role') != 'customer':
        flash("Unauthorized: This action requires customer privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ClientNume, ClientPrenume, ClientStrada, ClientNumar, ClientOras, ClientJudet
        FROM dbo.Client
        WHERE UserId = ?
        """,
        (session.get('id'),)
    )
    row = cursor.fetchone()
    if not row:
        flash("Customer record not found.")
        return redirect(url_for('customer_dashboard'))

    if request.method == 'POST':
        nume = request.form.get('Nume', '').strip()
        prenume = request.form.get('Prenume', '').strip()
        strada = request.form.get('Strada', '').strip()
        numar = request.form.get('Numar', '').strip()
        oras = request.form.get('Oras', '').strip()
        judet = request.form.get('Judet', '').strip()
        password = request.form.get('Password', '')
        password_confirm = request.form.get('PasswordConfirm', '')

        if not (nume and prenume and strada and numar and oras and judet):
            flash("All name and address fields are required.")
            return redirect(request.url)

        if password or password_confirm:
            if password != password_confirm:
                flash("Passwords do not match.")
                return redirect(request.url)

        try:
            cursor.execute(
                """
                UPDATE dbo.Client
                SET ClientNume = ?, ClientPrenume = ?, ClientStrada = ?, ClientNumar = ?, ClientOras = ?, ClientJudet = ?
                WHERE UserId = ?
                """,
                (nume, prenume, strada, numar, oras, judet, session.get('id'))
            )

            if password:
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                cursor.execute(
                    """
                    UPDATE dbo.Utilizatori
                    SET Password = ?
                    WHERE UserId = ?
                    """,
                    (password_hash, session.get('id'))
                )

            conn.commit()
            flash("Profile updated successfully.")
            return redirect(url_for('customer_details'))
        except Exception as e:
            conn.rollback()
            flash(f"An error occurred: {str(e)}")
            return redirect(request.url)

    customer = {
        "nume": row.ClientNume or "",
        "prenume": row.ClientPrenume or "",
        "strada": row.ClientStrada or "",
        "numar": row.ClientNumar or "",
        "oras": row.ClientOras or "",
        "judet": row.ClientJudet or "",
    }

    return render_template('customer_edit_profile.html', customer=customer)


@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('login'))

@app.route('/create-product', methods=['GET', 'POST'])
def create_produs():
    # 1. Session Check: Verify if logged in
    if not session.get('loggedin'):
        flash("Please log in to access this page.")
        return redirect(url_for('login'))

    # 2. Session Check: Verify if role is 'employee'
    if session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    # Fetch all categories
    cursor.execute("SELECT CategorieId, CategorieNume FROM dbo.Categorie")
    categories = [
        {"id": row.CategorieId, "name": row.CategorieNume}
        for row in cursor.fetchall()
    ]

    # Fetch all subcategories
    cursor.execute("SELECT SubcategorieId, SubcategorieNume, CategorieId FROM dbo.Subcategorie")
    subcategories = [
        {"id": row.SubcategorieId, "name": row.SubcategorieNume, "categorie_id": str(row.CategorieId)}
        for row in cursor.fetchall()
    ]

    if request.method == 'POST':
        try:
            sub_id = request.form.get('SubcategorieId') or None
            stoc = request.form.get('Stoc')
            pret = request.form.get('Pret')
            cost = request.form.get('Cost')
            descriere = request.form.get('Descriere')

            # Handle the Image file (convert to binary for SQL 'image' type)
            file = request.files.get('Imagine')
            image_binary = None
            if file and file.filename != '':
                image_binary = file.read()
                if len(image_binary) > MAX_IMAGE_BYTES:
                    flash("Image file is too large. Max size is 5 MB.")
                    return redirect(request.url)

            # Database Insertion
            query = """
                INSERT INTO dbo.Produs (SubcategorieId, Imagine, Stoc, Pret, Descriere, Cost)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            cursor.execute(query, (sub_id, Binary(image_binary) if image_binary else None, stoc, pret, descriere, cost))
            conn.commit()
            flash("Product created successfully!")
            return redirect(url_for('view_products'))

        except Exception as e:
            conn.rollback()
            flash(f"An error occurred: {str(e)}")
            return redirect(request.url)

    # If GET, show the form with categories and subcategories
    return render_template('create_product.html', categories=categories, subcategories=subcategories)

@app.route('/create-subcategory', methods=['GET', 'POST'])
def create_subcategory():
    # 1. Session Check: Verify if logged in
    if not session.get('loggedin'):
        flash("Please log in to access this page.")
        return redirect(url_for('login'))

    # 2. Session Check: Verify if role is 'employee'
    if session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    # Fetch all categories for dropdown
    cursor.execute("SELECT CategorieId, CategorieNume FROM dbo.Categorie")
    categories = [
        {"id": row.CategorieId, "name": row.CategorieNume}
        for row in cursor.fetchall()
    ]

    if request.method == 'POST':
        try:
            nume_subcategorie = request.form.get('SubcategorieNume')
            categorie_id = request.form.get('CategorieId')
            if not nume_subcategorie or not categorie_id:
                flash("All fields are required.")
                return redirect(request.url)
            query = """
                INSERT INTO dbo.Subcategorie (SubcategorieNume, CategorieId)
                VALUES (?, ?)
            """
            cursor.execute(query, (nume_subcategorie, categorie_id))
            conn.commit()
            flash("Subcategory created successfully!")
            return redirect(url_for('create_subcategory'))
        except Exception as e:
            conn.rollback()
            flash(f"An error occurred: {str(e)}")
            return redirect(request.url)

    return render_template('create_subcategory.html', categories=categories)

@app.route('/create-category', methods=['GET', 'POST'])
def create_category():
    # 1. Session Check: Verify if logged in
    if not session.get('loggedin'):
        flash("Please log in to access this page.")
        return redirect(url_for('login'))

    # 2. Session Check: Verify if role is 'employee'
    if session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            nume_categorie = request.form.get('CategorieNume')
            if not nume_categorie:
                flash("Category name is required.")
                return redirect(request.url)
            cursor = conn.cursor()
            query = """
                INSERT INTO dbo.Categorie (CategorieNume)
                VALUES (?)
            """
            cursor.execute(query, (nume_categorie,))
            conn.commit()
            flash("Category created successfully!")
            return redirect(url_for('create_category'))
        except Exception as e:
            conn.rollback()
            flash(f"An error occurred: {str(e)}")
            return redirect(request.url)

    return render_template('create_category.html')

@app.route('/create-customer', methods=['GET', 'POST'])
def create_customer():

    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    if request.method == 'POST':
        nume = request.form.get('Nume')
        prenume = request.form.get('Prenume')
        email = request.form.get('Email')
        telefon = request.form.get('Telefon')
        strada = request.form.get('Strada')
        numar = request.form.get('Numar')
        oras = request.form.get('Oras')
        judet = request.form.get('Judet')
        password = request.form.get('Password')
        password_confirm = request.form.get('PasswordConfirm')
        
        if not (nume and prenume and email and telefon and strada and numar and oras and judet and password and password_confirm):
            flash("All fields are required.")
            return redirect(request.url)
        if password != password_confirm:
            flash("Passwords do not match.")
            return redirect(request.url)
    
        # Validate phone number: 10 digits, all numbers
        if not re.fullmatch(r'\d{10}', telefon):
            flash("Phone number must be exactly 10 digits.")
            return redirect(request.url)
        # Validate email: standard format x@y.z
        if not re.fullmatch(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            flash("Invalid email address format.")
            return redirect(request.url)
    
        cursor = conn.cursor()
        # Check if customer already exists (by phone)
        cursor.execute("SELECT COUNT(*) FROM dbo.Client WHERE ClientTelefon = ?", (telefon,))
        exists = cursor.fetchone()[0]
        if exists:
            flash("A customer with this phone already exists.")
            return redirect(request.url)
        
        # Check if user already exists (by username/address)
        cursor.execute("SELECT COUNT(*) FROM dbo.Utilizatori WHERE Username = ?", (email))
        user_exists = cursor.fetchone()[0]
        if user_exists:
            flash("A user with this address already exists.")
            return redirect(request.url)
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            # Create user in Utilizatori
            cursor.execute("""
                INSERT INTO dbo.Utilizatori (Username, Password, UserCategory)
                OUTPUT INSERTED.UserId
                VALUES (?, ?, ?)
            """, (email, password_hash, 'customer'))
            user_id = cursor.fetchone()[0]
            print(user_id)
            # Insert customer with UserId
            query = """
                INSERT INTO dbo.Client (UserId, ClientNume, ClientPrenume, ClientTelefon, ClientStrada, ClientNumar, ClientOras, ClientJudet)
                OUTPUT INSERTED.ClientId
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.execute(query, (user_id, nume, prenume, telefon, strada, numar, oras, judet))
            client_id = cursor.fetchone()[0]

            # Check if Card de fidelitate is requested
            if request.form.get('CardFidelitate'):
                from datetime import datetime, timedelta
                now = datetime.now()
                cursor.execute("""
                    INSERT INTO dbo.CardFidelitate (ClientId, DataInregistrarii)
                    VALUES (?, ?)
                """, (client_id, now))

            conn.commit()
            flash("Customer added successfully!")
            return redirect(url_for('create_customer'))
        except Exception as e:
            conn.rollback()
            flash(f"An error occurred: {str(e)}")
            return redirect(request.url)

    return render_template('create_customer.html')



@app.route('/create-order', methods=['GET', 'POST'])
def create_order():
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute("SELECT ProdusId, Descriere, Pret, Stoc FROM dbo.Produs")
    products = [
        {
            "id": row.ProdusId,
            "name": row.Descriere,
            "price": float(row.Pret),
            "stock": int(row.Stoc) if row.Stoc is not None else 0,
        }
        for row in cursor.fetchall()
        if row.Descriere
    ]

    if request.method == 'POST':
        email = request.form.get('CustomerEmail', '').strip()
        product_names = [name.strip() for name in request.form.getlist('ProductName[]') if name.strip()]
        product_qtys = [qty.strip() for qty in request.form.getlist('ProductQty[]') if qty.strip()]

        if not email:
            flash("Customer email is required.")
            return redirect(request.url)

        if not product_names or not product_qtys or len(product_names) != len(product_qtys):
            flash("Please add at least one product with a quantity.")
            return redirect(request.url)

        try:
            order_items = []
            for name, qty_raw in zip(product_names, product_qtys):
                qty = int(qty_raw)
                if qty <= 0:
                    flash("Product quantities must be positive numbers.")
                    return redirect(request.url)
                order_items.append((name, qty))
        except ValueError:
            flash("Product quantities must be numbers.")
            return redirect(request.url)

        try:
            # Resolve client by user email (Username)
            cursor.execute(
                """
                SELECT c.ClientId
                FROM dbo.Client c
                JOIN dbo.Utilizatori u ON u.UserId = c.UserId
                WHERE u.Username = ?
                """,
                (email,)
            )
            client_row = cursor.fetchone()
            if not client_row:
                flash("No customer found for this email address.")
                return redirect(request.url)
            client_id = client_row[0]

            # Resolve employee id from logged in user
            cursor.execute(
                "SELECT AngajatId FROM dbo.Angajat WHERE UserId = ?",
                (session.get('id'),)
            )
            angajat_row = cursor.fetchone()
            if not angajat_row:
                flash("Employee record not found.")
                return redirect(request.url)
            angajat_id = angajat_row[0]

            # Aggregate quantities by product name
            requested = {}
            for name, qty in order_items:
                key = name.strip()
                requested[key] = requested.get(key, 0) + qty

            # Fetch products by name and validate stock
            placeholders = ",".join("?" for _ in requested)
            cursor.execute(
                f"""
                SELECT ProdusId, Descriere, Stoc
                FROM dbo.Produs
                WHERE Descriere IN ({placeholders})
                """,
                tuple(requested.keys())
            )
            product_rows = cursor.fetchall()
            products_by_name = {row.Descriere: (row.ProdusId, int(row.Stoc) if row.Stoc is not None else 0) for row in product_rows}

            missing = [name for name in requested.keys() if name not in products_by_name]
            if missing:
                flash("Some products no longer exist. Please reselect the items.")
                return redirect(request.url)

            for name, qty in requested.items():
                _, stock = products_by_name[name]
                if qty > stock:
                    flash(f"Insufficient stock for '{name}'. Available: {stock}.")
                    return redirect(request.url)

            # Create order and order items
            from datetime import datetime, timedelta
            now = datetime.now()

            cursor.execute(
                """
                SELECT DataInregistrarii
                FROM dbo.CardFidelitate
                WHERE ClientId = ?
                """,
                (client_id,)
            )
            card_row = cursor.fetchone()
            discount_pct = None
            if card_row and card_row[0]:
                days_active = (now - card_row[0]).days
                years_active = days_active / 365.25
                if years_active > 5:
                    discount_pct = 7
                elif years_active > 2:
                    discount_pct = 3

            cursor.execute(
                """
                INSERT INTO dbo.Comanda (ComandaData, ClientId, AngajatId, ReducereLoialitate)
                OUTPUT INSERTED.ComandaId
                VALUES (?, ?, ?, ?)
                """,
                (now, client_id, angajat_id, discount_pct)
            )
            comanda_id = cursor.fetchone()[0]

            for name, qty in requested.items():
                produs_id, stock = products_by_name[name]
                cursor.execute(
                    """
                    INSERT INTO dbo.ProdusComanda (ProdusId, ComandaId, ProdusComandaCantitate)
                    VALUES (?, ?, ?)
                    """,
                    (produs_id, comanda_id, qty)
                )
                cursor.execute(
                    "UPDATE dbo.Produs SET Stoc = ? WHERE ProdusId = ?",
                    (stock - qty, produs_id)
                )

            conn.commit()
            if discount_pct:
                flash(f"Loyalty discount applied: {discount_pct}%")
            flash("Order created successfully!")
            return redirect(url_for('create_order'))
        except Exception as e:
            conn.rollback()
            flash(f"An error occurred: {str(e)}")
            return redirect(request.url)

    return render_template('create_order.html', products=products)


@app.route('/create-delivery', methods=['GET', 'POST'])
def create_delivery():
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute("SELECT ProdusId, Descriere, Pret, Cost FROM dbo.Produs")
    products = [
        {
            "id": row.ProdusId,
            "name": row.Descriere,
            "price": float(row.Pret),
            "cost": float(row.Cost),
        }
        for row in cursor.fetchall()
        if row.Descriere
    ]

    cursor.execute("SELECT DistribuitorId, DistribuitorNume FROM dbo.Distribuitor")
    distributors = [
        {"id": row.DistribuitorId, "name": row.DistribuitorNume}
        for row in cursor.fetchall()
        if row.DistribuitorNume
    ]

    if request.method == 'POST':
        distributor_name = request.form.get('DistributorName', '').strip()
        product_names = [name.strip() for name in request.form.getlist('ProductName[]') if name.strip()]
        product_qtys = [qty.strip() for qty in request.form.getlist('ProductQty[]') if qty.strip()]

        if not distributor_name:
            flash("Distributor name is required.")
            return redirect(request.url)

        if not product_names or not product_qtys or len(product_names) != len(product_qtys):
            flash("Please add at least one product with a quantity.")
            return redirect(request.url)

        try:
            delivery_items = []
            for name, qty_raw in zip(product_names, product_qtys):
                qty = int(qty_raw)
                if qty <= 0:
                    flash("Product quantities must be positive numbers.")
                    return redirect(request.url)
                delivery_items.append((name, qty))
        except ValueError:
            flash("Product quantities must be numbers.")
            return redirect(request.url)

        try:
            cursor.execute(
                "SELECT DistribuitorId FROM dbo.Distribuitor WHERE DistribuitorNume = ?",
                (distributor_name,)
            )
            distributor_row = cursor.fetchone()
            if not distributor_row:
                flash("No distributor found with this name.")
                return redirect(request.url)
            distributor_id = distributor_row[0]

            cursor.execute(
                "SELECT AngajatId FROM dbo.Angajat WHERE UserId = ?",
                (session.get('id'),)
            )
            angajat_row = cursor.fetchone()
            if not angajat_row:
                flash("Employee record not found.")
                return redirect(request.url)
            angajat_id = angajat_row[0]

            requested = {}
            for name, qty in delivery_items:
                key = name.strip()
                requested[key] = requested.get(key, 0) + qty

            placeholders = ",".join("?" for _ in requested)
            cursor.execute(
                f"""
                SELECT ProdusId, Descriere
                FROM dbo.Produs
                WHERE Descriere IN ({placeholders})
                """,
                tuple(requested.keys())
            )
            product_rows = cursor.fetchall()
            products_by_name = {row.Descriere: row.ProdusId for row in product_rows}

            missing = [name for name in requested.keys() if name not in products_by_name]
            if missing:
                flash("Some products no longer exist. Please reselect the items.")
                return redirect(request.url)

            from datetime import datetime, timedelta
            now = datetime.now()

            cursor.execute(
                """
                INSERT INTO dbo.Livrare (DistribuitorId, DataLivrare, AngajatId)
                OUTPUT INSERTED.LivrareId
                VALUES (?, ?, ?)
                """,
                (distributor_id, now, angajat_id)
            )
            livrare_id = cursor.fetchone()[0]

            for name, qty in requested.items():
                produs_id = products_by_name[name]
                cursor.execute(
                    """
                    INSERT INTO dbo.ProdusLivrare (ProdusId, LivrareId, ProdusLivrareCantitate)
                    VALUES (?, ?, ?)
                    """,
                    (produs_id, livrare_id, qty)
                )
                cursor.execute(
                    "UPDATE dbo.Produs SET Stoc = Stoc + ? WHERE ProdusId = ?",
                    (qty, produs_id)
                )

            conn.commit()
            flash("Delivery created successfully!")
            return redirect(url_for('create_delivery'))
        except Exception as e:
            conn.rollback()
            flash(f"An error occurred: {str(e)}")
            return redirect(request.url)

    return render_template('create_delivery.html', products=products, distributors=distributors)


@app.route('/delivery-history')
def delivery_history():
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            l.LivrareId,
            d.DistribuitorNume,
            l.DataLivrare,
            SUM(pl.ProdusLivrareCantitate * p.Pret) AS TotalPret,
            SUM(pl.ProdusLivrareCantitate * p.Cost) AS TotalCost
        FROM dbo.Livrare l
        JOIN dbo.Distribuitor d ON d.DistribuitorId = l.DistribuitorId
        LEFT JOIN dbo.ProdusLivrare pl ON pl.LivrareId = l.LivrareId
        LEFT JOIN dbo.Produs p ON p.ProdusId = pl.ProdusId
        GROUP BY l.LivrareId, d.DistribuitorNume, l.DataLivrare
        ORDER BY l.LivrareId DESC
        """
    )
    rows = cursor.fetchall()
    deliveries = [
        {
            "id": row.LivrareId,
            "distributor": row.DistribuitorNume,
            "date": row.DataLivrare,
            "total_price": float(row.TotalPret) if row.TotalPret is not None else 0.0,
            "total_cost": float(row.TotalCost) if row.TotalCost is not None else 0.0,
        }
        for row in rows
    ]

    return render_template('delivery_history.html', deliveries=deliveries)


@app.route('/delivery-details/<int:delivery_id>')
def delivery_details(delivery_id):
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT l.LivrareId, d.DistribuitorNume, l.DataLivrare
        FROM dbo.Livrare l
        JOIN dbo.Distribuitor d ON d.DistribuitorId = l.DistribuitorId
        WHERE l.LivrareId = ?
        """,
        (delivery_id,)
    )
    delivery_row = cursor.fetchone()
    if not delivery_row:
        flash("Delivery not found.")
        return redirect(url_for('delivery_history'))

    cursor.execute(
        """
        SELECT
            p.Descriere,
            pl.ProdusLivrareCantitate,
            p.Pret,
            p.Cost
        FROM dbo.ProdusLivrare pl
        JOIN dbo.Produs p ON p.ProdusId = pl.ProdusId
        WHERE pl.LivrareId = ?
        ORDER BY p.Descriere
        """,
        (delivery_id,)
    )
    item_rows = cursor.fetchall()
    items = [
        {
            "product": row.Descriere,
            "qty": row.ProdusLivrareCantitate,
            "price": float(row.Pret),
            "cost": float(row.Cost),
            "line_price": float(row.Pret) * row.ProdusLivrareCantitate,
            "line_cost": float(row.Cost) * row.ProdusLivrareCantitate,
        }
        for row in item_rows
    ]

    delivery = {
        "id": delivery_row.LivrareId,
        "distributor": delivery_row.DistribuitorNume,
        "date": delivery_row.DataLivrare,
    }

    return render_template('delivery_details.html', delivery=delivery, items=items)


@app.route('/delete-delivery/<int:delivery_id>', methods=['POST'])
def delete_delivery(delivery_id):
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM dbo.Livrare WHERE LivrareId = ?", (delivery_id,))
    if not cursor.fetchone():
        flash("Delivery not found.")
        return redirect(url_for('delivery_history'))

    try:
        cursor.execute("DELETE FROM dbo.ProdusLivrare WHERE LivrareId = ?", (delivery_id,))
        cursor.execute("DELETE FROM dbo.Livrare WHERE LivrareId = ?", (delivery_id,))
        conn.commit()
        flash("Delivery deleted successfully.")
    except Exception as e:
        conn.rollback()
        flash(f"An error occurred: {str(e)}")

    return redirect(url_for('delivery_history'))


@app.route('/order-history')
def order_history():
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.ComandaId,
            cl.ClientNume,
            cl.ClientPrenume,
            u.Username,
            SUM(pc.ProdusComandaCantitate * p.Pret) AS TotalPret
        FROM dbo.Comanda c
        JOIN dbo.Client cl ON cl.ClientId = c.ClientId
        JOIN dbo.Utilizatori u ON u.UserId = cl.UserId
        LEFT JOIN dbo.ProdusComanda pc ON pc.ComandaId = c.ComandaId
        LEFT JOIN dbo.Produs p ON p.ProdusId = pc.ProdusId
        GROUP BY c.ComandaId, cl.ClientNume, cl.ClientPrenume, u.Username
        ORDER BY c.ComandaId DESC
        """
    )
    rows = cursor.fetchall()
    orders = [
        {
            "id": row.ComandaId,
            "customer_name": f"{row.ClientNume} {row.ClientPrenume}",
            "email": row.Username,
            "total_price": float(row.TotalPret) if row.TotalPret is not None else 0.0,
        }
        for row in rows
    ]

    return render_template('order_history.html', orders=orders)


@app.route('/order-details/<int:order_id>')
def order_details(order_id):
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.ComandaId,
            c.ComandaData,
            c.ReducereLoialitate,
            cl.ClientNume,
            cl.ClientPrenume,
            u.Username
        FROM dbo.Comanda c
        JOIN dbo.Client cl ON cl.ClientId = c.ClientId
        JOIN dbo.Utilizatori u ON u.UserId = cl.UserId
        WHERE c.ComandaId = ?
        """,
        (order_id,)
    )
    order_row = cursor.fetchone()
    if not order_row:
        flash("Order not found.")
        return redirect(url_for('order_history'))

    cursor.execute(
        """
        SELECT
            p.Descriere,
            pc.ProdusComandaCantitate,
            p.Pret
        FROM dbo.ProdusComanda pc
        JOIN dbo.Produs p ON p.ProdusId = pc.ProdusId
        WHERE pc.ComandaId = ?
        ORDER BY p.Descriere
        """,
        (order_id,)
    )
    item_rows = cursor.fetchall()
    items = [
        {
            "product": row.Descriere,
            "qty": row.ProdusComandaCantitate,
            "price": float(row.Pret),
            "line_total": float(row.Pret) * row.ProdusComandaCantitate,
        }
        for row in item_rows
    ]

    order = {
        "id": order_row.ComandaId,
        "date": order_row.ComandaData,
        "customer_name": f"{order_row.ClientNume} {order_row.ClientPrenume}",
        "email": order_row.Username,
        "discount_pct": int(order_row.ReducereLoialitate) if order_row.ReducereLoialitate is not None else 0,
    }

    return render_template('order_details.html', order=order, items=items)


@app.route('/delete-order/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM dbo.Comanda WHERE ComandaId = ?", (order_id,))
    if not cursor.fetchone():
        flash("Order not found.")
        return redirect(url_for('order_history'))

    try:
        cursor.execute("DELETE FROM dbo.ProdusComanda WHERE ComandaId = ?", (order_id,))
        cursor.execute("DELETE FROM dbo.Comanda WHERE ComandaId = ?", (order_id,))
        conn.commit()
        flash("Order deleted successfully.")
    except Exception as e:
        conn.rollback()
        flash(f"An error occurred: {str(e)}")

    return redirect(url_for('order_history'))


@app.route('/loyalty-discount')
def loyalty_discount():
    if not session.get('loggedin') or session.get('role') != 'employee':
        return jsonify({"discount_pct": 0})

    
    email = request.args.get('email', '').strip()
    if not email:
        return jsonify({"discount_pct": 0})
    
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT cf.DataInregistrarii
        FROM dbo.CardFidelitate cf
        JOIN dbo.Client c ON c.ClientId = cf.ClientId
        JOIN dbo.Utilizatori u ON u.UserId = c.UserId
        WHERE u.Username = ?
        """,
        (email,)
    )
    row = cursor.fetchone()
    
    if not row or not row[0]:
        return jsonify({"discount_pct": 0})

    from datetime import datetime, timedelta

    now = datetime.now()
    years_active = (now - row[0]).days / 365.25
    if years_active > 5:
        discount_pct = 7
    elif years_active > 2:
        discount_pct = 3
    else:
        discount_pct = 0

    return jsonify({"discount_pct": discount_pct})


@app.route('/edit-product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    # Session Checks
    if not session.get('loggedin'):
        flash("Please log in to access this page.")
        return redirect(url_for('login'))

    if session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ProdusId, Imagine, Stoc, Descriere
        FROM dbo.Produs
        WHERE ProdusId = ?
        """,
        (product_id,)
    )
    row = cursor.fetchone()
    if not row:
        flash("Product not found.")
        return redirect(url_for('view_products'))

    if request.method == 'POST':
        descriere = request.form.get('Descriere', '').strip()
        stoc_raw = request.form.get('Stoc', '').strip()

        if not descriere:
            flash("Description is required.")
            return redirect(request.url)

        try:
            stoc = int(stoc_raw)
        except (TypeError, ValueError):
            flash("Stock must be a number.")
            return redirect(request.url)

        if stoc < 0:
            flash("Stock must be zero or greater.")
            return redirect(request.url)

        file = request.files.get('Imagine')
        update_image = False
        image_binary = None

        if file and file.filename:
            update_image = True
            image_binary = file.read()
            if len(image_binary) > MAX_IMAGE_BYTES:
                flash("Image file is too large. Max size is 5 MB.")
                return redirect(request.url)
        elif request.form.get('RemoveImage') == '1':
            update_image = True
            image_binary = None

        try:
            if update_image:
                cursor.execute(
                    """
                    UPDATE dbo.Produs
                    SET Imagine = ?, Stoc = ?, Descriere = ?
                    WHERE ProdusId = ?
                    """,
                    (Binary(image_binary) if image_binary else None, stoc, descriere, product_id)
                )
            else:
                cursor.execute(
                    """
                    UPDATE dbo.Produs
                    SET Stoc = ?, Descriere = ?
                    WHERE ProdusId = ?
                    """,
                    (stoc, descriere, product_id)
                )
            conn.commit()
            flash("Product updated successfully.")
            return redirect(url_for('view_products'))
        except Exception as e:
            conn.rollback()
            flash(f"An error occurred: {str(e)}")
            return redirect(request.url)

    image_base64 = None
    if row.Imagine:
        image_base64 = base64.b64encode(row.Imagine).decode('utf-8')

    product = {
        "id": row.ProdusId,
        "image": image_base64,
        "stoc": int(row.Stoc) if row.Stoc is not None else 0,
        "descriere": row.Descriere or ""
    }

    return render_template('edit_product.html', product=product)


@app.route('/view-products')
def view_products():
    # Session Checks
    if not session.get('loggedin'):
        return redirect(url_for('login'))
    
    if session.get('role') != 'employee':
        print(f"\'{session.get('role')}\'")
        flash("Access denied.")
        return redirect(url_for('login'))

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            p.ProdusId,
            p.SubcategorieId,
            p.Imagine,
            p.Stoc,
            p.Pret,
            p.Descriere,
            s.SubcategorieNume,
            c.CategorieNume
        FROM dbo.Produs p
        LEFT JOIN dbo.Subcategorie s ON s.SubcategorieId = p.SubcategorieId
        LEFT JOIN dbo.Categorie c ON c.CategorieId = s.CategorieId
        """
    )
    rows = cursor.fetchall()

    products = []
    for row in rows:
        # Convert binary image to Base64 string for display
        image_base64 = None
        if row.Imagine:
            image_base64 = base64.b64encode(row.Imagine).decode('utf-8')

        products.append({
            "id": row.ProdusId,
            "sub_id": row.SubcategorieId,
            "subcategory": row.SubcategorieNume.strip() if row.SubcategorieNume else None,
            "category": row.CategorieNume.strip() if row.CategorieNume else None,
            "image": image_base64,
            "stoc": row.Stoc,
            "pret": row.Pret,
            "descriere": row.Descriere
        })

    return render_template('view_products.html', products=products)
