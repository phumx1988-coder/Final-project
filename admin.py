"""Hidden, role-protected back office for FOOTZONE."""
import math
import hashlib
import hmac
from urllib.parse import quote
from database import PRODUCT_SQL
from auth import verify, create_session

STATUSES = ('Pending', 'Confirmed', 'Shipped', 'Completed', 'Cancelled')

def is_admin(ctx):
    return bool(ctx.user and ctx.user['is_admin'])

def session_token(ctx):
    c=ctx.cookies.get('session')
    return c.value if c else ''

def csrf(ctx):
    return hmac.new(session_token(ctx).encode(), b'FOOTZONE:admin:forms:v1', hashlib.sha256).hexdigest()

def valid_post(ctx):
    return is_admin(ctx) and bool(session_token(ctx)) and hmac.compare_digest(ctx.f.get('csrf',''), csrf(ctx))

def guard(ctx):
    if not is_admin(ctx):return ctx.not_found()

def nav():
    return '<nav class="admin-links"><a href="/admin">Dashboard</a><a href="/admin/products">จัดการสินค้า</a><a href="/admin/payment-settings">ตั้งค่ารับเงิน</a><a href="/admin/categories">หมวดหมู่</a><a href="/admin/orders">คำสั่งซื้อ</a><a href="/admin/shipping">จัดการจัดส่ง</a><a href="/admin/sales">รายงานยอดขาย</a><a href="/">หน้าร้าน</a><a href="/logout">ออกจากระบบ</a></nav>'

def page(ctx,title,content):
    return ctx.page(title, '<section class="container section admin-area">'+nav()+f'<h1>{ctx.esc(title)}</h1>'+content+'</section>')

def login_page(ctx):
    if is_admin(ctx):return ctx.redirect('/admin')
    return ctx.page('Staff Sign In',ctx.render('admin_login'))

def login(ctx):
    identity=ctx.f.get('identity','').strip().lower()
    u=ctx.db.execute('SELECT * FROM users WHERE email=? AND is_admin=1',(identity,)).fetchone()
    if not u or not verify(ctx.f.get('password',''),u['password_hash']):
        return ctx.redirect('/admin/login','อีเมลหรือรหัสผ่านไม่ถูกต้อง',True)
    create_session(ctx,u['id'])
    return ctx.redirect('/admin','เข้าสู่ระบบผู้ดูแลสำเร็จ')

def dashboard(ctx):
    denied=guard(ctx)
    if denied:return denied
    db=ctx.db
    counts={name:db.execute(query).fetchone()[0] for name,query in {
        'สินค้า':'SELECT COUNT(*) FROM products', 'จำนวนสมาชิก':'SELECT COUNT(*) FROM users WHERE is_admin=0',
        'คำสั่งซื้อ':'SELECT COUNT(*) FROM orders', 'ยอดขายที่เสร็จสิ้น':'SELECT COALESCE(SUM(total),0) FROM orders WHERE payment_status="paid" AND status!="Cancelled"',
    }.items()}
    tiles=''.join(f'<div class="admin-tile"><small>{ctx.esc(k)}</small><strong>{ctx.baht(v) if k=="ยอดขายที่เสร็จสิ้น" else v}</strong></div>' for k,v in counts.items())
    latest=db.execute('SELECT o.id,o.total,o.status,u.name FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.id DESC LIMIT 8').fetchall()
    rows=''.join(f'<tr><td>#{o["id"]}</td><td>{ctx.esc(o["name"])}</td><td>{ctx.baht(o["total"])}</td><td>{ctx.esc(o["status"])}</td></tr>' for o in latest)
    shortcuts='<div class="admin-shortcuts"><a class="btn" href="/admin/products">จัดการสินค้า</a><a class="btn btn-outline" href="/admin/product">+ เพิ่มสินค้า</a><a class="btn btn-outline" href="/admin/categories">รูปหมวดหมู่</a><a class="btn btn-outline" href="/admin/payments">ตรวจสอบชำระเงิน</a><a class="btn btn-outline" href="/admin/sales">รายงานยอดขาย</a></div>'
    return page(ctx,'Dashboard','<p class="muted">เลือกเมนูด้านบนหรือปุ่มลัดเพื่อแก้ไขข้อมูลได้ทุกเวลาในขณะที่เข้าสู่ระบบ</p>'+shortcuts+'<div class="admin-stats">'+tiles+'</div><h2>คำสั่งซื้อล่าสุด</h2><div class="admin-scroll"><table class="admin-table"><tr><th>เลขที่</th><th>ลูกค้า</th><th>ยอดรวม</th><th>สถานะ</th></tr>'+rows+'</table></div>')


