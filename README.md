Pentru rulare:
~~~
pip install -r requirements.md (cel mai bine într-un venv)

python -m flask --app main.py run
~~~

Important: Autentificarea la baza de date o fac prin intermediul autentificatorului Windows. Pentru asta, programul citește la inițializare environment variable-ul SQL_CONNECTION_STRING din .env. Pentru a asigura conectarea la baza de date, numele desktop-ului din SQL_CONNECTION_STRING trebuie modificat.

Pentru testarea funcționalităților, am creat aceste două conturi:

- angajat: `test@test.test` / `test`
- client: `a@b.c` / `1234`