# -*- coding: utf-8 -*-
"""
MCP 기반 SQLite 재고 관리 예제

- 판매 물품 정보 테이블: id, name, price, stock, created_at, updated_at
- 재고 변동 내역 테이블: id, item_id, delta, reason, created_at

실행/연결 방법:
1. HTTP 서버 모드 (외부 MCP 클라이언트, Windsurf 등에서 접속)
   $ uv run main.py -- --http :8080
   → Windsurf에서 http://localhost:8080/mcp 로 연결

2. STDIO 모드 (로컬 MCP 클라이언트, uvx 등에서 연결)
   $ uv run main.py
   → uvx 등에서 stdio 모드로 연결
"""
import sqlite3
import pendulum
from mcp.server.fastmcp import FastMCP
from typing import Optional
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "inventory.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 판매 물품 정보 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        price INTEGER NOT NULL,
        stock INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )''')
    # 재고 변동 내역 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS stock_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        delta INTEGER NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(item_id) REFERENCES items(id)
    )''')
    conn.commit()
    # 예시 데이터 자동 생성
    c.execute('SELECT COUNT(*) FROM items')
    if c.fetchone()[0] == 0:
        now = pendulum.now().to_datetime_string()
        c.execute('INSERT INTO items (name, price, stock, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
                  ("노트북", 1200000, 10, now, now))
        c.execute('INSERT INTO items (name, price, stock, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
                  ("마우스", 25000, 50, now, now))
        c.execute('INSERT INTO items (name, price, stock, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
                  ("키보드", 70000, 30, now, now))
        conn.commit()
    conn.close()

init_db()

mcp = FastMCP("inventory-mcp")

@mcp.tool()
def get_item_stock_price(name: str) -> str:
    """물품 이름으로 가격과 재고를 조회합니다."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT price, stock FROM items WHERE name=?', (name,))
    row = c.fetchone()
    conn.close()
    if row:
        return f"{name} | 가격: {row[0]}원 | 재고: {row[1]}개"
    else:
        return f"'{name}'(을)를 찾을 수 없습니다."

@mcp.tool()
def change_item_stock(name: str, delta: int, reason: Optional[str] = None) -> str:
    """물품 이름, 변화량, 사유를 입력받아 재고를 변경합니다."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, stock FROM items WHERE name=?', (name,))
    row = c.fetchone()
    if not row:
        conn.close()
        return f"'{name}'(을)를 찾을 수 없습니다."
    item_id, stock = row
    new_stock = stock + delta
    if new_stock < 0:
        conn.close()
        return f"재고 부족! 현재 재고: {stock}개"
    now = pendulum.now().to_datetime_string()
    c.execute('UPDATE items SET stock=?, updated_at=? WHERE id=?', (new_stock, now, item_id))
    c.execute('INSERT INTO stock_history (item_id, delta, reason, created_at) VALUES (?, ?, ?, ?)',
              (item_id, delta, reason or '', now))
    conn.commit()
    conn.close()
    return f"'{name}' 재고가 {stock}개 → {new_stock}개로 변경되었습니다. (변동: {delta}, 사유: {reason or '-'} )"

@mcp.tool()
def get_stock_history_by_date(date: str) -> str:
    """입력한 날짜(YYYY-MM-DD)의 재고 변동 내역을 조회합니다."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 날짜 파싱 및 범위
    try:
        start = pendulum.parse(date).start_of('day').to_datetime_string()
        end = pendulum.parse(date).end_of('day').to_datetime_string()
    except Exception:
        return "날짜 형식이 잘못되었습니다. YYYY-MM-DD로 입력하세요."
    c.execute('''
        SELECT items.name, stock_history.delta, stock_history.reason, stock_history.created_at
        FROM stock_history
        JOIN items ON stock_history.item_id = items.id
        WHERE stock_history.created_at BETWEEN ? AND ?
        ORDER BY stock_history.created_at ASC
    ''', (start, end))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return f"{date}의 재고 변동 내역이 없습니다."
    result = [f"[{r[3]}] {r[0]} | 변화량: {r[1]} | 사유: {r[2] or '-'}" for r in rows]
    return "\n".join(result)

if __name__ == "__main__":
    import sys
    # HTTP 서버 모드: uv run main.py -- --http :8080
    # STDIO 모드: uv run main.py
    if '--http' in sys.argv:
        port = 8080
        for i, arg in enumerate(sys.argv):
            if arg == '--http' and i + 1 < len(sys.argv):
                try:
                    port = int(sys.argv[i + 1].lstrip(':'))
                except Exception:
                    pass
        print(f"[MCP] HTTP 서버 모드로 실행 중... (http://localhost:{port}/mcp)")
        mcp.run(http=f"0.0.0.0:{port}")
    else:
        print("[MCP] STDIO 모드로 실행 중...")
        mcp.run()