def categories(ctx):
    denied=guard(ctx)
    if denied:return denied
    rows=ctx.db.execute('SELECT * FROM categories ORDER BY id').fetchall()
    parts=[]
    for c in rows:
        image=(c['image'] or '').strip()
        thumb=f'<img src="{ctx.esc(image)}" alt="{ctx.esc(c["name"])}">' if image.startswith(('http://','https://','/static/')) else '<div class="admin-thumb-fallback">ไม่มีรูป</div>'
        parts.append(f'<tr><td>#{c["id"]}</td><td><div class="admin-thumb">{thumb}</div></td><td>{ctx.esc(c["name"])}</td><td><small>{ctx.esc(image or "-")}</small></td><td><a class="btn btn-sm" href="/admin/category?id={c["id"]}">แก้ไข</a></td></tr>')
    return page(ctx,'จัดการหมวดหมู่','<div class="admin-scroll"><table class="admin-table"><tr><th>ID</th><th>รูป</th><th>ชื่อหมวดหมู่</th><th>ลิงก์รูป</th><th>จัดการ</th></tr>'+''.join(parts)+'</table></div>')

def category_form(ctx):
    denied=guard(ctx)
    if denied:return denied
    cid=ctx.to_int(ctx.q.get('id'))
    c=ctx.db.execute('SELECT * FROM categories WHERE id=?',(cid,)).fetchone() if cid else None
    if not c:return ctx.not_found()
    image=(c['image'] or '').strip()
    preview=''
    if image.startswith(('http://','https://','/static/')):
        preview=f'<div class="admin-category-preview"><img src="{ctx.esc(image)}" alt="{ctx.esc(c["name"])}"></div>'
    body=(
        '<div class="admin-form">'+preview+
        f'<form class="form" method="post" action="/admin/category/save">'
        f'<input type="hidden" name="csrf" value="{csrf(ctx)}"><input type="hidden" name="id" value="{c["id"]}">'
        f'<label>ชื่อหมวดหมู่<input value="{ctx.esc(c["name"])}" disabled></label>'
        f'<label>ลิงก์รูปภาพหมวดหมู่ (https:// หรือ /static/)<input name="image" maxlength="1000" value="{ctx.esc(image)}" required></label>'
        '<p class="muted">ตัวอย่าง: /static/categories/boots.svg หรือ https://example.com/image.jpg</p>'
        '<button class="btn">บันทึกหมวดหมู่</button></form></div>'
    )
    return page(ctx,'แก้ไขหมวดหมู่',body)

def category_save(ctx):
    if not valid_post(ctx):return ctx.page('Access denied','<div class="container center">ไม่อนุญาตให้ทำรายการ</div>',403)
    cid=ctx.to_int(ctx.f.get('id'))
    image=ctx.f.get('image','').strip()
    if not cid:return ctx.redirect('/admin/categories','ไม่พบหมวดหมู่',True)
    if image and not image.startswith(('https://','http://','/static/')):
        return ctx.redirect('/admin/category?id='+str(cid),'URL รูปภาพไม่ถูกต้อง',True)
    if not ctx.db.execute('SELECT 1 FROM categories WHERE id=?',(cid,)).fetchone():
        return ctx.not_found()
    ctx.db.execute('UPDATE categories SET image=? WHERE id=?',(image,cid));ctx.db.commit()
    return ctx.redirect('/admin/categories','บันทึกรูปหมวดหมู่แล้ว')

def products(ctx):
    denied=guard(ctx)
    if denied:return denied
    rows=ctx.db.execute(PRODUCT_SQL+' ORDER BY p.id DESC').fetchall()
    items=''.join(f'<tr><td>#{p["id"]}</td><td>{ctx.esc(p["name"])}</td><td>{ctx.esc(p["brand"])}</td><td>{ctx.baht(p["price"])}</td><td>{p["stock"]}</td><td>{"เปิดขาย" if p["is_active"] else "ซ่อนแล้ว"}</td><td><a class="btn btn-sm" href="/admin/product?id={p["id"]}">แก้ไข</a> <form method="post" action="/admin/product/toggle" style="display:inline" onsubmit="return confirm(\'ยืนยันเปลี่ยนสถานะสินค้า?\')"><input type="hidden" name="csrf" value="{csrf(ctx)}"><input type="hidden" name="id" value="{p["id"]}"><button class="btn btn-sm btn-outline" type="submit">{"ลบออกจากหน้าร้าน" if p["is_active"] else "นำกลับมาขาย"}</button></form></td></tr>' for p in rows)
    return page(ctx,'จัดการสินค้า','<p><a class="btn" href="/admin/product">+ เพิ่มสินค้า</a> <a class="btn btn-outline" href="/admin">กลับ Dashboard</a></p><div class="admin-scroll"><table class="admin-table"><tr><th>ID</th><th>สินค้า</th><th>แบรนด์</th><th>ราคา</th><th>คงเหลือ</th><th>สถานะ</th><th>จัดการ</th></tr>'+items+'</table></div>')


