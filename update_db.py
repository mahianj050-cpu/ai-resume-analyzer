import sqlite3


def update_database():
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()

        # Check if username column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'username' not in columns:
            # Add username column if it doesn't exist
            cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
            print("✅ Successfully added username column")
        else:
            print("ℹ️ Username column already exists")

        conn.commit()
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    finally:
        conn.close()


if __name__ == "__main__":
    update_database()