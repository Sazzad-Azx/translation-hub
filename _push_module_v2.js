
// ============================================================
// PUSH MODULE – Deployment Control Panel
// ============================================================
// Flow: All articles visible → select languages → statuses appear
//       → inline push button per (article × language) cell

function initPushSection() {
    if (state.push.loaded) return;
    state.push.loaded = true;
    pushPopulateLanguagePanel();
    pushSetupEventListeners();
    pushLoadArticles(); // Load all article titles immediately
}

// ---------------------------------------------------------------------------
// Populate language checkboxes in the dropdown panel
// ---------------------------------------------------------------------------
function pushPopulateLanguagePanel() {
    const list = document.getElementById('push-lang-panel-list');
    if (!list) return;
    const langs = window.SUPPORTED_LOCALES || {};
    list.innerHTML = '';
    Object.entries(langs).sort((a, b) => a[1].localeCompare(b[1])).forEach(([code, name]) => {
        const lbl = document.createElement('label');
        lbl.className = 'push-lang-check-item';
        lbl.innerHTML = `<input type="checkbox" value="${code}" class="push-lang-cb"> <span>${name} <span style="color:#94a3b8;font-size:11px;">(${code.toUpperCase()})</span></span>`;
        list.appendChild(lbl);
    });
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------
function pushSetupEventListeners() {
    // Lang toggle button
    const toggleBtn = document.getElementById('push-lang-toggle');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            pushToggleLangPanel();
        });
    }

    // Close panel on outside click
    document.addEventListener('click', (e) => {
        if (state.push.langPanelOpen) {
            const sel = document.getElementById('push-lang-selector');
            if (sel && !sel.contains(e.target)) pushCloseLangPanel();
        }
    });

    // Select all checkbox
    const allCb = document.getElementById('push-lang-all');
    if (allCb) {
        allCb.addEventListener('change', () => {
            document.querySelectorAll('.push-lang-cb').forEach(cb => {
                cb.checked = allCb.checked;
            });
            pushSyncSelectAll();
        });
    }

    // Individual lang checkboxes → sync "select all"
    document.getElementById('push-lang-panel-list')?.addEventListener('change', () => {
        pushSyncSelectAll();
    });

    // Apply button
    document.getElementById('push-lang-apply')?.addEventListener('click', () => {
        pushApplyLanguages();
    });

    // Clear button
    document.getElementById('push-lang-clear-btn')?.addEventListener('click', () => {
        document.querySelectorAll('.push-lang-cb').forEach(cb => cb.checked = false);
        const allCb = document.getElementById('push-lang-all');
        if (allCb) allCb.checked = false;
        pushApplyLanguages();
    });

    // Refresh
    document.getElementById('push-refresh-btn')?.addEventListener('click', () => {
        pushLoadArticles();
    });

    // Search
    const searchInput = document.getElementById('push-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(state.push.searchTimeout);
            state.push.searchTimeout = setTimeout(() => {
                state.push.search = searchInput.value.trim();
                state.push.page = 1;
                pushLoadArticles();
            }, 350);
        });
    }

    // Select all rows checkbox
    document.getElementById('push-select-all')?.addEventListener('change', (e) => {
        const checked = e.target.checked;
        state.push.articles.forEach(a => {
            if (checked) state.push.selectedIds.add(a.intercom_id);
            else state.push.selectedIds.delete(a.intercom_id);
        });
        document.querySelectorAll('.push-row-cb').forEach(cb => { cb.checked = checked; });
        pushUpdateBulkBar();
    });

    // Bulk push
    document.getElementById('push-bulk-push-btn')?.addEventListener('click', () => {
        pushStartBulkPush();
    });

    // Bulk clear
    document.getElementById('push-bulk-clear-btn')?.addEventListener('click', () => {
        state.push.selectedIds.clear();
        document.querySelectorAll('.push-row-cb').forEach(cb => cb.checked = false);
        const selectAll = document.getElementById('push-select-all');
        if (selectAll) selectAll.checked = false;
        pushUpdateBulkBar();
    });

    // Push All Ready
    document.getElementById('push-all-ready-btn')?.addEventListener('click', () => {
        pushStartAllReady();
    });

    // Pagination
    document.getElementById('push-prev-btn')?.addEventListener('click', () => {
        if (state.push.page > 1) { state.push.page--; pushLoadArticles(); }
    });
    document.getElementById('push-next-btn')?.addEventListener('click', () => {
        const totalPages = Math.ceil(state.push.total / state.push.pageSize);
        if (state.push.page < totalPages) { state.push.page++; pushLoadArticles(); }
    });
    document.getElementById('push-page-size')?.addEventListener('change', (e) => {
        state.push.pageSize = parseInt(e.target.value);
        state.push.page = 1;
        pushLoadArticles();
    });

    // Confirmation modal
    document.getElementById('push-confirm-close')?.addEventListener('click', pushHideConfirm);
    document.getElementById('push-confirm-cancel')?.addEventListener('click', pushHideConfirm);
    document.getElementById('push-confirm-go')?.addEventListener('click', pushExecuteConfirmed);

    // Drawer close
    document.getElementById('push-drawer-close')?.addEventListener('click', pushCloseDrawer);
    document.getElementById('push-drawer-close-btn')?.addEventListener('click', pushCloseDrawer);
    document.getElementById('push-drawer-overlay')?.addEventListener('click', pushCloseDrawer);
    document.getElementById('push-drawer-push-btn')?.addEventListener('click', () => {
        if (state.push.drawerArticleId && state.push.drawerLocale) {
            pushCloseDrawer();
            pushShowConfirm([{iid: state.push.drawerArticleId, locale: state.push.drawerLocale}], 'cell');
        }
    });
}

