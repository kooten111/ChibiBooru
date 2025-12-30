"""
Tag ID Cache - Memory-efficient tag storage using IDs

Provides bidirectional mapping between tag names and integer IDs.
Used by cache_manager to store arrays of tag IDs instead of strings.

This optimization reduces memory usage by:
- Storing 4-byte int32 IDs instead of 50+ byte string objects
- Enabling faster set operations (int comparison vs string comparison)
- Reducing GC pressure from temporary string objects

Expected memory savings: ~200-500 MB
"""

import sys
from typing import Optional, List
from array import array
from database import get_db_connection


class TagIDCache:
    """Bidirectional mapping between tag names and IDs"""

    def __init__(self):
        self.name_to_id: dict[str, int] = {}
        self.id_to_name: dict[int, str] = {}
        self._load_from_db()

    def _load_from_db(self):
        """Load tag mappings from database with string interning"""
        with get_db_connection() as conn:
            for row in conn.execute("SELECT id, name FROM tags"):
                tag_id = row['id']
                # Use string interning to save memory
                tag_name = sys.intern(row['name'])
                self.name_to_id[tag_name] = tag_id
                self.id_to_name[tag_id] = tag_name

    def get_id(self, tag_name: str) -> Optional[int]:
        """Get tag ID from name"""
        return self.name_to_id.get(tag_name)

    def get_name(self, tag_id: int) -> Optional[str]:
        """Get tag name from ID"""
        return self.id_to_name.get(tag_id)

    def get_ids(self, tag_names: List[str]) -> array:
        """
        Convert list of tag names to array of IDs.

        Args:
            tag_names: List of tag name strings

        Returns:
            array of int32 IDs (only for tags that exist)
        """
        ids = [self.name_to_id[name] for name in tag_names if name in self.name_to_id]
        return array('i', ids)  # 'i' = signed int (typically 32-bit)

    def get_names(self, tag_ids: array) -> List[str]:
        """
        Convert array of tag IDs to list of names.

        Args:
            tag_ids: array of int32 tag IDs

        Returns:
            List of tag name strings
        """
        return [self.id_to_name[tag_id] for tag_id in tag_ids if tag_id in self.id_to_name]

    def get_ids_from_string(self, tags_string: str) -> array:
        """
        Convert space-separated tag string to array of IDs.

        Args:
            tags_string: Space-separated tag names

        Returns:
            array of int32 tag IDs
        """
        if not tags_string:
            return array('i')
        tag_names = tags_string.split()
        return self.get_ids(tag_names)

    def get_string_from_ids(self, tag_ids: array) -> str:
        """
        Convert array of tag IDs to space-separated string.

        Args:
            tag_ids: array of int32 tag IDs

        Returns:
            Space-separated tag names
        """
        names = self.get_names(tag_ids)
        return ' '.join(names)

    def reload(self):
        """Reload mappings from database (call when tags are added/removed)"""
        self.name_to_id.clear()
        self.id_to_name.clear()
        self._load_from_db()

    def get_tag_count(self) -> int:
        """Get total number of tags in cache"""
        return len(self.id_to_name)


# Global instance
_tag_id_cache: Optional[TagIDCache] = None


def get_tag_id_cache() -> TagIDCache:
    """Get or create global tag ID cache"""
    global _tag_id_cache
    if _tag_id_cache is None:
        _tag_id_cache = TagIDCache()
    return _tag_id_cache


def reload_tag_id_cache():
    """Force reload of tag ID cache from database"""
    global _tag_id_cache
    if _tag_id_cache is not None:
        _tag_id_cache.reload()
    else:
        _tag_id_cache = TagIDCache()
