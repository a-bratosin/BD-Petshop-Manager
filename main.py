# Route for creating a new customer
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from os import getenv
from dotenv import load_dotenv
from pyodbc import connect, Binary
import hashlib
import base64
import re

# FORMAT: UID is the user, PWD is the password
load_dotenv()
conn = connect(getenv("SQL_CONNECTION_STRING"))

print("Connected!")


app = Flask(__name__)
app.config['SECRET_KEY'] = getenv("SESSION_KEY")

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"

@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
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
            print(session)
            # Redirect employee to dashboard
            if session['role'] == 'employee':
                return redirect(url_for('employee_dashboard'))
            else:
                return render_template('index.html', msg='Logged in successfully!')
        else:
            msg = 'Incorrect username/password!'
    return render_template('login.html', msg=msg)
# Employee dashboard route
@app.route('/employee-dashboard')
def employee_dashboard():
    if not session.get('loggedin') or session.get('role') != 'employee':
        flash("Unauthorized: This action requires employee privileges.")
        return redirect(url_for('login'))
    return render_template('employee_dashboard.html')


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
            descriere = request.form.get('Descriere')

            # Handle the Image file (convert to binary for SQL 'image' type)
            file = request.files.get('Imagine')
            image_binary = None
            if file and file.filename != '':
                image_binary = file.read()

            # Database Insertion
            query = """
                INSERT INTO dbo.Produs (SubcategorieId, Imagine, Stoc, Pret, Descriere)
                VALUES (?, ?, ?, ?, ?)
            """
            cursor.execute(query, (sub_id, Binary(image_binary) if image_binary else None, stoc, pret, descriere))
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
                from datetime import datetime
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
            from datetime import datetime
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

    from datetime import datetime

    now = datetime.now()
    years_active = (now - row[0]).days / 365.25
    if years_active > 5:
        discount_pct = 7
    elif years_active > 2:
        discount_pct = 3
    else:
        discount_pct = 0

    return jsonify({"discount_pct": discount_pct})


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
    cursor.execute("SELECT ProdusId, SubcategorieId, Imagine, Stoc, Pret, Descriere FROM dbo.Produs")
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
            "image": image_base64,
            "stoc": row.Stoc,
            "pret": row.Pret,
            "descriere": row.Descriere
        })

    return render_template('view_products.html', products=products)
