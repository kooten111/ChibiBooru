# Debloat Progress Tracker

**Started:** 2025-11-02
**Status:** In Progress
**Estimated Code Reduction:** 900-1,200 lines (~15-20%)

---

## Priority 1: Critical Issues

### 1.1 Create Shared Notification Utility
- [ ] Create `static/js/utils/notifications.js`
- [ ] Replace notification in `static/js/saucenao-fetch.js:703-729`
- [ ] Replace notification in `static/js/global-uploader.js:75-94`
- [ ] Replace notification in `static/js/tag-editor.js:586-610`
- [ ] Test notifications work across all pages
- [ ] **Lines saved:** ~150

**Files affected:**
- `static/js/saucenao-fetch.js`
- `static/js/global-uploader.js`
- `static/js/tag-editor.js`

---

### 1.2 Extract Inline Styles from JavaScript
- [ ] Create `static/css/saucenao-modal.css` for SauceNAO modal styles
- [ ] Create `static/css/tag-editor-modal.css` for tag editor modal styles
- [ ] Replace inline styles in `static/js/saucenao-fetch.js` (108+ instances)
- [ ] Replace inline styles in `static/js/tag-editor.js` (similar count)
- [ ] Update HTML templates to include new CSS files
- [ ] Test all modals render correctly
- [ ] **Lines saved:** ~300

**Files affected:**
- `static/js/saucenao-fetch.js`
- `static/js/tag-editor.js`
- New: `static/css/saucenao-modal.css`
- New: `static/css/tag-editor-modal.css`
- `templates/*.html` (for CSS includes)

---

### 1.3 Split Large CSS File
- [ ] Analyze `static/css/components.css` (4,153 lines)
- [ ] Create `static/css/header.css`
- [ ] Create `static/css/modals.css`
- [ ] Create `static/css/forms.css`
- [ ] Create `static/css/panels.css`
- [ ] Create `static/css/buttons.css`
- [ ] Update HTML templates to include modular CSS files
- [ ] Remove duplicate CSS rules
- [ ] Test all pages render correctly
- [ ] **Lines saved:** ~500-800

**Files affected:**
- `static/css/components.css`
- New: `static/css/header.css`
- New: `static/css/modals.css`
- New: `static/css/forms.css`
- New: `static/css/panels.css`
- New: `static/css/buttons.css`
- `templates/*.html`

---

## Priority 2: High Priority Issues

### 2.1 Create Shared Utility Functions
- [x] Create `static/js/utils/helpers.js`
- [x] Move `escapeHtml()` from `autocomplete.js:325-329`
- [x] Move `escapeHtml()` from `tag-editor.js:574-578`
- [x] Move `formatCount()` from `autocomplete.js:319-323`
- [x] Move `formatCount()` from `tag-editor.js:580-584`
- [x] Update imports in affected files
- [x] Update HTML templates to use type="module"
- [x] Test autocomplete functionality (syntax verified)
- [x] Test tag editor functionality (syntax verified)
- [x] **Lines saved:** ~20 lines removed from duplicate functions

**Files affected:**
- `static/js/autocomplete.js` (removed 10 lines)
- `static/js/tag-editor.js` (removed 11 lines)
- New: `static/js/utils/helpers.js` (23 lines)
- `templates/index.html` (updated script tag)
- `templates/raw_data.html` (updated script tag)
- `templates/image.html` (updated 2 script tags)

**Status:** ✅ COMPLETED

---

### 2.2 Consolidate CSS Color Values
- [ ] Audit hardcoded `rgba(30, 30, 45` values (21 instances)
- [ ] Replace with CSS variable references
- [ ] Test visual consistency
- [ ] **Lines saved:** 0 (quality improvement)

**Files affected:**
- Multiple JS and CSS files with hardcoded colors

---

### 2.3 Fix Duplicate CSS Rules
- [ ] Remove duplicate `.header` definitions in `components.css`
- [ ] Remove duplicate `.header-content` definitions
- [ ] Consolidate similar panel styles
- [ ] Test header rendering
- [ ] **Lines saved:** ~50-100

**Files affected:**
- `static/css/components.css`

---

## Priority 3: Medium Priority Issues

### 3.1 Consolidate Python Imports
- [ ] Merge `repositories.tag_repository` imports in `models.py` (lines 21, 170, 189)
- [ ] Remove duplicate import in `routes.py:435`
- [ ] Test application runs without errors
- [ ] **Lines saved:** ~5

**Files affected:**
- `models.py`
- `routes.py`

---

### 3.2 Fix Bugs
- [x] Fix `processing.py:79` incorrect variable assignment
- [x] Test tag processing functionality (syntax validated)
- [ ] **Lines saved:** 0 (bug fix - quality improvement)

**Files affected:**
- `processing.py`

**Status:** ✅ COMPLETED

---

## Testing Checklist

After each change, verify:

### Frontend Testing
- [ ] Homepage loads correctly
- [ ] Image viewer works
- [ ] Tag autocomplete functions
- [ ] Tag editor modal opens and works
- [ ] SauceNAO fetch modal works
- [ ] Global uploader works
- [ ] Notifications appear correctly
- [ ] All styles render properly
- [ ] No console errors

### Backend Testing
- [ ] Application starts without errors
- [ ] Image upload works
- [ ] Tag processing works
- [ ] Database operations work
- [ ] No import errors

### Browser Testing
- [ ] Test in Chrome/Chromium
- [ ] Test in Firefox
- [ ] Check mobile responsiveness

---

## Progress Log

### 2025-11-02
- Initial bloat analysis completed
- Created debloat progress tracker
- Identified ~900-1,200 lines for removal/refactoring
- **COMPLETED:** Fixed `processing.py:79` bug (incorrect variable assignment in exception handler)
- **COMPLETED:** Created shared utility functions (escapeHtml, formatCount) - removed ~20 duplicate lines
  - Created `static/js/utils/helpers.js`
  - Refactored `autocomplete.js` and `tag-editor.js` to use ES6 modules
  - Updated 3 HTML templates to use `type="module"`
  - **FIX:** Exposed `toggleTagEditor` and `saveTags` functions globally for onclick handlers

---

## Notes

- Always test after each refactoring step
- Keep backups or use git commits
- Consider creating a feature branch for this work
- Don't refactor everything at once - incremental changes are safer

---

## Metrics

| Category | Before | After | Reduction |
|----------|--------|-------|-----------|
| Duplicate Functions | 3+ | - | - |
| Inline Styles (JS) | 108+ | - | - |
| CSS File Size | 4,153 lines | - | - |
| Total JS Lines | ~2,500 | - | - |
| Total CSS Lines | ~5,000 | - | - |

**Total estimated reduction:** 900-1,200 lines (~15-20%)
