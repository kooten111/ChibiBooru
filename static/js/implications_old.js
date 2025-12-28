// Tag Implications Manager JavaScript
import { showSuccess, showError, showInfo } from './utils/notifications.js';

let currentSuggestions = {};
let currentImplications = [];
let impliedTags = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    initializeTabs();
    loadSuggestions();
    loadExistingImplications();
    initializeManualForm();
});

// Tab Management
function initializeTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.getAttribute('data-tab');

            // Remove active class from all
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));

            // Add active to clicked
            button.classList.add('active');
            document.getElementById(`${tabName}-tab`).classList.add('active');
        });
    });
}

// Load Suggestions
async function loadSuggestions() {
    const summaryEl = document.getElementById('suggestionsSummary');
    const groupsEl = document.getElementById('patternGroups');

    summaryEl.innerHTML = '<div class="summary-loading">Loading suggestions...</div>';
    groupsEl.innerHTML = '';

    try {
        const response = await fetch('/api/implications/suggestions');
        const data = await response.json();

        currentSuggestions = data;

        // Display summary
        summaryEl.innerHTML = `
            <div class="summary-stats">
                <div class="stat-box">
                    <h4>Total Suggestions</h4>
                    <div class="stat-number">${data.summary.total}</div>
                </div>
                <div class="stat-box">
                    <h4>Naming Patterns</h4>
                    <div class="stat-number">${data.summary.naming_count}</div>
                </div>
                <div class="stat-box">
                    <h4>Statistical Correlations</h4>
                    <div class="stat-number">${data.summary.correlation_count}</div>
                </div>
            </div>
        `;

        // Display pattern groups
        if (data.naming && data.naming.length > 0) {
            groupsEl.innerHTML += createPatternGroup('Naming Patterns', 'naming', data.naming,
                'Tag name structure suggests relationships (costumes, franchises, variants)');
        }

        if (data.correlation && data.correlation.length > 0) {
            groupsEl.innerHTML += createPatternGroup('Statistical Correlations', 'correlation', data.correlation,
                'Tags that appear together 85%+ of the time');
        }

        if (data.summary.total === 0) {
            groupsEl.innerHTML = '<div class="no-suggestions">No suggestions found. All patterns have been reviewed!</div>';
        }

        // Attach event listeners
        attachPatternGroupListeners();

    } catch (error) {
        console.error('Error loading suggestions:', error);
        summaryEl.innerHTML = '<div class="error">Failed to load suggestions</div>';
    }
}

function createPatternGroup(title, type, suggestions, description) {
    const suggestionsHtml = suggestions.map((s, idx) => createSuggestionItem(s, type, idx)).join('');

    return `
        <div class="pattern-group" data-pattern="${type}">
            <div class="pattern-header">
                <div class="pattern-info">
                    <h4>${title}</h4>
                    <p>${description} • ${suggestions.length} found</p>
                </div>
                <div class="pattern-actions">
                    <button class="btn-secondary btn-small" onclick="reviewPattern('${type}')">Review All</button>
                    <button class="btn-success btn-small" onclick="approveAllHighConfidence('${type}')">
                        Approve High Confidence
                    </button>
                </div>
            </div>
            <div class="pattern-content">
                <div class="suggestions-grid">
                    ${suggestionsHtml}
                </div>
            </div>
        </div>
    `;
}

function createSuggestionItem(suggestion, type, idx) {
    const confidenceClass = suggestion.confidence >= 0.9 ? 'high-confidence' :
        suggestion.confidence >= 0.7 ? 'medium-confidence' : '';

    const confidencePercent = Math.round(suggestion.confidence * 100);

    return `
        <div class="suggestion-item ${confidenceClass}" data-type="${type}" data-index="${idx}">
            <div class="suggestion-flow">
                <span class="tag-badge">${suggestion.source_tag}</span>
                <span class="flow-arrow">→</span>
                <span class="tag-badge">${suggestion.implied_tag}</span>
            </div>
            <div class="suggestion-meta">
                <span>Confidence: ${confidencePercent}%</span>
                <span>Affects: ${suggestion.affected_images} images</span>
                <span>${suggestion.reason}</span>
            </div>
            <div class="suggestion-actions">
                <button class="btn-secondary btn-small" onclick="previewSuggestion('${type}', ${idx})">
                    Preview
                </button>
                <button class="btn-success btn-small" onclick="approveSuggestion('${type}', ${idx})">
                    ✓ Approve
                </button>
                <button class="btn-danger btn-small" onclick="rejectSuggestion('${type}', ${idx})">
                    ✗ Reject
                </button>
            </div>
        </div>
    `;
}

