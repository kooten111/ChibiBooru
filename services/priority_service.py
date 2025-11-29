"""
Priority Monitor - Auto-detect and apply BOORU_PRIORITY changes

This module automatically detects when config.BOORU_PRIORITY changes
and triggers a database repopulation to apply the new priority.

Called automatically on app startup.
"""

import hashlib
import json
from database import get_db_connection


def get_priority_hash(priority_list, version=1):
    """
    Generate a hash of the current priority list and version.

    Args:
        priority_list: The BOORU_PRIORITY list
        version: The BOORU_PRIORITY_VERSION number
    """
    # Include version in the hash so version bumps trigger re-tagging
    priority_data = {
        'version': version,
        'priority': priority_list
    }
    priority_str = json.dumps(priority_data, sort_keys=True)
    return hashlib.sha256(priority_str.encode()).hexdigest()


def get_stored_priority_hash():
    """Get the stored priority hash from database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT value FROM config_store
                WHERE key = 'booru_priority_hash'
            """)
            result = cursor.fetchone()
            return result['value'] if result else None
    except Exception:
        # Table might not exist yet
        return None


def store_priority_hash(priority_hash):
    """Store the current priority hash in database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO config_store (key, value)
            VALUES ('booru_priority_hash', ?)
        """, (priority_hash,))
        conn.commit()


def ensure_config_store_table():
    """Create config_store table if it doesn't exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def check_and_apply_priority_changes():
    """
    Check if BOORU_PRIORITY has changed and apply if needed.

    Returns:
        bool: True if priority was changed and applied, False otherwise
    """
    import config

    # Ensure config_store table exists
    ensure_config_store_table()

    # Get version from config (default to 1 for backwards compatibility)
    version = getattr(config, 'BOORU_PRIORITY_VERSION', 1)

    # Calculate current priority hash (includes version)
    current_hash = get_priority_hash(config.BOORU_PRIORITY, version)

    # Get stored hash
    stored_hash = get_stored_priority_hash()

    # First run - just store the hash
    if stored_hash is None:
        print("📝 First run: storing current BOORU_PRIORITY")
        print(f"   Version: {version}")
        print(f"   Priority: {' → '.join(config.BOORU_PRIORITY)}")
        store_priority_hash(current_hash)
        return False

    # Check if priority changed
    if current_hash != stored_hash:
        print("\n" + "=" * 70)
        print("🔄 BOORU_PRIORITY has changed!")
        print("=" * 70)
        print(f"\nVersion: {version}")
        print("Current priority:")
        for i, source in enumerate(config.BOORU_PRIORITY, 1):
            print(f"  {i}. {source}")
        print("\n⚙️  Automatically re-tagging all images...")
        print("   (Manual tag changes will be preserved)\n")

        # Import here to avoid circular dependency
        from database_models import repopulate_from_database

        # Apply the new priority
        repopulate_from_database()

        # Store the new hash
        store_priority_hash(current_hash)

        print("\n" + "=" * 70)
        print("✅ Priority change applied successfully!")
        print("=" * 70 + "\n")

        return True

    return False


if __name__ == "__main__":
    # For testing
    import config

    version = getattr(config, 'BOORU_PRIORITY_VERSION', 1)
    print(f"Current BOORU_PRIORITY (version {version}):")
    for i, source in enumerate(config.BOORU_PRIORITY, 1):
        print(f"  {i}. {source}")
    print()

    current_hash = get_priority_hash(config.BOORU_PRIORITY, version)
    stored_hash = get_stored_priority_hash()

    print(f"Current hash: {current_hash[:16]}...")
    print(f"Stored hash:  {stored_hash[:16] if stored_hash else 'None'}...")
    print()

    if current_hash == stored_hash:
        print("✓ Priority unchanged")
    else:
        print("✗ Priority has changed - would trigger repopulation")
