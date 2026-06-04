import sqlite3

def check():
    conn = sqlite3.connect('hireflow.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)
    for table_name_tup in tables:
        t_name = table_name_tup[0]
        cursor.execute(f"SELECT COUNT(*) FROM {t_name};")
        count = cursor.fetchone()[0]
        print(f"Table '{t_name}' has {count} records.")
    conn.close()

if __name__ == '__main__':
    check()
