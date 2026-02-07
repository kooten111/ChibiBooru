#!/usr/bin/env python3
"""
Tune similarity weights using SigLIP embeddings as ground truth.

This script:
1. Samples image pairs with known SigLIP (cosine) similarity
2. Computes tag-based similarity with various weight configurations
3. Finds weights that best correlate with visual similarity
4. Outputs recommended config values

Usage:
    source ./venv/bin/activate && python scripts/tune_similarity_weights.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from math import log
from collections import defaultdict
import statistics
import random
from itertools import product

import config
from database import get_db_connection
from services import similarity_db

# Extended categories to tune
EXTENDED_CATEGORIES = [
    '00_Subject_Count', '01_Body_Physique', '02_Body_Hair', '03_Body_Face',
    '04_Body_Genitalia', '05_Attire_Main', '06_Attire_Inner', '07_Attire_Legwear',
    '08_Attire_Acc', '09_Action', '10_Pose', '11_Expression', '12_Sexual_Act',
    '13_Object', '14_Setting', '15_Framing', '16_Focus', '17_Style_Art',
    '18_Style_Tech', '19_Meta_Attributes', '20_Meta_Text', '21_Status'
]

# Base categories (fallback)
BASE_CATEGORIES = ['character', 'copyright', 'artist', 'species', 'general', 'meta']


def get_tag_category_map():
    """Build map of tag_id -> (base_category, extended_category)"""
    with get_db_connection() as conn:
        query = "SELECT id, category, extended_category FROM tags"
        results = conn.execute(query).fetchall()
        return {
            row["id"]: {
                'category': row["category"] or "general",
                'extended_category': row["extended_category"]
            }
            for row in results
        }


def get_tag_counts():
    """Get frequency counts for all tags."""
    with get_db_connection() as conn:
        query = """
            SELECT tag_id, COUNT(*) as count
            FROM image_tags
            GROUP BY tag_id
        """
        return {row['tag_id']: row['count'] for row in conn.execute(query).fetchall()}


def get_sample_images(n=500):
    """Get sample images with their tags."""
    with get_db_connection() as conn:
        query = """
            SELECT i.id,
                   COALESCE(i.tags_character, '') || ' ' || 
                   COALESCE(i.tags_copyright, '') || ' ' || 
                   COALESCE(i.tags_artist, '') || ' ' || 
                   COALESCE(i.tags_species, '') || ' ' || 
                   COALESCE(i.tags_general, '') || ' ' || 
                   COALESCE(i.tags_meta, '') as combined_tags
            FROM images i
            ORDER BY RANDOM()
            LIMIT ?
        """
        samples = conn.execute(query, (n * 2,)).fetchall()
        # Filter out images with no tags
        samples = [s for s in samples if s['combined_tags'] and s['combined_tags'].strip()]
        return samples[:n]


def get_siglip_pairs(sample_ids, top_k=10):
    """
    For each sample, find its top_k most similar images by SigLIP.
    Returns list of (id1, id2, siglip_similarity) tuples.
    """
    print("[1/4] Loading SigLIP embeddings...")
    sample_id_set = set(sample_ids)
    
    # Get all embeddings
    all_ids, all_embeddings = similarity_db.get_all_embeddings()
    
    if len(all_ids) == 0:
        print("ERROR: No embeddings found in database!")
        return []
    
    print(f"      Loaded {len(all_ids)} embeddings ({all_embeddings.shape})")
    
    # Build id->index map
    id_to_idx = {img_id: idx for idx, img_id in enumerate(all_ids)}
    
    # Normalize for cosine similarity
    norms = np.linalg.norm(all_embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)  # Avoid div by zero
    normalized = all_embeddings / norms
    
    pairs = []
    sample_ids_with_embeddings = [sid for sid in sample_ids if sid in id_to_idx]
    
    print(f"[2/4] Computing SigLIP similarity for {len(sample_ids_with_embeddings)} images...")
    
    for i, sid in enumerate(sample_ids_with_embeddings):
        if i % 100 == 0:
            print(f"      Progress: {i}/{len(sample_ids_with_embeddings)}")
        
        idx = id_to_idx[sid]
        query_vec = normalized[idx:idx+1]  # Shape (1, dim)
        
        # Compute cosine similarity to all others
        similarities = np.dot(normalized, query_vec.T).flatten()
        
        # Set self-similarity to -inf to exclude
        similarities[idx] = -float('inf')
        
        # Get top_k indices
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        for tidx in top_indices:
            target_id = all_ids[tidx]
            sim_score = float(similarities[tidx])
            if sim_score > 0:  # Only include positive similarity
                pairs.append((sid, target_id, sim_score))
    
    print(f"      Generated {len(pairs)} similarity pairs")
    return pairs


def compute_tag_similarity_with_weights(tags1, tags2, tag_id_cache, tag_counts, 
                                         tag_category_map, category_weights,
                                         alpha=0.6, total_images=16000):
    """
    Compute tag similarity with given category weights.
    Uses asymmetric formula since that's the recommended method.
    """
    set1 = set((tags1 or "").split())
    set2 = set((tags2 or "").split())
    
    if not set1 or not set2:
        return 0.0
    
    def get_weight(tag):
        tag_id = tag_id_cache.get(tag)
        if tag_id is None:
            return 0.1
        
        tag_freq = tag_counts.get(tag_id, 1)
        idf_weight = 1.0 / log(tag_freq + 1)  # Original IDF
        
        cat_info = tag_category_map.get(tag_id, {'category': 'general', 'extended_category': None})
        
        # Use extended category if available
        if cat_info['extended_category'] and cat_info['extended_category'] in category_weights:
            cat_weight = category_weights[cat_info['extended_category']]
        else:
            # Fall back to base category
            cat_weight = category_weights.get(cat_info['category'], 1.0)
        
        return idf_weight * cat_weight
    
    intersection = set1 & set2
    union = set1 | set2
    
    intersection_weight = sum(get_weight(tag) for tag in intersection)
    query_weight = sum(get_weight(tag) for tag in set1)
    union_weight = sum(get_weight(tag) for tag in union)
    
    if query_weight == 0 or union_weight == 0:
        return 0.0
    
    query_coverage = intersection_weight / query_weight
    union_similarity = intersection_weight / union_weight
    
    return alpha * query_coverage + (1 - alpha) * union_similarity


def build_tag_id_cache():
    """Build a tag name -> tag_id cache."""
    with get_db_connection() as conn:
        query = "SELECT id, name FROM tags"
        results = conn.execute(query).fetchall()
        return {row['name']: row['id'] for row in results}


def compute_correlation(siglip_scores, tag_scores):
    """Compute Pearson correlation between SigLIP and tag similarity scores."""
    if len(siglip_scores) < 2:
        return 0.0
    
    mean_s = statistics.mean(siglip_scores)
    mean_t = statistics.mean(tag_scores)
    
    numerator = sum((s - mean_s) * (t - mean_t) for s, t in zip(siglip_scores, tag_scores))
    denom_s = sum((s - mean_s) ** 2 for s in siglip_scores) ** 0.5
    denom_t = sum((t - mean_t) ** 2 for t in tag_scores) ** 0.5
    
    if denom_s == 0 or denom_t == 0:
        return 0.0
    
    return numerator / (denom_s * denom_t)


def evaluate_weights(pairs, image_tags, tag_id_cache, tag_counts, tag_category_map,
                     category_weights, alpha):
    """Evaluate a weight configuration and return correlation with SigLIP."""
    siglip_scores = []
    tag_scores = []
    
    for id1, id2, siglip_sim in pairs:
        tags1 = image_tags.get(id1, "")
        tags2 = image_tags.get(id2, "")
        
        if not tags1 or not tags2:
            continue
        
        tag_sim = compute_tag_similarity_with_weights(
            tags1, tags2, tag_id_cache, tag_counts, tag_category_map,
            category_weights, alpha
        )
        
        siglip_scores.append(siglip_sim)
        tag_scores.append(tag_sim)
    
    return compute_correlation(siglip_scores, tag_scores)


def optimize_weights(pairs, image_tags, tag_id_cache, tag_counts, tag_category_map,
                     total_images):
    """
    Find optimal weights using grid search + refinement.
    """
    print("[3/4] Optimizing category weights...")
    
    # Start with current config weights as baseline
    current_weights = {**config.SIMILARITY_CATEGORY_WEIGHTS}
    current_weights.update(config.SIMILARITY_EXTENDED_CATEGORY_WEIGHTS)
    
    # Group categories for efficient search
    # High-impact categories (tune more precisely)
    high_impact = ['character', 'copyright', '01_Body_Physique', '02_Body_Hair', '03_Body_Face']
    # Medium-impact categories
    medium_impact = ['artist', 'species', '05_Attire_Main', '06_Attire_Inner', 
                     '07_Attire_Legwear', '08_Attire_Acc', '11_Expression', '21_Status']
    # Low-impact (contextual) - tune as a group
    low_impact = ['09_Action', '10_Pose', '12_Sexual_Act', '13_Object', '14_Setting']
    # Meta/style - tune as a group (should be low)
    meta_categories = ['15_Framing', '16_Focus', '17_Style_Art', '18_Style_Tech', 
                       '19_Meta_Attributes', '20_Meta_Text', 'meta', 'general']
    
    # Baseline correlation
    baseline_corr = evaluate_weights(pairs, image_tags, tag_id_cache, tag_counts,
                                     tag_category_map, current_weights, 0.6)
    print(f"      Baseline correlation: {baseline_corr:.4f}")
    
    best_weights = current_weights.copy()
    best_alpha = 0.6
    best_corr = baseline_corr
    
    # Grid search over alpha
    print("      Searching alpha values...")
    for alpha in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        corr = evaluate_weights(pairs, image_tags, tag_id_cache, tag_counts,
                                tag_category_map, current_weights, alpha)
        if corr > best_corr:
            best_corr = corr
            best_alpha = alpha
            print(f"        New best alpha: {alpha} -> correlation {corr:.4f}")
    
    print(f"      Best alpha: {best_alpha}")
    
    # Optimize high-impact categories individually
    print("      Optimizing high-impact categories...")
    for cat in high_impact:
        if cat not in best_weights:
            continue
        
        original = best_weights[cat]
        best_val = original
        
        # Test multipliers
        for mult in [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]:
            test_weights = best_weights.copy()
            test_weights[cat] = original * mult
            
            corr = evaluate_weights(pairs, image_tags, tag_id_cache, tag_counts,
                                    tag_category_map, test_weights, best_alpha)
            
            if corr > best_corr:
                best_corr = corr
                best_val = original * mult
                print(f"        {cat}: {original:.2f} -> {best_val:.2f} (corr: {corr:.4f})")
        
        best_weights[cat] = best_val
    
    # Optimize medium-impact categories
    print("      Optimizing medium-impact categories...")
    for cat in medium_impact:
        if cat not in best_weights:
            continue
        
        original = best_weights[cat]
        best_val = original
        
        for mult in [0.5, 1.0, 1.5, 2.0]:
            test_weights = best_weights.copy()
            test_weights[cat] = original * mult
            
            corr = evaluate_weights(pairs, image_tags, tag_id_cache, tag_counts,
                                    tag_category_map, test_weights, best_alpha)
            
            if corr > best_corr:
                best_corr = corr
                best_val = original * mult
        
        best_weights[cat] = best_val
    
    # Tune low-impact as a group
    print("      Optimizing low-impact categories as group...")
    for mult in [0.25, 0.5, 0.75, 1.0, 1.5]:
        test_weights = best_weights.copy()
        for cat in low_impact:
            if cat in test_weights:
                test_weights[cat] = current_weights.get(cat, 1.0) * mult
        
        corr = evaluate_weights(pairs, image_tags, tag_id_cache, tag_counts,
                                tag_category_map, test_weights, best_alpha)
        
        if corr > best_corr:
            best_corr = corr
            for cat in low_impact:
                if cat in best_weights:
                    best_weights[cat] = current_weights.get(cat, 1.0) * mult
            print(f"        Low-impact group: mult={mult} (corr: {corr:.4f})")
    
    # Tune meta categories as a group (should be low)
    print("      Optimizing meta categories as group...")
    for mult in [0.1, 0.25, 0.5, 1.0]:
        test_weights = best_weights.copy()
        for cat in meta_categories:
            if cat in test_weights:
                test_weights[cat] = current_weights.get(cat, 0.5) * mult
        
        corr = evaluate_weights(pairs, image_tags, tag_id_cache, tag_counts,
                                tag_category_map, test_weights, best_alpha)
        
        if corr > best_corr:
            best_corr = corr
            for cat in meta_categories:
                if cat in best_weights:
                    best_weights[cat] = current_weights.get(cat, 0.5) * mult
            print(f"        Meta group: mult={mult} (corr: {corr:.4f})")
    
    return best_weights, best_alpha, best_corr


def main():
    print("="*80)
    print("SIMILARITY WEIGHT TUNING USING SIGLIP AS GROUND TRUTH")
    print("="*80)
    
    # Get sample images
    print("\nGetting sample images...")
    samples = get_sample_images(500)
    print(f"Got {len(samples)} sample images with tags")
    
    image_tags = {s['id']: s['combined_tags'] for s in samples}
    sample_ids = list(image_tags.keys())
    
    # Get SigLIP similarity pairs
    pairs = get_siglip_pairs(sample_ids, top_k=10)
    
    if not pairs:
        print("ERROR: Could not generate similarity pairs!")
        return
    
    # Load tag metadata
    tag_id_cache = build_tag_id_cache()
    tag_counts = get_tag_counts()
    tag_category_map = get_tag_category_map()
    
    total_images = len(samples)
    
    # Optimize
    best_weights, best_alpha, best_corr = optimize_weights(
        pairs, image_tags, tag_id_cache, tag_counts, tag_category_map, total_images
    )
    
    # Output results
    print("\n" + "="*80)
    print("[4/4] RECOMMENDED CONFIGURATION")
    print("="*80)
    
    print(f"\nBest correlation with SigLIP: {best_corr:.4f}")
    print(f"\nASYMMETRIC_ALPHA: {best_alpha}")
    
    # Separate base and extended weights
    base_weights = {k: v for k, v in best_weights.items() if k in BASE_CATEGORIES}
    ext_weights = {k: v for k, v in best_weights.items() if k in EXTENDED_CATEGORIES}
    
    print("\n# SIMILARITY_CATEGORY_WEIGHTS (base categories):")
    print("SIMILARITY_CATEGORY_WEIGHTS:")
    for cat in BASE_CATEGORIES:
        if cat in base_weights:
            print(f"  {cat}: {base_weights[cat]:.1f}")
    
    print("\n# SIMILARITY_EXTENDED_CATEGORY_WEIGHTS (22 categories):")
    print("SIMILARITY_EXTENDED_CATEGORY_WEIGHTS:")
    for cat in EXTENDED_CATEGORIES:
        if cat in ext_weights:
            print(f"  {cat}: {ext_weights[cat]:.2f}")
    
    # Generate YAML snippet
    print("\n" + "-"*40)
    print("Copy-paste ready YAML for config.yml:")
    print("-"*40)
    
    print(f"\nASYMMETRIC_ALPHA: {best_alpha}")
    print("SIMILARITY_CATEGORY_WEIGHTS:")
    for cat in BASE_CATEGORIES:
        if cat in base_weights:
            print(f"  {cat}: {base_weights[cat]:.1f}")
    
    print("SIMILARITY_EXTENDED_CATEGORY_WEIGHTS:")
    for cat in EXTENDED_CATEGORIES:
        if cat in ext_weights:
            print(f"  '{cat}': {ext_weights[cat]:.2f}")


if __name__ == "__main__":
    main()