// ---------------------------------------------------------------------------
// Language panel helpers
// ---------------------------------------------------------------------------
function pushToggleLangPanel() {
    const panel = document.getElementById('push-lang-panel');
    if (!panel) return;
    state.push.langPanelOpen = !state.push.langPanelOpen;
    panel.classList.toggle('hidden', !state.push.langPanelOpen);
}

function pushCloseLangPanel() {
    state.push.langPanelOpen = false;
    document.getElementById('push-lang-panel')?.classList.add('hidden');
}

function pushSyncSelectAll() {
    const cbs = [...document.querySelectorAll('.push-lang-cb')];
    const allCb = document.getElementById('push-lang-all');
    if (!allCb) return;
    const checkedCount = cbs.filter(c => c.checked).length;
    allCb.checked = checkedCount === cbs.length;
    allCb.indeterminate = checkedCount > 0 && checkedCount < cbs.length;
}

function pushApplyLanguages() {
    const selected = [...document.querySelectorAll('.push-lang-cb:checked')].map(c => c.value);
    state.push.locales = selected;
    state.push.page = 1;
    state.push.selectedIds.clear();
    pushCloseLangPanel();
    pushUpdateLangUI();
    pushLoadArticles();
}

function pushUpdateLangUI() {
    const locales = state.push.locales;
    const langs = window.SUPPORTED_LOCALES || {};

    // Toggle button label
    const lbl = document.getElementById('push-lang-toggle-label');
    const btn = document.getElementById('push-lang-toggle');
    if (lbl) {
        lbl.textContent = locales.length === 0
            ? 'Select Languages'
            : locales.length === 1
                ? (langs[locales[0]] || locales[0].toUpperCase())
                : `${locales.length} Languages`;
    }
    if (btn) btn.classList.toggle('has-selection', locales.length > 0);

    // Chips bar
    const chipsBar = document.getElementById('push-lang-chips');
    if (chipsBar) {
        if (locales.length === 0) {
            chipsBar.classList.add('hidden');
            chipsBar.innerHTML = '';
        } else {
            chipsBar.classList.remove('hidden');
            chipsBar.innerHTML = locales.map(code =>
                `<span class="push-lang-chip">${(langs[code] || code).split(' ')[0]} <span style="opacity:.6">(${code.toUpperCase()})</span></span>`
            ).join('');
        }
    }

    // Hint
    const hint = document.getElementById('push-no-lang-hint');
    if (hint) hint.classList.toggle('hidden', locales.length > 0);

    // Push all ready button
    const pushBtn = document.getElementById('push-all-ready-btn');
    if (pushBtn) pushBtn.disabled = locales.length === 0;
}

