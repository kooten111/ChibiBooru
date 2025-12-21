import React, { useState } from 'react';
import { Search, Filter, Grid, LayoutGrid, ChevronDown, ChevronRight, X, Star, Clock, Shuffle, Tag, User, Palette, BookOpen, SlidersHorizontal, PanelLeftClose } from 'lucide-react';

/*
  GALLERY IMPROVEMENTS
  
  Current issues:
  1. No quick filter sidebar - have to type everything in search
  2. Header is always full size even when you know what you want
  3. No saved searches / recent searches
  4. No keyboard navigation between images
  5. Grid size not adjustable
  
  Proposed changes:
  1. Collapsible left sidebar with quick filters (ratings, sources, recent searches)
  2. Compact header option
  3. Grid density toggle (small/medium/large thumbnails)
  4. Keyboard shortcuts (J/K to navigate, Enter to open)
  5. Sticky filter bar showing active filters
*/

const QuickFilters = {
  rating: [
    { label: 'General', query: 'rating:general', color: '#22c55e' },
    { label: 'Sensitive', query: 'rating:sensitive', color: '#eab308' },
    { label: 'Questionable', query: 'rating:questionable', color: '#f97316' },
    { label: 'Explicit', query: 'rating:explicit', color: '#ef4444' },
  ],
  source: [
    { label: 'Danbooru', query: 'source:danbooru' },
    { label: 'Gelbooru', query: 'source:gelbooru' },
    { label: 'e621', query: 'source:e621' },
    { label: 'Pixiv', query: 'source:pixiv' },
    { label: 'Local Tagger', query: 'source:local_tagger' },
  ],
  special: [
    { label: 'Has Parent', query: 'has:parent', icon: '↑' },
    { label: 'Has Children', query: 'has:child', icon: '↓' },
    { label: 'In Pool', query: 'has:pool', icon: '📚' },
    { label: 'Favourites', query: 'is:favourite', icon: '⭐' },
  ]
};

