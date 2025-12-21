import React, { useState } from 'react';
import { Search, Filter, Tag, Edit3, Trash2, GitMerge, ArrowRight, ChevronDown, ChevronRight, Grid, List, Image, X, Check, Zap, Download, Upload, MoreHorizontal, Eye, Link2 } from 'lucide-react';

/*
  TAG BROWSER OVERHAUL
  
  Current problems:
  1. Tag browser is just a list - not useful for management
  2. Tag categorization is a separate page
  3. No way to see sample images for a tag
  4. No bulk operations (merge, delete, recategorize)
  5. No visibility into tag relationships (implications, aliases)
  6. Can't easily find uncategorized or problem tags
  7. No keyboard shortcuts for power users
  
  Solution: Combined Tag Management Interface
  
  Layout:
  ┌─────────────────────────────────────────────────────────────────────┐
  │ Header (compact)                                                    │
  ├────────────────┬──────────────────────────────────┬─────────────────┤
  │ Filters        │ Tag List                         │ Tag Detail      │
  │ 220px          │ (flexible)                       │ 320px           │
  │                │                                  │                 │
  │ ▼ Status       │ ┌────┬─────────┬─────┬─────────┐ │ [Tag Preview]   │
  │   ● All        │ │ ☐  │ tag_name│ cat │ count   │ │                 │
  │   ○ Uncateg.   │ ├────┼─────────┼─────┼─────────┤ │ Sample Images   │
  │   ○ Needs Rev. │ │ ☐  │ another │ gen │ 234     │ │ ┌───┐ ┌───┐    │
  │                │ └────┴─────────┴─────┴─────────┘ │ │   │ │   │    │
  │ ▼ Category     │                                  │ └───┘ └───┘    │
  │   ☐ Character  │                                  │                 │
  │   ☐ Copyright  │                                  │ Category        │
  │   ☐ Artist     │                                  │ [dropdown]      │
  │   ...          │                                  │                 │
  │                │                                  │ Extended Cat    │
  │ ▼ Extended     │                                  │ [dropdown]      │
  │   ☐ Subject    │                                  │                 │
  │   ☐ Body       │                                  │ Implications    │
  │   ...          │                                  │ tag1 → tag2     │
  │                │                                  │                 │
  │ ▼ Sort         │                                  │ Actions         │
  │   ○ Count ↓    │                                  │ [Edit] [Delete] │
  │   ○ Alpha ↑    │                                  │ [Merge] [Alias] │
  └────────────────┴──────────────────────────────────┴─────────────────┘
*/

// Extended categories data
const EXTENDED_CATEGORIES = [
  { key: '00_Subject_Count', name: 'Subject Count', shortcut: '0', color: '#3b82f6' },
  { key: '01_Body_Physique', name: 'Body Physique', shortcut: '1', color: '#8b5cf6' },
  { key: '02_Body_Hair', name: 'Hair', shortcut: '2', color: '#ec4899' },
  { key: '03_Body_Face', name: 'Face', shortcut: '3', color: '#f97316' },
  { key: '04_Body_Sensitive', name: 'Sensitive Parts', shortcut: '4', color: '#ef4444' },
  { key: '05_Attire_Head', name: 'Head Attire', shortcut: '5', color: '#22c55e' },
  { key: '06_Attire_Upper', name: 'Upper Attire', shortcut: '6', color: '#14b8a6' },
  { key: '07_Attire_Lower', name: 'Lower Attire', shortcut: '7', color: '#06b6d4' },
  { key: '08_Attire_Full', name: 'Full Attire', shortcut: '8', color: '#0ea5e9' },
  { key: '09_Action', name: 'Actions', shortcut: '9', color: '#f59e0b' },
  { key: '10_Pose', name: 'Poses', shortcut: 'q', color: '#84cc16' },
  { key: '11_Expression', name: 'Expressions', shortcut: 'e', color: '#facc15' },
  { key: '12_Objects', name: 'Objects', shortcut: 'r', color: '#a855f7' },
  { key: '13_Setting_Place', name: 'Setting/Place', shortcut: 't', color: '#6366f1' },
  { key: '14_Setting_Nature', name: 'Nature', shortcut: 'y', color: '#22c55e' },
  { key: '15_Framing', name: 'Framing', shortcut: 'u', color: '#64748b' },
  { key: '16_Focus', name: 'Focus', shortcut: 'i', color: '#78716c' },
  { key: '17_Style_Art', name: 'Art Style', shortcut: 'o', color: '#d946ef' },
  { key: '18_Style_Tech', name: 'Technical Style', shortcut: 'p', color: '#c084fc' },
  { key: '19_Meta_Attributes', name: 'Meta Attributes', shortcut: 'a', color: '#fbbf24' },
  { key: '20_Meta_Text', name: 'Meta Text', shortcut: 's', color: '#f472b6' },
  { key: '21_Status', name: 'Status', shortcut: 'z', color: '#94a3b8' },
];

