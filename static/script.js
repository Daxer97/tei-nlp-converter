/**
 * TEI NLP Converter - Production Ready Client-side JavaScript
 * With security enhancements and error handling
 */

// Constants
const MAX_TEXT_LENGTH = 100000;
const POLL_INTERVAL = 2000;
const API_TIMEOUT = 30000;

// State management
let state = {
    currentProcessedId: null,
    currentTaskId: null,
    pollTimer: null,
    historyPage: 0,
    historyLimit: 10
};

// Get CSRF token from the page
// Get CSRF token from cookie instead of input field
function getCSRFToken() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrf_token') {
            return decodeURIComponent(value);
        }
    }
    return '';
}

// Security utilities
const SecurityUtils = {
    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml: function(unsafe) {
        if (unsafe === null || unsafe === undefined) return '';
        return String(unsafe)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },
    
    /**
     * Sanitize user input
     */
    sanitizeInput: function(input) {
        // Remove control characters except newlines and tabs
        return input.replace(/[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]/g, '');
    },
    
    /**
     * Validate file type
     */
    isValidFileType: function(filename) {
        const validExtensions = ['.txt', '.text', '.md', '.markdown'];
        return validExtensions.some(ext => 
            filename.toLowerCase().endsWith(ext)
        );
    }
};

// API utilities
const API = {
    /**
     * Make API request with timeout and error handling
     */
    request: async function(url, options = {}) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), API_TIMEOUT);
        
        // Include CSRF token for non-GET requests
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };
        
        if (options.method && options.method !== 'GET') {
            headers['X-CSRF-Token'] = getCSRFToken();
        }
        
        try {
            const response = await fetch(url, {
                ...options,
                signal: controller.signal,
                headers: headers,
                credentials: 'same-origin'
            });
            
            clearTimeout(timeout);
            
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            clearTimeout(timeout);
            
            if (error.name === 'AbortError') {
                throw new Error('Request timeout');
            }
            throw error;
        }
    },
    
    /**
     * Process text through API
     */
    processText: async function(text, domain, options) {
        return await this.request('/process', {
            method: 'POST',
            body: JSON.stringify({
                text: SecurityUtils.sanitizeInput(text),
                domain: domain,
                options: options
            })
        });
    },
    
    /**
     * Get task status
     */
    getTaskStatus: async function(taskId) {
        return await this.request(`/task/${taskId}`);
    },
    
    /**
     * Get processing history
     */
    getHistory: async function(limit, offset, domain) {
        const params = new URLSearchParams({
            limit: limit,
            offset: offset
        });
        if (domain) params.append('domain', domain);
        
        return await this.request(`/history?${params}`);
    },
    
    /**
     * Download TEI XML
     */
    downloadTEI: function(textId) {
        window.location.href = `/download/${textId}`;
    }
};

// UI utilities
const UI = {
    /**
     * Show status message
     */
    showStatus: function(message, type = 'info') {
        const statusEl = document.getElementById('status-message');
        const textEl = statusEl.querySelector('.status-text');
        
        textEl.textContent = message;
        statusEl.className = `status-message status-${type}`;
        statusEl.style.display = 'block';
        
        // Auto-hide after 5 seconds for non-error messages
        if (type !== 'error') {
            setTimeout(() => this.hideStatus(), 5000);
        }
    },
    
    /**
     * Hide status message
     */
    hideStatus: function() {
        document.getElementById('status-message').style.display = 'none';
    },
    
    /**
     * Show loading state
     */
    showLoading: function(button) {
        button.disabled = true;
        button.querySelector('.btn-text').style.display = 'none';
        button.querySelector('.loading-spinner').style.display = 'inline-block';
    },
    
    /**
     * Hide loading state
     */
    hideLoading: function(button) {
        button.disabled = false;
        button.querySelector('.btn-text').style.display = 'inline';
        button.querySelector('.loading-spinner').style.display = 'none';
    },
    
    /**
     * Update character count
     */
    updateCharCount: function() {
        const input = document.getElementById('text-input');
        const count = document.getElementById('char-count');
        const length = input.value.length;
        
        count.textContent = length.toLocaleString();
        
        if (length > MAX_TEXT_LENGTH) {
            count.style.color = 'var(--danger-color)';
        } else if (length > MAX_TEXT_LENGTH * 0.9) {
            count.style.color = 'var(--warning-color)';
        } else {
            count.style.color = '';
        }
    },
    
    /**
     * Switch tab
     */
    switchTab: function(tabName) {
        // Update buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            const isActive = btn.dataset.tab === tabName;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', isActive);
        });
        
        // Update panes
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.remove('active');
        });
        document.getElementById(`${tabName}-tab`).classList.add('active');
    }
};