function attachPatternGroupListeners() {
    document.querySelectorAll('.pattern-header').forEach(header => {
        header.addEventListener('click', (e) => {
            if (e.target.tagName !== 'BUTTON') {
                const content = header.nextElementSibling;
                content.classList.toggle('expanded');
            }
        });
    });
}

function reviewPattern(type) {
    const pattern = document.querySelector(`[data-pattern="${type}"] .pattern-content`);
    pattern.classList.add('expanded');
    pattern.scrollIntoView({ behavior: 'smooth' });
}

async function approveAllHighConfidence(type) {
    if (!confirm('Approve all high confidence (>90%) suggestions for this pattern?')) {
        return;
    }

    const suggestions = currentSuggestions[type].filter(s => s.confidence >= 0.9);

    for (const suggestion of suggestions) {
        await approveSuggestionData(suggestion, type);
    }

    showSuccess(`Approved ${suggestions.length} high confidence suggestions!`);
    loadSuggestions();
}

async function previewSuggestion(type, idx) {
    const suggestion = currentSuggestions[type][idx];

    try {
        const response = await fetch('/api/implications/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_tag: suggestion.source_tag,
                implied_tag: suggestion.implied_tag
            })
        });

        const preview = await response.json();

        showInfo(`Preview for ${suggestion.source_tag} → ${suggestion.implied_tag}\n\n` +
            `Total images with source tag: ${preview.total_images}\n` +
            `Already have implied tag: ${preview.already_has_tag}\n` +
            `Will gain tag: ${preview.will_gain_tag}\n` +
            `Chain implications: ${preview.chain_implications.join(', ') || 'None'}`);

    } catch (error) {
        console.error('Error previewing:', error);
        showError('Failed to load preview');
    }
}

async function approveSuggestion(type, idx) {
    const suggestion = currentSuggestions[type][idx];
    await approveSuggestionData(suggestion, type);
    loadSuggestions();
}

async function approveSuggestionData(suggestion, type) {
    try {
        const response = await fetch('/api/implications/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_tag: suggestion.source_tag,
                implied_tag: suggestion.implied_tag,
                inference_type: type,
                confidence: suggestion.confidence
            })
        });

        const result = await response.json();

        if (result.status === 'success') {
            // Successfully approved
        } else {
            showError('Failed to approve: ' + (result.error || 'Unknown error'));
        }

    } catch (error) {
        console.error('Error approving:', error);
        showError('Failed to approve suggestion');
    }
}

function rejectSuggestion(type, idx) {
    const suggestion = currentSuggestions[type][idx];
    // Just remove from UI - we could add a rejected_implications table later
    const item = document.querySelector(`[data-type="${type}"][data-index="${idx}"]`);
    item.style.display = 'none';
}

// Manual Creation Form
function initializeManualForm() {
    const sourceInput = document.getElementById('sourceTag');
    const impliedInput = document.getElementById('impliedTag');
    const addBtn = document.getElementById('addImpliedBtn');
    const previewBtn = document.getElementById('previewImplicationBtn');
    const createBtn = document.getElementById('createImplicationBtn');

    // Add implied tag on button click or Enter
    addBtn.addEventListener('click', addImpliedTag);
    impliedInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addImpliedTag();
        }
    });

    previewBtn.addEventListener('click', previewManualImplication);
    createBtn.addEventListener('click', createManualImplication);

    // Update create button state when fields change
    sourceInput.addEventListener('input', updateCreateButtonState);
    impliedInput.addEventListener('input', updateCreateButtonState);
}

function addImpliedTag() {
    const input = document.getElementById('impliedTag');
    const tag = input.value.trim();

    if (tag && !impliedTags.includes(tag)) {
        impliedTags.push(tag);
        updateImpliedTagsList();
        input.value = '';
        updateCreateButtonState();
    }
}

