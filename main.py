#!/usr/bin/env python3
"""FOOTZONE – Football Equipment Store
รันด้วย:  python main.py   แล้วเปิด http://localhost:8000
ใช้ Python Standard Library + SQLite + HTML/CSS เท่านั้น (ไม่มี JavaScript)"""
import os, re, sys, html, mimetypes, traceback
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs, quote, unquote

import database, auth, cart, order, admin, payment, shipping, sales_overview, receipt
from database import PRODUCT_SQL, CAT_EMOJI, BRAND_COLORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def baht(n):
    n = float(n)
    return "฿{:,.0f}".format(n) if n.is_integer() else "฿{:,.2f}".format(n)


def to_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class Ctx:
    """ข้อมูลคำขอหนึ่งครั้ง + ตัวช่วยสร้างหน้า/Redirect/Cookie"""
    esc = staticmethod(esc)
    baht = staticmethod(baht)
    to_int = staticmethod(to_int)

    def __init__(self, handler, method, path, q, form):
        self.method, self.path, self.q, self.f = method, path, q, form
        self.full_path = handler.path
        self.cookies = SimpleCookie(handler.headers.get("Cookie", ""))
        self.out_cookies = []
        self.db = database.connect()
        self.user = auth.current_user(self)
        self.flash = None
        if "flash" in self.cookies:
            v = unquote(self.cookies["flash"].value)
            self.flash = (v[:1], v[1:])
            self.set_cookie("flash", "", 0)   # แสดงครั้งเดียว

    # ---- template ----
    def render(self, template_name, **kw):
        with open(os.path.join(BASE_DIR, "templates", template_name + ".html"), encoding="utf-8") as f:
            t = f.read()
        return re.sub(r"\{\{(\w+)\}\}", lambda m: str(kw.get(m.group(1), "")), t)

    def img(self, p):
        url = (p["image"] or "").strip()
        if url.startswith(("http://", "https://", "/static/")):
            return '<img src="%s" alt="%s" loading="lazy">' % (esc(url), esc(p["name"]))
        color = BRAND_COLORS.get(p["brand"], "#2b2f33")
        return '<div class="ph" style="--c:%s"><span>%s</span><b>%s</b></div>' % (
            color, CAT_EMOJI.get(p["category"], "⚽"), esc(p["brand"]))

    def category_thumb(self, c):
        url = (c["image"] or "").strip()
        if url.startswith(("http://", "https://", "/static/")):
            return '<div class="cat-thumb"><img src="%s" alt="%s" loading="lazy"></div>' % (esc(url), esc(c["name"]))
        return '<div class="cat-thumb cat-fallback"><b>%s</b></div>' % esc(c["name"])

    def media_box(self, url, name, brand, category, large=False):
        url = (url or "").strip()
        if url.startswith(("http://", "https://", "/static/")):
            cls = 'gallery-main-img' if large else 'gallery-thumb-img'
            return '<img class="%s" src="%s" alt="%s" loading="lazy">' % (cls, esc(url), esc(name))
        color = BRAND_COLORS.get(brand, "#2b2f33")
        extra = ' gallery-main-fallback' if large else ' gallery-thumb-fallback'
        return '<div class="ph%s" style="--c:%s"><span>%s</span><b>%s</b></div>' % (extra, color, CAT_EMOJI.get(category, "⚽"), esc(brand))

    def card(self, p):
        out = '<span class="badge-out">OUT OF STOCK</span>' if p["stock"] <= 0 else ""
        return f'''<article class="card"><a class="card-img" href="/product?id={p["id"]}">{self.img(p)}{out}</a>
<div class="card-body"><h3>{esc(p["name"])}</h3><p class="meta"><b>{esc(p["brand"])}</b></p>
<p class="meta">{esc(p["category"])}</p><div class="price">{"รอกำหนดราคา" if p["price"] == 0 and p["stock"] == 0 else baht(p["price"])}</div>
<a class="btn btn-sm" href="/product?id={p["id"]}">VIEW PRODUCT</a></div></article>'''

    def badge(self, status):
        return '<span class="status s-%s">%s</span>' % (esc(status).lower(), esc(status))

    # ---- response ----
    def page(self, title, body, status=200):
        u = self.user
        n = 0
        if u:
            n = self.db.execute("SELECT COALESCE(SUM(quantity),0) FROM cart WHERE user_id=?", (u["id"],)).fetchone()[0]
            links = ('<span class="hello">👤 %s</span><a href="/orders">คำสั่งซื้อ</a>' % esc(u["name"])
                     + ('<a class="admin-entry" href="/admin">Dashboard แอดมิน</a>' if u['is_admin'] else '')
                     + '<a class="nav-cta" href="/logout">ออกจากระบบ</a>')
        else:
            links = '<a href="/login">เข้าสู่ระบบ</a><a class="nav-cta" href="/register">สมัครสมาชิก</a>'
        flash = ""
        if self.flash and self.flash[1]:
            flash = '<div class="flash %s">%s</div>' % ("flash-err" if self.flash[0] == "e" else "flash-ok", esc(self.flash[1]))
        doc = f'''<!DOCTYPE html>
<html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} | FOOTZONE</title><link rel="stylesheet" href="/static/style.css"></head><body>
<header class="site-header"><div class="nav-wrap"><a class="logo" href="/">FOOT<span>ZONE</span></a>
<input type="checkbox" id="nav-toggle" class="nav-toggle"><label for="nav-toggle" class="burger">☰</label>
<nav class="nav"><a href="/">หน้าแรก</a><a href="/products">สินค้า</a><a href="/#categories">หมวดหมู่</a>
<a href="/#brands">แบรนด์</a><a href="/cart">🛒 ตะกร้า <span class="count">{n}</span></a>{links}</nav></div></header>
{flash}<main>{body}</main>
<footer class="site-footer"><div class="container foot-grid"><div><div class="logo">FOOT<span>ZONE</span></div>
<p>Football Equipment Store</p></div><div><h4>Contact</h4><p>โทร 02-123-4567<br>info@footzone.example.com</p></div>
<div><h4>Shop</h4><p><a href="/products">สินค้าทั้งหมด</a><br><a href="/#brands">แบรนด์</a></p></div></div>
<div class="copy">© {datetime.now().year} FOOTZONE – Football Equipment Store. All rights reserved.</div></footer>
</body></html>'''
        return (status, [("Content-Type", "text/html; charset=utf-8")], doc.encode("utf-8"))

    def not_found(self):
        return self.page("ไม่พบหน้า", '<div class="container center"><h1 class="big">404</h1><p>ไม่พบหน้าที่ต้องการ</p><a class="btn" href="/">กลับหน้าแรก</a></div>', 404)

    def redirect(self, url, msg=None, err=False):
        if msg:
            self.set_cookie("flash", quote(("e" if err else "s") + msg), 60)
        return (303, [("Location", url)], b"")

    def set_cookie(self, name, value, max_age=None):
        c = SimpleCookie()
        c[name] = value
        c[name]["path"] = "/"
        c[name]["httponly"] = True
        c[name]["samesite"] = "Lax"
        if max_age is not None:
            c[name]["max-age"] = max_age
        self.out_cookies = [x for x in self.out_cookies if not x.startswith(name + "=")]
        self.out_cookies.append(c.output(header="").strip())

    def need_login(self, next_url=None):
        if self.user:
            return None
        nxt = next_url or (self.full_path if self.method == "GET" else "/")
        return self.redirect("/login?next=" + quote(nxt), "กรุณาเข้าสู่ระบบก่อน", True)


