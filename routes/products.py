import base64
import hashlib
import re
from datetime import datetime

from flask import render_template, request, redirect, url_for, session, flash
from pyodbc import Binary


def register(app):
    conn = app.config['DB_CONN']
    max_image_bytes = app.config['MAX_IMAGE_BYTES']

    @app.route('/create-product', methods=['GET', 'POST'])
    def create_produs():
        if not session.get('loggedin'):
            flash("Please log in to access this page.")
            return redirect(url_for('login'))

        if session.get('role') != 'employee':
            flash("Unauthorized: This action requires employee privileges.")
            return redirect(url_for('login'))

        cursor = conn.cursor()
        cursor.execute("SELECT CategorieId, CategorieNume FROM dbo.Categorie")
        categories = [
            {"id": row.CategorieId, "name": row.CategorieNume}
            for row in cursor.fetchall()
        ]

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

                file = request.files.get('Imagine')
                image_binary = None
                if file and file.filename != '':
                    image_binary = file.read()
                    if len(image_binary) > max_image_bytes:
                        flash("Image file is too large. Max size is 5 MB.")
                        return redirect(request.url)

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

        return render_template('create_product.html', categories=categories, subcategories=subcategories)

    @app.route('/create-subcategory', methods=['GET', 'POST'])
    def create_subcategory():
        if not session.get('loggedin'):
            flash("Please log in to access this page.")
            return redirect(url_for('login'))

        if session.get('role') != 'employee':
            flash("Unauthorized: This action requires employee privileges.")
            return redirect(url_for('login'))

        cursor = conn.cursor()
        cursor.execute("SELECT CategorieId, CategorieNume FROM dbo.Categorie")
        categories = [
            {"id": row.CategorieId, "name": row.CategorieNume}
            for row in cursor.fetchall()
        ]

        if request.method == 'POST':
            try:
                nume_subcategorie = request.form.get('SubcategorieNume')
                categorie_id = request.form.get('CategorieId')
                descriere_subcategorie = request.form.get('SubcategorieDescriere', '').strip() or None
                if not nume_subcategorie or not categorie_id:
                    flash("All fields are required.")
                    return redirect(request.url)
                query = """
                    INSERT INTO dbo.Subcategorie (SubcategorieNume, CategorieId, SubcategorieDescriere)
                    VALUES (?, ?, ?)
                """
                cursor.execute(query, (nume_subcategorie, categorie_id, descriere_subcategorie))
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
        if not session.get('loggedin'):
            flash("Please log in to access this page.")
            return redirect(url_for('login'))

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

                query = """
                    INSERT INTO dbo.Client (UserId, ClientNume, ClientPrenume, ClientTelefon, ClientStrada, ClientNumar, ClientOras, ClientJudet)
                    OUTPUT INSERTED.ClientId
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
                cursor.execute(query, (user_id, nume, prenume, telefon, strada, numar, oras, judet))
                client_id = cursor.fetchone()[0]

                if request.form.get('CardFidelitate'):
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

    @app.route('/view-products')
    def view_products():
        if not session.get('loggedin'):
            return redirect(url_for('login'))

        if session.get('role') != 'employee':
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
                p.Cost,
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
                "cost": row.Cost,
                "descriere": row.Descriere
            })

        return render_template('view_products.html', products=products)

    @app.route('/view-customers')
    def view_customers():
        if not session.get('loggedin'):
            return redirect(url_for('login'))

        if session.get('role') != 'employee':
            flash("Access denied.")
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
            ORDER BY c.ClientNume, c.ClientPrenume
            """
        )
        rows = cursor.fetchall()

        customers = []
        for row in rows:
            name = f"{row.ClientNume} {row.ClientPrenume}".strip()
            address_parts = [
                row.ClientStrada or "",
                row.ClientNumar or "",
                row.ClientOras or "",
                row.ClientJudet or ""
            ]
            address = " ".join(part for part in address_parts if part).strip()

            customers.append({
                "id": row.ClientId,
                "name": name,
                "email": row.Username.strip() if row.Username else "",
                "phone": row.ClientTelefon or "",
                "address": address or "N/A"
            })

        return render_template('view_customers.html', customers=customers)

    @app.route('/edit-product/<int:product_id>', methods=['GET', 'POST'])
    def edit_product(product_id):
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
                if len(image_binary) > max_image_bytes:
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