export default function GalleryPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeFilters, setActiveFilters] = useState(['rating:general']);
  const [gridSize, setGridSize] = useState('medium'); // small, medium, large
  const [expandedSections, setExpandedSections] = useState(['rating', 'recent']);
  const [searchQuery, setSearchQuery] = useState('');
  
  const recentSearches = [
    '1girl blue_hair',
    'artist:sakimichan',
    'hatsune_miku rating:general',
    'landscape -character',
  ];
  
  const topTags = [
    { name: '1girl', count: 4521 },
    { name: 'solo', count: 3892 },
    { name: 'blue_hair', count: 1243 },
    { name: 'long_hair', count: 2891 },
  ];
  
  const toggleSection = (section) => {
    setExpandedSections(prev => 
      prev.includes(section) ? prev.filter(s => s !== section) : [...prev, section]
    );
  };
  
  const addFilter = (query) => {
    if (!activeFilters.includes(query)) {
      setActiveFilters([...activeFilters, query]);
    }
  };
  
  const removeFilter = (query) => {
    setActiveFilters(activeFilters.filter(f => f !== query));
  };
  
  const gridCols = {
    small: 'grid-cols-4 md:grid-cols-6 lg:grid-cols-8',
    medium: 'grid-cols-3 md:grid-cols-4 lg:grid-cols-5',
    large: 'grid-cols-2 md:grid-cols-3 lg:grid-cols-4',
  };

  return (
    <div className="h-screen bg-gray-900 flex flex-col overflow-hidden">
      {/* Compact Header */}
      <div className="flex-shrink-0 h-12 bg-gray-800 border-b border-gray-700 flex items-center px-4 gap-4">
        {/* Logo */}
        <span className="text-blue-400 font-semibold text-lg">ChibiBooru</span>
        
        {/* Search */}
        <div className="flex-1 max-w-2xl">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search tags..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg pl-10 pr-4 py-1.5 text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>
        
        {/* Right side controls */}
        <div className="flex items-center gap-2">
          {/* Grid size toggle */}
          <div className="flex bg-gray-700 rounded-lg p-0.5">
            {['small', 'medium', 'large'].map(size => (
              <button
                key={size}
                onClick={() => setGridSize(size)}
                className={`px-2 py-1 rounded text-xs ${gridSize === size ? 'bg-blue-500 text-white' : 'text-gray-400 hover:text-white'}`}
              >
                {size === 'small' ? 'S' : size === 'medium' ? 'M' : 'L'}
              </button>
            ))}
          </div>
          
          {/* Sidebar toggle */}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className={`p-1.5 rounded ${sidebarOpen ? 'bg-blue-500/20 text-blue-400' : 'text-gray-500 hover:text-gray-300'}`}
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
          
          {/* Random */}
          <button className="p-1.5 rounded text-gray-500 hover:text-gray-300" title="Random image">
            <Shuffle className="w-4 h-4" />
          </button>
        </div>
      </div>
      
      {/* Active Filters Bar (only shows when filters active) */}
      {activeFilters.length > 0 && (
        <div className="flex-shrink-0 bg-gray-800/50 border-b border-gray-700 px-4 py-2 flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500 uppercase">Filters:</span>
          {activeFilters.map(filter => (
            <span
              key={filter}
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs"
            >
              {filter}
              <button onClick={() => removeFilter(filter)} className="hover:text-white">
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
          <button 
            onClick={() => setActiveFilters([])}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            Clear all
          </button>
          <span className="ml-auto text-xs text-gray-500">2,847 results</span>
        </div>
      )}
      
      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <div className={`flex-shrink-0 border-r border-gray-700 bg-gray-800/30 overflow-hidden transition-all duration-200 ${sidebarOpen ? 'w-56' : 'w-0'}`}>
          <div className="w-56 h-full overflow-y-auto p-3 space-y-3">
            
            {/* Rating Filters */}
            <div>
              <button 
                onClick={() => toggleSection('rating')}
                className="w-full flex items-center justify-between text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2"
              >
                <span className="flex items-center gap-1.5">
                  <Star className="w-3.5 h-3.5" /> Rating
                </span>
                {expandedSections.includes('rating') ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
              {expandedSections.includes('rating') && (
                <div className="space-y-1">
                  {QuickFilters.rating.map(f => (
                    <button
                      key={f.query}
                      onClick={() => addFilter(f.query)}
                      className={`w-full text-left px-2 py-1 rounded text-sm flex items-center gap-2 ${
                        activeFilters.includes(f.query) 
                          ? 'bg-blue-500/20 text-blue-400' 
                          : 'text-gray-400 hover:bg-gray-700/50 hover:text-white'
                      }`}
                    >
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: f.color }} />
                      {f.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            
            {/* Source Filters */}
            <div>
              <button 
                onClick={() => toggleSection('source')}
                className="w-full flex items-center justify-between text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2"
              >
                <span className="flex items-center gap-1.5">
                  <BookOpen className="w-3.5 h-3.5" /> Source
                </span>
                {expandedSections.includes('source') ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
              {expandedSections.includes('source') && (
                <div className="space-y-1">
                  {QuickFilters.source.map(f => (
                    <button
                      key={f.query}
                      onClick={() => addFilter(f.query)}
                      className={`w-full text-left px-2 py-1 rounded text-sm ${
                        activeFilters.includes(f.query) 
                          ? 'bg-blue-500/20 text-blue-400' 
                          : 'text-gray-400 hover:bg-gray-700/50 hover:text-white'
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            
            {/* Special Filters */}
            <div>
              <button 
                onClick={() => toggleSection('special')}
                className="w-full flex items-center justify-between text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2"
              >
                <span className="flex items-center gap-1.5">
                  <Filter className="w-3.5 h-3.5" /> Special
                </span>
                {expandedSections.includes('special') ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
              {expandedSections.includes('special') && (
                <div className="space-y-1">
                  {QuickFilters.special.map(f => (
                    <button
                      key={f.query}
                      onClick={() => addFilter(f.query)}
                      className={`w-full text-left px-2 py-1 rounded text-sm flex items-center gap-2 ${
                        activeFilters.includes(f.query) 
                          ? 'bg-blue-500/20 text-blue-400' 
                          : 'text-gray-400 hover:bg-gray-700/50 hover:text-white'
                      }`}
                    >
                      <span>{f.icon}</span>
                      {f.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            
            {/* Recent Searches */}
            <div>
              <button 
                onClick={() => toggleSection('recent')}
                className="w-full flex items-center justify-between text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2"
              >
                <span className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5" /> Recent
                </span>
                {expandedSections.includes('recent') ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
              {expandedSections.includes('recent') && (
                <div className="space-y-1">
                  {recentSearches.map((search, i) => (
                    <button
                      key={i}
                      onClick={() => setSearchQuery(search)}
                      className="w-full text-left px-2 py-1 rounded text-sm text-gray-400 hover:bg-gray-700/50 hover:text-white truncate"
                    >
                      {search}
                    </button>
                  ))}
                </div>
              )}
            </div>
            
            {/* Top Tags */}
            <div>
              <button 
                onClick={() => toggleSection('tags')}
                className="w-full flex items-center justify-between text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2"
              >
                <span className="flex items-center gap-1.5">
                  <Tag className="w-3.5 h-3.5" /> Top Tags
                </span>
                {expandedSections.includes('tags') ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
              {expandedSections.includes('tags') && (
                <div className="space-y-1">
                  {topTags.map(tag => (
                    <button
                      key={tag.name}
                      onClick={() => addFilter(tag.name)}
                      className="w-full text-left px-2 py-1 rounded text-sm text-gray-400 hover:bg-gray-700/50 hover:text-white flex justify-between"
                    >
                      <span>{tag.name}</span>
                      <span className="text-xs text-gray-600">{tag.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            
          </div>
        </div>
        
        {/* Gallery Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className={`grid gap-2 ${gridCols[gridSize]}`}>
            {Array.from({ length: 30 }, (_, i) => (
              <div
                key={i}
                className="aspect-square bg-gray-800 rounded-lg border border-gray-700 hover:border-blue-500 cursor-pointer transition-all hover:scale-[1.02] hover:shadow-lg hover:shadow-blue-500/10 overflow-hidden group relative"
              >
                {/* Placeholder */}
                <div className="w-full h-full bg-gradient-to-br from-gray-700 to-gray-800 flex items-center justify-center">
                  <span className="text-gray-600 text-xs">#{i + 1}</span>
                </div>
                
                {/* Hover overlay with quick info */}
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-2">
                  <div className="flex gap-1 flex-wrap">
                    <span className="text-[10px] px-1 py-0.5 bg-pink-500/30 text-pink-300 rounded">character</span>
                    <span className="text-[10px] px-1 py-0.5 bg-purple-500/30 text-purple-300 rounded">vocaloid</span>
                  </div>
                </div>
                
                {/* Video badge example */}
                {i === 5 && (
                  <div className="absolute top-1 right-1 bg-black/70 text-white text-[10px] px-1 rounded">▶</div>
                )}
                
                {/* Rating badge */}
                {i % 4 === 0 && (
                  <div className="absolute top-1 left-1 w-2 h-2 rounded-full bg-green-500" title="General" />
                )}
              </div>
            ))}
          </div>
          
          {/* Load more / Infinite scroll indicator */}
          <div className="text-center py-8 text-gray-500 text-sm">
            Loading more...
          </div>
        </div>
      </div>
      
      {/* Keyboard shortcuts hint (bottom right) */}
      <div className="fixed bottom-4 right-4 text-xs text-gray-600 bg-gray-800/80 px-2 py-1 rounded">
        <kbd className="px-1 bg-gray-700 rounded">J</kbd>/<kbd className="px-1 bg-gray-700 rounded">K</kbd> navigate • <kbd className="px-1 bg-gray-700 rounded">Enter</kbd> open • <kbd className="px-1 bg-gray-700 rounded">?</kbd> help
      </div>
    </div>
  );
}