def product_form(ctx):
    denied=guard(ctx)
    if denied:return denied
    pid=ctx.to_int(ctx.q.get('id'))
    p=ctx.db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone() if pid else None
    if pid and not p:return ctx.not_found()
    def field(k):return ctx.esc(p[k]) if p else ''
    def choices(table,selected):
        return ''.join(f'<option value="{x["id"]}"{" selected" if x["id"]==selected else ""}>{ctx.esc(x["name"])}</option>' for x in ctx.db.execute('SELECT id,name FROM '+table+' ORDER BY id'))
    size_lines='\n'.join(r['size_name'] for r in ctx.db.execute('SELECT size_name FROM product_sizes WHERE product_id=? ORDER BY sort_order,id',(pid or 0,)))
    colors='\n'.join(f"{r['name']} | {r['hex_code']}" for r in ctx.db.execute('SELECT name,hex_code FROM product_colors WHERE product_id=? ORDER BY id',(pid or 0,)))
    extra_images='\n'.join(r['image_url'] for r in ctx.db.execute('SELECT image_url FROM product_images WHERE product_id=? ORDER BY sort_order,id',(pid or 0,)))
    body=f'''<form class="form" method="post" action="/admin/product/save" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf(ctx)}"><input type="hidden" name="id" value="{pid or ''}">
<label>ชื่อสินค้า<input name="name" maxlength="150" value="{field('name')}" required></label>
<label>แบรนด์<select name="brand_id" required>{choices('brands',p['brand_id'] if p else 0)}</select></label>
<label>หมวดหมู่<select name="category_id" required>{choices('categories',p['category_id'] if p else 0)}</select></label>
<label>ราคา (บาท)<input type="number" name="price" step="0.01" min="0" max="100000000" value="{field('price') or 0}" required></label>
<label>จำนวนคงเหลือ<input type="number" name="stock" min="0" max="10000000" value="{field('stock') if p else 0}" required></label>
<label>ลิงก์รูปภาพหลัก (https:// หรือ /static/)<input name="image" maxlength="1000" value="{field('image')}"></label>
<label>อัปโหลดรูปสินค้า (เลือกได้หลายรูป PNG, JPG, WebP; ไม่เกิน 4 MB ต่อรูป)<input type="file" name="product_photos" accept="image/png,image/jpeg,image/webp" multiple></label>
<p class="muted">รูปที่อัปโหลดจะเก็บไว้ใน static/uploads/products และคงอยู่เมื่อกลับมาแก้สินค้าอีกครั้ง การปล่อยช่องเลือกรูปว่างจะไม่ลบรูปเดิม</p>
<label>รูปตัวอย่างเพิ่มเติม (1 ลิงก์ต่อ 1 บรรทัด)<textarea name="extra_images" rows="6" maxlength="8000" placeholder="https://example.com/front.jpg&#10;https://example.com/side.jpg&#10;/static/products/demo-1.jpg">{ctx.esc(extra_images)}</textarea></label><p class="muted">ระบบจะแสดงรูปหลักร่วมกับรูปเพิ่มเติมเป็นแกลเลอรีสินค้า สูงสุด 12 รูปเพิ่มเติม</p>
<label>คำอธิบาย<textarea name="description" maxlength="5000">{field('description')}</textarea></label>
<div class="color-editor"><h3>เพิ่มสีสินค้าเอง</h3><p class="muted">เลือกสีจากจานสี หรือระบุรหัส HEX ใดก็ได้ แล้วกดเพิ่มลงรายการ</p>
<div class="color-editor-row"><label>ชื่อสี<input id="new-color-name" type="text" maxlength="50" placeholder="เช่น ฟ้าอ่อน"></label>
<label>จานสี<input id="new-color-picker" type="color" value="#3B82F6" aria-label="เลือกสี"></label>
<label>รหัส HEX<input id="new-color-hex" type="text" maxlength="7" value="#3B82F6" placeholder="#RRGGBB" pattern="#[a-fA-F0-9]{{6}}"></label>
<button type="button" class="btn btn-sm" id="add-product-color">+ เพิ่มสี</button></div>
<p id="color-editor-message" class="muted" role="status"></p></div>
<label>ไซส์/ขนาดที่มีจำหน่าย (1 ไซส์ต่อบรรทัด)<textarea name="sizes" rows="7" maxlength="1500" placeholder="EU 39&#10;EU 40&#10;EU 41">{ctx.esc(size_lines)}</textarea></label><p class="muted">ถ้ามีไซส์ ลูกค้าต้องเลือกไซส์ก่อนซื้อ (เช่น EU 39–45 / S–XXL / เบอร์ 5 / One Size)</p>
<label>สีที่มีจำหน่าย (แก้ไขเองได้ 1 สีต่อบรรทัด: ชื่อสี | #รหัสสี)<textarea id="product-color-lines" name="colors" rows="5" maxlength="2000" placeholder="ดำ | #000000&#10;ขาว | #FFFFFF">{ctx.esc(colors)}</textarea></label><p class="muted">รองรับ HEX 6 หลักทุกสี สูงสุด 30 สีต่อสินค้า หากไม่ระบุสี ลูกค้าจะซื้อสินค้าโดยไม่ต้องเลือกสี</p>
<script src="/static/admin_colors.js" defer></script>
<div class="admin-shortcuts"><button class="btn">บันทึกสินค้า</button><a class="btn btn-outline" href="/admin/products">ยกเลิก</a><a class="btn btn-outline" href="/admin">Dashboard</a></div></form>'''
    return page(ctx,'แก้ไขสินค้า' if p else 'เพิ่มสินค้า','<div class="admin-form">'+body+'</div>')

