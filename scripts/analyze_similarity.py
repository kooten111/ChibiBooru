#!/usr/bin/env python3
"""
Analyze tag similarity calculation to understand score distributions.

This script investigates:
1. IDF weight distribution across tags
2. Category weight impact
3. Actual similarity score distributions
4. Edge cases and potential improvements
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from math import log
from collections import defaultdict
import statistics

import config
from database import get_db_connection


def get_tag_counts_from_db():
    """Get tag counts directly from database."""
    with get_db_connection() as conn:
        query = """
            SELECT tag_id, COUNT(*) as count
            FROM image_tags
            GROUP BY tag_id
        """
        return {row['tag_id']: row['count'] for row in conn.execute(query).fetchall()}


def get_image_count_from_db():
    """Get total image count from database."""
    with get_db_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]


def analyze_idf_distribution():
    """Analyze how IDF weights are distributed across tags."""
    print("\n" + "="*80)
    print("IDF WEIGHT ANALYSIS")
    print("="*80)
    
    tag_counts = get_tag_counts_from_db()
    total_images = get_image_count_from_db()
    
    print(f"\nTotal images in database: {total_images:,}")
    print(f"Total unique tags: {len(tag_counts):,}")
    
    # Calculate IDF weights for all tags
    idf_weights = {}
    for tag_id, freq in tag_counts.items():
        # Current formula
        current_idf = 1.0 / log(freq + 1)
        # Standard TF-IDF style
        standard_idf = log(total_images / (freq + 1)) + 1
        idf_weights[tag_id] = {
            'freq': freq,
            'current_idf': current_idf,
            'standard_idf': standard_idf
        }
    
    # Get tag names for display
    with get_db_connection() as conn:
        tag_names = {row['id']: row['name'] for row in 
                     conn.execute("SELECT id, name FROM tags").fetchall()}
    
    # Statistics
    current_values = [w['current_idf'] for w in idf_weights.values()]
    standard_values = [w['standard_idf'] for w in idf_weights.values()]
    
    print(f"\n--- Current IDF Formula: 1 / log(freq + 1) ---")
    print(f"  Min:    {min(current_values):.4f}")
    print(f"  Max:    {max(current_values):.4f}")
    print(f"  Mean:   {statistics.mean(current_values):.4f}")
    print(f"  Median: {statistics.median(current_values):.4f}")
    print(f"  StdDev: {statistics.stdev(current_values):.4f}")
    
    print(f"\n--- Standard TF-IDF Formula: log(N / (freq + 1)) + 1 ---")
    print(f"  Min:    {min(standard_values):.4f}")
    print(f"  Max:    {max(standard_values):.4f}")
    print(f"  Mean:   {statistics.mean(standard_values):.4f}")
    print(f"  Median: {statistics.median(standard_values):.4f}")
    print(f"  StdDev: {statistics.stdev(standard_values):.4f}")
    
    # Show examples at different frequency levels
    print(f"\n--- IDF Comparison by Frequency ---")
    print(f"{'Frequency':<12} {'Current IDF':<12} {'Standard IDF':<14} {'Ratio':<8}")
    print("-" * 50)
    
    freq_examples = [1, 5, 10, 50, 100, 500, 1000, 5000, 10000]
    for freq in freq_examples:
        if freq > total_images:
            continue
        current = 1.0 / log(freq + 1)
        standard = log(total_images / (freq + 1)) + 1
        ratio = standard / current if current > 0 else 0
        print(f"{freq:<12} {current:<12.4f} {standard:<14.4f} {ratio:<8.2f}x")
    
    # Show actual top and bottom tags
    print(f"\n--- Top 10 Rarest Tags (Highest IDF) ---")
    sorted_by_rarity = sorted(idf_weights.items(), key=lambda x: x[1]['current_idf'], reverse=True)[:10]
    for tag_id, w in sorted_by_rarity:
        name = tag_names.get(tag_id, f"ID:{tag_id}")
        print(f"  {name:<40} freq={w['freq']:<6} IDF={w['current_idf']:.4f}")
    
    print(f"\n--- Top 10 Most Common Tags (Lowest IDF) ---")
    sorted_by_common = sorted(idf_weights.items(), key=lambda x: x[1]['current_idf'])[:10]
    for tag_id, w in sorted_by_common:
        name = tag_names.get(tag_id, f"ID:{tag_id}")
        print(f"  {name:<40} freq={w['freq']:<6} IDF={w['current_idf']:.4f}")
    
    return idf_weights, tag_names


def analyze_category_weight_impact():
    """Analyze how category weights affect final tag weights."""
    print("\n" + "="*80)
    print("CATEGORY WEIGHT IMPACT ANALYSIS")
    print("="*80)
    
    with get_db_connection() as conn:
        # Get tags with their categories
        query = """
            SELECT t.id, t.name, t.category, t.extended_category,
                   COUNT(it.image_id) as freq
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            GROUP BY t.id
            HAVING freq > 0
        """
        results = conn.execute(query).fetchall()
    
    # Calculate combined weights
    tag_weights = []
    for row in results:
        freq = row['freq']
        idf = 1.0 / log(freq + 1)
        
        ext_cat = row['extended_category']
        base_cat = row['category'] or 'general'
        
        if config.USE_EXTENDED_SIMILARITY and ext_cat:
            cat_weight = config.SIMILARITY_EXTENDED_CATEGORY_WEIGHTS.get(
                ext_cat, 
                config.SIMILARITY_CATEGORY_WEIGHTS.get(base_cat, 1.0)
            )
        else:
            cat_weight = config.SIMILARITY_CATEGORY_WEIGHTS.get(base_cat, 1.0)
        
        combined = idf * cat_weight
        
        tag_weights.append({
            'name': row['name'],
            'freq': freq,
            'base_cat': base_cat,
            'ext_cat': ext_cat,
            'idf': idf,
            'cat_weight': cat_weight,
            'combined': combined
        })
    
    # Show distribution by category
    print("\n--- Weight Distribution by Extended Category ---")
    by_category = defaultdict(list)
    for tw in tag_weights:
        cat = tw['ext_cat'] or tw['base_cat']
        by_category[cat].append(tw)
    
    print(f"\n{'Category':<25} {'Count':<8} {'Avg IDF':<10} {'Cat Wt':<8} {'Avg Combined':<12}")
    print("-" * 75)
    
    sorted_cats = sorted(by_category.items(), 
                         key=lambda x: statistics.mean(t['combined'] for t in x[1]) if x[1] else 0,
                         reverse=True)
    
    for cat, tags in sorted_cats:
        if not tags:
            continue
        avg_idf = statistics.mean(t['idf'] for t in tags)
        avg_combined = statistics.mean(t['combined'] for t in tags)
        cat_wt = tags[0]['cat_weight']
        print(f"{cat:<25} {len(tags):<8} {avg_idf:<10.4f} {cat_wt:<8.1f} {avg_combined:<12.4f}")
    
    # Show what dominates: IDF or category weight?
    print("\n--- Relative Contribution Analysis ---")
    print("For the same tag at different frequencies, how much does IDF vary vs category?")
    
    # Find tags with same category but different frequencies
    for cat in ['character', '01_Body_Physique', '10_Pose', '19_Meta_Attributes']:
        cat_tags = [t for t in tag_weights if t['ext_cat'] == cat or (t['ext_cat'] is None and t['base_cat'] == cat)]
        if len(cat_tags) >= 2:
            cat_tags.sort(key=lambda x: x['freq'])
            min_tag = cat_tags[0]
            max_tag = cat_tags[-1]
            print(f"\n  {cat}:")
            print(f"    Rarest:  {min_tag['name']:<30} freq={min_tag['freq']:<6} combined={min_tag['combined']:.4f}")
            print(f"    Common:  {max_tag['name']:<30} freq={max_tag['freq']:<6} combined={max_tag['combined']:.4f}")
            print(f"    Weight ratio: {min_tag['combined']/max_tag['combined']:.2f}x")
    
    return tag_weights


def analyze_similarity_scores():
    """Analyze actual similarity score distributions for all methods."""
    print("\n" + "="*80)
    print("SIMILARITY SCORE DISTRIBUTION ANALYSIS")
    print("="*80)
    
    # Import all similarity functions
    from services.query.similarity import (
        calculate_jaccard_similarity,
        calculate_weighted_similarity,
        calculate_weighted_tfidf_similarity,
        calculate_asymmetric_similarity,
        calculate_asymmetric_tfidf_similarity,
    )
    
    methods = {
        'jaccard': calculate_jaccard_similarity,
        'weighted': calculate_weighted_similarity,
        'weighted_tfidf': calculate_weighted_tfidf_similarity,
        'asymmetric': calculate_asymmetric_similarity,
        'asymmetric_tfidf': calculate_asymmetric_tfidf_similarity,
    }
    
    # Get some sample images with their tags
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
            LIMIT 200
        """
        samples = conn.execute(query).fetchall()
        samples = [s for s in samples if s['combined_tags'] and s['combined_tags'].strip()]
    
    print(f"\nAnalyzing {len(samples)} random images...")
    
    # Calculate pairwise similarities for a subset using all methods
    scores = {method: [] for method in methods}
    
    test_pairs = min(500, len(samples) * (len(samples) - 1) // 2)
    pair_count = 0
    
    for i, img1 in enumerate(samples):
        if pair_count >= test_pairs:
            break
        for img2 in samples[i+1:]:
            if pair_count >= test_pairs:
                break
            
            for method_name, method_func in methods.items():
                score = method_func(img1['combined_tags'], img2['combined_tags'])
                scores[method_name].append(score)
            
            pair_count += 1
    
    print(f"Calculated {pair_count} pairwise similarities per method")
    
    # Statistics for each method
    print(f"\n--- Score Distribution by Method ---")
    print(f"{'Method':<18} {'Min':<8} {'Max':<8} {'Mean':<8} {'Median':<8} {'StdDev':<8}")
    print("-" * 60)
    
    for method_name, method_scores in scores.items():
        print(f"{method_name:<18} "
              f"{min(method_scores):<8.4f} "
              f"{max(method_scores):<8.4f} "
              f"{statistics.mean(method_scores):<8.4f} "
              f"{statistics.median(method_scores):<8.4f} "
              f"{statistics.stdev(method_scores):<8.4f}")
    
    # Histogram-like buckets
    print("\n--- Score Distribution Buckets (% of pairs) ---")
    buckets = [(0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5), 
               (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]
    
    print(f"\n{'Range':<10} " + " ".join(f"{m:<10}" for m in methods.keys()))
    print("-" * 70)
    for low, high in buckets:
        row = f"{low:.1f}-{high:.1f}   "
        for method_name in methods:
            count = sum(1 for s in scores[method_name] if low <= s < high)
            pct = 100 * count / len(scores[method_name])
            row += f"{pct:>6.1f}%   "
        print(row)
    
    return scores


def analyze_edge_cases():
    """Analyze specific edge cases in the similarity calculation."""
    print("\n" + "="*80)
    print("EDGE CASE ANALYSIS")
    print("="*80)
    
    from services.query.similarity import calculate_weighted_similarity, _get_tag_weight
    
    with get_db_connection() as conn:
        # Find images that might expose edge cases
        
        # 1. Images with very few tags
        print("\n--- Images with few tags ---")
        sparse = conn.execute("""
            SELECT id, 
                   COALESCE(tags_character, '') || ' ' || 
                   COALESCE(tags_copyright, '') || ' ' || 
                   COALESCE(tags_artist, '') || ' ' || 
                   COALESCE(tags_species, '') || ' ' || 
                   COALESCE(tags_general, '') || ' ' || 
                   COALESCE(tags_meta, '') as combined_tags
            FROM images
            LIMIT 100
        """).fetchall()
        sparse = [s for s in sparse if s['combined_tags'].strip()]
        sparse.sort(key=lambda x: len(x['combined_tags'].split()))
        sparse = sparse[:5]
        
        for img in sparse:
            tags = img['combined_tags'].split()
            weights = [_get_tag_weight(t) for t in tags]
            print(f"  ID {img['id']}: {len(tags)} tags, total weight: {sum(weights):.4f}")
            print(f"    Tags: {', '.join(tags[:10])}{'...' if len(tags) > 10 else ''}")
        
        # 2. Images with many tags
        print("\n--- Images with many tags ---")
        dense = conn.execute("""
            SELECT id, 
                   COALESCE(tags_character, '') || ' ' || 
                   COALESCE(tags_copyright, '') || ' ' || 
                   COALESCE(tags_artist, '') || ' ' || 
                   COALESCE(tags_species, '') || ' ' || 
                   COALESCE(tags_general, '') || ' ' || 
                   COALESCE(tags_meta, '') as combined_tags
            FROM images
            LIMIT 100
        """).fetchall()
        dense = [s for s in dense if s['combined_tags'].strip()]
        dense.sort(key=lambda x: len(x['combined_tags'].split()), reverse=True)
        dense = dense[:5]
        
        for img in dense:
            tags = img['combined_tags'].split()
            weights = [_get_tag_weight(t) for t in tags]
            print(f"  ID {img['id']}: {len(tags)} tags, total weight: {sum(weights):.4f}")
        
        # 3. Character-heavy images
        print("\n--- Similarity between images with same character ---")
        # Find a popular character
        char_query = """
            SELECT t.name, COUNT(*) as cnt
            FROM tags t
            JOIN image_tags it ON t.id = it.tag_id
            WHERE t.category = 'character'
            GROUP BY t.id
            ORDER BY cnt DESC
            LIMIT 1
        """
        top_char = conn.execute(char_query).fetchone()
        
        if top_char:
            print(f"  Using character: {top_char['name']} ({top_char['cnt']} images)")
            
            # Get 3 random images with this character
            char_images = conn.execute("""
                SELECT i.id, 
                       COALESCE(i.tags_character, '') || ' ' || 
                       COALESCE(i.tags_copyright, '') || ' ' || 
                       COALESCE(i.tags_artist, '') || ' ' || 
                       COALESCE(i.tags_species, '') || ' ' || 
                       COALESCE(i.tags_general, '') || ' ' || 
                       COALESCE(i.tags_meta, '') as combined_tags
                FROM images i
                JOIN image_tags it ON i.id = it.image_id
                JOIN tags t ON it.tag_id = t.id
                WHERE t.name = ?
                ORDER BY RANDOM()
                LIMIT 3
            """, [top_char['name']]).fetchall()
            
            if len(char_images) >= 2:
                for i, img1 in enumerate(char_images):
                    for img2 in char_images[i+1:]:
                        sim = calculate_weighted_similarity(img1['combined_tags'], img2['combined_tags'])
                        print(f"    Image {img1['id']} vs {img2['id']}: similarity = {sim:.4f}")
    
    # 4. Test the 0.1 fallback for unknown tags
    print("\n--- Unknown tag handling ---")
    fake_tags1 = "1girl completely_fake_tag_xyz abc123"
    fake_tags2 = "1girl another_fake_tag"
    
    for tag in fake_tags1.split():
        w = _get_tag_weight(tag)
        status = "UNKNOWN (fallback)" if w == 0.1 else "found"
        print(f"  '{tag}': weight = {w:.4f} ({status})")


def suggest_improvements():
    """Based on analysis, suggest concrete improvements."""
    print("\n" + "="*80)
    print("SUGGESTED IMPROVEMENTS")
    print("="*80)
    
    total_images = get_image_count_from_db()
    
    print("""
Based on the analysis, here are potential improvements:

1. **IDF Formula Enhancement**
   Current:  1 / log(freq + 1)
   Problem:  Low dynamic range, rare & common tags aren't differentiated enough
   
   Proposed: log(N / (freq + 1)) + 1  where N = total images
   Benefit:  Standard TF-IDF with better discrimination
   
2. **Asymmetric Matching Option**
   Current:  Symmetric Jaccard (penalizes extra tags equally)
   Problem:  An image with 100 tags matching 30/30 of query scores lower
             than an image with 30 tags matching 30/30
   
   Proposed: Asymmetric mode that considers query coverage separately
   Formula:  α × (intersection/query_tags) + (1-α) × (intersection/union)
   
3. **Unknown Tag Penalty**
   Current:  Returns 0.1 for unknown tags
   Problem:  Arbitrary magic number, may inflate scores for typos
   
   Proposed: Return 0.0 or make configurable
   
4. **Category Weight Normalization**
   Current:  Weights range 0.3 to 6.0 (20x difference)
   Problem:  Category weight dominates over IDF for high-weight categories
   
   Proposed: Either normalize weights or add IDF dampening factor
""")
    
    print(f"\n--- Quick Math Example with total_images={total_images:,} ---")
    
    test_freqs = [1, 10, 100, 1000]
    print(f"\n{'Freq':<8} {'Current IDF':<14} {'Proposed IDF':<14} {'Improvement':<12}")
    print("-" * 50)
    
    for freq in test_freqs:
        current = 1.0 / log(freq + 1)
        proposed = log(total_images / (freq + 1)) + 1
        ratio = proposed / current
        print(f"{freq:<8} {current:<14.4f} {proposed:<14.4f} {ratio:<12.1f}x range")


def main():
    print("="*80)
    print("TAG SIMILARITY ANALYSIS REPORT")
    print("="*80)
    print(f"Using extended categories: {config.USE_EXTENDED_SIMILARITY}")
    print(f"Similarity method: {config.SIMILARITY_METHOD}")
    
    analyze_idf_distribution()
    analyze_category_weight_impact()
    analyze_similarity_scores()
    analyze_edge_cases()
    suggest_improvements()
    
    print("\n" + "="*80)
    print("Analysis complete!")
    print("="*80)


if __name__ == "__main__":
    main()
