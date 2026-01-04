# Route for creating a new customer
from flask import Flask, render_template, request, redirect, url_for, session, flash
from os import getenv
from dotenv import load_dotenv
from pyodbc import connect, Binary
import hashlib
import base64

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