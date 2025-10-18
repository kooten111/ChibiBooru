// static/js/saucenao-fetch.js

var SYSTEM_SECRET = localStorage.getItem('system_secret');
var saucenaoResults = [];
var selectedResult = null;

function formatFileSize(bytes) {
    if (bytes >= 1048576) {
        return (bytes / 1048576).toFixed(2) + ' MB';
    } else if (bytes >= 1024) {
        return (bytes / 1024).toFixed(2) + ' KB';
    }
    return bytes + ' bytes';
}

function showSauceNaoFetcher() {
    if (!SYSTEM_SECRET) {
        const secret = prompt('Enter system secret to use SauceNao fetch:');
        if (!secret) return;
        SYSTEM_SECRET = secret;
        localStorage.setItem('system_secret', secret);
    }
    
    const modal = document.createElement('div');
    modal.id = 'saucenaoModal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.9);
        z-index: 10000;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.2s ease-out;
    `;
    
    modal.innerHTML = `
        <div style="
            background: linear-gradient(135deg, rgba(30, 30, 45, 0.95) 0%, rgba(40, 40, 60, 0.95) 100%);
            backdrop-filter: blur(15px);
            border-radius: 16px;
            border: 1px solid rgba(135, 206, 235, 0.3);
            box-shadow: 0 20px 80px rgba(0, 0, 0, 0.8);
            max-width: 900px;
            width: 90%;
            max-height: 90vh;
            overflow-y: auto;
            padding: 30px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h2 style="margin: 0; color: #87ceeb; font-size: 1.5em;">🔍 SauceNao Fetch</h2>
                <button onclick="closeSauceNaoModal()" style="
                    background: rgba(255, 107, 107, 0.2);
                    border: 1px solid rgba(255, 107, 107, 0.5);
                    color: #ff6b6b;
                    padding: 8px 16px;
                    border-radius: 8px;
                    cursor: pointer;
                    font-weight: 600;
                ">&times; Close</button>
            </div>
            
            <div id="saucenaoContent">
                <div style="text-align: center; padding: 40px; color: #87ceeb;">
                    <div style="font-size: 2em; margin-bottom: 10px;">🔍</div>
                    <div style="font-size: 1.1em; font-weight: 600;">Searching SauceNao...</div>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Start search
    searchSauceNao();
}

function closeSauceNaoModal() {
    const modal = document.getElementById('saucenaoModal');
    if (modal) modal.remove();
}

async function searchSauceNao() {
    const filepath = document.getElementById('imageFilepath').value;
    
    try {
        const response = await fetch('/api/saucenao/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                filepath: filepath,
                secret: SYSTEM_SECRET
            })
        });
        
        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Non-JSON response:', text);
            throw new Error('Server returned non-JSON response. Check console for details.');
        }
        
        const data = await response.json();
        
        if (data.error === 'Unauthorized') {
            localStorage.removeItem('system_secret');
            SYSTEM_SECRET = null;
            showNotification('Invalid system secret', 'error');
            closeSauceNaoModal();
            return;
        }
        
        if (!data.found || !data.results || data.results.length === 0) {
            document.getElementById('saucenaoContent').innerHTML = `
                <div style="text-align: center; padding: 40px;">
                    <div style="font-size: 2em; margin-bottom: 10px;">😔</div>
                    <div style="color: #b0b0b0; font-size: 1.1em;">No results found on SauceNao</div>
                    <div style="color: #87ceeb; margin-top: 10px; font-size: 0.9em;">
                        Try searching manually on booru sites
                    </div>
                </div>
            `;
            return;
        }
        
        saucenaoResults = data.results;
        displaySauceNaoResults(data.results);
        
    } catch (error) {
        document.getElementById('saucenaoContent').innerHTML = `
            <div style="text-align: center; padding: 40px; color: #ff6b6b;">
                <div style="font-size: 2em; margin-bottom: 10px;">⚠️</div>
                <div style="font-size: 1.1em; font-weight: 600;">Error: ${error.message}</div>
            </div>
        `;
    }
}

