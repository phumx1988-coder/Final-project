import sqlite3
from pathlib import Path
DB = Path(__file__).with_name("footzone.db")
PRODUCT_SQL = "SELECT p.*, b.name AS brand, c.name AS category FROM products p JOIN brands b ON b.id=p.brand_id JOIN categories c ON c.id=p.category_id"
CAT_EMOJI={"รองเท้าฟุตบอล":"👟","เสื้อฟุตบอล":"👕","ลูกฟุตบอล":"⚽","อุปกรณ์":"🏆","กระเป๋า":"🎒","ผู้รักษาประตู":"🧤","รองเท้าฟุตซอล":"👟","อุปกรณ์ป้องกัน":"🛡️","อุปกรณ์ฝึกซ้อม":"🎯","เสื้อผ้าและอุปกรณ์":"👕"}
CATEGORY_DEFAULT_IMAGES={
    "รองเท้าฟุตบอล":"/static/categories/boots.svg",
    "เสื้อฟุตบอล":"/static/categories/jersey.svg",
    "ลูกฟุตบอล":"/static/categories/ball.svg",
    "อุปกรณ์":"/static/categories/gear.svg",
    "กระเป๋า":"/static/categories/bag.svg",
    "ผู้รักษาประตู":"/static/categories/goalkeeper.svg",
    "รองเท้าฟุตซอล":"/static/categories/futsal.svg",
    "อุปกรณ์ป้องกัน":"/static/categories/protection.svg",
    "อุปกรณ์ฝึกซ้อม":"/static/categories/training.svg",
    "เสื้อผ้าและอุปกรณ์":"/static/categories/apparel.svg",
}
BRAND_COLORS={"Nike":"#f15e42","Adidas":"#557fb4","Puma":"#c48d44","Mizuno":"#599f84"}
def connect():
    db=sqlite3.connect(DB, timeout=15)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    return db