def product_save(ctx):
    if not valid_post(ctx):return ctx.page('Access denied','<div class="container center">ไม่อนุญาตให้ทำรายการ</div>',403)
    f=ctx.f; pid=ctx.to_int(f.get('id'));name=f.get('name','').strip(); image=f.get('image','').strip()
    try:
        price=float(f.get('price',''));stock=int(f.get('stock','')); brand=int(f.get('brand_id',''));cat=int(f.get('category_id',''))
    except (ValueError,TypeError):return ctx.redirect('/admin/products','กรอกข้อมูลตัวเลขให้ถูกต้อง',True)
    if not name or len(name)>150 or not math.isfinite(price) or price<0 or price>100000000 or not (0<=stock<=10000000) or len(image)>1000:
        return ctx.redirect('/admin/products','ข้อมูลสินค้าไม่ถูกต้อง',True)
    if image and not image.startswith(('https://','http://','/static/')):return ctx.redirect('/admin/products','URL รูปภาพหลักไม่ถูกต้อง',True)
    if not ctx.db.execute('SELECT 1 FROM brands WHERE id=?',(brand,)).fetchone() or not ctx.db.execute('SELECT 1 FROM categories WHERE id=?',(cat,)).fetchone():
        return ctx.redirect('/admin/products','แบรนด์หรือหมวดหมู่ไม่ถูกต้อง',True)
    import re
    extra_images=[];seen_images=set()
    for raw in f.get('extra_images','').splitlines():
        url=raw.strip()
        if not url:continue
        if len(url)>1000 or not url.startswith(('https://','http://','/static/')):
            return ctx.redirect('/admin/products','ลิงก์รูปตัวอย่างเพิ่มเติมไม่ถูกต้อง',True)
        key=url.casefold()
        if key in seen_images:continue
        seen_images.add(key)
        extra_images.append(url)
    if len(extra_images)>12:return ctx.redirect('/admin/products','เพิ่มรูปตัวอย่างได้สูงสุด 12 รูปต่อสินค้า',True)
    import secrets
    from pathlib import Path
    incoming=f.get('_product_photos',[])
    if len(incoming)>12 or any(len(blob)>4_000_000 for blob in incoming):
        return ctx.redirect('/admin/products','อัปโหลดได้สูงสุด 12 รูป ขนาดไม่เกิน 4 MB ต่อรูป',True)
    formats=[]
    for blob in incoming:
        if blob.startswith(b'\x89PNG\r\n\x1a\n'):ext='.png'
        elif blob.startswith(b'\xff\xd8\xff'):ext='.jpg'
        elif blob[:4]==b'RIFF' and blob[8:12]==b'WEBP':ext='.webp'
        else:return ctx.redirect('/admin/products','ไฟล์รูปต้องเป็น PNG JPG หรือ WebP',True)
        formats.append(ext)
    existing_count=ctx.db.execute('SELECT COUNT(*) FROM product_images WHERE product_id=?',(pid,)).fetchone()[0] if pid else 0
    if max(len(extra_images), existing_count if not f.get('extra_images','').strip() else 0)+len(incoming)>12:
        return ctx.redirect('/admin/products','มีรูปเพิ่มเติมเกิน 12 รูป กรุณาลบบางรายการก่อน',True)
    size_values=[];size_seen=set()
    for line in f.get('sizes','').splitlines():
        size=line.strip()
        if not size:continue
        if len(size)>35 or any(ord(ch)<32 for ch in size) or '<' in size or '>' in size:
            return ctx.redirect('/admin/products','ข้อมูลไซส์ไม่ถูกต้อง',True)
        if size.casefold() in size_seen:return ctx.redirect('/admin/products','ไซส์ซ้ำกัน',True)
        size_seen.add(size.casefold());size_values.append(size)
    if len(size_values)>40:return ctx.redirect('/admin/products','เพิ่มได้สูงสุด 40 ไซส์ต่อสินค้า',True)
    colors=[];names=set()
    for line in f.get('colors','').strip().splitlines():
        if not line.strip():continue
        parts=[v.strip() for v in line.split('|')]
        if len(parts)!=2 or not parts[0] or len(parts[0])>50 or not re.fullmatch(r'#[0-9a-fA-F]{6}',parts[1]):
            return ctx.redirect('/admin/products','รูปแบบสีไม่ถูกต้อง กรุณาใช้ ชื่อสี | #AABBCC',True)
        if parts[0].casefold() in names:return ctx.redirect('/admin/products','ชื่อสีซ้ำกัน',True)
        names.add(parts[0].casefold());colors.append((parts[0],parts[1].upper()))
    if len(colors)>30:return ctx.redirect('/admin/products','เพิ่มได้สูงสุด 30 สีต่อสินค้า',True)
    if pid and not image:
        old_product=ctx.db.execute('SELECT image FROM products WHERE id=?',(pid,)).fetchone()
        if old_product:
            image=old_product['image'] or ''
    data=(name,brand,cat,price,stock,image,f.get('description','')[:5000])
    if pid:
        if not ctx.db.execute('SELECT 1 FROM products WHERE id=?',(pid,)).fetchone():return ctx.not_found()
        ctx.db.execute('UPDATE products SET name=?,brand_id=?,category_id=?,price=?,stock=?,image=?,description=? WHERE id=?',data+(pid,))
    else:
        pid=ctx.db.execute('INSERT INTO products(name,brand_id,category_id,price,stock,image,description) VALUES(?,?,?,?,?,?,?)',data).lastrowid
    ctx.db.execute('DELETE FROM product_colors WHERE product_id=?',(pid,))
    ctx.db.executemany('INSERT INTO product_colors(product_id,name,hex_code) VALUES(?,?,?)',[(pid,n,h) for n,h in colors])
    upload_dir=Path(__file__).with_name('static')/'uploads'/'products'
    saved=[]
    if incoming:
        upload_dir.mkdir(parents=True,exist_ok=True)
        for blob,ext in zip(incoming,formats):
            filename=secrets.token_hex(16)+ext
            (upload_dir/filename).write_bytes(blob)
            saved.append('/static/uploads/products/'+filename)
    # Do not overwrite existing product gallery with an empty form field.
    if pid and not f.get('extra_images','').strip():
        extra_images=[r['image_url'] for r in ctx.db.execute('SELECT image_url FROM product_images WHERE product_id=? ORDER BY sort_order,id',(pid,))]
    all_images=list(dict.fromkeys(extra_images+saved))
    if len(all_images)>12:
        return ctx.redirect('/admin/products','จำนวนรูปเพิ่มเติมเกิน 12 รูป',True)
    if not image and all_images:
        image=all_images.pop(0)
        ctx.db.execute('UPDATE products SET image=? WHERE id=?',(image,pid))
    ctx.db.execute('DELETE FROM product_images WHERE product_id=?',(pid,))
    ctx.db.executemany('INSERT INTO product_images(product_id,image_url,sort_order) VALUES(?,?,?)',[(pid,url,idx) for idx,url in enumerate(all_images,start=1)])
    ctx.db.execute('DELETE FROM product_sizes WHERE product_id=?',(pid,))
    ctx.db.executemany('INSERT INTO product_sizes(product_id,size_name,sort_order) VALUES(?,?,?)',[(pid,size,idx) for idx,size in enumerate(size_values)])
    ctx.db.commit();return ctx.redirect('/admin/products','บันทึกสินค้าแล้ว')


