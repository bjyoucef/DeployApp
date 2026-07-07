from app import get_db_connection
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT * FROM menu_items WHERE label LIKE '%Archiv%' OR label LIKE '%Boîte%';")
items = cursor.fetchall()
print("DEBUG: Existing items:")
for item in items:
    print(item)

# Check if parent Archivage exists
parent = next((i for i in items if i['label'] == 'Archivage' and i['parent_id'] is None), None)
if parent:
    parent_id = parent['id']
    print(f"DEBUG: Found parent Archivage with id={parent_id}")
    
    # Check if shortcut already exists
    exists = any(i for i in items if i['route'] == 'archivage_boites_list')
    if not exists:
        cursor.execute("""
            INSERT INTO menu_items (label, route, icon, parent_id, privilege, tooltip)
            VALUES ('Toutes les Boîtes', 'archivage_boites_list', 'fas fa-boxes', %s, 'MENU_ARCHIVAGE', 'Gérer les boîtes d\\'archives')
        """, (parent_id,))
        conn.commit()
        print("DEBUG: Inserted Toutes les Boîtes menu item successfully.")
    else:
        print("DEBUG: Menu item already exists.")
else:
    print("DEBUG: Parent Archivage not found.")
conn.close()
