#!/usr/bin/env python3
"""
Lightweight standalone worker for character prediction processing.
Minimizes memory usage by avoiding full database imports.
"""

import requests
import time
import sys
import os
import logging
import sqlite3
import math
from collections import defaultdict
from itertools import combinations
from typing import Dict, List, Tuple, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost:5000')
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 50))
WORKER_ID = os.environ.get('WORKER_ID', f'worker-{os.getpid()}')

# Path to character model database  
MODEL_DB_PATH = os.environ.get('MODEL_DB_PATH', './character_model.db')


def load_model_weights():
    """Load model weights directly from database without importing full app."""
    logger.info(f"Loading weights from {MODEL_DB_PATH}...")
    
    conn = sqlite3.connect(MODEL_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Load tag weights
        cur.execute("""
            SELECT t.name as tag_name, c.name as character, tw.weight
            FROM character_tag_weights tw
            JOIN tags t ON tw.tag_id = t.id
            JOIN characters c ON tw.character_id = c.id
        """)
        tag_weights = {
            (row['tag_name'], row['character']): row['weight']
            for row in cur.fetchall()
        }
        
        # Load pair weights
        cur.execute("""
            SELECT t1.name as tag1, t2.name as tag2, c.name as character, pw.weight
            FROM character_tag_pair_weights pw
            JOIN tags t1 ON pw.tag1_id = t1.id
            JOIN tags t2 ON pw.tag2_id = t2.id
            JOIN characters c ON pw.character_id = c.id
        """)
        pair_weights = {
            (row['tag1'], row['tag2'], row['character']): row['weight']
            for row in cur.fetchall()
        }
        
        logger.info(f"Loaded {len(tag_weights)} tag weights, {len(pair_weights)} pair weights")
        
    finally:
        # CRITICAL: Close connection immediately to free memory-mapped database
        conn.close()
        logger.info("Database connection closed")
    
    return tag_weights, pair_weights


def load_config():
    """Load config directly from database."""
    conn = sqlite3.connect(MODEL_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT key, value FROM character_model_config")
        config = {row['key']: row['value'] for row in cur.fetchall()}
    finally:
        conn.close()
    
    return config


def calculate_character_scores(image_tags, tag_weights, pair_weights, config):
    """Calculate raw scores for each character."""
    scores = defaultdict(float)
    
    # Individual tag weights
    for tag in image_tags:
        for (tag_key, character), weight in tag_weights.items():
            if tag_key == tag:
                scores[character] += weight
    
    # Tag pair weights
    pair_multiplier = config['pair_weight_multiplier']
    sorted_tags = sorted(image_tags)
    
    for tag1, tag2 in combinations(sorted_tags, 2):
        for (t1, t2, character), pair_weight in pair_weights.items():
            if (t1 == tag1 and t2 == tag2) or (t1 == tag2 and t2 == tag1):
                scores[character] += pair_weight * pair_multiplier
    
    return dict(scores)


def scores_to_probabilities(scores):
    """Convert scores to probabilities using softmax."""
    if not scores:
        return {}
    
    max_score = max(scores.values())
    exp_scores = {char: math.exp(score - max_score) for char, score in scores.items()}
    
    total = sum(exp_scores.values())
    if total == 0:
        return {char: 0.0 for char in scores}
    
    return {char: exp_score / total for char, exp_score in exp_scores.items()}


def predict_characters(image_tags, tag_weights, pair_weights, config):
    """Predict characters for an image."""
    if not image_tags:
        return []
    
    if not tag_weights and not pair_weights:
        return []
    
    scores = calculate_character_scores(image_tags, tag_weights, pair_weights, config)
    if not scores:
        return []
    
    probabilities = scores_to_probabilities(scores)
    
    min_confidence = config['min_confidence']
    max_predictions = int(config['max_predictions'])
    
    predictions = [(char, prob) for char, prob in probabilities.items() if prob >= min_confidence]
    predictions.sort(key=lambda x: x[1], reverse=True)
    predictions = predictions[:max_predictions]
    
    return predictions


def fetch_work_batch():
    """Fetch a batch of work from the server."""
    try:
        response = requests.get(
            f'{API_BASE_URL}/api/character/work',
            params={'batch_size': BATCH_SIZE, 'worker_id': WORKER_ID},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        if not data.get('images'):
            return None
            
        return data
    except Exception as e:
        logger.error(f"Failed to fetch work: {e}")
        return None


def submit_results(batch_id, results):
    """Submit processed results to the server."""
    try:
        response = requests.post(
            f'{API_BASE_URL}/api/character/results',
            json={
                'batch_id': batch_id,
                'worker_id': WORKER_ID,
                'results': results
            },
            timeout=30
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to submit results: {e}")
        return False


def process_batch(batch, tag_weights, pair_weights, config):
    """Process a batch of images and return predictions."""
    images = batch['images']
    results = {
        'predictions': {},
        'stats': {
            'processed': 0,
            'predictions_stored': 0,
            'skipped_no_tags': 0
        }
    }
    
    for image_data in images:
        image_id = image_data['image_id']
        tags = image_data['tags']
        
        results['stats']['processed'] += 1
        
        if not tags:
            results['stats']['skipped_no_tags'] += 1
            continue
        
        predictions = predict_characters(tags, tag_weights, pair_weights, config)
        
        if predictions:
            results['predictions'][image_id] = predictions
            results['stats']['predictions_stored'] += len(predictions)
    
    return results


def main():
    """Main worker loop."""
    logger.info(f"Worker {WORKER_ID} starting...")
    logger.info(f"API Base URL: {API_BASE_URL}")
    logger.info(f"Batch Size: {BATCH_SIZE}")
    logger.info(f"Model DB: {MODEL_DB_PATH}")
    
    # Load model weights once at startup
    logger.info("Loading model weights...")
    try:
        tag_weights, pair_weights = load_model_weights()
        config = load_config()
        
        if not tag_weights and not pair_weights:
            logger.error("No model weights found. Train the model first!")
            return 1
            
        logger.info(f"Model loaded: {len(tag_weights)} tag weights, {len(pair_weights)} pair weights")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return 1
    
    # Process batches until no more work
    batches_processed = 0
    total_images = 0
    
    while True:
        # Fetch work
        logger.info("Fetching work batch...")
        batch = fetch_work_batch()
        
        if not batch:
            logger.info("No more work available. Exiting.")
            break
        
        batch_id = batch['batch_id']
        num_images = len(batch['images'])
        logger.info(f"Processing batch {batch_id} ({num_images} images)...")
        
        # Process the batch
        results = process_batch(batch, tag_weights, pair_weights, config)
        
        # Submit results
        logger.info(f"Submitting results for batch {batch_id}...")
        if submit_results(batch_id, results):
            batches_processed += 1
            total_images += results['stats']['processed']
            logger.info(f"✓ Batch {batch_id} complete: {results['stats']['processed']} processed, {results['stats']['predictions_stored']} predictions")
        else:
            logger.error(f"✗ Failed to submit results for batch {batch_id}")
    
    logger.info(f"Worker {WORKER_ID} finished: {batches_processed} batches, {total_images} total images")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Worker crashed: {e}", exc_info=True)
        sys.exit(1)