def init_db():
    with connect() as db:
        db.executescript("""
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, phone TEXT UNIQUE, password_hash TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS brands(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, image TEXT DEFAULT "");
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, brand_id INTEGER NOT NULL REFERENCES brands(id), category_id INTEGER NOT NULL REFERENCES categories(id), price REAL NOT NULL, stock INTEGER NOT NULL DEFAULT 0, image TEXT DEFAULT '', description TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS cart(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, product_id INTEGER NOT NULL REFERENCES products(id), quantity INTEGER NOT NULL CHECK(quantity>0), PRIMARY KEY(user_id, product_id));
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), total REAL NOT NULL, status TEXT NOT NULL DEFAULT 'Pending', address TEXT NOT NULL, payment_method TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id), product_id INTEGER NOT NULL REFERENCES products(id), quantity INTEGER NOT NULL, unit_price REAL NOT NULL);
""")
        columns={r[1] for r in db.execute("PRAGMA table_info(users)")}
        if "is_admin" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        if not db.execute("SELECT 1 FROM brands LIMIT 1").fetchone():
            db.executemany("INSERT INTO brands(name) VALUES(?)", [(x,) for x in BRAND_COLORS])
        if not db.execute("SELECT 1 FROM categories LIMIT 1").fetchone():
            db.executemany("INSERT INTO categories(name,image) VALUES(?,?)", [(x, CATEGORY_DEFAULT_IMAGES.get(x, "/static/categories/default.svg")) for x in CAT_EMOJI])
        category_cols={r[1] for r in db.execute("PRAGMA table_info(categories)")}
        if "image" not in category_cols:
            db.execute("ALTER TABLE categories ADD COLUMN image TEXT DEFAULT ''")
        for name,image in CATEGORY_DEFAULT_IMAGES.items():
            db.execute("UPDATE categories SET image=COALESCE(NULLIF(image,''),?) WHERE name=?",(image,name))

        if not db.execute("SELECT 1 FROM products LIMIT 1").fetchone():
            items=[("Mercurial Vapor Academy",1,1,2890,14,"รองเท้าสตั๊ดสำหรับสปีดและการควบคุมบอล"),("Predator League",2,1,3190,9,"รองเท้าสำหรับการยิงและการจ่ายบอล"),("Future Play",3,1,2290,18,"รองเท้าฟุตบอลคล่องตัว"),("Morelia Neo",4,1,4490,7,"รองเท้าฟุตบอลสัมผัสนุ่ม"),("Match Jersey Pro",1,2,1290,26,"เสื้อฟุตบอลสวมใส่สบาย"),("Training Jersey",2,2,990,35,"เสื้อฝึกซ้อมระบายอากาศ"),("Competition Ball",2,3,1590,24,"ลูกฟุตบอลสำหรับแมตช์"),("Academy Ball",1,3,890,30,"ลูกฟุตบอลสำหรับฝึกซ้อม"),("Shin Guards",3,4,590,35,"สนับแข้งเพื่อปกป้อง"),("Grip Socks",4,4,390,50,"ถุงเท้ากันลื่น")]
            db.executemany("INSERT INTO products(name,brand_id,category_id,price,stock,description) VALUES(?,?,?,?,?,?)",items)

        if 'is_active' not in {r[1] for r in db.execute('PRAGMA table_info(products)')}:
            db.execute('ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1')

        order_cols={r[1] for r in db.execute("PRAGMA table_info(orders)")}
        for name,definition in {
            'subtotal':'REAL', 'shipping_fee':'REAL NOT NULL DEFAULT 0',
            'vat_rate':'REAL', 'vat_amount':'REAL', 'net_before_vat':'REAL',
            'discount_amount':'REAL NOT NULL DEFAULT 0',
            'payment_status':"TEXT NOT NULL DEFAULT 'pending'",
            'proof_file':'TEXT', 'payment_submitted_at':'TEXT',
            'payment_reviewed_at':'TEXT', 'payment_reviewed_by':'INTEGER',
            "payment_note": "TEXT NOT NULL DEFAULT ''"
        }.items():
            if name not in order_cols: db.execute(f'ALTER TABLE orders ADD COLUMN {name} {definition}')
        db.execute("CREATE TABLE IF NOT EXISTS payment_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '')")
        db.execute("CREATE TABLE IF NOT EXISTS product_colors (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE, name TEXT NOT NULL, hex_code TEXT NOT NULL, UNIQUE(product_id,name))")
        db.execute("CREATE TABLE IF NOT EXISTS product_images (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE, image_url TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0)")
        # Preserve cart contents while allowing different colors of one product in separate rows.
        cart_cols={r[1] for r in db.execute("PRAGMA table_info(cart)")}
        if 'color_name' not in cart_cols:
            db.execute("CREATE TABLE cart_colors_new (user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, product_id INTEGER NOT NULL REFERENCES products(id), color_name TEXT NOT NULL DEFAULT '', quantity INTEGER NOT NULL CHECK(quantity>0), PRIMARY KEY(user_id,product_id,color_name))")
            db.execute("INSERT INTO cart_colors_new(user_id,product_id,color_name,quantity) SELECT user_id,product_id,'',quantity FROM cart")
            db.execute("DROP TABLE cart")
            db.execute("ALTER TABLE cart_colors_new RENAME TO cart")
        if 'color_name' not in {r[1] for r in db.execute("PRAGMA table_info(order_items)")}:
            db.execute("ALTER TABLE order_items ADD COLUMN color_name TEXT NOT NULL DEFAULT ''")
        db.execute("CREATE TABLE IF NOT EXISTS product_sizes (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE, size_name TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, UNIQUE(product_id,size_name))")
        # Rebuild only cart structure when necessary; preserve existing rows, colors and quantities.
        cart_size_cols={r[1] for r in db.execute('PRAGMA table_info(cart)')}
        if 'size_name' not in cart_size_cols:
            if 'color_name' in cart_size_cols:
                db.execute("CREATE TABLE cart_size_new (user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, product_id INTEGER NOT NULL REFERENCES products(id), color_name TEXT NOT NULL DEFAULT '', size_name TEXT NOT NULL DEFAULT '', quantity INTEGER NOT NULL CHECK(quantity>0), PRIMARY KEY(user_id,product_id,color_name,size_name))")
                db.execute("INSERT INTO cart_size_new(user_id,product_id,color_name,size_name,quantity) SELECT user_id,product_id,color_name,'',quantity FROM cart")
                db.execute('DROP TABLE cart')
                db.execute('ALTER TABLE cart_size_new RENAME TO cart')
        if 'size_name' not in {r[1] for r in db.execute('PRAGMA table_info(order_items)')}:
            db.execute("ALTER TABLE order_items ADD COLUMN size_name TEXT NOT NULL DEFAULT ''")
        db.execute("CREATE TABLE IF NOT EXISTS shipments(order_id INTEGER PRIMARY KEY REFERENCES orders(id) ON DELETE CASCADE, carrier TEXT NOT NULL DEFAULT '', tracking_number TEXT NOT NULL DEFAULT '', tracking_status TEXT NOT NULL DEFAULT 'preparing', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        db.execute("CREATE TABLE IF NOT EXISTS shipment_events(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE, status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', updated_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        # Preserve historical orders and COD semantics without claiming prior transfers were paid.
        db.execute("UPDATE orders SET payment_status='cod_due' WHERE payment_method='cod' AND payment_status='pending'")

        # อัปเดตรายการตามหมวดและรุ่นโดยไม่ทับข้อมูลสินค้าที่มีอยู่แล้ว
        from catalog_seed import seed
        seed(db)
        from product_sizes import seed_sizes
        if not db.execute("SELECT 1 FROM payment_settings WHERE key='sizes_seeded_v1'").fetchone():
            seed_sizes(db)
            db.execute("INSERT INTO payment_settings(key,value) VALUES('sizes_seeded_v1','1')")
