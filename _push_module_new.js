
// ============================================================
// PUSH MODULE – Deployment Control Panel
// ============================================================
// Flow: Articles load immediately → Select language → Push

function initPushSection() {
    state.push.loaded = true;
    pushPopulateLanguages();
    pushSetupEventListeners();
    pushLoadArticles(); // Load articles immediately
}

function pushPopulateLanguages() {
    const sel = document.getElementById('push-lang-select');
    if (!sel) return;
    let html = '<option value="">— Select Language —</option>';
    for (const [loc, name] of Object.entries(TARGET_LANGUAGES)) {
        html += `<option value="${loc}">${escapeHtml(name)} (${loc})</option>`;
    }
    sel.innerHTML = html;
}

function pushSetupEventListeners() {
    // Language selector – reload with status info
    const langSel = document.getElementById('push-lang-select');
    if (langSel) {
        langSel.addEventListener('change', () => {
            state.push.locale = langSel.value;
            state.push.page = 1;
            state.push.selectedIds.clear();
            state.push.statusFilter = '';
            const statusFilter = document.getElementById('push-status-filter');
            if (statusFilter) statusFilter.value = '';
            const statsBar = document.getElementById('push-stats-bar');
            const pushAllBtn = document.getElementById('push-all-ready-btn');
            if (state.push.locale) {
                if (statsBar) statsBar.classList.remove('hidden');
                if (pushAllBtn) { pushAllBtn.disabled = false; pushAllBtn.title = ''; }
            } else {
                if (statsBar) statsBar.classList.add('hidden');
                if (pushAllBtn) { pushAllBtn.disabled = true; pushAllBtn.title = 'Select a language first'; }
            }
            pushLoadArticles();
        });
    }

    // Refresh
    const refreshBtn = document.getElementById('push-refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => pushLoadArticles());
    }

    // Search (debounced)
    const searchInput = document.getElementById('push-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(state.push.searchTimeout);
            state.push.searchTimeout = setTimeout(() => {
                state.push.search = searchInput.value.trim();
                state.push.page = 1;
                pushLoadArticles();
            }, 400);
        });
    }

    // Status filter dropdown
    const statusFilter = document.getElementById('push-status-filter');
    if (statusFilter) {
        statusFilter.addEventListener('change', () => {
            state.push.statusFilter = statusFilter.value;
            state.push.page = 1;
            pushLoadArticles();
            pushUpdateStatBadges();
        });
    }

    // Page size
    const pageSize = document.getElementById('push-page-size');
    if (pageSize) {
        pageSize.addEventListener('change', () => {
            state.push.pageSize = parseInt(pageSize.value) || 25;
            state.push.page = 1;
            pushLoadArticles();
        });
    }

    // Select all
    const selectAll = document.getElementById('push-select-all');
    if (selectAll) {
        selectAll.addEventListener('change', () => {
            const checked = selectAll.checked;
            state.push.articles.forEach(a => {
                if (checked) state.push.selectedIds.add(a.intercom_id);
                else state.push.selectedIds.delete(a.intercom_id);
            });
            pushRenderTable();
            pushUpdateBulkBar();
        });
    }

    // Pagination
    const prevBtn = document.getElementById('push-prev-btn');
    const nextBtn = document.getElementById('push-next-btn');
    if (prevBtn) prevBtn.addEventListener('click', () => { if (state.push.page > 1) { state.push.page--; pushLoadArticles(); } });
    if (nextBtn) nextBtn.addEventListener('click', () => {
        const maxPage = Math.ceil(state.push.total / state.push.pageSize) || 1;
        if (state.push.page < maxPage) { state.push.page++; pushLoadArticles(); }
    });

    // Stat badge click handlers (filters)
    document.querySelectorAll('.push-stat-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const filter = chip.dataset.filter;
            if (filter !== undefined && state.push.locale) {
                state.push.statusFilter = filter;
                if (statusFilter) statusFilter.value = filter;
                state.push.page = 1;
                pushLoadArticles();
                pushUpdateStatBadges();
            }
        });
    });

    // Push All Ready
    const pushAllReadyBtn = document.getElementById('push-all-ready-btn');
    if (pushAllReadyBtn) {
        pushAllReadyBtn.addEventListener('click', () => {
            if (!state.push.locale) {
                pushShowToast('Please select a target language first.', 'warning');
                return;
            }
            const readyIds = state.push.articles
                .filter(a => a.push_status === 'READY' || a.push_status === 'OUTDATED')
                .map(a => a.intercom_id);
            if (readyIds.length === 0) {
                pushShowToast('No items ready to push on this page.', 'warning');
                return;
            }
            pushShowConfirmation('all_ready', readyIds);
        });
    }

    // Bulk push
    const bulkPushBtn = document.getElementById('push-bulk-push-btn');
    if (bulkPushBtn) {
        bulkPushBtn.addEventListener('click', () => {
            if (!state.push.locale) {
                pushShowToast('Please select a target language first.', 'warning');
                return;
            }
            const selectedIds = Array.from(state.push.selectedIds);
            if (selectedIds.length === 0) return;
            pushShowConfirmation('bulk', selectedIds);
        });
    }

    // Clear selection
    const bulkClearBtn = document.getElementById('push-bulk-clear-btn');
    if (bulkClearBtn) {
        bulkClearBtn.addEventListener('click', () => {
            state.push.selectedIds.clear();
            pushRenderTable();
            pushUpdateBulkBar();
        });
    }

    // Confirmation modal
    document.getElementById('push-confirm-close')?.addEventListener('click', pushCloseConfirm);
    document.getElementById('push-confirm-cancel')?.addEventListener('click', pushCloseConfirm);
    document.getElementById('push-confirm-go')?.addEventListener('click', pushExecuteConfirmed);

    // Drawer
    document.getElementById('push-drawer-close')?.addEventListener('click', pushCloseDrawer);
    document.getElementById('push-drawer-close-btn')?.addEventListener('click', pushCloseDrawer);
    document.getElementById('push-drawer-overlay')?.addEventListener('click', pushCloseDrawer);
    document.getElementById('push-drawer-push-btn')?.addEventListener('click', () => {
        if (state.push.drawerArticleId && state.push.locale) {
            pushExecuteSingle(state.push.drawerArticleId);
        }
    });
}

