#!/usr/bin/env python3
"""
usage_tracker.py - Token and cost tracking for Auto Chat

Tracks token usage and costs for different API providers, stores data
in SQLite database, and provides usage statistics.
"""

import sqlite3
import logging
from contextlib import closing
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass

log = logging.getLogger("usage_tracker")

# Database file
DB_FILE = "usage_data.db"

# Pricing per 1M tokens (input/output) - as of 2024
PRICING = {
    "openai": {
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
        "gpt-4o": {"input": 5.0, "output": 15.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    },
    "openrouter": {
        # Generic pricing - actual prices vary by model
        "default": {"input": 1.0, "output": 2.0}
    },
    "ollama": {
        "default": {"input": 0.0, "output": 0.0}  # Local, free
    },
    "lmstudio": {
        "default": {"input": 0.0, "output": 0.0}  # Local, free
    }
}


@dataclass
class UsageRecord:
    """Represents a usage record for a single API call."""
    timestamp: str
    provider: str
    model: str
    persona: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    conversation_id: Optional[str] = None


class UsageTracker:
    """Tracks and stores token usage and costs."""

    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        self.current_session_usage: Dict[str, Any] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost": 0.0
        }
        self.initialize_database()

    def _connect(self):
        """Open a connection that is guaranteed to close when the block exits."""
        return closing(sqlite3.connect(self.db_file))

    def initialize_database(self):
        """Initialize the SQLite database with required tables."""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS usage (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        persona TEXT,
                        input_tokens INTEGER NOT NULL,
                        output_tokens INTEGER NOT NULL,
                        total_tokens INTEGER NOT NULL,
                        estimated_cost REAL NOT NULL,
                        conversation_id TEXT
                    )
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_timestamp ON usage(timestamp)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_provider ON usage(provider)
                """)

                conn.commit()
            log.info(f"Usage database initialized at {self.db_file}")
        except Exception as e:
            log.error(f"Error initializing database: {e}")

    def calculate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate estimated cost based on token usage."""
        provider = provider.lower()

        provider_pricing = PRICING.get(provider, {})

        if model in provider_pricing:
            pricing = provider_pricing[model]
        else:
            # Partial match (e.g., "gpt-4" in "gpt-4-0125-preview"),
            # falling back to the provider default
            pricing = next(
                (
                    provider_pricing[model_key]
                    for model_key in provider_pricing
                    if model_key in model.lower()
                ),
                None,
            )
            if pricing is None:
                pricing = provider_pricing.get("default", {"input": 0.0, "output": 0.0})

        # Pricing is per 1M tokens
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost

    def record_usage(
        self,
        provider: str,
        model: str,
        persona: str,
        input_tokens: int,
        output_tokens: int,
        conversation_id: Optional[str] = None
    ):
        """Record a usage event."""
        try:
            total_tokens = input_tokens + output_tokens
            estimated_cost = self.calculate_cost(provider, model, input_tokens, output_tokens)

            # Update session totals
            self.current_session_usage["input_tokens"] += input_tokens
            self.current_session_usage["output_tokens"] += output_tokens
            self.current_session_usage["total_tokens"] += total_tokens
            self.current_session_usage["estimated_cost"] += estimated_cost

            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO usage (
                        timestamp, provider, model, persona,
                        input_tokens, output_tokens, total_tokens,
                        estimated_cost, conversation_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(),
                    provider,
                    model,
                    persona,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    estimated_cost,
                    conversation_id
                ))
                conn.commit()

            log.debug(f"Recorded usage: {total_tokens} tokens, ${estimated_cost:.6f}")

            return estimated_cost
        except Exception as e:
            log.error(f"Error recording usage: {e}")
            return 0.0

    def get_session_usage(self) -> Dict[str, Any]:
        """Get usage statistics for the current session."""
        return self.current_session_usage.copy()

    def reset_session_usage(self):
        """Reset session usage counters."""
        self.current_session_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost": 0.0
        }
        log.info("Session usage reset")

    def get_total_usage(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get total usage statistics with optional filters."""
        empty = {
            "call_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost": 0.0
        }
        try:
            query = """
                SELECT
                    COUNT(*) as call_count,
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output,
                    SUM(total_tokens) as total_tokens,
                    SUM(estimated_cost) as total_cost
                FROM usage
                WHERE 1=1
            """
            params = []

            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)

            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)

            if provider:
                query += " AND provider = ?"
                params.append(provider.lower())

            with self._connect() as conn:
                row = conn.execute(query, params).fetchone()

            if row:
                return {
                    "call_count": row[0] or 0,
                    "input_tokens": row[1] or 0,
                    "output_tokens": row[2] or 0,
                    "total_tokens": row[3] or 0,
                    "estimated_cost": row[4] or 0.0
                }
            return dict(empty)
        except Exception as e:
            log.error(f"Error getting total usage: {e}")
            return dict(empty)

    def get_usage_by_provider(self) -> List[Dict[str, Any]]:
        """Get usage statistics grouped by provider."""
        try:
            with self._connect() as conn:
                rows = conn.execute("""
                    SELECT
                        provider,
                        COUNT(*) as call_count,
                        SUM(input_tokens) as total_input,
                        SUM(output_tokens) as total_output,
                        SUM(total_tokens) as total_tokens,
                        SUM(estimated_cost) as total_cost
                    FROM usage
                    GROUP BY provider
                    ORDER BY total_cost DESC
                """).fetchall()

            return [
                {
                    "provider": row[0],
                    "call_count": row[1],
                    "input_tokens": row[2],
                    "output_tokens": row[3],
                    "total_tokens": row[4],
                    "estimated_cost": row[5]
                }
                for row in rows
            ]
        except Exception as e:
            log.error(f"Error getting usage by provider: {e}")
            return []

    def get_usage_by_model(self, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get usage statistics grouped by model."""
        try:
            query = """
                SELECT
                    provider,
                    model,
                    COUNT(*) as call_count,
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output,
                    SUM(total_tokens) as total_tokens,
                    SUM(estimated_cost) as total_cost
                FROM usage
            """
            params = []

            if provider:
                query += " WHERE provider = ?"
                params.append(provider.lower())

            query += " GROUP BY provider, model ORDER BY total_cost DESC"

            with self._connect() as conn:
                rows = conn.execute(query, params).fetchall()

            return [
                {
                    "provider": row[0],
                    "model": row[1],
                    "call_count": row[2],
                    "input_tokens": row[3],
                    "output_tokens": row[4],
                    "total_tokens": row[5],
                    "estimated_cost": row[6]
                }
                for row in rows
            ]
        except Exception as e:
            log.error(f"Error getting usage by model: {e}")
            return []

    def export_usage_to_csv(self, filepath: str, start_date: Optional[str] = None, end_date: Optional[str] = None):
        """Export usage data to CSV file."""
        try:
            import csv

            query = """
                SELECT
                    timestamp, provider, model, persona,
                    input_tokens, output_tokens, total_tokens,
                    estimated_cost, conversation_id
                FROM usage
                WHERE 1=1
            """
            params = []

            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)

            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)

            query += " ORDER BY timestamp DESC"

            with self._connect() as conn:
                rows = conn.execute(query, params).fetchall()

            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    "Timestamp", "Provider", "Model", "Persona",
                    "Input Tokens", "Output Tokens", "Total Tokens",
                    "Estimated Cost", "Conversation ID"
                ])
                writer.writerows(rows)

            log.info(f"Usage data exported to {filepath}")
            return True
        except Exception as e:
            log.error(f"Error exporting usage data: {e}")
            return False


# Global tracker instance
_tracker = None


def get_tracker() -> UsageTracker:
    """Get the global usage tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker
