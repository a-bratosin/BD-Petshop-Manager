import base64
import hashlib
from datetime import datetime

from flask import render_template, request, redirect, url_for, session, flash

from utils.auth import allow_customer_or_guest
from utils.catalog import fetch_categories, fetch_product_names, build_products

# în acest modul definesc rutele pentru funcționalitățile disponibile clienților și vizitatorilor

def register(app):
    conn = app.config['DB_CONN']

    # ruta principală redirecționează către magazin
    @app.route("/")
    def hello_world():
        return redirect(url_for('customer_shop'))

    # ruta pentru dashboard-ul clientului
    @app.route('/customer-dashboard')
    def customer_dashboard():
        if not session.get('loggedin') or session.get('role') != 'customer':
            flash("Unauthorized: This action requires customer privileges.")
            return redirect(url_for('login'))
        cart_count = sum(int(qty) for qty in session.get('cart', {}).values())
        cursor = conn.cursor()
        categories = fetch_categories(cursor)

        return render_template(
            'customer_dashboard.html',
            cart_count=cart_count,
            categories=categories,
            is_guest=False
        )

    @app.route('/shop')
    def customer_shop():
        # verific dacă utilizatorul are drepturi de client sau vizitator
        if not allow_customer_or_guest():
            flash("Unauthorized: This action requires customer privileges.")
            return redirect(url_for('login'))

        if 'cart' not in session:
            session['cart'] = {}

        # realizez aici o subcerere pentru a obține produsele cele mai bine vândute
        # subcerere necorelată, deoarece nu am nevoie de alte informații din cererea principală
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

        # selectez o categorie aleatorie și preiau până la 12 produse din acea categorie
        # order by NEWID() este o metodă specifică SQL Server pentru a obține rezultate în ordine aleatorie
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

        # analog pentru subcategorie
        cursor.execute(
            """
            SELECT TOP 1
                s.SubcategorieId,
                s.SubcategorieNume,
                c.CategorieNume
            FROM dbo.Subcategorie s
            JOIN dbo.Categorie c ON c.CategorieId = s.CategorieId
            JOIN dbo.Produs p ON p.SubcategorieId = s.SubcategorieId
            GROUP BY s.SubcategorieId, s.SubcategorieNume, c.CategorieNume
            ORDER BY NEWID()
            """
        )
        subcategory_row = cursor.fetchone()
        random_subcategory = None
        subcategory_products = []
        if subcategory_row:
            random_subcategory = {
                "id": subcategory_row.SubcategorieId,
                "name": subcategory_row.SubcategorieNume,
                "category_name": subcategory_row.CategorieNume
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

    # aici implementez un search simplu pentru magazin, folosind LIKE în SQL
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

    # rută pentru vizualizarea produselor dintr-o anumită categorie
    # preiau din id categoria, apoi numele categoriei și produsele aferente
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

        # 
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
            heading=category_row.CategorieNume,
            is_guest=is_guest
        )

    # analog pentru subcategorie
    @app.route('/shop/subcategory/<int:subcategory_id>')
    def customer_subcategory_view(subcategory_id):
        if not allow_customer_or_guest():
            flash("Unauthorized: This action requires customer privileges.")
            return redirect(url_for('login'))

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.SubcategorieNume, s.SubcategorieDescriere, c.CategorieNume
            FROM dbo.Subcategorie s
            JOIN dbo.Categorie c ON c.CategorieId = s.CategorieId
            WHERE s.SubcategorieId = ?
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
            heading=f"{sub_row.CategorieNume}/{sub_row.SubcategorieNume}",
            subcategory_description=sub_row.SubcategorieDescriere.strip() if sub_row.SubcategorieDescriere else None,
            is_guest=is_guest
        )

    # rută pentru vizualizarea detaliilor pentru un produs
    @app.route('/product/<int:product_id>')
    def customer_product_details(product_id):
        if not allow_customer_or_guest():
            flash("Unauthorized: This action requires customer privileges.")
            return redirect(url_for('login'))
        
        # aici am nevoie doar de un select simplu pentru a prelua datele produsului
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
    
    # rută pentru vizualizarea coșului de cumpărături al utilizatorului curent
    @app.route('/cart')
    def customer_cart():
        if not allow_customer_or_guest():
            flash("Unauthorized: This action requires customer privileges.")
            return redirect(url_for('login'))

        # elementele coșului sunt stocate în sesiune sub forma unui dicționar {product_id: quantity}
        cart = session.get('cart', {})
        cart_ids = [int(pid) for pid in cart.keys()] if cart else []
        items = []
        total = 0.0

        # id-urile sunt preluate din coș, apoi realizez un select pentru a obține detaliile produselor
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

        # verific dacă produsul există și dacă are stoc suficient
        row = cursor.fetchone()
        if not row:
            flash("Product not found.")
            return redirect(request.referrer or url_for('customer_shop'))

        available_stock = int(row.Stoc) if row.Stoc is not None else 0
        if available_stock <= 0:
            flash("This product is currently out of stock.")
            return redirect(request.referrer or url_for('customer_shop'))

        # dacă produsul există, adaug cantitatea în coș
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

    # rută pentru golirea coșului de cumpărături
    @app.route('/cart/clear', methods=['POST'])
    def customer_cart_clear():
        if not allow_customer_or_guest():
            flash("Unauthorized: This action requires customer privileges.")
            return redirect(url_for('login'))

        session['cart'] = {}
        session.modified = True
        flash("Cart cleared.")
        return redirect(url_for('customer_cart'))

    # rută pentru eliminarea unui produs din coșul de cumpărături
    # id-ul produsului este trimis prin formular
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

    # rută pentru incrementarea sau decrementarea cantității unui produs din coș
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
        
        # pentru incrementare, verific mai întâi stocul disponibil
        cursor = conn.cursor()
        cursor.execute("SELECT Stoc FROM dbo.Produs WHERE ProdusId = ?", (product_id,))
        row = cursor.fetchone()
        if not row:
            flash("Product not found.")
            return redirect(url_for('customer_cart'))

        # dacă nu există suficient stoc, nu permit incrementarea
        available_stock = int(row.Stoc) if row.Stoc is not None else 0
        if current_qty + 1 > available_stock:
            flash("Not enough stock available for that quantity.")
            return redirect(url_for('customer_cart'))

        cart[str(product_id)] = current_qty + 1
        session['cart'] = cart
        session.modified = True

        return redirect(url_for('customer_cart'))

    # rută pentru confirmarea comenzii din coșul de cumpărături
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


        # mai întâi extrag id-ul clientului asociat utilizatorului curent
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

        # verific disponibilitatea stocului pentru toate produsele din coș
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
            # verific dacă clientul are card de fidelitate; dacă da, verific dacă clientul este suficient de vechi încât să primească discount
            # dacă da, este păstrat într-un câmp separat în tabela Comanda, ReducereLoialitate
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

            # inserez comanda în tabela Comanda
            cursor.execute(
                """
                INSERT INTO dbo.Comanda (ComandaData, ClientId, AngajatId, ReducereLoialitate)
                OUTPUT INSERTED.ComandaId
                VALUES (?, ?, ?, ?)
                """,
                (now, client_id, None, discount_pct)
            )
            comanda_id = cursor.fetchone()[0]

            # inserez fiecare produs din comanda în tabela ProdusComanda și actualizez stocul în tabela Produs
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
            # confirm tranzacția
            conn.commit()

            # elimin coșul din sesiune
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

    # rută pentru vizualizarea istoricului comenzilor unui client
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

        categories = fetch_categories(cursor)
        cart_count = sum(int(qty) for qty in session.get('cart', {}).values())

        return render_template(
            'customer_order_history.html',
            orders=orders,
            cart_count=cart_count,
            categories=categories,
            is_guest=False
        )


    # rută pentru vizualizarea detaliilor unei comenzi specifice
    # mai întâi extrag detaliile comenzii, apoi produsele aferente
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

        categories = fetch_categories(cursor)
        cart_count = sum(int(qty) for qty in session.get('cart', {}).values())

        return render_template(
            'customer_order_details.html',
            order=order,
            items=items,
            cart_count=cart_count,
            categories=categories,
            is_guest=False
        )


    # rută pentru vizualizarea detaliilor profilului clientului
    @app.route('/customer-details')
    def customer_details():
        if not session.get('loggedin') or session.get('role') != 'customer':
            flash("Unauthorized: This action requires customer privileges.")
            return redirect(url_for('login'))

        # extrag mai întâi detaliile clientului
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

        # extrag datele pentru cardul de fidelitate, și calculez vechimea cardului și discount-ul aferent
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

        categories = fetch_categories(cursor)
        cart_count = sum(int(qty) for qty in session.get('cart', {}).values())

        return render_template(
            'customer_details.html',
            customer=customer,
            cart_count=cart_count,
            categories=categories,
            is_guest=False
        )
    
    # rută pentru editarea profilului clientului
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
            nume = request.form.get('Nume', '').rstrip()
            prenume = request.form.get('Prenume', '').rstrip()
            strada = request.form.get('Strada', '').rstrip()
            numar = request.form.get('Numar', '').rstrip()
            oras = request.form.get('Oras', '').rstrip()
            judet = request.form.get('Judet', '').rstrip()
            password = request.form.get('Password', '').rstrip()
            password_confirm = request.form.get('PasswordConfirm', '').rstrip()

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

        categories = fetch_categories(cursor)
        cart_count = sum(int(qty) for qty in session.get('cart', {}).values())

        return render_template(
            'customer_edit_profile.html',
            customer=customer,
            cart_count=cart_count,
            categories=categories,
            is_guest=False
        )
