from datetime import datetime

from flask import render_template, request, redirect, url_for, session, flash


def register(app):
    conn = app.config['DB_CONN']

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
