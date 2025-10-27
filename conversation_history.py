"""
Conversation history management and storage.
"""
import json
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

log = logging.getLogger(__name__)

# Default database path
HISTORY_DB_PATH = "conversation_history.db"


class ConversationHistory:
    """Manages conversation history storage and retrieval."""

    def __init__(self, db_path: str = HISTORY_DB_PATH):
        """
        Initialize the conversation history manager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the database schema if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Create conversations table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        theme TEXT,
                        persona1 TEXT,
                        persona2 TEXT,
                        model1 TEXT,
                        model2 TEXT,
                        turn_count INTEGER,
                        is_favorite INTEGER DEFAULT 0,
                        notes TEXT
                    )
                ''')

                # Create messages table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id INTEGER NOT NULL,
                        turn_number INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        persona TEXT NOT NULL,
                        content TEXT NOT NULL,
                        FOREIGN KEY (conversation_id) REFERENCES conversations (id)
                    )
                ''')

                # Create indexes for faster searches
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_conversations_timestamp
                    ON conversations(timestamp)
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_conversations_theme
                    ON conversations(theme)
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_conversations_favorite
                    ON conversations(is_favorite)
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id)
                ''')

                conn.commit()
                log.info(f"Conversation history database initialized at {self.db_path}")
        except Exception as e:
            log.error(f"Error initializing database: {e}")
            raise

    def save_conversation(self, conversation: List[Dict[str, str]],
                         metadata: Dict[str, Any]) -> int:
        """
        Save a conversation to the history.

        Args:
            conversation: List of conversation messages
            metadata: Dictionary containing conversation metadata

        Returns:
            The ID of the saved conversation

        Raises:
            Exception: If there's an error saving the conversation
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Insert conversation metadata
                cursor.execute('''
                    INSERT INTO conversations
                    (timestamp, theme, persona1, persona2, model1, model2, turn_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    datetime.now().isoformat(),
                    metadata.get('theme', ''),
                    metadata.get('persona1', ''),
                    metadata.get('persona2', ''),
                    metadata.get('model1', ''),
                    metadata.get('model2', ''),
                    len([m for m in conversation if m['role'] in ('user', 'assistant')])
                ))

                conversation_id = cursor.lastrowid

                # Insert messages
                for idx, msg in enumerate(conversation):
                    cursor.execute('''
                        INSERT INTO messages
                        (conversation_id, turn_number, role, persona, content)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        conversation_id,
                        idx,
                        msg.get('role', ''),
                        msg.get('persona', ''),
                        msg.get('content', '')
                    ))

                conn.commit()
                log.info(f"Saved conversation {conversation_id} to history")
                return conversation_id
        except Exception as e:
            log.error(f"Error saving conversation to history: {e}")
            raise

    def get_conversation(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a conversation by ID.

        Args:
            conversation_id: The ID of the conversation to retrieve

        Returns:
            Dictionary containing conversation metadata and messages, or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Get conversation metadata
                cursor.execute('''
                    SELECT * FROM conversations WHERE id = ?
                ''', (conversation_id,))

                conv_row = cursor.fetchone()
                if not conv_row:
                    return None

                # Get messages
                cursor.execute('''
                    SELECT role, persona, content
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY turn_number
                ''', (conversation_id,))

                messages = [
                    {
                        'role': row['role'],
                        'persona': row['persona'],
                        'content': row['content']
                    }
                    for row in cursor.fetchall()
                ]

                return {
                    'id': conv_row['id'],
                    'timestamp': conv_row['timestamp'],
                    'metadata': {
                        'theme': conv_row['theme'],
                        'persona1': conv_row['persona1'],
                        'persona2': conv_row['persona2'],
                        'model1': conv_row['model1'],
                        'model2': conv_row['model2'],
                        'turn_count': conv_row['turn_count'],
                        'is_favorite': bool(conv_row['is_favorite']),
                        'notes': conv_row['notes']
                    },
                    'conversation': messages
                }
        except Exception as e:
            log.error(f"Error retrieving conversation {conversation_id}: {e}")
            return None

    def list_conversations(self, limit: int = 50, offset: int = 0,
                          search_query: Optional[str] = None,
                          favorites_only: bool = False) -> List[Dict[str, Any]]:
        """
        List conversations with optional filtering.

        Args:
            limit: Maximum number of conversations to return
            offset: Offset for pagination
            search_query: Optional search term to filter by theme or persona
            favorites_only: If True, only return favorited conversations

        Returns:
            List of conversation summaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                query = 'SELECT * FROM conversations WHERE 1=1'
                params = []

                if favorites_only:
                    query += ' AND is_favorite = 1'

                if search_query:
                    query += ' AND (theme LIKE ? OR persona1 LIKE ? OR persona2 LIKE ?)'
                    search_term = f'%{search_query}%'
                    params.extend([search_term, search_term, search_term])

                query += ' ORDER BY timestamp DESC LIMIT ? OFFSET ?'
                params.extend([limit, offset])

                cursor.execute(query, params)

                conversations = [
                    {
                        'id': row['id'],
                        'timestamp': row['timestamp'],
                        'theme': row['theme'],
                        'persona1': row['persona1'],
                        'persona2': row['persona2'],
                        'model1': row['model1'],
                        'model2': row['model2'],
                        'turn_count': row['turn_count'],
                        'is_favorite': bool(row['is_favorite']),
                        'notes': row['notes']
                    }
                    for row in cursor.fetchall()
                ]

                return conversations
        except Exception as e:
            log.error(f"Error listing conversations: {e}")
            return []

    def toggle_favorite(self, conversation_id: int) -> bool:
        """
        Toggle the favorite status of a conversation.

        Args:
            conversation_id: The ID of the conversation

        Returns:
            True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get current favorite status
                cursor.execute('''
                    SELECT is_favorite FROM conversations WHERE id = ?
                ''', (conversation_id,))

                row = cursor.fetchone()
                if not row:
                    return False

                # Toggle the status
                new_status = 0 if row[0] else 1
                cursor.execute('''
                    UPDATE conversations SET is_favorite = ? WHERE id = ?
                ''', (new_status, conversation_id))

                conn.commit()
                log.info(f"Toggled favorite status for conversation {conversation_id}")
                return True
        except Exception as e:
            log.error(f"Error toggling favorite for conversation {conversation_id}: {e}")
            return False

    def update_notes(self, conversation_id: int, notes: str) -> bool:
        """
        Update notes for a conversation.

        Args:
            conversation_id: The ID of the conversation
            notes: The notes to save

        Returns:
            True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    UPDATE conversations SET notes = ? WHERE id = ?
                ''', (notes, conversation_id))

                conn.commit()
                log.info(f"Updated notes for conversation {conversation_id}")
                return True
        except Exception as e:
            log.error(f"Error updating notes for conversation {conversation_id}: {e}")
            return False

    def delete_conversation(self, conversation_id: int) -> bool:
        """
        Delete a conversation from the history.

        Args:
            conversation_id: The ID of the conversation to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Delete messages first (foreign key constraint)
                cursor.execute('''
                    DELETE FROM messages WHERE conversation_id = ?
                ''', (conversation_id,))

                # Delete conversation
                cursor.execute('''
                    DELETE FROM conversations WHERE id = ?
                ''', (conversation_id,))

                conn.commit()
                log.info(f"Deleted conversation {conversation_id}")
                return True
        except Exception as e:
            log.error(f"Error deleting conversation {conversation_id}: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the conversation history.

        Returns:
            Dictionary containing statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Total conversations
                cursor.execute('SELECT COUNT(*) FROM conversations')
                total_conversations = cursor.fetchone()[0]

                # Total messages
                cursor.execute('SELECT COUNT(*) FROM messages')
                total_messages = cursor.fetchone()[0]

                # Favorite conversations
                cursor.execute('SELECT COUNT(*) FROM conversations WHERE is_favorite = 1')
                favorite_count = cursor.fetchone()[0]

                # Most used personas
                cursor.execute('''
                    SELECT persona1 as persona, COUNT(*) as count
                    FROM conversations
                    GROUP BY persona1
                    UNION ALL
                    SELECT persona2 as persona, COUNT(*) as count
                    FROM conversations
                    GROUP BY persona2
                    ORDER BY count DESC
                    LIMIT 5
                ''')
                top_personas = cursor.fetchall()

                return {
                    'total_conversations': total_conversations,
                    'total_messages': total_messages,
                    'favorite_count': favorite_count,
                    'top_personas': top_personas
                }
        except Exception as e:
            log.error(f"Error getting statistics: {e}")
            return {
                'total_conversations': 0,
                'total_messages': 0,
                'favorite_count': 0,
                'top_personas': []
            }
