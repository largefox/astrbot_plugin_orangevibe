import aiosqlite
import os

DB_PATH = ""


async def init_db(db_dir: str):
    global DB_PATH
    DB_PATH = os.path.join(db_dir, "orangequiz.db")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS play_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_name TEXT,
                test_id TEXT,
                result_name TEXT,
                ai_comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS test_stats (
                test_id TEXT PRIMARY KEY,
                play_count INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS create_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def record_play(
    user_id: str, user_name: str, test_id: str, result_name: str, ai_comment: str
):
    if not DB_PATH:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # Insert history
        await db.execute(
            """
            INSERT INTO play_history (user_id, user_name, test_id, result_name, ai_comment)
            VALUES (?, ?, ?, ?, ?)
        """,
            (user_id, user_name, test_id, result_name, ai_comment),
        )

        # Upsert stats
        await db.execute(
            """
            INSERT INTO test_stats (test_id, play_count)
            VALUES (?, 1)
            ON CONFLICT(test_id) DO UPDATE SET play_count = play_count + 1
        """,
            (test_id,),
        )

        await db.commit()


async def get_hot_quizzes(limit: int = 5):
    if not DB_PATH:
        return []

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT test_id, play_count FROM test_stats ORDER BY play_count DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {"test_id": row["test_id"], "play_count": row["play_count"]}
                for row in rows
            ]


async def get_user_history(user_id: str, test_id: str):
    if not DB_PATH:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM play_history WHERE user_id = ? AND test_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id, test_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


async def get_daily_create_count(user_id: str) -> int:
    if not DB_PATH:
        return 0
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM create_history WHERE user_id = ? AND date(created_at, 'localtime') = date('now', 'localtime')",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def record_create(user_id: str):
    if not DB_PATH:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO create_history (user_id) VALUES (?)", (user_id,))
        await db.commit()
