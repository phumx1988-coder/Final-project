"""สินค้าจากรายการที่ผู้ใช้ระบุ: ไม่สมมติราคาและจำนวนสต็อก"""
CATALOG = {'กระเป๋า': [('Adidas', 'Tiro League Duffel'), ('Nike', 'Academy Team Duffel'), ('Puma', 'teamGOAL Duffel'), ('Under Armour', 'Undeniable 5.0'), ('Kipsta', 'Essential Sports Bag')], 'ผู้รักษาประตู': [('Adidas', 'Predator Pro'), ('Nike', 'Vapor Grip3'), ('Puma', 'Future Ultimate'), ('Uhlsport', 'Absolutgrip'), ('Reusch', 'Attrakt Gold X')], 'รองเท้าฟุตบอล': [('Nike', 'Mercurial Vapor 16'), ('Nike', 'Phantom GX 2'), ('Adidas', 'Predator Elite'), ('Adidas', 'F50 Elite'), ('Puma', 'Future Ultimate'), ('Puma', 'Ultra Ultimate'), ('Mizuno', 'Morelia Neo IV Japan'), ('New Balance', 'Furon Elite')], 'รองเท้าฟุตซอล': [('Nike', 'Lunar Gato II'), ('Nike', 'Tiempo Streetgato'), ('Adidas', 'Mundial Goal'), ('Adidas', 'Top Sala Competition'), ('Puma', 'Future 7 Play IT'), ('Mizuno', 'Morelia Sala Classic'), ('Joma', 'Top Flex'), ('Asics', 'Calcetto WD')], 'ลูกฟุตบอล': [('Adidas', 'UEFA Champions League Pro'), ('Adidas', 'Tiro League'), ('Nike', 'Flight'), ('Nike', 'Academy'), ('Puma', 'Orbita Ultimate'), ('Puma', 'Orbita Pro'), ('Molten', 'Vantaggio 5000'), ('Select', 'Brillant Super')], 'อุปกรณ์ป้องกัน': [('Nike', 'Mercurial Lite'), ('Adidas', 'Tiro Match Shin Guards'), ('Puma', 'Ultra Light Sleeve'), ('G-Form', 'Pro-S Blade'), ('McDavid', 'Hex Padded Leg Sleeve'), ('Storelli', 'BodyShield')], 'อุปกรณ์ฝึกซ้อม': [('Adidas', 'Tiro Training Equipment'), ('Nike', 'Training Cones'), ('Puma', 'Training Ball'), ('Select', 'Training Ball'), ('Kipsta', 'Agility Training Equipment'), ('Mitre', 'Training Equipment')], 'เสื้อผ้าและอุปกรณ์': [('Adidas', 'Tiro 24 Training Jersey'), ('Adidas', 'Entrada 22 Shorts'), ('Nike', 'Dri-FIT Academy'), ('Nike', 'Park 20'), ('Puma', 'teamGOAL Jersey'), ('Puma', 'teamLIGA Shorts'), ('Under Armour', 'Tech Training'), ('Kappa', 'Kombat')]}

# ราคาที่ผู้ใช้ระบุสำหรับรายการรหัส 11–64 (บาท)
# รักษาข้อมูลเดิม: เติมราคาให้เฉพาะสินค้ารายการตั้งต้นที่ราคายังเป็น 0
PRICES = {'กระเป๋า': [1200, 1400, 1200, 1500, 500],
 'ผู้รักษาประตู': [1500, 3500, 2500, 2800, 3500],
 'รองเท้าฟุตบอล': [7500, 7000, 8000, 8000, 6000, 6000, 9000, 7000],
 'รองเท้าฟุตซอล': [3500, 3000, 1500, 3000, 2000, 2500, 3000, 2500],
 'ลูกฟุตบอล': [5000, 1200, 5000, 1000, 3500, 2500, 4300, 4000],
 'อุปกรณ์ป้องกัน': [900, 900, 700, 1500, 1500, 2000],
 'อุปกรณ์ฝึกซ้อม': [800, 300, 1200, 1500, 400, 800],
 'เสื้อผ้าและอุปกรณ์': [1500, 600, 900, 1200, 750, 750, 990, 1200]}

def seed(db):
    # ใช้ชื่อรุ่น + แบรนด์ + หมวดหมู่ เพื่อแยกสินค้ารุ่นชื่อซ้ำกัน
    for category, models in CATALOG.items():
        prices=PRICES[category]
        assert len(prices)==len(models)
        db.execute('INSERT OR IGNORE INTO categories(name) VALUES(?)',(category,))
        cat_id=db.execute('SELECT id FROM categories WHERE name=?',(category,)).fetchone()[0]
        for (brand, name), price in zip(models,prices):
            db.execute('INSERT OR IGNORE INTO brands(name) VALUES(?)',(brand,))
            brand_id=db.execute('SELECT id FROM brands WHERE name=?',(brand,)).fetchone()[0]
            existing=db.execute('SELECT id,price FROM products WHERE name=? AND brand_id=? AND category_id=? LIMIT 1',(name,brand_id,cat_id)).fetchone()
            if existing:
                # 0 = ราคาตั้งต้นยังไม่กำหนด; ไม่เปลี่ยนราคาจริงที่แอดมินตั้งไว้แล้ว
                if existing['price']==0:
                    db.execute('UPDATE products SET price=? WHERE id=?',(price,existing['id']))
            else:
                note='เพิ่มจากรายการสินค้าที่ผู้ใช้กำหนดราคา; กรุณากำหนดสต็อกและรูปภาพในหน้าแอดมิน'
                if category=='ผู้รักษาประตู':note='ถุงมือผู้รักษาประตู — '+note
                db.execute('INSERT INTO products(name,brand_id,category_id,price,stock,description) VALUES(?,?,?,?,?,?)',(name,brand_id,cat_id,price,0,note))
