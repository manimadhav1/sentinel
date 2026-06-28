from __future__ import annotations
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

from config import DATABASE_PATH
from utils.logger import get_logger

logger = get_logger("database_service")


# ── Schema ─────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number        TEXT UNIQUE NOT NULL,
    employee_id           TEXT NOT NULL,
    employee_name         TEXT NOT NULL,
    client_id             TEXT NOT NULL,
    client_name           TEXT NOT NULL,
    contract_id           TEXT NOT NULL,
    billing_period_start  TEXT NOT NULL,
    billing_period_end    TEXT NOT NULL,
    invoice_date          TEXT NOT NULL,
    due_date              TEXT NOT NULL,
    currency              TEXT NOT NULL,
    total_amount          REAL NOT NULL,
    total_amount_inr      REAL NOT NULL,
    gst_amount            REAL NOT NULL DEFAULT 0,
    regular_hours         REAL NOT NULL DEFAULT 0,
    overtime_hours        REAL NOT NULL DEFAULT 0,
    status                TEXT NOT NULL DEFAULT 'GENERATED',
    pdf_path              TEXT,
    excel_path            TEXT,
    invoice_json          TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_queue (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file       TEXT,
    employee_name     TEXT,
    client_name       TEXT,
    stage             TEXT NOT NULL,
    confidence        REAL NOT NULL,
    priority          TEXT NOT NULL DEFAULT 'NORMAL',
    ambiguous_fields  TEXT,
    errors            TEXT,
    warnings          TEXT,
    raw_data          TEXT,
    status            TEXT NOT NULL DEFAULT 'PENDING',
    reviewer_notes    TEXT,
    resolved_at       TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type    TEXT NOT NULL,
    invoice_number TEXT,
    stage         TEXT,
    status        TEXT,
    confidence    REAL,
    message       TEXT,
    metadata      TEXT,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_invoices_employee   ON invoices(employee_id);
CREATE INDEX IF NOT EXISTS idx_invoices_client     ON invoices(client_id);
CREATE INDEX IF NOT EXISTS idx_invoices_period     ON invoices(billing_period_start, billing_period_end);
CREATE INDEX IF NOT EXISTS idx_invoices_status     ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_review_status       ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_audit_invoice       ON audit_log(invoice_number);
"""


@contextmanager
def _conn():
    con = sqlite3.connect(str(DATABASE_PATH))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


class DatabaseService:

    @staticmethod
    def initialise() -> None:
        """Create all tables if they don't exist."""
        with _conn() as con:
            con.executescript(SCHEMA)
        logger.info(f"Database initialised at {DATABASE_PATH}")

    # ── Invoice CRUD ───────────────────────────────────────────────────────────

    @staticmethod
    def save_invoice(invoice_data: dict) -> int:
        """Insert a new invoice. Returns the row id."""
        now = datetime.utcnow().isoformat()
        billing = invoice_data.get("billing", {})
        with _conn() as con:
            cur = con.execute("""
                INSERT INTO invoices (
                    invoice_number, employee_id, employee_name,
                    client_id, client_name, contract_id,
                    billing_period_start, billing_period_end,
                    invoice_date, due_date, currency,
                    total_amount, total_amount_inr, gst_amount,
                    regular_hours, overtime_hours,
                    status, pdf_path, excel_path,
                    invoice_json, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                invoice_data["invoice_number"],
                invoice_data["employee_id"],
                invoice_data["employee_name"],
                invoice_data["client_id"],
                invoice_data["client_name"],
                invoice_data["contract_id"],
                invoice_data["billing_period_start"],
                invoice_data["billing_period_end"],
                invoice_data["invoice_date"],
                invoice_data["due_date"],
                billing.get("currency", "INR"),
                billing.get("total_amount", 0),
                billing.get("total_amount_inr", 0),
                billing.get("gst_amount", 0),
                billing.get("regular_hours", 0),
                billing.get("overtime_hours", 0),
                invoice_data.get("status", "GENERATED"),
                invoice_data.get("pdf_path"),
                invoice_data.get("excel_path"),
                json.dumps(invoice_data),
                now, now,
            ))
        logger.info(f"Invoice saved: {invoice_data['invoice_number']}")
        return cur.lastrowid

    @staticmethod
    def get_invoice(invoice_number: str) -> dict | None:
        with _conn() as con:
            row = con.execute(
                "SELECT * FROM invoices WHERE invoice_number = ?",
                (invoice_number,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def update_invoice_status(invoice_number: str, status: str) -> None:
        now = datetime.utcnow().isoformat()
        with _conn() as con:
            con.execute(
                "UPDATE invoices SET status=?, updated_at=? WHERE invoice_number=?",
                (status, now, invoice_number),
            )
        logger.info(f"Invoice {invoice_number} → status={status}")

    @staticmethod
    def list_invoices(
        client_id: str | None = None,
        employee_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        query  = "SELECT * FROM invoices WHERE 1=1"
        params: list = []
        if client_id:
            query += " AND client_id=?"; params.append(client_id)
        if employee_id:
            query += " AND employee_id=?"; params.append(employee_id)
        if status:
            query += " AND status=?"; params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with _conn() as con:
            rows = con.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def is_duplicate(
        employee_id: str, client_id: str,
        billing_period_start: str, billing_period_end: str,
    ) -> dict | None:
        """Returns existing invoice dict if duplicate found, else None."""
        with _conn() as con:
            row = con.execute("""
                SELECT * FROM invoices
                WHERE employee_id=? AND client_id=?
                  AND billing_period_start=? AND billing_period_end=?
            """, (employee_id, client_id,
                  billing_period_start, billing_period_end)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def next_sequence(client_id: str) -> int:
        """Returns next invoice sequence number for a client."""
        with _conn() as con:
            row = con.execute(
                "SELECT COUNT(*) as cnt FROM invoices WHERE client_id=?",
                (client_id,)
            ).fetchone()
        return (row["cnt"] or 0) + 1

    # ── Review Queue ───────────────────────────────────────────────────────────

    @staticmethod
    def add_to_review_queue(
        stage: str,
        confidence: float,
        errors: list,
        warnings: list,
        ambiguous_fields: list,
        raw_data: dict,
        source_file: str = "",
        employee_name: str = "",
        client_name: str = "",
        priority: str = "NORMAL",
    ) -> int:
        now = datetime.utcnow().isoformat()
        with _conn() as con:
            cur = con.execute("""
                INSERT INTO review_queue (
                    source_file, employee_name, client_name,
                    stage, confidence, priority,
                    ambiguous_fields, errors, warnings,
                    raw_data, status, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                source_file, employee_name, client_name,
                stage, confidence, priority,
                json.dumps(ambiguous_fields),
                json.dumps(errors),
                json.dumps(warnings),
                json.dumps(raw_data),
                "PENDING", now,
            ))
        logger.info(f"Added to review queue: stage={stage} confidence={confidence:.2f}")
        return cur.lastrowid

    @staticmethod
    def get_review_queue(status: str = "PENDING") -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM review_queue WHERE status=? ORDER BY confidence ASC, created_at ASC",
                (status,)
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def resolve_review_item(
        item_id: int,
        status: str = "RESOLVED",
        resolver: str = "",
        notes: str = "",
    ) -> None:
        now = datetime.utcnow().isoformat()
        resolved_status = status if status in ("APPROVED", "REJECTED", "RESOLVED") else "RESOLVED"
        note_text = f"[{resolver}] {notes}".strip(" []") if resolver else notes
        with _conn() as con:
            con.execute("""
                UPDATE review_queue
                SET status=?, reviewer_notes=?, resolved_at=?
                WHERE id=?
            """, (resolved_status, note_text, now, item_id))
        logger.info(f"Review item {item_id} → {resolved_status}")

    # ── Audit Log ──────────────────────────────────────────────────────────────

    @staticmethod
    def log_event(
        event_type: str,
        invoice_number: str = "",
        stage: str = "",
        status: str = "",
        confidence: float = 1.0,
        message: str = "",
        metadata: dict | None = None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        with _conn() as con:
            con.execute("""
                INSERT INTO audit_log
                (event_type, invoice_number, stage, status,
                 confidence, message, metadata, created_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                event_type, invoice_number, stage, status,
                confidence, message,
                json.dumps(metadata or {}), now,
            ))

    @staticmethod
    def get_audit_log(invoice_number: str) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM audit_log WHERE invoice_number=? ORDER BY created_at",
                (invoice_number,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Dashboard stats ────────────────────────────────────────────────────────

    @staticmethod
    def get_stats() -> dict:
        with _conn() as con:
            total = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
            by_status = con.execute(
                "SELECT status, COUNT(*) as cnt FROM invoices GROUP BY status"
            ).fetchall()
            total_billed = con.execute(
                "SELECT SUM(total_amount_inr) FROM invoices"
            ).fetchone()[0] or 0
            pending_review = con.execute(
                "SELECT COUNT(*) FROM review_queue WHERE status='PENDING'"
            ).fetchone()[0]
            by_client = con.execute("""
                SELECT client_name, COUNT(*) as cnt, SUM(total_amount_inr) as total
                FROM invoices GROUP BY client_id ORDER BY total DESC LIMIT 10
            """).fetchall()

        return {
            "total_invoices":   total,
            "total_billed_inr": round(total_billed, 2),
            "pending_review":   pending_review,
            "by_status":        {r["status"]: r["cnt"] for r in by_status},
            "top_clients":      [dict(r) for r in by_client],
        }