// Processing functions
async function processText(event) {
    event.preventDefault();
    
    const textInput = document.getElementById('text-input');
    const domain = document.getElementById('domain').value;
    const button = document.getElementById('process-btn');
    
    // Validation
    const text = textInput.value.trim();
    if (!text) {
        UI.showStatus('Please enter some text to process', 'warning');
        return;
    }
    
    if (text.length > MAX_TEXT_LENGTH) {
        UI.showStatus(`Text exceeds maximum length of ${MAX_TEXT_LENGTH} characters`, 'error');
        return;
    }
    
    // Get options
    const options = {
        include_dependencies: document.getElementById('include-dependencies').checked,
        include_pos: document.getElementById('include-pos').checked,
        include_lemmas: document.getElementById('include-lemma').checked  // ← Change to include_lemmas
    };
    
    UI.showLoading(button);
    
    try {
        const startTime = Date.now();
        const result = await API.processText(text, domain, options);
        
        if (result.task_id) {
            // Background processing
            state.currentTaskId = result.task_id;
            showTaskModal();
            pollTaskStatus(result.task_id);
        } else {
            // Immediate result
            const processingTime = (Date.now() - startTime) / 1000;
            displayResults(result, processingTime);
            UI.showStatus('Text processed successfully', 'success');
        }
        
        // Refresh history
        loadHistory();
        
    } catch (error) {
        console.error('Processing error:', error);
        UI.showStatus(`Error: ${error.message}`, 'error');
    } finally {
        UI.hideLoading(button);
    }
}

function showTaskModal() {
    document.getElementById('task-modal').style.display = 'flex';
}

function hideTaskModal() {
    document.getElementById('task-modal').style.display = 'none';
    if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
    }
}

async function pollTaskStatus(taskId) {
    state.pollTimer = setInterval(async () => {
        try {
            const task = await API.getTaskStatus(taskId);
            
            if (task.status === 'completed') {
                hideTaskModal();
                displayResults(task.result, task.duration);
                UI.showStatus('Processing completed', 'success');
            } else if (task.status === 'failed') {
                hideTaskModal();
                UI.showStatus(`Processing failed: ${task.error}`, 'error');
            }
            
            // Update modal message
            document.getElementById('task-message').textContent = 
                `Status: ${task.status}`;
            
        } catch (error) {
            console.error('Poll error:', error);
        }
    }, POLL_INTERVAL);
}

function displayResults(result, processingTime) {
    // Store current ID
    state.currentProcessedId = result.id;
    
    // Show results section
    document.getElementById('results').style.display = 'block';
    
    // Display processing time
    if (processingTime) {
        document.getElementById('processing-time').textContent = 
            `Processed in ${processingTime.toFixed(2)}s`;
    }
    
    // Display NLP results
    displayNLPResults(result.nlp_results);
    
    // Display TEI XML
    const xmlElement = document.getElementById('tei-xml');
    xmlElement.textContent = result.tei_xml;
    
    // Display visualization
    displayVisualization(result.tei_xml);
    
    // Display statistics
    displayStatistics(result.nlp_results);
    
    // Switch to NLP tab
    UI.switchTab('nlp');
}