# ---------------- หน้าสินค้า (Catalog) ----------------
FEATURED_SQL = (PRODUCT_SQL.replace("FROM products p", ", COALESCE(SUM(oi.quantity),0) AS sold FROM products p")
                + " LEFT JOIN order_items oi ON oi.product_id=p.id WHERE p.stock>0 AND p.is_active=1 GROUP BY p.id ORDER BY sold DESC, p.id LIMIT 8")
PRICE_RANGES = {"": ("ทุกช่วงราคา", None, None), "0-1000": ("ต่ำกว่า ฿1,000", 0, 1000),
                "1000-2500": ("฿1,000 - ฿2,499", 1000, 2500), "2500-5000": ("฿2,500 - ฿4,999", 2500, 5000),
                "5000+": ("฿5,000 ขึ้นไป", 5000, None)}
SORTS = {"new": ("ใหม่ล่าสุด", "p.created_at DESC, p.id DESC"), "asc": ("ราคา ต่ำ → สูง", "p.price ASC, p.id"),
         "desc": ("ราคา สูง → ต่ำ", "p.price DESC, p.id")}


def opts(pairs, sel):
    return "".join('<option value="%s"%s>%s</option>' % (esc(v), " selected" if str(v) == str(sel) else "", esc(l))
                   for v, l in pairs)


