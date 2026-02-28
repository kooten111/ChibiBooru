/**
 * Duplicate Finder — review workflow for pHash duplicate pairs.
 *
 * Phase 2: background scan + paginated cache reads.
 *
 * Flow:
 *   1. Check cache stats  → if empty, show "Scan" button
 *   2. User clicks Scan   → POST /api/duplicate-review/scan → poll progress
 *   3. Cache ready         → load first page (PAGE_SIZE pairs)
 *   4. Navigate            → lazy-load forward/backward pages
 */

import { showNotification } from '../utils/notifications.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const PAGE_SIZE = 50;
const POLL_MS  = 1000;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let pairs       = [];           // currently loaded page
let totalPairs  = 0;            // total unreviewed at this threshold
let pageOffset  = 0;            // current offset in the cache
let currentIndex = 0;           // cursor within `pairs`
let stagedActions = new Map();  // key = "idA-idB"
let compareMode  = 'side';
let sliderPos    = 50;
let isLoading    = false;
let isDraggingSlider = false;
let isComparing  = false;
let scanTaskId   = null;
let commitTaskId = null;
let pollTimer    = null;
let commitPollTimer = null;
let phashBits    = 256;         // default for hash_size=16; updated from server
let scanThreshold = 64;         // scan-time max distance; updated from server

// DOM refs
let $content, $actionBar, $keyboardHints;
let $progressText, $progressFill, $pendingBadge;
let $thresholdSlider, $thresholdValue;
let $reviewOverlay, $reviewList;
let $rescanBtn;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function pairKey(a, b) { return `${Math.min(a, b)}-${Math.max(a, b)}`; }

