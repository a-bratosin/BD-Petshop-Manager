import base64

# utilitare pentru gestionarea catalogului de produse și categorii
# interogări simple, care sunt folosite în mai multe module

def fetch_categories(cursor):
    cursor.execute(
        """
        SELECT CategorieId, CategorieNume
        FROM dbo.Categorie
        ORDER BY CategorieNume
        """
    )
    categories = [
        {"id": row.CategorieId, "name": row.CategorieNume, "subcategories": []}
        for row in cursor.fetchall()
        if row.CategorieNume
    ]
    categories_by_id = {cat["id"]: cat for cat in categories}

    cursor.execute(
        """
        SELECT SubcategorieId, SubcategorieNume, CategorieId
        FROM dbo.Subcategorie
        ORDER BY SubcategorieNume
        """
    )
    for row in cursor.fetchall():
        if not row.SubcategorieNume:
            continue
        cat = categories_by_id.get(row.CategorieId)
        if cat is not None:
            cat["subcategories"].append({
                "id": row.SubcategorieId,
                "name": row.SubcategorieNume
            })

    return categories


def fetch_product_names(cursor):
    cursor.execute(
        """
        SELECT Descriere
        FROM dbo.Produs
        WHERE Descriere IS NOT NULL
        ORDER BY Descriere
        """
    )
    return [row.Descriere for row in cursor.fetchall()]


def build_products(rows):
    products = []
    for row in rows:
        image_base64 = None
        if row.Imagine:
            image_base64 = base64.b64encode(row.Imagine).decode('utf-8')
        products.append({
            "id": row.ProdusId,
            "image": image_base64,
            "stoc": int(row.Stoc) if row.Stoc is not None else 0,
            "pret": float(row.Pret) if row.Pret is not None else 0.0,
            "descriere": row.Descriere
        })
    return products