function updateImpliedTagsList() {
    const listEl = document.getElementById('impliedTagsList');

    if (impliedTags.length === 0) {
        listEl.innerHTML = '<div style="color: #888; text-align: center;">No tags added yet</div>';
        return;
    }

    listEl.innerHTML = impliedTags.map((tag, idx) => `
        <div class="implied-tag-item">
            <span>${tag}</span>
            <button class="remove-tag-btn" onclick="removeImpliedTag(${idx})">×</button>
        </div>
    `).join('');
}

function removeImpliedTag(idx) {
    impliedTags.splice(idx, 1);
    updateImpliedTagsList();
    updateCreateButtonState();
}

function updateCreateButtonState() {
    const sourceTag = document.getElementById('sourceTag').value.trim();
    const createBtn = document.getElementById('createImplicationBtn');

    createBtn.disabled = !sourceTag || impliedTags.length === 0;
}

async function previewManualImplication() {
    const sourceTag = document.getElementById('sourceTag').value.trim();

    if (!sourceTag || impliedTags.length === 0) {
        showInfo('Please enter source tag and at least one implied tag');
        return;
    }

    const previewSection = document.getElementById('previewSection');
    const previewContent = document.getElementById('previewContent');

    previewContent.innerHTML = '<div>Loading preview...</div>';
    previewSection.style.display = 'block';

    try {
        // Preview each implication
        const previews = await Promise.all(
            impliedTags.map(async (impliedTag) => {
                const response = await fetch('/api/implications/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source_tag: sourceTag, implied_tag: impliedTag })
                });
                return { tag: impliedTag, data: await response.json() };
            })
        );

        previewContent.innerHTML = previews.map(p => `
            <div style="margin-bottom: 15px; padding: 10px; background: #0d0d0d; border-radius: 4px;">
                <strong>${sourceTag} → ${p.tag}</strong><br>
                <small>
                    ${p.data.will_gain_tag} images will gain this tag
                    ${p.data.chain_implications.length > 0 ? `<br>Chain: ${p.data.chain_implications.join(' → ')}` : ''}
                </small>
            </div>
        `).join('');

    } catch (error) {
        console.error('Error previewing:', error);
        previewContent.innerHTML = '<div style="color: #ff6b6b;">Failed to load preview</div>';
    }
}

async function createManualImplication() {
    const sourceTag = document.getElementById('sourceTag').value.trim();

    if (!sourceTag || impliedTags.length === 0) {
        showInfo('Please enter source tag and at least one implied tag');
        return;
    }

    try {
        for (const impliedTag of impliedTags) {
            const response = await fetch('/api/implications/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_tag: sourceTag,
                    implied_tag: impliedTag
                })
            });

            const result = await response.json();

            if (result.status !== 'success') {
                showError(`Failed to create ${sourceTag} → ${impliedTag}: ${result.error}`);
                return;
            }
        }

        showSuccess(`Successfully created ${impliedTags.length} implication(s)!`);

        // Reset form
        document.getElementById('sourceTag').value = '';
        impliedTags = [];
        updateImpliedTagsList();
        document.getElementById('previewSection').style.display = 'none';
        updateCreateButtonState();

        // Reload existing implications
        loadExistingImplications();

    } catch (error) {
        console.error('Error creating implications:', error);
        showError('Failed to create implications');
    }
}

// Load Existing Implications
async function loadExistingImplications() {
    const listEl = document.getElementById('implicationsList');
    listEl.innerHTML = '<div class="implications-loading">Loading implications...</div>';

    try {
        const response = await fetch('/api/implications/all');
        const data = await response.json();

        currentImplications = data.implications;

        if (currentImplications.length === 0) {
            listEl.innerHTML = '<div style="text-align: center; padding: 40px; color: #888;">No implications created yet</div>';
            return;
        }

        // Group by category
        const grouped = {};
        currentImplications.forEach(imp => {
            const cat = imp.source_category || 'general';
            if (!grouped[cat]) grouped[cat] = [];
            grouped[cat].push(imp);
        });

        let html = '';
        for (const [category, implications] of Object.entries(grouped)) {
            html += `
                <div class="implication-group">
                    <div class="group-header" onclick="toggleGroup(this)">
                        <span>${category.charAt(0).toUpperCase() + category.slice(1)} (${implications.length})</span>
                        <span>▼</span>
                    </div>
                    <div class="group-content">
                        ${implications.map(imp => createImplicationRow(imp)).join('')}
                    </div>
                </div>
            `;
        }

        listEl.innerHTML = html;

        // Apply filters
        applyImplicationFilters();

    } catch (error) {
        console.error('Error loading implications:', error);
        listEl.innerHTML = '<div style="color: #ff6b6b;">Failed to load implications</div>';
    }
}

