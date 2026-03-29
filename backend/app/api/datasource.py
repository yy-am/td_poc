"""数据源管理 API"""
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter()
VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(identifier: str) -> str:
    if not VALID_IDENTIFIER.fullmatch(identifier):
        raise HTTPException(status_code=400, detail="非法表名")
    return f'"{identifier}"'


async def get_table_names(db: AsyncSession) -> list[str]:
    conn = await db.connection()
    return await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())


async def get_table_columns(db: AsyncSession, table_name: str) -> list[dict]:
    conn = await db.connection()
    return await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_columns(table_name))


@router.get("/tables")
async def list_tables(db: AsyncSession = Depends(get_db)):
    """列出所有数据表及行数"""
    tables = []
    for table_name in sorted(await get_table_names(db)):
        try:
            count_result = await db.execute(
                text(f"SELECT COUNT(*) FROM {quote_identifier(table_name)}")
            )
            count = count_result.scalar_one()
        except Exception:
            count = 0
        tables.append({"table_name": table_name, "row_count": count})
    return tables


@router.get("/tables/{table_name}/schema")
async def get_table_schema(table_name: str, db: AsyncSession = Depends(get_db)):
    """获取表结构"""
    table_names = await get_table_names(db)
    if table_name not in table_names:
        raise HTTPException(status_code=404, detail="数据表不存在")

    columns = []
    for column in await get_table_columns(db, table_name):
        columns.append({
            "column_name": column["name"],
            "data_type": str(column["type"]),
            "nullable": "YES" if column.get("nullable", True) else "NO",
            "comment": column.get("comment") or "",
        })

    quoted_table_name = quote_identifier(table_name)
    count_result = await db.execute(text(f"SELECT COUNT(*) FROM {quoted_table_name}"))
    count = count_result.scalar_one()

    # 预览前5行
    preview_result = await db.execute(text(f"SELECT * FROM {quoted_table_name} LIMIT 5"))
    preview_rows = [dict(row) for row in preview_result.mappings().all()] if columns else []

    return {
        "table_name": table_name,
        "columns": columns,
        "row_count": count,
        "preview": preview_rows,
    }


@router.post("/query")
async def execute_query(body: dict, db: AsyncSession = Depends(get_db)):
    """执行SQL查询（管理用途）"""
    sql = body.get("sql", "")
    if not sql.strip().upper().startswith("SELECT"):
        return {"error": "仅允许SELECT查询"}
    try:
        result = await db.execute(text(sql))
        columns = list(result.keys())
        rows = [dict(row) for row in result.mappings().all()]
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        return {"error": str(e)}
