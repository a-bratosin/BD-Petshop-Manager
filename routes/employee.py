from datetime import datetime, timedelta

from flask import render_template, request, redirect, url_for, session, flash


def register(app):
    conn = app.config['DB_CONN']

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
        current_customer_range, customer_range_label, customer_start, customer_end = resolve_range(customer_range_key)
        current_delivery_range, delivery_range_label, delivery_start, delivery_end = resolve_range(delivery_range_key)

        orders_filter = ""
        orders_params = ()
        if customer_start is not None and customer_end is not None:
            orders_filter = "WHERE c.ComandaData >= ? AND c.ComandaData <= ?"
            orders_params = (customer_start, customer_end)

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
            top_products=top_products,
            current_customer_range=current_customer_range,
            customer_range_label=customer_range_label,
            current_delivery_range=current_delivery_range,
            delivery_range_label=delivery_range_label
        )
