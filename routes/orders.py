from datetime import datetime

from flask import render_template, request, redirect, url_for, session, flash, jsonify


def register(app):
    conn = app.config['DB_CONN']

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
                for name, qty in order_items:
                    key = name.strip()
                    requested[key] = requested.get(key, 0) + qty

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

        now = datetime.now()
        years_active = (now - row[0]).days / 365.25
        if years_active > 5:
            discount_pct = 7
        elif years_active > 2:
            discount_pct = 3
        else:
            discount_pct = 0

        return jsonify({"discount_pct": discount_pct})