function displayNLPResults(nlpResults) {
    const container = document.getElementById('nlp-results');
    let html = '';
    
    // Entities
    if (nlpResults.entities && nlpResults.entities.length > 0) {
        html += '<div class="nlp-section">';
        html += '<h4>Named Entities</h4>';
        html += '<div class="entities">';

        nlpResults.entities.forEach(entity => {
            const entityClass = getEntityClass(entity.label);
            const text = SecurityUtils.escapeHtml(entity.text);
            const label = SecurityUtils.escapeHtml(entity.label);

            // Build tooltip with additional info for domain-specific entities
            let tooltip = label;
            if (entity.confidence) {
                tooltip += ` (${(entity.confidence * 100).toFixed(1)}% confidence)`;
            }
            if (entity.kb_enrichment) {
                tooltip += `\nKB: ${entity.kb_enrichment.kb_id || 'unknown'}`;
                if (entity.kb_enrichment.entity_id) {
                    tooltip += ` - ID: ${entity.kb_enrichment.entity_id}`;
                }
            }

            html += `<span class="entity ${entityClass}" title="${SecurityUtils.escapeHtml(tooltip)}">${text}</span> `;
        });

        html += '</div>';

        // Show KB enrichment details if available
        const enrichedEntities = nlpResults.entities.filter(e => e.kb_enrichment);
        if (enrichedEntities.length > 0) {
            html += '<div class="kb-enrichment">';
            html += '<h5>Knowledge Base Enrichment</h5>';
            html += '<ul class="kb-list">';

            enrichedEntities.slice(0, 5).forEach(entity => {
                const kb = entity.kb_enrichment;
                const text = SecurityUtils.escapeHtml(entity.text);
                const kbId = SecurityUtils.escapeHtml(kb.kb_id || 'unknown');
                const entityId = SecurityUtils.escapeHtml(kb.entity_id || '');
                const definition = kb.definition ? SecurityUtils.escapeHtml(kb.definition.substring(0, 150)) : '';

                html += `<li><strong>${text}</strong> [${kbId}:${entityId}]`;
                if (definition) {
                    html += `<br><small>${definition}${kb.definition && kb.definition.length > 150 ? '...' : ''}</small>`;
                }
                html += '</li>';
            });

            if (enrichedEntities.length > 5) {
                html += `<li class="more-items">... and ${enrichedEntities.length - 5} more enriched entities</li>`;
            }

            html += '</ul></div>';
        }

        html += '</div>';
    }
    
    // Sentences
    if (nlpResults.sentences && nlpResults.sentences.length > 0) {
        html += '<div class="nlp-section">';
        html += '<h4>Sentences</h4>';
        html += '<ol class="sentence-list">';
        
        nlpResults.sentences.forEach(sentence => {
            const text = SecurityUtils.escapeHtml(sentence.text);
            html += `<li>${text}</li>`;
        });
        
        html += '</ol></div>';
    }
    
    // Dependencies
    if (nlpResults.dependencies && nlpResults.dependencies.length > 0) {
        html += '<div class="nlp-section">';
        html += '<h4>Dependencies</h4>';
        html += '<ul class="dependency-list">';
        
        const deps = nlpResults.dependencies.slice(0, 10);
        deps.forEach(dep => {
            const from = SecurityUtils.escapeHtml(dep.from_text);
            const to = SecurityUtils.escapeHtml(dep.to_text);
            const type = SecurityUtils.escapeHtml(dep.dep);
            html += `<li>${from} → ${to} <span class="dep-type">(${type})</span></li>`;
        });
        
        if (nlpResults.dependencies.length > 10) {
            html += `<li class="more-items">... and ${nlpResults.dependencies.length - 10} more</li>`;
        }
        
        html += '</ul></div>';
    }
    
    container.innerHTML = html;
}

function getEntityClass(label) {
    const labelLower = label.toLowerCase();

    // Standard NLP entities
    if (['person', 'per'].includes(labelLower)) return 'entity-person';
    if (['location', 'loc', 'gpe'].includes(labelLower)) return 'entity-place';
    if (['organization', 'org'].includes(labelLower)) return 'entity-org';
    if (['date', 'time'].includes(labelLower)) return 'entity-time';

    // Medical domain entities
    if (['drug', 'chemical', 'medication'].includes(labelLower)) return 'entity-drug';
    if (['disease', 'condition', 'symptom'].includes(labelLower)) return 'entity-disease';
    if (['procedure', 'treatment'].includes(labelLower)) return 'entity-procedure';
    if (['anatomy', 'body_part'].includes(labelLower)) return 'entity-anatomy';
    if (['icd10_code', 'icd9_code', 'cpt_code', 'ndc_code'].includes(labelLower)) return 'entity-code';
    if (['dosage', 'frequency'].includes(labelLower)) return 'entity-measure';

    // Legal domain entities
    if (['statute', 'law', 'regulation'].includes(labelLower)) return 'entity-law';
    if (['court', 'judge', 'attorney'].includes(labelLower)) return 'entity-legal';
    if (['case_citation', 'usc_citation', 'cfr_citation', 'public_law'].includes(labelLower)) return 'entity-citation';

    // Financial domain entities
    if (['ticker_symbol', 'stock'].includes(labelLower)) return 'entity-financial';
    if (['currency_amount', 'money', 'percent'].includes(labelLower)) return 'entity-currency';
    if (['cusip', 'isin'].includes(labelLower)) return 'entity-code';
    if (['fiscal_period'].includes(labelLower)) return 'entity-time';

    return 'entity-misc';
}

