import React, { useState, useMemo, useCallback } from 'react';
import { Search, Tag, Image, BarChart3, X, Plus, Minus, Edit3, Trash2, GitMerge, ChevronDown, ChevronRight, Check, Filter, Grid, List, Layers, FolderPlus, Download, Upload, Zap, Link2, MoreHorizontal, RefreshCw, AlertTriangle, Info } from 'lucide-react';

// ============================================================================
// MOCK DATA
// ============================================================================

const EXTENDED_CATEGORIES = [
  { key: '00_Subject_Count', name: 'Subject Count', shortcut: '0', desc: 'Count & Gender' },
  { key: '01_Body_Physique', name: 'Body Physique', shortcut: '1', desc: 'Permanent body traits' },
  { key: '02_Body_Hair', name: 'Body Hair', shortcut: '2', desc: 'Hair properties' },
  { key: '03_Body_Face', name: 'Body Face', shortcut: '3', desc: 'Eye color & face marks' },
  { key: '04_Body_Genitalia', name: 'Body Genitalia', shortcut: '4', desc: 'NSFW anatomy' },
  { key: '05_Attire_Main', name: 'Attire Main', shortcut: '5', desc: 'Main clothing' },
  { key: '06_Attire_Inner', name: 'Attire Inner', shortcut: '6', desc: 'Underwear' },
  { key: '07_Attire_Legwear', name: 'Attire Legwear', shortcut: '7', desc: 'Socks & hosiery' },
  { key: '08_Attire_Accessories', name: 'Accessories', shortcut: '8', desc: 'Jewelry, glasses' },
  { key: '09_Action', name: 'Action', shortcut: '9', desc: 'Activities' },
  { key: '10_Pose', name: 'Pose', shortcut: 'q', desc: 'Body positions' },
  { key: '11_Expression', name: 'Expression', shortcut: 'w', desc: 'Facial expressions' },
  { key: '12_Objects', name: 'Objects', shortcut: 'e', desc: 'Held/nearby objects' },
  { key: '13_Setting_Location', name: 'Location', shortcut: 'r', desc: 'Environment' },
  { key: '14_Setting_Elements', name: 'Elements', shortcut: 't', desc: 'Background elements' },
  { key: '15_Framing', name: 'Framing', shortcut: 'y', desc: 'Camera angle' },
  { key: '16_Focus', name: 'Focus', shortcut: 'u', desc: 'Visual emphasis' },
  { key: '17_Style', name: 'Style', shortcut: 'i', desc: 'Art style' },
  { key: '18_Effects', name: 'Effects', shortcut: 'o', desc: 'Visual effects' },
  { key: '19_Meta_Attributes', name: 'Meta Attributes', shortcut: 'p', desc: 'Image metadata' },
  { key: '20_Meta_Text', name: 'Meta Text', shortcut: 'a', desc: 'Text elements' },
  { key: '21_Status', name: 'Status', shortcut: 's', desc: 'State of being' },
];

const BASE_CATEGORIES = ['character', 'copyright', 'artist', 'species', 'general', 'meta'];

const MOCK_TAGS = [
  { name: '1girl', base: 'general', extended: '00_Subject_Count', count: 4521 },
  { name: 'solo', base: 'general', extended: '00_Subject_Count', count: 3876 },
  { name: 'blue_hair', base: 'general', extended: '02_Body_Hair', count: 1243 },
  { name: 'long_hair', base: 'general', extended: '02_Body_Hair', count: 3102 },
  { name: 'blue_eyes', base: 'general', extended: '03_Body_Face', count: 2156 },
  { name: 'smile', base: 'general', extended: null, count: 2341 },
  { name: 'sitting', base: 'general', extended: null, count: 876 },
  { name: 'standing', base: 'general', extended: null, count: 1432 },
  { name: 'looking_at_viewer', base: 'general', extended: null, count: 2876 },
  { name: 'school_uniform', base: 'general', extended: '05_Attire_Main', count: 567 },
  { name: 'hatsune_miku', base: 'character', extended: null, count: 654 },
  { name: 'remilia_scarlet', base: 'character', extended: null, count: 432 },
  { name: 'vocaloid', base: 'copyright', extended: null, count: 789 },
  { name: 'touhou', base: 'copyright', extended: null, count: 1234 },
  { name: 'highres', base: 'meta', extended: '19_Meta_Attributes', count: 3456 },
  { name: 'absurdres', base: 'meta', extended: '19_Meta_Attributes', count: 1234 },
  { name: 'outdoors', base: 'general', extended: '13_Setting_Location', count: 987 },
  { name: 'indoors', base: 'general', extended: '13_Setting_Location', count: 1543 },
  { name: 'twintails', base: 'general', extended: '02_Body_Hair', count: 421 },
  { name: 'ponytail', base: 'general', extended: '02_Body_Hair', count: 654 },
  { name: 'blush', base: 'general', extended: '11_Expression', count: 1876 },
  { name: 'open_mouth', base: 'general', extended: '11_Expression', count: 1234 },
  { name: 'thighhighs', base: 'general', extended: '07_Attire_Legwear', count: 876 },
  { name: 'misspeled_tga', base: 'general', extended: null, count: 2 },
];

const MOCK_IMAGES = Array.from({ length: 50 }, (_, i) => ({
  id: i + 1,
  filepath: `images/folder${Math.floor(i / 10) + 1}/image_${i + 1}.jpg`,
  thumb: `/thumbnails/thumb_${i + 1}.jpg`,
  tags: ['1girl', 'blue_hair', 'smile', 'school_uniform'].slice(0, Math.floor(Math.random() * 4) + 1),
}));

