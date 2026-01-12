

### A) auth.py

1) Obținerea utilizatorului cu credențialele introduse în formularul de login (interogare simplă cu SELECT):
~~~
'SELECT UserId,Username,UserCategory FROM Utilizatori WHERE Username=? and Password=?', (username, password_hash)
~~~

2) Introducerea unui nou utilizator în baza de date (Interogare simplă cu INSERT):
~~~
"""INSERT INTO dbo.Utilizatori (Username, Password, UserCategory)
OUTPUT INSERTED.UserId
VALUES (?, ?, ?)""", (email, password_hash, 'customer')
~~~

3) Introducerea clientului aferent (Interogare simplă cu INSERT):
~~~
"""INSERT INTO dbo.Client (UserId, ClientNume, ClientPrenume, ClientTelefon, ClientStrada, ClientNumar, ClientOras, ClientJudet)
OUTPUT INSERTED.ClientId
VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (user_id, nume, prenume, telefon, strada, numar, oras, judet)
~~~

4) Introducerea cardului de loialiate aferent (Interogare simplă cu INSERT):
~~~
"""INSERT INTO dbo.CardFidelitate (ClientId, DataInregistrarii)
VALUES (?, ?)""", (client_id, now)
~~~

### B) customer.py

5) Obținerea primelor 12 cele mai bine-vândute produse (Interogare complexă cu subcerere în JOIN)
~~~
SELECT TOP 12
            p.ProdusId,
            p.Imagine,
            p.Stoc,
            p.Pret,
            p.Descriere,
            sales.TotalSold
        FROM dbo.Produs p
        JOIN (
            SELECT
                pc.ProdusId,
                SUM(pc.ProdusComandaCantitate) AS TotalSold
            FROM dbo.ProdusComanda pc
            GROUP BY pc.ProdusId
        ) sales ON sales.ProdusId = p.ProdusId
        ORDER BY sales.TotalSold DESC, p.Descriere
        """
~~~

6) Selectarea unei categorii aleatoare care care conține produse (Interogare cu JOIN/INNER JOIN, JOIN are rolul de a filtra pentru categorii cu subcategorii și produse):
~~~
SELECT TOP 1
    c.CategorieId,
    c.CategorieNume
FROM dbo.Categorie c
JOIN dbo.Subcategorie s ON s.CategorieId = c.CategorieId
JOIN dbo.Produs p ON p.SubcategorieId = s.SubcategorieId
GROUP BY c.CategorieId, c.CategorieNume
ORDER BY NEWID()
~~~

7) Selectarea primelor 12 produse care aparțin unei categorii date (Interogare complexă cu JOIN):
~~~
"""
SELECT TOP 12
    p.ProdusId,
    p.Imagine,
    p.Stoc,
    p.Pret,
    p.Descriere
FROM dbo.Produs p
JOIN dbo.Subcategorie s ON s.SubcategorieId = p.SubcategorieId
WHERE s.CategorieId = ?
ORDER BY p.Descriere
""",
(category_row.CategorieId,)
~~~

8) Selectarea unei subcategorii aleatoare care care conține produse (Interogare complexă cu JOIN)
~~~
SELECT TOP 1
    s.SubcategorieId,
    s.SubcategorieNume,
    c.CategorieNume
FROM dbo.Subcategorie s
JOIN dbo.Categorie c ON c.CategorieId = s.CategorieId
JOIN dbo.Produs p ON p.SubcategorieId = s.SubcategorieId
GROUP BY s.SubcategorieId, s.SubcategorieNume, c.CategorieNume
ORDER BY NEWID()
~~~
9) Selectarea primelor 12 produse care aparțin unei subcategorii date (Interogare simplă cu SELECT)
~~~
"""
SELECT TOP 12
    p.ProdusId,
    p.Imagine,
    p.Stoc,
    p.Pret,
    p.Descriere
FROM dbo.Produs p
WHERE p.SubcategorieId = ?
ORDER BY p.Descriere
""",
(subcategory_row.SubcategorieId,)
~~~
10) Selectarea tuturor produselor ale căror descrieri se potrivesc cu un query (interogare simplă cu SELECT):
~~~
"""
SELECT
    p.ProdusId,
    p.Imagine,
    p.Stoc,
    p.Pret,
    p.Descriere
FROM dbo.Produs p
WHERE p.Descriere LIKE ?
ORDER BY p.Descriere
""",
(f"%{query}%",)
~~~