function displaySauceNaoResults(results) {
    const html = `
        <div style="margin-bottom: 20px; padding: 15px; background: rgba(74, 158, 255, 0.1); border-radius: 10px; border: 1px solid rgba(135, 206, 235, 0.3);">
            <div style="color: #87ceeb; font-weight: 600; margin-bottom: 5px;">
                ✓ Found ${results.length} potential match${results.length !== 1 ? 'es' : ''}
            </div>
            <div style="color: #b0b0b0; font-size: 0.9em;">
                Click on a result to view details and apply metadata
            </div>
        </div>
        
        <div style="display: grid; gap: 15px;">
            ${results.map((result, idx) => `
                <div class="saucenao-result" onclick="selectSauceNaoResult(${idx})" style="
                    background: rgba(30, 30, 45, 0.5);
                    border: 2px solid rgba(135, 206, 235, 0.2);
                    border-radius: 12px;
                    padding: 15px;
                    cursor: pointer;
                    transition: all 0.3s ease;
                " onmouseover="this.style.borderColor='rgba(135, 206, 235, 0.5)'; this.style.transform='translateX(5px)';" onmouseout="this.style.borderColor='rgba(135, 206, 235, 0.2)'; this.style.transform='translateX(0)';">
                    <div style="display: flex; gap: 15px; align-items: center;">
                        ${result.thumbnail ? `
                            <img src="${result.thumbnail}" style="
                                width: 100px;
                                height: 100px;
                                object-fit: cover;
                                border-radius: 8px;
                                border: 1px solid rgba(135, 206, 235, 0.2);
                            ">
                        ` : ''}
                        <div style="flex: 1;">
                            <div style="
                                font-size: 1.2em;
                                font-weight: 700;
                                color: #87ceeb;
                                margin-bottom: 8px;
                            ">
                                ${(result.similarity).toFixed(1)}% Match
                            </div>
                            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                                ${result.sources.map(source => `
                                    <span style="
                                        background: rgba(74, 158, 255, 0.2);
                                        padding: 4px 12px;
                                        border-radius: 12px;
                                        color: #87ceeb;
                                        font-size: 0.9em;
                                        font-weight: 600;
                                        text-transform: capitalize;
                                    ">
                                        ${source.type}
                                    </span>
                                `).join('')}
                            </div>
                        </div>
                        <div style="
                            color: #87ceeb;
                            font-size: 1.5em;
                        ">→</div>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    
    document.getElementById('saucenaoContent').innerHTML = html;
}

async function selectSauceNaoResult(idx) {
    const result = saucenaoResults[idx];
    selectedResult = result;
    
    // Show loading
    document.getElementById('saucenaoContent').innerHTML = `
        <div style="text-align: center; padding: 40px; color: #87ceeb;">
            <div style="font-size: 2em; margin-bottom: 10px;">⚙️</div>
            <div style="font-size: 1.1em; font-weight: 600;">Loading metadata...</div>
        </div>
    `;
    
    try {
        // Fetch metadata from all sources in parallel
        const metadataPromises = result.sources.map(source => 
            fetch('/api/saucenao/fetch_metadata', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    source: source.type,
                    post_id: source.post_id,
                    secret: SYSTEM_SECRET
                })
            }).then(async r => {
                const contentType = r.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    const text = await r.text();
                    console.error('Non-JSON response from fetch_metadata:', text);
                    throw new Error('Server returned non-JSON response');
                }
                const data = await r.json();
                console.log(`Metadata result from ${source.type}:`, data);
                return {...data, source: source.type};
            }).catch(err => {
                console.error(`Failed to fetch ${source.type}:`, err);
                return {status: 'error', error: err.message, source: source.type};
            })
        );
        
        const metadataResults = await Promise.all(metadataPromises);
        console.log('All metadata results:', metadataResults);
        displayMetadataOptions(metadataResults);
        
    } catch (error) {
        document.getElementById('saucenaoContent').innerHTML = `
            <div style="text-align: center; padding: 40px; color: #ff6b6b;">
                <div style="font-size: 2em; margin-bottom: 10px;">⚠️</div>
                <div style="font-size: 1.1em; font-weight: 600;">Error: ${error.message}</div>
            </div>
        `;
    }
}

