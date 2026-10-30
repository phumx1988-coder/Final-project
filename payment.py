"""Payment workflow: manual transfer/PromptPay confirmation and admin review."""
import os, hmac, hashlib, secrets, io, re
from pathlib import Path
from urllib.parse import quote
from database import DB

UPLOAD_DIR = Path(__file__).with_name('private_payment_slips')
MAX_UPLOAD = 4 * 1024 * 1024
METHODS = {'transfer':'โอนผ่านธนาคาร','promptpay':'QR PromptPay','cod':'เก็บเงินปลายทาง'}
PAY_LABEL = {'pending':'รอชำระเงิน','review':'รอตรวจสอบการชำระเงิน','paid':'ชำระเงินแล้ว','failed':'ชำระเงินไม่สำเร็จ','refunded':'คืนเงินแล้ว','cod_due':'รอเก็บเงินปลายทาง'}
SHIP_LABEL = {'Pending':'รอจัดเตรียมสินค้า','Confirmed':'กำลังจัดเตรียมสินค้า','Shipped':'กำลังจัดส่ง','Completed':'จัดส่งสำเร็จ','Cancelled':'ยกเลิก'}

STORE_QR_DIR = Path(__file__).with_name('private_store_qr')

def setting(ctx,key):
    row=ctx.db.execute('SELECT value FROM payment_settings WHERE key=?',(key,)).fetchone()
    return row['value'] if row else ''

