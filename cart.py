from database import PRODUCT_SQL
def rows(ctx):
    if not ctx.user:return []
    return ctx.db.execute('SELECT p.id,p.name,p.price,p.stock,p.is_active,c.quantity,c.color_name,c.size_name FROM cart c JOIN products p ON p.id=c.product_id WHERE c.user_id=? ORDER BY p.id,c.color_name,c.size_name',(ctx.user['id'],)).fetchall()
def view(ctx):
    if not ctx.user:return ctx.need_login('/cart')
    items=rows(ctx);out='';total=0
    for p in items:
        qty=p['quantity'];cost=qty*p['price'];total+=cost
        color=p['color_name'] or '';size=p['size_name'] or ''
        out+=f'''<div class="cart-line"><div><b>{ctx.esc(p['name'])}</b><p>{ctx.baht(p['price'])} / ชิ้น · สี: {ctx.esc(color or 'ไม่ระบุ')} · ไซส์: {ctx.esc(size or 'ไม่ระบุ')}</p></div><form method="post" action="/cart/update"><input type="hidden" name="product_id" value="{p['id']}"><input type="hidden" name="color_name" value="{ctx.esc(color)}"><input type="hidden" name="size_name" value="{ctx.esc(size)}"><input type="number" name="quantity" min="0" max="{p['stock']}" value="{qty}"><button class="btn btn-sm">อัปเดต (0 = ลบ)</button></form><strong>{ctx.baht(cost)}</strong></div>'''
    if not items:out='<div class="empty">ตะกร้าว่าง <a href="/products">เลือกซื้อสินค้า</a></div>'
    else:out+=f'<div class="summary"><a class="btn btn-outline" href="/products">← เลือกสินค้าเพิ่ม</a><span>รวมทั้งหมด <strong>{ctx.baht(total)}</strong></span><a class="btn" href="/checkout">เลือกวิธีชำระเงิน →</a></div>'
    return ctx.page('ตะกร้าสินค้า',f'<section class="container section"><h1>🛒 ตะกร้าของฉัน</h1>{out}</section>')
def add(ctx):
    if not ctx.user:return ctx.need_login('/products')
    pid=ctx.to_int(ctx.f.get('product_id'));qty=ctx.to_int(ctx.f.get('quantity'),0)
    if not pid or not qty or qty<1:return ctx.redirect('/cart','จำนวนสินค้าไม่ถูกต้อง',True)
    p=ctx.db.execute('SELECT stock FROM products WHERE id=? AND is_active=1',(pid,)).fetchone()
    if not p:return ctx.redirect('/products','ไม่พบสินค้า',True)
    options=ctx.db.execute('SELECT name FROM product_colors WHERE product_id=?',(pid,)).fetchall()
    color=ctx.f.get('color_name','').strip()
    if (options and color not in [o['name'] for o in options]) or (not options and color):return ctx.redirect('/product?id='+str(pid),'กรุณาเลือกสีที่มีจำหน่าย',True)
    size_options=[o['size_name'] for o in ctx.db.execute('SELECT size_name FROM product_sizes WHERE product_id=?',(pid,))]
    size=ctx.f.get('size_name','').strip()
    if (size_options and size not in size_options) or (not size_options and size):return ctx.redirect('/product?id='+str(pid),'กรุณาเลือกไซส์ที่มีจำหน่าย',True)
    total_selected=ctx.db.execute('SELECT COALESCE(SUM(quantity),0) FROM cart WHERE product_id=? AND user_id=?',(pid,ctx.user['id'])).fetchone()[0]
    if qty+total_selected>p['stock']:return ctx.redirect('/cart','สินค้าในสต็อกไม่พอ',True)
    ctx.db.execute('INSERT INTO cart(user_id,product_id,color_name,size_name,quantity) VALUES(?,?,?,?,?) ON CONFLICT(user_id,product_id,color_name,size_name) DO UPDATE SET quantity=quantity+excluded.quantity',(ctx.user['id'],pid,color,size,qty));ctx.db.commit()
    return ctx.redirect('/product?id='+str(pid),'เพิ่มสินค้าลงตะกร้าแล้ว สามารถเลือกสินค้าอื่นต่อ หรือไปที่ตะกร้าเพื่อชำระเงิน')
def update(ctx):
    if not ctx.user:return ctx.need_login('/cart')
    pid=ctx.to_int(ctx.f.get('product_id'));qty=ctx.to_int(ctx.f.get('quantity'));color=ctx.f.get('color_name','');size=ctx.f.get('size_name','')
    if not pid or qty is None or qty<0:return ctx.redirect('/cart','จำนวนไม่ถูกต้อง',True)
    p=ctx.db.execute('SELECT stock FROM products WHERE id=? AND is_active=1',(pid,)).fetchone()
    other=ctx.db.execute('SELECT COALESCE(SUM(quantity),0) FROM cart WHERE product_id=? AND user_id=? AND NOT (color_name=? AND size_name=?)',(pid,ctx.user['id'],color,size)).fetchone()[0]
    if not p or qty+other>p['stock']:return ctx.redirect('/cart','สต็อกไม่เพียงพอ',True)
    if qty==0:ctx.db.execute('DELETE FROM cart WHERE user_id=? AND product_id=? AND color_name=? AND size_name=?',(ctx.user['id'],pid,color,size))
    else:ctx.db.execute('UPDATE cart SET quantity=? WHERE user_id=? AND product_id=? AND color_name=? AND size_name=?',(qty,ctx.user['id'],pid,color,size))
    ctx.db.commit();return ctx.redirect('/cart','อัปเดตตะกร้าแล้ว')
ROUTES={('GET','/cart'):view,('POST','/cart/add'):add,('POST','/cart/update'):update}
