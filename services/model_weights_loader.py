"""
Shared memory and lazy loading utilities for model weights.

This module provides efficient ways to load and share model weights across
multiple processes without duplicating memory.
"""

import multiprocessing
import sqlite3
import pickle
import mmap
import os
from typing import Dict, Tuple, Optional, List
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# Global shared memory stores (one per model type)
_shared_rating_weights = None
_shared_character_weights = None


class SharedWeights:
    """
    Wrapper for shared memory weight dictionaries.
    Uses multiprocessing.Manager for simplicity (slower but easier than raw shared memory).
    Note: For RAM-constrained systems, workers should load weights from database directly instead.
    """
    def __init__(self, tag_weights: Dict, pair_weights: Dict):
        """
        Initialize shared weights from dictionaries.
        
        Args:
            tag_weights: {(tag, rating/character): weight}
            pair_weights: {(tag1, tag2, rating/character): weight}
        """
        self.manager = multiprocessing.Manager()
        # Convert to regular dicts for Manager (tuples as keys work fine)
        self.tag_weights = self.manager.dict(tag_weights)
        self.pair_weights = self.manager.dict(pair_weights)
        self._size = len(tag_weights) + len(pair_weights)
    
    def get_tag_weight(self, key: Tuple) -> float:
        """Get tag weight from shared dict."""
        return self.tag_weights.get(key, 0.0)
    
    def get_pair_weight(self, key: Tuple) -> float:
        """Get pair weight from shared dict."""
        return self.pair_weights.get(key, 0.0)
    
    def __len__(self):
        return self._size


def load_weights_shared_rating() -> Optional[SharedWeights]:
    """
    Load rating weights into shared memory.
    Returns None if model not trained.
    
    Returns:
        SharedWeights or None
    """
    try:
        from services.rating_service import load_weights, get_model_connection
        
        # Load weights normally
        tag_weights, pair_weights = load_weights()
        
        if not tag_weights and not pair_weights:
            return None
        
        # Create shared weights
        shared = SharedWeights(tag_weights, pair_weights)
        logger.info(f"Loaded {len(tag_weights)} tag weights and {len(pair_weights)} pair weights into shared memory (rating)")
        return shared
    except Exception as e:
        logger.error(f"Failed to load rating weights into shared memory: {e}")
        return None


def get_weights_for_tags_rating(tag_names: List[str], conn: Optional[sqlite3.Connection] = None) -> Tuple[Dict, Dict]:
    """
    Lazy load weights for specific tags from rating model database.
    Only queries weights relevant to the provided tags.
    
    Args:
        tag_names: List of tag names to get weights for
        conn: Optional database connection (creates new if None)
    
    Returns:
        tuple: (tag_weights, pair_weights) dictionaries
    """
    from services.rating_service import get_model_connection
    from repositories.rating_repository import get_or_create_tag_id
    
    if not tag_names:
        return {}, {}
    
    # Use provided connection or create new one
    if conn is None:
        conn_context = get_model_connection()
        conn = conn_context.__enter__()
        should_close = True
    else:
        should_close = False
    
    try:
        cur = conn.cursor()
        
        # Get tag IDs for the provided tag names
        placeholders = ','.join('?' * len(tag_names))
        cur.execute(f"""
            SELECT id, name FROM tags
            WHERE name IN ({placeholders})
        """, tag_names)
        
        tag_id_map = {row['name']: row['id'] for row in cur.fetchall()}
        tag_ids = list(tag_id_map.values())
        
        if not tag_ids:
            return {}, {}
        
        # Load tag weights for these tags
        tag_id_placeholders = ','.join('?' * len(tag_ids))
        cur.execute(f"""
            SELECT t.name as tag_name, r.name as rating, tw.weight
            FROM rating_tag_weights tw
            JOIN tags t ON tw.tag_id = t.id
            JOIN ratings r ON tw.rating_id = r.id
            WHERE tw.tag_id IN ({tag_id_placeholders})
        """, tag_ids)
        
        tag_weights = {
            (row['tag_name'], row['rating']): row['weight']
            for row in cur.fetchall()
        }
        
        # Load pair weights for pairs involving these tags
        # Need to check both tag1_id and tag2_id
        cur.execute(f"""
            SELECT t1.name as tag1, t2.name as tag2, r.name as rating, pw.weight
            FROM rating_tag_pair_weights pw
            JOIN tags t1 ON pw.tag1_id = t1.id
            JOIN tags t2 ON pw.tag2_id = t2.id
            JOIN ratings r ON pw.rating_id = r.id
            WHERE pw.tag1_id IN ({tag_id_placeholders})
               OR pw.tag2_id IN ({tag_id_placeholders})
        """, tag_ids + tag_ids)
        
        pair_weights = {
            (row['tag1'], row['tag2'], row['rating']): row['weight']
            for row in cur.fetchall()
        }
        
        return tag_weights, pair_weights
    
    finally:
        if should_close:
            conn_context.__exit__(None, None, None)