// --- Load articles ---
async function pushLoadArticles() {
    const tbody = document.getElementById('push-table-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="empty-cell"><i class="fas fa-spinner fa-spin"></i> Loading articles...</td></tr>';

    try {
        const params = new URLSearchParams({
            page: state.push.page,
            page_size: state.push.pageSize,
        });
        if (state.push.locale) params.set('locale', state.push.locale);
        if (state.push.search) params.set('search', state.push.search);
        if (state.push.statusFilter) params.set('status_filter', state.push.statusFilter);

        const resp = await fetch(`/api/push/articles?${params}`);
        const data = await resp.json();

        if (data.success) {
            state.push.articles = data.articles || [];
            state.push.total = data.total || 0;
            state.push.counts = data.counts || {};
            pushRenderTable();
            pushRenderPagination();
            pushUpdateCounts();
            pushUpdateStatBadges();
            pushUpdateBulkBar();
        } else {
            if (tbody) tbody.innerHTML = `<tr><td colspan="4" class="empty-cell" style="color:#dc2626;">${escapeHtml(data.error || 'Failed to load')}</td></tr>`;
        }
    } catch (err) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="4" class="empty-cell" style="color:#dc2626;">Error: ${escapeHtml(err.message)}</td></tr>`;
    }
}

// --- Render table ---
function pushRenderTable() {
    const tbody = document.getElementById('push-table-body');
    if (!tbody) return;

    if (state.push.articles.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">No articles found.</td></tr>';
        return;
    }

    const hasLocale = !!state.push.locale;

    tbody.innerHTML = '';
    state.push.articles.forEach(article => {
        const iid = article.intercom_id;
        const checked = state.push.selectedIds.has(iid);
        const status = article.push_status;
        const tr = document.createElement('tr');
        tr.dataset.id = iid;

        // Build action button based on status
        let actionBtn = '';
        if (!hasLocale) {
            actionBtn = `<button class="push-row-btn push-row-btn-disabled" disabled title="Select a language first"><i class="fas fa-globe"></i> Select Lang</button>`;
        } else if (status === 'READY' || status === 'OUTDATED') {
            actionBtn = `<button class="push-row-btn push-row-btn-ready push-single-btn" data-id="${iid}" title="Push to ${escapeHtml(TARGET_LANGUAGES[state.push.locale] || state.push.locale)}"><i class="fas fa-cloud-upload-alt"></i> Push</button>`;
        } else if (status === 'LIVE') {
            actionBtn = `<button class="push-row-btn push-row-btn-live" disabled title="Already published"><i class="fas fa-check"></i> Live</button>`;
        } else if (status === 'PENDING') {
            actionBtn = `<button class="push-row-btn push-row-btn-pushing" disabled><i class="fas fa-spinner fa-spin"></i> Pushing</button>`;
        } else {
            actionBtn = `<button class="push-row-btn push-row-btn-disabled" disabled title="${escapeHtml(article.reason || '')}"><i class="fas fa-ban"></i> N/A</button>`;
        }

        const statusBadge = pushRenderBadge(status, article.reason);

        tr.innerHTML = `
            <td><input type="checkbox" class="push-row-cb" data-id="${iid}" ${checked ? 'checked' : ''} aria-label="Select ${escapeHtml(article.title)}"></td>
            <td><a href="#" class="push-article-link" data-id="${iid}" title="Click to preview">${escapeHtml(article.title || 'Untitled')}</a></td>
            <td>${statusBadge}</td>
            <td style="text-align:center;">${actionBtn}</td>
        `;

        tbody.appendChild(tr);
    });

    // Bind checkboxes
    tbody.querySelectorAll('.push-row-cb').forEach(cb => {
        cb.addEventListener('change', () => {
            if (cb.checked) state.push.selectedIds.add(cb.dataset.id);
            else state.push.selectedIds.delete(cb.dataset.id);
            pushUpdateBulkBar();
        });
    });

    // Bind article links → open preview drawer
    tbody.querySelectorAll('.push-article-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            if (state.push.locale) {
                pushOpenDrawer(link.dataset.id);
            } else {
                pushShowToast('Select a language to preview translations.', 'info');
            }
        });
    });

    // Bind inline push buttons
    tbody.querySelectorAll('.push-single-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const iid = btn.dataset.id;
            if (iid && state.push.locale) {
                pushExecuteSingle(iid);
            }
        });
    });
}

function pushRenderBadge(status, reason) {
    const map = {
        'READY':               `<span class="push-badge push-badge-ready" title="${escapeHtml(reason || '')}"><i class="fas fa-check-circle"></i> Ready</span>`,
        'LIVE':                `<span class="push-badge push-badge-live" title="${escapeHtml(reason || '')}"><i class="fas fa-globe"></i> Live</span>`,
        'OUTDATED':            `<span class="push-badge push-badge-outdated" title="${escapeHtml(reason || '')}"><i class="fas fa-exclamation-triangle"></i> Outdated</span>`,
        'MISSING':             `<span class="push-badge push-badge-missing" title="${escapeHtml(reason || '')}"><i class="fas fa-times-circle"></i> Missing</span>`,
        'FAILED':              `<span class="push-badge push-badge-failed" title="${escapeHtml(reason || '')}"><i class="fas fa-exclamation-circle"></i> Failed</span>`,
        'PENDING':             `<span class="push-badge push-badge-pending" title="${escapeHtml(reason || '')}"><i class="fas fa-spinner fa-spin"></i> Pending</span>`,
        'NEEDS_RETRANSLATION': `<span class="push-badge push-badge-retranslation" title="${escapeHtml(reason || '')}"><i class="fas fa-redo"></i> Re-translate</span>`,
        'NO_LANG':             `<span class="push-badge push-badge-nolang" title="Select a language to see status"><i class="fas fa-globe"></i> Select Lang</span>`,
    };
    return map[status] || `<span class="push-badge push-badge-nolang" title="${escapeHtml(reason || '')}">${escapeHtml(status)}</span>`;
}

// --- Pagination ---
function pushRenderPagination() {
    const totalPages = Math.max(1, Math.ceil(state.push.total / state.push.pageSize));
    const info = document.getElementById('push-page-info');
    if (info) info.textContent = `Page ${state.push.page} of ${totalPages} (${state.push.total} articles)`;
    const prevBtn = document.getElementById('push-prev-btn');
    const nextBtn = document.getElementById('push-next-btn');
    if (prevBtn) prevBtn.disabled = state.push.page <= 1;
    if (nextBtn) nextBtn.disabled = state.push.page >= totalPages;
}

// --- Counts ---
function pushUpdateCounts() {
    const c = state.push.counts;
    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val ?? 0; };
    setVal('push-stat-total', c.total);
    setVal('push-stat-ready', c.ready);
    setVal('push-stat-live', c.live);
    setVal('push-stat-outdated', c.outdated);
    setVal('push-stat-missing', c.missing);
    setVal('push-stat-failed', (c.failed || 0) + (c.needs_retranslation || 0));
}

function pushUpdateStatBadges() {
    document.querySelectorAll('.push-stat-chip').forEach(chip => {
        chip.classList.remove('push-stat-active');
    });
    const filter = state.push.statusFilter || '';
    document.querySelectorAll('.push-stat-chip').forEach(chip => {
        if ((chip.dataset.filter || '') === filter) {
            chip.classList.add('push-stat-active');
        }
    });
}

// --- Bulk bar ---
function pushUpdateBulkBar() {
    const bar = document.getElementById('push-bulk-bar');
    const summary = document.getElementById('push-bulk-summary');
    const count = state.push.selectedIds.size;

    if (count === 0) {
        if (bar) bar.classList.add('hidden');
        return;
    }
    if (bar) bar.classList.remove('hidden');

    let readyCount = 0;
    let blockedCount = 0;
    state.push.articles.forEach(a => {
        if (state.push.selectedIds.has(a.intercom_id)) {
            if (a.push_status === 'READY' || a.push_status === 'OUTDATED') readyCount++;
            else blockedCount++;
        }
    });

    if (summary) {
        summary.innerHTML = `${count} selected &bull; <span style="color:#059669">${readyCount} pushable</span> &bull; <span style="color:#dc2626">${blockedCount} blocked</span>`;
    }
}

// --- Confirmation Modal ---
function pushShowConfirmation(action, ids) {
    state.push.confirmAction = action;
    state.push.confirmIds = ids;

    const body = document.getElementById('push-confirm-body');
    const langName = TARGET_LANGUAGES[state.push.locale] || state.push.locale;

    let readyIds = [];
    let blockedIds = [];
    for (const id of ids) {
        const article = state.push.articles.find(a => a.intercom_id === id);
        if (article && (article.push_status === 'READY' || article.push_status === 'OUTDATED')) {
            readyIds.push(id);
        } else {
            blockedIds.push(id);
        }
    }

    let html = `<p>You're about to push <strong>${readyIds.length}</strong> article(s) to <strong>${escapeHtml(langName)}</strong>.</p>`;
    if (blockedIds.length > 0) {
        html += `<p style="color:#d97706;"><i class="fas fa-exclamation-triangle"></i> ${blockedIds.length} item(s) are blocked and will be <strong>excluded</strong>.</p>`;
    }
    html += `<p style="font-size:13px;color:var(--text-muted);margin-top:12px;">This will publish the translated content to Intercom. Proceed?</p>`;

    if (body) body.innerHTML = html;
    document.getElementById('push-confirm-overlay')?.classList.remove('hidden');
    state.push.confirmIds = readyIds;
}

function pushCloseConfirm() {
    document.getElementById('push-confirm-overlay')?.classList.add('hidden');
    state.push.confirmAction = null;
    state.push.confirmIds = [];
}

async function pushExecuteConfirmed() {
    const ids = state.push.confirmIds || [];
    pushCloseConfirm();
    if (ids.length === 0) {
        pushShowToast('No pushable items.', 'warning');
        return;
    }
    await pushExecuteBulk(ids);
}

// --- Push execution ---
async function pushExecuteSingle(intercom_id) {
    const row = document.querySelector(`tr[data-id="${intercom_id}"]`);
    const btn = row?.querySelector('.push-row-btn');
    if (btn) {
        btn.disabled = true;
        btn.className = 'push-row-btn push-row-btn-pushing';
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Pushing';
    }
    if (row) row.classList.add('push-row-pending');

    try {
        const resp = await fetch('/api/push/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ intercom_id, locale: state.push.locale }),
        });
        const data = await resp.json();

        if (row) row.classList.remove('push-row-pending');

        if (data.success) {
            if (row) {
                row.classList.add('push-row-success');
                setTimeout(() => row.classList.remove('push-row-success'), 3000);
            }
            pushShowToast('Successfully pushed!', 'success');
            pushCloseDrawer();
            setTimeout(() => pushLoadArticles(), 500);
        } else {
            if (row) {
                row.classList.add('push-row-failed');
                setTimeout(() => row.classList.remove('push-row-failed'), 5000);
            }
            pushShowToast('Push failed: ' + (data.message || data.error || 'Unknown error'), 'error');
            if (btn) {
                btn.disabled = false;
                btn.className = 'push-row-btn push-row-btn-ready push-single-btn';
                btn.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> Push';
            }
        }
    } catch (err) {
        if (row) row.classList.remove('push-row-pending');
        pushShowToast('Push failed: ' + err.message, 'error');
        if (btn) {
            btn.disabled = false;
            btn.className = 'push-row-btn push-row-btn-ready push-single-btn';
            btn.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> Push';
        }
    }
}

