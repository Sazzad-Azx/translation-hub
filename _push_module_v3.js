
// ============================================================
// PUSH MODULE – Deployment Control Panel
// ============================================================
// Mirrors the Translate section UX:
//   • All article titles visible immediately
//   • Language picker (dropdown with checkboxes + badge) in action bar
//   • Row checkboxes for article selection
//   • Job counter: selected articles × selected languages = jobs
//   • "Push Selected"  → selected rows × selected langs (READY/OUTDATED)
//   • "Push All Ready" → all rows × selected langs (READY/OUTDATED)
//   • Status cells: badge only (no inline push buttons)

function initPushSection() {
    if (state.push.loaded) return;
    state.push.loaded = true;
    pushPopulateLangDropdown();
    pushSetupEventListeners();
    pushLoadArticles();
}

// ---------------------------------------------------------------------------
// Populate language dropdown (mirrors tr-lang-dropdown-list)
// ---------------------------------------------------------------------------
function pushPopulateLangDropdown() {
    const list = document.getElementById('push-lang-dropdown-list');
    if (!list) return;
    list.innerHTML = '';
    Object.entries(TARGET_LANGUAGES)
        .sort((a, b) => a[1].localeCompare(b[1]))
        .forEach(([code, name]) => {
            const lbl = document.createElement('label');
            lbl.innerHTML = `<input type="checkbox" class="push-lang-cb" value="${code}">
                <span>${name} <span style="color:#94a3b8;font-size:11px;">(${code.toUpperCase()})</span></span>`;
            list.appendChild(lbl);
        });
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------
function pushSetupEventListeners() {
    // Language picker toggle
    document.getElementById('push-lang-picker-btn')?.addEventListener('click', (e) => {
        e.stopPropagation();
        document.getElementById('push-lang-dropdown')?.classList.toggle('hidden');
    });

    // Close dropdown on outside click
    document.addEventListener('click', (e) => {
        const wrap = document.getElementById('push-lang-picker-wrap');
        if (wrap && !wrap.contains(e.target)) {
            document.getElementById('push-lang-dropdown')?.classList.add('hidden');
        }
    });

    // Select All languages
    document.getElementById('push-lang-select-all')?.addEventListener('change', (e) => {
        document.querySelectorAll('.push-lang-cb').forEach(cb => { cb.checked = e.target.checked; });
        pushOnLangChange();
    });

    // Individual language checkboxes
    document.getElementById('push-lang-dropdown-list')?.addEventListener('change', () => {
        pushSyncSelectAllLang();
        pushOnLangChange();
    });

    // Refresh
    document.getElementById('push-refresh-btn')?.addEventListener('click', () => pushLoadArticles());

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

    // Select-all rows (re-bound each render via pushBindTableEvents)
    // Page size
    document.getElementById('push-page-size')?.addEventListener('change', (e) => {
        state.push.pageSize = parseInt(e.target.value);
        state.push.page = 1;
        pushLoadArticles();
    });

    // Pagination
    document.getElementById('push-prev-btn')?.addEventListener('click', () => {
        if (state.push.page > 1) { state.push.page--; pushLoadArticles(); }
    });
    document.getElementById('push-next-btn')?.addEventListener('click', () => {
        const total = Math.ceil(state.push.total / state.push.pageSize);
        if (state.push.page < total) { state.push.page++; pushLoadArticles(); }
    });

    // Push Selected
    document.getElementById('push-selected-btn')?.addEventListener('click', () => pushStartSelected());

    // Push All Ready
    document.getElementById('push-all-ready-btn')?.addEventListener('click', () => pushStartAllReady());

    // Confirmation modal
    document.getElementById('push-confirm-close')?.addEventListener('click', pushHideConfirm);
    document.getElementById('push-confirm-cancel')?.addEventListener('click', pushHideConfirm);
    document.getElementById('push-confirm-go')?.addEventListener('click', pushExecuteConfirmed);

    // Drawer
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
// Language helpers
// ---------------------------------------------------------------------------
function pushSyncSelectAllLang() {
    const cbs = [...document.querySelectorAll('.push-lang-cb')];
    const allCb = document.getElementById('push-lang-select-all');
    if (!allCb) return;
    const n = cbs.filter(c => c.checked).length;
    allCb.checked = n === cbs.length;
    allCb.indeterminate = n > 0 && n < cbs.length;
}

function pushOnLangChange() {
    const selected = [...document.querySelectorAll('.push-lang-cb:checked')].map(c => c.value);
    state.push.locales = selected;

    // Update badge
    const badge = document.getElementById('push-lang-badge');
    if (badge) badge.textContent = selected.length;

    // Reload articles with new locales
    state.push.page = 1;
    pushLoadArticles();
    pushUpdateJobCounter();
    pushUpdateActionButtons();
}

// ---------------------------------------------------------------------------
// Job counter & button states
// ---------------------------------------------------------------------------
function pushUpdateJobCounter() {
    const articles = state.push.selectedIds.size;
    const langs = state.push.locales.length;
    document.getElementById('push-sel-article-count').textContent = articles;
    document.getElementById('push-sel-lang-count').textContent = langs;
    document.getElementById('push-sel-combo-count').textContent = articles * langs;
}

function pushUpdateActionButtons() {
    const hasLangs = state.push.locales.length > 0;
    const hasSelection = state.push.selectedIds.size > 0;
    const selBtn = document.getElementById('push-selected-btn');
    const allBtn = document.getElementById('push-all-ready-btn');
    if (selBtn) selBtn.disabled = !hasLangs || !hasSelection;
    if (allBtn) allBtn.disabled = !hasLangs;
}

// ---------------------------------------------------------------------------
// Load articles
// ---------------------------------------------------------------------------
function pushLoadArticles() {
    const tbody = document.getElementById('push-table-body');
    const colSpan = 2 + state.push.locales.length;
    if (tbody) tbody.innerHTML = `<tr><td colspan="${Math.max(colSpan, 2)}" class="empty-cell"><i class="fas fa-spinner fa-spin"></i> Loading…</td></tr>`;

    pushRenderTableHeader();

    if (state.push.locales.length === 0) {
        // No locales → just load titles
        const params = new URLSearchParams({ search: state.push.search, page: state.push.page, page_size: state.push.pageSize });
        fetch(`/api/push/articles?${params}`)
            .then(r => r.json())
            .then(data => {
                if (!data.success) throw new Error(data.error || 'Failed');
                state.push.articles = data.articles || [];
                state.push.total = data.total || 0;
                const el = document.getElementById('push-stat-articles');
                if (el) el.textContent = state.push.total;
                pushRenderTable();
                pushRenderPagination();
                pushUpdateJobCounter();
                pushUpdateActionButtons();
            })
            .catch(err => {
                if (tbody) tbody.innerHTML = `<tr><td colspan="2" class="empty-cell" style="color:#dc2626;"><i class="fas fa-exclamation-circle"></i> ${escapeHtml(err.message)}</td></tr>`;
            });
    } else {
        // Multi-locale → load status matrix
        const params = new URLSearchParams({ locales: state.push.locales.join(','), search: state.push.search, page: state.push.page, page_size: state.push.pageSize });
        fetch(`/api/push/articles-multi?${params}`)
            .then(r => r.json())
            .then(data => {
                if (!data.success) throw new Error(data.error || 'Failed');
                state.push.articles = data.articles || [];
                state.push.total = data.total || 0;
                const el = document.getElementById('push-stat-articles');
                if (el) el.textContent = state.push.total;
                pushRenderTable();
                pushRenderPagination();
                pushUpdateJobCounter();
                pushUpdateActionButtons();
            })
            .catch(err => {
                if (tbody) tbody.innerHTML = `<tr><td colspan="${colSpan}" class="empty-cell" style="color:#dc2626;"><i class="fas fa-exclamation-circle"></i> ${escapeHtml(err.message)}</td></tr>`;
            });
    }
}

// ---------------------------------------------------------------------------
// Table header (dynamic language columns)
// ---------------------------------------------------------------------------
function pushRenderTableHeader() {
    const thead = document.getElementById('push-thead-row');
    if (!thead) return;
    thead.innerHTML = `
        <th class="push-th-check"><input type="checkbox" id="push-select-all" title="Select all" aria-label="Select all"></th>
        <th class="push-th-title">Article Title</th>
        ${state.push.locales.map(code =>
            `<th class="push-th-lang" title="${escapeHtml(TARGET_LANGUAGES[code] || code)}">${code.toUpperCase()}</th>`
        ).join('')}
    `;
    // Bind select-all
    document.getElementById('push-select-all')?.addEventListener('change', (e) => {
        const checked = e.target.checked;
        state.push.articles.forEach(a => {
            if (checked) state.push.selectedIds.add(a.intercom_id);
            else state.push.selectedIds.delete(a.intercom_id);
        });
        document.querySelectorAll('.push-row-cb').forEach(cb => { cb.checked = checked; });
        pushUpdateJobCounter();
        pushUpdateActionButtons();
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

        const localeCells = hasLocales
            ? state.push.locales.map(loc => {
                const ld = (article.locale_data || {})[loc] || {};
                return `<td class="push-td-lang" data-iid="${iid}" data-locale="${loc}">
                    ${pushRenderBadge(ld.status || 'MISSING', ld.reason || '')}
                </td>`;
            }).join('')
            : '';

        tr.innerHTML = `
            <td><input type="checkbox" class="push-row-cb" data-id="${iid}" ${checked ? 'checked' : ''} aria-label="Select article"></td>
            <td><a href="#" class="push-article-link" data-id="${iid}">${escapeHtml(article.title || 'Untitled')}</a></td>
            ${localeCells}
        `;
        tbody.appendChild(tr);
    });

    // Bind row checkboxes
    tbody.querySelectorAll('.push-row-cb').forEach(cb => {
        cb.addEventListener('change', () => {
            const id = cb.dataset.id;
            if (cb.checked) state.push.selectedIds.add(id);
            else state.push.selectedIds.delete(id);
            const sa = document.getElementById('push-select-all');
            if (sa) {
                sa.checked = state.push.selectedIds.size === state.push.articles.length;
                sa.indeterminate = state.push.selectedIds.size > 0 && state.push.selectedIds.size < state.push.articles.length;
            }
            pushUpdateJobCounter();
            pushUpdateActionButtons();
        });
    });

    // Bind article title links → drawer
    tbody.querySelectorAll('.push-article-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            pushOpenDrawer(link.dataset.id);
        });
    });
}