// ---------------------------------------------------------------------------
// Load articles (multi-locale or just titles if no locale selected)
// ---------------------------------------------------------------------------
function pushLoadArticles() {
    const tbody = document.getElementById('push-table-body');
    if (tbody) {
        const colSpan = 2 + state.push.locales.length;
        tbody.innerHTML = `<tr><td colspan="${Math.max(colSpan, 2)}" class="empty-cell"><i class="fas fa-spinner fa-spin"></i> Loading…</td></tr>`;
    }

    // Update table header first
    pushRenderTableHeader();

    if (state.push.locales.length === 0) {
        // No locale selected — just load article titles
        const params = new URLSearchParams({
            search: state.push.search,
            page: state.push.page,
            page_size: state.push.pageSize,
        });
        fetch(`/api/push/articles?${params}`)
            .then(r => r.json())
            .then(data => {
                if (!data.success) throw new Error(data.error || 'Failed');
                state.push.articles = data.articles || [];
                state.push.total = data.total || 0;
                pushRenderTable();
                pushRenderPagination();
                pushUpdateBulkBar();
            })
            .catch(err => {
                if (tbody) tbody.innerHTML = `<tr><td colspan="2" class="empty-cell" style="color:#dc2626;"><i class="fas fa-exclamation-circle"></i> ${escapeHtml(err.message)}</td></tr>`;
            });
    } else {
        // Locales selected — load multi-locale status matrix
        const params = new URLSearchParams({
            locales: state.push.locales.join(','),
            search: state.push.search,
            page: state.push.page,
            page_size: state.push.pageSize,
        });
        fetch(`/api/push/articles-multi?${params}`)
            .then(r => r.json())
            .then(data => {
                if (!data.success) throw new Error(data.error || 'Failed');
                state.push.articles = data.articles || [];
                state.push.total = data.total || 0;
                pushRenderTable();
                pushRenderPagination();
                pushUpdateBulkBar();
            })
            .catch(err => {
                if (tbody) {
                    const colSpan = 2 + state.push.locales.length;
                    tbody.innerHTML = `<tr><td colspan="${colSpan}" class="empty-cell" style="color:#dc2626;"><i class="fas fa-exclamation-circle"></i> ${escapeHtml(err.message)}</td></tr>`;
                }
            });
    }
}

// ---------------------------------------------------------------------------
// Render dynamic table header (language columns)
// ---------------------------------------------------------------------------
function pushRenderTableHeader() {
    const thead = document.getElementById('push-thead-row');
    if (!thead) return;
    const langs = window.SUPPORTED_LOCALES || {};

    // Keep the first two TH elements (checkbox + title)
    thead.innerHTML = `
        <th class="push-th-check"><input type="checkbox" id="push-select-all" title="Select all" aria-label="Select all"></th>
        <th class="push-th-title">Article Title</th>
        ${state.push.locales.map(code =>
            `<th class="push-th-lang" title="${escapeHtml(langs[code] || code)}">${code.toUpperCase()}</th>`
        ).join('')}
    `;

    // Re-bind select-all after re-render
    document.getElementById('push-select-all')?.addEventListener('change', (e) => {
        const checked = e.target.checked;
        state.push.articles.forEach(a => {
            if (checked) state.push.selectedIds.add(a.intercom_id);
            else state.push.selectedIds.delete(a.intercom_id);
        });
        document.querySelectorAll('.push-row-cb').forEach(cb => { cb.checked = checked; });
        pushUpdateBulkBar();
    });
}