def orders(ctx):
    denied=guard(ctx)
    if denied:return denied
    rows=ctx.db.execute('SELECT o.*,u.name,u.email FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.id DESC').fetchall()
    parts=[]
    for o in rows:
        options=''.join(f'<option value="{s}"{" selected" if o["status"]==s else ""}>{s}</option>' for s in STATUSES)
        parts.append(f'''<tr><td>#{o['id']}</td><td>{ctx.esc(o['name'])}<small>{ctx.esc(o['email'])}</small></td><td>{ctx.baht(o['total'])}</td><td>{ctx.esc(o['payment_method'])}<small>{ctx.esc(o['address'])}</small></td><td><form method="post" action="/admin/order/status" class="admin-inline"><input type="hidden" name="csrf" value="{csrf(ctx)}"><input type="hidden" name="id" value="{o['id']}"><select name="status">{options}</select><button class="btn btn-sm">บันทึก</button></form></td></tr>''')
    return page(ctx,'จัดการคำสั่งซื้อ','<p class="muted">สถานะเป็นข้อมูลสำหรับระบบสาธิต ไม่ยืนยันการรับเงินจริง</p><div class="admin-scroll"><table class="admin-table"><tr><th>ID</th><th>ลูกค้า</th><th>ยอด</th><th>วิธีชำระ / ที่อยู่</th><th>สถานะ</th></tr>'+''.join(parts)+'</table></div>')