function formatBytes(bytes) {
    if (!bytes) return '—';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function cmpClass(valA, valB, side) {
    const a = Number(valA) || 0, b = Number(valB) || 0;
    if (a === b) return 'dup-tie';
    return (side === 'a') === (a > b) ? 'dup-win' : 'dup-lose';
}

function confidenceClass(c) {
    if (c >= 85) return 'high';
    if (c >= 60) return 'medium';
    return 'low';
}

function actionLabel(action, detail) {
    switch (action) {
        case 'delete_a': return 'Delete A';
        case 'delete_b': return 'Delete B';
        case 'non_duplicate': return 'Not Dup';
        case 'related':
            if (detail === 'parent_child_ab') return 'A→B Parent';
            if (detail === 'parent_child_ba') return 'B→A Parent';
            return 'Siblings';
        default: return action;
    }
}

function actionBadgeClass(action) {
    if (action.startsWith('delete')) return 'delete';
    if (action === 'non_duplicate') return 'non-dup';
    return 'related';
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
async function api(url, opts) {
    const res = await fetch(url, opts);
    const json = await res.json();
    if (!res.ok && json.error) throw new Error(json.error);
    return json;
}

async function fetchCacheStats() {
    return api('/api/duplicate-review/cache-stats');
}

async function triggerScan(threshold = 15) {
    return api(`/api/duplicate-review/scan?threshold=${threshold}`, { method: 'POST' });
}

async function fetchQueue(threshold, offset = 0, limit = PAGE_SIZE) {
    return api(`/api/duplicate-review/queue?threshold=${threshold}&offset=${offset}&limit=${limit}`);
}

async function pollTaskStatus(taskId) {
    return api(`/api/task_status?task_id=${taskId}`);
}

async function commitToServer(actions) {
    return api('/api/duplicate-review/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actions })
    });
}

// ---------------------------------------------------------------------------
// Re-scan helpers
// ---------------------------------------------------------------------------
function setRescanEnabled(enabled) {
    if ($rescanBtn) {
        $rescanBtn.disabled = !enabled;
        $rescanBtn.title = enabled ? 'Re-scan all images for duplicates' : 'Scan in progress…';
    }
}

// ---------------------------------------------------------------------------
// Boot: check cache → scan or load
// ---------------------------------------------------------------------------
async function boot() {
    showLoadingSpinner('Checking duplicate cache…');

    try {
        const stats = await fetchCacheStats();
        // Adapt slider to server's hash size / scan threshold
        if (stats.phash_bits) phashBits = stats.phash_bits;
        if (stats.scan_threshold) scanThreshold = stats.scan_threshold;
        {
            const maxThreshold = scanThreshold || Math.min(Math.round(phashBits / 4), 64);
            $thresholdSlider.max = maxThreshold;
            if (parseInt($thresholdSlider.value) > maxThreshold) {
                $thresholdSlider.value = Math.min(20, maxThreshold);
                $thresholdValue.textContent = $thresholdSlider.value;
            }
        }
        if (stats.cached_pairs > 0) {
            // Cache exists — show re-scan button and load pairs
            if ($rescanBtn) $rescanBtn.style.display = '';
            await loadPage(0);
        } else {
            // Empty cache — show scan prompt
            renderScanPrompt(stats);
        }
    } catch (err) {
        renderError(err.message);
    }
}

function renderScanPrompt(stats) {
    $actionBar.style.display = 'none';
    $keyboardHints.style.display = 'none';
    $content.innerHTML = `
        <div class="dup-state-message">
            <div class="icon">🔍</div>
            <h2>No cached duplicate data</h2>
            <p>${stats.hashed_images} images have pHash values.
               Click <strong>Scan</strong> to find duplicate pairs (this runs in the background).</p>
            <button class="dup-scan-btn" id="btnStartScan">Scan for Duplicates</button>
        </div>`;
    document.getElementById('btnStartScan').addEventListener('click', startScan);
}

// ---------------------------------------------------------------------------
// Scan flow
// ---------------------------------------------------------------------------
async function startScan() {
    try {
        showLoadingSpinner('Starting scan…');
        setRescanEnabled(false);
        const computedThreshold = Math.min(Math.round(phashBits / 4), 64);
        const resp = await triggerScan(computedThreshold);
        scanTaskId = resp.task_id;
        showNotification('Duplicate scan started — this may take a while.', 'info');
        startPolling();
    } catch (err) {
        setRescanEnabled(true);
        renderError(`Scan failed: ${err.message}`);
    }
}

function startPolling() {
    stopPolling();
    pollTimer = setInterval(pollProgress, POLL_MS);
}

function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

async function pollProgress() {
    if (!scanTaskId) { stopPolling(); return; }
    try {
        const s = await pollTaskStatus(scanTaskId);
        if (s.status === 'running' || s.status === 'pending') {
            const pct = s.total ? Math.round(s.progress / s.total * 100) : 0;
            showLoadingSpinner(s.message || `Scanning… ${pct}%`, pct);
        } else if (s.status === 'completed') {
            stopPolling();
            scanTaskId = null;
            setRescanEnabled(true);
            const r = s.result || {};
            showNotification(`Scan complete — ${r.pair_count ?? 0} pairs found in ${r.elapsed_seconds ?? '?'}s`, 'success');
            if ($rescanBtn) $rescanBtn.style.display = '';
            await loadPage(0);
        } else {
            // failed / cancelled
            stopPolling();
            scanTaskId = null;
            setRescanEnabled(true);
            renderError(s.error || s.message || 'Scan failed');
        }
    } catch (err) {
        stopPolling();
        renderError(`Poll error: ${err.message}`);
    }
}

// ---------------------------------------------------------------------------
// Page loading
// ---------------------------------------------------------------------------
async function loadPage(offset) {
    const threshold = parseInt($thresholdSlider.value);
    isLoading = true;
    showLoadingSpinner(`Loading pairs (threshold ≤ ${threshold})…`);

    try {
        const data = await fetchQueue(threshold, offset, PAGE_SIZE);
        if (data.phash_bits) phashBits = data.phash_bits;
        if (data.scan_threshold) scanThreshold = data.scan_threshold;
        pairs = data.pairs;
        totalPairs = data.total;
        pageOffset = offset;
        currentIndex = 0;

        if (pairs.length > 0) {
            $actionBar.style.display = '';
            $keyboardHints.style.display = '';
            renderPair();
        } else if (totalPairs === 0) {
            renderEmpty();
        } else {
            // Offset past end, go back
            await loadPage(0);
            return;
        }
    } catch (err) {
        renderError(err.message);
    } finally {
        isLoading = false;
    }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
function showLoadingSpinner(msg, pct) {
    $actionBar.style.display = 'none';
    $keyboardHints.style.display = 'none';
    const bar = typeof pct === 'number'
        ? `<div class="dup-scan-progress"><div class="dup-scan-progress-fill" style="width:${pct}%"></div></div>`
        : '';
    $content.innerHTML = `
        <div class="dup-loading">
            <div class="dup-spinner"></div>
            <span>${msg}</span>
            ${bar}
        </div>`;
}

function renderError(msg) {
    $content.innerHTML = `
        <div class="dup-state-message">
            <div class="icon">⚠️</div>
            <h2>Error</h2>
            <p>${msg}</p>
            <button class="dup-scan-btn" id="btnRetry">Retry</button>
        </div>`;
    document.getElementById('btnRetry')?.addEventListener('click', boot);
}

function renderPair() {
    if (pairs.length === 0) { renderEmpty(); return; }

    // If we walked past the end of this page, load next page
    if (currentIndex >= pairs.length) {
        if (pageOffset + pairs.length < totalPairs) {
            loadPage(pageOffset + PAGE_SIZE);
        } else {
            renderComplete();
        }
        return;
    }
    // If we walked before this page, load previous page
    if (currentIndex < 0) {
        if (pageOffset > 0) {
            // Load previous page and set cursor to last item
            loadPage(Math.max(0, pageOffset - PAGE_SIZE)).then(() => {
                currentIndex = pairs.length - 1;
                renderPair();
            });
        } else {
            currentIndex = 0;
            renderPair();
        }
        return;
    }

    const pair = pairs[currentIndex];
    const a = pair.image_a;
    const b = pair.image_b;
    const pixA = (a.width || 0) * (a.height || 0);
    const pixB = (b.width || 0) * (b.height || 0);
    const key = pairKey(a.id, b.id);
    const staged = stagedActions.get(key);

    const modeClass = `mode-${compareMode}`;
    let stageClassA = '', stageClassB = '', badgeA = '', badgeB = '';
    if (staged) {
        if (staged.action === 'delete_a') {
            stageClassA = 'staged-delete'; badgeA = 'DELETE';
        } else if (staged.action === 'delete_b') {
            stageClassB = 'staged-delete'; badgeB = 'DELETE';
        } else {
            stageClassA = 'staged'; stageClassB = 'staged';
            const lbl = actionLabel(staged.action, staged.detail);
            badgeA = lbl; badgeB = lbl;
        }
    }

    $content.innerHTML = `
        <div class="dup-comparison ${modeClass}" id="comparison">
            <div class="dup-image-panel" id="panelA">
                <div class="dup-img-wrap ${stageClassA}" id="wrapA">
                    <span class="dup-label">A</span>
                    <span class="dup-staged-badge">${badgeA}</span>
                    <img src="/static/${a.thumb}" data-full="/static/${a.path}"
                         alt="Image A" loading="eager"
                         onclick="window.open('/view/${encodeURIComponent(a.filepath)}', '_blank')">
                </div>
            </div>
            <div class="dup-image-panel" id="panelB">
                <div class="dup-img-wrap ${stageClassB}" id="wrapB">
                    <span class="dup-label">B</span>
                    <span class="dup-staged-badge">${badgeB}</span>
                    <img src="/static/${b.thumb}" data-full="/static/${b.path}"
                         alt="Image B" loading="eager"
                         onclick="window.open('/view/${encodeURIComponent(b.filepath)}', '_blank')">
                </div>
            </div>
            <span class="dup-overlay-label" id="overlayLabel">A</span>
            <div class="dup-overlay-hint" id="overlayHint">Hold <kbd>C</kbd> to compare</div>
            <div class="dup-slider-handle" id="sliderHandle"></div>
        </div>

        <div class="dup-info-row">
            <div class="dup-info-card">
                <a href="/view/${encodeURIComponent(a.filepath)}" target="_blank">${a.filepath}</a>
                <span class="dup-info-detail"><span class="${cmpClass(pixA, pixB, 'a')}">${a.width || '?'}×${a.height || '?'}</span> <span class="dup-sep">·</span> <span class="${cmpClass(a.file_size, b.file_size, 'a')}">${formatBytes(a.file_size)}</span> <span class="dup-sep">·</span> <span class="${cmpClass(a.tag_count, b.tag_count, 'a')}">${a.tag_count} tags</span></span>
            </div>
            <div class="dup-info-card">
                <a href="/view/${encodeURIComponent(b.filepath)}" target="_blank">${b.filepath}</a>
                <span class="dup-info-detail"><span class="${cmpClass(pixA, pixB, 'b')}">${b.width || '?'}×${b.height || '?'}</span> <span class="dup-sep">·</span> <span class="${cmpClass(a.file_size, b.file_size, 'b')}">${formatBytes(b.file_size)}</span> <span class="dup-sep">·</span> <span class="${cmpClass(a.tag_count, b.tag_count, 'b')}">${b.tag_count} tags</span></span>
            </div>
        </div>

        <div class="dup-confidence">
            <div class="dup-confidence-bar">
                <div class="dup-confidence-fill ${confidenceClass(pair.confidence)}"
                     style="width: ${pair.confidence}%"></div>
            </div>
            <span class="dup-confidence-text">${pair.distance === 0 ? 'Identical' : pair.confidence + '% match'} · distance ${pair.distance}</span>
        </div>
    `;

    // Load full-res images after thumbs
    requestAnimationFrame(() => {
        $content.querySelectorAll('.dup-img-wrap img').forEach(img => {
            const full = img.dataset.full;
            if (full) {
                const loader = new Image();
                loader.onload = () => { img.src = full; };
                loader.src = full;
            }
        });
    });

    if (compareMode === 'slider') { updateSlider(sliderPos); setupSliderDrag(); }

    updateProgress();
    updateUnstageBtn(staged);
    updateActionHighlights(staged);

    // Preload neighbours
    preloadPair(currentIndex + 1);
    preloadPair(currentIndex - 1);
}

function renderEmpty() {
    const threshold = $thresholdSlider.value;
    $content.innerHTML = `
        <div class="dup-state-message">
            <div class="icon">🔍</div>
            <h2>No duplicate pairs found</h2>
            <p>No unreviewed duplicates at threshold ≤ ${threshold}. Try increasing the threshold or re-scan.</p>
            <button class="dup-scan-btn" id="btnRescan">Re-scan</button>
        </div>`;
    $actionBar.style.display = 'none';
    $keyboardHints.style.display = 'none';
    updateProgress();
    document.getElementById('btnRescan')?.addEventListener('click', startScan);
}

function renderComplete() {
    const pending = stagedActions.size;
    $content.innerHTML = `
        <div class="dup-state-message">
            <div class="icon">✅</div>
            <h2>All pairs reviewed!</h2>
            <p>${pending > 0
                ? `You have ${pending} pending action(s). Click <strong>Review</strong> to commit them.`
                : 'All duplicate pairs have been processed.'
            }</p>
        </div>`;
    $actionBar.style.display = 'none';
    $keyboardHints.style.display = 'none';
    updateProgress();
}

function updateProgress() {
    const globalIndex = pageOffset + currentIndex;
    const display = totalPairs > 0 ? `${Math.min(globalIndex + 1, totalPairs)} / ${totalPairs}` : '0 / 0';
    $progressText.textContent = display;
    const pct = totalPairs > 0 ? ((globalIndex + 1) / totalPairs) * 100 : 0;
    $progressFill.style.width = `${Math.min(pct, 100)}%`;
    $pendingBadge.textContent = stagedActions.size > 0 ? stagedActions.size : '';
}

function updateUnstageBtn(staged) {
    const btn = document.getElementById('btnUnstage');
    if (btn) btn.style.display = staged ? '' : 'none';
}

function updateActionHighlights(staged) {
    document.querySelectorAll('.dup-action-btn.active').forEach(b => b.classList.remove('active'));
    if (!staged) return;
    switch (staged.action) {
        case 'delete_a': document.getElementById('btnDeleteA')?.classList.add('active'); break;
        case 'delete_b': document.getElementById('btnDeleteB')?.classList.add('active'); break;
        case 'non_duplicate': document.getElementById('btnNotDup')?.classList.add('active'); break;
        case 'related':
            if (staged.detail === 'sibling') {
                document.getElementById('btnSiblings')?.classList.add('active');
            } else {
                document.getElementById('btnRelated')?.classList.add('active');
            }
            break;
    }
}

function preloadPair(index) {
    if (index < 0 || index >= pairs.length) return;
    const p = pairs[index];
    [p.image_a, p.image_b].forEach(img => { new Image().src = `/static/${img.path}`; });
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
function goTo(index) {
    if (isLoading) return;
    currentIndex = index;
    renderPair();
}
function next() { goTo(currentIndex + 1); }
function prev() { goTo(currentIndex - 1); }

// ---------------------------------------------------------------------------
// Staging Actions
// ---------------------------------------------------------------------------
function stageAction(action, detail) {
    if (pairs.length === 0 || currentIndex < 0 || currentIndex >= pairs.length) return;
    const pair = pairs[currentIndex];
    const key = pairKey(pair.image_a.id, pair.image_b.id);

    const existing = stagedActions.get(key);
    if (existing && existing.action === action && existing.detail === detail) {
        unstage(); return;
    }

    stagedActions.set(key, { action, detail, pair });
    updateProgress();
    renderPair();
    setTimeout(() => next(), 300);
}

function unstage() {
    if (pairs.length === 0 || currentIndex < 0 || currentIndex >= pairs.length) return;
    const pair = pairs[currentIndex];
    const key = pairKey(pair.image_a.id, pair.image_b.id);
    stagedActions.delete(key);
    updateProgress();
    renderPair();
}

// ---------------------------------------------------------------------------
// Comparison Modes
// ---------------------------------------------------------------------------
function setMode(mode) {
    compareMode = mode;
    document.querySelectorAll('.dup-mode-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === mode);
    });
    renderPair();
}

function startComparison() {
    if (compareMode !== 'overlay' || isComparing) return;
    isComparing = true;
    document.getElementById('comparison')?.classList.add('comparing');
    const hint = document.getElementById('overlayHint');
    if (hint) hint.textContent = 'Showing B';
    const olbl = document.getElementById('overlayLabel');
    if (olbl) olbl.textContent = 'B';
}

function stopComparison() {
    if (!isComparing) return;
    isComparing = false;
    document.getElementById('comparison')?.classList.remove('comparing');
    const hint = document.getElementById('overlayHint');
    if (hint) hint.textContent = 'Hold C to compare';
    const olbl = document.getElementById('overlayLabel');
    if (olbl) olbl.textContent = 'A';
}

function updateSlider(pct) {
    sliderPos = Math.max(0, Math.min(100, pct));
    const comp = document.getElementById('comparison');
    const handle = document.getElementById('sliderHandle');
    if (comp) comp.style.setProperty('--slider-clip-right', `${100 - sliderPos}%`);
    if (handle) handle.style.left = `${sliderPos}%`;
}

function setupSliderDrag() {
    const handle = document.getElementById('sliderHandle');
    const comp = document.getElementById('comparison');
    if (!handle || !comp) return;

    handle.addEventListener('mousedown', e => { e.preventDefault(); isDraggingSlider = true; });
    comp.addEventListener('mousedown', e => {
        if (compareMode !== 'slider') return;
        isDraggingSlider = true;
        const rect = comp.getBoundingClientRect();
        updateSlider(((e.clientX - rect.left) / rect.width) * 100);
    });
}

document.addEventListener('mousemove', e => {
    if (!isDraggingSlider) return;
    const comp = document.getElementById('comparison');
    if (!comp) return;
    const rect = comp.getBoundingClientRect();
    updateSlider(((e.clientX - rect.left) / rect.width) * 100);
});
document.addEventListener('mouseup', () => { isDraggingSlider = false; });

// ---------------------------------------------------------------------------
// Review Panel
// ---------------------------------------------------------------------------
function openReview() { renderReviewList(); $reviewOverlay.classList.add('open'); }
function closeReview() { $reviewOverlay.classList.remove('open'); }

function renderReviewList() {
    if (stagedActions.size === 0) {
        $reviewList.innerHTML = `
            <div class="dup-state-message" style="padding: var(--spacing-lg);">
                <p>No actions staged yet.</p>
            </div>`;
        return;
    }

    let html = '';
    for (const [key, entry] of stagedActions) {
        const { action, detail, pair } = entry;
        html += `
            <div class="dup-review-item" data-key="${key}">
                <div class="dup-review-thumbs">
                    <img src="/static/${pair.image_a.thumb}" alt="A">
                    <img src="/static/${pair.image_b.thumb}" alt="B">
                </div>
                <span class="dup-review-action-badge ${actionBadgeClass(action)}">${actionLabel(action, detail)}</span>
                <button class="dup-review-remove" data-key="${key}" title="Remove">✕</button>
            </div>`;
    }
    $reviewList.innerHTML = html;

    $reviewList.querySelectorAll('.dup-review-remove').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            stagedActions.delete(btn.dataset.key);
            updateProgress();
            renderReviewList();
            renderPair();
        });
    });
}

