import React, { useState } from 'react';
import { X, ChevronLeft, ChevronRight, Tag, Info, Image, Download, Trash2, Search, Eye, ZoomIn, Maximize2, PanelLeftClose, PanelRightClose } from 'lucide-react';

/*
  LAYOUT CONCEPT FOR PORTRAIT-HEAVY GALLERY
  
  Key changes from current:
  1. Sidebars are collapsible - can hide to give image full width
  2. Action buttons moved to floating bar over image (bottom)
  3. Narrower sidebars when open (260px vs 300px)
  4. Option for single-sidebar mode (tags + metadata stacked on one side)
  
  Three layout modes:
  - Full: Both sidebars visible (for browsing/editing)
  - Focus: No sidebars, just image + floating actions
  - Hybrid: One sidebar with both tags and metadata stacked
*/

export default function ImageViewer() {
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [focusMode, setFocusMode] = useState(false);
  
  // Demo data
  const tags = {
    character: ['hatsune_miku', 'kagamine_rin'],
    copyright: ['vocaloid'],
    artist: ['artist_name'],
    general: ['1girl', 'blue_hair', 'twintails', 'detached_sleeves', 'thighhighs', 'skirt', 'necktie', 'headphones', 'smile', 'looking_at_viewer']
  };
  
  const metadata = {
    source: 'danbooru',
    dimensions: '1200 × 1800',
    filesize: '2.4 MB',
    rating: 'general'
  };
  
  const related = Array(6).fill(null);
  
  if (focusMode) {
    return (
      <div className="h-screen bg-black flex items-center justify-center relative">
        {/* Exit focus mode */}
        <button 
          onClick={() => setFocusMode(false)}
          className="absolute top-4 right-4 z-50 p-2 bg-black/50 hover:bg-black/80 rounded-lg text-white"
        >
          <X className="w-5 h-5" />
        </button>
        
        {/* Image */}
        <div className="max-w-full max-h-full p-4">
          <div className="bg-gradient-to-b from-blue-900/30 to-purple-900/30 rounded-lg flex items-center justify-center"
               style={{ width: '600px', height: '900px' }}>
            <span className="text-gray-500">Portrait Image</span>
          </div>
        </div>
        
        {/* Floating action bar */}
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex gap-2 bg-black/70 backdrop-blur-sm px-4 py-2 rounded-full">
          <button className="p-2 hover:bg-white/10 rounded-full text-white"><ChevronLeft className="w-5 h-5" /></button>
          <button className="p-2 hover:bg-white/10 rounded-full text-white"><ZoomIn className="w-5 h-5" /></button>
          <button className="p-2 hover:bg-white/10 rounded-full text-white"><Download className="w-5 h-5" /></button>
          <button className="p-2 hover:bg-white/10 rounded-full text-white"><Search className="w-5 h-5" /></button>
          <button className="p-2 hover:bg-white/10 rounded-full text-red-400"><Trash2 className="w-5 h-5" /></button>
          <button className="p-2 hover:bg-white/10 rounded-full text-white"><ChevronRight className="w-5 h-5" /></button>
        </div>
        
        {/* Keyboard hint */}
        <div className="absolute bottom-20 left-1/2 -translate-x-1/2 text-xs text-gray-500">
          ESC to exit • ←→ navigate • scroll to zoom
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-gray-900 flex flex-col overflow-hidden">
      {/* Header - compact */}
      <div className="flex-shrink-0 h-12 bg-gray-800 border-b border-gray-700 flex items-center px-4 justify-between">
        <div className="flex items-center gap-4">
          <span className="text-blue-400 font-semibold">ChibiBooru</span>
          <input 
            type="text" 
            placeholder="Search..." 
            className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-1 text-sm w-64 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <button 
            onClick={() => setLeftOpen(!leftOpen)}
            className={`p-1.5 rounded ${leftOpen ? 'bg-blue-500/20 text-blue-400' : 'text-gray-500 hover:text-gray-300'}`}
            title="Toggle tags panel"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
          <button 
            onClick={() => setRightOpen(!rightOpen)}
            className={`p-1.5 rounded ${rightOpen ? 'bg-blue-500/20 text-blue-400' : 'text-gray-500 hover:text-gray-300'}`}
            title="Toggle info panel"
          >
            <PanelRightClose className="w-4 h-4" />
          </button>
          <button 
            onClick={() => setFocusMode(true)}
            className="p-1.5 rounded text-gray-500 hover:text-gray-300"
            title="Focus mode (F)"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>
      </div>
      
      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar - Tags */}
        <div 
          className={`flex-shrink-0 border-r border-gray-700 bg-gray-800/50 overflow-hidden transition-all duration-200 ${
            leftOpen ? 'w-64' : 'w-0'
          }`}
        >
          <div className="w-64 h-full overflow-y-auto p-3 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-2">
                <Tag className="w-3.5 h-3.5" /> Tags
              </h2>
              <span className="text-xs text-gray-600">Edit</span>
            </div>
            
            {Object.entries(tags).map(([category, tagList]) => (
              <div key={category} className="space-y-1">
                <h3 className={`text-xs font-medium uppercase tracking-wide ${
                  category === 'character' ? 'text-pink-400' :
                  category === 'copyright' ? 'text-purple-400' :
                  category === 'artist' ? 'text-orange-400' :
                  'text-blue-400'
                }`}>
                  {category}
                </h3>
                <div className="space-y-0.5">
                  {tagList.map(tag => (
                    <div key={tag} className="flex justify-between items-center py-0.5 px-1 rounded hover:bg-gray-700/50 group cursor-pointer">
                      <span className="text-sm text-gray-300 group-hover:text-white">{tag.replace(/_/g, ' ')}</span>
                      <span className="text-xs text-gray-600">42</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
        
        {/* Center - Image */}
        <div className="flex-1 flex flex-col min-w-0 relative">
          {/* Image container - takes all available space */}
          <div className="flex-1 flex items-center justify-center p-4 min-h-0">
            <div 
              className="max-w-full max-h-full bg-gradient-to-b from-blue-900/20 to-purple-900/20 rounded-lg border border-gray-700 flex items-center justify-center shadow-2xl"
              style={{ 
                width: 'min(100%, 600px)', 
                aspectRatio: '2/3'  /* Portrait aspect ratio */
              }}
            >
              <div className="text-center text-gray-500">
                <Image className="w-16 h-16 mx-auto mb-2 opacity-50" />
                <div className="text-sm">Portrait Image</div>
                <div className="text-xs mt-1">1200 × 1800</div>
              </div>
            </div>
          </div>
          
          {/* Floating action bar - positioned at bottom of image area */}
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-1 bg-gray-800/90 backdrop-blur-sm px-3 py-1.5 rounded-full border border-gray-700 shadow-xl">
            <button className="p-1.5 hover:bg-gray-700 rounded-full text-gray-400 hover:text-white" title="Previous">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <div className="w-px h-4 bg-gray-700 mx-1" />
            <button className="p-1.5 hover:bg-gray-700 rounded-full text-gray-400 hover:text-white" title="Focus mode">
              <Maximize2 className="w-4 h-4" />
            </button>
            <button className="p-1.5 hover:bg-gray-700 rounded-full text-gray-400 hover:text-white" title="Find similar">
              <Search className="w-4 h-4" />
            </button>
            <button className="p-1.5 hover:bg-gray-700 rounded-full text-gray-400 hover:text-white" title="Visual similar">
              <Eye className="w-4 h-4" />
            </button>
            <button className="p-1.5 hover:bg-gray-700 rounded-full text-green-400 hover:text-green-300" title="Download">
              <Download className="w-4 h-4" />
            </button>
            <button className="p-1.5 hover:bg-gray-700 rounded-full text-red-400 hover:text-red-300" title="Delete">
              <Trash2 className="w-4 h-4" />
            </button>
            <div className="w-px h-4 bg-gray-700 mx-1" />
            <button className="p-1.5 hover:bg-gray-700 rounded-full text-gray-400 hover:text-white" title="Next">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
        
        {/* Right sidebar - Info + Related */}
        <div 
          className={`flex-shrink-0 border-l border-gray-700 bg-gray-800/50 overflow-hidden transition-all duration-200 ${
            rightOpen ? 'w-64' : 'w-0'
          }`}
        >
          <div className="w-64 h-full overflow-y-auto p-3 space-y-4">
            {/* Metadata */}
            <div>
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-2 mb-2">
                <Info className="w-3.5 h-3.5" /> Info
              </h2>
              <div className="space-y-2 text-sm">
                {Object.entries(metadata).map(([key, value]) => (
                  <div key={key} className="flex justify-between">
                    <span className="text-gray-500 capitalize">{key}</span>
                    <span className="text-gray-300">{value}</span>
                  </div>
                ))}
              </div>
            </div>
            
            {/* Related */}
            <div>
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-2 mb-2">
                <Image className="w-3.5 h-3.5" /> Similar
              </h2>
              <div className="grid grid-cols-2 gap-2">
                {related.map((_, i) => (
                  <div key={i} className="aspect-square bg-gray-700/50 rounded-lg border border-gray-600 hover:border-blue-500 cursor-pointer transition-colors flex items-center justify-center">
                    <span className="text-xs text-gray-600">#{i + 1}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
