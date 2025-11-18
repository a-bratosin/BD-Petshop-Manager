from flask import Flask, render_template, request, redirect, url_for, session
from os import getenv
from dotenv import load_dotenv
from pyodbc import connect
import hashlib

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
            session['username'] = account[1]
            return render_template('index.html', msg='Logged in successfully!')
        else:
            msg = 'Incorrect username/password!'
    return render_template('login.html', msg=msg)


@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    return redirect(url_for('login'))