async function commitAll() {
    if (stagedActions.size === 0) return;

    const actions = [];
    for (const [, entry] of stagedActions) {
        const { action, detail, pair } = entry;
        actions.push({
            image_id_a: pair.image_a.id,
            image_id_b: pair.image_b.id,
            action,
            detail: detail || undefined
        });
    }

    try {
        isLoading = true;
        showCommitProgress('Starting commit…', 0, actions.length);
        const resp = await commitToServer(actions);
        commitTaskId = resp.task_id;
        startCommitPolling();
    } catch (err) {
        isLoading = false;
        showNotification(`Commit failed: ${err.message}`, 'error', 6000);
    }
}

function showCommitProgress(msg, current, total) {
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;
    const $footer = document.querySelector('.dup-review-footer');
    if ($footer) {
        $footer.innerHTML = `
            <div class="dup-commit-progress-wrap">
                <span class="dup-commit-progress-text">${msg}</span>
                <div class="dup-scan-progress">
                    <div class="dup-scan-progress-fill" style="width:${pct}%"></div>
                </div>
                <span class="dup-commit-progress-count">${current} / ${total}</span>
            </div>`;
    }
}

function restoreReviewFooter() {
    const $footer = document.querySelector('.dup-review-footer');
    if ($footer) {
        $footer.innerHTML = `
            <button class="dup-clear-btn" id="reviewClear">Clear All</button>
            <button class="dup-commit-btn" id="reviewCommit">Commit All</button>`;
        document.getElementById('reviewClear')?.addEventListener('click', clearAll);
        document.getElementById('reviewCommit')?.addEventListener('click', commitAll);
    }
}