function displayMetadataOptions(metadataResults) {
    const validResults = metadataResults.filter(r => r.status === 'success');
    const failedResults = metadataResults.filter(r => r.status !== 'success');
    
    if (validResults.length === 0) {
        // Show which sources failed and why
        const failedSources = metadataResults.map(r => 
            `<div style="color: #ff6b6b; padding: 8px; background: rgba(255, 107, 107, 0.1); border-radius: 6px; margin: 5px 0;">
                <strong>${r.source}</strong>: ${r.error || 'Unknown error'}
            </div>`
        ).join('');
        
        document.getElementById('saucenaoContent').innerHTML = `
            <div style="padding: 40px;">
                <div style="text-align: center; font-size: 2em; margin-bottom: 15px; color: #ff6b6b;">⚠️</div>
                <div style="text-align: center; font-size: 1.1em; font-weight: 600; color: #ff6b6b; margin-bottom: 20px;">
                    Failed to fetch metadata from all sources
                </div>
                <div style="color: #b0b0b0; margin-bottom: 15px;">Details:</div>
                ${failedSources}
                <div style="margin-top: 20px; text-align: center;">
                    <button onclick="displaySauceNaoResults(saucenaoResults)" style="
                        background: rgba(74, 74, 74, 0.5);
                        border: 1px solid rgba(135, 206, 235, 0.3);
                        color: #87ceeb;
                        padding: 10px 20px;
                        border-radius: 8px;
                        cursor: pointer;
                        font-weight: 600;
                    ">← Back to Results</button>
                </div>
            </div>
        `;
        return;
    }
    
    // Show warning if some sources failed
    const warningSection = failedResults.length > 0 ? `
        <div style="
            background: rgba(255, 165, 0, 0.1);
            border: 1px solid rgba(255, 165, 0, 0.3);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
        ">
            <div style="color: #ffa500; font-weight: 600; margin-bottom: 8px;">⚠️ Some sources unavailable</div>
            <div style="color: #b0b0b0; font-size: 0.9em;">
                ${failedResults.map(r => r.source).join(', ')} could not be fetched
            </div>
        </div>
    ` : '';
    
    // Use first valid result as default
    const primaryResult = validResults[0];
    
    const html = `
        <div style="margin-bottom: 20px;">
            <button onclick="displaySauceNaoResults(saucenaoResults)" style="
                background: rgba(74, 74, 74, 0.5);
                border: 1px solid rgba(135, 206, 235, 0.3);
                color: #87ceeb;
                padding: 8px 16px;
                border-radius: 8px;
                cursor: pointer;
                font-weight: 600;
            ">← Back to Results</button>
        </div>
        
        <div style="display: grid; gap: 20px;">
            <div style="
                background: rgba(30, 30, 45, 0.5);
                border: 1px solid rgba(135, 206, 235, 0.2);
                border-radius: 12px;
                padding: 20px;
            ">
                <h3 style="margin: 0 0 15px 0; color: #87ceeb; font-size: 1.1em;">Select Source</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    ${validResults.map((result, idx) => {
                        const sourceInfo = selectedResult.sources.find(s => s.type === result.source);
                        return `
                        <div style="display: flex; flex-direction: column; gap: 8px;">
                            <button onclick="selectMetadataSource(${idx})" id="sourceBtn${idx}" style="
                                background: ${idx === 0 ? 'rgba(74, 158, 255, 0.3)' : 'rgba(74, 74, 74, 0.5)'};
                                border: 2px solid ${idx === 0 ? 'rgba(135, 206, 235, 0.5)' : 'rgba(135, 206, 235, 0.2)'};
                                color: #e8e8e8;
                                padding: 12px;
                                border-radius: 10px;
                                cursor: pointer;
                                font-weight: 600;
                                text-transform: capitalize;
                                transition: all 0.2s ease;
                                display: flex;
                                flex-direction: column;
                                gap: 10px;
                                align-items: center;
                            " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 15px rgba(74, 158, 255, 0.3)';" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='';">
                                ${result.preview_url ? `
                                    <img src="${result.preview_url}" style="
                                        width: 100%;
                                        height: 150px;
                                        object-fit: cover;
                                        border-radius: 8px;
                                        border: 1px solid rgba(135, 206, 235, 0.2);
                                    " onerror="this.style.display='none'">
                                ` : ''}
                                <div style="text-align: center; width: 100%;">
                                    <div style="font-size: 1.1em; margin-bottom: 4px;">${result.source}</div>
                                    ${result.width && result.height ? `
                                        <div style="font-size: 0.85em; color: #87ceeb;">${result.width}×${result.height}</div>
                                    ` : ''}
                                    ${result.file_size ? `
                                        <div style="font-size: 0.8em; color: #b0b0b0; margin-top: 2px;">
                                            ${formatFileSize(result.file_size)}
                                        </div>
                                    ` : ''}
                                </div>
                            </button>
                            ${sourceInfo && sourceInfo.url ? `
                                <a href="${sourceInfo.url}" target="_blank" rel="noopener" style="
                                    padding: 6px 12px;
                                    background: rgba(74, 158, 255, 0.2);
                                    border: 1px solid rgba(135, 206, 235, 0.3);
                                    color: #87ceeb;
                                    text-decoration: none;
                                    border-radius: 8px;
                                    font-size: 0.85em;
                                    font-weight: 600;
                                    text-align: center;
                                    transition: all 0.2s ease;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    gap: 5px;
                                " onmouseover="this.style.background='rgba(74, 158, 255, 0.3)'; this.style.transform='translateY(-2px)';" onmouseout="this.style.background='rgba(74, 158, 255, 0.2)'; this.style.transform='translateY(0)';">
                                    <span>🔗</span>
                                    <span>View on ${result.source}</span>
                                </a>
                            ` : ''}
                        </div>
                    `}).join('')}
                </div>
            </div>
            
            <div id="metadataPreview">
                ${renderMetadataPreview(primaryResult, 0)}
            </div>
            
            <div style="
                background: rgba(30, 30, 45, 0.5);
                border: 1px solid rgba(135, 206, 235, 0.2);
                border-radius: 12px;
                padding: 20px;
            ">
                <h3 style="margin: 0 0 15px 0; color: #87ceeb; font-size: 1.1em;">Apply Options</h3>
                
                <label style="
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    cursor: pointer;
                    padding: 12px;
                    background: rgba(40, 40, 60, 0.5);
                    border-radius: 8px;
                    margin-bottom: 15px;
                ">
                    <input type="checkbox" id="downloadImage" style="
                        width: 20px;
                        height: 20px;
                        cursor: pointer;
                    ">
                    <div>
                        <div style="color: #e8e8e8; font-weight: 600;">Download Higher Quality Image</div>
                        <div style="color: #b0b0b0; font-size: 0.85em; margin-top: 4px;">
                            Replace current image file with booru source
                        </div>
                    </div>
                </label>
                
                <div style="display: flex; gap: 10px;">
                    <button onclick="applySauceNaoMetadata()" style="
                        flex: 1;
                        background: linear-gradient(135deg, #4a9e6f 0%, #358a5f 100%);
                        border: none;
                        color: #fff;
                        padding: 12px 24px;
                        border-radius: 10px;
                        cursor: pointer;
                        font-weight: 600;
                        font-size: 1em;
                        box-shadow: 0 4px 15px rgba(74, 158, 111, 0.3);
                        transition: all 0.3s ease;
                    " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 6px 20px rgba(74, 158, 111, 0.4)';" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 15px rgba(74, 158, 111, 0.3)';">
                        ✓ Apply Metadata
                    </button>
                    <button onclick="closeSauceNaoModal()" style="
                        background: rgba(74, 74, 74, 0.5);
                        border: 1px solid rgba(135, 206, 235, 0.3);
                        color: #e8e8e8;
                        padding: 12px 24px;
                        border-radius: 10px;
                        cursor: pointer;
                        font-weight: 600;
                        transition: all 0.3s ease;
                    ">Cancel</button>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('saucenaoContent').innerHTML = html;
    
    // Store metadata results for later use
    window.currentMetadataResults = validResults;
    window.selectedMetadataIdx = 0;
}

function renderMetadataPreview(result, idx) {
    const tags = result.tags || {};
    
    return `
        <div style="...">
            <h3 style="...">Metadata Preview</h3>
            
            ${result.preview_url ? `
                <div style="margin-bottom: 15px; text-align: center;">
                    <img src="${result.preview_url}" style="
                        max-width: 300px;
                        max-height: 300px;
                        border-radius: 8px;
                        border: 1px solid rgba(135, 206, 235, 0.3);
                    " onerror="this.style.display='none';">
                </div>
            ` : ''}
            
            ${result.image_url ? `
                <div style="margin-bottom: 15px;">
                    <a href="${result.image_url}" target="_blank" style="
                        color: #87ceeb;
                        text-decoration: none;
                        font-weight: 600;
                        display: inline-flex;
                        align-items: center;
                        gap: 5px;
                    ">
                        🔗 View Full Image
                    </a>
                </div>
            ` : ''}
            
            ${renderTagCategory('Character', tags.character)}
            ${renderTagCategory('Copyright', tags.copyright)}
            ${renderTagCategory('Artist', tags.artist)}
            ${renderTagCategory('Meta', tags.meta)}
            ${renderTagCategory('General', tags.general, true)}
        </div>
    `;
}

function renderTagCategory(name, tagsString, expandable = false) {
    if (!tagsString || tagsString.trim() === '') return '';
    
    const tags = tagsString.split(' ').filter(t => t);
    const displayTags = expandable && tags.length > 20 ? tags.slice(0, 20) : tags;
    const hasMore = expandable && tags.length > 20;
    
    return `
        <div style="margin-bottom: 15px;">
            <div style="
                color: #87ceeb;
                font-weight: 600;
                font-size: 0.9em;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 8px;
                padding-bottom: 5px;
                border-bottom: 1px solid rgba(135, 206, 235, 0.2);
            ">${name} (${tags.length})</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                ${displayTags.map(tag => `
                    <span style="
                        background: rgba(74, 158, 255, 0.15);
                        border: 1px solid rgba(135, 206, 235, 0.3);
                        padding: 4px 10px;
                        border-radius: 12px;
                        color: #e8e8e8;
                        font-size: 0.85em;
                        font-weight: 500;
                    ">${tag}</span>
                `).join('')}
                ${hasMore ? `<span style="color: #87ceeb; font-size: 0.85em; padding: 4px;">+${tags.length - 20} more</span>` : ''}
            </div>
        </div>
    `;
}

