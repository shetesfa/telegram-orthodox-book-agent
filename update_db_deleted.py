import sqlite3

conn = sqlite3.connect(r"C:\Users\Tesfa\.gemini\antigravity\scratch\telegram-book-agent\data\database\books.db")
cur = conn.cursor()

bad_terms = [
    "%kooblife%", "%ትኩሳት%", "%ዳዊት_ወልደጊዮርጊስ%", "%ኤርሚያስ_አመልጋ%",
    "%ቆርጠሀት%", "%ያገር_ልጅ%", "%በራስ መተማመን%", "%ኢህአፓ%", "%ጳውሎስ ኞኞ%",
    "%ገዳሙ ገዛኸኝ%", "%ደገልሃን%", "%መስፍን ሀብተማርያም%", "%ስሞተኛው%"
]

total = 0
for b in bad_terms:
    cur.execute("UPDATE processed_files SET status = 'deleted' WHERE filename LIKE ?", (b,))
    total += cur.rowcount

conn.commit()
print(f"Updated {total} records in database to 'deleted'.")