// ============================================================================
// STYLES
// ============================================================================

const styles = `
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

  * { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg-primary: #0f1114;
    --bg-secondary: #161a1f;
    --bg-tertiary: #1c2128;
    --bg-hover: #262d36;
    --bg-active: #2d3640;
    
    --border-color: #2d3640;
    --border-hover: #3d4a58;
    
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #6e7681;
    
    --accent-blue: #58a6ff;
    --accent-green: #3fb950;
    --accent-orange: #d29922;
    --accent-red: #f85149;
    --accent-purple: #a371f7;
    
    --font-sans: 'Plus Jakarta Sans', -apple-system, sans-serif;
    --font-mono: 'JetBrains Mono', monospace;
    
    --radius-sm: 4px;
    --radius-md: 6px;
    --radius-lg: 8px;
    
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
    --shadow-lg: 0 8px 24px rgba(0,0,0,0.5);
  }

  .tag-manager {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: var(--font-sans);
    font-size: 13px;
    overflow: hidden;
  }

  /* Header */
  .tm-header {
    flex-shrink: 0;
    height: 48px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    padding: 0 16px;
    gap: 16px;
  }

  .tm-logo {
    font-weight: 700;
    color: var(--accent-blue);
    font-size: 15px;
    letter-spacing: -0.3px;
  }

  .tm-breadcrumb { color: var(--text-muted); }

  .tm-title {
    font-weight: 600;
    color: var(--text-primary);
  }

  .tm-mode-tabs {
    display: flex;
    gap: 2px;
    background: var(--bg-tertiary);
    padding: 3px;
    border-radius: var(--radius-md);
    margin-left: 24px;
  }

  .tm-mode-tab {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .tm-mode-tab:hover { color: var(--text-primary); background: var(--bg-hover); }
  .tm-mode-tab.active { color: var(--text-primary); background: var(--bg-active); }

  .tm-header-stats {
    margin-left: auto;
    display: flex;
    gap: 20px;
    font-size: 12px;
    color: var(--text-muted);
  }

  .tm-header-stats .value {
    font-weight: 600;
    font-family: var(--font-mono);
  }

  .tm-header-stats .value.success { color: var(--accent-green); }
  .tm-header-stats .value.warning { color: var(--accent-orange); }

  /* Working Set Bar */
  .tm-working-set {
    flex-shrink: 0;
    background: linear-gradient(135deg, rgba(88, 166, 255, 0.08), rgba(163, 113, 247, 0.08));
    border-bottom: 1px solid rgba(88, 166, 255, 0.2);
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .tm-working-set.empty {
    background: var(--bg-secondary);
    border-bottom-color: var(--border-color);
  }

  .ws-label {
    font-weight: 600;
    color: var(--accent-blue);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .ws-count {
    font-family: var(--font-mono);
    font-weight: 600;
    color: var(--text-primary);
  }

  .ws-thumbs {
    display: flex;
    gap: 4px;
  }

  .ws-thumb {
    width: 36px;
    height: 36px;
    border-radius: var(--radius-sm);
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    color: var(--text-muted);
  }

  .ws-more {
    font-size: 11px;
    color: var(--text-secondary);
    margin-left: 4px;
  }

  .ws-actions {
    margin-left: auto;
    display: flex;
    gap: 8px;
  }

  .ws-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .ws-btn:hover {
    background: var(--bg-hover);
    border-color: var(--border-hover);
    color: var(--text-primary);
  }

  .ws-btn.primary {
    background: var(--accent-blue);
    border-color: var(--accent-blue);
    color: white;
  }

  .ws-btn.primary:hover {
    background: #4a9aef;
  }

  .ws-btn.danger:hover {
    background: rgba(248, 81, 73, 0.1);
    border-color: var(--accent-red);
    color: var(--accent-red);
  }

  /* Main Content */
  .tm-main {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  /* Sidebar */
  .tm-sidebar {
    width: 240px;
    flex-shrink: 0;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .tm-sidebar-search {
    padding: 12px;
    border-bottom: 1px solid var(--border-color);
  }

  .tm-search-input {
    width: 100%;
    padding: 8px 12px 8px 32px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-primary);
    font-size: 12px;
    outline: none;
    transition: border-color 0.15s;
  }

  .tm-search-input:focus {
    border-color: var(--accent-blue);
  }

  .tm-search-input::placeholder {
    color: var(--text-muted);
  }

  .tm-search-wrapper {
    position: relative;
  }

  .tm-search-wrapper svg {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
  }

  .tm-sidebar-content {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
  }

  /* Filter Sections */
  .filter-section {
    margin-bottom: 16px;
  }

  .filter-header {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    margin: 0 -8px;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    cursor: pointer;
    width: calc(100% + 16px);
    text-align: left;
    transition: all 0.15s;
  }

  .filter-header:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .filter-content {
    padding-top: 8px;
  }

  .filter-option {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    margin: 0 -8px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: background 0.15s;
  }

  .filter-option:hover {
    background: var(--bg-hover);
  }

  .filter-option input {
    accent-color: var(--accent-blue);
  }

  .filter-option .label {
    flex: 1;
    color: var(--text-secondary);
    font-size: 12px;
  }

  .filter-option.active .label {
    color: var(--text-primary);
  }

  .filter-option .count {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-muted);
  }

  /* Quick Actions */
  .quick-actions {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid var(--border-color);
  }

  .quick-action-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 8px;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    font-size: 12px;
    text-align: left;
    cursor: pointer;
    transition: all 0.15s;
  }

  .quick-action-btn:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .quick-action-btn svg {
    width: 14px;
    height: 14px;
  }

  /* Content Area */
  .tm-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .tm-content-header {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
  }

  .tm-content-count {
    font-size: 12px;
    color: var(--text-secondary);
  }

  .tm-content-count span {
    font-family: var(--font-mono);
    color: var(--text-primary);
    font-weight: 600;
  }

  .tm-content-controls {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .tm-view-toggle {
    display: flex;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    padding: 2px;
  }

  .tm-view-btn {
    padding: 4px 8px;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
    transition: all 0.15s;
  }

  .tm-view-btn:hover { color: var(--text-secondary); }
  .tm-view-btn.active { background: var(--bg-active); color: var(--text-primary); }

  /* Tag Table */
  .tm-tag-table {
    flex: 1;
    overflow-y: auto;
  }

  .tag-table {
    width: 100%;
    border-collapse: collapse;
  }

  .tag-table th {
    position: sticky;
    top: 0;
    background: var(--bg-secondary);
    padding: 10px 12px;
    text-align: left;
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid var(--border-color);
  }

  .tag-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border-color);
    vertical-align: middle;
  }

  .tag-table tr:hover td {
    background: var(--bg-hover);
  }

  .tag-table tr.selected td {
    background: rgba(88, 166, 255, 0.1);
  }

  .tag-name {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-primary);
  }

  .tag-category {
    display: inline-block;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
  }

  .tag-category.character { background: rgba(163, 113, 247, 0.15); color: var(--accent-purple); }
  .tag-category.copyright { background: rgba(210, 153, 34, 0.15); color: var(--accent-orange); }
  .tag-category.artist { background: rgba(248, 81, 73, 0.15); color: var(--accent-red); }
  .tag-category.general { background: rgba(88, 166, 255, 0.15); color: var(--accent-blue); }
  .tag-category.meta { background: rgba(110, 118, 129, 0.15); color: var(--text-secondary); }
  .tag-category.species { background: rgba(63, 185, 80, 0.15); color: var(--accent-green); }

  .tag-extended {
    font-size: 11px;
    color: var(--text-muted);
  }

  .tag-extended.missing {
    color: var(--accent-orange);
  }

  .tag-count {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-secondary);
    text-align: right;
  }

  .tag-actions {
    display: flex;
    gap: 4px;
    opacity: 0;
    transition: opacity 0.15s;
  }

  tr:hover .tag-actions {
    opacity: 1;
  }

  .tag-action-btn {
    padding: 4px;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
    transition: all 0.15s;
  }

  .tag-action-btn:hover {
    background: var(--bg-active);
    color: var(--text-primary);
  }

  /* Detail Panel */
  .tm-detail {
    width: 320px;
    flex-shrink: 0;
    background: var(--bg-secondary);
    border-left: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .tm-detail-header {
    flex-shrink: 0;
    padding: 16px;
    border-bottom: 1px solid var(--border-color);
  }

  .detail-tag-name {
    font-family: var(--font-mono);
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .detail-tag-count {
    font-size: 12px;
    color: var(--text-secondary);
  }

  .tm-detail-content {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }

  .detail-section {
    margin-bottom: 20px;
  }

  .detail-section-title {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 10px;
  }

  .detail-samples {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
  }

  .detail-sample {
    aspect-ratio: 1;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    font-size: 10px;
  }

  .detail-select {
    width: 100%;
    padding: 8px 12px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-primary);
    font-size: 12px;
    cursor: pointer;
    outline: none;
  }

  .detail-select:focus {
    border-color: var(--accent-blue);
  }

  .detail-implications {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .implication-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    font-size: 12px;
  }

  .implication-arrow {
    color: var(--text-muted);
  }

  .implication-tag {
    font-family: var(--font-mono);
    color: var(--accent-blue);
  }

  .detail-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .detail-action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 8px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-secondary);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s;
  }

  .detail-action-btn:hover {
    background: var(--bg-hover);
    border-color: var(--border-hover);
    color: var(--text-primary);
  }

  .detail-action-btn.danger:hover {
    background: rgba(248, 81, 73, 0.1);
    border-color: var(--accent-red);
    color: var(--accent-red);
  }

  .detail-action-btn.primary {
    background: rgba(88, 166, 255, 0.1);
    border-color: rgba(88, 166, 255, 0.3);
    color: var(--accent-blue);
  }

  .detail-action-btn.primary:hover {
    background: rgba(88, 166, 255, 0.2);
  }

  /* Bulk Actions Bar */
  .tm-bulk-bar {
    flex-shrink: 0;
    background: rgba(88, 166, 255, 0.08);
    border-bottom: 1px solid rgba(88, 166, 255, 0.2);
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .bulk-count {
    font-size: 12px;
    color: var(--accent-blue);
  }

  .bulk-count span {
    font-weight: 600;
  }

  .bulk-actions {
    display: flex;
    gap: 8px;
  }

  .bulk-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-secondary);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s;
  }

  .bulk-btn:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .bulk-clear {
    margin-left: auto;
    padding: 4px 8px;
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 12px;
    cursor: pointer;
  }

  .bulk-clear:hover {
    color: var(--text-primary);
  }

  /* Image Grid */
  .tm-image-grid {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }

  .image-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 8px;
  }

  .image-item {
    position: relative;
    aspect-ratio: 1;
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
    border: 2px solid transparent;
    cursor: pointer;
    overflow: hidden;
    transition: all 0.15s;
  }

  .image-item:hover {
    border-color: var(--border-hover);
  }

  .image-item.selected {
    border-color: var(--accent-blue);
  }

  .image-item .check {
    position: absolute;
    top: 6px;
    left: 6px;
    width: 20px;
    height: 20px;
    background: var(--bg-primary);
    border: 2px solid var(--border-color);
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.15s;
  }

  .image-item:hover .check,
  .image-item.selected .check {
    opacity: 1;
  }

  .image-item.selected .check {
    background: var(--accent-blue);
    border-color: var(--accent-blue);
    color: white;
  }

  .image-placeholder {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    font-size: 10px;
  }

  /* Stats Mode */
  .tm-stats {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
  }

  .stat-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: 20px;
  }

  .stat-value {
    font-family: var(--font-mono);
    font-size: 28px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .stat-label {
    font-size: 12px;
    color: var(--text-secondary);
  }

  .stat-change {
    font-size: 11px;
    margin-top: 8px;
  }

  .stat-change.positive { color: var(--accent-green); }
  .stat-change.negative { color: var(--accent-red); }

  .stats-section {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: 20px;
    margin-bottom: 16px;
  }

  .stats-section-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 16px;
  }

  .category-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
  }

  .category-bar-label {
    width: 100px;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .category-bar-track {
    flex: 1;
    height: 20px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    overflow: hidden;
  }

  .category-bar-fill {
    height: 100%;
    background: var(--accent-blue);
    border-radius: var(--radius-sm);
    transition: width 0.3s ease;
  }

  .category-bar-fill.character { background: var(--accent-purple); }
  .category-bar-fill.copyright { background: var(--accent-orange); }
  .category-bar-fill.artist { background: var(--accent-red); }
  .category-bar-fill.general { background: var(--accent-blue); }
  .category-bar-fill.meta { background: var(--text-muted); }
  .category-bar-fill.species { background: var(--accent-green); }

  .category-bar-value {
    width: 120px;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-secondary);
    text-align: right;
  }

  /* Keyboard Shortcuts Footer */
  .tm-footer {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 24px;
    padding: 8px 16px;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-color);
    font-size: 11px;
    color: var(--text-muted);
  }

  .tm-footer kbd {
    display: inline-block;
    padding: 2px 5px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 10px;
    margin-right: 4px;
  }

  /* Modal Styles */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-lg);
    width: 100%;
    max-width: 480px;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .modal-close {
    padding: 4px;
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
  }

  .modal-close:hover {
    color: var(--text-primary);
  }

  .modal-body {
    padding: 20px;
    overflow-y: auto;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 16px 20px;
    border-top: 1px solid var(--border-color);
  }

  .modal-btn {
    padding: 8px 16px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .modal-btn:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .modal-btn.primary {
    background: var(--accent-blue);
    border-color: var(--accent-blue);
    color: white;
  }

  .modal-btn.primary:hover {
    background: #4a9aef;
  }

  .modal-btn.danger {
    background: var(--accent-red);
    border-color: var(--accent-red);
    color: white;
  }

  .modal-input {
    width: 100%;
    padding: 10px 12px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-primary);
    font-size: 13px;
    outline: none;
    margin-bottom: 12px;
  }

  .modal-input:focus {
    border-color: var(--accent-blue);
  }

  .modal-label {
    display: block;
    font-size: 12px;
    font-weight: 500;
    color: var(--text-secondary);
    margin-bottom: 6px;
  }

  .modal-warning {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px;
    background: rgba(210, 153, 34, 0.1);
    border: 1px solid rgba(210, 153, 34, 0.3);
    border-radius: var(--radius-md);
    margin-bottom: 16px;
  }

  .modal-warning svg {
    flex-shrink: 0;
    color: var(--accent-orange);
  }

  .modal-warning-text {
    font-size: 12px;
    color: var(--text-secondary);
  }

  .modal-checkbox {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--text-secondary);
    margin-bottom: 8px;
  }

  .modal-checkbox input {
    accent-color: var(--accent-blue);
  }

  /* Scrollbar */
  ::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  ::-webkit-scrollbar-track {
    background: transparent;
  }

  ::-webkit-scrollbar-thumb {
    background: var(--bg-active);
    border-radius: 4px;
  }

  ::-webkit-scrollbar-thumb:hover {
    background: var(--border-hover);
  }
`;

