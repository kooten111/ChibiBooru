"""
Configuration management for rating inference system.
"""

from typing import Dict
from database import get_db_connection

# Rating categories
RATINGS = [
    'rating:general',
    'rating:sensitive',
    'rating:questionable',
    'rating:explicit'
]

# Model database configuration
USE_SEPARATE_MODEL_DB = True


def get_model_connection():
    """Get connection to model database (separate or main DB)."""
    if USE_SEPARATE_MODEL_DB:
        from repositories.rating_repository import get_model_db_connection
        return get_model_db_connection()
    else:
        return get_db_connection()


def get_config() -> Dict[str, float]:
    """Get current inference configuration from database."""
    with get_model_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM rating_inference_config")
        return {row['key']: row['value'] for row in cur.fetchall()}


def update_config(key: str, value: float) -> None:
    """Update a single config value."""
    with get_model_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO rating_inference_config (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()


def reset_config_to_defaults() -> None:
    """Reset all config to factory defaults."""
    import config
    defaults = config.RATING_MODEL_CONFIG.copy()
    
    # Add rating-specific thresholds
    defaults.update({
        'threshold_general': 0.5,
        'threshold_sensitive': 0.6,
        'threshold_questionable': 0.7,
        'threshold_explicit': 0.8,
        'min_training_samples': 50,
    })

    with get_model_connection() as conn:
        cur = conn.cursor()
        for key, value in defaults.items():
            cur.execute(
                "UPDATE rating_inference_config SET value = ? WHERE key = ?",
                (value, key)
            )
        conn.commit()