function displayVisualization(teiXml) {
    const container = document.getElementById('tei-visual');
    
    try {
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(teiXml, 'text/xml');
        
        if (xmlDoc.querySelector('parsererror')) {
            container.innerHTML = '<p class="error">Failed to parse XML</p>';
            return;
        }
        
        const tree = createTreeView(xmlDoc.documentElement, 0);
        container.innerHTML = tree;
    } catch (error) {
        console.error('Visualization error:', error);
        container.innerHTML = '<p class="error">Failed to create visualization</p>';
    }
}

function createTreeView(node, level, maxDepth = 10) {
    if (level > maxDepth) return '';
    
    if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent.trim();
        if (text) {
            const escaped = SecurityUtils.escapeHtml(text);
            const truncated = escaped.length > 50 ? 
                escaped.substring(0, 50) + '...' : escaped;
            return `<div class="tree-text" style="margin-left: ${level * 20}px">
                "${truncated}"
            </div>`;
        }
        return '';
    }
    
    let html = `<div class="tree-node" style="margin-left: ${level * 20}px">`;
    html += `<span class="tree-tag">&lt;${SecurityUtils.escapeHtml(node.nodeName)}`;
    
    // Add attributes
    if (node.attributes) {
        for (let attr of node.attributes) {
            const name = SecurityUtils.escapeHtml(attr.name);
            const value = SecurityUtils.escapeHtml(attr.value);
            html += ` <span class="tree-attr">${name}="${value}"</span>`;
        }
    }
    html += '&gt;</span>';
    
    // Add children
    let childContent = '';
    for (let child of node.childNodes) {
        childContent += createTreeView(child, level + 1, maxDepth);
    }
    
    if (childContent) {
        html += childContent;
        html += `<span class="tree-tag" style="margin-left: ${level * 20}px">
            &lt;/${SecurityUtils.escapeHtml(node.nodeName)}&gt;</span>`;
    }
    
    html += '</div>';
    
    return html;
}