async function pushExecuteBulk(ids) {
    ids.forEach(id => {
        const row = document.querySelector(`tr[data-id="${id}"]`);
        if (row) row.classList.add('push-row-pending');
        const btn = row?.querySelector('.push-row-btn');
        if (btn) {
            btn.disabled = true;
            btn.className = 'push-row-btn push-row-btn-pushing';
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
    });

    pushShowToast(`Pushing ${ids.length} article(s)...`, 'info');

    try {
        const resp = await fetch('/api/push/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ intercom_ids: ids, locale: state.push.locale }),
        });
        const data = await resp.json();

        ids.forEach(id => {
            const row = document.querySelector(`tr[data-id="${id}"]`);
            if (row) row.classList.remove('push-row-pending');
        });

        if (data.success) {
            const results = data.results || [];
            results.forEach(r => {
                const row = document.querySelector(`tr[data-id="${r.intercom_id}"]`);
                if (row) {
                    if (r.success) {
                        row.classList.add('push-row-success');
                        setTimeout(() => row.classList.remove('push-row-success'), 5000);
                    } else {
                        row.classList.add('push-row-failed');
                        setTimeout(() => row.classList.remove('push-row-failed'), 5000);
                    }
                }
            });

            const msg = `Push complete: ${data.completed} succeeded, ${data.failed} failed.`;
            pushShowToast(msg, data.failed > 0 ? 'warning' : 'success');

            state.push.selectedIds.clear();
            setTimeout(() => pushLoadArticles(), 1000);
        } else {
            pushShowToast('Bulk push failed: ' + (data.error || 'Unknown'), 'error');
        }
    } catch (err) {
        ids.forEach(id => {
            const row = document.querySelector(`tr[data-id="${id}"]`);
            if (row) row.classList.remove('push-row-pending');
        });
        pushShowToast('Bulk push failed: ' + err.message, 'error');
    }
}

