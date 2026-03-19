import sqlite3
import secrets
import hashlib
import os
from datetime import datetime, timedelta, date as dt_date
from typing import Optional, List, Dict, Tuple

DB_PATH = 'auth/auth.db'

def get_db():
    # Ensure auth directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            prefix TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            valid_until TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()

def generate_key() -> str:
    return f"sk_{secrets.token_urlsafe(32)}"

def create_api_key(name: str, valid_until: Optional[str] = None) -> str:
    """
    Creates a new API key.
    valid_until: 'YYYY-MM-DD' string or None
    Returns the raw key (to show to user once).
    """
    init_db()
    raw_key = generate_key()
    hashed = hash_key(raw_key)
    prefix = raw_key[:6]
    
    # Parse date if provided
    valid_dt = None
    if valid_until:
        try:
            # Tenta formatos comuns
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                try:
                    valid_dt = datetime.strptime(valid_until, fmt)
                    # Define para o final do dia
                    valid_dt = valid_dt.replace(hour=23, minute=59, second=59)
                    break
                except ValueError:
                    continue
            
            if not valid_dt:
                raise ValueError(f"Formato de data inválido: {valid_until}")
                
        except Exception as e:
            print(f"Erro ao processar data: {e}")
            raise e

    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO api_keys (key_hash, name, prefix, valid_until) VALUES (?, ?, ?, ?)',
            (hashed, name, prefix, valid_dt)
        )
        conn.commit()
    finally:
        conn.close()
        
    return raw_key

def delete_api_key(key_id: int) -> bool:
    init_db()
    conn = get_db()
    try:
        cursor = conn.execute('DELETE FROM api_keys WHERE id = ?', (key_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def delete_all_api_keys() -> int:
    """Delete all API keys. Returns the number of keys deleted."""
    init_db()
    conn = get_db()
    try:
        cursor = conn.execute('DELETE FROM api_keys')
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()

def list_api_keys() -> List[dict]:
    init_db()
    conn = get_db()
    try:
        rows = conn.execute('SELECT id, name, prefix, created_at, valid_until, is_active FROM api_keys').fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def validate_api_key(raw_key: str) -> bool:
    if not raw_key:
        return False

    # Modo Cloud Run: valida contra AUTH_API_KEY (lista separada por vírgula)
    env_keys = os.environ.get('AUTH_API_KEY', '')
    if env_keys:
        return raw_key in [k.strip() for k in env_keys.split(',') if k.strip()]

    # Modo local: valida contra SQLite
    init_db()
    hashed = hash_key(raw_key)
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT valid_until, is_active FROM api_keys WHERE key_hash = ?', 
            (hashed,)
        ).fetchone()
        
        if not row:
            return False
            
        if not row['is_active']:
            return False
            
        if row['valid_until']:
            valid_until = datetime.fromisoformat(row['valid_until']) if isinstance(row['valid_until'], str) else row['valid_until']
            if datetime.now() > valid_until:
                return False
                
        return True
    finally:
        conn.close()