def order_status(ctx):
    if not valid_post(ctx):return ctx.page('Access denied','<div class="container center">ไม่อนุญาตให้ทำรายการ</div>',403)
    oid=ctx.to_int(ctx.f.get('id')); status=ctx.f.get('status','')
    if status not in STATUSES or not oid:return ctx.redirect('/admin/orders','สถานะไม่ถูกต้อง',True)
    pay=ctx.db.execute('SELECT payment_status,payment_method FROM orders WHERE id=?',(oid,)).fetchone()
    if pay and status in ('Shipped','Completed') and pay['payment_status']!='paid':
        return ctx.redirect('/admin/orders','ต้องตรวจสอบการชำระเงินก่อนจัดส่ง',True)
    old=ctx.db.execute('SELECT status FROM orders WHERE id=?',(oid,)).fetchone()
    if not old:return ctx.not_found()
    # Cancellation returns stock once; restoring from Cancelled reserves it again, only if enough stock.
    if old['status']!='Cancelled' and status=='Cancelled':
        for i in ctx.db.execute('SELECT product_id,quantity FROM order_items WHERE order_id=?',(oid,)):
            ctx.db.execute('UPDATE products SET stock=stock+? WHERE id=?',(i['quantity'],i['product_id']))
    elif old['status']=='Cancelled' and status!='Cancelled':
        items=ctx.db.execute('SELECT product_id,quantity FROM order_items WHERE order_id=?',(oid,)).fetchall()
        from collections import defaultdict
        needed=defaultdict(int)
        for i in items:needed[i['product_id']]+=i['quantity']
        if any(ctx.db.execute('SELECT stock FROM products WHERE id=?',(pid,)).fetchone()['stock']<qty for pid,qty in needed.items()):
            return ctx.redirect('/admin/orders','สินค้าไม่เพียงพอสำหรับเปิดคำสั่งซื้ออีกครั้ง',True)
        for i in items:ctx.db.execute('UPDATE products SET stock=stock-? WHERE id=?',(i['quantity'],i['product_id']))
    ctx.db.execute('UPDATE orders SET status=? WHERE id=?',(status,oid));ctx.db.commit()
    return ctx.redirect('/admin/orders','อัปเดตสถานะแล้ว')

def product_toggle(ctx):
    if not valid_post(ctx):
        return ctx.page('Access denied','<div class="container center">ไม่อนุญาตให้ทำรายการ</div>',403)
    pid=ctx.to_int(ctx.f.get('id'))
    if not pid or pid<=0:return ctx.not_found()
    product=ctx.db.execute('SELECT is_active FROM products WHERE id=?',(pid,)).fetchone()
    if not product:return ctx.not_found()
    active=0 if product['is_active'] else 1
    ctx.db.execute('UPDATE products SET is_active=? WHERE id=?',(active,pid))
    if not active:
        ctx.db.execute('DELETE FROM cart WHERE product_id=?',(pid,))
    ctx.db.commit()
    return ctx.redirect('/admin/products','นำสินค้ากลับมาแสดงแล้ว' if active else 'ซ่อนสินค้าแล้ว (ข้อมูลและประวัติยังอยู่)')

ROUTES={('GET','/admin/login'):login_page,('POST','/admin/login'):login,('GET','/admin'):dashboard,('GET','/admin/products'):products,('GET','/admin/categories'):categories,('GET','/admin/category'):category_form,('POST','/admin/category/save'):category_save,('GET','/admin/product'):product_form,('POST','/admin/product/save'):product_save,('POST','/admin/product/toggle'):product_toggle,('GET','/admin/orders'):orders,('POST','/admin/order/status'):order_status}

# Payment review is an independent workflow from shipping status.
from payment import payment_name, method_name

