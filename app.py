import uuid
from os import getenv

from dotenv import load_dotenv
from flask import Flask, session
from pyodbc import connect

from routes import auth, customer, employee, products, orders, deliveries


def create_app():
    load_dotenv()

    conn = connect(getenv("SQL_CONNECTION_STRING"))
    print("Connected!")

    app = Flask(__name__)
    app.config['SECRET_KEY'] = getenv("SESSION_KEY")
    app.config['SERVER_INSTANCE_ID'] = uuid.uuid4().hex
    app.config['DB_CONN'] = conn
    app.config['MAX_IMAGE_BYTES'] = 5 * 1024 * 1024

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
