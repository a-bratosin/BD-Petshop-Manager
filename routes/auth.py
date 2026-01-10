import hashlib
import re
from datetime import datetime

from flask import render_template, request, redirect, url_for, session, flash


def register(app):
    conn = app.config['DB_CONN']

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        msg = ''
        next_path = request.args.get('next') or request.form.get('next') or ''
        if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
            username = request.form['username'].rstrip()
            password = request.form['password'].rstrip()
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            cursor = conn.cursor()
            cursor.execute('SELECT UserId,Username,UserCategory FROM Utilizatori WHERE Username=? and Password=?', (username, password_hash))
            account = cursor.fetchone()
            if account:
                session['loggedin'] = True
                session['id'] = account[0]
                session['username'] = account[1].strip()
                session['role'] = account[2].strip()
                session['server_instance'] = app.config.get('SERVER_INSTANCE_ID')
                if session['role'] == 'employee':
                    return redirect(url_for('employee_dashboard'))
                else:
                    if next_path.startswith('/'):
                        return redirect(next_path)
                    return redirect(url_for('customer_dashboard'))
            else:
                msg = 'Incorrect username/password!'
        return render_template('login.html', msg=msg, next=next_path)

    @app.route('/register', methods=['GET', 'POST'], endpoint='register')
    def register_user():
        if session.get('loggedin'):
            if session.get('role') == 'customer':
                return redirect(url_for('customer_shop'))
            return redirect(url_for('employee_dashboard'))

        if request.method == 'POST':
            nume = request.form.get('Nume', '').rstrip()
            prenume = request.form.get('Prenume', '').rstrip()
            email = request.form.get('Email', '').rstrip()
            telefon = request.form.get('Telefon', '').rstrip()
            strada = request.form.get('Strada', '').rstrip()
            numar = request.form.get('Numar', '').rstrip()
            oras = request.form.get('Oras', '').rstrip()
            judet = request.form.get('Judet', '').rstrip()
            password = request.form.get('Password', '').rstrip()
            password_confirm = request.form.get('PasswordConfirm', '').rstrip()

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

    @app.route('/logout')
    def logout():
        session.pop('loggedin', None)
        session.pop('id', None)
        session.pop('username', None)
        session.pop('role', None)
        return redirect(url_for('login'))