def payments(ctx):
    denied=guard(ctx)
    if denied:return denied
    q=ctx.q.get('q','').strip()
    sql='SELECT o.*,u.name,u.email FROM orders o JOIN users u ON u.id=o.user_id'
    args=[]
    if q:
        if not q.isdigit():return page(ctx,'ตรวจสอบการชำระเงิน','<p>กรุณาระบุเลขที่คำสั่งซื้อเป็นตัวเลข</p>')
        sql+=' WHERE o.id=?';args.append(int(q))
    sql+=' ORDER BY CASE WHEN o.payment_status="review" THEN 0 ELSE 1 END,o.id DESC'
    records=ctx.db.execute(sql,args).fetchall()
    out=f'<form method="get" action="/admin/payments" class="form"><label>ค้นหาเลขคำสั่งซื้อ<input name="q" value="{ctx.esc(q)}" placeholder="เช่น 12"></label><button class="btn btn-sm">ค้นหา</button></form>'
    for o in records:
        proof=f'<a href="/payment/slip?id={o["id"]}" target="_blank" rel="noopener">เปิดสลิป</a>' if o['proof_file'] else 'ยังไม่มีสลิป'
        review=''
        if o['payment_status']=='review':
            review=f'''<form class="form" action="/admin/payment/review" method="post"><input type="hidden" name="csrf" value="{csrf(ctx)}"><input type="hidden" name="id" value="{o['id']}"><label>หมายเหตุถึงลูกค้า<input name="note" maxlength="500" placeholder="เช่น ยอดไม่ตรง / สลิปไม่ชัด"></label><div class="admin-pay-actions"><button class="btn btn-sm" name="decision" value="paid">ยืนยันชำระแล้ว</button><button class="btn btn-sm btn-outline" name="decision" value="failed">ปฏิเสธสลิป</button></div></form>'''
        if o['payment_status']=='paid':
            review+=f'''<form method="post" action="/admin/payment/review"><input type="hidden" name="csrf" value="{csrf(ctx)}"><input type="hidden" name="id" value="{o['id']}"><label>หมายเหตุคืนเงิน<input name="note" maxlength="500"></label><button class="btn btn-sm btn-outline" name="decision" value="refunded">บันทึกการคืนเงิน (หลังคืนเงินจริงแล้ว)</button></form>'''
        receipt_link=f'<p><a href="/receipt?id={o["id"]}" target="_blank" rel="noopener">เปิดใบเสร็จรับเงิน</a></p>' if o['payment_status']=='paid' and o['status']!='Cancelled' else ''
        reviewer=''
        if o['payment_reviewed_by']:
            admin_user=ctx.db.execute('SELECT email FROM users WHERE id=?',(o['payment_reviewed_by'],)).fetchone()
            reviewer=f'<p class="muted">ผู้ตรวจสอบ: {ctx.esc(admin_user["email"] if admin_user else str(o["payment_reviewed_by"]))} · {ctx.esc(o["payment_reviewed_at"])}</p>'
        out+=f'''<div class="admin-payment"><h3>#{o['id']} · {ctx.esc(o['name'])} · {ctx.baht(o['total'])}</h3><p>{ctx.esc(method_name(o['payment_method']))} | สถานะชำระเงิน: <b>{ctx.esc(payment_name(o['payment_status']))}</b></p><p>แจ้งชำระ: {ctx.esc(o['payment_submitted_at'] or '-')} · {proof}</p>{reviewer}{receipt_link}{review}</div>'''
    return page(ctx,'ตรวจสอบการชำระเงิน',out)

def payment_review(ctx):
    if not valid_post(ctx):return ctx.page('Access denied','<div class="container center">ไม่อนุญาต</div>',403)
    oid=ctx.to_int(ctx.f.get('id'));decision=ctx.f.get('decision');note=ctx.f.get('note','').strip()[:500]
    if decision not in ('paid','failed','refunded') or not oid:return ctx.redirect('/admin/payments','คำขอไม่ถูกต้อง',True)
    o=ctx.db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    if not o:return ctx.not_found()
    if o['status']=='Cancelled' and decision=='paid':return ctx.redirect('/admin/payments','คำสั่งซื้อนี้ยกเลิกแล้ว',True)
    allowed=((o['payment_status']=='review' and decision in ('paid','failed')) or
             (o['payment_status']=='paid' and decision=='refunded'))
    if not allowed:return ctx.redirect('/admin/payments','สถานะปัจจุบันไม่อนุญาตให้ดำเนินการ',True)
    ctx.db.execute('UPDATE orders SET payment_status=?,payment_reviewed_by=?,payment_reviewed_at=CURRENT_TIMESTAMP,payment_note=? WHERE id=?',(decision,ctx.user['id'],note,oid))
    ctx.db.commit()
    return ctx.redirect('/admin/payments?q='+str(oid),'อัปเดตสถานะชำระเงินแล้ว')

ROUTES.update({('GET','/admin/payments'):payments,('POST','/admin/payment/review'):payment_review})

_original_nav=nav
def nav():
    return _original_nav().replace('<a href="/admin/orders">', '<a href="/admin/payments">ตรวจสอบชำระเงิน</a><a href="/admin/orders">')