// ---------------------------------------------------------------------------
// Render table rows
// ---------------------------------------------------------------------------
function pushRenderTable() {
    const tbody = document.getElementById('push-table-body');
    if (!tbody) return;

    if (state.push.articles.length === 0) {
        const colSpan = 2 + state.push.locales.length;
        tbody.innerHTML = `<tr><td colspan="${colSpan}" class="empty-cell">No articles found.</td></tr>`;
        return;
    }

    tbody.innerHTML = '';
    const hasLocales = state.push.locales.length > 0;

    state.push.articles.forEach(article => {
        const iid = article.intercom_id;
        const checked = state.push.selectedIds.has(iid);
        const tr = document.createElement('tr');
        tr.dataset.id = iid;

        // Build locale cells
        let localeCells = '';
        if (hasLocales) {
            localeCells = state.push.locales.map(loc => {
                const ld = (article.locale_data || {})[loc] || {};
                const status = ld.status || 'MISSING';
                const reason = ld.reason || '';
                return `<td class="push-td-lang" data-iid="${iid}" data-locale="${loc}">
                    ${pushRenderCell(status, reason, iid, loc)}
                </td>`;
            }).join('');
        }

        tr.innerHTML = `
            <td><input type="checkbox" class="push-row-cb" data-id="${iid}" ${checked ? 'checked' : ''} aria-label="Select article"></td>
            <td><a href="#" class="push-article-link" data-id="${iid}">${escapeHtml(article.title || 'Untitled')}</a></td>
            ${localeCells}
        `;
        tbody.appendChild(tr);
    });

    // Bind checkboxes
    tbody.querySelectorAll('.push-row-cb').forEach(cb => {
        cb.addEventListener('change', () => {
            const id = cb.dataset.id;
            if (cb.checked) state.push.selectedIds.add(id);
            else state.push.selectedIds.delete(id);
            const selectAll = document.getElementById('push-select-all');
            if (selectAll) {
                selectAll.checked = state.push.selectedIds.size === state.push.articles.length;
                selectAll.indeterminate = state.push.selectedIds.size > 0 && state.push.selectedIds.size < state.push.articles.length;
            }
            pushUpdateBulkBar();
        });
    });

    // Bind article title links → drawer
    tbody.querySelectorAll('.push-article-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            pushOpenDrawer(link.dataset.id);
        });
    });

    // Bind cell push buttons
    tbody.querySelectorAll('.push-cell-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const iid = btn.dataset.iid;
            const locale = btn.dataset.locale;
            pushShowConfirm([{iid, locale}], 'cell');
        });
    });
}

// ---------------------------------------------------------------------------
// Render a status badge + optional push button inside a table cell
// ---------------------------------------------------------------------------
function pushRenderCell(status, reason, iid, locale) {
    const badge = pushRenderBadge(status, reason);
    const pushable = (status === 'READY' || status === 'OUTDATED');
    if (pushable) {
        return `<div class="push-cell-wrap">
            ${badge}
            <button class="push-cell-btn" data-iid="${iid}" data-locale="${locale}" title="Push to ${locale.toUpperCase()}">
                <i class="fas fa-cloud-upload-alt"></i> Push
            </button>
        </div>`;
    }
    return `<div class="push-cell-wrap">${badge}</div>`;
}