function startCommitPolling() {
    stopCommitPolling();
    commitPollTimer = setInterval(pollCommitProgress, 500);
}

function stopCommitPolling() {
    if (commitPollTimer) { clearInterval(commitPollTimer); commitPollTimer = null; }
}

async function pollCommitProgress() {
    if (!commitTaskId) { stopCommitPolling(); return; }
    try {
        const s = await pollTaskStatus(commitTaskId);
        if (s.status === 'running' || s.status === 'pending') {
            showCommitProgress(
                s.message || 'Committing…',
                s.progress || 0,
                s.total || 0
            );
        } else if (s.status === 'completed') {
            stopCommitPolling();
            commitTaskId = null;
            const result = s.result || {};
            const msg = `Done: ${result.success_count} succeeded` +
                        (result.error_count > 0 ? `, ${result.error_count} failed` : '');

            if (result.error_count > 0) {
                showNotification(msg, 'warning', 6000);
                const failedKeys = new Set(
                    (result.errors || []).map(e => pairKey(e.image_id_a, e.image_id_b))
                );
                for (const key of [...stagedActions.keys()]) {
                    if (!failedKeys.has(key)) stagedActions.delete(key);
                }
            } else {
                showNotification(msg, 'success');
                stagedActions.clear();
            }

            restoreReviewFooter();
            closeReview();
            await loadPage(0);
            isLoading = false;
        } else {
            stopCommitPolling();
            commitTaskId = null;
            restoreReviewFooter();
            showNotification(s.error || s.message || 'Commit failed', 'error', 6000);
            isLoading = false;
        }
    } catch (err) {
        stopCommitPolling();
        commitTaskId = null;
        restoreReviewFooter();
        showNotification(`Commit poll error: ${err.message}`, 'error', 6000);
        isLoading = false;
    }
}