function displayStatistics(nlpResults) {
    const container = document.getElementById('stats-content');
    
    const stats = {
        'Sentences': nlpResults.sentences ? nlpResults.sentences.length : 0,
        'Tokens': nlpResults.sentences ? 
            nlpResults.sentences.reduce((sum, s) => sum + (s.tokens ? s.tokens.length : 0), 0) : 0,
        'Entities': nlpResults.entities ? nlpResults.entities.length : 0,
        'Dependencies': nlpResults.dependencies ? nlpResults.dependencies.length : 0,
        'Noun Phrases': nlpResults.noun_chunks ? nlpResults.noun_chunks.length : 0
    };
    
    let html = '';
    for (const [label, value] of Object.entries(stats)) {
        html += `
            <div class="stat-card">
                <div class="stat-label">${label}</div>
                <div class="stat-value">${value.toLocaleString()}</div>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    // Validate file type
    if (!SecurityUtils.isValidFileType(file.name)) {
        UI.showStatus('Invalid file type. Please upload a .txt or .md file', 'error');
        event.target.value = '';
        return;
    }
    
    // Validate file size (100KB max)
    if (file.size > 102400) {
        UI.showStatus('File too large. Maximum size is 100KB', 'error');
        event.target.value = '';
        return;
    }
    
    const reader = new FileReader();
    reader.onload = (e) => {
        const content = e.target.result;
        document.getElementById('text-input').value = content;
        UI.updateCharCount();
    };
    reader.onerror = () => {
        UI.showStatus('Failed to read file', 'error');
    };
    reader.readAsText(file);
}

async function loadHistory(page = 0) {
    const domain = document.getElementById('history-filter').value;
    
    try {
        const result = await API.getHistory(
            state.historyLimit,
            page * state.historyLimit,
            domain
        );
        
        displayHistory(result.items);
        displayPagination(result.total, page);
        
        state.historyPage = page;
        
    } catch (error) {
        console.error('Failed to load history:', error);
        document.getElementById('history-list').innerHTML = 
            '<p class="error">Failed to load history</p>';
    }
}

function displayHistory(items) {
    const container = document.getElementById('history-list');
    
    if (items.length === 0) {
        container.innerHTML = '<p class="empty-state">No processing history yet</p>';
        return;
    }
    
    let html = '';
    items.forEach(item => {
        const date = new Date(item.created_at).toLocaleString();
        const text = SecurityUtils.escapeHtml(item.text_preview);
        const domain = SecurityUtils.escapeHtml(item.domain);
        
        html += `
            <div class="history-item" data-id="${item.id}">
                <div class="history-header">
                    <span class="history-domain">${domain}</span>
                    <span class="history-date">${date}</span>
                </div>
                <div class="history-text">${text}</div>
                <div class="history-actions">
                    <button class="btn btn-sm" onclick="loadHistoryItem(${item.id})">
                        Load
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteHistoryItem(${item.id})">
                        Delete
                    </button>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

function displayPagination(total, currentPage) {
    const container = document.getElementById('history-pagination');
    const totalPages = Math.ceil(total / state.historyLimit);
    
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }
    
    let html = '';
    
    // Previous button
    html += `<button class="page-btn" ${currentPage === 0 ? 'disabled' : ''} 
             onclick="loadHistory(${currentPage - 1})">Previous</button>`;
    
    // Page numbers
    for (let i = 0; i < Math.min(totalPages, 5); i++) {
        html += `<button class="page-btn ${i === currentPage ? 'active' : ''}" 
                 onclick="loadHistory(${i})">${i + 1}</button>`;
    }
    
    // Next button
    html += `<button class="page-btn" ${currentPage >= totalPages - 1 ? 'disabled' : ''} 
             onclick="loadHistory(${currentPage + 1})">Next</button>`;
    
    container.innerHTML = html;
}

async function loadHistoryItem(id) {
    try {
        UI.showStatus('Loading item...', 'info');
        
        // Fetch the full item data from the NEW endpoint
        const response = await fetch(`/text/${id}`);
        if (!response.ok) throw new Error('Item not found');
        
        const item = await response.json();
        
        // Display full results using the existing displayResults function
        displayResults({
            id: item.id,
            domain: item.domain,
            nlp_results: item.nlp_results,
            tei_xml: item.tei_xml
        });
        
        UI.showStatus('Item loaded successfully', 'success');
    } catch (error) {
        UI.showStatus(`Failed to load: ${error.message}`, 'error');
    }
}

async function deleteHistoryItem(id) {
    if (!confirm('Are you sure you want to delete this item?')) return;
    
    try {
        // Delete from backend first
        await API.request(`/text/${id}`, { method: 'DELETE' });
        
        // Manually update the DOM
        const itemElement = document.querySelector(`.history-item[data-id="${id}"]`);
        if (itemElement) {
            // Fade out animation
            itemElement.style.transition = 'opacity 0.3s';
            itemElement.style.opacity = '0';
            
            // Remove after animation
            setTimeout(() => {
                itemElement.remove();
                
                // If no items left, show empty state
                const container = document.getElementById('history-list');
                if (container.querySelectorAll('.history-item').length === 0) {
                    container.innerHTML = '<p class="empty-state">No processing history yet</p>';
                }
            }, 300);
        }
        
        UI.showStatus('Item deleted successfully', 'success');
        
    } catch (error) {
        console.error('Delete error:', error);
        UI.showStatus(`Failed to delete: ${error.message}`, 'error');
    }
}

// ============================================
// Classical NLP Processing for Latin/Greek
// ============================================

// Classical NLP state
const classicalState = {
    cacheKey: null,
    processingMode: 'general',
    botanicalTerms: [],
    searchResults: []
};

// Classical API utilities
const ClassicalAPI = {
    /**
     * Process classical text
     */
    processText: async function(text, language, model, title, includeBotanical) {
        const response = await fetch('/api/v2/classical/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRFToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                text: SecurityUtils.sanitizeInput(text),
                language: language,
                model: model || null,
                title: title || 'Classical Text',
                include_botanical: includeBotanical
            })
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        return await response.json();
    },

    /**
     * Search occurrences
     */
    search: async function(cacheKey, query, mode, wordsBefore, wordsAfter, fuzzyThreshold) {
        const params = new URLSearchParams({ cache_key: cacheKey });

        const response = await fetch(`/api/v2/classical/search?${params}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRFToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                query: query,
                mode: mode,
                words_before: parseInt(wordsBefore),
                words_after: parseInt(wordsAfter),
                fuzzy_threshold: parseFloat(fuzzyThreshold)
            })
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        return await response.json();
    },

    /**
     * Export HTML report
     */
    exportHTML: async function(cacheKey, query, mode, wordsBefore, wordsAfter) {
        const params = new URLSearchParams({
            cache_key: cacheKey,
            download: 'true'
        });

        const response = await fetch(`/api/v2/classical/export/html?${params}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRFToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                query: query,
                mode: mode,
                words_before: parseInt(wordsBefore),
                words_after: parseInt(wordsAfter)
            })
        });

        if (!response.ok) {
            throw new Error('Failed to export HTML report');
        }

        // Download the file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `occorrenze_${query}.html`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
    },

    /**
     * Detect language
     */
    detectLanguage: async function(text) {
        const params = new URLSearchParams({ text: text.substring(0, 1000) });

        const response = await fetch(`/api/v2/classical/detect-language?${params}`, {
            headers: { 'X-CSRF-Token': getCSRFToken() },
            credentials: 'same-origin'
        });

        if (!response.ok) {
            throw new Error('Language detection failed');
        }

        return await response.json();
    }
};