// ---------------------------------------------------------------------------
// Render a status badge span
// ---------------------------------------------------------------------------
function pushRenderBadge(status, reason) {
    const map = {
        READY:             { cls: 'push-badge-ready',         icon: 'fa-check-circle',       label: 'Ready' },
        LIVE:              { cls: 'push-badge-live',          icon: 'fa-globe',              label: 'Live' },
        OUTDATED:          { cls: 'push-badge-outdated',      icon: 'fa-exclamation-triangle', label: 'Outdated' },
        MISSING:           { cls: 'push-badge-missing',       icon: 'fa-times-circle',       label: 'Missing' },
        FAILED:            { cls: 'push-badge-failed',        icon: 'fa-exclamation-circle', label: 'Failed' },
        PENDING:           { cls: 'push-badge-pending',       icon: 'fa-spinner fa-spin',    label: 'Pushing…' },
        NEEDS_RETRANSLATION: { cls: 'push-badge-retranslation', icon: 'fa-language',         label: 'Re-translate' },
        NOT_SELECTED:      { cls: 'push-badge-nolang',        icon: 'fa-minus',              label: '—' },
    };
    const d = map[status] || map['NOT_SELECTED'];
    return `<span class="push-badge ${d.cls}" title="${escapeHtml(reason || status)}"><i class="fas ${d.icon}"></i> ${d.label}</span>`;
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------
function pushRenderPagination() {
    const totalPages = Math.max(1, Math.ceil(state.push.total / state.push.pageSize));
    const info = document.getElementById('push-page-info');
    if (info) info.textContent = `PAGE ${state.push.page} of ${totalPages}  (${state.push.total} articles)`;
    const prev = document.getElementById('push-prev-btn');
    const next = document.getElementById('push-next-btn');
    if (prev) prev.disabled = state.push.page <= 1;
    if (next) next.disabled = state.push.page >= totalPages;
}

// ---------------------------------------------------------------------------
// Bulk bar
// ---------------------------------------------------------------------------
function pushUpdateBulkBar() {
    const bar = document.getElementById('push-bulk-bar');
    const summary = document.getElementById('push-bulk-summary');
    const n = state.push.selectedIds.size;
    if (!bar) return;
    if (n === 0) {
        bar.classList.add('hidden');
        return;
    }
    bar.classList.remove('hidden');
    if (summary) summary.textContent = `${n} article${n > 1 ? 's' : ''} selected`;
}

// ---------------------------------------------------------------------------
// Push All Ready
// ---------------------------------------------------------------------------
function pushStartAllReady() {
    if (state.push.locales.length === 0) {
        pushShowToast('Select at least one language first.', 'warn');
        return;
    }
    // Collect all READY/OUTDATED pairs across all articles × locales
    const pairs = [];
    state.push.articles.forEach(a => {
        const ld = a.locale_data || {};
        state.push.locales.forEach(loc => {
            const s = (ld[loc] || {}).status;
            if (s === 'READY' || s === 'OUTDATED') pairs.push({iid: a.intercom_id, locale: loc});
        });
    });
    if (pairs.length === 0) {
        pushShowToast('No articles are ready to push.', 'warn');
        return;
    }
    pushShowConfirm(pairs, 'all_ready');
}

// ---------------------------------------------------------------------------
// Bulk push (selected rows × all locales)
// ---------------------------------------------------------------------------
function pushStartBulkPush() {
    if (state.push.locales.length === 0) {
        pushShowToast('Select at least one language first.', 'warn');
        return;
    }
    const pairs = [];
    state.push.selectedIds.forEach(iid => {
        const article = state.push.articles.find(a => a.intercom_id === iid);
        if (!article) return;
        const ld = article.locale_data || {};
        state.push.locales.forEach(loc => {
            const s = (ld[loc] || {}).status;
            if (s === 'READY' || s === 'OUTDATED') pairs.push({iid, locale: loc});
        });
    });
    if (pairs.length === 0) {
        pushShowToast('No ready articles in the selection.', 'warn');
        return;
    }
    pushShowConfirm(pairs, 'bulk');
}

// ---------------------------------------------------------------------------
// Confirmation modal
// ---------------------------------------------------------------------------
function pushShowConfirm(pairs, action) {
    state.push.confirmPairs = pairs;
    state.push.confirmAction = action;

    const body = document.getElementById('push-confirm-body');
    if (body) {
        // Group by locale
        const byLocale = {};
        pairs.forEach(({locale}) => { byLocale[locale] = (byLocale[locale] || 0) + 1; });
        const langs = window.SUPPORTED_LOCALES || {};
        const rows = Object.entries(byLocale).map(([loc, n]) =>
            `<li><strong>${langs[loc] || loc.toUpperCase()}</strong>: ${n} article${n > 1 ? 's' : ''}</li>`
        ).join('');

        body.innerHTML = `
            <p>You are about to push <strong>${pairs.length}</strong> article-language pair${pairs.length > 1 ? 's' : ''} to the live platform:</p>
            <ul style="margin:10px 0 10px 18px;">${rows}</ul>
            <p style="color:#64748b;font-size:12px;">Only Ready and Outdated items will be pushed. Missing or failed translations are excluded.</p>
        `;
    }
    document.getElementById('push-confirm-overlay')?.classList.remove('hidden');
}

function pushHideConfirm() {
    document.getElementById('push-confirm-overlay')?.classList.add('hidden');
    state.push.confirmPairs = [];
    state.push.confirmAction = null;
}

async function pushExecuteConfirmed() {
    const pairs = state.push.confirmPairs;
    if (!pairs || pairs.length === 0) { pushHideConfirm(); return; }
    pushHideConfirm();

    let ok = 0, fail = 0;
    for (const {iid, locale} of pairs) {
        pushSetCellPending(iid, locale);
        try {
            const res = await fetch('/api/push/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({intercom_id: iid, locale}),
            });
            const data = await res.json();
            if (data.success) {
                pushSetCellStatus(iid, locale, 'LIVE', 'Published successfully');
                ok++;
            } else {
                pushSetCellStatus(iid, locale, 'FAILED', data.error || 'Push failed');
                fail++;
            }
        } catch (e) {
            pushSetCellStatus(iid, locale, 'FAILED', e.message);
            fail++;
        }
    }

    const msg = fail === 0
        ? `✓ ${ok} push${ok > 1 ? 'es' : ''} completed successfully.`
        : `${ok} succeeded, ${fail} failed.`;
    pushShowToast(msg, fail === 0 ? 'success' : 'warn');
}

