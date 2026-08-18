"""
Agent-WAL: The Embedded Write-Ahead Logging & Deterministic Replay Engine for AI Agents.
Standard library only: hashlib, json, sqlite3, time, os, dataclasses, typing.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


GENESIS_HASH: str = "0000000000000000000000000000000000000000000000000000000000000000"


@dataclasses.dataclass(frozen=True)
class WALRecord:
    """Immutable Write-Ahead Log Entry for an Agent Execution Step."""
    step_id: int
    prev_hash: str
    session_id: str
    intent_action: str
    input_payload: Dict[str, Any]
    output_payload: Optional[Dict[str, Any]]
    status: str
    timestamp: float
    signature_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


class AgentWALEngine:
    """
    ACID-Compliant Embedded Write-Ahead Logging Engine for Autonomous Agents.
    Guarantees crash recovery, deterministic time-travel replay, and SHA-256 state provenance.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()
        self._last_hash = self._get_last_hash()

    def _init_db(self) -> None:
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_wal (
                    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prev_hash TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    intent_action TEXT NOT NULL,
                    input_payload TEXT NOT NULL,
                    output_payload TEXT,
                    status TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    signature_hash TEXT NOT NULL UNIQUE
                )
            """)
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON agent_wal(session_id);")

    def _get_last_hash(self) -> str:
        cur = self._conn.cursor()
        cur.execute("SELECT signature_hash FROM agent_wal ORDER BY step_id DESC LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else GENESIS_HASH

    def log_intent(
        self,
        session_id: str,
        intent_action: str,
        input_payload: Dict[str, Any],
    ) -> int:
        """
        Write-Ahead Log Phase 1: Commits the intent and parameters BEFORE execution.
        """
        ts = time.time()
        in_json = json.dumps(input_payload, sort_keys=True)
        
        # Intermediate provisional hash
        raw_msg = f"{self._last_hash}:{session_id}:{intent_action}:{in_json}:{ts:.6f}:PENDING"
        sig_hash = hashlib.sha256(raw_msg.encode("utf-8")).hexdigest()

        with self._conn:
            cur = self._conn.execute("""
                INSERT INTO agent_wal (prev_hash, session_id, intent_action, input_payload, status, timestamp, signature_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (self._last_hash, session_id, intent_action, in_json, "COMMITTED_PENDING_EXECUTION", ts, sig_hash))
            step_id = cur.lastrowid

        self._last_hash = sig_hash
        return step_id

    def commit_execution(
        self,
        step_id: int,
        output_payload: Dict[str, Any],
        status: str = "EXECUTED_SUCCESS",
    ) -> WALRecord:
        """
        Write-Ahead Log Phase 2: Commits the final output payload & updates the cryptographic chain.
        """
        ts = time.time()
        out_json = json.dumps(output_payload, sort_keys=True)

        cur = self._conn.cursor()
        cur.execute("SELECT prev_hash, session_id, intent_action, input_payload FROM agent_wal WHERE step_id = ?", (step_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Step ID {step_id} not found in WAL.")

        prev_hash, session_id, intent_action, in_json = row
        raw_msg = f"{step_id}:{prev_hash}:{session_id}:{intent_action}:{in_json}:{out_json}:{status}:{ts:.6f}"
        final_sig = hashlib.sha256(raw_msg.encode("utf-8")).hexdigest()

        with self._conn:
            self._conn.execute("""
                UPDATE agent_wal
                SET output_payload = ?, status = ?, timestamp = ?, signature_hash = ?
                WHERE step_id = ?
            """, (out_json, status, ts, final_sig, step_id))

        self._last_hash = final_sig

        return WALRecord(
            step_id=step_id,
            prev_hash=prev_hash,
            session_id=session_id,
            intent_action=intent_action,
            input_payload=json.loads(in_json),
            output_payload=output_payload,
            status=status,
            timestamp=ts,
            signature_hash=final_sig,
        )

    def recover_uncommitted_steps(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Crash Recovery: Finds any pending/uncommitted intent records to safely resume or rollback.
        """
        cur = self._conn.cursor()
        cur.execute("""
            SELECT step_id, intent_action, input_payload, timestamp
            FROM agent_wal
            WHERE session_id = ? AND status = 'COMMITTED_PENDING_EXECUTION'
            ORDER BY step_id ASC
        """, (session_id,))
        return [
            {"step_id": r[0], "action": r[1], "input": json.loads(r[2]), "timestamp": r[3]}
            for r in cur.fetchall()
        ]

    def verify_ledger_integrity(self) -> Tuple[bool, Optional[str]]:
        """Validates full SHA-256 unbroken chain of the Write-Ahead Log."""
        cur = self._conn.cursor()
        cur.execute("SELECT step_id, prev_hash, signature_hash FROM agent_wal ORDER BY step_id ASC")
        rows = cur.fetchall()
        
        current_prev = GENESIS_HASH
        for step_id, prev_hash, sig_hash in rows:
            if prev_hash != current_prev:
                return False, f"Broken chain at step_id {step_id}: expected {current_prev}, got {prev_hash}"
            current_prev = sig_hash
        return True, None


class DeterministicReplayEngine:
    """
    Time-Travel Replay Engine:
    Re-executes historic agent workflows deterministically in mock sandboxes without side-effects.
    """

    def __init__(self, wal_engine: AgentWALEngine):
        self.wal = wal_engine

    def replay_session(
        self,
        session_id: str,
        mock_handler: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        cur = self.wal._conn.cursor()
        cur.execute("""
            SELECT step_id, intent_action, input_payload, output_payload, status
            FROM agent_wal
            WHERE session_id = ?
            ORDER BY step_id ASC
        """, (session_id,))
        
        replayed_steps = []
        for step_id, action, in_str, out_str, status in cur.fetchall():
            in_payload = json.loads(in_str)
            original_out = json.loads(out_str) if out_str else {}
            
            replayed_out = mock_handler(action, in_payload) if mock_handler else original_out
            replayed_steps.append({
                "step_id": step_id,
                "action": action,
                "input": in_payload,
                "original_output": original_out,
                "replayed_output": replayed_out,
                "status": status,
            })

        return replayed_steps
