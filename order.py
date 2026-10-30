"""Checkout, order placement and customer order history."""
import os
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
import cart
from payment import csrf, valid_csrf, method_name, payment_name, shipping_name

VAT_RATE = Decimal("0.07")  # VAT 7% รวมอยู่ในราคาขายแล้ว
SHIPPING_COST=60
FREE_SHIPPING_FROM=1500

def totals(items):
    subtotal=round(sum(r['price']*r['quantity'] for r in items),2)
    discount=0.0 # Discounts deliberately disabled until a real promotion rule is configured
    shipping=0 if subtotal>=FREE_SHIPPING_FROM else SHIPPING_COST
    base = Decimal(str(subtotal)) - Decimal(str(discount)) + Decimal(str(shipping))
    vat = (base * VAT_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return subtotal,discount,shipping,float(base)

def vat_breakdown(total):
    """Separate VAT included in the paid amount (inclusive VAT)."""
    gross = Decimal(str(total)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    net = (gross / (Decimal('1') + VAT_RATE)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    vat = gross - net
    return float(net), float(vat)


def stock_ok(items):
    grouped=defaultdict(lambda: {'qty': 0, 'stock': 0, 'price': 0, 'is_active': 1})
    for r in items:
        p=grouped[r['id']]
        p['qty']+=r['quantity'];p['stock']=r['stock'];p['price']=r['price'];p['is_active']=r['is_active']
    return all(x['is_active'] and x['price']>0 and x['qty']<=x['stock'] for x in grouped.values())

def checkout(ctx):
    if not ctx.user:return ctx.need_login('/checkout')
    items=cart.rows(ctx)
    if not items:return ctx.redirect('/cart','โปรดเลือกสินค้าก่อน',True)
    if not stock_ok(items):return ctx.redirect('/cart','มีสินค้าที่ยังไม่กำหนดราคาหรือสต็อกไม่พอ',True)
    subtotal,discount,shipping,total=totals(items)
    net, vat = vat_breakdown(total)
    lines=''.join(f'<div class="cart-line"><span><b>{ctx.esc(r["name"])} × {r["quantity"]}</b><small> สี: {ctx.esc(r["color_name"] or "ไม่ระบุ")} · ไซส์: {ctx.esc(r["size_name"] or "ไม่ระบุ")} · {ctx.baht(r["price"])} / ชิ้น</small></span><strong>{ctx.baht(r["price"]*r["quantity"])}</strong></div>' for r in items)
    methods=''.join(f'<label class="payment-choice"><input type="radio" name="payment_method" value="{value}" {"checked" if value=="promptpay" else ""}><span>{label}</span></label>' for value,label in [('promptpay','QR PromptPay (แจ้งสลิปหลังโอน)'),('transfer','โอนเงินผ่านธนาคาร (แจ้งสลิปหลังโอน)')])
    body=f'''<section class="container section narrow"><h1>สรุปคำสั่งซื้อ</h1><p class="muted">เลือกซื้อสินค้าต่อได้จนกว่าจะกดยืนยันคำสั่งซื้อ</p><p><a class="btn btn-outline" href="/cart">← กลับไปแก้ไขตะกร้า</a> <a class="btn btn-outline" href="/products">เลือกสินค้าเพิ่ม</a></p>{lines}<div class="cart-line">ยอดสินค้า <strong>{ctx.baht(subtotal)}</strong></div><div class="cart-line">ส่วนลด <strong>-{ctx.baht(discount)}</strong></div><div class="cart-line">ค่าจัดส่ง <strong>{ctx.baht(shipping)}</strong></div><div class="cart-line">ยอดก่อน VAT 7% <strong>{ctx.baht(net)}</strong></div><div class="cart-line">VAT 7% (รวมในราคา) <strong>{ctx.baht(vat)}</strong></div><div class="summary"><span>รวมสุทธิ</span><strong>{ctx.baht(total)}</strong></div><p class="muted">จัดส่งฟรีเมื่อมูลค่าสินค้าตั้งแต่ {ctx.baht(FREE_SHIPPING_FROM)} ขึ้นไป · ยังไม่มีโค้ดส่วนลดที่เปิดใช้</p><form method="post" action="/checkout" class="form checkout-form"><input type="hidden" name="csrf" value="{csrf(ctx)}"><label>ที่อยู่จัดส่ง<textarea name="address" maxlength="1000" required></textarea></label><h2>เลือกวิธีชำระเงิน</h2>{methods}<button class="btn" type="submit">ยืนยันคำสั่งซื้อ {ctx.baht(total)}</button></form><p class="muted">PromptPay/โอนเงินใช้การแนบสลิปและให้ผู้ดูแลตรวจสอบ ไม่ยืนยันการรับเงินอัตโนมัติ</p></section>'''
    return ctx.page('สรุปคำสั่งซื้อ',body)

def submit(ctx):
    if not ctx.user:return ctx.need_login('/cart')
    if not valid_csrf(ctx):return ctx.page('คำขอไม่ถูกต้อง','<section class="container section">คำขอไม่ถูกต้อง</section>',403)
    address=ctx.f.get('address','').strip();method=ctx.f.get('payment_method','')
    if not address or len(address)>1000 or method not in ('transfer','promptpay'):return ctx.redirect('/checkout','ข้อมูลการจัดส่งหรือวิธีชำระเงินไม่ถูกต้อง',True)
    db=ctx.db
    try:
        db.execute('BEGIN IMMEDIATE')
        items=cart.rows(ctx)
        if not items:db.rollback();return ctx.redirect('/cart','ไม่มีสินค้าในตะกร้า',True)
        if not stock_ok(items):db.rollback();return ctx.redirect('/cart','สินค้าไม่เพียงพอหรือยังไม่กำหนดราคา',True)
        subtotal,discount,shipping,total=totals(items)
        net, vat = vat_breakdown(total)
        order=db.execute('INSERT INTO orders(user_id,total,address,payment_method,status,subtotal,discount_amount,shipping_fee,payment_status,vat_rate,vat_amount,net_before_vat) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(ctx.user['id'],total,address,method,'Pending',subtotal,discount,shipping,'pending',0.07,vat,net)).lastrowid
        for r in items:
            db.execute('INSERT INTO order_items(order_id,product_id,quantity,unit_price,color_name,size_name) VALUES(?,?,?,?,?,?)',(order,r['id'],r['quantity'],r['price'],r['color_name'],r['size_name']))
        grouped=defaultdict(int)
        for r in items:grouped[r['id']]+=r['quantity']
        for pid,qty in grouped.items():
            updated=db.execute('UPDATE products SET stock=stock-? WHERE id=? AND stock>=?',(qty,pid,qty))
            if updated.rowcount!=1:raise ValueError('สินค้าในสต็อกไม่เพียงพอ')
        db.execute('DELETE FROM cart WHERE user_id=?',(ctx.user['id'],));db.commit()
    except Exception:db.rollback();raise
    return ctx.redirect('/order?id='+str(order),'บันทึกคำสั่งซื้อแล้ว กรุณาดูรายละเอียดการชำระเงิน')

def orders(ctx):
    if not ctx.user:return ctx.need_login('/orders')
    records=ctx.db.execute('SELECT * FROM orders WHERE user_id=? ORDER BY id DESC',(ctx.user['id'],)).fetchall()
    body=''.join(f'<div class="cart-line"><div><b>คำสั่งซื้อ #{o["id"]}</b><p>{ctx.esc(o["created_at"])} · {ctx.esc(method_name(o["payment_method"]))}</p><p>ชำระเงิน: {ctx.esc(payment_name(o["payment_status"]))} · จัดส่ง: {ctx.esc(shipping_name(o["status"]))}</p><a href="/order?id={o["id"]}">ดูรายละเอียด / แจ้งชำระเงิน →</a> · <a href="/tracking?id={o["id"]}">ติดตามพัสดุ →</a></div><strong>{ctx.baht(o["total"])}</strong></div>' for o in records) or '<p class="empty">ยังไม่มีคำสั่งซื้อ</p>'
    return ctx.page('คำสั่งซื้อ',f'<section class="container section"><h1>คำสั่งซื้อของฉัน</h1>{body}</section>')
ROUTES={('GET','/checkout'):checkout,('POST','/checkout'):submit,('GET','/orders'):orders}
