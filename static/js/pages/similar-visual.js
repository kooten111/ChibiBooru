/**
 * Similarity Search page - method toggles, weights, thresholds, fetch and render.
 * Config is read from script#similar-visual-config (JSON).
 */
(function () {
    const configEl = document.getElementById('similar-visual-config');
    const config = configEl ? JSON.parse(configEl.textContent) : { filepath: '', exclude_family: false };

    let filepath = config.filepath || '';
    let selectedMethods = ['vector'];
    const methodWeights = { phash: 100, colorhash: 100, tags: 100, vector: 100 };
    const methodThresholds = {
        visual: 15,
        tags: 10,
        vector: 30
    };
    let excludeFamily = !!config.exclude_family;
    let isLoading = false;

    let allResults = [];
    let displayedCount = 0;
    const PAGE_SIZE = 20;

    const methodBtns = document.querySelectorAll('.method-btn');
    const weightsContainer = document.getElementById('weightsContainer');
    const weightRows = document.querySelectorAll('.weight-row');
    const blendNote = document.getElementById('blendNote');
    const thresholdSection = document.getElementById('thresholdSection');
    const visualThresholdRow = document.getElementById('visualThresholdRow');
    const tagThresholdRow = document.getElementById('tagThresholdRow');
    const semanticThresholdRow = document.getElementById('semanticThresholdRow');
    const visualThresholdSlider = document.getElementById('visualThresholdSlider');
    const tagThresholdSlider = document.getElementById('tagThresholdSlider');
    const semanticThresholdSlider = document.getElementById('semanticThresholdSlider');
    const visualThresholdValue = document.getElementById('visualThresholdValue');
    const tagThresholdValue = document.getElementById('tagThresholdValue');
    const semanticThresholdValue = document.getElementById('semanticThresholdValue');
    const excludeFamilyCheckbox = document.getElementById('excludeFamily');
    const searchBtn = document.getElementById('searchBtn');
    const resultCount = document.getElementById('resultCount');
    const resultsGridContainer = document.querySelector('.results-grid-container');

    function encodePathForUrl(path) {
        if (!path) return '';
        return path.split('/').map(part => encodeURIComponent(part)).join('/');
    }

    function updateUI() {
        if (blendNote) blendNote.style.display = selectedMethods.length > 1 ? 'inline' : 'none';
        if (weightsContainer) weightsContainer.classList.toggle('visible', selectedMethods.length > 1);
        weightRows.forEach(row => {
            const method = row.dataset.weight;
            row.style.display = selectedMethods.includes(method) ? 'flex' : 'none';
        });

        const hasVisual = selectedMethods.includes('phash') || selectedMethods.includes('colorhash');
        const hasTags = selectedMethods.includes('tags');
        const hasVector = selectedMethods.includes('vector');

        if (visualThresholdRow) visualThresholdRow.style.display = hasVisual ? 'block' : 'none';
        if (tagThresholdRow) tagThresholdRow.style.display = hasTags ? 'block' : 'none';
        if (semanticThresholdRow) semanticThresholdRow.style.display = hasVector ? 'block' : 'none';
        if (thresholdSection) thresholdSection.style.display = (hasVisual || hasTags || hasVector) ? 'block' : 'none';
    }

    function updateSliderFill(slider) {
        const value = slider.value;
        const color = getComputedStyle(slider.parentElement).getPropertyValue('--weight-color').trim();
        slider.style.background = `linear-gradient(to right, ${color} 0%, ${color} ${value}%, rgba(255, 255, 255, 0.2) ${value}%, rgba(255, 255, 255, 0.2) 100%)`;
    }

    let searchTimeout = null;
    function debouncedSearch() {
        if (searchTimeout) clearTimeout(searchTimeout);
        searchTimeout = setTimeout(fetchResults, 300);
    }

    function buildApiUrl() {
        const excludeFamilyParam = excludeFamily ? 'true' : 'false';
        const visualThreshold = methodThresholds.visual;
        const tagThreshold = (methodThresholds.tags / 100).toFixed(2);
        const semanticThreshold = (methodThresholds.vector / 100).toFixed(2);

        const hasOnlyVisual = selectedMethods.every(m => m === 'phash' || m === 'colorhash');
        if (hasOnlyVisual) {
            let colorWeight = 0;
            if (selectedMethods.includes('colorhash') && selectedMethods.includes('phash')) {
                const pW = methodWeights.phash;
                const cW = methodWeights.colorhash;
                colorWeight = cW / (pW + cW);
            } else if (selectedMethods.includes('colorhash')) {
                colorWeight = 1;
            }
            return `/api/similar/${encodeURIComponent(filepath)}?threshold=${visualThreshold}&limit=500&exclude_family=${excludeFamilyParam}&color_weight=${colorWeight}`;
        }

        let totalWeight = 0;
        selectedMethods.forEach(m => { totalWeight += methodWeights[m] || 0; });

        let visualWeight = 0;
        if (selectedMethods.includes('phash')) visualWeight += methodWeights.phash / totalWeight;
        if (selectedMethods.includes('colorhash')) visualWeight += methodWeights.colorhash / totalWeight;
        const tagWeight = selectedMethods.includes('tags') ? methodWeights.tags / totalWeight : 0;
        const semanticWeight = selectedMethods.includes('vector') ? methodWeights.vector / totalWeight : 0;

        return `/api/similar-blended/${encodeURIComponent(filepath)}?visual_weight=${visualWeight.toFixed(2)}&tag_weight=${tagWeight.toFixed(2)}&semantic_weight=${semanticWeight.toFixed(2)}&visual_threshold=${visualThreshold}&tag_threshold=${tagThreshold}&semantic_threshold=${semanticThreshold}&exclude_family=${excludeFamilyParam}`;
    }

    async function fetchResults() {
        if (isLoading || !searchBtn) return;
        isLoading = true;
        searchBtn.disabled = true;
        searchBtn.innerHTML = '<div class="spinner"></div><span>Searching...</span>';

        try {
            const response = await fetch(buildApiUrl());
            const data = await response.json();
            allResults = data.similar || [];
            displayedCount = 0;
            if (resultCount) resultCount.textContent = `${allResults.length} found`;
            showInitialResults();
        } catch (err) {
            console.error('Search error:', err);
        } finally {
            isLoading = false;
            if (searchBtn) {
                searchBtn.disabled = false;
                searchBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg><span>Find Similar</span>`;
            }
        }
    }

    function showInitialResults() {
        const container = document.querySelector('.results-grid-container');
        if (!container) return;

        if (allResults.length === 0) {
            container.innerHTML = `<div class="empty-state"><div class="empty-state-content"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg><p>No similar images found</p></div></div>`;
            return;
        }
        container.innerHTML = `<div class="results-grid" id="resultsGrid"></div>`;
        displayedCount = 0;
        loadMore();
    }

    function renderCard(img) {
        const distance = img.distance ?? img.visual_distance ?? Math.round((1 - (img.score || 0)) * 64);
        const distanceClass = distance <= 5 ? 'identical' : distance <= 10 ? 'similar' : distance <= 15 ? 'loose' : 'different';
        const score = img.score || img.similarity || 0.5;
        const visualScore = img.visual_score !== undefined ? Math.round(img.visual_score * 100) : null;
        const tagScore = img.tag_score !== undefined ? Math.round(img.tag_score * 100) : null;
        const semanticScore = img.semantic_score !== undefined ? Math.round(img.semantic_score * 100) : null;

        const safePath = (img.path || '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
        return `<div class="result-card" data-path="${safePath}">
            <div class="result-thumb">
                <img src="/static/${encodePathForUrl(img.thumb)}" alt="Similar" loading="lazy">
                <span class="distance-badge ${distanceClass}">${distance}</span>
                <div class="result-overlay">
                    ${visualScore !== null ? `<div class="score-row"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg><span>${visualScore}%</span></div>` : ''}
                    ${tagScore !== null ? `<div class="score-row"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2"><path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z"></path><path d="M7 7h.01"></path></svg><span>${tagScore}%</span></div>` : ''}
                    ${semanticScore !== null ? `<div class="score-row"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#a855f7" stroke-width="2"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"></path></svg><span>${semanticScore}%</span></div>` : ''}
                    <div class="actions">
                        <a href="/view/${encodePathForUrl(img.path)}" class="action-btn btn-view"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg></a>
                        <button class="action-btn btn-delete" type="button"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg></button>
                    </div>
                </div>
            </div>
            <div class="score-bar"><div class="score-bar-fill" style="width: ${score * 100}%;"></div></div>
        </div>`;
    }

    function loadMore() {
        const grid = document.getElementById('resultsGrid');
        if (!grid || displayedCount >= allResults.length) return;
        const nextBatch = allResults.slice(displayedCount, displayedCount + PAGE_SIZE);
        const html = nextBatch.map(img => renderCard(img)).join('');
        grid.insertAdjacentHTML('beforeend', html);
        displayedCount += nextBatch.length;
        if (resultCount) resultCount.textContent = `${displayedCount} / ${allResults.length} shown`;
    }

    function doDeleteImage(imagePath, cardEl) {
        if (!imagePath || !cardEl) return;
        if (!confirm('Delete this image?')) return;
        cardEl.style.opacity = '0.5';

        const secret = localStorage.getItem('system_secret');
        if (!secret) {
            alert('Please configure system secret in System panel first');
            cardEl.style.opacity = '1';
            return;
        }
        const cleanPath = imagePath.replace('images/', '');
        fetch(`/api/delete_image?secret=${encodeURIComponent(secret)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filepath: imagePath })
        }).then(r => {
            if (r.ok) {
                cardEl.remove();
                allResults = allResults.filter(r => r.path !== imagePath);
                displayedCount = document.querySelectorAll('.result-card').length;
                if (resultCount) resultCount.textContent = `${displayedCount} / ${allResults.length} shown`;
            } else { throw new Error('Failed to delete'); }
        }).catch(err => {
            console.error('Delete error:', err);
            alert('Failed to delete image');
            cardEl.style.opacity = '1';
        });
    }

    window.deleteSimilarImage = function (cardEl) {
        if (!cardEl) return;
        const imagePath = cardEl.dataset.path;
        if (imagePath) doDeleteImage(imagePath, cardEl);
    };
    window.deleteImage = function (imagePath, button) {
        const card = button && button.closest && button.closest('.result-card');
        if (card) doDeleteImage(imagePath, card);
    };

    methodBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.disabled) return;
            const method = btn.dataset.method;
            if (btn.classList.contains('selected')) {
                if (selectedMethods.length === 1) return;
                selectedMethods = selectedMethods.filter(m => m !== method);
                btn.classList.remove('selected');
            } else {
                selectedMethods.push(method);
                btn.classList.add('selected');
            }
            updateUI();
            debouncedSearch();
        });
    });

    weightRows.forEach(row => {
        const slider = row.querySelector('.weight-slider');
        const valueSpan = row.querySelector('.weight-value');
        const method = row.dataset.weight;
        if (!slider) return;
        updateSliderFill(slider);
        slider.addEventListener('input', () => {
            if (valueSpan) valueSpan.textContent = slider.value + '%';
            methodWeights[method] = parseInt(slider.value, 10);
            updateSliderFill(slider);
            debouncedSearch();
        });
    });

    if (visualThresholdSlider) visualThresholdSlider.addEventListener('input', () => {
        methodThresholds.visual = parseInt(visualThresholdSlider.value, 10);
        if (visualThresholdValue) visualThresholdValue.textContent = methodThresholds.visual;
        debouncedSearch();
    });
    if (tagThresholdSlider) tagThresholdSlider.addEventListener('input', () => {
        methodThresholds.tags = parseInt(tagThresholdSlider.value, 10);
        if (tagThresholdValue) tagThresholdValue.textContent = methodThresholds.tags + '%';
        debouncedSearch();
    });
    if (semanticThresholdSlider) semanticThresholdSlider.addEventListener('input', () => {
        methodThresholds.vector = parseInt(semanticThresholdSlider.value, 10);
        if (semanticThresholdValue) semanticThresholdValue.textContent = methodThresholds.vector + '%';
        debouncedSearch();
    });
    if (excludeFamilyCheckbox) excludeFamilyCheckbox.addEventListener('change', () => {
        excludeFamily = excludeFamilyCheckbox.checked;
        debouncedSearch();
    });
    if (searchBtn) searchBtn.addEventListener('click', fetchResults);
    if (resultsGridContainer) resultsGridContainer.addEventListener('scroll', () => {
        const { scrollTop, scrollHeight, clientHeight } = resultsGridContainer;
        if (scrollTop + clientHeight >= scrollHeight - 200) loadMore();
    });

    document.body.addEventListener('click', function (e) {
        const btn = e.target.closest('.result-card .btn-delete');
        if (btn) window.deleteSimilarImage(btn.closest('.result-card'));
    });

    updateUI();
    fetchResults();
})();