def home(ctx):
    db = ctx.db
    feat = "".join(ctx.card(p) for p in db.execute(FEATURED_SQL).fetchall())
    brands = "".join(
        '<a class="brand" style="--c:%s" href="/products?brand=%d"><b>%s</b><small>%d สินค้า</small></a>'
        % (BRAND_COLORS.get(b["name"], "#333"), b["id"], esc(b["name"]), b["n"])
        for b in db.execute("SELECT b.id,b.name,COUNT(p.id) n FROM brands b LEFT JOIN products p ON p.brand_id=b.id AND p.is_active=1 GROUP BY b.id ORDER BY b.id"))
    cats = "".join(
        '<a class="cat" href="/products?category=%d">%s<b>%s</b><small>%d สินค้า</small></a>'
        % (c["id"], ctx.category_thumb(c), esc(c["name"]), c["n"])
        for c in db.execute("SELECT c.id,c.name,c.image,COUNT(p.id) n FROM categories c LEFT JOIN products p ON p.category_id=c.id AND p.is_active=1 GROUP BY c.id ORDER BY c.id"))
    return ctx.page("หน้าแรก", ctx.render("index", featured=feat, brands=brands, categories=cats))


def products(ctx):
    db, g = ctx.db, ctx.q
    q = g.get("q", "").strip()
    brand, cat = to_int(g.get("brand")), to_int(g.get("category"))
    pr = g.get("price", "")
    sort = g.get("sort", "new")
    instock = g.get("instock") == "1"
    if pr not in PRICE_RANGES: pr = ""
    if sort not in SORTS: sort = "new"
    where, args = ["p.is_active=1"], []
    if q:
        where.append("p.name LIKE ? ESCAPE '\\'")
        args.append("%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if brand: where.append("p.brand_id=?"); args.append(brand)
    if cat: where.append("p.category_id=?"); args.append(cat)
    lo, hi = PRICE_RANGES[pr][1:]
    if lo is not None: where.append("p.price>=?"); args.append(lo)
    if hi is not None: where.append("p.price<?"); args.append(hi)
    if instock: where.append("p.stock>0")
    sql = PRODUCT_SQL + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY " + SORTS[sort][1]
    rows = db.execute(sql, args).fetchall()
    bo = opts([("", "ทุกแบรนด์")] + [(b["id"], b["name"]) for b in db.execute("SELECT * FROM brands ORDER BY id")], brand or "")
    co = opts([("", "ทุกหมวดหมู่")] + [(c["id"], c["name"]) for c in db.execute("SELECT * FROM categories ORDER BY id")], cat or "")
    items = "".join(ctx.card(p) for p in rows) or '<p class="empty">ไม่พบสินค้าที่ตรงกับเงื่อนไข</p>'
    return ctx.page("สินค้าทั้งหมด", ctx.render(
        "products", q=esc(q), brand_opts=bo, cat_opts=co,
        price_opts=opts([(k, v[0]) for k, v in PRICE_RANGES.items()], pr),
        sort_opts=opts([(k, v[0]) for k, v in SORTS.items()], sort),
        instock="checked" if instock else "", count=len(rows), items=items))


def product(ctx):
    pid = to_int(ctx.q.get("id"))
    p = ctx.db.execute(PRODUCT_SQL + " WHERE p.id=? AND p.is_active=1", (pid,)).fetchone() if pid else None
    if not p:
        return ctx.not_found()
    gallery_urls=[]
    seen=set()
    primary=(p["image"] or "").strip()
    if primary:
        gallery_urls.append(primary); seen.add(primary.casefold())
    for r in ctx.db.execute('SELECT image_url FROM product_images WHERE product_id=? ORDER BY sort_order,id',(pid,)):
        url=(r['image_url'] or '').strip()
        if url and url.casefold() not in seen:
            gallery_urls.append(url); seen.add(url.casefold())
    if not gallery_urls:
        gallery_html='<div class="detail-image">'+ctx.media_box('', p['name'], p['brand'], p['category'], large=True)+'</div>'
    else:
        main_html='<div class="detail-image gallery-display">'+ctx.media_box(gallery_urls[0], p['name'], p['brand'], p['category'], large=True)+'</div>'
        thumbs=''.join(
            f'<button type="button" class="gallery-thumb {"is-active" if index == 0 else ""}" '
            f'data-gallery-src="{esc(url)}" aria-label="ดูรูปสินค้า {index + 1}" '
            f'aria-pressed="{"true" if index == 0 else "false"}">'
            f'{ctx.media_box(url, p["name"], p["brand"], p["category"], large=False)}</button>'
            for index, url in enumerate(gallery_urls)
        )
        gallery_html=main_html + '<div class="product-gallery-grid" aria-label="เลือกรูปภาพสินค้า">'+thumbs+'</div>'
    sizes=ctx.db.execute('SELECT size_name FROM product_sizes WHERE product_id=? ORDER BY sort_order,id',(pid,)).fetchall()
    size_choice='<label>เลือกไซส์ / ขนาด<select name="size_name" required><option value="">-- กรุณาเลือกไซส์ --</option>'+''.join(f'<option value="{esc(r["size_name"])}">{esc(r["size_name"])}</option>' for r in sizes)+'</select></label>' if sizes else ''
    colors=ctx.db.execute('SELECT name,hex_code FROM product_colors WHERE product_id=? ORDER BY id',(pid,)).fetchall()
    color_choice='<label>เลือกสี<select name="color_name" required>'+''.join(f'<option value="{esc(c["name"])}">{esc(c["name"])} ({esc(c["hex_code"] )})</option>' for c in colors)+'</select></label>' if colors else ''
    color_swatches='<div class="product-color-swatches">'+''.join(f'<span class="color-chip"><i style="background:{esc(c["hex_code"])}"></i>{esc(c["name"])}</span>' for c in colors)+'</div>' if colors else ''
    gallery_count_note=f'<p class="muted">มีรูปตัวอย่างสินค้า {len(gallery_urls)} รูป · คลิกรูปย่อด้านล่างเพื่อเปลี่ยนภาพหลัก</p>' if gallery_urls else '<p class="muted">ยังไม่มีรูปตัวอย่างเพิ่มเติม</p>'
    if p["stock"] <= 0:
        stock_text, buy = '<span class="out">สินค้าหมด</span>', '<div class="out-box">OUT OF STOCK</div>'
    else:
        low = " (เหลือน้อย!)" if p["stock"] <= 5 else ""
        stock_text = "คงเหลือ %d ชิ้น%s" % (p["stock"], low)
        buy = f'''<form method="post" action="/cart/add" class="buy"><input type="hidden" name="product_id" value="{p["id"]}">
<label>จำนวน <input type="number" name="quantity" value="1" min="1" max="{p["stock"]}" required></label>
{color_choice}{size_choice}<button class="btn" type="submit">ADD TO CART</button></form>'''
    return ctx.page(p["name"], ctx.render(
        "product", image=gallery_html, gallery_note=gallery_count_note, name=esc(p["name"]), brand=esc(p["brand"]), category=esc(p["category"]),
        price=("รอกำหนดราคา" if p["price"] == 0 and p["stock"] == 0 else baht(p["price"])), description=esc(p["description"]), stock_text=stock_text, buy=buy, color_swatches=color_swatches,
        created=esc(p["created_at"][:10])))



ROUTES = {("GET", "/"): home, ("GET", "/products"): products, ("GET", "/product"): product}
for _m in (auth, cart, order, admin, payment, shipping, sales_overview, receipt):
    ROUTES.update(_m.ROUTES)


# ---------------- HTTP Server ----------------
class Handler(BaseHTTPRequestHandler):
    server_version = "FOOTZONE/1.0"

    def do_GET(self): self.process("GET")
    def do_POST(self): self.process("POST")

    def static(self, path):
        root = os.path.realpath(os.path.join(BASE_DIR, "static"))
        fp = os.path.realpath(os.path.join(root, unquote(path[len("/static/"):])))
        if not fp.startswith(root + os.sep) or not os.path.isfile(fp):
            return self.reply((404, [("Content-Type", "text/plain; charset=utf-8")], b"Not found"), [])
        with open(fp, "rb") as f:
            data = f.read()
        ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
        self.reply((200, [("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))], data), [])

    def process(self, method):
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        if method == "GET" and path.startswith("/static/"):
            return self.static(path)
        form = {}
        if method == "POST":
            try:
                claimed = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                claimed = 0
            if claimed < 0 or claimed > (25_000_000 if path == "/admin/product/save" else 5_000_000):
                return self.reply((413, [("Content-Type", "text/plain; charset=utf-8")], "ไฟล์ใหญ่เกินกำหนด".encode()), [])
            raw = self.rfile.read(claimed)
            ctype = self.headers.get("Content-Type", "")
            if ctype.lower().startswith("multipart/form-data"):
                from email.parser import BytesParser
                from email.policy import default
                msg = BytesParser(policy=default).parsebytes(b"MIME-Version: 1.0\r\nContent-Type: " + ctype.encode("latin1", "replace") + b"\r\n\r\n" + raw)
                if not msg.is_multipart():
                    return self.reply((400, [], b"Bad multipart request"), [])
                for part in msg.iter_parts():
                    key = part.get_param("name", header="content-disposition")
                    if not key: continue
                    val = part.get_payload(decode=True) or b""
                    if key in ("slip", "store_qr"):
                        form["_" + key + "_bytes"] = val
                    elif key == "product_photos":
                        if part.get_filename() and val:
                            form.setdefault("_product_photos", []).append(val)
                    else:
                        form[key] = val[:12000].decode("utf-8", "replace")
            else:
                form = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True).items()}
        q = {k: v[0] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        ctx = Ctx(self, method, path, q, form)
        try:
            route = ROUTES.get((method, path))
            resp = route(ctx) if route else ctx.not_found()
        except Exception:
            traceback.print_exc()
            resp = ctx.page("Error", '<div class="container center"><h1 class="big">500</h1><p>เกิดข้อผิดพลาดภายในระบบ</p><a class="btn" href="/">กลับหน้าแรก</a></div>', 500)
        finally:
            ctx.db.close()
        self.reply(resp, ctx.out_cookies)

    def reply(self, resp, cookies):
        status, headers, body = resp
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        for c in cookies:
            self.send_header("Set-Cookie", c)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    database.init_db()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print("FOOTZONE กำลังทำงานที่ http://localhost:%d  (กด Ctrl+C เพื่อหยุด)" % PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nหยุดเซิร์ฟเวอร์แล้ว")