11) Selectarea numelui unei categorii după id (interogare simplă cu SELECT):
~~~
"SELECT CategorieNume FROM dbo.Categorie WHERE CategorieId = ?", (category_id,)
~~~

12) Selectarea tuturor produselor care aparțin unei categorii (interogare simplă cu SELECT):
~~~
"""
SELECT
    p.ProdusId,
    p.Imagine,
    p.Stoc,
    p.Pret,
    p.Descriere
FROM dbo.Produs p
JOIN dbo.Subcategorie s ON s.SubcategorieId = p.SubcategorieId
WHERE s.CategorieId = ?
ORDER BY p.Descriere
""",
(category_id,)
~~~

13) Selectarea numelui, și descrierii unei subcategorii, dar și numele categorieri aferente, după Id (Interogare simplă cu JOIN)
~~~
"""
SELECT s.SubcategorieNume, s.SubcategorieDescriere, c.CategorieNume
FROM dbo.Subcategorie s
JOIN dbo.Categorie c ON c.CategorieId = s.CategorieId
WHERE s.SubcategorieId = ?
""",
(subcategory_id,)
~~~

14) Selectarea tuturor produselor care aparțin unei subcategorii (interogare simplă cu SELECT):
~~~
"""
SELECT
    p.ProdusId,
    p.Imagine,
    p.Stoc,
    p.Pret,
    p.Descriere
FROM dbo.Produs p
WHERE p.SubcategorieId = ?
ORDER BY p.Descriere
""",
(subcategory_id,)
~~~

15) Selectarea detaliilor despre un produs în funcție de ID (interogare simplă cu SELECT):
~~~
"""
SELECT ProdusId, Imagine, Stoc, Pret, Descriere
FROM dbo.Produs
WHERE ProdusId = ?
""",
(product_id,)
~~~

16) Selectarea detaliilor despre produse pentru o listă de ID-uri de produse (interogare simplă cu SELECT):
~~~
f"""
SELECT ProdusId, Descriere, Pret, Imagine
FROM dbo.Produs
WHERE ProdusId IN ({placeholders})
""",
tuple(cart_ids)
~~~

17) Selectarea detaliilor despre produse pentru o listă de ID-uri de produse (interogare simplă cu SELECT):
~~~
"SELECT ProdusId, Stoc, Descriere FROM dbo.Produs WHERE ProdusId = ?",
(product_id,)
~~~

18) Selectarea doar a stocului unui produs în funcție de ID (interogare simplă cu SELECT):
~~~
"SELECT Stoc FROM dbo.Produs WHERE ProdusId = ?", (product_id,)
~~~

19) Selectarea Id-ului clientului după UserId (Interogare simplă cu SELECT)
~~~
"SELECT ClientId FROM dbo.Client WHERE UserId = ",
(session.get('id'),)
~~~

20) Selectarea stocurilor pentru o listă de Id-uri de produse (interogare simplă cu SELECT)
~~~
f"""
SELECT ProdusId, Stoc
FROM dbo.Produs
WHERE ProdusId IN ({placeholders})
""",
tuple(requested.keys())
~~~

21) Selectarea datei înregistrării în funcție de ClientId (interogare simplă cu SELECT)
~~~
"""
SELECT DataInregistrarii
FROM dbo.CardFidelitate
WHERE ClientId = ?
""",
(client_id,)
~~~

22) Introducerea unei comenzi noi în baza de date (interogare simplă cu INSERT)
~~~
"""
INSERT INTO dbo.Comanda (ComandaData, ClientId, AngajatId, ReducereLoialitate)
OUTPUT INSERTED.ComandaId
VALUES (?, ?, ?, ?)
""",
(now, client_id, None, discount_pct)
~~~