// ---------------------------------------------------------------------------
// Cell state helpers (update individual cells without re-rendering)
// ---------------------------------------------------------------------------
function pushSetCellPending(iid, locale) {
    const cell = document.querySelector(`.push-td-lang[data-iid="${iid}"][data-locale="${locale}"]`);
    if (!cell) return;
    cell.innerHTML = `<div class="push-cell-wrap">${pushRenderBadge('PENDING', 'Pushing…')}</div>`;
}

function pushSetCellStatus(iid, locale, status, reason) {
    const cell = document.querySelector(`.push-td-lang[data-iid="${iid}"][data-locale="${locale}"]`);
    if (!cell) return;
    cell.innerHTML = pushRenderCell(status, reason, iid, locale);
    // Re-bind push button if READY/OUTDATED
    cell.querySelectorAll('.push-cell-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            pushShowConfirm([{iid: btn.dataset.iid, locale: btn.dataset.locale}], 'cell');
        });
    });

    // Also update in-memory article data
    const article = state.push.articles.find(a => a.intercom_id === iid);
    if (article) {
        if (!article.locale_data) article.locale_data = {};
        if (!article.locale_data[locale]) article.locale_data[locale] = {};
        article.locale_data[locale].status = status;
        article.locale_data[locale].reason = reason;
    }
}

// ---------------------------------------------------------------------------
// Drawer (preview)
// ---------------------------------------------------------------------------
function pushOpenDrawer(iid) {
    const article = state.push.articles.find(a => a.intercom_id === iid);
    if (!article) return;

    state.push.drawerOpen = true;
    state.push.drawerArticleId = iid;
    // Default to first selected locale
    state.push.drawerLocale = state.push.locales[0] || null;

    const title = document.getElementById('push-drawer-title');
    if (title) title.textContent = article.title || 'Article Preview';

    // Build language tabs
    pushRenderDrawerTabs();

    // Load content
    pushLoadDrawerContent(iid, state.push.drawerLocale);

    document.getElementById('push-drawer')?.classList.remove('hidden');
    document.getElementById('push-drawer-overlay')?.classList.remove('hidden');
}

function pushRenderDrawerTabs() {
    const tabsEl = document.getElementById('push-drawer-lang-tabs');
    if (!tabsEl) return;
    if (state.push.locales.length === 0) {
        tabsEl.innerHTML = '';
        return;
    }
    const langs = window.SUPPORTED_LOCALES || {};
    tabsEl.innerHTML = state.push.locales.map(loc =>
        `<button class="push-drawer-lang-tab ${loc === state.push.drawerLocale ? 'active' : ''}" data-locale="${loc}">
            ${loc.toUpperCase()}
        </button>`
    ).join('');
    tabsEl.querySelectorAll('.push-drawer-lang-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            state.push.drawerLocale = tab.dataset.locale;
            tabsEl.querySelectorAll('.push-drawer-lang-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            pushLoadDrawerContent(state.push.drawerArticleId, state.push.drawerLocale);
        });
    });
}