function selectMetadataSource(idx) {
    window.selectedMetadataIdx = idx;
    
    // Update button styles
    const results = window.currentMetadataResults;
    results.forEach((_, i) => {
        const btn = document.getElementById(`sourceBtn${i}`);
        if (btn) {
            if (i === idx) {
                btn.style.background = 'rgba(74, 158, 255, 0.3)';
                btn.style.borderColor = 'rgba(135, 206, 235, 0.5)';
            } else {
                btn.style.background = 'rgba(74, 74, 74, 0.5)';
                btn.style.borderColor = 'rgba(135, 206, 235, 0.2)';
            }
        }
    });
    
    // Update preview
    document.getElementById('metadataPreview').innerHTML = renderMetadataPreview(results[idx], idx);
}

async function applySauceNaoMetadata() {
    const selectedIdx = window.selectedMetadataIdx || 0;
    const selectedMetadata = window.currentMetadataResults[selectedIdx];
    const downloadImage = document.getElementById('downloadImage').checked;
    const filepath = document.getElementById('imageFilepath').value;
    
    // Get the source info
    const sourceInfo = selectedResult.sources.find(s => s.type === selectedMetadata.source);
    
    // Show loading overlay
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.8);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10001;
        animation: fadeIn 0.3s ease-out;
    `;
    overlay.innerHTML = `
        <div style="
            color: white;
            font-size: 1.2em;
            font-weight: 600;
            padding: 30px 50px;
            background: linear-gradient(135deg, rgba(30, 30, 45, 0.95) 0%, rgba(40, 40, 60, 0.95) 100%);
            border-radius: 16px;
            box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5);
            text-align: center;
        ">
            <div style="font-size: 2em; margin-bottom: 15px;">⚙️</div>
            <div id="applyStatus">Applying metadata...</div>
            ${downloadImage ? '<div style="font-size: 0.9em; color: #87ceeb; margin-top: 10px;" id="downloadStatus">Preparing download...</div>' : ''}
        </div>
    `;
    document.body.appendChild(overlay);
    
    // Client-side timeout (90 seconds)
    const timeoutId = setTimeout(() => {
        overlay.remove();
        showNotification('Operation timed out - check Flask console for details', 'error');
    }, 90000);
    
    try {
        if (downloadImage) {
            const statusEl = document.getElementById('downloadStatus');
            if (statusEl) statusEl.textContent = 'Downloading image...';
        }
        
        const response = await fetch('/api/saucenao/apply', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                filepath: filepath,
                source: selectedMetadata.source,
                post_id: sourceInfo.post_id,
                tags: selectedMetadata.tags,
                download_image: downloadImage,
                image_url: selectedMetadata.image_url,
                secret: SYSTEM_SECRET
            })
        });
        
        clearTimeout(timeoutId);
        
        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Non-JSON response from apply:', text);
            throw new Error('Server returned non-JSON response. Check console for details.');
        }
        
        const data = await response.json();
        
        if (data.error === 'Unauthorized') {
            localStorage.removeItem('system_secret');
            SYSTEM_SECRET = null;
            overlay.remove();
            showNotification('Invalid system secret', 'error');
            closeSauceNaoModal();
            return;
        }
        
        if (data.status === 'success') {
            document.getElementById('applyStatus').textContent = 'Success!';
            if (downloadImage && document.getElementById('downloadStatus')) {
                document.getElementById('downloadStatus').textContent = '✓ Image downloaded';
            }
            
            setTimeout(() => {
                // Redirect to new URL if filepath changed, otherwise reload
                if (data.redirect_url) {
                    window.location.href = data.redirect_url;
                } else {
                    window.location.reload();
                }
            }, 1000);
        } else {
            throw new Error(data.error || 'Unknown error');
        }
        
    } catch (error) {
        clearTimeout(timeoutId);
        overlay.remove();
        console.error('Apply error:', error);
        showNotification('Error: ' + error.message, 'error');
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 100px;
        right: 30px;
        padding: 15px 25px;
        background: ${type === 'error' ? 'linear-gradient(135deg, #ff6b6b 0%, #c92a2a 100%)' : 
                     type === 'success' ? 'linear-gradient(135deg, #51cf66 0%, #37b24d 100%)' :
                     'linear-gradient(135deg, #4a9eff 0%, #357abd 100%)'};
        color: white;
        border-radius: 10px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        z-index: 10002;
        font-weight: 600;
        max-width: 400px;
        animation: slideInRight 0.3s ease-out;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 4000);
}