function createImplicationRow(imp) {
    return `
        <div class="implication-row">
            <div class="implication-details">
                <span class="tag-badge ${imp.source_category}">${imp.source_tag}</span>
                <span class="flow-arrow">→</span>
                <span class="tag-badge ${imp.implied_category}">${imp.implied_tag}</span>
            </div>
            <div class="implication-meta">
                ${imp.inference_type} • ${Math.round((imp.confidence || 1.0) * 100)}%
            </div>
            <div class="implication-row-actions">
                <button class="btn-secondary btn-small" onclick="viewChain('${imp.source_tag}')">
                    View Chain
                </button>
                <button class="btn-danger btn-small" onclick="deleteImplication('${imp.source_tag}', '${imp.implied_tag}')">
                    Delete
                </button>
            </div>
        </div>
    `;
}

function toggleGroup(header) {
    const content = header.nextElementSibling;
    content.classList.toggle('expanded');
    const arrow = header.querySelector('span:last-child');
    arrow.textContent = content.classList.contains('expanded') ? '▲' : '▼';
}

async function viewChain(tagName) {
    try {
        const response = await fetch(`/api/implications/chain/${encodeURIComponent(tagName)}`);
        const chain = await response.json();

        const modal = document.getElementById('chainModal');
        const visualization = document.getElementById('chainVisualization');

        visualization.innerHTML = renderChain(chain);

        modal.classList.add('active');

        // Close modal on click outside or X
        const closeBtn = modal.querySelector('.close');
        closeBtn.onclick = () => modal.classList.remove('active');
        modal.onclick = (e) => {
            if (e.target === modal) modal.classList.remove('active');
        };

    } catch (error) {
        console.error('Error loading chain:', error);
        showError('Failed to load implication chain');
    }
}

function renderChain(node, depth = 0) {
    let html = `
        <div class="chain-node" style="margin-left: ${depth * 20}px;">
            <span class="tag-badge ${node.category}">${node.tag}</span>
        </div>
    `;

    if (node.implies && node.implies.length > 0) {
        html += '<div class="chain-arrow" style="margin-left: ' + (depth * 20 + 30) + 'px;">↓</div>';
        node.implies.forEach(child => {
            html += renderChain(child, depth + 1);
        });
    }

    return html;
}

async function deleteImplication(sourceTag, impliedTag) {
    if (!confirm(`Delete implication: ${sourceTag} → ${impliedTag}?`)) {
        return;
    }

    try {
        const response = await fetch('/api/implications/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_tag: sourceTag,
                implied_tag: impliedTag
            })
        });

        const result = await response.json();

        if (result.status === 'success') {
            showSuccess('Implication deleted');
            loadExistingImplications();
        } else {
            showError('Failed to delete: ' + (result.error || 'Unknown error'));
        }

    } catch (error) {
        console.error('Error deleting:', error);
        showError('Failed to delete implication');
    }
}

// Filter existing implications
document.getElementById('implicationFilter')?.addEventListener('input', applyImplicationFilters);
document.getElementById('typeFilter')?.addEventListener('change', applyImplicationFilters);

function applyImplicationFilters() {
    const searchText = document.getElementById('implicationFilter')?.value.toLowerCase() || '';
    const typeFilter = document.getElementById('typeFilter')?.value || 'all';

    document.querySelectorAll('.implication-row').forEach(row => {
        const text = row.textContent.toLowerCase();
        const matchesSearch = text.includes(searchText);
        const meta = row.querySelector('.implication-meta').textContent;
        const matchesType = typeFilter === 'all' || meta.includes(typeFilter);

        row.style.display = (matchesSearch && matchesType) ? 'flex' : 'none';
    });
}

// Refresh button
document.getElementById('refreshSuggestionsBtn')?.addEventListener('click', loadSuggestions);
