from datetime import datetime, timedelta

from flask import render_template, request, redirect, url_for, session, flash

# module pentru rutele angajaților

def register(app):
    conn = app.config['DB_CONN']

    # rută pentru panoul de control al angajaților
    @app.route('/employee-dashboard')
    def employee_dashboard():
        if not session.get('loggedin') or session.get('role') != 'employee':
            flash("Unauthorized: This action requires employee privileges.")
            return redirect(url_for('login'))
        return render_template('employee_dashboard.html')

    # rută pentru vizualizarea veniturilor și cheltuielilor într-un interval calendaristic introdus din formular
    @app.route('/revenues-expenses', methods=['GET', 'POST'])
    def revenues_expenses():
        if not session.get('loggedin') or session.get('role') != 'employee':
            flash("Unauthorized: This action requires employee privileges.")
            return redirect(url_for('login'))

        # preluăm datele din formular 
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
                    # calculăm veniturile și cheltuielile în intervalul specificat
                    cursor.execute(
                        """
                        SELECT SUM(pc.ProdusComandaCantitate * p.Pret) AS TotalRevenue
                        FROM dbo.Comanda c
                        JOIN dbo.ProdusComanda pc ON pc.ComandaId = c.ComandaId
                        JOIN dbo.Produs p ON p.ProdusId = pc.ProdusId
                        WHERE c.ComandaData >= ? AND c.ComandaData <= ?
                        """,
                        (start_date, end_date)
                    )
                    revenue_row = cursor.fetchone()
                    revenue = float(revenue_row[0]) if revenue_row and revenue_row[0] is not None else 0.0

                    cursor.execute(
                        """
                        SELECT SUM(pl.ProdusLivrareCantitate * p.Cost) AS TotalExpense
                        FROM dbo.Livrare l
                        JOIN dbo.ProdusLivrare pl ON pl.LivrareId = l.LivrareId
                        JOIN dbo.Produs p ON p.ProdusId = pl.ProdusId
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
    
    # rută pentru vizualizarea analizelor de date despre clienți, distribuitori și produse
    @app.route('/analytics')
    def analytics():
        if not session.get('loggedin') or session.get('role') != 'employee':
            flash("Unauthorized: This action requires employee privileges.")
            return redirect(url_for('login'))

        cursor = conn.cursor()
        range_options = {
            "month": ("Past Month", timedelta(days=30)),
            "6months": ("Past 6 Months", timedelta(days=183)),
            "all": ("All Time", None),
        }

        def resolve_range(range_key):
            key = range_key.strip().lower()
            if key not in range_options:
                key = "all"
            label, delta = range_options[key]
            if delta is None:
                return key, label, None, None
            end_date = datetime.now()
            start_date = end_date - delta
            return key, label, start_date, end_date

        customer_range_key = request.args.get('customer_range', 'all')
        delivery_range_key = request.args.get('delivery_range', 'all')
        low_turnover_range_key = request.args.get('low_turnover_range', 'all')
        current_customer_range, customer_range_label, customer_start, customer_end = resolve_range(customer_range_key)
        current_delivery_range, delivery_range_label, delivery_start, delivery_end = resolve_range(delivery_range_key)
        current_low_turnover_range, low_turnover_range_label, low_turnover_start, low_turnover_end = resolve_range(
            low_turnover_range_key
        )

        orders_filter = ""
        orders_params = ()
        if customer_start is not None and customer_end is not None:
            orders_filter = "WHERE c.ComandaData >= ? AND c.ComandaData <= ?"
            orders_params = (customer_start, customer_end)

        # analizăm clienții cei mai activi și cei care au cheltuit cei mai mulți bani
        cursor.execute(
            f"""
            SELECT TOP 1
                cl.ClientId,
                cl.ClientNume,
                cl.ClientPrenume,
                u.Username,
                COUNT(*) AS OrderCount
            FROM dbo.Comanda c
            JOIN dbo.Client cl ON cl.ClientId = c.ClientId
            JOIN dbo.Utilizatori u ON u.UserId = cl.UserId
            {orders_filter}
            GROUP BY cl.ClientId, cl.ClientNume, cl.ClientPrenume, u.Username
            ORDER BY COUNT(*) DESC, cl.ClientId
            """,
            orders_params
        )
        row = cursor.fetchone()
        prolific_by_orders = None
        if row:
            prolific_by_orders = {
                "name": f"{row.ClientNume} {row.ClientPrenume}",
                "email": row.Username,
                "count": int(row.OrderCount),
            }

        # analizăm clientul care a cheltuit cei mai mulți bani
        cursor.execute(
            f"""
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
            {orders_filter}
            GROUP BY cl.ClientId, cl.ClientNume, cl.ClientPrenume, u.Username
            ORDER BY SUM(pc.ProdusComandaCantitate * p.Pret) DESC, cl.ClientId
            """,
            orders_params
        )
        row = cursor.fetchone()
        prolific_by_spend = None
        if row:
            prolific_by_spend = {
                "name": f"{row.ClientNume} {row.ClientPrenume}",
                "email": row.Username,
                "total": float(row.TotalSpent) if row.TotalSpent is not None else 0.0,
            }

        # analizăm distribuitorii cei mai activi și cei care au livrat cele mai multe produse
        cursor.execute(
            f"""
            SELECT TOP 1
                d.DistribuitorId,
                d.DistribuitorNume,
                COUNT(l.LivrareId) AS DeliveryCount
            FROM dbo.Distribuitor d
            LEFT JOIN dbo.Livrare l ON l.DistribuitorId = d.DistribuitorId
            {"AND l.DataLivrare >= ? AND l.DataLivrare <= ?" if delivery_start is not None and delivery_end is not None else ""}
            GROUP BY d.DistribuitorId, d.DistribuitorNume
            ORDER BY COUNT(l.LivrareId) DESC, d.DistribuitorId
            """,
            (delivery_start, delivery_end) if delivery_start is not None and delivery_end is not None else ()
        )
        row = cursor.fetchone()
        prolific_distributor = None
        if row:
            prolific_distributor = {
                "name": row.DistribuitorNume,
                "count": int(row.DeliveryCount),
            }
    
        # analizăm distribuitorul care a livrat cele mai multe produse
        cursor.execute(
            f"""
            SELECT TOP 1
                d.DistribuitorId,
                d.DistribuitorNume,
                SUM(pl.ProdusLivrareCantitate) AS QuantityTotal
            FROM dbo.Distribuitor d
            LEFT JOIN dbo.Livrare l ON l.DistribuitorId = d.DistribuitorId
            {"AND l.DataLivrare >= ? AND l.DataLivrare <= ?" if delivery_start is not None and delivery_end is not None else ""}
            LEFT JOIN dbo.ProdusLivrare pl ON pl.LivrareId = l.LivrareId
            GROUP BY d.DistribuitorId, d.DistribuitorNume
            ORDER BY SUM(pl.ProdusLivrareCantitate) DESC, d.DistribuitorId
            """,
            (delivery_start, delivery_end) if delivery_start is not None and delivery_end is not None else ()
        )
        row = cursor.fetchone()
        prolific_distributor_qty = None
        if row and row.QuantityTotal is not None:
            prolific_distributor_qty = {
                "name": row.DistribuitorNume,
                "quantity": int(row.QuantityTotal),
            }

        # analizăm cele mai bine vândute produse după venituri
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

        turnover_filter = ""
        turnover_params = ()
        if low_turnover_start is not None and low_turnover_end is not None:
            turnover_filter = "WHERE c.ComandaData >= ? AND c.ComandaData <= ?"
            turnover_params = (low_turnover_start, low_turnover_end)

        cursor.execute(
            f"""
            SELECT TOP 5
                p.ProdusId,
                p.Descriere,
                COALESCE(sales.TotalSold, 0) AS TotalSold
            FROM dbo.Produs p
            LEFT JOIN (
                SELECT
                    pc.ProdusId,
                    SUM(pc.ProdusComandaCantitate) AS TotalSold
                FROM dbo.Comanda c
                JOIN dbo.ProdusComanda pc ON pc.ComandaId = c.ComandaId
                {turnover_filter}
                GROUP BY pc.ProdusId
            ) sales ON sales.ProdusId = p.ProdusId
            ORDER BY COALESCE(sales.TotalSold, 0) ASC, p.Descriere
            """,
            turnover_params
        )
        rows = cursor.fetchall()
        low_turnover_products = [
            {
                "id": row.ProdusId,
                "name": row.Descriere,
                "total_sold": int(row.TotalSold) if row.TotalSold is not None else 0,
            }
            for row in rows
        ]

        return render_template(
            'analytics.html',
            prolific_by_orders=prolific_by_orders,
            prolific_by_spend=prolific_by_spend,
            prolific_distributor=prolific_distributor,
            prolific_distributor_qty=prolific_distributor_qty,
            top_products=top_products,
            low_turnover_products=low_turnover_products,
            current_customer_range=current_customer_range,
            customer_range_label=customer_range_label,
            current_delivery_range=current_delivery_range,
            delivery_range_label=delivery_range_label,
            current_low_turnover_range=current_low_turnover_range,
            low_turnover_range_label=low_turnover_range_label
        )