function clearAll() {
    stagedActions.clear();
    updateProgress();
    renderReviewList();
    renderPair();
}

// ---------------------------------------------------------------------------
// Keyboard Shortcuts
// ---------------------------------------------------------------------------
function setupKeyboard() {
    document.addEventListener('keydown', e => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

        if (e.key === 'c' || e.key === 'C') { if (!e.repeat) startComparison(); return; }

        switch (e.key) {
            case 'ArrowRight': case 'j': e.preventDefault(); next(); break;
            case 'ArrowLeft':  case 'k': e.preventDefault(); prev(); break;
            case 'a': stageAction('delete_a'); break;
            case 'b': stageAction('delete_b'); break;
            case 'n': stageAction('non_duplicate'); break;
            case 's': stageAction('related', 'sibling'); break;
            case 'r': toggleRelatedMenu(); break;
            case 'u': unstage(); break;
            case '1': setMode('side'); break;
            case '2': setMode('overlay'); break;
            case '3': setMode('slider'); break;
            case 'Enter':
                e.preventDefault();
                if ($reviewOverlay.classList.contains('open')) closeReview();
                else openReview();
                break;
            case 'Escape':
                closeReview();
                closeRelatedMenu();
                break;
        }
    });

    document.addEventListener('keyup', e => {
        if (e.key === 'c' || e.key === 'C') stopComparison();
    });
}

