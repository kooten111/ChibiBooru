# TODO: Fix Recent Problematic Commits

## Overview
Three commits have been identified as not working as intended. Investigation complete.

---

## 1. Similarity Cache System - Manual Action Required
**Commit:** `e6c8a4f` (PR #29) - "Implement pre-computed similarity cache to reduce FAISS memory footprint by ~400MB"

### Status: 🟡 Requires Manual Action

### Root Cause
The cache table exists but has **0 entries**. The cache only gets populated:
1. During new image ingestion (after feature was added)
2. Via manual API rebuild call

Existing 14,117 images were never cached because they predate the feature.

### Solution
Run a one-time cache rebuild via API:
```bash
curl -X POST "http://localhost:5000/api/similarity/rebuild-cache" \
     -H "X-API-Secret: YOUR_SECRET"
```

---

## 2. Character Management Page Layout - Fixed ✅
**Commit:** `ce7ce5d` / `56c2536` (PR #30) - "Transform character management page to three-panel dashboard layout"

### Issue
The "Prediction Preview" tab (primary use case) was secondary.

### Fix Applied
- Changed default active tab from "Character Images" to "Prediction Preview"
- Modified: `templates/character_manage.html`

---

## 3. Rate Manage/Review Modern UI - Fixed ✅
**Commit:** `c9fd726` (PR #31) - "Rework rate_manage and rate_review pages for modern UI"

### Issue
V2 templates existed but routes served legacy templates.

### Fix Applied
- Main routes now serve v2 modern UI templates
- Legacy templates available at `/rate/manage/legacy` and `/rate/review/legacy`
- Modified: `routers/web.py`

---

## Summary

| Issue | Status | Fix |
|-------|--------|-----|
| Similarity Cache | 🟡 Manual Action | Run `/api/similarity/rebuild-cache` |
| Character Page Tab | ✅ Fixed | Default tab changed |
| Rate Pages V2 | ✅ Fixed | Routes serve v2 templates |

---

## Remaining Action Items

- [ ] Trigger similarity cache rebuild via API (one-time operation)
- [ ] Consider adding a "Rebuild Cache" button to the admin UI
- [ ] Remove legacy rate templates after confirming v2 works well
