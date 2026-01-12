from datetime import datetime

from flask import render_template, request, redirect, url_for, session, flash

# modul pentru gestionarea rutelor legate de livrări

def register(app):
    conn = app.config['DB_CONN']


    # rută pentru crearea unei noi livrări de produse de la un distribuitor
    @app.route('/create-delivery', methods=['GET', 'POST'])
    def create_delivery():
        if not session.get('loggedin') or session.get('role') != 'employee':
            flash("Unauthorized: This action requires employee privileges.")
            return redirect(url_for('login'))


        # mai întâi preluăm lista de produse și distribuitori pentru a le putea afișa în formular
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

        # logica pentru procesarea formularului de creare a livrării
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
                # obținem ID-urile necesare pentru inserarea livrării
                cursor.execute(
                    "SELECT DistribuitorId FROM dbo.Distribuitor WHERE DistribuitorNume = ?",
                    (distributor_name,)
                )
                distributor_row = cursor.fetchone()
                if not distributor_row:
                    flash("No distributor found with this name.")
                    return redirect(request.url)
                distributor_id = distributor_row[0]

                # obținem AngajatId pe baza UserId din sesiune
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

                # verificăm dacă toate produsele există
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


                # dacă toate verificările au trecut, inserăm livrarea și actualizăm stocurile
                cursor.execute(
                    """
                    INSERT INTO dbo.Livrare (DistribuitorId, DataLivrare, AngajatId)
                    OUTPUT INSERTED.LivrareId
                    VALUES (?, ?, ?)
                    """,
                    (distributor_id, now, angajat_id)
                )
                livrare_id = cursor.fetchone()[0]

                # inserăm fiecare produs în ProdusLivrare și actualizăm stocul în Produs
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
    
    # rută pentru afișarea istoricului livrărilor
    @app.route('/delivery-history')
    def delivery_history():
        if not session.get('loggedin') or session.get('role') != 'employee':
            flash("Unauthorized: This action requires employee privileges.")
            return redirect(url_for('login'))
        
        # preluăm istoricul livrărilor împreună cu totalurile aferente
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


    # rută pentru vizualizarea listei de distribuitori de către angajați
    @app.route('/view-distributors')
    def view_distributors():
        if not session.get('loggedin') or session.get('role') != 'employee':
            flash("Unauthorized: This action requires employee privileges.")
            return redirect(url_for('login'))

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM dbo.Distribuitor
            ORDER BY DistribuitorNume
            """
        )
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        distributors = []
        for row in rows:
            data = dict(zip(columns, row))
            street = (data.get('DistribuitorStrada') or '').strip()
            number_raw = data.get('DistribuitorNumar')
            number = str(number_raw).strip() if number_raw is not None else ''
            address = " ".join(part for part in [street, number] if part).strip() or "N/A"

            distributors.append({
                "id": data.get('DistribuitorId'),
                "name": (data.get('DistribuitorNume') or "").strip(),
                "phone": str(data.get('DistribuitorTelefon') or "").strip(),
                "email": (data.get('DistribuitorEmail') or "").strip(),
                "city": (data.get('DistribuitorOras') or "").strip(),
                "county": (data.get('DistribuitorJudet') or "").strip(),
                "address": address,
            })

        return render_template('view_distributors.html', distributors=distributors)

    # rută pentru crearea unui nou distribuitor
    @app.route('/create-distributor', methods=['GET', 'POST'])
    def create_distributor():
        if not session.get('loggedin') or session.get('role') != 'employee':
            flash("Unauthorized: This action requires employee privileges.")
            return redirect(url_for('login'))

        if request.method == 'POST':
            # preluăm datele din formular
            name = request.form.get('DistribuitorNume', '').strip()
            phone = request.form.get('DistribuitorTelefon', '').strip() or None
            email = request.form.get('DistribuitorEmail', '').strip() or None
            street = request.form.get('DistribuitorStrada', '').strip() or None
            number = request.form.get('DistribuitorNumar', '').strip() or None
            city = request.form.get('DistribuitorOras', '').strip() or None
            county = request.form.get('DistribuitorJudet', '').strip() or None
            if not name:
                flash("Company name is required.")
                return redirect(request.url)

            # verificăm dacă există deja un distribuitor cu același nume
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM dbo.Distribuitor WHERE DistribuitorNume = ?",
                (name,)
            )
            if cursor.fetchone():
                flash("A company with this name already exists.")
                return redirect(request.url)

            try:
                # dacă toate verificările au trecut, inserăm noul distribuitor
                cursor.execute(
                    """
                    INSERT INTO dbo.Distribuitor (
                        DistribuitorNume,
                        DistribuitorTelefon,
                        DistribuitorEmail,
                        DistribuitorStrada,
                        DistribuitorNumar,
                        DistribuitorOras,
                        DistribuitorJudet
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, phone, email, street, number, city, county)
                )
                conn.commit()
                flash("Delivery company added successfully!")
                return redirect(url_for('view_distributors'))
            except Exception as e:
                conn.rollback()
                flash(f"An error occurred: {str(e)}")
                return redirect(request.url)

        return render_template('create_distributor.html')

    # rută pentru editarea unui distribuitor existent de către angajat
    @app.route('/edit-distributor/<int:distributor_id>', methods=['GET', 'POST'])
    def edit_distributor(distributor_id):
        if not session.get('loggedin') or session.get('role') != 'employee':
            flash("Unauthorized: This action requires employee privileges.")
            return redirect(url_for('login'))

        # preluăm datele distribuitorului existent pentru a le afișa în formular
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM dbo.Distribuitor
            WHERE DistribuitorId = ?
            """,
            (distributor_id,)
        )
        row = cursor.fetchone()
        if not row:
            flash("Delivery company not found.")
            return redirect(url_for('view_distributors'))

        columns = [col[0] for col in cursor.description]
        distributor = dict(zip(columns, row))

        if request.method == 'POST':
            # preluăm datele actualizate din formular
            name = request.form.get('DistribuitorNume', '').strip()
            phone = request.form.get('DistribuitorTelefon', '').strip() or None
            email = request.form.get('DistribuitorEmail', '').strip() or None
            street = request.form.get('DistribuitorStrada', '').strip() or None
            number = request.form.get('DistribuitorNumar', '').strip() or None
            city = request.form.get('DistribuitorOras', '').strip() or None
            county = request.form.get('DistribuitorJudet', '').strip() or None

            if not name:
                flash("Company name is required.")
                return redirect(request.url)

            try:
                # actualizăm datele distribuitorului în baza de date printr-o interogare UPDATE
                cursor.execute(
                    """
                    UPDATE dbo.Distribuitor
                    SET DistribuitorNume = ?,
                        DistribuitorTelefon = ?,
                        DistribuitorEmail = ?,
                        DistribuitorStrada = ?,
                        DistribuitorNumar = ?,
                        DistribuitorOras = ?,
                        DistribuitorJudet = ?
                    WHERE DistribuitorId = ?
                    """,
                    (name, phone, email, street, number, city, county, distributor_id)
                )
                conn.commit()
                flash("Delivery company updated successfully!")
                return redirect(url_for('view_distributors'))
            except Exception as e:
                conn.rollback()
                flash(f"An error occurred: {str(e)}")
                return redirect(request.url)

        return render_template('edit_distributor.html', distributor=distributor)

    # rută pentru vizualizarea detaliilor unei livrări
    @app.route('/delivery-details/<int:delivery_id>')
    def delivery_details(delivery_id):
        if not session.get('loggedin') or session.get('role') != 'employee':
            flash("Unauthorized: This action requires employee privileges.")
            return redirect(url_for('login'))

        # mai întâi preluăm detaliile livrării
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

        # apoi preluăm produsele asociate livrării
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
    
    # rută pentru ștergerea unei livrări
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