// --- Preview Drawer ---
async function pushOpenDrawer(intercom_id) {
    state.push.drawerArticleId = intercom_id;
    state.push.drawerOpen = true;

    const body = document.getElementById('push-drawer-body');
    const title = document.getElementById('push-drawer-title');
    const pushBtn = document.getElementById('push-drawer-push-btn');

    if (title) title.textContent = 'Loading...';
    if (body) body.innerHTML = '<div style="text-align:center;padding:40px;"><i class="fas fa-spinner fa-spin fa-2x"></i></div>';
    if (pushBtn) pushBtn.disabled = true;

    const overlay = document.getElementById('push-drawer-overlay');
    const drawer = document.getElementById('push-drawer');
    if (overlay) overlay.classList.remove('hidden');
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            if (drawer) drawer.classList.remove('hidden');
        });
    });

    try {
        const resp = await fetch(`/api/push/preview?intercom_id=${intercom_id}&locale=${state.push.locale}`);
        const data = await resp.json();

        if (data.success && data.preview) {
            const p = data.preview;
            const langName = TARGET_LANGUAGES[state.push.locale] || state.push.locale;
            if (title) title.textContent = p.source?.title || 'Article Preview';

            let html = '';

            html += `<div class="push-preview-meta">
                <div class="push-meta-item">Push Status ${pushRenderBadge(p.push_status, p.reason)}</div>
                <div class="push-meta-item">Language <strong>${escapeHtml(langName)}</strong></div>
                <div class="push-meta-item">Source Updated <strong>${p.source?.source_updated_relative || '—'}</strong></div>
                <div class="push-meta-item">Last Pulled <strong>${p.source?.pulled_relative || '—'}</strong></div>
                <div class="push-meta-item">Translated <strong>${p.translation?.translated_relative || '—'}</strong></div>
                <div class="push-meta-item">Last Pushed <strong>${p.translation?.pushed_relative || '—'}</strong></div>
            </div>`;

            if (p.is_outdated) {
                html += `<div class="push-outdated-banner">
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>Translation may be outdated — source was updated after translation.</span>
                </div>`;
            }

            html += `<div class="push-preview-section">
                <h4><i class="fas fa-file-alt"></i> Original (English)</h4>
                <div class="push-preview-content">${p.source?.body_html || '<em>No content</em>'}</div>
            </div>`;

            html += `<div class="push-preview-section">
                <h4><i class="fas fa-language"></i> Translation (${escapeHtml(langName)})</h4>`;
            if (p.translation?.title || p.translation?.body_html) {
                html += `<div class="push-preview-content">
                    <h3>${escapeHtml(p.translation?.title || '')}</h3>
                    ${p.translation?.body_html || '<em>No body</em>'}
                </div>`;
            } else {
                html += `<div class="push-preview-content" style="color:#dc2626;"><em>No translation available for this language.</em></div>`;
            }
            html += `</div>`;

            if (body) body.innerHTML = html;

            if (pushBtn) {
                if (p.push_status === 'READY' || p.push_status === 'OUTDATED') {
                    pushBtn.disabled = false;
                    pushBtn.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> Push This Article';
                } else if (p.push_status === 'LIVE') {
                    pushBtn.disabled = true;
                    pushBtn.innerHTML = '<i class="fas fa-check"></i> Already Live';
                } else if (p.push_status === 'MISSING') {
                    pushBtn.disabled = true;
                    pushBtn.innerHTML = '<i class="fas fa-times"></i> Missing Translation';
                } else {
                    pushBtn.disabled = true;
                    pushBtn.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> Not Pushable';
                }
            }
        } else {
            if (body) body.innerHTML = `<div style="color:#dc2626;padding:20px;">Error: ${escapeHtml(data.error || 'Could not load preview')}</div>`;
        }
    } catch (err) {
        if (body) body.innerHTML = `<div style="color:#dc2626;padding:20px;">Network error: ${escapeHtml(err.message)}</div>`;
    }
}

