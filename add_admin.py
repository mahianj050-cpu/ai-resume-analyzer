import sqlite3
from werkzeug.security import generate_password_hash

email = "myadmin2@gmail.com"
password = generate_password_hash("adminpass1")  # use a strong password

conn = sqlite3.connect('users.db')
cursor = conn.cursor()

cursor.execute("INSERT INTO users (email, password, is_admin) VALUES (?, ?, ?)", (email, password, 1))

conn.commit()
conn.close()
print("Admin user added.")
