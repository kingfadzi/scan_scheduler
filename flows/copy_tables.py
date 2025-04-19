import asyncio
import yaml
import aioodbc
import asyncpg
from pathlib import Path
from typing import List, Dict, Any, Union
from prefect import flow, task, get_run_logger

CHUNK_SIZE = 5000
CONFIG_PATH = "config/dbload/table_mapping.yaml"

def load_config(path: str = CONFIG_PATH) -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)

@task
async def extract_postgres_schema(conn_str: str, table: str) -> str:
    schema, name = table.split(".")
    conn = await asyncpg.connect(conn_str)
    try:
        rows = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = $2
            ORDER BY ordinal_position;
        """, schema, name)
    finally:
        await conn.close()

    ddl = f'CREATE TABLE {table} (\n  ' + ",\n  ".join(
        f'"{r["column_name"]}" {r["data_type"]}' + (" NOT NULL" if r["is_nullable"] == "NO" else "")
        for r in rows
    ) + "\n);"
    return ddl

@task
async def extract_sqlserver_schema(conn_str: str, table: str) -> str:
    schema, name = table.split(".")
    ddl_lines = []
    async with aioodbc.connect(dsn=conn_str, autocommit=True) as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
            """, (schema, name))
            rows = await cur.fetchall()

            for col_name, col_type, nullable in rows:
                pg_type = sqlserver_to_postgres_type(col_type)
                line = f'"{col_name}" {pg_type}'
                if nullable == "NO":
                    line += " NOT NULL"
                ddl_lines.append(line)

    return f'CREATE TABLE {table} (\n  ' + ",\n  ".join(ddl_lines) + "\n);"

def sqlserver_to_postgres_type(sql_type: str) -> str:
    mapping = {
        "int": "integer",
        "bigint": "bigint",
        "smallint": "smallint",
        "varchar": "text",
        "nvarchar": "text",
        "datetime": "timestamptz",
        "bit": "boolean",
        "decimal": "numeric",
        "float": "double precision"
    }
    return mapping.get(sql_type.lower(), "text")

@task
async def recreate_table(conn_str: str, ddl: str, table: str):
    conn = await asyncpg.connect(conn_str)
    async with conn.transaction():
        await conn.execute(f'DROP TABLE IF EXISTS {table} CASCADE;')
        await conn.execute(ddl)
    await conn.close()

@task
async def fetch_chunk_postgres(conn_str: str, table: str, offset: int, limit: int):
    conn = await asyncpg.connect(conn_str)
    try:
        query = f'SELECT * FROM {table} OFFSET {offset} LIMIT {limit}'
        rows = await conn.fetch(query)
        return rows
    finally:
        await conn.close()

@task
async def fetch_chunk_sqlserver(conn_str: str, table: str, offset: int, limit: int):
    schema, name = table.split(".")
    rows = []
    async with aioodbc.connect(dsn=conn_str, autocommit=True) as conn:
        async with conn.cursor() as cur:
            await cur.execute(f"""
                SELECT * FROM {schema}.{name}
                ORDER BY (SELECT NULL)
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, (offset, limit))
            col_names = [d[0] for d in cur.description]
            async for row in cur:
                rows.append(dict(zip(col_names, row)))
    return rows

@task
async def insert_chunk_pg(conn_str: str, table: str, rows: List[Union[asyncpg.Record, Dict]]) -> int:
    if not rows:
        return 0
    conn = await asyncpg.connect(conn_str)
    try:
        col_names = list(rows[0].keys())
        placeholders = ", ".join(f"${i+1}" for i in range(len(col_names)))
        insert_stmt = f'INSERT INTO {table} ({", ".join(col_names)}) VALUES ({placeholders})'

        async with conn.transaction():
            for row in rows:
                values = list(row.values()) if isinstance(row, dict) else list(row)
                await conn.execute(insert_stmt, *values)
        return len(rows)
    finally:
        await conn.close()

async def copy_table(entry, src_type, src_conn, dst_conn, src_table, dst_table, logger):
    try:
        logger.info(f"Preparing {dst_table} from {src_table} ({src_type})")

        try:
            if src_type == "postgres":
                ddl = await extract_postgres_schema.fn(src_conn, src_table)
            else:
                ddl = await extract_sqlserver_schema.fn(src_conn, dst_table)

            ddl = ddl.replace(src_table, dst_table)
        except Exception as e:
            logger.error(f"Failed to extract schema from source DB for {src_table}: {e}")
            return

        try:
            await recreate_table.fn(dst_conn, ddl, dst_table)
        except Exception as e:
            logger.error(f"Failed to create target table {dst_table}: {e}")
            return

        offset = 0
        total = 0
        while True:
            try:
                if src_type == "postgres":
                    rows = await fetch_chunk_postgres.fn(src_conn, src_table, offset, CHUNK_SIZE)
                else:
                    rows = await fetch_chunk_sqlserver.fn(src_conn, src_table, offset, CHUNK_SIZE)
            except Exception as e:
                logger.error(f"Failed to fetch from source {src_table} at offset {offset}: {e}")
                return

            if not rows:
                break

            try:
                inserted = await insert_chunk_pg.fn(dst_conn, dst_table, rows)
            except Exception as e:
                logger.error(f"Failed to insert into {dst_table}: {e}")
                return

            offset += CHUNK_SIZE
            total += inserted
            logger.info(f"[{src_table} → {dst_table}] Copied {inserted} rows (offset: {offset})")

        logger.info(f"Done {src_table} → {dst_table} | Total rows: {total}")
    except Exception as e:
        logger.error(f"Unexpected error during migration {src_table} → {dst_table}: {e}")

@flow(name="Multi-DB Table Copy Flow")
async def copy_multi_db_tables():
    logger = get_run_logger()
    config = load_config()

    for db_entry in config.get("databases", []):
        if not db_entry.get("enabled", True):
            continue

        src_type = db_entry.get("source_type", "postgres").lower()
        db_name = db_entry.get("name", "unnamed")
        src_conn = db_entry["source_db"]
        dst_conn = db_entry["target_db"]
        tables = db_entry.get("tables", [])

        logger.info(f"--- Starting DB Group: {db_name} ({src_type}) ---")

        await asyncio.gather(*[
            copy_table(db_entry, src_type, src_conn, dst_conn, t["source"], t["dest"], logger)
            for t in tables if t.get("enabled", True)
        ])

        logger.info(f"--- Finished DB Group: {db_name} ---")

if __name__ == "__main__":
    asyncio.run(copy_multi_db_tables())


