import sqlite3

conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Add the is_admin column with default value 0
cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")

conn.commit()
conn.close()
print("Column 'is_admin' added to users table.")