23) Inserarea unei intrări în tabelul ProdusComanda (interogare simplă cu INSERT)
~~~
"""
INSERT INTO dbo.ProdusComanda (ProdusId, ComandaId, ProdusComandaCantitate)
VALUES (?, ?, ?)
""",
(pid, comanda_id, qty)
~~~

24) Actualizarea stocului după trimiterea unei comenzi (Interogare simplă cu UPDATE)
~~~
"UPDATE dbo.Produs SET Stoc = ? WHERE ProdusId = ?", (products_by_id[pid] - qty, pid)
~~~

25) Obținerea tuturor comenzilor trimise de clientul actual (Interogare complexă cu funcții agregat):
~~~
"""
SELECT
    c.ComandaId,
    c.ComandaData,
    c.ReducereLoialitate,
    SUM(pc.ProdusComandaCantitate * p.Pret) AS TotalPret
FROM dbo.Comanda c
JOIN dbo.Client cl ON cl.ClientId = c.ClientId
LEFT JOIN dbo.ProdusComanda pc ON pc.ComandaId = c.ComandaId
LEFT JOIN dbo.Produs p ON p.ProdusId = pc.ProdusId
WHERE cl.UserId = ?
GROUP BY c.ComandaId, c.ComandaData, c.ReducereLoialitate
ORDER BY c.ComandaId DESC
""",
(session.get('id'),)
~~~

26) Obținerea detaliilor despre o comandă în funcție de ID, verificând că aceasta aparține utilizatorului curent (Interogare simplă cu JOIN)
~~~
 """
SELECT
    c.ComandaId,
    c.ComandaData,
    c.ReducereLoialitate
FROM dbo.Comanda c
JOIN dbo.Client cl ON cl.ClientId = c.ClientId
WHERE cl.UserId = ? AND c.ComandaId = ?
""",
(session.get('id'), order_id)
~~~

27) Obținerea cantității cumpărate dintr-un produs într-o comandă, împreună cu descriereea și prețul său (Interogare simplă cu JOIN)
~~~
"""
SELECT
    p.Descriere,
    pc.ProdusComandaCantitate,
    p.Pret
FROM dbo.ProdusComanda pc
JOIN dbo.Produs p ON p.ProdusId = pc.ProdusId
WHERE pc.ComandaId = ?
ORDER BY p.Descriere
""",
(order_id,)
~~~

28) Obținerea detaliilor despre clientul actual prin intermediul UserId (interogare simplă cu JOIN):
~~~
"""
SELECT
    c.ClientId,
    c.ClientNume,
    c.ClientPrenume,
    c.ClientTelefon,
    c.ClientStrada,
    c.ClientNumar,
    c.ClientOras,
    c.ClientJudet,
    u.Username
FROM dbo.Client c
JOIN dbo.Utilizatori u ON u.UserId = c.UserId
WHERE u.UserId = ?
""",
(session.get('id'),)
~~~

29) Obținerea datei înregistrării a cardului de loialitate al unui client (interogare simplă cu SELECT):
~~~
"""
SELECT DataInregistrarii
FROM dbo.CardFidelitate
WHERE ClientId = ?
""",
~~~


30) Selectarea datei primei comenzi trimise de client (interogare simplă cu SELECT + funcție agregat):
~~~
"""
SELECT MIN(ComandaData)
FROM dbo.Comanda
WHERE ClientId = ?
""",
(client_row.ClientId,)
~~~

31) Selectarea detaliilor despre un client în funcție de ID (interogare simplă cu SELECT):
~~~
"""
SELECT ClientNume, ClientPrenume, ClientStrada, ClientNumar, ClientOras, ClientJudet
FROM dbo.Client
WHERE UserId = ?
""",
(session.get('id'),)
~~~

32) Actualizarea câmpurilor unui element din tabela Client pe baza unui UserId (interogare simplă cu UPDATE):
~~~
"""
UPDATE dbo.Client
SET ClientNume = ?, ClientPrenume = ?, ClientStrada = ?, ClientNumar = ?, ClientOras = ?, ClientJudet = ?
WHERE UserId = ?
""",
~~~