const BASE_CATEGORIES = [
  { key: 'character', name: 'Character', color: '#ff6b9d' },
  { key: 'copyright', name: 'Copyright', color: '#c084fc' },
  { key: 'artist', name: 'Artist', color: '#f97316' },
  { key: 'species', name: 'Species', color: '#22c55e' },
  { key: 'meta', name: 'Meta', color: '#fbbf24' },
  { key: 'general', name: 'General', color: '#3b82f6' },
];

// Demo data
const demoTags = [
  { name: '1girl', category: 'general', extended: '00_Subject_Count', count: 4521, uncategorized: false },
  { name: 'hatsune_miku', category: 'character', extended: null, count: 892, uncategorized: false },
  { name: 'blue_hair', category: 'general', extended: '02_Body_Hair', count: 1243, uncategorized: false },
  { name: 'sitting', category: 'general', extended: null, count: 876, uncategorized: true },
  { name: 'smile', category: 'general', extended: null, count: 2341, uncategorized: true },
  { name: 'long_hair', category: 'general', extended: '02_Body_Hair', count: 3102, uncategorized: false },
  { name: 'vocaloid', category: 'copyright', extended: null, count: 654, uncategorized: false },
  { name: 'twintails', category: 'general', extended: null, count: 421, uncategorized: true },
  { name: 'school_uniform', category: 'general', extended: null, count: 567, uncategorized: true },
  { name: 'outdoors', category: 'general', extended: null, count: 234, uncategorized: true },
];

