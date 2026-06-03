"""
通用分页工具函数

使用 SQLAlchemy 窗口函数 func.count().over() 实现单次数据库往返的分页查询，
替代传统的 COUNT + SELECT 双查询模式。
"""

from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any


async def paginate_with_window(
    db: AsyncSession,
    base_stmt: Any,
    conditions: list,
    order_by: list,
    page: int,
    count: int,
    max_count: int = 1000,
) -> tuple[list, int]:
    """
    使用窗口函数的单次分页查询。

    Args:
        db: AsyncSession 数据库会话
        base_stmt: select(...) 基础查询语句
        conditions: where 条件列表
        order_by: 排序列表
        page: 页码（从 1 开始）
        count: 每页条数
        max_count: 每页最大条数限制

    Returns:
        (rows, total) 元组
        - rows: 不含 total 列的原始行数据
        - total: 满足条件的总记录数
    """
    limit = max(1, min(int(count or 15), max_count))
    page = max(1, int(page or 1))
    skip = (page - 1) * limit

    # 在 base_stmt 的 select 列中追加窗口函数
    stmt = base_stmt.add_columns(func.count().over().label("_total"))

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(*order_by).offset(skip).limit(limit)

    result = await db.execute(stmt)
    raw_rows = result.all()

    if not raw_rows:
        return [], 0

    total = int(raw_rows[0]._total)
    # 去除 _total 列，返回原始列
    rows = [row[:-1] for row in raw_rows]

    return rows, total