// Classical UI functions
const ClassicalUI = {
    /**
     * Toggle between general and classical processing modes
     */
    toggleProcessingMode: function(mode) {
        classicalState.processingMode = mode;

        const generalOptions = document.getElementById('general-options');
        const classicalOptions = document.getElementById('classical-options');
        const occurrenceSearch = document.getElementById('occurrence-search');
        const botanicalResults = document.getElementById('botanical-results');

        if (mode === 'classical') {
            generalOptions.style.display = 'none';
            classicalOptions.style.display = 'block';
        } else {
            generalOptions.style.display = 'block';
            classicalOptions.style.display = 'none';
            occurrenceSearch.style.display = 'none';
            botanicalResults.style.display = 'none';
        }
    },

    /**
     * Display botanical terms
     */
    displayBotanicalTerms: function(terms) {
        const container = document.getElementById('botanical-list');
        const section = document.getElementById('botanical-results');

        if (!terms || terms.length === 0) {
            section.style.display = 'none';
            return;
        }

        section.style.display = 'block';

        let html = '<table class="botanical-table"><thead><tr>';
        html += '<th>Termine</th><th>Lemma</th><th>Nome Scientifico</th>';
        html += '<th>Nome Comune</th><th>Occorrenze</th>';
        html += '</tr></thead><tbody>';

        terms.forEach(term => {
            html += '<tr>';
            html += `<td>${SecurityUtils.escapeHtml(term.text)}</td>`;
            html += `<td>${SecurityUtils.escapeHtml(term.lemma)}</td>`;
            html += `<td><em>${SecurityUtils.escapeHtml(term.scientific_name || '-')}</em></td>`;
            html += `<td>${SecurityUtils.escapeHtml(term.common_name || '-')}</td>`;
            html += `<td>${term.occurrences}</td>`;
            html += '</tr>';
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    },

    /**
     * Display search results
     */
    displaySearchResults: function(response) {
        const container = document.getElementById('search-list');
        const resultsSection = document.getElementById('search-results');
        const totalSpan = document.getElementById('search-total');
        const freqSpan = document.getElementById('search-frequency');

        resultsSection.style.display = 'block';

        totalSpan.textContent = `${response.total_occurrences} occorrenze trovate`;
        freqSpan.textContent = `(${response.statistics.frequency.toFixed(2)}% del testo)`;

        if (response.results.length === 0) {
            container.innerHTML = '<p class="empty-state">Nessuna occorrenza trovata</p>';
            return;
        }

        let html = '';
        response.results.forEach((result, index) => {
            html += `
                <div class="search-result-item">
                    <span class="result-number">${index + 1}</span>
                    <div class="result-context">
                        <span class="context-before">${SecurityUtils.escapeHtml(result.context_before)}</span>
                        <span class="result-word">${SecurityUtils.escapeHtml(result.word_found)}</span>
                        <span class="context-after">${SecurityUtils.escapeHtml(result.context_after)}</span>
                    </div>
                    <div class="result-meta">
                        Riga ${result.line_number}
                        ${result.lemma ? ` | Lemma: ${result.lemma}` : ''}
                        ${result.pos_tag ? ` | POS: ${result.pos_tag}` : ''}
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;

        // Display word cloud
        this.displayWordCloud(response.wordcloud_data);
    },

    /**
     * Display word cloud
     */
    displayWordCloud: function(wordcloudData) {
        const container = document.querySelector('#search-wordcloud .wordcloud');

        if (!wordcloudData || wordcloudData.length === 0) {
            container.innerHTML = '<span>Nessun dato disponibile</span>';
            return;
        }

        const maxCount = Math.max(...wordcloudData.map(w => w.count));

        let html = '';
        wordcloudData.slice(0, 40).forEach(item => {
            const size = 1 + (item.count / maxCount) * 2;
            const hue = 200 + (item.count / maxCount) * 60;

            html += `<span class="wordcloud-word" style="font-size: ${size}em; color: hsl(${hue}, 60%, 45%);">
                ${SecurityUtils.escapeHtml(item.word)}
            </span> `;
        });

        container.innerHTML = html;
    },

    /**
     * Show fuzzy options
     */
    toggleFuzzyOptions: function(mode) {
        const fuzzyOptions = document.getElementById('fuzzy-options');
        fuzzyOptions.style.display = mode === 'fuzzy' ? 'block' : 'none';
    }
};

/**
 * Process classical text
 */
async function processClassicalText(text) {
    const language = document.getElementById('classical-language').value;
    const model = document.getElementById('classical-model').value;
    const includeBotanical = document.getElementById('include-botanical').checked;
    const button = document.getElementById('process-btn');

    try {
        UI.showLoading(button);
        UI.showStatus('Elaborazione testo classico...', 'info');

        const result = await ClassicalAPI.processText(
            text, language, model, 'Classical Text', includeBotanical
        );

        // Store cache key for search
        classicalState.cacheKey = result.metadata.cache_key;
        classicalState.botanicalTerms = result.botanical_terms;

        // Display results
        displayResults({
            tei_xml: result.tei_xml,
            nlp_results: {
                language: result.detected_language,
                model: result.model_used,
                word_count: result.word_count,
                sentence_count: result.sentence_count
            },
            processing_time: result.processing_time_ms / 1000
        });

        // Show botanical terms
        ClassicalUI.displayBotanicalTerms(result.botanical_terms);

        // Show search section
        document.getElementById('occurrence-search').style.display = 'block';

        UI.showStatus(
            `Testo elaborato con ${result.model_used}. Lingua: ${result.detected_language}`,
            'success'
        );

    } catch (error) {
        console.error('Classical processing error:', error);
        UI.showStatus(`Errore: ${error.message}`, 'error');
    } finally {
        UI.hideLoading(button);
    }
}

/**
 * Handle occurrence search
 */
async function handleSearch(event) {
    event.preventDefault();

    const query = document.getElementById('search-query').value.trim();
    if (!query) {
        UI.showStatus('Inserisci un termine da cercare', 'warning');
        return;
    }

    if (!classicalState.cacheKey) {
        UI.showStatus('Prima elabora un testo', 'warning');
        return;
    }

    const mode = document.querySelector('input[name="search-mode"]:checked').value;
    const wordsBefore = document.getElementById('words-before').value;
    const wordsAfter = document.getElementById('words-after').value;
    const fuzzyThreshold = document.getElementById('fuzzy-threshold').value / 100;

    try {
        UI.showStatus('Ricerca in corso...', 'info');

        const results = await ClassicalAPI.search(
            classicalState.cacheKey,
            query,
            mode,
            wordsBefore,
            wordsAfter,
            fuzzyThreshold
        );

        classicalState.searchResults = results;
        ClassicalUI.displaySearchResults(results);

        UI.showStatus(`Trovate ${results.total_occurrences} occorrenze`, 'success');

    } catch (error) {
        console.error('Search error:', error);
        UI.showStatus(`Errore ricerca: ${error.message}`, 'error');
    }
}

/**
 * Export HTML report
 */
async function exportSearchReport() {
    const query = document.getElementById('search-query').value.trim();
    if (!query || !classicalState.cacheKey) {
        UI.showStatus('Esegui prima una ricerca', 'warning');
        return;
    }

    const mode = document.querySelector('input[name="search-mode"]:checked').value;
    const wordsBefore = document.getElementById('words-before').value;
    const wordsAfter = document.getElementById('words-after').value;

    try {
        UI.showStatus('Generazione report HTML...', 'info');

        await ClassicalAPI.exportHTML(
            classicalState.cacheKey,
            query,
            mode,
            wordsBefore,
            wordsAfter
        );

        UI.showStatus('Report HTML scaricato', 'success');

    } catch (error) {
        console.error('Export error:', error);
        UI.showStatus(`Errore export: ${error.message}`, 'error');
    }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    // Load initial data
    loadHistory();
    
    // Setup event listeners
    document.getElementById('process-form').addEventListener('submit', processText);
    document.getElementById('file-input').addEventListener('change', handleFileUpload);
    document.getElementById('text-input').addEventListener('input', UI.updateCharCount);
    document.getElementById('history-filter').addEventListener('change', () => loadHistory(0));
    document.getElementById('refresh-history-btn').addEventListener('click', () => loadHistory(state.historyPage));
    
    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => UI.switchTab(e.target.dataset.tab));
    });
    
    // Download button
    document.getElementById('download-btn').addEventListener('click', () => {
        if (state.currentProcessedId) {
            API.downloadTEI(state.currentProcessedId);
        } else {
            UI.showStatus('No processed text available for download', 'warning');
        }
    });
    
    // Copy XML button
    document.getElementById('copy-xml-btn').addEventListener('click', () => {
        const xml = document.getElementById('tei-xml').textContent;
        navigator.clipboard.writeText(xml).then(() => {
            UI.showStatus('XML copied to clipboard', 'success');
        }).catch(() => {
            UI.showStatus('Failed to copy XML', 'error');
        });
    });
    
    // Cancel task button
    document.getElementById('cancel-task-btn').addEventListener('click', hideTaskModal);
    
    // Close status button
    window.closeStatus = () => UI.hideStatus();
    
    // Initialize char count
    UI.updateCharCount();

    // Classical NLP event listeners
    const processingModeSelect = document.getElementById('processing-mode');
    if (processingModeSelect) {
        processingModeSelect.addEventListener('change', (e) => {
            ClassicalUI.toggleProcessingMode(e.target.value);
        });
    }

    const searchForm = document.getElementById('search-form');
    if (searchForm) {
        searchForm.addEventListener('submit', handleSearch);
    }

    const exportHtmlBtn = document.getElementById('export-html-btn');
    if (exportHtmlBtn) {
        exportHtmlBtn.addEventListener('click', exportSearchReport);
    }

    // Fuzzy threshold slider
    const fuzzyThreshold = document.getElementById('fuzzy-threshold');
    if (fuzzyThreshold) {
        fuzzyThreshold.addEventListener('input', (e) => {
            document.getElementById('fuzzy-value').textContent = e.target.value + '%';
        });
    }

    // Search mode radio buttons
    const searchModeRadios = document.querySelectorAll('input[name="search-mode"]');
    searchModeRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            ClassicalUI.toggleFuzzyOptions(e.target.value);
        });
    });
});

// Override processText for classical mode
const originalProcessText = typeof processText === 'function' ? processText : null;

async function processText(event) {
    event.preventDefault();

    const processingMode = document.getElementById('processing-mode')?.value || 'general';
    const text = document.getElementById('text-input').value.trim();

    if (!text) {
        UI.showStatus('Please enter some text to process', 'warning');
        return;
    }

    if (processingMode === 'classical') {
        await processClassicalText(text);
    } else {
        // Call original general processing
        const domain = document.getElementById('domain').value;
        const button = document.getElementById('process-btn');

        const options = {
            include_dependencies: document.getElementById('include-dependencies')?.checked,
            include_pos: document.getElementById('include-pos')?.checked,
            include_lemma: document.getElementById('include-lemma')?.checked
        };

        try {
            UI.showLoading(button);
            UI.showStatus('Processing text...', 'info');

            const result = await API.processText(text, domain, options);

            if (result.task_id) {
                startPolling(result.task_id);
            } else {
                state.currentProcessedId = result.id;
                displayResults(result);
                UI.showStatus('Processing completed successfully', 'success');
            }
        } catch (error) {
            console.error('Processing error:', error);
            UI.showStatus(`Error: ${error.message}`, 'error');
        } finally {
            UI.hideLoading(button);
        }
    }
}