// ---------------------------------------------------------------------------
// Status badge (no push button — status only)
// ---------------------------------------------------------------------------
function pushRenderBadge(status, reason) {
    const map = {
        READY:               { cls: 'push-badge-ready',          icon: 'fa-check-circle',         label: 'Ready' },
        LIVE:                { cls: 'push-badge-live',           icon: 'fa-globe',                label: 'Live' },
        OUTDATED:            { cls: 'push-badge-outdated',       icon: 'fa-exclamation-triangle', label: 'Outdated' },
        MISSING:             { cls: 'push-badge-missing',        icon: 'fa-times-circle',         label: 'Missing' },
        FAILED:              { cls: 'push-badge-failed',         icon: 'fa-exclamation-circle',   label: 'Failed' },
        PENDING:             { cls: 'push-badge-pending',        icon: 'fa-spinner fa-spin',      label: 'Pushing…' },
        NEEDS_RETRANSLATION: { cls: 'push-badge-retranslation',  icon: 'fa-language',             label: 'Re-translate' },
    };
    const d = map[status] || { cls: 'push-badge-nolang', icon: 'fa-minus', label: '—' };
    return `<span class="push-badge ${d.cls}" title="${escapeHtml(reason || status)}"><i class="fas ${d.icon}"></i> ${d.label}</span>`;
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------
function pushRenderPagination() {
    const totalPages = Math.max(1, Math.ceil(state.push.total / state.push.pageSize));
    const info = document.getElementById('push-page-info');
    if (info) info.textContent = `Page ${state.push.page} of ${totalPages} (${state.push.total} articles)`;
    const prev = document.getElementById('push-prev-btn');
    const next = document.getElementById('push-next-btn');
    if (prev) prev.disabled = state.push.page <= 1;
    if (next) next.disabled = state.push.page >= totalPages;
}

// ---------------------------------------------------------------------------
// Push Selected
// ---------------------------------------------------------------------------
function pushStartSelected() {
    if (state.push.locales.length === 0) { pushShowToast('Select at least one language first.', 'warn'); return; }
    if (state.push.selectedIds.size === 0) { pushShowToast('Select at least one article first.', 'warn'); return; }

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

    if (pairs.length === 0) { pushShowToast('No ready translations in the selection.', 'warn'); return; }
    pushShowConfirm(pairs, 'selected');
}

// ---------------------------------------------------------------------------
// Push All Ready
// ---------------------------------------------------------------------------
function pushStartAllReady() {
    if (state.push.locales.length === 0) { pushShowToast('Select at least one language first.', 'warn'); return; }

    const pairs = [];
    state.push.articles.forEach(a => {
        const ld = a.locale_data || {};
        state.push.locales.forEach(loc => {
            const s = (ld[loc] || {}).status;
            if (s === 'READY' || s === 'OUTDATED') pairs.push({iid: a.intercom_id, locale: loc});
        });
    });

    if (pairs.length === 0) { pushShowToast('No articles are ready to push.', 'warn'); return; }
    pushShowConfirm(pairs, 'all_ready');
}

// ---------------------------------------------------------------------------
// Confirmation modal
// ---------------------------------------------------------------------------
function pushShowConfirm(pairs, action) {
    state.push.confirmPairs = pairs;
    state.push.confirmAction = action;

    const body = document.getElementById('push-confirm-body');
    if (body) {
        const byLocale = {};
        pairs.forEach(({locale}) => { byLocale[locale] = (byLocale[locale] || 0) + 1; });
        const rows = Object.entries(byLocale)
            .map(([loc, n]) => `<li><strong>${TARGET_LANGUAGES[loc] || loc.toUpperCase()}</strong>: ${n} article${n !== 1 ? 's' : ''}</li>`)
            .join('');
        const actionLabel = action === 'all_ready' ? 'Push All Ready' : 'Push Selected';
        body.innerHTML = `
            <p><strong>${actionLabel}</strong> — publishing <strong>${pairs.length}</strong> translation${pairs.length !== 1 ? 's' : ''} to the live platform:</p>
            <ul style="margin:10px 0 10px 18px;">${rows}</ul>
            <p style="color:#64748b;font-size:12px;">Only <em>Ready</em> and <em>Outdated</em> items are included. Missing or failed translations are skipped.</p>
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
    const pairs = state.push.confirmPairs || [];
    if (pairs.length === 0) { pushHideConfirm(); return; }
    pushHideConfirm();

    let ok = 0, fail = 0;
    for (const {iid, locale} of pairs) {
        pushSetCellStatus(iid, locale, 'PENDING', 'Pushing…');
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
        ? `✓ ${ok} push${ok !== 1 ? 'es' : ''} completed successfully.`
        : `${ok} succeeded, ${fail} failed.`;
    pushShowToast(msg, fail === 0 ? 'success' : 'warn');
}

// ---------------------------------------------------------------------------
// Update a single cell's badge in-place
// ---------------------------------------------------------------------------
function pushSetCellStatus(iid, locale, status, reason) {
    const cell = document.querySelector(`.push-td-lang[data-iid="${iid}"][data-locale="${locale}"]`);
    if (cell) cell.innerHTML = pushRenderBadge(status, reason);

    // Keep in-memory state up to date
    const article = state.push.articles.find(a => a.intercom_id === iid);
    if (article) {
        if (!article.locale_data) article.locale_data = {};
        if (!article.locale_data[locale]) article.locale_data[locale] = {};
        article.locale_data[locale].status = status;
        article.locale_data[locale].reason = reason;
    }
}

// ---------------------------------------------------------------------------
// Preview Drawer
// ---------------------------------------------------------------------------
function pushOpenDrawer(iid) {
    const article = state.push.articles.find(a => a.intercom_id === iid);
    if (!article) return;

    state.push.drawerOpen = true;
    state.push.drawerArticleId = iid;
    state.push.drawerLocale = state.push.locales[0] || null;

    const title = document.getElementById('push-drawer-title');
    if (title) title.textContent = article.title || 'Article Preview';

    pushRenderDrawerTabs();
    pushLoadDrawerContent(iid, state.push.drawerLocale);

    document.getElementById('push-drawer')?.classList.remove('hidden');
    document.getElementById('push-drawer-overlay')?.classList.remove('hidden');
}

function pushRenderDrawerTabs() {
    const tabsEl = document.getElementById('push-drawer-lang-tabs');
    if (!tabsEl) return;
    if (state.push.locales.length === 0) { tabsEl.innerHTML = ''; return; }

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

            const statusHtml = locale && p.push_status
                ? `<div style="margin-bottom:14px;">${pushRenderBadge(p.push_status, p.reason)} <span style="font-size:12px;color:#64748b;margin-left:6px;">${escapeHtml(p.reason || '')}</span></div>`
                : '';

            const outdatedBanner = (p.push_status === 'OUTDATED' || p.push_status === 'NEEDS_RETRANSLATION')
                ? `<div class="push-outdated-banner"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(p.reason || 'Content may be outdated')}</div>`
                : '';

            const metaHtml = `
                <div class="push-preview-meta">
                    <div class="push-meta-item"><span>Source Updated</span><strong>${escapeHtml(p.source_updated_relative || '—')}</strong></div>
                    <div class="push-meta-item"><span>Translated</span><strong>${escapeHtml(p.translated_relative || '—')}</strong></div>
                    <div class="push-meta-item"><span>Last Pushed</span><strong>${escapeHtml(p.pushed_relative || '—')}</strong></div>
                    <div class="push-meta-item"><span>Language</span><strong>${locale ? (TARGET_LANGUAGES[locale] || locale.toUpperCase()) : 'Source'}</strong></div>
                </div>`;

            const srcTitle = p.source_title ? `<div style="font-weight:700;font-size:15px;margin-bottom:8px;">${escapeHtml(p.source_title)}</div>` : '';
            const srcBody = p.source_body_html
                ? `<div class="push-preview-content">${p.source_body_html}</div>`
                : `<div class="push-preview-content" style="color:#94a3b8;font-style:italic;">No source content</div>`;

            const transSection = locale ? (() => {
                const tt = p.translated_title ? `<div style="font-weight:700;font-size:15px;margin-bottom:8px;">${escapeHtml(p.translated_title)}</div>` : '';
                const tb = p.translated_body_html
                    ? `<div class="push-preview-content">${p.translated_body_html}</div>`
                    : `<div class="push-preview-content" style="color:#94a3b8;font-style:italic;">No translation yet</div>`;
                return `<div class="push-preview-section">
                    <h4><i class="fas fa-language"></i> ${TARGET_LANGUAGES[locale] || locale.toUpperCase()} Translation</h4>
                    ${tt}${tb}
                </div>`;
            })() : '';

            body.innerHTML = `${statusHtml}${outdatedBanner}${metaHtml}
                <div class="push-preview-section">
                    <h4><i class="fas fa-file-alt"></i> Original (English)</h4>
                    ${srcTitle}${srcBody}
                </div>
                ${transSection}`;

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