function pushCloseDrawer() {
    state.push.drawerOpen = false;
    state.push.drawerArticleId = null;
    const overlay = document.getElementById('push-drawer-overlay');
    const drawer = document.getElementById('push-drawer');
    if (drawer) drawer.classList.add('hidden');
    setTimeout(() => {
        if (overlay) overlay.classList.add('hidden');
    }, 350);
}

// --- Toast ---
function pushShowToast(msg, type) {
    let toast = document.getElementById('push-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'push-toast';
        toast.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;padding:12px 20px;border-radius:10px;font-size:14px;font-weight:500;box-shadow:0 4px 12px rgba(0,0,0,0.15);transition:opacity 0.3s;max-width:400px;';
        document.body.appendChild(toast);
    }
    const colors = {
        success: { bg: '#d1fae5', color: '#065f46', icon: 'fa-check-circle' },
        error: { bg: '#fee2e2', color: '#991b1b', icon: 'fa-times-circle' },
        warning: { bg: '#fef3c7', color: '#92400e', icon: 'fa-exclamation-triangle' },
        info: { bg: '#dbeafe', color: '#1e40af', icon: 'fa-info-circle' },
    };
    const style = colors[type] || colors.info;
    toast.style.background = style.bg;
    toast.style.color = style.color;
    toast.innerHTML = `<i class="fas ${style.icon}"></i> ${escapeHtml(msg)}`;
    toast.style.opacity = '1';

    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {
        toast.style.opacity = '0';
    }, 5000);
}
