import hashlib,hmac,secrets,sqlite3
from datetime import datetime,timedelta,timezone
from urllib.parse import quote
def digest(password,salt=None):
    salt=salt or secrets.token_bytes(16)
    h=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,250000)
    return salt.hex()+':'+h.hex()
def verify(password,stored):
    try:
        s,h=stored.split(':'); return hmac.compare_digest(digest(password,bytes.fromhex(s)),stored)
    except (ValueError,AttributeError): return False
def current_user(ctx):
    c=ctx.cookies.get('session')
    if not c:return None
    return ctx.db.execute("SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires_at>?",(c.value,datetime.now(timezone.utc).isoformat())).fetchone()
def login_page(ctx):
    return ctx.page('เข้าสู่ระบบ',ctx.render('auth',title='เข้าสู่ระบบ',action='/login',fields="""<label>อีเมลหรือเบอร์โทร<input name="identity" autocomplete="username" required></label><label>รหัสผ่าน<input name="password" type="password" autocomplete="current-password" required></label>""",button='เข้าสู่ระบบ',other='<a href="/register">ยังไม่มีบัญชี? สมัครสมาชิก</a>'))
def register_page(ctx):
    return ctx.page('สมัครสมาชิก',ctx.render('auth',title='สมัครสมาชิก',action='/register',fields="""<label>ชื่อผู้ใช้<input name="name" maxlength="80" required></label><label>อีเมล<input name="email" type="email" maxlength="200" required></label><label>เบอร์โทร<input name="phone" maxlength="20" required></label><label>รหัสผ่าน (อย่างน้อย 8 ตัวอักษร)<input name="password" type="password" minlength="8" autocomplete="new-password" required></label>""",button='สร้างบัญชี',other='<a href="/login">มีบัญชีแล้ว? เข้าสู่ระบบ</a>'))
def create_session(ctx,uid):
    t=secrets.token_urlsafe(32)
    exp=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()
    ctx.db.execute('INSERT INTO sessions VALUES(?,?,?)',(t,uid,exp));ctx.db.commit()
    ctx.set_cookie('session',t,604800)
def register(ctx):
    name=ctx.f.get('name','').strip(); email=ctx.f.get('email','').strip().lower(); phone=ctx.f.get('phone','').strip(); password=ctx.f.get('password','')
    if not name or '@' not in email or not phone or len(password)<8:return ctx.redirect('/register','ข้อมูลไม่ครบหรือรหัสผ่านสั้นเกินไป',True)
    try:
        cur=ctx.db.execute('INSERT INTO users(name,email,phone,password_hash) VALUES(?,?,?,?)',(name,email,phone,digest(password)))
        ctx.db.commit()
    except sqlite3.IntegrityError:return ctx.redirect('/register','อีเมลหรือเบอร์โทรถูกใช้แล้ว',True)
    create_session(ctx,cur.lastrowid); return ctx.redirect('/','สมัครสมาชิกสำเร็จ')
def login(ctx):
    idn=ctx.f.get('identity','').strip(); password=ctx.f.get('password','')
    u=ctx.db.execute('SELECT * FROM users WHERE email=? OR phone=?',(idn.lower(),idn)).fetchone()
    if not u or not verify(password,u['password_hash']):return ctx.redirect('/login','ข้อมูลเข้าสู่ระบบไม่ถูกต้อง',True)
    create_session(ctx,u['id']);return ctx.redirect('/','เข้าสู่ระบบสำเร็จ')
def logout(ctx):
    c=ctx.cookies.get('session')
    if c:ctx.db.execute('DELETE FROM sessions WHERE token=?',(c.value,));ctx.db.commit()
    ctx.set_cookie('session','',0);return ctx.redirect('/','ออกจากระบบแล้ว')
ROUTES={('GET','/login'):login_page,('POST','/login'):login,('GET','/register'):register_page,('POST','/register'):register,('GET','/logout'):logout}
