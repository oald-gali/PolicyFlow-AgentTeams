from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock

from .models import CaseLessonReviewRecord, CaseMemoryEntry, RunRecord, ToolReceipt


class RunNotFoundError(KeyError):
    pass


class EffectConflictError(RuntimeError):
    pass


class LessonReviewConflictError(RuntimeError):
    pass


class RunStore:
    """Small SQLite checkpoint store used by the offline MVP runtime."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
              run_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tool_effects (
              idempotency_key TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              tool_name TEXT NOT NULL,
              receipt_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS case_lesson_reviews (
              lesson_id TEXT PRIMARY KEY,
              source_run_id TEXT NOT NULL,
              decision TEXT NOT NULL,
              candidate_hash TEXT NOT NULL,
              token_fingerprint TEXT NOT NULL UNIQUE,
              review_json TEXT NOT NULL,
              reviewed_at TEXT NOT NULL,
              FOREIGN KEY(source_run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS case_memory_entries (
              dataset_revision INTEGER PRIMARY KEY,
              lesson_id TEXT NOT NULL UNIQUE,
              entry_json TEXT NOT NULL,
              added_at TEXT NOT NULL,
              FOREIGN KEY(lesson_id) REFERENCES case_lesson_reviews(lesson_id)
            );
            """
        )
        self._connection.commit()

    def save_run(self, run: RunRecord) -> None:
        payload = run.model_dump_json()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO runs(run_id, status, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  status=excluded.status,
                  payload_json=excluded.payload_json,
                  updated_at=excluded.updated_at
                """,
                (
                    run.run_id,
                    run.status.value,
                    payload,
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                ),
            )
            self._connection.commit()

    def get_run(self, run_id: str) -> RunRecord:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return RunRecord.model_validate_json(row["payload_json"])

    def list_runs(self, limit: int = 20) -> list[RunRecord]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM runs ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [RunRecord.model_validate_json(row["payload_json"]) for row in rows]

    def save_effect(self, run_id: str, receipt: ToolReceipt) -> ToolReceipt:
        """Persist a side effect exactly once and return the canonical receipt."""
        with self._lock:
            row = self._connection.execute(
                "SELECT receipt_json FROM tool_effects WHERE idempotency_key = ?",
                (receipt.idempotency_key,),
            ).fetchone()
            if row is not None:
                existing = ToolReceipt.model_validate_json(row["receipt_json"])
                if (
                    existing.tool_name != receipt.tool_name
                    or not existing.arguments_hash
                    or existing.arguments_hash != receipt.arguments_hash
                ):
                    raise EffectConflictError(
                        "idempotency key is already bound to different or unverifiable arguments"
                    )
                return existing
            self._connection.execute(
                """
                INSERT INTO tool_effects(idempotency_key, run_id, tool_name, receipt_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    receipt.idempotency_key,
                    run_id,
                    receipt.tool_name,
                    receipt.model_dump_json(),
                    receipt.created_at.isoformat(),
                ),
            )
            self._connection.commit()
        return receipt

    def get_effect(self, idempotency_key: str) -> ToolReceipt | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT receipt_json FROM tool_effects WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return ToolReceipt.model_validate_json(row["receipt_json"]) if row else None

    def get_lesson_review(self, lesson_id: str) -> CaseLessonReviewRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT review_json FROM case_lesson_reviews WHERE lesson_id = ?",
                (lesson_id,),
            ).fetchone()
        return CaseLessonReviewRecord.model_validate_json(row["review_json"]) if row else None

    def case_memory_revision(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(dataset_revision), 0) AS revision "
                "FROM case_memory_entries"
            ).fetchone()
        return int(row["revision"])

    def list_case_memory_entries(self) -> list[CaseMemoryEntry]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT entry_json FROM case_memory_entries "
                "ORDER BY dataset_revision ASC"
            ).fetchall()
        return [CaseMemoryEntry.model_validate_json(row["entry_json"]) for row in rows]

    def case_memory_snapshot(self) -> tuple[int, list[CaseMemoryEntry]]:
        """Return one internally consistent view for APIs and audit exports."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT entry_json FROM case_memory_entries "
                "ORDER BY dataset_revision ASC"
            ).fetchall()
            entries = [
                CaseMemoryEntry.model_validate_json(row["entry_json"]) for row in rows
            ]
        revision = entries[-1].dataset_revision if entries else 0
        return revision, entries

    def commit_lesson_review(
        self,
        *,
        run: RunRecord,
        review: CaseLessonReviewRecord,
        entry: CaseMemoryEntry | None,
    ) -> None:
        """Atomically persist the human review, optional dataset entry and Run Trace."""

        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                existing = self._connection.execute(
                    "SELECT decision FROM case_lesson_reviews WHERE lesson_id = ?",
                    (review.lesson_id,),
                ).fetchone()
                if existing is not None:
                    raise LessonReviewConflictError(
                        f"case lesson already reviewed as {existing['decision']}"
                    )
                row = self._connection.execute(
                    "SELECT COALESCE(MAX(dataset_revision), 0) AS revision "
                    "FROM case_memory_entries"
                ).fetchone()
                current_revision = int(row["revision"])
                if review.base_revision != current_revision:
                    raise LessonReviewConflictError(
                        "case-memory dataset changed; issue a fresh review token"
                    )
                expected_revision = current_revision + 1 if review.decision == "approve" else None
                if review.target_revision != expected_revision:
                    raise LessonReviewConflictError(
                        "review token target revision is stale or invalid"
                    )

                self._connection.execute(
                    """
                    INSERT INTO case_lesson_reviews(
                      lesson_id, source_run_id, decision, candidate_hash,
                      token_fingerprint, review_json, reviewed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review.lesson_id,
                        review.source_run_id,
                        review.decision,
                        review.candidate_hash,
                        review.token_fingerprint,
                        review.model_dump_json(),
                        review.reviewed_at.isoformat(),
                    ),
                )
                if review.decision == "approve":
                    if entry is None or entry.dataset_revision != expected_revision:
                        raise LessonReviewConflictError(
                            "approved review requires the exact next dataset revision"
                        )
                    self._connection.execute(
                        """
                        INSERT INTO case_memory_entries(
                          dataset_revision, lesson_id, entry_json, added_at
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            entry.dataset_revision,
                            entry.lesson_id,
                            entry.model_dump_json(),
                            entry.added_at.isoformat(),
                        ),
                    )
                elif entry is not None:
                    raise LessonReviewConflictError(
                        "rejected lesson cannot enter the case-memory dataset"
                    )

                self._connection.execute(
                    """
                    INSERT INTO runs(run_id, status, payload_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                      status=excluded.status,
                      payload_json=excluded.payload_json,
                      updated_at=excluded.updated_at
                    """,
                    (
                        run.run_id,
                        run.status.value,
                        run.model_dump_json(),
                        run.created_at.isoformat(),
                        run.updated_at.isoformat(),
                    ),
                )
                self._connection.commit()
            except LessonReviewConflictError:
                self._connection.rollback()
                raise
            except sqlite3.IntegrityError as error:
                self._connection.rollback()
                raise LessonReviewConflictError(
                    "case lesson review conflicts with persisted state"
                ) from error
            except Exception:
                self._connection.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()
