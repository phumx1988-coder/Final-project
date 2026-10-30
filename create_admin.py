"""Run separately once: python create_admin.py"""
from getpass import getpass
import database, auth

def main():
    database.init_db()
    print('สร้าง/เปลี่ยนรหัสผ่านผู้ดูแล FOOTZONE (ไม่แสดงในหน้าร้าน)')
    email=input('อีเมลแอดมิน [admin@footzone.com]: ').strip().lower() or 'admin@footzone.com'
    if '@' not in email:raise SystemExit('รูปแบบอีเมลไม่ถูกต้อง')
    pwd=getpass('ตั้งรหัสผ่านแอดมิน (อย่างน้อย 12 ตัวอักษร): ')
    confirm=getpass('ยืนยันรหัสผ่าน: ')
    if len(pwd)<12 or pwd!=confirm:raise SystemExit('รหัสผ่านสั้นเกินไป หรือยืนยันรหัสผ่านไม่ตรงกัน')
    with database.connect() as db:
        u=db.execute('SELECT id,is_admin FROM users WHERE email=?',(email,)).fetchone()
        if u and not u['is_admin']:
            raise SystemExit('อีเมลนี้เป็นบัญชีลูกค้าแล้ว โปรดเลือกอีเมลอื่น')
        if u:
            db.execute('UPDATE users SET password_hash=? WHERE id=?',(auth.digest(pwd),u['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
        else:
            db.execute('INSERT INTO users(name,email,phone,password_hash,is_admin) VALUES(?,?,?,?,1)',('Administrator',email,None,auth.digest(pwd)))
    print('สร้าง/อัปเดตบัญชีแอดมินสำเร็จ เข้าใช้งานที่ http://localhost:8000/admin/login')

if __name__=='__main__':main()