def store_qr(ctx):
    name=setting(ctx,'qr_filename')
    if not name or not re.fullmatch(r'[a-f0-9]{40}\.(png|jpg|webp)',name):return ctx.not_found()
    path=STORE_QR_DIR/name
    if not path.is_file():return ctx.not_found()
    mime={'.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp'}[path.suffix]
    return (200,[('Content-Type',mime),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')],path.read_bytes())

def csrf(ctx):
    token=ctx.cookies.get('session')
    return hmac.new((token.value if token else '').encode(),b'FOOTZONE:payment:v1',hashlib.sha256).hexdigest()
def valid_csrf(ctx):
    token=ctx.cookies.get('session')
    return bool(token and hmac.compare_digest(ctx.f.get('csrf',''),csrf(ctx)))
def method_name(method):return METHODS.get(method,method)
def payment_name(status):return PAY_LABEL.get(status,status)
def shipping_name(status):return SHIP_LABEL.get(status,status)

def get_order(ctx, oid, admin=False):
    if not ctx.user:return None
    if admin and ctx.user['is_admin']:
        return ctx.db.execute('SELECT o.*,u.name,u.email FROM orders o JOIN users u ON u.id=o.user_id WHERE o.id=?',(oid,)).fetchone()
    return ctx.db.execute('SELECT * FROM orders WHERE id=? AND user_id=?',(oid,ctx.user['id'])).fetchone()

def emv_field(tag, value):
    return f'{tag}{len(value):02d}{value}'

def promptpay_payload(identifier, amount):
    """Thailand PromptPay merchant-presented EMV QR for a phone or 13-digit national/tax ID."""
    digits=re.sub(r'[^0-9]','',identifier)
    if len(digits)==10 and digits.startswith('0'):
        account=emv_field('01','0066'+digits[1:])
    elif len(digits)==13:
        account=emv_field('02',digits)
    else:
        raise ValueError('PromptPay ID must be a Thai 10-digit phone or 13-digit ID')
    merchant=emv_field('00','A000000677010111')+account
    payload=(emv_field('00','01')+emv_field('01','12')+emv_field('29',merchant)+
             emv_field('58','TH')+emv_field('53','764')+emv_field('54',f'{amount:.2f}')+'6304')
    crc=0xffff
    for byte in payload.encode('ascii'):
        crc ^= byte << 8
        for _ in range(8):crc=((crc<<1)^0x1021) & 0xffff if (crc&0x8000) else (crc<<1)&0xffff
    return payload+f'{crc:04X}'

def qr(ctx):
    if not ctx.user:return ctx.not_found()
    oid=ctx.to_int(ctx.q.get('id'));o=get_order(ctx,oid)
    identifier=setting(ctx,'promptpay_id') or os.environ.get('FOOTZONE_PROMPTPAY_ID','')
    if not o or o['payment_method']!='promptpay' or o['status']=='Cancelled' or o['payment_status'] not in ('pending','failed','review'):
        return ctx.not_found()
    try:
        import qrcode
        payload=promptpay_payload(identifier,o['total'])
        img=qrcode.make(payload);buf=io.BytesIO();img.save(buf,format='PNG')
        return (200,[('Content-Type','image/png'),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')],buf.getvalue())
    except (ImportError,ValueError):return ctx.not_found()

def detail(ctx):
    if not ctx.user:return ctx.need_login('/orders')
    oid=ctx.to_int(ctx.q.get('id'))
    o=get_order(ctx,oid)
    if not o:return ctx.not_found()
    items=ctx.db.execute('SELECT oi.*,p.name FROM order_items oi JOIN products p ON p.id=oi.product_id WHERE oi.order_id=?',(oid,)).fetchall()
    lines=''.join(f'<div class="cart-line"><span>{ctx.esc(r["name"])} × {r["quantity"]}<small> · สี: {ctx.esc(r["color_name"] or "ไม่ระบุ")} · ไซส์: {ctx.esc(r["size_name"] or "ไม่ระบุ")} · {ctx.baht(r["unit_price"])} / ชิ้น</small></span><strong>{ctx.baht(r["quantity"]*r["unit_price"])}</strong></div>' for r in items)
    shipping=o['shipping_fee'] or 0; discount=o['discount_amount'] or 0; subtotal=o['subtotal'] if o['subtotal'] is not None else o['total']-shipping+discount
    summary=f'<div class="cart-line">ค่าสินค้า <strong>{ctx.baht(subtotal)}</strong></div><div class="cart-line">ส่วนลด <strong>-{ctx.baht(discount)}</strong></div><div class="cart-line">ค่าจัดส่ง <strong>{ctx.baht(shipping)}</strong></div><div class="summary"><strong>ยอดสุทธิ {ctx.baht(o["total"])}</strong></div>'
    details=f'<p>วิธีชำระ: <b>{ctx.esc(method_name(o["payment_method"]))}</b></p><p>สถานะชำระเงิน: <b>{ctx.esc(payment_name(o["payment_status"]))}</b></p><p>สถานะจัดส่ง: <b>{ctx.esc(shipping_name(o["status"]))}</b></p>'
    method=o['payment_method']; instructions=''
    if method in ('transfer','promptpay') and o['payment_status'] in ('pending','failed','review'):
        bank=setting(ctx,'bank_name')+' / '+setting(ctx,'account_name')+' / '+setting(ctx,'account_number') if setting(ctx,'account_number') else os.environ.get('FOOTZONE_BANK_INFO','ยังไม่ได้ตั้งค่าบัญชีรับโอน (แจ้งร้านค้าก่อนโอน)')
        promptpay=setting(ctx,'promptpay_id') or os.environ.get('FOOTZONE_PROMPTPAY_ID','')
        if method=='transfer': instructions=f'<div class="payment-instructions"><h3>ข้อมูลโอนเงิน</h3><p>{ctx.esc(bank)}</p><p>โอนยอด <strong>{ctx.baht(o["total"])}</strong> แล้วแนบสลิปด้านล่าง</p></div>'
        else:
            instructions=f'<div class="payment-instructions"><h3>PromptPay</h3><p>{"หมายเลขรับเงิน: " + ctx.esc(promptpay) if promptpay else "ยังไม่ได้กำหนดหมายเลข PromptPay ของร้าน"}</p><p>ยอดชำระ <strong>{ctx.baht(o["total"])}</strong> — หลังสแกนด้วยแอปธนาคาร กรุณาแนบสลิป</p></div>'
        if method=='promptpay' and setting(ctx,'qr_filename'):
            instructions += '<p><img class="promptpay-qr" src="/payment/store-qr" alt="QR Code ร้านค้า"></p><p class="muted">QR รูปภาพจากร้านอาจไม่ระบุยอดเงินอัตโนมัติ ตรวจสอบผู้รับและจำนวนเงินก่อนโอน</p>'
        elif method=='promptpay' and promptpay:
            try:
                promptpay_payload(promptpay,o['total'])
                instructions += f'<p><img class="promptpay-qr" src="/payment/qr?id={oid}" alt="QR PromptPay ยอด {ctx.baht(o["total"])}"></p><p class="muted">QR ระบุยอดเงินแล้ว กรุณาตรวจชื่อผู้รับก่อนโอน</p>'
            except ValueError:instructions += '<p class="muted">หมายเลข PromptPay ร้านค้าไม่ถูกต้อง</p>'
        instructions += f'''<form class="form payment-form" method="post" action="/payment/notify" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf(ctx)}"><input type="hidden" name="id" value="{oid}"><label>แนบสลิปโอนเงิน (JPG, PNG, WebP ไม่เกิน 4 MB)<input type="file" name="slip" accept="image/jpeg,image/png,image/webp" required></label><button class="btn">ส่งหลักฐานการชำระเงิน</button></form>'''
    if method=='cod':instructions='<p class="muted">คำสั่งซื้อเก่าที่เคยเลือกเก็บเงินปลายทาง โปรดติดต่อร้านเพื่อดำเนินการ</p>'
    if o['proof_file']:
        instructions+=f'<p>หลักฐานล่าสุด: <a href="/payment/slip?id={oid}" target="_blank" rel="noopener">ดูสลิปที่ส่งไว้</a></p>'
    if o['payment_status']=='review':instructions+='<p class="muted">กำลังรอแอดมินตรวจสอบสลิป ร้านจะแสดงผลการตรวจสอบในหน้านี้</p>'
    if o['payment_note']:instructions+='<p class="muted">หมายเหตุจากร้าน: '+ctx.esc(o['payment_note'])+'</p>'
    receipt_link=f'<p><a class="btn" href="/receipt?id={oid}">🧾 ดู / พิมพ์ใบเสร็จรับเงิน</a></p>' if o['payment_status']=='paid' and o['status']!='Cancelled' else ''
    return ctx.page('รายละเอียดคำสั่งซื้อ',f'<section class="container section narrow"><a href="/orders">← คำสั่งซื้อของฉัน</a><h1>คำสั่งซื้อ #{oid}</h1>{details}<p>ที่อยู่จัดส่ง: {ctx.esc(o["address"])}</p>{lines}{summary}{instructions}{receipt_link}<p><a class="btn btn-outline" href="/tracking?id={oid}">ติดตามพัสดุ →</a></p></section>')

def notify(ctx):
    if not ctx.user:return ctx.need_login('/orders')
    if not valid_csrf(ctx):return ctx.page('คำขอไม่ถูกต้อง','<section class="container section">คำขอไม่ถูกต้อง</section>',403)
    oid=ctx.to_int(ctx.f.get('id')); o=get_order(ctx,oid)
    if not o:return ctx.not_found()
    if o['payment_method'] not in ('transfer','promptpay') or o['payment_status'] not in ('pending','failed','review') or o['status']=='Cancelled':
        return ctx.redirect('/order?id='+str(oid),'ไม่สามารถส่งหลักฐานได้ในสถานะนี้',True)
    blob=ctx.f.get('_slip_bytes',b'')
    if not blob or len(blob)>MAX_UPLOAD:return ctx.redirect('/order?id='+str(oid),'กรุณาแนบรูปสลิปไม่เกิน 4 MB',True)
    ext=None
    if blob.startswith(b'\xff\xd8\xff'):ext='.jpg'
    elif blob.startswith(b'\x89PNG\r\n\x1a\n'):ext='.png'
    elif blob[:4]==b'RIFF' and blob[8:12]==b'WEBP':ext='.webp'
    if not ext:return ctx.redirect('/order?id='+str(oid),'อนุญาตเฉพาะไฟล์รูปภาพ JPG PNG หรือ WebP',True)
    UPLOAD_DIR.mkdir(mode=0o700,exist_ok=True)
    name=secrets.token_hex(20)+ext
    with open(UPLOAD_DIR/name,'xb') as f:f.write(blob)
    old=o['proof_file']
    ctx.db.execute('UPDATE orders SET proof_file=?,payment_status="review",payment_submitted_at=CURRENT_TIMESTAMP,payment_note="",payment_reviewed_at=NULL,payment_reviewed_by=NULL WHERE id=? AND user_id=?',(name,oid,ctx.user['id']))
    ctx.db.commit()
    if old:
        try:(UPLOAD_DIR/old).unlink(missing_ok=True)
        except OSError:pass
    return ctx.redirect('/order?id='+str(oid),'ส่งหลักฐานแล้ว กรุณารอแอดมินตรวจสอบ')

def slip(ctx):
    oid=ctx.to_int(ctx.q.get('id'))
    o=get_order(ctx,oid,admin=True)
    if not o or not o['proof_file']:return ctx.not_found()
    path=UPLOAD_DIR/o['proof_file']
    if path.parent!=UPLOAD_DIR or not path.is_file():return ctx.not_found()
    mime={'.jpg':'image/jpeg','.png':'image/png','.webp':'image/webp'}.get(path.suffix)
    if not mime:return ctx.not_found()
    return (200,[('Content-Type',mime),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Content-Disposition','inline')],path.read_bytes())

ROUTES={('GET','/order'):detail,('POST','/payment/notify'):notify,('GET','/payment/slip'):slip,('GET','/payment/qr'):qr,('GET','/payment/store-qr'):store_qr}
