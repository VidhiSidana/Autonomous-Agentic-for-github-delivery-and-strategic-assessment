
import sqlite3
from pathlib import Path


class EngineeringMemory:

    def __init__(self):

        project_root = Path(__file__).resolve().parent.parent

        self.db_path = project_root / "memory" / "engineering_memory.db"

        self.create_table()

    def connect(self):
        return sqlite3.connect(self.db_path)

    def create_table(self):

        with self.connect() as connection:

            connection.execute("""
                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def save_finding(self, title, content):

        with self.connect() as connection:

            connection.execute(
                "INSERT INTO findings (title, content) VALUES (?, ?)",
                (title, content)
            )

        return "Finding saved successfully."

    def retrieve_findings(self):

        with self.connect() as connection:

            cursor = connection.execute("""
                SELECT id, title, content, created_at
                FROM findings
                ORDER BY id DESC
            """)

            return cursor.fetchall()

    def search_findings(self, keyword):

        with self.connect() as connection:

            cursor = connection.execute("""
                SELECT id, title, content, created_at
                FROM findings
                WHERE title LIKE ? OR content LIKE ?
                ORDER BY id DESC
            """, (f"%{keyword}%", f"%{keyword}%"))

            return cursor.fetchall()


if __name__ == "__main__":

    memory = EngineeringMemory()

    findings = memory.retrieve_findings()

    print("\nStored Engineering Findings:")

    for finding in findings:

        print(f"\nID: {finding[0]}")
        print(f"Title: {finding[1]}")
        print(f"Content: {finding[2]}")
        print(f"Created At: {finding[3]}")



