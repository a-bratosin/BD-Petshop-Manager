from flask import Flask

from os import getenv
from dotenv import load_dotenv
from pyodbc import connect


# FORMAT: UID is the user, PWD is the password
load_dotenv()
conn = connect(getenv("SQL_CONNECTION_STRING"))

print("Connected!")


app = Flask(__name__)



@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"