// ============================================================================
// COMPONENTS
// ============================================================================

function TagManager() {
  const [mode, setMode] = useState('tags'); // 'tags', 'images', 'stats'
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState(new Set());
  const [selectedImages, setSelectedImages] = useState(new Set());
  const [workingSet, setWorkingSet] = useState([]);
  const [currentTag, setCurrentTag] = useState(MOCK_TAGS[0]);
  const [viewMode, setViewMode] = useState('list');
  const [showDetailPanel, setShowDetailPanel] = useState(true);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [showMergeModal, setShowMergeModal] = useState(false);
  
  // Filter state
  const [filters, setFilters] = useState({
    status: 'all',
    baseCategory: [],
    extendedCategory: [],
    sort: 'count_desc'
  });

  const [expandedSections, setExpandedSections] = useState({
    status: true,
    baseCategory: true,
    extendedCategory: false,
    sort: false
  });

  // Filter tags
  const filteredTags = useMemo(() => {
    let tags = [...MOCK_TAGS];
    
    if (searchQuery) {
      tags = tags.filter(t => t.name.includes(searchQuery.toLowerCase()));
    }
    
    if (filters.status === 'uncategorized') {
      tags = tags.filter(t => !t.extended);
    } else if (filters.status === 'orphaned') {
      tags = tags.filter(t => t.count === 0);
    } else if (filters.status === 'low_usage') {
      tags = tags.filter(t => t.count < 5);
    }
    
    if (filters.baseCategory.length > 0) {
      tags = tags.filter(t => filters.baseCategory.includes(t.base));
    }
    
    // Sort
    tags.sort((a, b) => {
      switch (filters.sort) {
        case 'count_asc': return a.count - b.count;
        case 'alpha_asc': return a.name.localeCompare(b.name);
        case 'alpha_desc': return b.name.localeCompare(a.name);
        default: return b.count - a.count;
      }
    });
    
    return tags;
  }, [searchQuery, filters]);

  const toggleSection = (section) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const toggleTagSelection = (tagName) => {
    setSelectedTags(prev => {
      const next = new Set(prev);
      if (next.has(tagName)) next.delete(tagName);
      else next.add(tagName);
      return next;
    });
  };

  const toggleImageSelection = (imageId) => {
    setSelectedImages(prev => {
      const next = new Set(prev);
      if (next.has(imageId)) next.delete(imageId);
      else next.add(imageId);
      return next;
    });
  };

  const addSelectedToWorkingSet = () => {
    const images = MOCK_IMAGES.filter(img => selectedImages.has(img.id));
    setWorkingSet(prev => {
      const existing = new Set(prev.map(i => i.id));
      const newImages = images.filter(i => !existing.has(i.id));
      return [...prev, ...newImages];
    });
    setSelectedImages(new Set());
  };

  const clearWorkingSet = () => setWorkingSet([]);

  // Stats
  const stats = useMemo(() => ({
    totalTags: MOCK_TAGS.length,
    categorized: MOCK_TAGS.filter(t => t.extended).length,
    uncategorized: MOCK_TAGS.filter(t => !t.extended && t.base === 'general').length,
    orphaned: MOCK_TAGS.filter(t => t.count === 0).length,
    totalImages: MOCK_IMAGES.length,
    avgTagsPerImage: 4.2,
    byCategory: BASE_CATEGORIES.map(cat => ({
      name: cat,
      count: MOCK_TAGS.filter(t => t.base === cat).length,
      percentage: (MOCK_TAGS.filter(t => t.base === cat).length / MOCK_TAGS.length * 100).toFixed(1)
    }))
  }), []);

  return (
    <>
      <style>{styles}</style>
      <div className="tag-manager">
        {/* Header */}
        <header className="tm-header">
          <span className="tm-logo">ChibiBooru</span>
          <span className="tm-breadcrumb">›</span>
          <span className="tm-title">Tag Manager</span>
          
          <div className="tm-mode-tabs">
            <button 
              className={`tm-mode-tab ${mode === 'tags' ? 'active' : ''}`}
              onClick={() => setMode('tags')}
            >
              <Tag size={14} /> Tags
            </button>
            <button 
              className={`tm-mode-tab ${mode === 'images' ? 'active' : ''}`}
              onClick={() => setMode('images')}
            >
              <Image size={14} /> Images
            </button>
            <button 
              className={`tm-mode-tab ${mode === 'stats' ? 'active' : ''}`}
              onClick={() => setMode('stats')}
            >
              <BarChart3 size={14} /> Stats
            </button>
          </div>
          
          <div className="tm-header-stats">
            <span><span className="value success">{stats.categorized}</span> categorized</span>
            <span><span className="value warning">{stats.uncategorized}</span> need review</span>
          </div>
        </header>

        {/* Working Set Bar */}
        <div className={`tm-working-set ${workingSet.length === 0 ? 'empty' : ''}`}>
          <span className="ws-label">Working Set</span>
          <span className="ws-count">{workingSet.length} images</span>
          
          {workingSet.length > 0 && (
            <>
              <div className="ws-thumbs">
                {workingSet.slice(0, 6).map((img, i) => (
                  <div key={i} className="ws-thumb">{img.id}</div>
                ))}
                {workingSet.length > 6 && (
                  <span className="ws-more">+{workingSet.length - 6}</span>
                )}
              </div>
              
              <div className="ws-actions">
                <button className="ws-btn primary">
                  <Plus size={14} /> Add Tags
                </button>
                <button className="ws-btn">
                  <Minus size={14} /> Remove Tags
                </button>
                <button className="ws-btn">
                  <FolderPlus size={14} /> Save as Pool
                </button>
                <button className="ws-btn danger" onClick={clearWorkingSet}>
                  <X size={14} /> Clear
                </button>
              </div>
            </>
          )}
          
          {workingSet.length === 0 && (
            <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
              Select images to build a working set for bulk operations
            </span>
          )}
        </div>

        {/* Bulk Tag Actions Bar */}
        {mode === 'tags' && selectedTags.size > 0 && (
          <div className="tm-bulk-bar">
            <span className="bulk-count"><span>{selectedTags.size}</span> tags selected</span>
            <div className="bulk-actions">
              <button className="bulk-btn">
                <Tag size={14} /> Set Base Category
              </button>
              <button className="bulk-btn">
                <Layers size={14} /> Set Extended
              </button>
              <button className="bulk-btn" onClick={() => setShowMergeModal(true)}>
                <GitMerge size={14} /> Merge
              </button>
              <button className="bulk-btn">
                <Trash2 size={14} /> Delete
              </button>
            </div>
            <button className="bulk-clear" onClick={() => setSelectedTags(new Set())}>
              Clear selection
            </button>
          </div>
        )}

        {/* Main Content */}
        <div className="tm-main">
          {/* Sidebar */}
          <aside className="tm-sidebar">
            <div className="tm-sidebar-search">
              <div className="tm-search-wrapper">
                <Search size={14} />
                <input 
                  type="text"
                  className="tm-search-input"
                  placeholder={mode === 'tags' ? 'Search tags...' : 'Search images...'}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            </div>
            
            <div className="tm-sidebar-content">
              {mode === 'tags' && (
                <>
                  {/* Status Filter */}
                  <div className="filter-section">
                    <button className="filter-header" onClick={() => toggleSection('status')}>
                      {expandedSections.status ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      Status
                    </button>
                    {expandedSections.status && (
                      <div className="filter-content">
                        {[
                          { value: 'all', label: 'All Tags', count: stats.totalTags },
                          { value: 'uncategorized', label: 'Uncategorized', count: stats.uncategorized },
                          { value: 'orphaned', label: 'Orphaned', count: stats.orphaned },
                          { value: 'low_usage', label: 'Low Usage (<5)', count: 3 }
                        ].map(opt => (
                          <label key={opt.value} className={`filter-option ${filters.status === opt.value ? 'active' : ''}`}>
                            <input 
                              type="radio" 
                              name="status" 
                              checked={filters.status === opt.value}
                              onChange={() => setFilters(f => ({ ...f, status: opt.value }))}
                            />
                            <span className="label">{opt.label}</span>
                            <span className="count">{opt.count}</span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Base Category Filter */}
                  <div className="filter-section">
                    <button className="filter-header" onClick={() => toggleSection('baseCategory')}>
                      {expandedSections.baseCategory ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      Base Category
                    </button>
                    {expandedSections.baseCategory && (
                      <div className="filter-content">
                        {BASE_CATEGORIES.map(cat => {
                          const count = MOCK_TAGS.filter(t => t.base === cat).length;
                          return (
                            <label key={cat} className="filter-option">
                              <input 
                                type="checkbox"
                                checked={filters.baseCategory.includes(cat)}
                                onChange={(e) => {
                                  setFilters(f => ({
                                    ...f,
                                    baseCategory: e.target.checked 
                                      ? [...f.baseCategory, cat]
                                      : f.baseCategory.filter(c => c !== cat)
                                  }));
                                }}
                              />
                              <span className="label">{cat}</span>
                              <span className="count">{count}</span>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* Extended Category Filter */}
                  <div className="filter-section">
                    <button className="filter-header" onClick={() => toggleSection('extendedCategory')}>
                      {expandedSections.extendedCategory ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      Extended Category
                    </button>
                    {expandedSections.extendedCategory && (
                      <div className="filter-content" style={{ maxHeight: '200px', overflowY: 'auto' }}>
                        {EXTENDED_CATEGORIES.slice(0, 10).map(cat => (
                          <label key={cat.key} className="filter-option">
                            <input type="checkbox" />
                            <span className="label">{cat.name}</span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Quick Actions */}
                  <div className="quick-actions">
                    <button className="quick-action-btn">
                      <Zap size={14} style={{ color: 'var(--accent-orange)' }} />
                      Auto-Categorize
                    </button>
                    <button className="quick-action-btn">
                      <Download size={14} />
                      Export Categories
                    </button>
                    <button className="quick-action-btn">
                      <Upload size={14} />
                      Import Categories
                    </button>
                    <button className="quick-action-btn">
                      <Link2 size={14} />
                      Manage Implications
                    </button>
                  </div>
                </>
              )}

              {mode === 'images' && (
                <>
                  <div className="filter-section">
                    <button className="filter-header" onClick={() => toggleSection('status')}>
                      {expandedSections.status ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      Quick Filters
                    </button>
                    {expandedSections.status && (
                      <div className="filter-content">
                        <label className="filter-option">
                          <input type="radio" name="img-filter" />
                          <span className="label">All Images</span>
                        </label>
                        <label className="filter-option">
                          <input type="radio" name="img-filter" />
                          <span className="label">AI-tagged only</span>
                        </label>
                        <label className="filter-option">
                          <input type="radio" name="img-filter" />
                          <span className="label">Needs review</span>
                        </label>
                        <label className="filter-option">
                          <input type="radio" name="img-filter" />
                          <span className="label">No rating</span>
                        </label>
                      </div>
                    )}
                  </div>

                  <div className="quick-actions">
                    <button className="quick-action-btn primary" onClick={addSelectedToWorkingSet} disabled={selectedImages.size === 0}>
                      <Plus size={14} />
                      Add {selectedImages.size || ''} to Working Set
                    </button>
                  </div>
                </>
              )}
            </div>
          </aside>

          {/* Content Area */}
          {mode === 'tags' && (
            <>
              <div className="tm-content">
                <div className="tm-content-header">
                  <span className="tm-content-count">
                    Showing <span>{filteredTags.length}</span> tags
                  </span>
                  <div className="tm-content-controls">
                    <div className="tm-view-toggle">
                      <button 
                        className={`tm-view-btn ${viewMode === 'list' ? 'active' : ''}`}
                        onClick={() => setViewMode('list')}
                      >
                        <List size={14} />
                      </button>
                      <button 
                        className={`tm-view-btn ${viewMode === 'grid' ? 'active' : ''}`}
                        onClick={() => setViewMode('grid')}
                      >
                        <Grid size={14} />
                      </button>
                    </div>
                  </div>
                </div>

                <div className="tm-tag-table">
                  <table className="tag-table">
                    <thead>
                      <tr>
                        <th style={{ width: '40px' }}>
                          <input 
                            type="checkbox" 
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedTags(new Set(filteredTags.map(t => t.name)));
                              } else {
                                setSelectedTags(new Set());
                              }
                            }}
                          />
                        </th>
                        <th>Tag Name</th>
                        <th>Base</th>
                        <th>Extended</th>
                        <th style={{ textAlign: 'right' }}>Count</th>
                        <th style={{ width: '80px' }}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredTags.map(tag => (
                        <tr 
                          key={tag.name} 
                          className={selectedTags.has(tag.name) ? 'selected' : ''}
                          onClick={() => setCurrentTag(tag)}
                        >
                          <td onClick={(e) => e.stopPropagation()}>
                            <input 
                              type="checkbox"
                              checked={selectedTags.has(tag.name)}
                              onChange={() => toggleTagSelection(tag.name)}
                            />
                          </td>
                          <td><span className="tag-name">{tag.name}</span></td>
                          <td><span className={`tag-category ${tag.base}`}>{tag.base}</span></td>
                          <td>
                            <span className={`tag-extended ${!tag.extended ? 'missing' : ''}`}>
                              {tag.extended ? EXTENDED_CATEGORIES.find(c => c.key === tag.extended)?.name : '—'}
                            </span>
                          </td>
                          <td><span className="tag-count">{tag.count.toLocaleString()}</span></td>
                          <td>
                            <div className="tag-actions">
                              <button className="tag-action-btn" onClick={(e) => { e.stopPropagation(); setShowRenameModal(true); }}>
                                <Edit3 size={14} />
                              </button>
                              <button className="tag-action-btn">
                                <MoreHorizontal size={14} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Detail Panel */}
              {showDetailPanel && currentTag && (
                <aside className="tm-detail">
                  <div className="tm-detail-header">
                    <div className="detail-tag-name">{currentTag.name}</div>
                    <div className="detail-tag-count">{currentTag.count.toLocaleString()} images</div>
                  </div>
                  
                  <div className="tm-detail-content">
                    <div className="detail-section">
                      <div className="detail-section-title">Sample Images</div>
                      <div className="detail-samples">
                        {[1,2,3,4,5,6].map(i => (
                          <div key={i} className="detail-sample">IMG</div>
                        ))}
                      </div>
                    </div>

                    <div className="detail-section">
                      <div className="detail-section-title">Base Category</div>
                      <select className="detail-select" defaultValue={currentTag.base}>
                        {BASE_CATEGORIES.map(cat => (
                          <option key={cat} value={cat}>{cat}</option>
                        ))}
                      </select>
                    </div>

                    <div className="detail-section">
                      <div className="detail-section-title">Extended Category</div>
                      <select className="detail-select" defaultValue={currentTag.extended || ''}>
                        <option value="">— Not set —</option>
                        {EXTENDED_CATEGORIES.map(cat => (
                          <option key={cat.key} value={cat.key}>{cat.name}</option>
                        ))}
                      </select>
                    </div>

                    <div className="detail-section">
                      <div className="detail-section-title">Implications</div>
                      <div className="detail-implications">
                        <div className="implication-item">
                          <span className="implication-arrow">→</span>
                          <span className="implication-tag">hair</span>
                          <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>(parent)</span>
                        </div>
                      </div>
                    </div>

                    <div className="detail-section">
                      <div className="detail-section-title">Actions</div>
                      <div className="detail-actions">
                        <button className="detail-action-btn" onClick={() => setShowRenameModal(true)}>
                          <Edit3 size={14} /> Rename
                        </button>
                        <button className="detail-action-btn">
                          <GitMerge size={14} /> Merge
                        </button>
                        <button className="detail-action-btn primary">
                          <Layers size={14} /> Add to Set
                        </button>
                        <button className="detail-action-btn danger">
                          <Trash2 size={14} /> Delete
                        </button>
                      </div>
                    </div>
                  </div>
                </aside>
              )}
            </>
          )}

          {mode === 'images' && (
            <>
              <div className="tm-content">
                <div className="tm-content-header">
                  <span className="tm-content-count">
                    Search results: <span>{MOCK_IMAGES.length}</span> images
                  </span>
                  <div className="tm-content-controls">
                    <button className="ws-btn" onClick={() => setSelectedImages(new Set(MOCK_IMAGES.map(i => i.id)))}>
                      Select All
                    </button>
                    <button className="ws-btn primary" onClick={addSelectedToWorkingSet}>
                      Add {selectedImages.size || 'All'} to Working Set
                    </button>
                  </div>
                </div>

                <div className="tm-image-grid">
                  <div className="image-grid">
                    {MOCK_IMAGES.map(img => (
                      <div 
                        key={img.id}
                        className={`image-item ${selectedImages.has(img.id) ? 'selected' : ''}`}
                        onClick={() => toggleImageSelection(img.id)}
                      >
                        <div className="check">
                          {selectedImages.has(img.id) && <Check size={12} />}
                        </div>
                        <div className="image-placeholder">{img.id}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Bulk Tag Editor Panel */}
              {workingSet.length > 0 && (
                <aside className="tm-detail">
                  <div className="tm-detail-header">
                    <div className="detail-tag-name">Bulk Tag Editor</div>
                    <div className="detail-tag-count">{workingSet.length} images selected</div>
                  </div>
                  
                  <div className="tm-detail-content">
                    <div className="detail-section">
                      <div className="detail-section-title">Tags on ALL images</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                        <span className="tag-category general">1girl</span>
                      </div>
                    </div>

                    <div className="detail-section">
                      <div className="detail-section-title">Tags on SOME images</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                        <span className="tag-category general">smile (18)</span>
                        <span className="tag-category general">sitting (12)</span>
                        <span className="tag-category general">outdoors (6)</span>
                      </div>
                    </div>

                    <div className="detail-section">
                      <div className="detail-section-title">Add Tags</div>
                      <input type="text" className="detail-select" placeholder="Search or enter tag..." />
                      <div style={{ marginTop: '8px' }}>
                        <button className="detail-action-btn primary" style={{ width: '100%' }}>
                          <Plus size={14} /> Apply Tags to All
                        </button>
                      </div>
                    </div>

                    <div className="detail-section">
                      <div className="detail-section-title">Remove Tags</div>
                      <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                        Click tags above to queue removal
                      </p>
                      <button className="detail-action-btn danger" style={{ width: '100%' }}>
                        <Minus size={14} /> Remove Selected Tags
                      </button>
                    </div>
                  </div>
                </aside>
              )}
            </>
          )}

          {mode === 'stats' && (
            <div className="tm-stats">
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-value">{stats.totalTags.toLocaleString()}</div>
                  <div className="stat-label">Total Tags</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{stats.totalImages.toLocaleString()}</div>
                  <div className="stat-label">Total Images</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{stats.categorized}</div>
                  <div className="stat-label">Categorized Tags</div>
                  <div className="stat-change positive">
                    {((stats.categorized / stats.totalTags) * 100).toFixed(1)}% complete
                  </div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{stats.avgTagsPerImage}</div>
                  <div className="stat-label">Avg Tags per Image</div>
                </div>
              </div>

              <div className="stats-section">
                <div className="stats-section-title">Tags by Base Category</div>
                {stats.byCategory.map(cat => (
                  <div key={cat.name} className="category-bar">
                    <span className="category-bar-label">{cat.name}</span>
                    <div className="category-bar-track">
                      <div 
                        className={`category-bar-fill ${cat.name}`}
                        style={{ width: `${cat.percentage}%` }}
                      />
                    </div>
                    <span className="category-bar-value">
                      {cat.count} ({cat.percentage}%)
                    </span>
                  </div>
                ))}
              </div>

              <div className="stats-section">
                <div className="stats-section-title">Problem Tags</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  <div>
                    <h4 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                      <AlertTriangle size={14} style={{ color: 'var(--accent-orange)', verticalAlign: 'middle', marginRight: '6px' }} />
                      Uncategorized (high usage)
                    </h4>
                    {MOCK_TAGS.filter(t => !t.extended && t.count > 500).slice(0, 5).map(t => (
                      <div key={t.name} style={{ padding: '4px 0', fontSize: '12px', color: 'var(--text-secondary)' }}>
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{t.name}</span>
                        <span style={{ marginLeft: '8px', color: 'var(--text-muted)' }}>({t.count})</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <h4 style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                      <Info size={14} style={{ color: 'var(--accent-blue)', verticalAlign: 'middle', marginRight: '6px' }} />
                      Low Usage (&lt;5 images)
                    </h4>
                    {MOCK_TAGS.filter(t => t.count < 5).map(t => (
                      <div key={t.name} style={{ padding: '4px 0', fontSize: '12px', color: 'var(--text-secondary)' }}>
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{t.name}</span>
                        <span style={{ marginLeft: '8px', color: 'var(--text-muted)' }}>({t.count})</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer with keyboard shortcuts */}
        <footer className="tm-footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>Space</kbd> select</span>
          <span><kbd>Enter</kbd> open detail</span>
          <span><kbd>0-9</kbd> set category</span>
          <span><kbd>E</kbd> edit</span>
          <span><kbd>D</kbd> delete</span>
          <span><kbd>?</kbd> all shortcuts</span>
        </footer>

        {/* Rename Modal */}
        {showRenameModal && (
          <div className="modal-overlay" onClick={() => setShowRenameModal(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <span className="modal-title">Rename Tag</span>
                <button className="modal-close" onClick={() => setShowRenameModal(false)}>
                  <X size={18} />
                </button>
              </div>
              <div className="modal-body">
                <label className="modal-label">Current name</label>
                <input type="text" className="modal-input" value={currentTag?.name || ''} disabled />
                
                <label className="modal-label">New name</label>
                <input type="text" className="modal-input" placeholder="Enter new tag name..." />
                
                <div className="modal-warning">
                  <AlertTriangle size={16} />
                  <span className="modal-warning-text">
                    This will update {currentTag?.count || 0} images. This action cannot be undone.
                  </span>
                </div>
                
                <label className="modal-checkbox">
                  <input type="checkbox" defaultChecked />
                  Create alias from old name
                </label>
                <label className="modal-checkbox">
                  <input type="checkbox" />
                  Update related implications
                </label>
              </div>
              <div className="modal-footer">
                <button className="modal-btn" onClick={() => setShowRenameModal(false)}>Cancel</button>
                <button className="modal-btn primary">Rename Tag</button>
              </div>
            </div>
          </div>
        )}

        {/* Merge Modal */}
        {showMergeModal && (
          <div className="modal-overlay" onClick={() => setShowMergeModal(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <span className="modal-title">Merge Tags</span>
                <button className="modal-close" onClick={() => setShowMergeModal(false)}>
                  <X size={18} />
                </button>
              </div>
              <div className="modal-body">
                <label className="modal-label">Tags to merge</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '16px' }}>
                  {Array.from(selectedTags).map(tag => (
                    <span key={tag} className="tag-category general">{tag}</span>
                  ))}
                </div>
                
                <label className="modal-label">Merge into</label>
                <select className="modal-input" style={{ marginBottom: '16px' }}>
                  {Array.from(selectedTags).map(tag => (
                    <option key={tag} value={tag}>{tag}</option>
                  ))}
                </select>
                
                <label className="modal-checkbox">
                  <input type="checkbox" defaultChecked />
                  Create aliases from merged names
                </label>
                <label className="modal-checkbox">
                  <input type="checkbox" defaultChecked />
                  Preserve category from target tag
                </label>
              </div>
              <div className="modal-footer">
                <button className="modal-btn" onClick={() => setShowMergeModal(false)}>Cancel</button>
                <button className="modal-btn primary">Merge Tags</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

export default TagManager;