function pushLoadDrawerContent(iid, locale) {
    const body = document.getElementById('push-drawer-body');
    if (!body) return;
    body.innerHTML = '<div style="text-align:center;padding:40px;"><i class="fas fa-spinner fa-spin"></i> Loading preview…</div>';

    const pushBtn = document.getElementById('push-drawer-push-btn');

    const params = new URLSearchParams({intercom_id: iid});
    if (locale) params.set('locale', locale);

    fetch(`/api/push/preview?${params}`)
        .then(r => r.json())
        .then(data => {
            if (!data.success) throw new Error(data.error || 'Failed to load preview');
            const p = data.preview || {};
            const langs = window.SUPPORTED_LOCALES || {};

            const statusHtml = locale && p.push_status
                ? `<div style="margin-bottom:14px;">${pushRenderBadge(p.push_status, p.reason)} <span style="font-size:12px;color:#64748b;margin-left:6px;">${escapeHtml(p.reason || '')}</span></div>`
                : '';

            const metaHtml = `
                <div class="push-preview-meta">
                    <div class="push-meta-item"><span>Source Updated</span><strong>${escapeHtml(p.source_updated_relative || '—')}</strong></div>
                    <div class="push-meta-item"><span>Translated</span><strong>${escapeHtml(p.translated_relative || '—')}</strong></div>
                    <div class="push-meta-item"><span>Last Pushed</span><strong>${escapeHtml(p.pushed_relative || '—')}</strong></div>
                    <div class="push-meta-item"><span>Language</span><strong>${locale ? (langs[locale] || locale.toUpperCase()) : 'Source'}</strong></div>
                </div>`;

            const outdatedBanner = p.push_status === 'OUTDATED' || p.push_status === 'NEEDS_RETRANSLATION'
                ? `<div class="push-outdated-banner"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(p.reason || 'Content may be outdated')}</div>`
                : '';

            const srcTitle = p.source_title ? `<div style="font-weight:700;font-size:15px;margin-bottom:8px;">${escapeHtml(p.source_title)}</div>` : '';
            const srcBody = p.source_body_html
                ? `<div class="push-preview-content">${p.source_body_html}</div>`
                : `<div class="push-preview-content" style="color:#94a3b8;font-style:italic;">No source content</div>`;

            const transSection = locale ? (() => {
                const transTitle = p.translated_title ? `<div style="font-weight:700;font-size:15px;margin-bottom:8px;">${escapeHtml(p.translated_title)}</div>` : '';
                const transBody = p.translated_body_html
                    ? `<div class="push-preview-content">${p.translated_body_html}</div>`
                    : `<div class="push-preview-content" style="color:#94a3b8;font-style:italic;">No translation yet</div>`;
                return `
                    <div class="push-preview-section">
                        <h4><i class="fas fa-language"></i> ${langs[locale] || locale.toUpperCase()} Translation</h4>
                        ${transTitle}${transBody}
                    </div>`;
            })() : '';

            body.innerHTML = `
                ${statusHtml}
                ${outdatedBanner}
                ${metaHtml}
                <div class="push-preview-section">
                    <h4><i class="fas fa-file-alt"></i> Original (English)</h4>
                    ${srcTitle}${srcBody}
                </div>
                ${transSection}
            `;

            // Update push button visibility
            if (pushBtn) {
                const canPush = locale && (p.push_status === 'READY' || p.push_status === 'OUTDATED');
                pushBtn.classList.toggle('hidden', !canPush);
            }
        })
        .catch(err => {
            body.innerHTML = `<div style="color:#dc2626;padding:20px;"><i class="fas fa-exclamation-circle"></i> ${escapeHtml(err.message)}</div>`;
            if (pushBtn) pushBtn.classList.add('hidden');
        });
}

function pushCloseDrawer() {
    state.push.drawerOpen = false;
    state.push.drawerArticleId = null;
    state.push.drawerLocale = null;
    document.getElementById('push-drawer')?.classList.add('hidden');
    document.getElementById('push-drawer-overlay')?.classList.add('hidden');
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------
function pushShowToast(msg, type = 'info') {
    const toast = document.getElementById('push-toast');
    if (!toast) return;
    const styles = {
        success: { bg: '#f0fdf4', color: '#065f46', icon: 'fa-check-circle' },
        warn:    { bg: '#fffbeb', color: '#92400e', icon: 'fa-exclamation-triangle' },
        error:   { bg: '#fef2f2', color: '#991b1b', icon: 'fa-times-circle' },
        info:    { bg: '#eff6ff', color: '#1e40af', icon: 'fa-info-circle' },
    };
    const s = styles[type] || styles.info;
    toast.classList.remove('hidden');
    toast.style.background = s.bg;
    toast.style.color = s.color;
    toast.innerHTML = `<i class="fas ${s.icon}"></i> ${escapeHtml(msg)}`;
    toast.style.opacity = '1';
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { toast.style.opacity = '0'; }, 5000);
}
