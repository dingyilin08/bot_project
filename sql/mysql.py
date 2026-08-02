import os

import aiomysql
from contextlib import asynccontextmanager


@asynccontextmanager
async def connect_mysql():
    conn = await aiomysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "bot_project"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        db=os.getenv("MYSQL_DATABASE", "bot_project"),
        charset='utf8mb4',
        autocommit=False
    )
    try:
        yield conn
    except BaseException:
        # 所有业务连接均关闭自动提交。显式回滚能保证异常路径不会把
        # 未完成的跨表操作遗留给连接关闭时的隐式行为处理。
        await conn.rollback()
        raise
    finally:
        conn.close()