// ---------------------------------------------------------------------------
// Related Menu
// ---------------------------------------------------------------------------
function toggleRelatedMenu() {
    const menu = document.getElementById('relatedMenu');
    if (menu) menu.classList.toggle('open');
}

function closeRelatedMenu() {
    const menu = document.getElementById('relatedMenu');
    if (menu) menu.classList.remove('open');
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
function init() {
    $content        = document.getElementById('contentArea');
    $actionBar      = document.getElementById('actionBar');
    $keyboardHints  = document.getElementById('keyboardHints');
    $progressText   = document.getElementById('progressText');
    $progressFill   = document.getElementById('progressFill');
    $pendingBadge   = document.getElementById('pendingBadge');
    $thresholdSlider = document.getElementById('thresholdSlider');
    $thresholdValue = document.getElementById('thresholdValue');
    $reviewOverlay  = document.getElementById('reviewOverlay');
    $reviewList     = document.getElementById('reviewList');
    $rescanBtn      = document.getElementById('btnRescanToolbar');

    // Re-scan button (hidden until cache exists)
    if ($rescanBtn) {
        $rescanBtn.style.display = 'none';
        $rescanBtn.addEventListener('click', startScan);
    }

    // Mode buttons
    document.querySelectorAll('.dup-mode-btn').forEach(btn => {
        btn.addEventListener('click', () => setMode(btn.dataset.mode));
    });

    // Threshold slider — changing threshold reloads from cache (instant)
    let thresholdDebounce;
    $thresholdSlider.addEventListener('input', () => {
        $thresholdValue.textContent = $thresholdSlider.value;
        clearTimeout(thresholdDebounce);
        thresholdDebounce = setTimeout(() => loadPage(0), 400);
    });

    // Action buttons
    document.getElementById('btnPrev').addEventListener('click', prev);
    document.getElementById('btnNext').addEventListener('click', next);
    document.getElementById('btnDeleteA').addEventListener('click', () => stageAction('delete_a'));
    document.getElementById('btnDeleteB').addEventListener('click', () => stageAction('delete_b'));
    document.getElementById('btnNotDup').addEventListener('click', () => stageAction('non_duplicate'));
    document.getElementById('btnSiblings').addEventListener('click', () => stageAction('related', 'sibling'));
    document.getElementById('btnRelated').addEventListener('click', toggleRelatedMenu);
    document.getElementById('btnUnstage').addEventListener('click', unstage);

    document.querySelectorAll('.dup-related-item').forEach(item => {
        item.addEventListener('click', () => {
            stageAction('related', item.dataset.detail);
            closeRelatedMenu();
        });
    });

    document.getElementById('pendingBtn').addEventListener('click', openReview);
    document.getElementById('reviewClose').addEventListener('click', closeReview);
    document.getElementById('reviewClear').addEventListener('click', clearAll);
    document.getElementById('reviewCommit').addEventListener('click', commitAll);

    $reviewOverlay.addEventListener('click', e => { if (e.target === $reviewOverlay) closeReview(); });
    document.addEventListener('click', e => { if (!e.target.closest('.dup-related-wrap')) closeRelatedMenu(); });

    setupKeyboard();
    boot();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
