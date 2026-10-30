"""Printable payment receipt, available only after verified payment.
This is an ordinary payment receipt, not a Thai tax invoice.
"""
from payment import get_order, method_name, setting


def receipt(ctx):
    if not ctx.user:
        return ctx.need_login('/orders')
    oid = ctx.to_int(ctx.q.get('id'))
    if not oid or oid <= 0:
        return ctx.not_found()
    o = get_order(ctx, oid, admin=True)
    if not o or o['payment_status'] != 'paid' or o['status'] == 'Cancelled':
        return ctx.not_found()
    buyer = ctx.db.execute('SELECT name,email FROM users WHERE id=?',(o['user_id'],)).fetchone()
    if not buyer:
        return ctx.not_found()
    items = ctx.db.execute('''
        SELECT oi.quantity, oi.unit_price, oi.color_name, oi.size_name, p.name
        FROM order_items oi JOIN products p ON p.id=oi.product_id
        WHERE oi.order_id=? ORDER BY oi.id
    ''', (oid,)).fetchall()
    rows = ''.join(
        f'<tr><td>{ctx.esc(i["name"])}'
        f'<small>สี: {ctx.esc(i["color_name"] or "ไม่ระบุ")} · ไซส์: {ctx.esc(i["size_name"] or "ไม่ระบุ")}</small></td>'
        f'<td class="number">{i["quantity"]}</td>'
        f'<td class="number">{ctx.baht(i["unit_price"])}</td>'
        f'<td class="number">{ctx.baht(i["quantity"] * i["unit_price"])}</td></tr>'
        for i in items
    )
    shipping = o['shipping_fee'] or 0
    discount = o['discount_amount'] or 0
    subtotal = o['subtotal'] if o['subtotal'] is not None else o['total'] - shipping + discount
    shop = setting(ctx,'account_name') or 'FOOTZONE'
    vat_line = ''
    if o['vat_rate'] is not None and o['vat_amount'] is not None:
        vat_line = (f'<div class="line"><span>ยอดก่อน VAT</span><b>{ctx.baht(o["net_before_vat"])}</b></div>'
                    f'<div class="line"><span>VAT 7% (รวมในราคา)</span><b>{ctx.baht(o["vat_amount"])}</b></div>')
    paid_at = o['payment_reviewed_at'] or 'ไม่ระบุวันที่ยืนยัน'
    number = f'FZ-R-{oid:06d}'
    body = f'''<!doctype html><html lang="th"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>ใบเสร็จรับเงิน {number} | FOOTZONE</title>
    <style>
    *{{box-sizing:border-box}}body{{font-family:Tahoma,Arial,sans-serif;background:#eef1f4;color:#182025;margin:0}}
    .paper{{max-width:850px;margin:36px auto;background:white;padding:42px;box-shadow:0 8px 35px #0001}}
    header{{display:flex;justify-content:space-between;gap:20px;align-items:start;border-bottom:3px solid #2c6d46;padding-bottom:20px}}
    h1{{margin:0;font-size:26px}}h2{{font-size:17px;margin:26px 0 10px}}.brand{{font-size:27px;font-weight:900;letter-spacing:1px}}
    .brand span{{color:#2c9659}}.muted,small{{color:#697680}}.meta{{display:grid;grid-template-columns:1fr 1fr;gap:7px 30px;margin-top:24px}}
    table{{border-collapse:collapse;width:100%;margin-top:12px}}th,td{{padding:12px 8px;border-bottom:1px solid #dde3e8;text-align:left;vertical-align:top}}th{{background:#f1f5f3}}
    td small{{display:block;margin-top:6px}}.number{{text-align:right;white-space:nowrap}}.totals{{margin-left:auto;max-width:340px;margin-top:18px}}
    .line{{display:flex;justify-content:space-between;gap:25px;padding:8px 0}}.grand{{border-top:2px solid #2c6d46;font-size:20px;font-weight:bold;padding-top:15px}}
    .notice{{font-size:12px;margin-top:24px;color:#66727a;line-height:1.6}}.actions{{display:flex;gap:10px;max-width:850px;margin:18px auto}}
    button,a.button{{background:#286b48;border:0;color:#fff;padding:12px 19px;border-radius:6px;font:inherit;cursor:pointer;text-decoration:none}}
    @media(max-width:650px){{.paper{{padding:20px;margin:8px}}header{{display:block}}.meta{{grid-template-columns:1fr}}th,td{{padding:9px 3px;font-size:12px}}}}
    @media print{{@page{{size:A4;margin:12mm}}body{{background:white}}.paper{{max-width:none;margin:0;padding:0;box-shadow:none}}.actions{{display:none}}tr{{break-inside:avoid}}}}
    </style></head><body>
    <div class="actions"><button type="button" onclick="window.print()">พิมพ์ใบเสร็จ / บันทึก PDF</button><a class="button" href="/order?id={oid}">กลับคำสั่งซื้อ</a></div>
    <div class="paper"><header><div><div class="brand">FOOT<span>ZONE</span></div><p class="muted">ผู้รับเงิน: {ctx.esc(shop)}</p></div>
    <div><h1>ใบเสร็จรับเงิน</h1><p>เลขที่ {number}</p><p class="muted">ชำระเงินแล้ว</p></div></header>
    <div class="meta"><div><b>ลูกค้า</b><br>{ctx.esc(buyer['name'])}</div><div><b>อีเมล</b><br>{ctx.esc(buyer['email'])}</div>
    <div><b>เลขที่คำสั่งซื้อ</b><br>#{oid}</div><div><b>วันที่สั่งซื้อ</b><br>{ctx.esc(o['created_at'])}</div>
    <div><b>วันที่ยืนยันชำระเงิน</b><br>{ctx.esc(paid_at)}</div><div><b>วิธีชำระเงิน</b><br>{ctx.esc(method_name(o['payment_method']))}</div>
    <div style="grid-column:1/-1"><b>ที่อยู่จัดส่ง</b><br>{ctx.esc(o['address'])}</div></div>
    <h2>รายการสินค้า</h2><table><thead><tr><th>สินค้า</th><th class="number">จำนวน</th><th class="number">ราคาต่อชิ้น</th><th class="number">รวม</th></tr></thead><tbody>{rows}</tbody></table>
    <div class="totals"><div class="line"><span>ยอดสินค้า</span><b>{ctx.baht(subtotal)}</b></div>
    <div class="line"><span>ส่วนลด</span><b>-{ctx.baht(discount)}</b></div>
    <div class="line"><span>ค่าจัดส่ง</span><b>{ctx.baht(shipping)}</b></div>
    {vat_line}
    <div class="line grand"><span>รวมชำระ</span><span>{ctx.baht(o['total'])}</span></div></div>
    <p class="notice">เอกสารนี้เป็นใบเสร็จยืนยันการรับชำระเงินจากระบบ FOOTZONE ไม่ใช่ใบกำกับภาษี
    หากร้านต้องออกใบกำกับภาษี จำเป็นต้องเพิ่มข้อมูลกิจการและรายละเอียดทางภาษีที่ถูกต้อง</p></div></body></html>'''
    return (200, [('Content-Type','text/html; charset=utf-8'), ('Cache-Control','no-store'), ('X-Content-Type-Options','nosniff')], body.encode('utf-8'))

ROUTES = {('GET','/receipt'): receipt}