export default function TagBrowser() {
  const [selectedTag, setSelectedTag] = useState(demoTags[0]);
  const [selectedTags, setSelectedTags] = useState(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState('list'); // list, grid
  const [detailOpen, setDetailOpen] = useState(true);
  
  // Filter state
  const [filters, setFilters] = useState({
    status: 'all', // all, uncategorized, needs_extended
    categories: [],
    extendedCategories: [],
    sort: 'count_desc', // count_desc, count_asc, alpha_asc, alpha_desc
  });
  
  // Expanded sections
  const [expanded, setExpanded] = useState({
    status: true,
    category: true,
    extended: false,
    sort: false,
  });
  
  const toggleSection = (section) => {
    setExpanded(prev => ({ ...prev, [section]: !prev[section] }));
  };
  
  const toggleTagSelection = (tagName) => {
    setSelectedTags(prev => {
      const next = new Set(prev);
      if (next.has(tagName)) {
        next.delete(tagName);
      } else {
        next.add(tagName);
      }
      return next;
    });
  };
  
  const selectAllVisible = () => {
    setSelectedTags(new Set(demoTags.map(t => t.name)));
  };
  
  const clearSelection = () => {
    setSelectedTags(new Set());
  };

  return (
    <div className="h-screen bg-gray-900 flex flex-col overflow-hidden">
      {/* Compact Header */}
      <div className="flex-shrink-0 h-12 bg-gray-800 border-b border-gray-700 flex items-center px-4 gap-4">
        <span className="text-blue-400 font-semibold">ChibiBooru</span>
        <span className="text-gray-500">›</span>
        <span className="text-gray-300 font-medium">Tag Manager</span>
        
        <div className="flex-1" />
        
        {/* Quick stats */}
        <div className="flex items-center gap-4 text-xs">
          <span className="text-gray-500">
            <span className="text-green-400 font-medium">8,432</span> categorized
          </span>
          <span className="text-gray-500">
            <span className="text-orange-400 font-medium">1,203</span> need review
          </span>
        </div>
        
        {/* Actions */}
        <div className="flex items-center gap-2">
          <button className="p-1.5 text-gray-500 hover:text-gray-300 rounded" title="Import">
            <Upload className="w-4 h-4" />
          </button>
          <button className="p-1.5 text-gray-500 hover:text-gray-300 rounded" title="Export">
            <Download className="w-4 h-4" />
          </button>
        </div>
      </div>
      
      {/* Bulk Actions Bar (when tags selected) */}
      {selectedTags.size > 0 && (
        <div className="flex-shrink-0 bg-blue-500/10 border-b border-blue-500/30 px-4 py-2 flex items-center gap-3">
          <span className="text-sm text-blue-400">
            <span className="font-semibold">{selectedTags.size}</span> tags selected
          </span>
          <div className="flex gap-2">
            <button className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded text-gray-300 flex items-center gap-1">
              <Tag className="w-3 h-3" /> Set Category
            </button>
            <button className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded text-gray-300 flex items-center gap-1">
              <GitMerge className="w-3 h-3" /> Merge
            </button>
            <button className="px-2 py-1 text-xs bg-red-500/20 hover:bg-red-500/30 rounded text-red-400 flex items-center gap-1">
              <Trash2 className="w-3 h-3" /> Delete
            </button>
          </div>
          <div className="flex-1" />
          <button onClick={selectAllVisible} className="text-xs text-gray-500 hover:text-gray-300">
            Select all visible
          </button>
          <button onClick={clearSelection} className="text-xs text-gray-500 hover:text-gray-300">
            Clear selection
          </button>
        </div>
      )}
      
      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar: Filters */}
        <div className="w-56 flex-shrink-0 bg-gray-800/50 border-r border-gray-700 overflow-y-auto p-3">
          {/* Search */}
          <div className="relative mb-4">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search tags..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg pl-9 pr-3 py-1.5 text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          
          {/* Status Filter */}
          <div className="mb-3">
            <button 
              onClick={() => toggleSection('status')}
              className="w-full flex items-center justify-between text-xs font-semibold text-gray-500 uppercase tracking-wide py-1"
            >
              <span>Status</span>
              {expanded.status ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            </button>
            {expanded.status && (
              <div className="mt-1 space-y-0.5">
                {[
                  { value: 'all', label: 'All Tags', count: 9635 },
                  { value: 'uncategorized', label: 'Uncategorized', count: 1203, color: 'text-orange-400' },
                  { value: 'needs_extended', label: 'Needs Extended', count: 856, color: 'text-yellow-400' },
                  { value: 'orphaned', label: 'Unused (0 images)', count: 42, color: 'text-red-400' },
                ].map(option => (
                  <button
                    key={option.value}
                    onClick={() => setFilters(f => ({ ...f, status: option.value }))}
                    className={`w-full text-left px-2 py-1 rounded text-sm flex items-center justify-between ${
                      filters.status === option.value 
                        ? 'bg-blue-500/20 text-blue-400' 
                        : 'text-gray-400 hover:bg-gray-700/50'
                    }`}
                  >
                    <span>{option.label}</span>
                    <span className={`text-xs ${option.color || 'text-gray-600'}`}>{option.count}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          
          {/* Base Category Filter */}
          <div className="mb-3">
            <button 
              onClick={() => toggleSection('category')}
              className="w-full flex items-center justify-between text-xs font-semibold text-gray-500 uppercase tracking-wide py-1"
            >
              <span>Category</span>
              {expanded.category ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            </button>
            {expanded.category && (
              <div className="mt-1 space-y-0.5">
                {BASE_CATEGORIES.map(cat => (
                  <button
                    key={cat.key}
                    onClick={() => {
                      setFilters(f => ({
                        ...f,
                        categories: f.categories.includes(cat.key)
                          ? f.categories.filter(c => c !== cat.key)
                          : [...f.categories, cat.key]
                      }));
                    }}
                    className={`w-full text-left px-2 py-1 rounded text-sm flex items-center gap-2 ${
                      filters.categories.includes(cat.key)
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'text-gray-400 hover:bg-gray-700/50'
                    }`}
                  >
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: cat.color }} />
                    <span>{cat.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          
          {/* Extended Category Filter */}
          <div className="mb-3">
            <button 
              onClick={() => toggleSection('extended')}
              className="w-full flex items-center justify-between text-xs font-semibold text-gray-500 uppercase tracking-wide py-1"
            >
              <span>Extended Category</span>
              {expanded.extended ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            </button>
            {expanded.extended && (
              <div className="mt-1 space-y-0.5 max-h-48 overflow-y-auto">
                {EXTENDED_CATEGORIES.map(cat => (
                  <button
                    key={cat.key}
                    onClick={() => {
                      setFilters(f => ({
                        ...f,
                        extendedCategories: f.extendedCategories.includes(cat.key)
                          ? f.extendedCategories.filter(c => c !== cat.key)
                          : [...f.extendedCategories, cat.key]
                      }));
                    }}
                    className={`w-full text-left px-2 py-1 rounded text-xs flex items-center gap-2 ${
                      filters.extendedCategories.includes(cat.key)
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'text-gray-400 hover:bg-gray-700/50'
                    }`}
                  >
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: cat.color }} />
                    <span className="truncate">{cat.name}</span>
                    <span className="ml-auto text-gray-600 text-[10px]">{cat.shortcut}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          
          {/* Sort */}
          <div className="mb-3">
            <button 
              onClick={() => toggleSection('sort')}
              className="w-full flex items-center justify-between text-xs font-semibold text-gray-500 uppercase tracking-wide py-1"
            >
              <span>Sort By</span>
              {expanded.sort ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            </button>
            {expanded.sort && (
              <div className="mt-1 space-y-0.5">
                {[
                  { value: 'count_desc', label: 'Count (High → Low)' },
                  { value: 'count_asc', label: 'Count (Low → High)' },
                  { value: 'alpha_asc', label: 'Name (A → Z)' },
                  { value: 'alpha_desc', label: 'Name (Z → A)' },
                  { value: 'recent', label: 'Recently Added' },
                ].map(option => (
                  <button
                    key={option.value}
                    onClick={() => setFilters(f => ({ ...f, sort: option.value }))}
                    className={`w-full text-left px-2 py-1 rounded text-sm ${
                      filters.sort === option.value
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'text-gray-400 hover:bg-gray-700/50'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          
          {/* Quick Actions */}
          <div className="pt-3 border-t border-gray-700 space-y-1">
            <button className="w-full text-left px-2 py-1.5 rounded text-sm text-gray-400 hover:bg-gray-700/50 flex items-center gap-2">
              <Zap className="w-3.5 h-3.5 text-yellow-500" />
              Auto-Categorize
            </button>
            <button className="w-full text-left px-2 py-1.5 rounded text-sm text-gray-400 hover:bg-gray-700/50 flex items-center gap-2">
              <Link2 className="w-3.5 h-3.5 text-blue-500" />
              Manage Implications
            </button>
          </div>
        </div>
        
        {/* Center: Tag List */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* List Header */}
          <div className="flex-shrink-0 bg-gray-800/30 border-b border-gray-700 px-4 py-2 flex items-center gap-4">
            <span className="text-sm text-gray-500">
              Showing <span className="text-gray-300 font-medium">{demoTags.length}</span> tags
            </span>
            
            <div className="flex-1" />
            
            {/* View Mode Toggle */}
            <div className="flex bg-gray-700 rounded p-0.5">
              <button
                onClick={() => setViewMode('list')}
                className={`p-1 rounded ${viewMode === 'list' ? 'bg-gray-600 text-white' : 'text-gray-400'}`}
              >
                <List className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('grid')}
                className={`p-1 rounded ${viewMode === 'grid' ? 'bg-gray-600 text-white' : 'text-gray-400'}`}
              >
                <Grid className="w-4 h-4" />
              </button>
            </div>
            
            {/* Detail Panel Toggle */}
            <button
              onClick={() => setDetailOpen(!detailOpen)}
              className={`p-1.5 rounded ${detailOpen ? 'bg-blue-500/20 text-blue-400' : 'text-gray-500'}`}
            >
              <Eye className="w-4 h-4" />
            </button>
          </div>
          
          {/* Tag List */}
          <div className="flex-1 overflow-y-auto">
            {viewMode === 'list' ? (
              <table className="w-full">
                <thead className="sticky top-0 bg-gray-800 text-xs text-gray-500 uppercase">
                  <tr>
                    <th className="w-8 p-2">
                      <input type="checkbox" className="rounded" />
                    </th>
                    <th className="text-left p-2">Tag Name</th>
                    <th className="text-left p-2 w-24">Category</th>
                    <th className="text-left p-2 w-32">Extended</th>
                    <th className="text-right p-2 w-20">Count</th>
                    <th className="w-10"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {demoTags.map(tag => (
                    <tr 
                      key={tag.name}
                      onClick={() => setSelectedTag(tag)}
                      className={`cursor-pointer transition-colors ${
                        selectedTag?.name === tag.name 
                          ? 'bg-blue-500/10' 
                          : 'hover:bg-gray-800/50'
                      }`}
                    >
                      <td className="p-2">
                        <input 
                          type="checkbox" 
                          checked={selectedTags.has(tag.name)}
                          onChange={() => toggleTagSelection(tag.name)}
                          onClick={(e) => e.stopPropagation()}
                          className="rounded"
                        />
                      </td>
                      <td className="p-2">
                        <div className="flex items-center gap-2">
                          <span className="text-gray-200 font-medium">{tag.name}</span>
                          {tag.uncategorized && (
                            <span className="px-1.5 py-0.5 text-[10px] bg-orange-500/20 text-orange-400 rounded">
                              needs review
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="p-2">
                        <span 
                          className="px-2 py-0.5 rounded text-xs font-medium"
                          style={{ 
                            backgroundColor: BASE_CATEGORIES.find(c => c.key === tag.category)?.color + '20',
                            color: BASE_CATEGORIES.find(c => c.key === tag.category)?.color
                          }}
                        >
                          {tag.category}
                        </span>
                      </td>
                      <td className="p-2">
                        {tag.extended ? (
                          <span className="text-xs text-gray-400">
                            {EXTENDED_CATEGORIES.find(c => c.key === tag.extended)?.name}
                          </span>
                        ) : (
                          <span className="text-xs text-gray-600">—</span>
                        )}
                      </td>
                      <td className="p-2 text-right">
                        <span className="text-sm text-gray-400">{tag.count.toLocaleString()}</span>
                      </td>
                      <td className="p-2">
                        <button className="p-1 text-gray-600 hover:text-gray-400">
                          <MoreHorizontal className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              /* Grid View */
              <div className="p-4 grid grid-cols-4 gap-2">
                {demoTags.map(tag => (
                  <div
                    key={tag.name}
                    onClick={() => setSelectedTag(tag)}
                    className={`p-3 rounded-lg border cursor-pointer transition-all ${
                      selectedTag?.name === tag.name
                        ? 'bg-blue-500/10 border-blue-500'
                        : 'bg-gray-800/50 border-gray-700 hover:border-gray-600'
                    }`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <span className="font-medium text-gray-200 text-sm truncate">{tag.name}</span>
                      <input 
                        type="checkbox"
                        checked={selectedTags.has(tag.name)}
                        onChange={() => toggleTagSelection(tag.name)}
                        onClick={(e) => e.stopPropagation()}
                        className="rounded"
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span 
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                        style={{ 
                          backgroundColor: BASE_CATEGORIES.find(c => c.key === tag.category)?.color + '20',
                          color: BASE_CATEGORIES.find(c => c.key === tag.category)?.color
                        }}
                      >
                        {tag.category}
                      </span>
                      <span className="text-xs text-gray-500">{tag.count.toLocaleString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        
        {/* Right Sidebar: Tag Detail */}
        {detailOpen && selectedTag && (
          <div className="w-80 flex-shrink-0 bg-gray-800/50 border-l border-gray-700 overflow-y-auto">
            <div className="p-4 space-y-4">
              {/* Tag Header */}
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-gray-200">{selectedTag.name}</h2>
                  <p className="text-sm text-gray-500">{selectedTag.count.toLocaleString()} images</p>
                </div>
                <button onClick={() => setDetailOpen(false)} className="p-1 text-gray-500 hover:text-gray-300">
                  <X className="w-4 h-4" />
                </button>
              </div>
              
              {/* Sample Images */}
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Sample Images</h3>
                <div className="grid grid-cols-3 gap-1">
                  {[1,2,3,4,5,6].map(i => (
                    <div key={i} className="aspect-square bg-gray-700 rounded-lg overflow-hidden">
                      <div className="w-full h-full bg-gradient-to-br from-gray-600 to-gray-700" />
                    </div>
                  ))}
                </div>
                <a href="#" className="text-xs text-blue-400 hover:underline mt-2 inline-block">
                  View all images →
                </a>
              </div>
              
              {/* Category Editor */}
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Base Category</h3>
                <select className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm">
                  {BASE_CATEGORIES.map(cat => (
                    <option key={cat.key} value={cat.key} selected={cat.key === selectedTag.category}>
                      {cat.name}
                    </option>
                  ))}
                </select>
              </div>
              
              {/* Extended Category Editor */}
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Extended Category</h3>
                <select className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm">
                  <option value="">— Not set —</option>
                  {EXTENDED_CATEGORIES.map(cat => (
                    <option key={cat.key} value={cat.key} selected={cat.key === selectedTag.extended}>
                      [{cat.shortcut}] {cat.name}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-600 mt-1">
                  Press <kbd className="px-1 bg-gray-700 rounded">1</kbd>-<kbd className="px-1 bg-gray-700 rounded">9</kbd> or <kbd className="px-1 bg-gray-700 rounded">Q</kbd>-<kbd className="px-1 bg-gray-700 rounded">Z</kbd> for quick assign
                </p>
              </div>
              
              {/* Implications */}
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Implications</h3>
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-sm text-gray-400">
                    <span className="text-blue-400">hatsune_miku</span>
                    <ArrowRight className="w-3 h-3" />
                    <span>vocaloid</span>
                  </div>
                  <button className="text-xs text-blue-400 hover:underline">
                    + Add implication
                  </button>
                </div>
              </div>
              
              {/* Aliases */}
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Aliases</h3>
                <div className="text-sm text-gray-500 italic">No aliases</div>
                <button className="text-xs text-blue-400 hover:underline mt-1">
                  + Add alias
                </button>
              </div>
              
              {/* Actions */}
              <div className="pt-4 border-t border-gray-700 space-y-2">
                <button className="w-full px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-gray-300 flex items-center justify-center gap-2">
                  <Edit3 className="w-4 h-4" /> Rename Tag
                </button>
                <button className="w-full px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-gray-300 flex items-center justify-center gap-2">
                  <GitMerge className="w-4 h-4" /> Merge Into...
                </button>
                <button className="w-full px-3 py-2 bg-red-500/20 hover:bg-red-500/30 rounded-lg text-sm text-red-400 flex items-center justify-center gap-2">
                  <Trash2 className="w-4 h-4" /> Delete Tag
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
      
      {/* Keyboard Shortcuts Hint */}
      <div className="flex-shrink-0 bg-gray-800 border-t border-gray-700 px-4 py-1.5 flex items-center gap-4 text-xs text-gray-600">
        <span><kbd className="px-1 bg-gray-700 rounded">↑↓</kbd> navigate</span>
        <span><kbd className="px-1 bg-gray-700 rounded">Space</kbd> select</span>
        <span><kbd className="px-1 bg-gray-700 rounded">1-9</kbd> set extended category</span>
        <span><kbd className="px-1 bg-gray-700 rounded">E</kbd> edit</span>
        <span><kbd className="px-1 bg-gray-700 rounded">D</kbd> delete</span>
        <span><kbd className="px-1 bg-gray-700 rounded">?</kbd> all shortcuts</span>
      </div>
    </div>
  );
}