33) Actualizarea parolei unui utilizator în funcție de ID (interogare simplă cu UPDATE)


### C) deliveries.py

34) Selectarea tuturor produselor din tabelul Produs (interogare simplă cu SELECT):
~~~
SELECT ProdusId, Descriere, Pret, Cost FROM dbo.Produs
~~~

35) Selectarea numelor și IDurilor tuturor distribuitorilor (interogare simplă cu SELECT)
~~~
SELECT DistribuitorId, DistribuitorNume FROM dbo.Distribuitor
~~~

36) Selectarea id-ului angajatului în funcție de UserId (interogare simplă cu SELECT):
~~~
"SELECT AngajatId FROM dbo.Angajat WHERE UserId = ?"
~~~
37) Selectarea Id-urilor și descrierilor pentru o listă de produse după descrieri (interogare simplă cu SELECT)
~~~
f"""
SELECT ProdusId, Descriere
FROM dbo.Produs
WHERE Descriere IN ({placeholders})
""",
tuple(requested.keys())
~~~

38) Introducerea unei livrări noi (interogare simplă cu INSERT)
~~~
"""
INSERT INTO dbo.Livrare (DistribuitorId, DataLivrare, AngajatId)
OUTPUT INSERTED.LivrareId
VALUES (?, ?, ?)
""",
(distributor_id, now, angajat_id)
~~~

39) Introducerea elementelor de legătură după introducerea livrării (interogare simplă cu INSERT)
~~~
"""
INSERT INTO dbo.ProdusLivrare (ProdusId, LivrareId, ProdusLivrareCantitate)
VALUES (?, ?, ?)
""",
~~~

40) Actualizarea stocului după o livrare (interogare simplă cu UPDATE):
~~~
"UPDATE dbo.Produs SET Stoc = Stoc + ? WHERE ProdusId = ?", (qty, produs_id)
~~~

41) Obținerea istoricului tuturor livrărilor (interogare complexă cu JOIN)
~~~
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
~~~


42) Selectarea tuturor distribuitorilor (Interogare simplă cu SELECT)
~~~
"""
SELECT *
FROM dbo.Distribuitor
ORDER BY DistribuitorNume
"""
~~~


43) Selectarea primului distribuitor cu un nume dat (interogare simplă cu SELECT):
~~~
"SELECT 1 FROM dbo.Distribuitor WHERE DistribuitorNume = ?",(name,)
~~~

44) Introducerea unui distribuitor nou (interogare simplă cu INSERT)
~~~
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
~~~

45) Selectarea tutuor informațiilor despre un Distribuitor în funcție de ID (interogare simplă cu SELECT)
~~~
"""
SELECT *
FROM dbo.Distribuitor
WHERE DistribuitorId = ?
""",
(distributor_id,)
~~~

46) Actualizarea detaliilor despre un Distribuitor (interogare simplă cu UPDATE)
~~~
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
~~~

47) Selectarea datei unei livrări și numelui utilizatorului în funcție de id-ul livrării (interogare simplă cu SELECT)
~~~
"""
SELECT l.LivrareId, d.DistribuitorNume, l.DataLivrare
FROM dbo.Livrare l
JOIN dbo.Distribuitor d ON d.DistribuitorId = l.DistribuitorId
WHERE l.LivrareId = ?
""",
(delivery_id,)
~~~

48) Extragerea produselor asociate unei livrări (interogare simplă cu SELECT)
~~~
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
~~~

49) Verificara existenței unei livrări după ID (interogare simplă cu SELECT)
~~~
SELECT 1 FROM dbo.Livrare WHERE LivrareId = ?", (delivery_id,)
~~~
50) Eliminarea unei intrări ProdusLivrare asociată unei livrări (interogare simplă cu DELETE)
~~~
"DELETE FROM dbo.ProdusLivrare WHERE LivrareId = ?", (delivery_id,)
~~~
1)  Eliminarea unei intrări Livrare în funcție de ID (interogare simplă cu DELETE)
~~~
"DELETE FROM dbo.Livrare WHERE LivrareId = ?", (delivery_id,)
~~~
