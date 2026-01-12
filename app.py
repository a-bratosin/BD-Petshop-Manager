import uuid
from os import getenv

from dotenv import load_dotenv
from flask import Flask, session
from pyodbc import connect

# fiindcă aplicația este compusă din ~2000 de linii de cod, am împărțit-o în mai multe module
from routes import auth, customer, employee, products, orders, deliveries


# în aplicația principală doar realizez conexiunea la baza de date și înregistrez modulele de rute
def create_app():
    load_dotenv()

    # conectare la baza de date
    conn = connect(getenv("SQL_CONNECTION_STRING"))
    print("Connected!")

    app = Flask(__name__)
    # inițializez cheia secretă pentru a permite trimiterea de mesaje flash
    app.config['SECRET_KEY'] = getenv("SESSION_KEY")
    # generez un ID unic pentru instanța curentă a serverului
    app.config['SERVER_INSTANCE_ID'] = uuid.uuid4().hex
    app.config['DB_CONN'] = conn
    app.config['MAX_IMAGE_BYTES'] = 5 * 1024 * 1024

    # înainte de a procesa orice cerere, verific dacă sesiunea aparține instanței curente a serverului
    # dacă nu, șterg sesiunea asociată utilizatorului
    @app.before_request
    def enforce_server_session():
        server_id = app.config.get('SERVER_INSTANCE_ID')
        if session:
            session_server = session.get('server_instance')
            if session_server and session_server != server_id:
                session.clear()
            elif not session_server:
                session['server_instance'] = server_id

    auth.register(app)
    customer.register(app)
    employee.register(app)
    products.register(app)
    orders.register(app)
    deliveries.register(app)

    return app


app = create_app()


if __name__ == "__main__":
    app.run()
