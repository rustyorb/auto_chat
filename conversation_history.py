import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

log = logging.getLogger(__name__)

DB_FILE = "conversation_history.db"

class ConversationHistory:
    """Manages storage and retrieval of conversation history in an SQLite database."""

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database and create tables if they don't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        theme TEXT,
                        persona1 TEXT,
                        persona2 TEXT,
                        model1 TEXT,
                        model2 TEXT,
                        turn_count INTEGER,
                        is_favorite INTEGER DEFAULT 0
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id INTEGER,
                        role TEXT,
                        persona TEXT,
                        content TEXT,
                        FOREIGN KEY (conversation_id) REFERENCES conversations (id)
                    )
                """)
                conn.commit()
        except sqlite3.Error as e:
            log.exception(f"Database initialization failed: {e}")
            raise

    def save_conversation(self, conversation: List[Dict[str, str]], metadata: Dict[str, Any]) -> int:
        """Save a new conversation to the database.

        Args:
            conversation: The list of message dictionaries.
            metadata: A dictionary containing conversation metadata.

        Returns:
            The ID of the newly saved conversation.
        """
        timestamp = datetime.now().isoformat()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Insert conversation metadata
                cursor.execute("""
                    INSERT INTO conversations (timestamp, theme, persona1, persona2, model1, model2, turn_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp,
                    metadata.get('theme', 'N/A'),
                    metadata.get('persona1', 'N/A'),
                    metadata.get('persona2', 'N/A'),
                    metadata.get('model1', 'N/A'),
                    metadata.get('model2', 'N/A'),
                    len(conversation)
                ))
                conversation_id = cursor.lastrowid

                # Insert messages
                messages_to_insert = [
                    (conversation_id, msg.get('role'), msg.get('persona'), msg.get('content'))
                    for msg in conversation
                ]
                cursor.executemany("""
                    INSERT INTO messages (conversation_id, role, persona, content)
                    VALUES (?, ?, ?, ?)
                """, messages_to_insert)

                conn.commit()
                log.info(f"Saved conversation with ID: {conversation_id}")
                return conversation_id
        except sqlite3.Error as e:
            log.exception(f"Failed to save conversation: {e}")
            raise

    def get_conversation(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a single conversation and its messages from the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Get conversation metadata
                cursor.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
                conv_row = cursor.fetchone()

                if not conv_row:
                    return None

                # Get messages
                cursor.execute("SELECT role, persona, content FROM messages WHERE conversation_id = ?", (conversation_id,))
                messages = [dict(row) for row in cursor.fetchall()]

                return {
                    "id": conv_row["id"],
                    "timestamp": conv_row["timestamp"],
                    "metadata": dict(conv_row),
                    "conversation": messages
                }
        except sqlite3.Error as e:
            log.exception(f"Failed to retrieve conversation {conversation_id}: {e}")
            return None

    def list_conversations(self, limit: int = 50, offset: int = 0, search_query: Optional[str] = None, favorites_only: bool = False) -> List[Dict[str, Any]]:
        """List conversations with filtering and pagination."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                base_query = "SELECT id, timestamp, theme, persona1, persona2, turn_count, is_favorite FROM conversations"
                conditions = []
                params = []

                if search_query:
                    conditions.append("(theme LIKE ? OR persona1 LIKE ? OR persona2 LIKE ?)")
                    like_query = f"%{search_query}%"
                    params.extend([like_query, like_query, like_query])

                if favorites_only:
                    conditions.append("is_favorite = 1")

                if conditions:
                    base_query += " WHERE " + " AND ".join(conditions)

                base_query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                cursor.execute(base_query, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            log.exception(f"Failed to list conversations: {e}")
            return []

    def delete_conversation(self, conversation_id: int):
        """Delete a conversation and its messages."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
                cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
                conn.commit()
                log.info(f"Deleted conversation with ID: {conversation_id}")
        except sqlite3.Error as e:
            log.exception(f"Failed to delete conversation {conversation_id}: {e}")
            raise

    def toggle_favorite(self, conversation_id: int):
        """Toggle the favorite status of a conversation."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE conversations SET is_favorite = 1 - is_favorite WHERE id = ?", (conversation_id,))
                conn.commit()
                log.info(f"Toggled favorite for conversation ID: {conversation_id}")
        except sqlite3.Error as e:
            log.exception(f"Failed to toggle favorite for conversation {conversation_id}: {e}")
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """Get some basic statistics from the history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Total conversations
                cursor.execute("SELECT COUNT(*) FROM conversations")
                total_conversations = cursor.fetchone()[0]

                # Total messages
                cursor.execute("SELECT COUNT(*) FROM messages")
                total_messages = cursor.fetchone()[0]

                # Favorite count
                cursor.execute("SELECT COUNT(*) FROM conversations WHERE is_favorite = 1")
                favorite_count = cursor.fetchone()[0]

                # Top personas (simple version)
                cursor.execute("""
                    SELECT persona, COUNT(persona) as count FROM (
                        SELECT persona1 as persona FROM conversations
                        UNION ALL
                        SELECT persona2 as persona FROM conversations
                    )
                    WHERE persona != 'N/A'
                    GROUP BY persona
                    ORDER BY count DESC
                    LIMIT 5
                """)
                top_personas = cursor.fetchall()

                return {
                    "total_conversations": total_conversations,
                    "total_messages": total_messages,
                    "favorite_count": favorite_count,
                    "top_personas": top_personas,
                }
        except sqlite3.Error as e:
            log.exception(f"Failed to get statistics: {e}")
            return {}