# Payment account settings: limited to authenticated admins; uploaded QR is stored outside /static.
def payment_settings_page(ctx):
    denied=guard(ctx)
    if denied:return denied
    from payment import setting
    def f(key):return ctx.esc(setting(ctx,key))
    picture='<p><img class="promptpay-qr" src="/payment/store-qr" alt="QR ปัจจุบัน"></p>' if setting(ctx,'qr_filename') else '<p class="muted">ยังไม่ได้อัปโหลดรูป QR</p>'
    body=(f'<div class="admin-form"><p class="muted">บันทึกข้อมูลบัญชีเจ้าของร้านและอัปโหลดรูป QR จากเครื่องได้ รูป QR แบบอัปโหลดไม่ระบุยอดอัตโนมัติ</p>'
          f'<form class="form" method="post" action="/admin/payment-settings" enctype="multipart/form-data">'
          f'<input type="hidden" name="csrf" value="{csrf(ctx)}">'
          f'<label>ชื่อธนาคาร<input name="bank_name" maxlength="100" value="{f("bank_name")}"></label>'
          f'<label>ชื่อบัญชี<input name="account_name" maxlength="120" value="{f("account_name")}"></label>'
          f'<label>เลขบัญชีธนาคาร<input name="account_number" maxlength="30" value="{f("account_number")}"></label>'
          f'<label>หมายเลข PromptPay (มือถือ 10 หลัก / เลข 13 หลัก)<input name="promptpay_id" maxlength="20" value="{f("promptpay_id")}"></label>'
          f'{picture}<label>เปลี่ยนภาพ QR (JPG PNG WebP ไม่เกิน 4 MB)<input type="file" name="store_qr" accept="image/png,image/jpeg,image/webp"></label>'
          '<label class="checkbox"><input type="checkbox" name="remove_qr" value="1">ลบรูป QR ที่อัปโหลด (กลับไปใช้ QR ที่สร้างจากหมายเลข PromptPay)</label>'
          '<button class="btn">บันทึกการตั้งค่า</button></form></div>')
    return page(ctx,'ตั้งค่าช่องทางรับเงิน',body)

def payment_settings_save(ctx):
    if not valid_post(ctx):return ctx.page('Access denied','<div class="container center">ไม่อนุญาต</div>',403)
    import re,secrets
    from payment import setting, STORE_QR_DIR, MAX_UPLOAD, promptpay_payload
    fields={key:ctx.f.get(key,'').strip() for key in ('bank_name','account_name','account_number','promptpay_id')}
    if any(len(fields[k])>limit for k,limit in (('bank_name',100),('account_name',120),('account_number',30),('promptpay_id',20))):return ctx.redirect('/admin/payment-settings','ข้อมูลยาวเกินกำหนด',True)
    if fields['account_number'] and not re.fullmatch(r'[0-9 -]{6,30}',fields['account_number']):return ctx.redirect('/admin/payment-settings','เลขบัญชีต้องเป็นตัวเลข',True)
    if fields['promptpay_id']:
        try:promptpay_payload(fields['promptpay_id'],1)
        except ValueError:return ctx.redirect('/admin/payment-settings','หมายเลข PromptPay ไม่ถูกต้อง',True)
    blob=ctx.f.get('_store_qr_bytes',b'')
    ext=''
    if blob:
        if len(blob)>MAX_UPLOAD:return ctx.redirect('/admin/payment-settings','รูป QR ใหญ่เกิน 4 MB',True)
        if blob.startswith(b'\x89PNG\r\n\x1a\n'):ext='.png'
        elif blob.startswith(b'\xff\xd8\xff'):ext='.jpg'
        elif blob[:4]==b'RIFF' and blob[8:12]==b'WEBP':ext='.webp'
        else:return ctx.redirect('/admin/payment-settings','รูป QR ต้องเป็น PNG JPG หรือ WebP',True)
    old=setting(ctx,'qr_filename')
    new=None
    if ext:
        STORE_QR_DIR.mkdir(mode=0o700,exist_ok=True)
        new=secrets.token_hex(20)+ext
        with open(STORE_QR_DIR/new,'xb') as file:file.write(blob)
    for key,value in fields.items():ctx.db.execute('INSERT INTO payment_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
    if new or ctx.f.get('remove_qr')=='1':
        ctx.db.execute('INSERT INTO payment_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('qr_filename',new or ''))
    ctx.db.commit()
    if old and (new or ctx.f.get('remove_qr')=='1'):
        try:(STORE_QR_DIR/old).unlink(missing_ok=True)
        except OSError:pass
    return ctx.redirect('/admin/payment-settings','บันทึกช่องทางรับเงินแล้ว')

ROUTES.update({('GET','/admin/payment-settings'):payment_settings_page,('POST','/admin/payment-settings'):payment_settings_save})
