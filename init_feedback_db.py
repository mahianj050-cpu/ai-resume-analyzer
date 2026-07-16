import sqlite3

conn = sqlite3.connect('feedback.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT NOT NULL,
    feedback_text TEXT NOT NULL,
    sentiment_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()
conn.close()

print("feedback.db and table created successfully.")
