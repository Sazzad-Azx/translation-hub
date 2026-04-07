// ============================================================
// FundedNext Translation Hub - Frontend Application
// ============================================================

// Register Chart.js datalabels plugin globally if available
if (typeof Chart !== 'undefined' && typeof ChartDataLabels !== 'undefined') {
    Chart.register(ChartDataLabels);
    Chart.defaults.set('plugins.datalabels', { display: false }); // off by default, enable per chart
}

// Loader HTML helpers
const FN_LOADER = '<span class="fn-loader"></span>';
const FN_LOADER_INLINE = '<span class="fn-loader-inline"></span>';

// ─── Generic Confirm Modal ─────────────────────────────────
function showConfirmModal({ title, body, confirmText, confirmIcon, onConfirm }) {
    const overlay = document.getElementById('generic-confirm-overlay');
    const titleEl = document.getElementById('generic-confirm-title');
    const bodyEl = document.getElementById('generic-confirm-body');
    const okBtn = document.getElementById('generic-confirm-ok');
    const cancelBtn = document.getElementById('generic-confirm-cancel');
    const closeBtn = document.getElementById('generic-confirm-close');

    titleEl.innerHTML = `<i class="fas ${confirmIcon || 'fa-exclamation-circle'}"></i> ${title || 'Confirm'}`;
    bodyEl.innerHTML = body || '';
    okBtn.innerHTML = `<i class="fas ${confirmIcon || 'fa-check'}"></i> ${confirmText || 'Confirm'}`;

    overlay.classList.remove('hidden');

    function cleanup() {
        overlay.classList.add('hidden');
        okBtn.removeEventListener('click', handleOk);
        cancelBtn.removeEventListener('click', handleCancel);
        closeBtn.removeEventListener('click', handleCancel);
    }
    function handleOk() { cleanup(); onConfirm(); }
    function handleCancel() { cleanup(); }

    okBtn.addEventListener('click', handleOk);
    cancelBtn.addEventListener('click', handleCancel);
    closeBtn.addEventListener('click', handleCancel);
}

// ─── Auth state ────────────────────────────────────────────
let authState = {
    token: localStorage.getItem('auth_token') || '',
    user: null,   // {email, name, role}
    authenticated: false,
};

function authHeaders() {
    const h = { 'Content-Type': 'application/json' };
    if (authState.token) h['Authorization'] = `Bearer ${authState.token}`;
    return h;
}

// Intercept all fetch calls to /api/ to add auth header and handle 401
const _originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
    if (typeof url === 'string' && url.startsWith('/api/') && url !== '/api/auth/login') {
        options = options || {};
        options.headers = options.headers || {};
        // If headers is a Headers object, convert
        if (options.headers instanceof Headers) {
            if (authState.token) options.headers.set('Authorization', `Bearer ${authState.token}`);
        } else {
            if (authState.token && !options.headers['Authorization']) {
                options.headers['Authorization'] = `Bearer ${authState.token}`;
            }
        }
    }
    return _originalFetch.call(this, url, options).then(response => {
        // Auto-redirect to login on 401 (expired / invalid token)
        if (response.status === 401 && typeof url === 'string' &&
            url.startsWith('/api/') && url !== '/api/auth/login' && url !== '/api/auth/me') {
            console.warn('[Auth] 401 received – session expired, redirecting to login.');
            authState.token = '';
            authState.user = null;
            authState.authenticated = false;
            localStorage.removeItem('auth_token');
            state._appBooted = false;
            showLogin();
        }
        return response;
    });
};

// Global state
let state = {
    articles: [],
    selectedArticles: new Set(),
    selectedLanguages: new Set(),
    languages: {},
    currentPreview: null,
    supabaseArticles: [],
    savedTranslations: [],
    dashboardStats: null,
    changesChart: null,
    costChart: null,
    // Content Hub state
    hub: {
        loaded: false,
        articles: [],
        selectedIds: new Set(),
        selectedMeta: {},
        page: 1,
        pageSize: 25,
        total: 0,
        totalWords: 0,
        search: '',
        healthFilter: 'ALL',
        sortBy: 'title_asc',
        activeTab: 'articles',
        counts: {},
        searchTimeout: null,
        drawerOpen: false,
    },
    // Pull module state
    pull: {
        loaded: false,
        tableExists: false,
        articles: [],
        selectedIds: new Set(),
        page: 1,
        pageSize: 25,
        total: 0,
        search: '',
        statusFilter: '',
        searchTimeout: null,
    },
    // Glossary module state
    gl: {
        loaded: false,
        tablesExist: false,
        glossaries: [],
        glossaryTotal: 0,
        glossaryPage: 1,
        glossaryPageSize: 25,
        glossarySearch: '',
        glossaryFilter: 'ALL',
        glossarySort: 'name_asc',
        glossarySearchTimeout: null,
        currentGlossaryId: null,
        currentGlossary: null,
        terms: [],
        selectedTermIds: new Set(),
        termPage: 1,
        termPageSize: 100,
        termTotal: 0,
        termSearch: '',
        termSearchTimeout: null,
        editingGlossaryId: null,
        editingTermId: null,
        usage: {},
        drawerSelectedLanguages: new Set(),
    },
    // Language module state
    lang: {
        loaded: false,
        languages: {},
        totalArticles: 0,
        search: '',
    },
    // Push module state
    push: {
        loaded: false,
        locales: [],
        tempLocales: [],
        langPanelOpen: false,
        articles: [],
        selectedIds: new Set(),
        page: 1,
        pageSize: 25,
        total: 0,
        search: '',
        searchTimeout: null,
        drawerOpen: false,
        drawerArticleId: null,
        drawerLocale: null,
        confirmAction: null,
        confirmPairs: [],
    },
    // Translate module state
    tr: {
        loaded: false,
        articles: [],
        languages: {},
        page: 1,
        pageSize: 25,
        total: 0,
        search: '',
        statusFilter: 'ALL',
        languageFilter: '',
        sortBy: 'attention',
        selectedArticles: new Set(),
        selectedLanguages: new Set(),
        searchTimeout: null,
        counts: {},
        drawerOpen: false,
        translating: false,
    },
};

// ---- Initialisation ----
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
});

async function initializeApp() {
    setupLoginListeners();

    // Check if user has a saved token
    if (authState.token) {
        const valid = await authCheckSession();
        if (valid) {
            showApp();
            return;
        }
    }
    // Show login screen
    showLogin();
}

function showLogin() {
    document.documentElement.classList.remove('has-token');
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('app-wrapper').classList.add('hidden');
}

function showApp() {
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('app-wrapper').classList.remove('hidden');
    authUpdateUI();

    // Boot the main app once
    if (!state._appBooted) {
        state._appBooted = true;
        setupNavigation();
        setupEventListeners();
        testConnection();
        loadDashboardData();
        // Restore section from URL hash on page load
        const hash = window.location.hash.replace('#', '');
        if (hash) {
            switchSection(hash);
        }
    }
}

// ─── Login listeners ──────────────────────────────────────
function setupLoginListeners() {
    const form = document.getElementById('login-form');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('login-email').value.trim();
            const password = document.getElementById('login-password').value;
            const errEl = document.getElementById('login-error');
            const btn = document.getElementById('login-btn');
            const btnText = btn.querySelector('.login-btn-text');
            const btnLoading = btn.querySelector('.login-btn-loading');

            errEl.classList.add('hidden');
            btn.disabled = true;
            btnText.classList.add('hidden');
            btnLoading.classList.remove('hidden');

            try {
                const resp = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password }),
                });
                const data = await resp.json();
                if (data.success) {
                    authState.token = data.token;
                    authState.user = { email: data.email, name: data.name, role: data.role };
                    authState.authenticated = true;
                    localStorage.setItem('auth_token', data.token);
                    showApp();
                } else {
                    errEl.textContent = data.error || 'Login failed';
                    errEl.classList.remove('hidden');
                }
            } catch (err) {
                errEl.textContent = 'Network error. Please try again.';
                errEl.classList.remove('hidden');
            }

            btn.disabled = false;
            btnText.classList.remove('hidden');
            btnLoading.classList.add('hidden');
        });
    }

    // Password toggle
    const toggle = document.getElementById('password-toggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            const inp = document.getElementById('login-password');
            const icon = document.getElementById('eye-icon');
            if (inp.type === 'password') {
                inp.type = 'text';
                if (icon) icon.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>';
            } else {
                inp.type = 'password';
                if (icon) icon.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
            }
        });
    }
}

async function authCheckSession() {
    try {
        const resp = await fetch('/api/auth/me', {
            headers: authHeaders(),
        });
        if (resp.ok) {
            const data = await resp.json();
            if (data.success) {
                authState.user = { email: data.email, name: data.name, role: data.role };
                authState.authenticated = true;
                return true;
            }
        }
    } catch (e) { /* ignore */ }
    // Invalid token
    authState.token = '';
    authState.authenticated = false;
    localStorage.removeItem('auth_token');
    return false;
}

function authUpdateUI() {
    const user = authState.user;
    if (!user) return;

    // Avatar initials
    const initials = (user.name || user.email || 'A')
        .split(' ')
        .map(w => w[0])
        .join('')
        .substring(0, 2)
        .toUpperCase();
    const avatarEl = document.getElementById('user-avatar');
    if (avatarEl) avatarEl.textContent = initials;

    const nameEl = document.getElementById('user-name');
    if (nameEl) nameEl.textContent = user.name || user.email;

    const ddName = document.getElementById('dropdown-user-name');
    if (ddName) ddName.textContent = user.name || 'Admin';
    const ddEmail = document.getElementById('dropdown-user-email');
    if (ddEmail) ddEmail.textContent = user.email;
    const ddRole = document.getElementById('dropdown-user-role');
    if (ddRole) {
        const roleLabel = user.role === 'super_admin' ? 'Super Admin' : user.role;
        ddRole.textContent = roleLabel;
    }

    // Show admin nav for super admin
    const adminNav = document.getElementById('admin-nav-item');
    const adminDivider = document.getElementById('admin-nav-divider');
    if (user.role === 'super_admin') {
        if (adminNav) adminNav.style.display = '';
        if (adminDivider) adminDivider.style.display = '';
    } else {
        if (adminNav) adminNav.style.display = 'none';
        if (adminDivider) adminDivider.style.display = 'none';
    }
}

async function authLogout() {
    try {
        await fetch('/api/auth/logout', {
            method: 'POST',
            headers: authHeaders(),
        });
    } catch (e) { /* ignore */ }
    authState.token = '';
    authState.user = null;
    authState.authenticated = false;
    localStorage.removeItem('auth_token');
    // Reset app booted state
    state._appBooted = false;
    showLogin();
    // Clear login form
    const emailInp = document.getElementById('login-email');
    const passInp = document.getElementById('login-password');
    if (emailInp) emailInp.value = '';
    if (passInp) passInp.value = '';
}

// ─── Automation section ──────────────────────────────────
let autoState = { loaded: false, settings: null, tableExists: false };

async function initAutomationSection() {
    if (autoState.loaded) {
        autoRefreshStatus();
        autoRefreshPullStatus();
        return;
    }
    autoState.loaded = true;
    setupAutomationListeners();
    await autoCheckTable();
}

function setupAutomationListeners() {
    // Toggle switch
    const toggle = document.getElementById('auto-sync-toggle');
    if (toggle) {
        toggle.addEventListener('change', async () => {
            const enabled = toggle.checked;
            toggle.disabled = true;
            try {
                const resp = await fetch('/api/automation/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled }),
                });
                const data = await resp.json();
                if (data.success) {
                    showAutoToast(enabled ? 'Auto-sync enabled! Next run at ~00:00 UTC.' : 'Auto-sync disabled.', 'success');
                    await autoRefreshStatus();
                } else {
                    showAutoToast('Failed to toggle: ' + (data.error || 'Unknown error'), 'error');
                    toggle.checked = !enabled; // Revert
                }
            } catch (err) {
                showAutoToast('Error: ' + err.message, 'error');
                toggle.checked = !enabled;
            }
            toggle.disabled = false;
        });
    }

    // Run Now button
    document.getElementById('auto-run-now-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('auto-run-now-btn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="fn-loader-inline"></span> Running…'; }
        try {
            const resp = await fetch('/api/automation/run-now', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            const data = await resp.json();
            if (data.success) {
                showAutoToast(data.message || `Synced ${data.synced} articles.`, 'success');
            } else if (data.skipped) {
                showAutoToast('Auto-sync is disabled. Enable it first or use Pull > Sync Source List.', 'warning');
            } else {
                showAutoToast('Sync failed: ' + (data.error || 'Unknown'), 'error');
            }
            await autoRefreshStatus();
        } catch (err) {
            showAutoToast('Error: ' + err.message, 'error');
        }
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-play"></i> Run Now'; }
    });

    // Refresh button
    document.getElementById('auto-refresh-btn')?.addEventListener('click', () => autoRefreshStatus());

    // Auto-create table
    document.getElementById('auto-create-settings-table-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('auto-create-settings-table-btn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="fn-loader-inline"></span> Creating…'; }
        try {
            const resp = await fetch('/api/automation/create-table', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
            const data = await resp.json();
            if (data.success) {
                showAutoToast('Table created successfully!', 'success');
                await autoCheckTable();
            } else {
                showAutoToast('Failed: ' + (data.error || 'Unknown'), 'error');
            }
        } catch (err) {
            showAutoToast('Error: ' + err.message, 'error');
        }
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-magic"></i> Auto-Create Table'; }
    });

    // Copy SQL
    document.getElementById('auto-copy-settings-sql-btn')?.addEventListener('click', async () => {
        const sqlEl = document.getElementById('auto-setup-sql');
        if (sqlEl) {
            sqlEl.classList.toggle('hidden');
            if (!sqlEl.classList.contains('hidden')) {
                try {
                    const resp = await fetch('/api/automation/table-status');
                    const data = await resp.json();
                    sqlEl.textContent = data.setup_sql || 'No SQL available.';
                    await navigator.clipboard.writeText(data.setup_sql || '');
                    showAutoToast('SQL copied to clipboard!', 'success');
                } catch (e) { /* ignore */ }
            }
        }
    });

    // ── Auto Pull Card listeners ──

    // Toggle switch
    const pullToggle = document.getElementById('auto-pull-toggle');
    if (pullToggle) {
        pullToggle.addEventListener('change', async () => {
            const enabled = pullToggle.checked;
            pullToggle.disabled = true;
            try {
                const resp = await fetch('/api/automation/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: 'auto_pull_articles', enabled }),
                });
                const data = await resp.json();
                if (data.success) {
                    showAutoToast(enabled ? 'Auto-pull enabled! Next run at ~01:30 UTC.' : 'Auto-pull disabled.', 'success');
                    await autoRefreshPullStatus();
                } else {
                    showAutoToast('Failed to toggle: ' + (data.error || 'Unknown error'), 'error');
                    pullToggle.checked = !enabled;
                }
            } catch (err) {
                showAutoToast('Error: ' + err.message, 'error');
                pullToggle.checked = !enabled;
            }
            pullToggle.disabled = false;
        });
    }

    // Run Now button
    document.getElementById('auto-pull-run-now-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('auto-pull-run-now-btn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="fn-loader-inline"></span> Pulling…'; }
        try {
            const resp = await fetch('/api/automation/run-now', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: 'auto_pull_articles' }),
            });
            const data = await resp.json();
            if (data.success) {
                showAutoToast(data.message || `Pulled ${data.pulled} article(s).`, 'success');
            } else if (data.skipped) {
                showAutoToast('Auto-pull is disabled. Enable it first or use Pull section manually.', 'warning');
            } else {
                showAutoToast('Pull failed: ' + (data.error || 'Unknown'), 'error');
            }
            await autoRefreshPullStatus();
        } catch (err) {
            showAutoToast('Error: ' + err.message, 'error');
        }
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-play"></i> Run Now'; }
    });

    // Refresh button
    document.getElementById('auto-pull-refresh-btn')?.addEventListener('click', () => autoRefreshPullStatus());
}

async function autoCheckTable() {
    try {
        const resp = await fetch('/api/automation/table-status');
        const data = await resp.json();
        autoState.tableExists = data.table_exists;

        const banner = document.getElementById('auto-setup-banner');
        const main = document.getElementById('auto-main-content');

        if (data.table_exists) {
            if (banner) banner.classList.add('hidden');
            if (main) main.classList.remove('hidden');
            await autoRefreshStatus();
            await autoRefreshPullStatus();
        } else {
            if (banner) banner.classList.remove('hidden');
            if (main) main.classList.add('hidden');
            const sqlEl = document.getElementById('auto-setup-sql');
            if (sqlEl) sqlEl.textContent = data.setup_sql || '';
        }
    } catch (err) {
        console.warn('Automation table check failed:', err);
    }
}

async function autoRefreshStatus() {
    try {
        const resp = await fetch('/api/automation/settings');
        const data = await resp.json();
        if (!data.success) return;

        const s = data.settings;
        autoState.settings = s;

        // Update toggle
        const toggle = document.getElementById('auto-sync-toggle');
        if (toggle) toggle.checked = !!s.enabled;

        // Status label
        const label = document.getElementById('auto-sync-status-label');
        if (label) {
            label.textContent = s.enabled ? 'Enabled' : 'Disabled';
            label.classList.toggle('enabled', !!s.enabled);
        }

        // Status badge
        const badge = document.getElementById('auto-sync-status-badge');
        if (badge) {
            if (s.enabled) {
                badge.innerHTML = '<span class="auto-badge auto-badge-enabled"><i class="fas fa-check-circle"></i> Active</span>';
            } else {
                badge.innerHTML = '<span class="auto-badge auto-badge-disabled"><i class="fas fa-pause-circle"></i> Disabled</span>';
            }
        }

        // Last run
        const lastRunEl = document.getElementById('auto-last-run');
        if (lastRunEl) {
            if (s.last_run_at) {
                const d = new Date(s.last_run_at);
                lastRunEl.textContent = d.toLocaleString();
            } else {
                lastRunEl.textContent = 'Never';
            }
        }

        // Last result
        const lastResultEl = document.getElementById('auto-last-result');
        if (lastResultEl) {
            if (s.last_run_status === 'success') {
                lastResultEl.innerHTML = `<span class="auto-badge auto-badge-success"><i class="fas fa-check"></i> Success</span> <span style="font-size:12px;color:var(--text-muted);margin-left:6px;">${escapeHtml(s.last_run_message || '')}</span>`;
            } else if (s.last_run_status === 'error') {
                lastResultEl.innerHTML = `<span class="auto-badge auto-badge-error"><i class="fas fa-times"></i> Error</span> <span style="font-size:12px;color:#dc2626;margin-left:6px;">${escapeHtml(s.last_run_message || '')}</span>`;
            } else {
                lastResultEl.textContent = '—';
            }
        }

        // Next run
        const nextRunEl = document.getElementById('auto-next-run');
        if (nextRunEl) {
            if (s.enabled && s.next_run_at) {
                const d = new Date(s.next_run_at);
                nextRunEl.textContent = d.toLocaleString();
            } else {
                nextRunEl.textContent = s.enabled ? '~00:00 UTC (next midnight)' : '—';
            }
        }
    } catch (err) {
        console.warn('Automation status refresh failed:', err);
    }
}

async function autoRefreshPullStatus() {
    try {
        const resp = await fetch('/api/automation/settings?key=auto_pull_articles');
        const data = await resp.json();
        if (!data.success) return;

        const s = data.settings;

        // Update toggle
        const toggle = document.getElementById('auto-pull-toggle');
        if (toggle) toggle.checked = !!s.enabled;

        // Status label
        const label = document.getElementById('auto-pull-status-label');
        if (label) {
            label.textContent = s.enabled ? 'Enabled' : 'Disabled';
            label.classList.toggle('enabled', !!s.enabled);
        }

        // Status badge
        const badge = document.getElementById('auto-pull-status-badge');
        if (badge) {
            if (s.enabled) {
                badge.innerHTML = '<span class="auto-badge auto-badge-enabled"><i class="fas fa-check-circle"></i> Active</span>';
            } else {
                badge.innerHTML = '<span class="auto-badge auto-badge-disabled"><i class="fas fa-pause-circle"></i> Disabled</span>';
            }
        }

        // Last run
        const lastRunEl = document.getElementById('auto-pull-last-run');
        if (lastRunEl) {
            if (s.last_run_at) {
                const d = new Date(s.last_run_at);
                lastRunEl.textContent = d.toLocaleString();
            } else {
                lastRunEl.textContent = 'Never';
            }
        }

        // Last result
        const lastResultEl = document.getElementById('auto-pull-last-result');
        if (lastResultEl) {
            if (s.last_run_status === 'success') {
                lastResultEl.innerHTML = `<span class="auto-badge auto-badge-success"><i class="fas fa-check"></i> Success</span> <span style="font-size:12px;color:var(--text-muted);margin-left:6px;">${escapeHtml(s.last_run_message || '')}</span>`;
            } else if (s.last_run_status === 'error') {
                lastResultEl.innerHTML = `<span class="auto-badge auto-badge-error"><i class="fas fa-times"></i> Error</span> <span style="font-size:12px;color:#dc2626;margin-left:6px;">${escapeHtml(s.last_run_message || '')}</span>`;
            } else {
                lastResultEl.textContent = '—';
            }
        }

        // Next run
        const nextRunEl = document.getElementById('auto-pull-next-run');
        if (nextRunEl) {
            if (s.enabled && s.next_run_at) {
                const d = new Date(s.next_run_at);
                nextRunEl.textContent = d.toLocaleString();
            } else {
                nextRunEl.textContent = s.enabled ? '~01:30 UTC (daily)' : '—';
            }
        }
    } catch (err) {
        console.warn('Auto-pull status refresh failed:', err);
    }
}

function showAutoToast(msg, type = 'info') {
    const toast = document.getElementById('auto-toast');
    if (!toast) return;
    const iconMap = { success: 'check-circle', error: 'exclamation-circle', warning: 'exclamation-triangle', info: 'info-circle' };
    toast.className = `tr-toast tr-toast-${type}`;
    toast.innerHTML = `<i class="fas fa-${iconMap[type] || 'info-circle'}"></i> ${msg}`;
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 5000);
}

// ─── Admin panel ──────────────────────────────────────────
let adminState = { loaded: false, admins: [], tableExists: true };

async function initAdminSection() {
    if (adminState.loaded) { loadAdmins(); return; }
    adminState.loaded = true;

    // Check table
    try {
        const resp = await fetch('/api/auth/admins-table', { headers: authHeaders() });
        const data = await resp.json();
        const banner = document.getElementById('admin-setup-banner');
        if (!data.exists) {
            adminState.tableExists = false;
            const sqlPre = document.getElementById('admin-setup-sql');
            if (banner) banner.classList.remove('hidden');
            if (sqlPre) sqlPre.textContent = data.sql || '';
        } else {
            adminState.tableExists = true;
            if (banner) banner.classList.add('hidden');
        }
    } catch (e) {
        // If the check fails but admins load OK, hide the banner
        const banner = document.getElementById('admin-setup-banner');
        if (banner) banner.classList.add('hidden');
    }

    // Copy SQL button
    const copyBtn = document.getElementById('admin-copy-sql');
    if (copyBtn) {
        copyBtn.addEventListener('click', () => {
            const sql = document.getElementById('admin-setup-sql').textContent;
            navigator.clipboard.writeText(sql);
            copyBtn.innerHTML = '✅ &nbsp;Copied!';
            setTimeout(() => { copyBtn.innerHTML = '📋 &nbsp;Copy SQL'; }, 2000);
        });
    }

    // Auto-create table button
    const autoCreateBtn = document.getElementById('admin-auto-create');
    if (autoCreateBtn) {
        autoCreateBtn.addEventListener('click', async () => {
            autoCreateBtn.disabled = true;
            autoCreateBtn.innerHTML = '<span class="fn-loader-inline"></span> &nbsp;Creating...';
            try {
                const resp = await fetch('/api/auth/admins-table/create', {
                    method: 'POST',
                    headers: authHeaders(),
                });
                const data = await resp.json();
                if (data.success) {
                    document.getElementById('admin-setup-banner').classList.add('hidden');
                    adminState.tableExists = true;
                    loadAdmins();
                } else {
                    alert(data.error || 'Auto-create failed. Please use the SQL Editor.');
                }
            } catch (e) {
                alert('Failed to auto-create table. Please use the SQL Editor.');
            }
            autoCreateBtn.disabled = false;
            autoCreateBtn.innerHTML = '⚡ &nbsp;Auto-Create Table';
        });
    }

    // Add admin button
    const addBtn = document.getElementById('admin-add-btn');
    if (addBtn) {
        addBtn.addEventListener('click', async () => {
            const name = document.getElementById('admin-add-name').value.trim();
            const email = document.getElementById('admin-add-email').value.trim();
            const password = document.getElementById('admin-add-password').value;
            const role = document.getElementById('admin-add-role').value;
            const errEl = document.getElementById('admin-add-error');

            errEl.classList.add('hidden');
            if (!name || !email || !password) {
                errEl.textContent = 'All fields are required.';
                errEl.classList.remove('hidden');
                return;
            }
            if (password.length < 6) {
                errEl.textContent = 'Password must be at least 6 characters.';
                errEl.classList.remove('hidden');
                return;
            }

            addBtn.disabled = true;
            addBtn.innerHTML = '<span class="fn-loader-inline"></span> &nbsp;Adding...';

            try {
                const resp = await fetch('/api/auth/admins', {
                    method: 'POST',
                    headers: authHeaders(),
                    body: JSON.stringify({ name, email, password, role }),
                });
                const data = await resp.json();
                if (data.success) {
                    document.getElementById('admin-add-name').value = '';
                    document.getElementById('admin-add-email').value = '';
                    document.getElementById('admin-add-password').value = '';
                    loadAdmins();
                } else {
                    errEl.textContent = data.error || 'Failed to create admin.';
                    errEl.classList.remove('hidden');
                }
            } catch (e) {
                errEl.textContent = 'Network error.';
                errEl.classList.remove('hidden');
            }

            addBtn.disabled = false;
            addBtn.innerHTML = '➕ &nbsp;Add Admin';
        });
    }

    await loadAdmins();
}

async function loadAdmins() {
    const tbody = document.getElementById('admin-table-body');
    if (!tbody) return;

    try {
        const resp = await fetch('/api/auth/admins', { headers: authHeaders() });
        const data = await resp.json();
        adminState.admins = data.admins || [];
        // If we successfully fetched admins, the table exists — hide the setup banner
        if (resp.ok) {
            adminState.tableExists = true;
            const banner = document.getElementById('admin-setup-banner');
            if (banner) banner.classList.add('hidden');
        }
    } catch (e) {
        adminState.admins = [];
    }

    // Always show super admin row at top
    const superAdmin = authState.user && authState.user.role === 'super_admin' ? authState.user : null;

    let html = '';

    // Super admin row (not deletable)
    if (superAdmin) {
        html += `<tr>
            <td><span class="ap-name">${escapeHtml(superAdmin.name)}</span></td>
            <td><span class="ap-email">${escapeHtml(superAdmin.email)}</span></td>
            <td class="ap-td-center"><span class="ap-role-badge ap-role-super"><div class="ap-role-dot"></div>Super Admin</span></td>
            <td class="ap-td-center"><span class="ap-status-badge ap-status-active"><div class="ap-status-dot"></div>Active</span></td>
            <td><span class="ap-date">—</span></td>
            <td class="ap-td-center"><span class="ap-protected">Protected</span></td>
        </tr>`;
    }

    // Other admins
    if (adminState.admins.length === 0) {
        html += `<tr><td colspan="6" style="text-align:center;padding:24px;color:#93C5E0;font-weight:500;">No other admins yet. Add one above.</td></tr>`;
    } else {
        for (const admin of adminState.admins) {
            const created = admin.created_at ? new Date(admin.created_at).toLocaleDateString('en', { month:'short', day:'numeric', year:'numeric' }) : '—';
            const statusCls = admin.is_active ? 'ap-status-active' : 'ap-status-inactive';
            const statusText = admin.is_active ? 'Active' : 'Inactive';
            const roleCls = admin.role === 'super_admin' ? 'ap-role-super' : admin.role === 'admin' ? 'ap-role-admin' : admin.role === 'editor' ? 'ap-role-editor' : 'ap-role-viewer';
            const roleLabel = admin.role === 'super_admin' ? 'Super Admin' : admin.role.charAt(0).toUpperCase() + admin.role.slice(1);
            const toggleIcon = admin.is_active ? '⛔' : '✅';
            const toggleTitle = admin.is_active ? 'Deactivate' : 'Activate';
            html += `<tr data-admin-id="${admin.id}">
                <td><span class="ap-name">${escapeHtml(admin.name || '')}</span></td>
                <td><span class="ap-email">${escapeHtml(admin.email)}</span></td>
                <td class="ap-td-center"><span class="ap-role-badge ${roleCls}"><div class="ap-role-dot"></div>${roleLabel}</span></td>
                <td class="ap-td-center"><span class="ap-status-badge ${statusCls}"><div class="ap-status-dot"></div>${statusText}</span></td>
                <td><span class="ap-date">${created}</span></td>
                <td class="ap-td-center">
                    <button class="ap-action-btn" title="${toggleTitle}" onclick="adminToggleActive(${admin.id}, ${!admin.is_active})">${toggleIcon}</button>
                    <button class="ap-action-btn ap-delete" title="Delete" onclick="adminDelete(${admin.id})">🗑️</button>
                </td>
            </tr>`;
        }
    }

    tbody.innerHTML = html;
}

async function adminToggleActive(adminId, newStatus) {
    try {
        await fetch(`/api/auth/admins/${adminId}`, {
            method: 'PUT',
            headers: authHeaders(),
            body: JSON.stringify({ is_active: newStatus }),
        });
        loadAdmins();
    } catch (e) { alert('Failed to update admin.'); }
}

async function adminDelete(adminId) {
    if (!confirm('Are you sure you want to delete this admin?')) return;
    try {
        await fetch(`/api/auth/admins/${adminId}`, {
            method: 'DELETE',
            headers: authHeaders(),
        });
        loadAdmins();
    } catch (e) { alert('Failed to delete admin.'); }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ---- Navigation ----
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const sectionId = item.getAttribute('data-section');
            switchSection(sectionId);
            window.location.hash = sectionId;
        });
    });

    // Sidebar toggle (mobile)
    const toggle = document.getElementById('sidebar-toggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            document.getElementById('sidebar').classList.toggle('open');
        });
    }
}

function switchSection(sectionId) {
    // Update nav items
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const activeNav = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
    if (activeNav) activeNav.classList.add('active');

    // Update page sections
    document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
    const section = document.getElementById(`section-${sectionId}`);
    if (section) section.classList.add('active');

    // Update topbar title
    const titleMap = {
        'dashboard': 'Dashboard',
        'content-hub': 'Control Tower',
        'pull': 'Pull',
        'translate': 'Translate',
        'push': 'Push',
        'automation': 'Automation',
        'fundee-update': 'Fundee Update',
        'language': 'Language',
        'glossary': 'Glossary',
        'admin': 'Admin Panel'
    };
    const topbarTitle = document.getElementById('topbar-title');
    if (topbarTitle) topbarTitle.textContent = titleMap[sectionId] || sectionId;

    // Close sidebar on mobile
    document.getElementById('sidebar').classList.remove('open');

    // Refresh dashboard data when navigating back to it
    if (sectionId === 'dashboard') {
        loadDashboardData();
    }

    // Lazy-load sections on first visit
    if (sectionId === 'content-hub' && !state.hub.loaded) {
        initContentHub();
    }
    if (sectionId === 'pull' && !state.pull.loaded) {
        initPullSection();
    }
    if (sectionId === 'translate' && !state.tr.loaded) {
        initTranslateSection();
    }
    if (sectionId === 'glossary' && !state.gl.loaded) {
        initGlossarySection();
    }
    if (sectionId === 'push' && !state.push.loaded) {
        initPushSection();
    }
    if (sectionId === 'language' && !state.lang.loaded) {
        initLanguageSection();
    }
    if (sectionId === 'automation') {
        initAutomationSection();
    }
    if (sectionId === 'admin') {
        initAdminSection();
    }
}

// ---- Event Listeners ----
function setupEventListeners() {
    // Refresh button - context-aware based on active section
    const refreshBtn = document.getElementById('refresh-page-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            // Get the currently active section
            const activeSection = document.querySelector('.page-section.active');
            if (!activeSection) {
                // Fallback to dashboard if no section is active
                await loadDashboardData();
                return;
            }

            const sectionId = activeSection.id.replace('section-', '');
            
            // Call appropriate refresh function based on active section
            switch (sectionId) {
                case 'dashboard':
                    await loadDashboardData();
                    break;
                case 'content-hub':
                    await loadHubArticles();
                    break;
                case 'pull':
                    await loadPullStats();
                    await loadPullArticles();
                    break;
                case 'translate':
                    await trLoadArticles();
                    break;
                case 'push':
                    await pushLoadArticles();
                    break;
                case 'language':
                    await langLoadStats();
                    break;
                case 'glossary':
                    await glLoadGlossaries();
                    break;
                case 'automation':
                    await autoRefreshStatus();
                    await autoRefreshPullStatus();
                    break;
                default:
                    // For other sections, try to refresh dashboard as fallback
                    await loadDashboardData();
                    break;
            }
        });
    }

    // ── User menu & logout ──
    const userMenuBtn = document.getElementById('user-menu-btn');
    const userDropdown = document.getElementById('user-dropdown');
    if (userMenuBtn && userDropdown) {
        userMenuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            userDropdown.classList.toggle('hidden');
        });
        document.addEventListener('click', () => {
            userDropdown.classList.add('hidden');
        });
    }
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            authLogout();
        });
    }

    // Period toggle buttons for charts
    document.querySelectorAll('.period-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const parent = btn.closest('.chart-period-toggle');
            parent.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const period = btn.getAttribute('data-period');
            const isForCost = btn.getAttribute('data-chart') === 'cost';
            if (isForCost) {
                renderCostChart(period);
            } else {
                renderChangesChart(period);
            }
        });
    });

    // Modal close buttons
    const closeResults = document.querySelector('.close');
    if (closeResults) closeResults.addEventListener('click', () => {
        const modal = document.getElementById('results-modal');
        if (modal) modal.classList.remove('show');
    });
    const closeSaved = document.querySelector('.close-saved-translation');
    if (closeSaved) closeSaved.addEventListener('click', () => {
        const m = document.getElementById('saved-translation-modal');
        if (m) { m.classList.remove('show'); m.classList.add('hidden'); }
    });
}

// ---- Connection Test ----
async function testConnection() {
    const dot = document.getElementById('conn-dot');
    const text = document.getElementById('conn-text');
    if (!dot || !text) return;
    
    dot.className = 'conn-dot';
    text.textContent = 'Connecting...';
    
    try {
        const response = await fetch('/api/test-connection');
        const data = await response.json();
        
        if (data.success && data.intercom) {
            dot.className = 'conn-dot connected';
            text.textContent = `Connected (${data.articles_count} articles)`;
        } else {
            throw new Error(data.error || 'Connection failed');
        }
    } catch (error) {
        dot.className = 'conn-dot error';
        text.textContent = 'Disconnected';
    }
}

// ---- Dashboard Data ----
async function loadDashboardData() {
    // Fetch stats and costs in parallel — stats render instantly, costs fill in when ready
    const statsPromise = fetch('/api/dashboard/stats').then(r => r.ok ? r.json() : null).catch(() => null);
    const costsPromise = fetch('/api/dashboard/costs').then(r => r.ok ? r.json() : null).catch(() => null);

    // Render stats as soon as they arrive (non-cost cards, changes chart, articles, activity)
    const statsData = await statsPromise;
    if (statsData && statsData.success) {
        state.dashboardStats = statsData;
        renderDashboard(statsData);
    } else {
        renderDashboard(getPlaceholderStats());
    }

    // Render cost data when it arrives (API Cost card + Cost Analysis chart)
    const costsData = await costsPromise;
    if (costsData && costsData.success) {
        Object.assign(state.dashboardStats, costsData);
        renderCostData(costsData);
    }
}

function getPlaceholderStats() {
    return {
        success: true,
        total_articles: 0,
        total_translated: 0,
        changed_this_week: 0,
        changed_this_month: 0,
        cost_week: 0,
        cost_month: 0,
        top_articles: [],
        recent_activities: [],
        changes_weekly: [0, 0, 0, 0, 0, 0, 0],
        changes_monthly: [],
        cost_weekly: [0, 0, 0, 0, 0, 0, 0],
        cost_monthly: []
    };
}

function renderDashboard(data) {
    // Stat cards
    setStatValue('stat-total-articles', formatNumber(data.total_articles || 0));
    setStatValue('stat-translated', formatNumber(data.total_translated || 0));
    // Source changes: show 7d or 30d based on toggle state
    window._sourceChangesRange = window._sourceChangesRange || '7d';
    if (window._sourceChangesRange === '30d') {
        setStatValue('stat-changed-week', formatNumber(data.changed_this_month || 0));
    } else {
        setStatValue('stat-changed-week', formatNumber(data.changed_this_week || 0));
    }
    // Last synced
    const syncEl = document.getElementById('dash-last-synced');
    if (syncEl) syncEl.textContent = 'Last synced: ' + (data.last_synced || '—');

    // Charts — only render changes chart here; cost chart rendered by renderCostData
    renderChangesChart('week', data);

    // Ranking table
    renderRankingTable(data.top_articles || []);

    // Recent activity
    renderActivityFeed(data.recent_activities || []);
}

function renderCostData(data) {
    // API Cost (All Time) card
    if (data.cost_all_time !== undefined) {
        setStatValue('stat-cost-month', '$' + data.cost_all_time.toFixed(2));
    }
    // Cost Analysis chart
    renderCostChart('week', data);
}

function toggleSourceChangesRange() {
    window._sourceChangesRange = window._sourceChangesRange === '7d' ? '30d' : '7d';
    const label = document.getElementById('stat-changed-label');
    if (label) {
        label.textContent = window._sourceChangesRange === '30d' ? 'Source Changes (30 Days)' : 'Source Changes (7 Days)';
    }
    if (state.dashboardStats) renderDashboard(state.dashboardStats);
}

function setStatValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function formatNumber(n) {
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return n.toString();
}

// ---- Charts ----
function renderChangesChart(period, data) {
    data = data || state.dashboardStats || getPlaceholderStats();
    const ctx = document.getElementById('changesChart');
    if (!ctx) return;

    if (state.changesChart) {
        state.changesChart.destroy();
    }

    let labels, values;
    if (period === 'month') {
        labels = data.changes_monthly_labels || generateMonthLabels();
        values = data.changes_monthly || generateZeros(labels.length);
        } else {
        labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        values = data.changes_weekly || [0, 0, 0, 0, 0, 0, 0];
    }

    state.changesChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Source Article Changes',
                data: values,
                backgroundColor: 'rgba(37, 99, 235, 0.15)',
                borderColor: '#2563eb',
                borderWidth: 2,
                borderRadius: 6,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 20 } },
            plugins: {
                legend: { display: false },
                datalabels: {
                    display: true,
                    anchor: 'end',
                    align: 'top',
                    color: '#2563eb',
                    font: { size: 11, weight: '600' },
                    formatter: function(v) { return v > 0 ? v : ''; }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grace: '15%',
                    ticks: { stepSize: 1, font: { size: 11 }, color: '#94a3b8' },
                    grid: { color: '#f1f5f9' }
                },
                x: {
                    ticks: { font: { size: 11 }, color: '#94a3b8' },
                    grid: { display: false }
                }
            }
        }
    });
}

function renderCostChart(period, data) {
    data = data || state.dashboardStats || getPlaceholderStats();
    const ctx = document.getElementById('costChart');
    if (!ctx) return;

    if (state.costChart) {
        state.costChart.destroy();
    }

    let labels, currentValues, previousValues;
    if (period === 'month') {
        labels = data.cost_monthly_labels || generateMonthLabels();
        currentValues = data.cost_monthly || generateZeros(labels.length);
        previousValues = generateZeros(labels.length);
    } else {
        labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        currentValues = data.cost_weekly || [0, 0, 0, 0, 0, 0, 0];
        previousValues = data.cost_prev_weekly || [0, 0, 0, 0, 0, 0, 0];
    }

    // Create gradient fill for "This period" line
    const chartCtx = ctx.getContext('2d');
    const gradient = chartCtx.createLinearGradient(0, 0, 0, 260);
    gradient.addColorStop(0, 'rgba(45, 130, 150, 0.25)');
    gradient.addColorStop(0.6, 'rgba(45, 130, 150, 0.06)');
    gradient.addColorStop(1, 'rgba(45, 130, 150, 0)');

    state.costChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: period === 'month' ? 'This month' : 'This week',
                    data: currentValues,
                    borderColor: '#2d8296',
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#ffffff',
                    pointBorderColor: '#2d8296',
                    pointBorderWidth: 2.5,
                    pointRadius: 4,
                    pointHoverRadius: 7,
                    pointHoverBackgroundColor: '#2d8296',
                    pointHoverBorderColor: '#ffffff',
                    pointHoverBorderWidth: 2,
                    borderWidth: 2.5
                },
                {
                    label: period === 'month' ? 'Last month' : 'Last week',
                    data: previousValues,
                    borderColor: '#94a3b8',
                    backgroundColor: 'transparent',
                    fill: false,
                    tension: 0.4,
                    pointBackgroundColor: '#ffffff',
                    pointBorderColor: '#94a3b8',
                    pointBorderWidth: 2,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    pointHoverBackgroundColor: '#94a3b8',
                    pointHoverBorderColor: '#ffffff',
                    pointHoverBorderWidth: 2,
                    borderWidth: 1.5,
                    borderDash: [5, 5]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    align: 'end',
                    labels: {
                        usePointStyle: true,
                        pointStyle: 'rectRounded',
                        padding: 16,
                        font: { size: 12, weight: '600' },
                        color: '#64748b',
                        boxWidth: 14,
                        boxHeight: 10
                    }
                },
                tooltip: {
                    backgroundColor: '#1a2742',
                    titleColor: '#e2e8f0',
                    bodyColor: '#ffffff',
                    titleFont: { size: 12, weight: '600' },
                    bodyFont: { size: 13, weight: '700' },
                    padding: { top: 10, bottom: 10, left: 14, right: 14 },
                    cornerRadius: 10,
                    displayColors: true,
                    boxPadding: 6,
                    callbacks: {
                        label: function(context) {
                            return ' ' + context.dataset.label + ':  $' + (context.parsed.y || 0).toFixed(2);
                        }
                    }
                },
                datalabels: {
                    display: true,
                    anchor: 'end',
                    align: 'top',
                    font: { size: 10, weight: '600' },
                    formatter: function(v) { return v > 0 ? '$' + v.toFixed(2) : ''; },
                    color: function(context) { return context.datasetIndex === 0 ? '#2d8296' : '#94a3b8'; }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: v => '$' + v.toFixed(2),
                        font: { size: 11, weight: '500' },
                        color: '#94a3b8',
                        padding: 8
                    },
                    grid: {
                        color: '#f0f3f8',
                        drawBorder: false
                    },
                    border: { display: false }
                },
                x: {
                    ticks: {
                        font: { size: 11, weight: '500' },
                        color: '#94a3b8',
                        padding: 6
                    },
                    grid: { display: false },
                    border: { display: false }
                }
            }
        }
    });
}

function generateMonthLabels() {
    const labels = [];
    for (let i = 4; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i * 7);
        labels.push(`W${Math.ceil(d.getDate() / 7)}`);
    }
    return labels;
}

function generateZeros(n) {
    return Array(n).fill(0);
}

// ---- Ranking Table ----
function renderRankingTable(articles) {
    const tbody = document.getElementById('ranking-table-body');
    if (!tbody) return;

    if (!articles || articles.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" class="empty-cell">No recently updated articles found.</td></tr>';
        return;
    }

    tbody.innerHTML = '';
    articles.forEach((article, index) => {
        const rank = index + 1;
        let rankClass = 'rank-default';
        if (rank === 1) rankClass = 'rank-1';
        else if (rank === 2) rankClass = 'rank-2';
        else if (rank === 3) rankClass = 'rank-3';

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><span class="rank-number ${rankClass}">${rank}</span></td>
            <td class="article-name-cell" title="${escapeHtml(article.title || '')}">${escapeHtml(article.title || 'Untitled')}</td>
            <td style="font-size:12px;color:var(--steel);">${article.last_updated || '--'}</td>
        `;
        tbody.appendChild(tr);
    });
}

// ---- Activity Feed ----
function renderActivityFeed(activities) {
    const feed = document.getElementById('activity-feed');
    if (!feed) return;

    if (!activities || activities.length === 0) {
        feed.innerHTML = '<div class="activity-empty">No recent activities. Start pulling and translating articles to see activity here.</div>';
        return;
    }
    
    feed.innerHTML = '';
    activities.forEach(activity => {
        const iconMap = {
            'translate': 'activity-icon-translate',
            'pull': 'activity-icon-pull',
            'push': 'activity-icon-push',
            'sync': 'activity-icon-sync'
        };
        const faMap = {
            'translate': 'fa-exchange-alt',
            'pull': 'fa-cloud-download-alt',
            'push': 'fa-cloud-upload-alt',
            'sync': 'fa-sync-alt'
        };

        const type = activity.type || 'sync';
        const iconClass = iconMap[type] || 'activity-icon-sync';
        const faClass = faMap[type] || 'fa-sync-alt';

                const item = document.createElement('div');
        item.className = 'activity-item';
                item.innerHTML = `
            <div class="activity-icon-wrap ${iconClass}">
                <i class="fas ${faClass}"></i>
            </div>
            <div class="activity-body">
                <div class="activity-text">${activity.text || ''}</div>
                <div class="activity-time">${activity.time || ''}</div>
            </div>
        `;
        feed.appendChild(item);
    });
}

// ---- Utility ----
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ---- Results Modal (kept for translate flow) ----
function showResults(results) {
    const modal = document.getElementById('results-modal');
    const content = document.getElementById('results-content');
    if (!modal || !content) return;
    
    const stats = results.stats || {};
    const resultItems = results.results || [];
    
    let html = `
        <div class="results-item">
            <div class="results-title">Summary</div>
            <div class="results-details">
                Articles processed: ${stats.articles_processed || 0}<br>
                Translations created/updated: ${stats.translations_created || 0}<br>
                Errors: ${stats.errors ? stats.errors.length : 0}
            </div>
        </div>
    `;
    
    resultItems.forEach(result => {
        const successCount = Object.values(result.translations || {}).filter(v => typeof v === 'string' && v.startsWith('success')).length;
        const errorCount = result.errors ? result.errors.length : 0;
        
        html += `
            <div class="results-item ${errorCount > 0 ? 'error' : ''}">
                <div class="results-title">${escapeHtml(result.article_title)}</div>
                <div class="results-details">
                    Successfully translated: ${successCount} language(s)<br>
                    ${errorCount > 0 ? 'Errors: ' + errorCount : 'No errors'}
                </div>
            </div>
        `;
    });
    
    content.innerHTML = html;
    modal.classList.add('show');
}


// ============================================================
// PULL MODULE
// ============================================================

async function initPullSection() {
    state.pull.loaded = true;
    setupPullEventListeners();
    await checkPullTableStatus();
}

function setupPullEventListeners() {
    // Sync source list
    const syncBtn = document.getElementById('pull-sync-btn');
    if (syncBtn) syncBtn.addEventListener('click', pullSyncSource);

    // Pull selected
    const pullBtn = document.getElementById('pull-selected-btn');
    if (pullBtn) pullBtn.addEventListener('click', pullSelectedArticles);

    // Pull confirmation modal buttons
    document.getElementById('pull-confirm-close')?.addEventListener('click', pullHideConfirm);
    document.getElementById('pull-confirm-cancel')?.addEventListener('click', pullHideConfirm);
    document.getElementById('pull-confirm-go')?.addEventListener('click', pullExecuteConfirmed);

    // Search
    const searchInput = document.getElementById('pull-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(state.pull.searchTimeout);
            state.pull.searchTimeout = setTimeout(() => {
                state.pull.search = searchInput.value.trim();
                state.pull.page = 1;
                loadPullArticles();
            }, 400);
        });
    }

    // Status filter
    const statusFilter = document.getElementById('pull-status-filter');
    if (statusFilter) {
        statusFilter.addEventListener('change', () => {
            state.pull.statusFilter = statusFilter.value;
            state.pull.page = 1;
            loadPullArticles();
            updatePullStatusBadges();
        });
    }

    // Stat mini card click handlers — filter by clicking the cards
    const pullStatCards = {
        'pull-chip-uptodate': 'up_to_date',
        'pull-chip-needsupdate': 'needs_update',
        'pull-chip-never': 'never_pulled',
        'pull-chip-failed': 'failed',
    };
    Object.entries(pullStatCards).forEach(([id, filterVal]) => {
        const card = document.getElementById(id);
        if (card) card.addEventListener('click', () => {
            // Toggle: click same filter again to clear
            if (state.pull.statusFilter === filterVal) {
                state.pull.statusFilter = '';
                if (statusFilter) statusFilter.value = '';
            } else {
                state.pull.statusFilter = filterVal;
                if (statusFilter) statusFilter.value = filterVal;
            }
            state.pull.page = 1;
            loadPullArticles();
        });
    });

    // Page size
    const pageSize = document.getElementById('pull-page-size');
    if (pageSize) {
        pageSize.addEventListener('change', () => {
            state.pull.pageSize = parseInt(pageSize.value) || 25;
            state.pull.page = 1;
            loadPullArticles();
        });
    }

    // Select all
    const selectAll = document.getElementById('pull-select-all');
    if (selectAll) {
        selectAll.addEventListener('change', () => {
            const checked = selectAll.checked;
            state.pull.articles.forEach(a => {
                if (checked) {
                    state.pull.selectedIds.add(a.intercom_id);
        } else {
                    state.pull.selectedIds.delete(a.intercom_id);
                }
            });
            renderPullTable();
            updatePullSelectedCount();
        });
    }

    // Pagination is rendered dynamically in renderPullPagination()

    // Setup buttons
    const copyBtn = document.getElementById('copy-setup-sql-btn');
    if (copyBtn) copyBtn.addEventListener('click', () => {
        const sql = document.getElementById('pull-setup-sql');
        if (sql) {
            navigator.clipboard.writeText(sql.textContent).then(() => {
                copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                setTimeout(() => { copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy SQL'; }, 2000);
            });
        }
    });

    const verifyBtn = document.getElementById('verify-pull-setup-btn');
    if (verifyBtn) verifyBtn.addEventListener('click', checkPullTableStatus);

    const autoCreateBtn = document.getElementById('auto-create-table-btn');
    if (autoCreateBtn) autoCreateBtn.addEventListener('click', autoCreatePullTable);
}

async function autoCreatePullTable() {
    const btn = document.getElementById('auto-create-table-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="fn-loader-inline"></span> Creating...'; }
    try {
        const resp = await fetch('/api/pull/create-table', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        const data = await resp.json();
        if (data.success) {
            if (btn) btn.innerHTML = '<i class="fas fa-check"></i> Created!';
            await checkPullTableStatus();
        } else {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-magic"></i> Auto-Create Table'; }
            alert('Auto-create failed. Please copy the SQL below and run it in Supabase Dashboard > SQL Editor.\n\n' + (data.error || ''));
        }
    } catch (err) {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-magic"></i> Auto-Create Table'; }
        alert('Error: ' + err.message);
    }
}

async function checkPullTableStatus() {
    try {
        const resp = await fetch('/api/pull/status');
        const data = await resp.json();
        const banner = document.getElementById('pull-setup-banner');
        const statsBar = document.getElementById('pull-stats-bar');

        if (data.table_exists) {
            state.pull.tableExists = true;
            if (banner) banner.classList.add('hidden');
            if (statsBar) statsBar.style.display = '';
            await loadPullStats();
            await loadPullArticles();
            updatePullStatusBadges();
        } else {
            state.pull.tableExists = false;
            if (banner) {
                banner.classList.remove('hidden');
                const sqlPre = document.getElementById('pull-setup-sql');
                if (sqlPre && data.setup_sql) sqlPre.textContent = data.setup_sql;
            }
            if (statsBar) statsBar.style.display = 'none';
            const tbody = document.getElementById('pull-table-body');
            if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">Run the setup SQL first to enable the Pull module.</td></tr>';
        }
    } catch (err) {
        console.error('Pull status check failed:', err);
    }
}

async function loadPullStats() {
    try {
        const resp = await fetch('/api/pull/stats');
        const data = await resp.json();
        if (data.success) {
            const total = data.total || 0;
            const uptodate = data.up_to_date || 0;
            const needs = data.needs_update || 0;
            const never = data.never_pulled || 0;
            const failed = data.failed || 0;
            setVal('pull-stat-total', total);
            setVal('pull-stat-uptodate', uptodate);
            setVal('pull-stat-needsupdate', needs);
            setVal('pull-stat-never', never);
            setVal('pull-stat-failed', failed);
            // Update progress bars
            const setBar = (id, val) => { const el = document.getElementById(id); if (el) el.style.width = (total ? Math.round(val/total*100) : 0) + '%'; };
            setBar('pull-bar-uptodate', uptodate);
            setBar('pull-bar-needsupdate', needs);
            setBar('pull-bar-never', never);
            setBar('pull-bar-failed', failed);
        }
    } catch (err) {
        console.warn('Pull stats error:', err);
    }
}

function setVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function updatePullStatusBadges() {
    // No-op — stat mini cards don't need active state toggling
}

async function loadPullArticles() {
    if (!state.pull.tableExists) return;
    const tbody = document.getElementById('pull-table-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="empty-cell"><span class="fn-loader"></span> Loading...</td></tr>';

    try {
        const params = new URLSearchParams({
            page: state.pull.page,
            page_size: state.pull.pageSize,
        });
        if (state.pull.search) params.set('search', state.pull.search);
        if (state.pull.statusFilter) params.set('status_filter', state.pull.statusFilter);

        const resp = await fetch(`/api/pull/articles?${params}`);
        const data = await resp.json();
        
        if (data.success) {
            state.pull.articles = data.articles || [];
            state.pull.total = data.total || 0;
            renderPullTable();
            renderPullPagination();
            } else {
            if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="empty-cell" style="color:#dc2626;">${escapeHtml(data.error || 'Failed to load')}</td></tr>`;
        }
    } catch (err) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="empty-cell" style="color:#dc2626;">Error: ${escapeHtml(err.message)}</td></tr>`;
    }
}

function renderPullTable() {
    const tbody = document.getElementById('pull-table-body');
    if (!tbody) return;

    if (state.pull.articles.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">No articles found. Click <strong>Sync Source List</strong> to import articles from Intercom.</td></tr>';
        return;
    }

    tbody.innerHTML = '';
    state.pull.articles.forEach(article => {
        const iid = article.intercom_id;
        const checked = state.pull.selectedIds.has(iid);
        const needsPull = article.needs_pull || 'never_pulled';
        const isPulling = needsPull === 'pulling';
        const stateVal = (article.state || 'draft').toLowerCase();
        const stateCls = stateVal === 'published' ? 'pl-s-published' : 'pl-s-draft';

        const tr = document.createElement('tr');
        if (isPulling) tr.classList.add('row-pulling');

        tr.innerHTML = `
            <td style="padding-left:18px"><input type="checkbox" class="pl-cb" data-iid="${iid}" ${checked ? 'checked' : ''} ${isPulling ? 'disabled' : ''}></td>
            <td><div class="pl-article-title" title="${escapeHtml(article.title || '')}">${escapeHtml(article.title || 'Untitled')}</div></td>
            <td>${renderPullBadge(needsPull)}</td>
            <td class="pl-td-center"><span class="pl-state-badge ${stateCls}">${escapeHtml(article.state || 'Draft')}</span></td>
            <td><span class="pl-dt">${formatPullDate(article.pulled_at)}</span></td>
            <td><span class="pl-dt-source">${formatPullDate(article.source_updated_at)}</span></td>
        `;

        const cb = tr.querySelector('input[type="checkbox"]');
        cb.addEventListener('change', () => {
            if (cb.checked) {
                state.pull.selectedIds.add(iid);
            } else {
                state.pull.selectedIds.delete(iid);
            }
            updatePullSelectedCount();
            const selectAll = document.getElementById('pull-select-all');
            if (selectAll) selectAll.checked = state.pull.articles.every(a => state.pull.selectedIds.has(a.intercom_id));
        });

        tbody.appendChild(tr);
    });

    const selectAll = document.getElementById('pull-select-all');
    if (selectAll) selectAll.checked = state.pull.articles.length > 0 && state.pull.articles.every(a => state.pull.selectedIds.has(a.intercom_id));

    updatePullSelectedCount();
}

function renderPullBadge(status) {
    const map = {
        'up_to_date':        '<span class="pl-badge pl-b-uptodate"><div class="pl-badge-dot"></div>Up to Date</span>',
        'updated_in_source': '<span class="pl-badge pl-b-needsupdate"><div class="pl-badge-dot"></div>Needs Update</span>',
        'never_pulled':      '<span class="pl-badge pl-b-never"><div class="pl-badge-dot"></div>Never Pulled</span>',
        'failed':            '<span class="pl-badge pl-b-failed"><div class="pl-badge-dot"></div>Pull Failed</span>',
        'pulling':           '<span class="pl-badge pl-b-pulling"><div class="pl-badge-dot"></div>Pulling…</span>',
    };
    return map[status] || map['never_pulled'];
}

function formatPullDate(isoStr) {
    if (!isoStr) return '<span style="color:#93C5E0;font-style:italic">—</span>';
    try {
        const d = new Date(isoStr);
        const now = new Date();
        const diff = now - d;
        // If less than 24h, show relative
        if (diff < 86400000 && diff >= 0) {
            if (diff < 60000) return 'Just now';
            if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
            return Math.floor(diff / 3600000) + 'h ago';
        }
        // Otherwise show date
        const month = d.toLocaleString('en', { month: 'short' });
        const day = d.getDate();
        const year = d.getFullYear();
        const hours = d.getHours().toString().padStart(2, '0');
        const mins = d.getMinutes().toString().padStart(2, '0');
        return `${month} ${day}, ${year} ${hours}:${mins}`;
    } catch {
        return isoStr.slice(0, 16);
    }
}

function renderPullPagination() {
    const maxPage = Math.ceil(state.pull.total / state.pull.pageSize) || 1;
    const cur = state.pull.page;
    const infoEl = document.getElementById('pull-page-info');
    const btnsEl = document.getElementById('pull-page-btns');

    if (infoEl) {
        const from = state.pull.total === 0 ? 0 : (cur - 1) * state.pull.pageSize + 1;
        const to = Math.min(cur * state.pull.pageSize, state.pull.total);
        infoEl.textContent = `Showing ${from} – ${to}  of  ${state.pull.total} articles  ·  Page ${cur} of ${maxPage}`;
    }

    if (!btnsEl) return;
    btnsEl.innerHTML = '';

    const mkBtn = (label, page, active) => {
        const b = document.createElement('button');
        b.className = 'pl-page-btn' + (active ? ' active' : '');
        b.textContent = label;
        if (page && page !== cur) {
            b.addEventListener('click', () => { state.pull.page = page; loadPullArticles(); });
        }
        return b;
    };

    // Prev
    if (cur > 1) btnsEl.appendChild(mkBtn('← Prev', cur - 1, false));

    // Page numbers with ellipsis
    const pages = [];
    pages.push(1);
    if (cur > 3) pages.push('…');
    for (let i = Math.max(2, cur - 1); i <= Math.min(maxPage - 1, cur + 1); i++) pages.push(i);
    if (cur < maxPage - 2) pages.push('…');
    if (maxPage > 1) pages.push(maxPage);

    pages.forEach(p => {
        if (p === '…') {
            const dots = document.createElement('button');
            dots.className = 'pl-page-btn';
            dots.textContent = '···';
            dots.style.cursor = 'default';
            btnsEl.appendChild(dots);
        } else {
            btnsEl.appendChild(mkBtn(String(p), p, p === cur));
        }
    });

    // Next
    if (cur < maxPage) btnsEl.appendChild(mkBtn('Next →', cur + 1, false));
}

function updatePullSelectedCount() {
    const countEl = document.getElementById('pull-selected-count');
    const btn = document.getElementById('pull-selected-btn');
    const n = state.pull.selectedIds.size;
    if (countEl) countEl.textContent = n;
    if (btn) btn.disabled = n === 0;
}

// ---- Sync Source List ----
async function pullSyncSource() {
    const btn = document.getElementById('pull-sync-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="fn-loader-inline"></span> &nbsp;Syncing...'; }
    showPullToast('Syncing article list from Intercom...', 'loading');

    try {
        const resp = await fetch('/api/pull/sync-source', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        const data = await resp.json();

        if (data.success) {
            showPullToast(`Synced ${data.synced} articles from Intercom.`, 'success');
            await loadPullStats();
            await loadPullArticles();
        } else {
            showPullToast('Sync failed: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (err) {
        showPullToast('Sync failed: ' + err.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '⚡ &nbsp;Sync Source List'; }
    }
}

// ---- Pull Selected Articles ----
function pullSelectedArticles() {
    const ids = Array.from(state.pull.selectedIds);
    if (ids.length === 0) { alert('Select at least one article to pull.'); return; }

    // Show styled confirmation modal
    pullShowConfirm(ids);
}

function pullShowConfirm(ids) {
    state.pull._pendingPullIds = ids;
    const body = document.getElementById('pull-confirm-body');
    if (body) {
        body.innerHTML = `
            <p>Pull full content for <strong>${ids.length}</strong> article${ids.length !== 1 ? 's' : ''} from Intercom?</p>
            <p style="color:#64748b;font-size:13px;margin-top:8px;">This will fetch and store the latest body/title for the selected article${ids.length !== 1 ? 's' : ''}.</p>
        `;
    }
    document.getElementById('pull-confirm-overlay')?.classList.remove('hidden');
}

function pullHideConfirm() {
    document.getElementById('pull-confirm-overlay')?.classList.add('hidden');
    state.pull._pendingPullIds = null;
}

async function pullExecuteConfirmed() {
    const ids = state.pull._pendingPullIds || [];
    if (ids.length === 0) { pullHideConfirm(); return; }
    pullHideConfirm();

    const btn = document.getElementById('pull-selected-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="fn-loader-inline"></span> &nbsp;Pulling...'; }
    showPullToast(`Pulling ${ids.length} article(s)...`, 'loading');

    try {
        const resp = await fetch('/api/pull/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ intercom_ids: ids }),
        });
        const data = await resp.json();

        if (data.success) {
            const msg = `Pulled ${data.pulled} article(s)` + (data.failed > 0 ? `, ${data.failed} failed` : '');
            showPullToast(msg, data.failed > 0 ? 'error' : 'success');
            state.pull.selectedIds.clear();
            await loadPullStats();
            await loadPullArticles();
            // Refresh Content Hub in background so health status updates
            if (state.hub.loaded) loadHubArticles();
        } else {
            showPullToast('Pull failed: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (err) {
        showPullToast('Pull failed: ' + err.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '⬇️ &nbsp;Pull Selected &nbsp;<span class="pl-btn-count" id="pull-selected-count">0</span>'; }
        updatePullSelectedCount();
    }
}

// ---- Toast Helper ----
function showPullToast(message, type) {
    const toast = document.getElementById('pull-toast');
    const icon = document.getElementById('pull-toast-icon');
    const text = document.getElementById('pull-toast-text');
    if (!toast) return;

    toast.className = 'pull-toast';
    if (type === 'success') {
        toast.classList.add('toast-success');
        if (icon) { icon.className = ''; icon.textContent = '✅'; }
    } else if (type === 'error') {
        toast.classList.add('toast-error');
        if (icon) { icon.className = ''; icon.textContent = '❌'; }
    } else {
        if (icon) { icon.className = ''; icon.innerHTML = '<span class="fn-loader-inline"></span>'; }
    }
    if (text) text.textContent = message;

    // Auto-hide after 5s for success/error
    if (type === 'success' || type === 'error') {
        setTimeout(() => { toast.classList.add('hidden'); }, 5000);
    }
}


// ============================================================
// CONTENT HUB MODULE
// ============================================================

async function initContentHub() {
    state.hub.loaded = true;
    setupHubEventListeners();
    await loadHubArticles();
}

function setupHubEventListeners() {
    // Filter tabs (new navy design)
    document.querySelectorAll('.ch-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.ch-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            state.hub.healthFilter = tab.getAttribute('data-health');
            state.hub.page = 1;
            loadHubArticles();
        });
    });

    // Search
    const searchInput = document.getElementById('ch-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(state.hub.searchTimeout);
            state.hub.searchTimeout = setTimeout(() => {
                state.hub.search = searchInput.value.trim();
                state.hub.page = 1;
                loadHubArticles();
            }, 400);
        });
    }

    // Sort
    const sortSelect = document.getElementById('ch-sort-select');
    if (sortSelect) {
        sortSelect.addEventListener('change', () => {
            state.hub.sortBy = sortSelect.value;
            state.hub.page = 1;
            loadHubArticles();
        });
    }

    // Page size
    const pageSizeSelect = document.getElementById('ch-page-size');
    if (pageSizeSelect) {
        pageSizeSelect.addEventListener('change', () => {
            state.hub.pageSize = parseInt(pageSizeSelect.value) || 25;
            state.hub.page = 1;
            loadHubArticles();
        });
    }

    // Select all
    const selectAll = document.getElementById('ch-select-all');
    if (selectAll) {
        selectAll.addEventListener('change', () => {
            const checked = selectAll.checked;
            state.hub.articles.forEach(a => {
                const sid = String(a.intercom_id);
                if (checked) {
                    state.hub.selectedIds.add(sid);
                    state.hub.selectedMeta[sid] = { title: a.title || '', intercom_id: sid };
                } else {
                    state.hub.selectedIds.delete(sid);
                    delete state.hub.selectedMeta[sid];
                }
            });
            renderHubTable();
            updateHubBulkBar();
        });
    }

    // Pagination is now handled dynamically in renderHubPagination()

    // Drawer close
    const drawerClose = document.getElementById('ch-drawer-close');
    const drawerOverlay = document.getElementById('ch-drawer-overlay');
    if (drawerClose) drawerClose.addEventListener('click', closeHubDrawer);
    if (drawerOverlay) drawerOverlay.addEventListener('click', closeHubDrawer);

    // Bulk actions
    const bulkPull = document.getElementById('ch-bulk-pull');
    if (bulkPull) bulkPull.addEventListener('click', () => hubBulkAction('pull'));
    const bulkTranslate = document.getElementById('ch-bulk-translate');
    if (bulkTranslate) bulkTranslate.addEventListener('click', () => hubBulkAction('translate'));
    const bulkPush = document.getElementById('ch-bulk-push');
    if (bulkPush) bulkPush.addEventListener('click', () => hubBulkAction('push'));
}

async function loadHubArticles() {
    const tbody = document.getElementById('ch-table-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="empty-cell"><span class="fn-loader"></span> Loading articles...</td></tr>';

    try {
        const params = new URLSearchParams({
            page: state.hub.page,
            page_size: state.hub.pageSize,
            sort: state.hub.sortBy,
        });
        if (state.hub.search) params.set('search', state.hub.search);
        if (state.hub.healthFilter && state.hub.healthFilter !== 'ALL') params.set('health', state.hub.healthFilter);

        const resp = await fetch(`/api/content-hub/articles?${params}`);
        const data = await resp.json();
        
        if (data.success) {
            state.hub.articles = data.articles || [];
            state.hub.total = data.total || 0;
            state.hub.totalWords = data.total_words || 0;
            state.hub.counts = data.counts || {};
            renderHubTable();
            renderHubPagination();
            updateHubFilterCounts();
            updateHubGlobalStats();
        } else {
            if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="empty-cell" style="color:#dc2626;">${escapeHtml(data.error || 'Failed to load')}</td></tr>`;
        }
    } catch (err) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="empty-cell" style="color:#dc2626;">Error: ${escapeHtml(err.message)}</td></tr>`;
    }
}

function renderHubTable() {
    const tbody = document.getElementById('ch-table-body');
    if (!tbody) return;

    if (state.hub.articles.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No articles match this filter. Try syncing from the <strong>Pull</strong> section first.</td></tr>';
        return;
    }
    
    tbody.innerHTML = '';
    state.hub.articles.forEach(article => {
        const iid = String(article.intercom_id);
        const checked = state.hub.selectedIds.has(iid);
        const health = article.health || 'NEEDS_PULL';
        const tr = document.createElement('tr');

        tr.innerHTML = `
            <td style="padding-left:18px"><input type="checkbox" class="ch-cb" data-iid="${iid}" ${checked ? 'checked' : ''}></td>
            <td class="ch-title-cell">
                <div class="ch-article-title" title="${escapeHtml(article.title || '')}">${escapeHtml(article.title || 'Untitled')}</div>
                <div class="ch-article-path">${article.collection_name ? escapeHtml(article.collection_name) + ' <span class="ch-breadcrumb-sep">›</span> Article' : 'Article'}</div>
            </td>
            <td><span class="ch-word-cell">${article.source_updated_relative || '—'}</span></td>
            <td class="ch-th-center">${article.pulled ? '<span class="ch-pulled-yes">✓</span>' : '<span class="ch-pulled-no">✗</span>'}</td>
            <td>${renderLangChips(article.lang_statuses || {})}</td>
            <td>${renderHealthBadge(health)}</td>
            <td class="ch-th-center">${state.hub.healthFilter === 'ARCHIVED'
                ? `<button class="ch-unarchive-btn" data-iid="${iid}" title="Unarchive this article"><i class="fas fa-undo-alt"></i></button>`
                : `<button class="ch-archive-btn" data-iid="${iid}" title="Archive this article">🗄</button>`
            }</td>
        `;

        // Archive / Unarchive button
        const archiveBtn = tr.querySelector('.ch-archive-btn');
        const unarchiveBtn = tr.querySelector('.ch-unarchive-btn');
        if (archiveBtn) {
            archiveBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                hubArchiveSingle(iid, article.title || 'Untitled');
            });
        }
        if (unarchiveBtn) {
            unarchiveBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                hubUnarchiveSingle(iid, article.title || 'Untitled');
            });
        }

        // Checkbox
        const cb = tr.querySelector('input[type="checkbox"]');
        cb.addEventListener('click', (e) => e.stopPropagation());
        cb.addEventListener('change', () => {
            if (cb.checked) {
                state.hub.selectedIds.add(iid);
                state.hub.selectedMeta[iid] = { title: article.title || '', intercom_id: iid };
            } else {
                state.hub.selectedIds.delete(iid);
                delete state.hub.selectedMeta[iid];
            }
            updateHubBulkBar();
            const selectAll = document.getElementById('ch-select-all');
            if (selectAll) selectAll.checked = state.hub.articles.every(a => state.hub.selectedIds.has(String(a.intercom_id)));
        });

        // Row click → drawer
        tr.addEventListener('click', (e) => {
            if (e.target.tagName === 'INPUT') return;
            openHubDrawer(iid);
        });

        tbody.appendChild(tr);
    });

    // Update select-all state
    const selectAll = document.getElementById('ch-select-all');
    if (selectAll) selectAll.checked = state.hub.articles.length > 0 && state.hub.articles.every(a => state.hub.selectedIds.has(a.intercom_id));
}

function renderLangChips(langStatuses) {
    if (!langStatuses || Object.keys(langStatuses).length === 0) return '<span class="ch-word-cell">—</span>';
    const chipClass = {
        'NOT_STARTED': 'ch-lang-not-started',
        'TRANSLATED': 'ch-lang-translated',
        'APPROVED': 'ch-lang-approved',
        'PUSHED': 'ch-lang-pushed',
        'OUTDATED': 'ch-lang-outdated',
    };
    let html = '<div class="ch-lang-chips">';
    for (const [loc, status] of Object.entries(langStatuses)) {
        const cls = chipClass[status] || 'ch-lang-not-started';
        const short = loc.split('-')[0].toUpperCase();
        html += `<span class="ch-lang-chip ${cls}" title="${loc}: ${status}">${short}</span>`;
    }
    html += '</div>';
    return html;
}

function renderHealthBadge(health) {
    const map = {
        'NEEDS_PULL':        '<span class="ch-health-badge ch-health-NEEDS_PULL"><div class="ch-health-dot"></div>Needs Pull</span>',
        'OUTDATED':          '<span class="ch-health-badge ch-health-OUTDATED"><div class="ch-health-dot"></div>Outdated</span>',
        'NEEDS_TRANSLATION': '<span class="ch-health-badge ch-health-NEEDS_TRANSLATION"><div class="ch-health-dot"></div>Needs Translation</span>',
        'NEEDS_PUSH':        '<span class="ch-health-badge ch-health-NEEDS_PUSH"><div class="ch-health-dot"></div>Ready to Push</span>',
        'COMPLETE':          '<span class="ch-health-badge ch-health-COMPLETE"><div class="ch-health-dot"></div>Live</span>',
        'FAILED':            '<span class="ch-health-badge ch-health-FAILED"><div class="ch-health-dot"></div>Failed</span>',
    };
    return map[health] || map['NEEDS_PULL'];
}

function renderHubPagination() {
    const maxPage = Math.ceil(state.hub.total / state.hub.pageSize) || 1;
    const infoEl = document.getElementById('ch-page-info');
    const btnsEl = document.getElementById('ch-page-btns');

    if (infoEl) {
        const from = state.hub.total === 0 ? 0 : (state.hub.page - 1) * state.hub.pageSize + 1;
        const to = Math.min(state.hub.page * state.hub.pageSize, state.hub.total);
        infoEl.textContent = `Showing ${from} – ${to}  of  ${state.hub.total} articles  ·  Page ${state.hub.page} of ${maxPage}`;
    }
    if (!btnsEl) return;
    btnsEl.innerHTML = '';

    // Prev button
    const prevBtn = document.createElement('button');
    prevBtn.className = 'ch-page-btn';
    prevBtn.textContent = '← Prev';
    prevBtn.disabled = state.hub.page <= 1;
    prevBtn.addEventListener('click', () => { if (state.hub.page > 1) { state.hub.page--; loadHubArticles(); } });
    btnsEl.appendChild(prevBtn);

    // Page number buttons with ellipsis
    const pages = [];
    if (maxPage <= 7) {
        for (let i = 1; i <= maxPage; i++) pages.push(i);
    } else {
        pages.push(1);
        if (state.hub.page > 3) pages.push('...');
        for (let i = Math.max(2, state.hub.page - 1); i <= Math.min(maxPage - 1, state.hub.page + 1); i++) pages.push(i);
        if (state.hub.page < maxPage - 2) pages.push('...');
        pages.push(maxPage);
    }
    pages.forEach(p => {
        const btn = document.createElement('button');
        btn.className = 'ch-page-btn' + (p === state.hub.page ? ' ch-page-active' : '');
        btn.textContent = p;
        if (p === '...') { btn.disabled = true; btn.style.cursor = 'default'; }
        else btn.addEventListener('click', () => { state.hub.page = p; loadHubArticles(); });
        btnsEl.appendChild(btn);
    });

    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.className = 'ch-page-btn';
    nextBtn.textContent = 'Next →';
    nextBtn.disabled = state.hub.page >= maxPage;
    nextBtn.addEventListener('click', () => { if (state.hub.page < maxPage) { state.hub.page++; loadHubArticles(); } });
    btnsEl.appendChild(nextBtn);
}

function updateHubFilterCounts() {
    const c = state.hub.counts || {};
    const setCount = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val ?? 0; };
    setCount('ch-count-ALL', c.ALL || 0);
    setCount('ch-count-NEEDS_PULL', c.NEEDS_PULL || 0);
    setCount('ch-count-NEEDS_TRANSLATION', c.NEEDS_TRANSLATION || 0);
    setCount('ch-count-NEEDS_PUSH', c.NEEDS_PUSH || 0);
    setCount('ch-count-OUTDATED', c.OUTDATED || 0);
    setCount('ch-count-COMPLETE', c.COMPLETE || 0);
    setCount('ch-count-ARCHIVED', c.ARCHIVED || 0);
}

function updateHubGlobalStats() {
    const artEl = document.getElementById('ch-article-count-val');
    if (artEl) artEl.textContent = (state.hub.counts.ALL || state.hub.total || 0).toLocaleString();
}

function updateHubBulkBar() {
    const bar = document.getElementById('ch-bulk-bar');
    const countEl = document.getElementById('ch-bulk-count');
    const n = state.hub.selectedIds.size;

    if (n === 0) {
        if (bar) bar.classList.add('hidden');
            } else {
        if (bar) bar.classList.remove('hidden');
        if (countEl) countEl.textContent = n;
    }
}

// ---- Details Drawer ----
async function openHubDrawer(intercomId) {
    const drawer = document.getElementById('ch-drawer');
    const overlay = document.getElementById('ch-drawer-overlay');
    const body = document.getElementById('ch-drawer-body');
    if (!drawer || !overlay || !body) return;

    drawer.classList.remove('hidden');
    overlay.classList.remove('hidden');
    state.hub.drawerOpen = true;
    body.innerHTML = '<div style="text-align:center;padding:40px;"><span class="fn-loader"></span></div>';

    try {
        const resp = await fetch(`/api/content-hub/article/${intercomId}`);
        const data = await resp.json();
        if (!data.success || !data.article) {
            body.innerHTML = '<p style="color:#dc2626;">Failed to load article details.</p>';
            return;
        }
        renderDrawerContent(data.article);
    } catch (err) {
        body.innerHTML = `<p style="color:#dc2626;">Error: ${escapeHtml(err.message)}</p>`;
    }
}

function closeHubDrawer() {
    const drawer = document.getElementById('ch-drawer');
    const overlay = document.getElementById('ch-drawer-overlay');
    if (drawer) drawer.classList.add('hidden');
    if (overlay) overlay.classList.add('hidden');
    state.hub.drawerOpen = false;
}

function renderDrawerContent(article) {
    const body = document.getElementById('ch-drawer-body');
    const titleEl = document.getElementById('ch-drawer-title');
    if (!body) return;
    if (titleEl) titleEl.textContent = article.title || 'Article Details';

    let html = '';

    // --- Overview ---
    html += `<div class="ch-detail-section">
        <h4><i class="fas fa-info-circle"></i> Overview</h4>
        <div class="ch-detail-meta">
            <span class="ch-detail-label">Title</span>
            <span class="ch-detail-value">${escapeHtml(article.title || '')}</span>
            <span class="ch-detail-label">Path</span>
            <span class="ch-detail-value">${escapeHtml(article.collection_name || 'Uncategorized')} › Article</span>
            <span class="ch-detail-label">State</span>
            <span class="ch-detail-value" style="text-transform:capitalize">${escapeHtml(article.state || '—')}</span>
            <span class="ch-detail-label">Source Updated</span>
            <span class="ch-detail-value">${article.source_updated_relative || '—'}</span>
            <span class="ch-detail-label">Last Pulled</span>
            <span class="ch-detail-value">${article.pulled_relative || 'Never'}</span>
            <span class="ch-detail-label">Health</span>
            <span class="ch-detail-value">${renderHealthBadge(article.health)}</span>
        </div>
    </div>`;

    // --- Language Status ---
    if (article.languages && article.languages.length > 0) {
        html += `<div class="ch-detail-section">
            <h4><i class="fas fa-globe"></i> Language Status</h4>
            <table class="ch-drawer-lang-table">
                <thead><tr><th>Language</th><th>Status</th><th>Last Action</th></tr></thead>
                <tbody>`;
        article.languages.forEach(lang => {
            const statusCls = {
                'NOT_STARTED': 'ch-lang-not-started',
                'TRANSLATED': 'ch-lang-translated',
                'APPROVED': 'ch-lang-approved',
                'PUSHED': 'ch-lang-pushed',
                'OUTDATED': 'ch-lang-outdated',
            }[lang.status] || 'ch-lang-not-started';
            html += `<tr>
                <td>${escapeHtml(lang.language)}</td>
                <td><span class="ch-lang-chip ${statusCls}" style="font-size:11px;padding:3px 8px;">${lang.status.replace('_', ' ')}</span></td>
                <td style="font-size:12px;color:#94a3b8;">${lang.last_translated_relative || '—'}</td>
            </tr>`;
        });
        html += `</tbody></table></div>`;
    }

    // --- Activity Log ---
    if (article.activity && article.activity.length > 0) {
        html += `<div class="ch-detail-section">
            <h4><i class="fas fa-history"></i> Activity Log</h4>`;
        article.activity.forEach(act => {
            html += `<div class="ch-drawer-activity-item">
                <div class="ch-activity-icon" style="background:${act.color}22;color:${act.color};">
                    <i class="fas ${act.icon}"></i>
        </div>
                <div>
                    <span class="ch-activity-text">${act.action}</span>
                    <span class="ch-activity-time">${act.relative || ''}</span>
        </div>
            </div>`;
        });
        html += `</div>`;
    }

    // --- URL link ---
    if (article.url) {
        html += `<div class="ch-detail-section">
            <a href="${escapeHtml(article.url)}" target="_blank" class="btn btn-small btn-secondary" style="width:100%;text-align:center;">
                <i class="fas fa-external-link-alt"></i> View on Intercom
            </a>
        </div>`;
    }

    body.innerHTML = html;
}

// ---- Bulk Actions ----
async function hubBulkAction(actionType) {
    const ids = Array.from(state.hub.selectedIds);
    if (ids.length === 0) return;

    // Get article title from selectedMeta (robust) or fallback to current articles
    let searchTitle = '';
    const firstId = ids[0];
    if (state.hub.selectedMeta[firstId]) {
        searchTitle = (state.hub.selectedMeta[firstId].title || '').substring(0, 40);
    } else {
        const selectedArticle = state.hub.articles.find(a => String(a.intercom_id) === String(firstId));
        searchTitle = selectedArticle ? (selectedArticle.title || '').substring(0, 40) : '';
    }

    if (actionType === 'pull') {
        // Only use search filter for single article; clear it for multi-select
        state.pull.search = ids.length === 1 ? searchTitle : '';
        state.pull.page = 1;

        switchSection('pull');

        // If already initialized, force reload with search
        if (state.pull.loaded && state.pull.tableExists) {
            await loadPullArticles();
        } else {
            await _waitForTableLoad('pull-table-body');
        }

        // Set search input value (only for single article)
        if (ids.length === 1 && searchTitle) {
            const searchInput = document.getElementById('pull-search-input');
            if (searchInput) searchInput.value = searchTitle;
        } else {
            const searchInput = document.getElementById('pull-search-input');
            if (searchInput) searchInput.value = '';
        }

        // Select the articles
        ids.forEach(id => state.pull.selectedIds.add(String(id)));
        updatePullSelectedCount();
        renderPullTable();

    } else if (actionType === 'translate') {
        // Only use search filter for single article; clear it for multi-select
        state.tr.search = ids.length === 1 ? searchTitle : '';
        state.tr.page = 1;

        switchSection('translate');

        // If already initialized, force reload with search
        if (state.tr.loaded) {
            await trLoadArticles();
        } else {
            await _waitForTableLoad('tr-table-body');
        }

        // Set search input value (only for single article)
        if (ids.length === 1 && searchTitle) {
            const searchInput = document.getElementById('tr-search-input');
            if (searchInput) searchInput.value = searchTitle;
        } else {
            const searchInput = document.getElementById('tr-search-input');
            if (searchInput) searchInput.value = '';
        }

        // Select the articles
        ids.forEach(id => state.tr.selectedArticles.add(String(id)));
        trUpdateActionBar();
        trRenderTable();

    } else if (actionType === 'push') {
        // Only use search filter for single article; clear it for multi-select
        // so all selected articles appear in the table
        state.push.search = ids.length === 1 ? searchTitle : '';
        state.push.page = 1;

        const wasLoaded = state.push.loaded;
        switchSection('push');

        // Wait for init to finish if first visit (initPushSection is async)
        if (!wasLoaded) {
            await new Promise(resolve => {
                const check = () => state.push._initDone ? resolve() : setTimeout(check, 100);
                check();
                setTimeout(resolve, 5000);
            });
        }

        // Force reload articles
        await pushLoadArticles();

        // Set search input value (only for single article)
        if (ids.length === 1 && searchTitle) {
            const searchInput = document.getElementById('push-search-input');
            if (searchInput) searchInput.value = searchTitle;
        } else {
            const searchInput = document.getElementById('push-search-input');
            if (searchInput) searchInput.value = '';
        }

        // Select the articles (normalize to string for consistent matching)
        ids.forEach(id => state.push.selectedIds.add(String(id)));
        pushUpdateJobCounter();
        pushUpdateActionButtons();
        pushRenderTable();
    }
}

// ---- Archive Selected Articles ----
async function hubArchiveSelected() {
    const ids = Array.from(state.hub.selectedIds);
    if (ids.length === 0) return;

    const count = ids.length;
    showConfirmModal({
        title: 'Confirm Archive',
        body: `<p><strong>Archive ${count} article${count > 1 ? 's' : ''}</strong> — they will be hidden from the application.</p><p style="margin-top:10px;font-size:13px;color:#4A90C4;">Archived articles can be restored later from the Archived filter.</p>`,
        confirmText: 'Archive',
        confirmIcon: 'fa-archive',
        onConfirm: async () => {
            const archiveBtn = document.getElementById('ch-bulk-archive');
            if (archiveBtn) { archiveBtn.disabled = true; archiveBtn.innerHTML = '<span class="fn-loader-inline"></span> Archiving...'; }
            try {
                const resp = await fetch('/api/content-hub/archive', {
                    method: 'POST',
                    headers: authHeaders(),
                    body: JSON.stringify({ intercom_ids: ids }),
                });
                const data = await resp.json();
                if (data.success) {
                    state.hub.selectedIds.clear();
                    state.hub.selectedMeta = {};
                    updateHubBulkBar();
                    await loadHubArticles();
                    showHubToast(`${data.archived} article${data.archived > 1 ? 's' : ''} archived successfully.`, 'success');
                } else {
                    showHubToast('Archive failed: ' + (data.error || 'Unknown error'), 'error');
                }
            } catch (err) {
                showHubToast('Archive failed: ' + err.message, 'error');
            } finally {
                if (archiveBtn) { archiveBtn.disabled = false; archiveBtn.innerHTML = '<i class="fas fa-archive"></i> Archive'; }
            }
        }
    });
}

async function hubArchiveSingle(intercomId, title) {
    showConfirmModal({
        title: 'Confirm Archive',
        body: `<p><strong>Archive "${escapeHtml(title)}"?</strong></p><p style="margin-top:8px;font-size:13px;color:#4A90C4;">It will be hidden from the application.</p>`,
        confirmText: 'Archive',
        confirmIcon: 'fa-archive',
        onConfirm: async () => {
            try {
                const resp = await fetch('/api/content-hub/archive', {
                    method: 'POST',
                    headers: authHeaders(),
                    body: JSON.stringify({ intercom_ids: [intercomId] }),
                });
                const data = await resp.json();
                if (data.success) {
                    state.hub.selectedIds.delete(intercomId);
                    delete state.hub.selectedMeta[intercomId];
                    updateHubBulkBar();
                    await loadHubArticles();
                    showHubToast('Article archived successfully.', 'success');
                } else {
                    showHubToast('Archive failed: ' + (data.error || 'Unknown error'), 'error');
                }
            } catch (err) {
                showHubToast('Archive failed: ' + err.message, 'error');
            }
        }
    });
}

async function hubUnarchiveSingle(intercomId, title) {
    showConfirmModal({
        title: 'Confirm Unarchive',
        body: `<p><strong>Unarchive "${escapeHtml(title)}"?</strong></p><p style="margin-top:8px;font-size:13px;color:#4A90C4;">It will be visible in the application again.</p>`,
        confirmText: 'Unarchive',
        confirmIcon: 'fa-undo-alt',
        onConfirm: async () => {
            try {
                const resp = await fetch('/api/content-hub/unarchive', {
                    method: 'POST',
                    headers: authHeaders(),
                    body: JSON.stringify({ intercom_ids: [intercomId] }),
                });
                const data = await resp.json();
                if (data.success) {
                    await loadHubArticles();
                    showHubToast('Article unarchived successfully.', 'success');
                } else {
                    showHubToast('Unarchive failed: ' + (data.error || 'Unknown error'), 'error');
                }
            } catch (err) {
                showHubToast('Unarchive failed: ' + err.message, 'error');
            }
        }
    });
}

function showHubToast(message, type) {
    // Reuse existing toast pattern or create simple one
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i> ${message}`;
    toast.style.cssText = 'position:fixed;top:20px;right:20px;z-index:10000;padding:12px 20px;border-radius:8px;color:#fff;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,0.15);transition:opacity 0.3s;';
    toast.style.background = type === 'success' ? '#22c55e' : '#ef4444';
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 3000);
}

// Helper: wait for a table to finish loading (spinner disappears)
function _waitForTableLoad(tbodyId) {
    return new Promise(resolve => {
        const check = () => {
            const tbody = document.getElementById(tbodyId);
            const hasSpinner = tbody && (tbody.querySelector('.fa-spinner') || tbody.querySelector('.fn-loader'));
            if (tbody && !hasSpinner) {
                resolve();
            } else {
                setTimeout(check, 200);
            }
        };
        setTimeout(check, 500);
        setTimeout(resolve, 8000);
    });
}


// =============================================================
// TRANSLATE MODULE
// =============================================================

function initTranslateSection() {
    state.tr.loaded = true;

    // Search
    const searchInput = document.getElementById('tr-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(state.tr.searchTimeout);
            state.tr.searchTimeout = setTimeout(() => {
                state.tr.search = searchInput.value.trim();
                state.tr.page = 1;
                trLoadArticles();
            }, 350);
        });
    }

    // Stat card clicks (filter)
    document.querySelectorAll('.tr-stat-card[data-status]').forEach(card => {
        card.addEventListener('click', () => {
            state.tr.statusFilter = card.dataset.status || 'ALL';
            state.tr.page = 1;
            // Instantly move active highlight before loading
            document.querySelectorAll('.tr-stat-card').forEach(c => {
                if (c.dataset.status === state.tr.statusFilter) {
                    c.classList.add('tr-s-active');
                } else {
                    c.classList.remove('tr-s-active');
                }
            });
            trLoadArticles();
        });
    });

    // Language filter dropdown
    const langFilter = document.getElementById('tr-lang-filter');
    if (langFilter) {
        langFilter.addEventListener('change', () => {
            state.tr.languageFilter = langFilter.value;
            state.tr.page = 1;
            trLoadArticles();
        });
    }

    // Sort
    const sortSelect = document.getElementById('tr-sort-select');
    if (sortSelect) {
        sortSelect.addEventListener('change', () => {
            state.tr.sortBy = sortSelect.value;
            state.tr.page = 1;
            trLoadArticles();
        });
    }

    // Page size
    const pageSizeSelect = document.getElementById('tr-page-size');
    if (pageSizeSelect) {
        pageSizeSelect.addEventListener('change', () => {
            state.tr.pageSize = parseInt(pageSizeSelect.value);
            state.tr.page = 1;
            trLoadArticles();
        });
    }

    // Select all checkbox
    const selectAll = document.getElementById('tr-select-all');
    if (selectAll) {
        selectAll.addEventListener('change', () => {
            if (selectAll.checked) {
                state.tr.articles.forEach(a => state.tr.selectedArticles.add(a.intercom_id));
    } else {
                state.tr.selectedArticles.clear();
            }
            trRenderTable();
            trUpdateActionBar();
        });
    }

    // Pagination is handled dynamically in trRenderPagination()

    // Language picker toggle
    const langPickerBtn = document.getElementById('tr-lang-picker-btn');
    const langDropdown = document.getElementById('tr-lang-dropdown');
    if (langPickerBtn && langDropdown) {
        langPickerBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            langDropdown.classList.toggle('hidden');
        });
        document.addEventListener('click', (e) => {
            if (!langDropdown.contains(e.target) && e.target !== langPickerBtn) {
                langDropdown.classList.add('hidden');
            }
        });
    }

    // Select all languages
    const langSelectAll = document.getElementById('tr-lang-select-all');
    if (langSelectAll) {
        langSelectAll.addEventListener('change', () => {
            const checkboxes = document.querySelectorAll('#tr-lang-dropdown-list input[type="checkbox"]');
            checkboxes.forEach(cb => { cb.checked = langSelectAll.checked; });
            state.tr.selectedLanguages.clear();
            if (langSelectAll.checked) {
                Object.keys(state.tr.languages).forEach(loc => state.tr.selectedLanguages.add(loc));
            }
            trUpdateActionBar();
        });
    }

    // Translate Selected button
    const translateBtn = document.getElementById('tr-translate-btn');
    if (translateBtn) {
        translateBtn.addEventListener('click', () => {
            trShowConfirmModal();
        });
    }

    // Translate All Missing button
    const missingBtn = document.getElementById('tr-translate-missing-btn');
    if (missingBtn) {
        missingBtn.addEventListener('click', () => {
            trTranslateAllMissing();
        });
    }

    // Confirm modal buttons
    const confirmCancel = document.getElementById('tr-confirm-cancel');
    const confirmOk = document.getElementById('tr-confirm-ok');
    if (confirmCancel) confirmCancel.addEventListener('click', () => trHideConfirmModal());
    if (confirmOk) confirmOk.addEventListener('click', () => trExecuteBulkTranslate());

    // Drawer close
    const drawerClose = document.getElementById('tr-drawer-close');
    const drawerOverlay = document.getElementById('tr-drawer-overlay');
    if (drawerClose) drawerClose.addEventListener('click', trCloseDrawer);
    if (drawerOverlay) drawerOverlay.addEventListener('click', trCloseDrawer);

    trLoadArticles();
}


async function trLoadArticles() {
    const tbody = document.getElementById('tr-table-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="20" class="empty-cell"><span class="fn-loader"></span> Loading...</td></tr>';

    try {
        const params = new URLSearchParams({
            search: state.tr.search,
            page: state.tr.page,
            page_size: state.tr.pageSize,
            status: state.tr.statusFilter === 'ALL' ? '' : state.tr.statusFilter,
            language: state.tr.languageFilter,
            sort: state.tr.sortBy,
        });
        const resp = await fetch(`/api/translate-hub/articles?${params}`);
        const data = await resp.json();
        if (data.success) {
            state.tr.articles = data.articles || [];
            state.tr.total = data.total || 0;
            state.tr.counts = data.counts || {};
            state.tr.languages = data.languages || {};
            trPopulateLanguageDropdowns();
            trRenderFilterCounts();
            trRenderTable();
            trRenderPagination();
            // Update header stat
            const statEl = document.getElementById('tr-stat-articles');
            if (statEl) statEl.textContent = state.tr.counts.ALL || 0;
        } else {
            if (tbody) tbody.innerHTML = `<tr><td colspan="20" class="empty-cell">Error: ${escapeHtml(data.error || 'Unknown')}</td></tr>`;
        }
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="20" class="empty-cell">Network error: ${escapeHtml(e.message)}</td></tr>`;
    }
}


function trPopulateLanguageDropdowns() {
    const langs = state.tr.languages;
    // Language filter dropdown
    const langFilter = document.getElementById('tr-lang-filter');
    if (langFilter && langFilter.options.length <= 1) {
        for (const [loc, name] of Object.entries(langs)) {
            const opt = document.createElement('option');
            opt.value = loc;
            opt.textContent = `${name} (${loc})`;
            langFilter.appendChild(opt);
        }
    }

    // Language picker dropdown
    const langList = document.getElementById('tr-lang-dropdown-list');
    if (langList && langList.children.length === 0) {
        for (const [loc, name] of Object.entries(langs)) {
            const label = document.createElement('label');
            label.innerHTML = `<input type="checkbox" value="${loc}" class="tr-lang-cb"> ${escapeHtml(name)} (${loc})`;
            label.querySelector('input').addEventListener('change', (e) => {
                if (e.target.checked) {
                    state.tr.selectedLanguages.add(loc);
        } else {
                    state.tr.selectedLanguages.delete(loc);
                }
                trUpdateActionBar();
            });
            langList.appendChild(label);
        }
    }
}


function trRenderFilterCounts() {
    const c = state.tr.counts;
    const total = c.ALL || 1;
    const el = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
    const bar = (id, val) => { const e = document.getElementById(id); if (e) e.style.width = Math.min(100, Math.round((val / total) * 100)) + '%'; };

    const allVal = c.ALL || 0;
    const needsVal = c.NOT_STARTED || 0;
    const outdatedVal = c.OUTDATED || 0;
    const progressVal = c.IN_PROGRESS || 0;
    const completedVal = (c.TRANSLATED || 0) + (c.APPROVED || 0);
    const failedVal = c.FAILED || 0;

    el('tr-count-ALL', allVal);
    el('tr-count-NEEDS', needsVal);
    el('tr-count-OUTDATED', outdatedVal);
    el('tr-count-INPROGRESS', progressVal);
    el('tr-count-TRANSLATED', completedVal);
    el('tr-count-FAILED', failedVal);

    bar('tr-bar-ALL', allVal);
    bar('tr-bar-NEEDS', needsVal);
    bar('tr-bar-OUTDATED', outdatedVal);
    bar('tr-bar-INPROGRESS', progressVal);
    bar('tr-bar-TRANSLATED', completedVal);
    bar('tr-bar-FAILED', failedVal);

    // Zero-state styling
    const zeroMap = { 'tr-sc-progress': progressVal, 'tr-sc-failed': failedVal };
    document.querySelectorAll('.tr-stat-card').forEach(card => {
        const cls = Array.from(card.classList).find(c => c.startsWith('tr-sc-'));
        if (cls && zeroMap.hasOwnProperty(cls) && zeroMap[cls] === 0) {
            card.classList.add('tr-zero-state');
        } else {
            card.classList.remove('tr-zero-state');
        }
    });

    // Active card state based on current filter
    document.querySelectorAll('.tr-stat-card').forEach(card => {
        const status = card.dataset.status;
        if (status === state.tr.statusFilter) {
            card.classList.add('tr-s-active');
        } else {
            card.classList.remove('tr-s-active');
        }
    });
}


function trRenderTable() {
    const thead = document.getElementById('tr-table-head');
    const tbody = document.getElementById('tr-table-body');
    if (!thead || !tbody) return;

    const langs = Object.entries(state.tr.languages);
    const articles = state.tr.articles;

    // Build header
    let headHtml = `<tr>
        <th class="tr-th-check"><input type="checkbox" id="tr-select-all-hdr" title="Select all"></th>
        <th class="tr-th-title">Title</th>`;
    for (const [loc, name] of langs) {
        const shortName = name.split(' ')[0].substring(0, 4);
        headHtml += `<th class="tr-th-lang">
            <div class="tr-th-lang-header">
                <span class="tr-lang-code">${escapeHtml(loc.toUpperCase())}</span>
            </div>
        </th>`;
    }
    headHtml += `</tr>`;
    thead.innerHTML = headHtml;

    // Re-attach select all listener
    const selectAllHdr = document.getElementById('tr-select-all-hdr');
    if (selectAllHdr) {
        selectAllHdr.checked = articles.length > 0 && articles.every(a => state.tr.selectedArticles.has(a.intercom_id));
        selectAllHdr.addEventListener('change', () => {
            if (selectAllHdr.checked) {
                articles.forEach(a => state.tr.selectedArticles.add(a.intercom_id));
            } else {
                articles.forEach(a => state.tr.selectedArticles.delete(a.intercom_id));
            }
            trRenderTable();
            trUpdateActionBar();
        });
    }

    if (articles.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${2 + langs.length}" class="empty-cell">
            <i class="fas fa-language" style="font-size:2rem;color:var(--text-muted);margin-bottom:8px;display:block;"></i>
            No articles found. Pull articles first in the Pull section.
        </td></tr>`;
        return;
    }

    let bodyHtml = '';
    for (const a of articles) {
        const isSelected = state.tr.selectedArticles.has(a.intercom_id);
        const needsAttention = ['NOT_STARTED', 'OUTDATED', 'FAILED'].includes(a.row_status);
        const rowClass = needsAttention ? 'tr-attention' : '';

        bodyHtml += `<tr class="${rowClass}">
            <td style="padding-left:18px"><input type="checkbox" class="tr-row-cb" data-id="${a.intercom_id}" ${isSelected ? 'checked' : ''}></td>
            <td style="text-align:left;padding-left:18px">
                <div class="tr-article-title" data-id="${a.intercom_id}">${escapeHtml(a.title)}</div>
                <div class="tr-article-collection">${escapeHtml(a.collection_name || 'Uncategorized')}</div>
            </td>`;
        for (const [loc] of langs) {
            const st = (a.lang_statuses && a.lang_statuses[loc]) || 'NOT_STARTED';
            bodyHtml += `<td class="tr-cell-lang" data-iid="${a.intercom_id}" data-loc="${loc}">${trStatusChip(st)}</td>`;
        }
        bodyHtml += `</tr>`;
    }
    tbody.innerHTML = bodyHtml;

    // Row checkbox listeners
    tbody.querySelectorAll('.tr-row-cb').forEach(cb => {
        cb.addEventListener('change', () => {
            const id = cb.dataset.id;
            if (cb.checked) {
                state.tr.selectedArticles.add(id);
        } else {
                state.tr.selectedArticles.delete(id);
            }
            trUpdateActionBar();
            // Update header checkbox
            if (selectAllHdr) {
                selectAllHdr.checked = articles.length > 0 && articles.every(a => state.tr.selectedArticles.has(a.intercom_id));
            }
        });
    });

    // Title click -> drawer
    tbody.querySelectorAll('.tr-article-title').forEach(el => {
        el.addEventListener('click', () => {
            trOpenDrawer(el.dataset.id);
        });
    });
}


function trStatusChip(status) {
    const map = {
        'NOT_STARTED': { cls: 'not-started', label: 'NEW' },
        'IN_PROGRESS': { cls: 'in-progress', label: 'TRANSLATING' },
        'OUTDATED':    { cls: 'outdated', label: 'OUTDATED' },
        'TRANSLATED':  { cls: 'translated', label: 'DONE' },
        'APPROVED':    { cls: 'approved', label: 'DONE' },
        'FAILED':      { cls: 'failed', label: 'FAILED' },
    };
    const m = map[status] || map['NOT_STARTED'];
    return `<span class="tr-status-chip ${m.cls}">${m.label}</span>`;
}

function trSetCellStatus(iid, locale, status) {
    const cell = document.querySelector(`td.tr-cell-lang[data-iid="${iid}"][data-loc="${locale}"]`);
    if (cell) cell.innerHTML = trStatusChip(status);
}


function trRenderPagination() {
    const maxPage = Math.max(1, Math.ceil(state.tr.total / state.tr.pageSize));
    const current = state.tr.page;
    const info = document.getElementById('tr-page-info');
    const btnsWrap = document.getElementById('tr-page-btns');
    if (!btnsWrap) return;

    const start = (current - 1) * state.tr.pageSize + 1;
    const end = Math.min(current * state.tr.pageSize, state.tr.total);
    if (info) info.textContent = `Showing ${start} – ${end}  of  ${state.tr.total} articles  ·  Page ${current} of ${maxPage}`;

    // Build page buttons
    let btnsHtml = `<button class="tr-page-btn" id="tr-prev-btn" ${current <= 1 ? 'disabled' : ''}>← Prev</button>`;

    // Show up to 5 page numbers with ellipsis
    const pages = [];
    if (maxPage <= 7) {
        for (let i = 1; i <= maxPage; i++) pages.push(i);
    } else {
        pages.push(1);
        if (current > 3) pages.push('...');
        for (let i = Math.max(2, current - 1); i <= Math.min(maxPage - 1, current + 1); i++) pages.push(i);
        if (current < maxPage - 2) pages.push('...');
        pages.push(maxPage);
    }

    for (const p of pages) {
        if (p === '...') {
            btnsHtml += `<button class="tr-page-btn" disabled>···</button>`;
        } else {
            btnsHtml += `<button class="tr-page-btn ${p === current ? 'tr-page-active' : ''}" data-page="${p}">${p}</button>`;
        }
    }

    btnsHtml += `<button class="tr-page-btn" id="tr-next-btn" ${current >= maxPage ? 'disabled' : ''}>Next →</button>`;
    btnsWrap.innerHTML = btnsHtml;

    // Attach listeners
    const prevBtn = document.getElementById('tr-prev-btn');
    const nextBtn = document.getElementById('tr-next-btn');
    if (prevBtn) prevBtn.addEventListener('click', () => { if (state.tr.page > 1) { state.tr.page--; trLoadArticles(); } });
    if (nextBtn) nextBtn.addEventListener('click', () => { if (state.tr.page < maxPage) { state.tr.page++; trLoadArticles(); } });
    btnsWrap.querySelectorAll('[data-page]').forEach(btn => {
        btn.addEventListener('click', () => {
            const p = parseInt(btn.dataset.page);
            if (p !== current) { state.tr.page = p; trLoadArticles(); }
        });
    });
}


function trUpdateActionBar() {
    const articleCount = state.tr.selectedArticles.size;
    const langCount = state.tr.selectedLanguages.size;
    const combos = articleCount * langCount;

    const elArticles = document.getElementById('tr-sel-article-count');
    const elLangs = document.getElementById('tr-sel-lang-count');
    const elCombos = document.getElementById('tr-sel-combo-count');
    const translateBtn = document.getElementById('tr-translate-btn');
    const langBadge = document.getElementById('tr-lang-badge');

    if (elArticles) elArticles.textContent = articleCount;
    if (elLangs) elLangs.textContent = langCount;
    if (elCombos) elCombos.textContent = combos;
    if (translateBtn) translateBtn.disabled = combos === 0 || state.tr.translating;
    if (langBadge) langBadge.textContent = langCount;
}


// --- Confirm Modal ---

function trShowConfirmModal() {
    const articleCount = state.tr.selectedArticles.size;
    const langCount = state.tr.selectedLanguages.size;
    const combos = articleCount * langCount;

    if (combos === 0) return;

    // Block translation of outdated articles — they need re-pulling first
    const outdatedArticles = (state.tr.articles || []).filter(
        a => state.tr.selectedArticles.has(a.intercom_id) && a.row_status === 'OUTDATED'
    );
    if (outdatedArticles.length > 0) {
        const names = outdatedArticles.map(a => `<li>${escapeHtml(a.title)}</li>`).slice(0, 5).join('');
        const more = outdatedArticles.length > 5 ? `<li style="color:var(--text-muted);">...and ${outdatedArticles.length - 5} more</li>` : '';
        const overlay = document.getElementById('generic-confirm-overlay');
        const title = document.getElementById('generic-confirm-title');
        const body = document.getElementById('generic-confirm-body');
        const okBtn = document.getElementById('generic-confirm-ok');
        const cancelBtn = document.getElementById('generic-confirm-cancel');
        if (overlay && title && body) {
            title.innerHTML = '<i class="fas fa-exclamation-triangle" style="color:var(--warning);"></i> Cannot Translate Outdated Articles';
            body.innerHTML = `
                <p><strong>${outdatedArticles.length} article(s)</strong> have outdated source content. The source was updated on Intercom after the last pull.</p>
                <ul style="margin:10px 0;padding-left:20px;font-size:0.88rem;">${names}${more}</ul>
                <p style="margin-top:12px;font-size:0.82rem;color:var(--text-muted);">
                    <i class="fas fa-info-circle"></i> Please go to the <strong>Pull</strong> page and re-pull these articles first to get the latest source content, then translate.
                </p>
            `;
            if (okBtn) okBtn.style.display = 'none';
            if (cancelBtn) cancelBtn.textContent = 'OK';
            overlay.classList.remove('hidden');
            const closeHandler = () => {
                overlay.classList.add('hidden');
                if (okBtn) okBtn.style.display = '';
                if (cancelBtn) cancelBtn.textContent = 'Cancel';
            };
            cancelBtn.onclick = closeHandler;
            const closeBtn = document.getElementById('generic-confirm-close');
            if (closeBtn) closeBtn.onclick = closeHandler;
        }
        return;
    }

    const selectedLangNames = Array.from(state.tr.selectedLanguages).map(loc => {
        return state.tr.languages[loc] || loc;
    });

    const body = document.getElementById('tr-confirm-body');
    if (body) {
        body.innerHTML = `
            <div class="tr-modal-stat"><span class="tr-modal-stat-label">Articles</span><span class="tr-modal-stat-val">${articleCount}</span></div>
            <div class="tr-modal-stat"><span class="tr-modal-stat-label">Languages</span><span class="tr-modal-stat-val">${langCount}</span></div>
            <div class="tr-modal-stat"><span class="tr-modal-stat-label">Total Jobs</span><span class="tr-modal-stat-val">${combos}</span></div>
            <div style="margin-top:12px;font-size:0.82rem;color:var(--text-muted);">
                <strong>Languages:</strong> ${selectedLangNames.map(n => escapeHtml(n)).join(', ')}
            </div>
            <div style="margin-top:8px;font-size:0.78rem;color:var(--warning);">
                <i class="fas fa-info-circle"></i> Translation uses GPT-4o-mini. Processing ${combos} job(s) with concurrency limit of 3.
            </div>
        `;
    }

    document.getElementById('tr-confirm-overlay').classList.remove('hidden');
}

function trHideConfirmModal() {
    document.getElementById('tr-confirm-overlay').classList.add('hidden');
}


// Glossary enforcement is automatic: all active glossaries are applied during translation.

async function trExecuteBulkTranslate() {
    trHideConfirmModal();

    const articleIds = Array.from(state.tr.selectedArticles);
    const locales = Array.from(state.tr.selectedLanguages);
    if (articleIds.length === 0 || locales.length === 0) return;

    state.tr.translating = true;
    trUpdateActionBar();

    const totalJobs = articleIds.length * locales.length;
    let completed = 0, ok = 0, fail = 0;
    const origTitle = document.title;

    trShowToast(`Translating 0/${totalJobs}...`, 'fn-loader');
    document.title = `Translating 0/${totalJobs}... — Translation Hub`;

    // Mark all selected cells as IN_PROGRESS
    for (const iid of articleIds) {
        for (const loc of locales) {
            trSetCellStatus(iid, loc, 'IN_PROGRESS');
        }
    }

    // Translate one article×locale at a time for live cell updates
    for (const iid of articleIds) {
        for (const loc of locales) {
            try {
                const resp = await fetch('/api/translate-hub/bulk', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ intercom_ids: [iid], locales: [loc] }),
                });
                const data = await resp.json();
                if (data.success && (data.failed || 0) === 0) {
                    trSetCellStatus(iid, loc, 'TRANSLATED');
                    ok++;
                } else {
                    trSetCellStatus(iid, loc, 'FAILED');
                    fail++;
                }
            } catch (e) {
                trSetCellStatus(iid, loc, 'FAILED');
                fail++;
            }
            completed++;
            document.title = `Translating ${completed}/${totalJobs}... — Translation Hub`;
            trShowToast(`Translating ${completed}/${totalJobs}...`, 'fn-loader');
        }
    }

    document.title = `Done — ${ok} translated, ${fail} failed`;
    const msg = `Completed: ${ok} success, ${fail} failed out of ${totalJobs} jobs.`;
    trShowToast(msg, fail > 0 ? 'fa-exclamation-triangle' : 'fa-check-circle');

    setTimeout(() => { document.title = origTitle; }, 5000);

    state.tr.translating = false;
    state.tr.selectedArticles.clear();
    trUpdateActionBar();
    setTimeout(() => trLoadArticles(), 1500);
    if (state.hub.loaded) setTimeout(() => loadHubArticles(), 2000);
    setTimeout(() => {
        const toast = document.getElementById('tr-toast');
        if (toast) toast.classList.add('hidden');
    }, 6000);
}


// --- Translate All Missing ---

async function trTranslateAllMissing() {
    const locales = Array.from(state.tr.selectedLanguages);
    if (locales.length === 0) {
        alert('Please select at least one language from the language picker first.');
        return;
    }

    trShowToast('Finding missing translations...', 'fn-loader');

    try {
        const resp = await fetch('/api/translate-hub/missing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ locales }),
        });
        const data = await resp.json();
        if (!data.success) {
            trShowToast(`Error: ${data.error || 'Unknown'}`, 'fa-times-circle');
            return;
        }

        const missing = data.missing || [];
        const totalCombos = data.total_combinations || 0;
        const totalArticles = data.total_articles || 0;

        if (totalCombos === 0) {
            trShowToast('All translations are up to date!', 'fa-check-circle');
            setTimeout(() => { const toast = document.getElementById('tr-toast'); if (toast) toast.classList.add('hidden'); }, 3000);
            return;
        }

        // Auto-select these articles
        state.tr.selectedArticles.clear();
        missing.forEach(m => state.tr.selectedArticles.add(m.intercom_id));
        trUpdateActionBar();
        trRenderTable();

        // Show confirmation
        const body = document.getElementById('tr-confirm-body');
        if (body) {
            const selectedLangNames = locales.map(loc => state.tr.languages[loc] || loc);
            body.innerHTML = `
                <div class="tr-modal-stat"><span class="tr-modal-stat-label">Articles needing translation</span><span class="tr-modal-stat-val">${totalArticles}</span></div>
                <div class="tr-modal-stat"><span class="tr-modal-stat-label">Languages</span><span class="tr-modal-stat-val">${locales.length}</span></div>
                <div class="tr-modal-stat"><span class="tr-modal-stat-label">Total Jobs</span><span class="tr-modal-stat-val">${totalCombos}</span></div>
                <div style="margin-top:12px;font-size:0.82rem;color:var(--text-muted);">
                    <strong>Languages:</strong> ${selectedLangNames.map(n => escapeHtml(n)).join(', ')}
        </div>
                <div style="margin-top:8px;font-size:0.78rem;color:var(--warning);">
                    <i class="fas fa-magic"></i> This will translate all articles that need translation. Outdated articles are skipped.
        </div>
    `;
        }
        document.getElementById('tr-confirm-overlay').classList.remove('hidden');
        // Hide the scanning toast
        const toast = document.getElementById('tr-toast');
        if (toast) toast.classList.add('hidden');

    } catch (e) {
        trShowToast(`Network error: ${e.message}`, 'fa-times-circle');
    }
}


// --- Drawer ---

async function trOpenDrawer(intercomId) {
    const drawer = document.getElementById('tr-drawer');
    const overlay = document.getElementById('tr-drawer-overlay');
    const drawerTitle = document.getElementById('tr-drawer-title');
    const drawerBody = document.getElementById('tr-drawer-body');

    if (drawerTitle) drawerTitle.textContent = 'Loading...';
    if (drawerBody) drawerBody.innerHTML = '<div style="text-align:center;padding:40px;"><span class="fn-loader"></span></div>';
    drawer.classList.remove('hidden');
    overlay.classList.remove('hidden');
    state.tr.drawerOpen = true;

    try {
        const resp = await fetch(`/api/translate-hub/article/${intercomId}`);
        const data = await resp.json();
        if (data.success && data.article) {
            trRenderDrawer(data.article);
        } else {
            if (drawerBody) drawerBody.innerHTML = `<p style="color:var(--danger);">Error: ${escapeHtml(data.error || 'Not found')}</p>`;
        }
    } catch (e) {
        if (drawerBody) drawerBody.innerHTML = `<p style="color:var(--danger);">Network error: ${escapeHtml(e.message)}</p>`;
    }
}

function trCloseDrawer() {
    document.getElementById('tr-drawer').classList.add('hidden');
    document.getElementById('tr-drawer-overlay').classList.add('hidden');
    state.tr.drawerOpen = false;
}

function trRenderDrawer(article) {
    const drawerTitle = document.getElementById('tr-drawer-title');
    const drawerBody = document.getElementById('tr-drawer-body');
    if (drawerTitle) drawerTitle.textContent = article.title || 'Untitled';

    // Store article data for language switching
    state.tr._drawerArticle = article;

    let html = '';

    // Overview bar (compact)
    html += `<div class="tr-drawer-section">
        <h4><i class="fas fa-info-circle"></i> Overview</h4>
        <div class="tr-drawer-meta" style="display:grid;grid-template-columns:auto 1fr;gap:4px 12px;">
            <span style="font-weight:600;color:var(--text-muted);">Collection</span>
            <span>${escapeHtml(article.collection_name || 'Uncategorized')}</span>
            <span style="font-weight:600;color:var(--text-muted);">Source Updated</span>
            <span>${escapeHtml(article.source_updated_relative || 'N/A')}</span>
            <span style="font-weight:600;color:var(--text-muted);">Pulled</span>
            <span>${escapeHtml(article.pulled_relative || 'Never')}</span>
        </div>
    </div>`;

    // Source content preview
    if (article.source_body_preview) {
        html += `<div class="tr-drawer-section">
            <h4><i class="fas fa-file-alt"></i> Source Content Preview</h4>
            <div class="tr-source-preview">${article.source_body_preview}</div>
        </div>`;
    }

    // Language selector + translation preview
    html += `<div class="tr-drawer-section">
        <h4><i class="fas fa-globe"></i> Translation Preview</h4>
        <div class="tr-drawer-lang-select-wrap">
            <label for="tr-drawer-lang-picker"><i class="fas fa-language"></i> Language</label>
            <select id="tr-drawer-lang-picker" class="tr-drawer-lang-select">
                <option value="">— Select a language —</option>`;
    if (article.languages && article.languages.length > 0) {
        for (const lang of article.languages) {
            const statusLabel = { 'TRANSLATED': '✓', 'APPROVED': '✓✓', 'OUTDATED': '⚠', 'FAILED': '✗', 'IN_PROGRESS': '…', 'NOT_STARTED': '' }[lang.status] || '';
            html += `<option value="${escapeHtml(lang.locale)}">${escapeHtml(lang.language)} ${statusLabel}</option>`;
        }
    }
    html += `</select>
        </div>
        <div id="tr-drawer-lang-preview">
            <div class="tr-drawer-no-translation">
                <i class="fas fa-language"></i>
                Select a language above to view its translation preview
            </div>
        </div>
    </div>`;

    // View on Intercom
    if (article.url) {
        html += `<div class="tr-drawer-section" style="margin-top:8px;">
            <a href="${escapeHtml(article.url)}" target="_blank" class="btn btn-small btn-secondary" style="width:100%;text-align:center;">
                <i class="fas fa-external-link-alt"></i> View on Intercom
            </a>
        </div>`;
    }

    if (drawerBody) drawerBody.innerHTML = html;

    // Attach language picker event
    const picker = document.getElementById('tr-drawer-lang-picker');
    if (picker) {
        picker.addEventListener('change', () => {
            trDrawerShowLangPreview(picker.value);
        });
    }
}

function trDrawerShowLangPreview(locale) {
    const container = document.getElementById('tr-drawer-lang-preview');
    if (!container) return;

    const article = state.tr._drawerArticle;
    if (!article || !locale) {
        container.innerHTML = `<div class="tr-drawer-no-translation">
            <i class="fas fa-language"></i>
            Select a language above to view its translation preview
        </div>`;
        return;
    }

    const lang = (article.languages || []).find(l => l.locale === locale);
    if (!lang) {
        container.innerHTML = `<div class="tr-drawer-no-translation">
            <i class="fas fa-exclamation-circle"></i>
            Language data not available
        </div>`;
        return;
    }

    let html = '';

    // Status bar
    html += `<div class="tr-drawer-lang-status-bar">
        <strong>${escapeHtml(lang.language)}</strong>
        ${trStatusChip(lang.status)}
        <span class="tr-drawer-lang-meta">
            ${lang.last_translated_relative ? `Translated ${escapeHtml(lang.last_translated_relative)}` : 'Not translated yet'}
            ${lang.engine ? ` · ${escapeHtml(lang.engine)}` : ''}
            ${lang.model ? ` (${escapeHtml(lang.model)})` : ''}
        </span>
    </div>`;

    // Translation content
    if (lang.translated_title || lang.translated_body_preview) {
        if (lang.translated_title) {
            html += `<div class="tr-drawer-translation-title">${escapeHtml(lang.translated_title)}</div>`;
        }
        html += `<div class="tr-translated-preview">
            ${lang.translated_body_preview || '<em>No body content available</em>'}
        </div>`;
    } else {
        html += `<div class="tr-drawer-no-translation">
            <i class="fas fa-file-excel"></i>
            No translation available for ${escapeHtml(lang.language)}
        </div>`;
    }

    // Retranslate button
    html += `<button class="tr-drawer-retranslate-btn" onclick="trRetranslateOne('${escapeHtml(article.intercom_id)}', '${escapeHtml(lang.locale)}')">
        <i class="fas fa-redo-alt"></i> Retranslate ${escapeHtml(lang.language)}
    </button>`;

    container.innerHTML = html;
}


// --- Retranslate One ---
async function trRetranslateOne(intercomId, locale) {
    if (state.tr.translating) return;
    if (!confirm(`Retranslate this article to ${state.tr.languages[locale] || locale}?`)) return;

    state.tr.translating = true;
    trShowToast(`Translating to ${state.tr.languages[locale] || locale}...`, 'fn-loader');

    try {
        const resp = await fetch('/api/translate-hub/bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ intercom_ids: [intercomId], locales: [locale] }),
        });
        const data = await resp.json();
        if (data.success) {
            trShowToast(data.completed > 0 ? 'Translation complete!' : 'Translation failed.', data.completed > 0 ? 'fa-check-circle' : 'fa-times-circle');
        } else {
            trShowToast(`Error: ${data.error || 'Unknown'}`, 'fa-times-circle');
        }
    } catch (e) {
        trShowToast(`Error: ${e.message}`, 'fa-times-circle');
    }

    state.tr.translating = false;
    // Reload drawer
    setTimeout(() => {
        trOpenDrawer(intercomId);
        trLoadArticles();
    }, 1000);
    setTimeout(() => { const toast = document.getElementById('tr-toast'); if (toast) toast.classList.add('hidden'); }, 5000);
}


// --- Toast ---

function trShowToast(msg, iconClass) {
    const toast = document.getElementById('tr-toast');
    const icon = document.getElementById('tr-toast-icon');
    const text = document.getElementById('tr-toast-text');
    if (toast) toast.classList.remove('hidden');
    if (icon) {
        if (iconClass === 'fn-loader') {
            icon.className = '';
            icon.innerHTML = '<span class="fn-loader-inline"></span>';
        } else {
            icon.innerHTML = '';
            icon.className = `fas ${iconClass}`;
        }
    }
    if (text) text.textContent = msg;
}


// ============================================================
// GLOSSARY MODULE
// ============================================================

async function initGlossarySection() {
    state.gl.loaded = true;

    // Check tables exist
    try {
        const resp = await fetch('/api/glossary/status');
        const data = await resp.json();
        if (!data.tables_exist) {
            state.gl.tablesExist = false;
            document.getElementById('gl-setup-banner').classList.remove('hidden');
            document.getElementById('gl-main-content').classList.add('hidden');
            if (data.setup_sql) {
                document.getElementById('gl-setup-sql').textContent = data.setup_sql;
            }
        } else {
            state.gl.tablesExist = true;
            document.getElementById('gl-setup-banner').classList.add('hidden');
            document.getElementById('gl-main-content').classList.remove('hidden');
            glLoadGlossaries();
        }
    } catch (e) {
        console.error('Glossary status check failed', e);
    }

    // --- Setup event listeners ---
    // Create tables
    document.getElementById('gl-create-tables-btn')?.addEventListener('click', async () => {
        glShowToast('Creating tables...', 'fn-loader');
        try {
            const resp = await fetch('/api/glossary/create-tables', { method: 'POST' });
            const data = await resp.json();
                if (data.success) {
                glShowToast('Tables created!', 'fa-check-circle');
                state.gl.tablesExist = true;
                document.getElementById('gl-setup-banner').classList.add('hidden');
                document.getElementById('gl-main-content').classList.remove('hidden');
                glLoadGlossaries();
                } else {
                glShowToast('Failed: ' + (data.error || 'Unknown'), 'fa-times-circle');
            }
        } catch (e) {
            glShowToast('Error: ' + e.message, 'fa-times-circle');
        }
        setTimeout(() => { const t = document.getElementById('gl-toast'); if (t) t.classList.add('hidden'); }, 4000);
    });

    // Copy SQL button
    document.getElementById('gl-copy-sql-btn')?.addEventListener('click', () => {
        const sql = document.getElementById('gl-setup-sql');
        if (sql) {
            navigator.clipboard.writeText(sql.textContent).then(() => {
                const btn = document.getElementById('gl-copy-sql-btn');
                btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                setTimeout(() => { btn.innerHTML = '<i class="fas fa-copy"></i> Copy SQL'; }, 2000);
            });
        }
    });

    // Create glossary button - opens left drawer
    document.getElementById('gl-create-btn')?.addEventListener('click', () => {
        glOpenCreateDrawer();
    });

    // Drawer close handlers
    document.getElementById('gl-drawer-close')?.addEventListener('click', glCloseCreateDrawer);
    document.getElementById('gl-glossary-drawer-overlay')?.addEventListener('click', glCloseCreateDrawer);
    
    // ESC key to close drawer
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !document.getElementById('gl-glossary-drawer')?.classList.contains('hidden')) {
            glCloseCreateDrawer();
        }
    });

    // Drawer create button
    document.getElementById('gl-drawer-create')?.addEventListener('click', glCreateGlossaryFromDrawer);
    
    // Modal handlers for editing (keep old modal for edit)
    document.getElementById('gl-modal-cancel')?.addEventListener('click', () => {
        document.getElementById('gl-glossary-modal-overlay').classList.add('hidden');
    });
    document.getElementById('gl-modal-save')?.addEventListener('click', glSaveGlossary);
    
    // Search handlers for dual-list
    const availableSearch = document.getElementById('gl-available-search');
    if (availableSearch) {
        availableSearch.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const options = document.querySelectorAll('#gl-available-languages .gl-lang-option');
            options.forEach(opt => {
                const text = opt.textContent.toLowerCase();
                opt.style.display = text.includes(query) ? '' : 'none';
            });
        });
    }
    
    const selectedSearch = document.getElementById('gl-selected-search');
    if (selectedSearch) {
        selectedSearch.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const items = document.querySelectorAll('#gl-selected-languages .gl-selected-lang-item');
            items.forEach(item => {
                const text = item.textContent.toLowerCase();
                item.style.display = text.includes(query) ? '' : 'none';
            });
        });
    }
    
    // Update available list when source language changes
    const sourceSelect = document.getElementById('gl-drawer-source');
    if (sourceSelect) {
        sourceSelect.addEventListener('change', () => {
            const sourceLocale = sourceSelect.value;
            if (state.gl.drawerSelectedLanguages && state.gl.drawerSelectedLanguages.has(sourceLocale)) {
                state.gl.drawerSelectedLanguages.delete(sourceLocale);
            }
            glPopulateDualListPicker();
            glUpdateSelectedLanguagesList();
        });
    }

    // Back button
    document.getElementById('gl-back-btn')?.addEventListener('click', () => {
        state.gl.currentGlossaryId = null;
        state.gl.currentGlossary = null;
        document.getElementById('gl-list-view').classList.remove('hidden');
        document.getElementById('gl-term-view').classList.add('hidden');
        document.getElementById('gl-stat-terms-wrap').style.display = 'none';
        glLoadGlossaries();
    });

    // Add term button
    document.getElementById('gl-add-term-btn')?.addEventListener('click', () => {
        state.gl.editingTermId = null;
        document.getElementById('gl-term-drawer-title').textContent = 'Add Term';
        glOpenTermDrawer();
    });

    // Term drawer close/cancel
    document.getElementById('gl-term-drawer-close')?.addEventListener('click', glCloseTermDrawer);
    document.getElementById('gl-term-drawer-cancel')?.addEventListener('click', glCloseTermDrawer);
    document.getElementById('gl-term-drawer-overlay')?.addEventListener('click', glCloseTermDrawer);

    // Term drawer save
    document.getElementById('gl-term-drawer-save')?.addEventListener('click', glSaveTerm);

    // Bulk delete
    document.getElementById('gl-bulk-delete-btn')?.addEventListener('click', glBulkDelete);

    // Select all checkbox
    document.getElementById('gl-select-all')?.addEventListener('change', (e) => {
        const checked = e.target.checked;
        state.gl.selectedTermIds.clear();
        if (checked) {
            state.gl.terms.forEach(t => state.gl.selectedTermIds.add(t.id));
        }
        glRenderTermTable();
        glUpdateBulkBar();
    });

    // Term search
    document.getElementById('gl-term-search')?.addEventListener('input', (e) => {
        clearTimeout(state.gl.termSearchTimeout);
        state.gl.termSearchTimeout = setTimeout(() => {
            state.gl.termSearch = e.target.value;
            state.gl.termPage = 1;
            glLoadTerms();
        }, 300);
    });

    // Page size
    document.getElementById('gl-term-page-size')?.addEventListener('change', (e) => {
        state.gl.termPageSize = parseInt(e.target.value) || 25;
        state.gl.termPage = 1;
        glLoadTerms();
    });

    // Pagination
    document.getElementById('gl-prev-btn')?.addEventListener('click', () => {
        if (state.gl.termPage > 1) { state.gl.termPage--; glLoadTerms(); }
    });
    document.getElementById('gl-next-btn')?.addEventListener('click', () => {
        const totalPages = Math.ceil(state.gl.termTotal / state.gl.termPageSize);
        if (state.gl.termPage < totalPages) { state.gl.termPage++; glLoadTerms(); }
    });

    // Import XLSX
    document.getElementById('gl-import-btn')?.addEventListener('click', () => {
        document.getElementById('gl-import-file').click();
    });
    document.getElementById('gl-import-file')?.addEventListener('change', glHandleImport);

    // Export XLSX
    document.getElementById('gl-export-btn')?.addEventListener('click', glHandleExport);

    // Edit glossary settings
    document.getElementById('gl-edit-glossary-btn')?.addEventListener('click', () => {
        if (!state.gl.currentGlossary) return;
        state.gl.editingGlossaryId = state.gl.currentGlossaryId;
        document.getElementById('gl-modal-title').innerHTML = '<i class="fas fa-cog"></i> Edit Glossary';
        document.getElementById('gl-modal-name').value = state.gl.currentGlossary.name || '';
        // Set the source language dropdown to the glossary's current source locale
        const sourceSelect = document.getElementById('gl-modal-source');
        if (sourceSelect) {
            sourceSelect.value = state.gl.currentGlossary.source_locale || 'en';
        }
        const targets = state.gl.currentGlossary.target_locales || [];
        glPopulateModalTargets(typeof targets === 'string' ? JSON.parse(targets) : targets);
        document.getElementById('gl-glossary-modal-overlay').classList.remove('hidden');
    });

    // --- Glossary List View Controls ---
    // Filter buttons
    document.querySelectorAll('.gl-filter-btn[data-filter]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.gl-filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.gl.glossaryFilter = btn.dataset.filter;
            state.gl.glossaryPage = 1;
            glLoadGlossaries();
        });
    });

    // Search
    document.getElementById('gl-search-input')?.addEventListener('input', (e) => {
        clearTimeout(state.gl.glossarySearchTimeout);
        state.gl.glossarySearchTimeout = setTimeout(() => {
            state.gl.glossarySearch = e.target.value.trim();
            state.gl.glossaryPage = 1;
            glLoadGlossaries();
        }, 350);
    });

    // Sort
    document.getElementById('gl-sort-select')?.addEventListener('change', (e) => {
        state.gl.glossarySort = e.target.value;
        glLoadGlossaries();
    });

    // Pagination
    document.getElementById('gl-glossary-prev-btn')?.addEventListener('click', () => {
        if (state.gl.glossaryPage > 1) {
            state.gl.glossaryPage--;
            glLoadGlossaries();
        }
    });
    document.getElementById('gl-glossary-next-btn')?.addEventListener('click', () => {
        const totalPages = Math.ceil(state.gl.glossaryTotal / state.gl.glossaryPageSize);
        if (state.gl.glossaryPage < totalPages) {
            state.gl.glossaryPage++;
            glLoadGlossaries();
        }
    });

    // List view Import XLSX button
    document.getElementById('gl-list-import-btn')?.addEventListener('click', async () => {
        // Reload glossaries to get latest list
        await glLoadGlossaries();
        const glossaries = state.gl.glossaries.filter(g => g.is_active !== false);
        if (glossaries.length === 0) {
            alert('Please create a glossary first before importing.');
        return;
    }
        // Create a simple selection dialog
        const options = glossaries.map(g => `${g.id}: ${g.name}`).join('\n');
        const selection = prompt(`Select glossary to import into:\n\n${options}\n\nEnter the glossary ID or name:`, '');
        if (!selection) return;
        // Find glossary by ID or name
        const g = glossaries.find(gl => 
            gl.id === selection.trim() || 
            gl.name.toLowerCase() === selection.toLowerCase() ||
            gl.id.toLowerCase() === selection.toLowerCase()
        );
        if (!g) {
            alert('Glossary not found. Please enter a valid glossary ID or name.');
            return;
        }
        // Trigger file input
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = '.xlsx';
        fileInput.style.display = 'none';
        fileInput.addEventListener('change', async () => {
            const file = fileInput.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            glShowToast('Importing...', 'fn-loader');
            try {
                const resp = await fetch(`/api/glossary/glossaries/${g.id}/import`, {
            method: 'POST',
                    body: formData,
                });
                const data = await resp.json();
                if (data.success !== false) {
                    const msg = `Import complete: ${data.created || 0} created, ${data.updated || 0} updated.`;
                    glShowToast(msg, 'fa-check-circle');
                    glLoadGlossaries();
                } else {
                    glShowToast('Import failed: ' + (data.error || 'Unknown'), 'fa-times-circle');
                }
            } catch (err) {
                glShowToast('Import error: ' + err.message, 'fa-times-circle');
            }
            fileInput.remove();
            setTimeout(() => { const t = document.getElementById('gl-toast'); if (t) t.classList.add('hidden'); }, 5000);
        });
        document.body.appendChild(fileInput);
        fileInput.click();
    });
}


// --- Glossary List ---

async function glLoadGlossaries() {
    const tbody = document.getElementById('gl-glossary-tbody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="empty-cell"><span class="fn-loader"></span> Loading...</td></tr>';

    try {
        const params = new URLSearchParams({
            search: state.gl.glossarySearch,
            status: state.gl.glossaryFilter,
            sort: state.gl.glossarySort,
            page: state.gl.glossaryPage,
            page_size: state.gl.glossaryPageSize,
        });
        const resp = await fetch(`/api/glossary/glossaries?${params}`);
        const data = await resp.json();
        if (data.success) {
            state.gl.glossaries = data.glossaries || [];
            state.gl.glossaryTotal = data.total || 0;
            document.getElementById('gl-stat-glossaries').textContent = state.gl.glossaryTotal;
            glRenderGlossaryTable();
            glRenderGlossaryPagination();
            glRenderFilterCounts();
        } else {
            if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">Error: ${escapeHtml(data.error || 'Unknown')}</td></tr>`;
        }
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">Network error</td></tr>`;
    }
}

function glRenderGlossaryPagination() {
    const totalPages = Math.max(1, Math.ceil(state.gl.glossaryTotal / state.gl.glossaryPageSize));
    const info = document.getElementById('gl-glossary-page-info');
    if (info) info.textContent = `Page ${state.gl.glossaryPage} of ${totalPages} (${state.gl.glossaryTotal} glossaries)`;
    const prevBtn = document.getElementById('gl-glossary-prev-btn');
    const nextBtn = document.getElementById('gl-glossary-next-btn');
    if (prevBtn) prevBtn.disabled = state.gl.glossaryPage <= 1;
    if (nextBtn) nextBtn.disabled = state.gl.glossaryPage >= totalPages;
}

async function glRenderFilterCounts() {
    try {
        // Fetch counts for each filter
        const [allResp, activeResp, inactiveResp] = await Promise.all([
            fetch('/api/glossary/glossaries?status=ALL&page_size=1'),
            fetch('/api/glossary/glossaries?status=ACTIVE&page_size=1'),
            fetch('/api/glossary/glossaries?status=INACTIVE&page_size=1'),
        ]);
        const [allData, activeData, inactiveData] = await Promise.all([
            allResp.json(), activeResp.json(), inactiveResp.json(),
        ]);
        const setCount = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        setCount('gl-count-all', allData.total || 0);
        setCount('gl-count-active', activeData.total || 0);
        setCount('gl-count-inactive', inactiveData.total || 0);
    } catch (e) { /* ignore */ }
}

function glRenderGlossaryTable() {
    const tbody = document.getElementById('gl-glossary-tbody');
    if (!tbody) return;

    if (state.gl.glossaries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No glossaries yet. Click "New Glossary" to create one.</td></tr>';
        return;
    }

    let html = '';
    for (const g of state.gl.glossaries) {
        const targets = typeof g.target_locales === 'string' ? JSON.parse(g.target_locales) : (g.target_locales || []);
        const langChips = targets.slice(0, 5).map(l => `<span class="gl-lang-chip">${l.toUpperCase()}</span>`).join('');
        const more = targets.length > 5 ? `<span class="gl-lang-chip">+${targets.length - 5}</span>` : '';
        const created = g.created_at ? new Date(g.created_at).toLocaleDateString() : '--';
        const createdBy = g.created_by || 'system';
        html += `<tr class="gl-glossary-row" data-id="${g.id}">
            <td style="text-align:left;padding-left:16px;"><a href="#" class="gl-glossary-link" data-id="${g.id}">${escapeHtml(g.name || 'Untitled')}</a></td>
            <td>${escapeHtml((g.source_locale || 'en').toUpperCase())}</td>
            <td>${langChips}${more}</td>
            <td style="text-align:center">${g.term_count || 0}</td>
            <td>${escapeHtml(createdBy)}</td>
            <td>${created}</td>
            <td style="text-align:center;">
                <div style="display:inline-flex;gap:8px;align-items:center;justify-content:center;">
                    <label class="gl-toggle-switch" title="${g.is_active !== false ? 'Deactivate' : 'Activate'}">
                        <input type="checkbox" class="gl-toggle-input" data-id="${g.id}" ${g.is_active !== false ? 'checked' : ''}>
                        <span class="gl-toggle-slider"></span>
                    </label>
                    <button class="btn btn-icon gl-edit-btn" data-id="${g.id}" title="Settings"><i class="fas fa-cog"></i></button>
                    <button class="btn btn-icon gl-delete-btn" data-id="${g.id}" title="Delete"><i class="fas fa-trash"></i></button>
                </div>
            </td>
        </tr>`;
    }
    tbody.innerHTML = html;

    // Click to open
    tbody.querySelectorAll('.gl-glossary-link').forEach(a => {
        a.addEventListener('click', (e) => {
            e.preventDefault();
            glOpenGlossary(a.dataset.id);
        });
    });

    // Edit button
    tbody.querySelectorAll('.gl-edit-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const g = state.gl.glossaries.find(x => x.id === btn.dataset.id);
            if (!g) return;
            state.gl.editingGlossaryId = g.id;
            document.getElementById('gl-modal-title').innerHTML = '<i class="fas fa-cog"></i> Edit Glossary';
            document.getElementById('gl-modal-name').value = g.name || '';
            const targets = typeof g.target_locales === 'string' ? JSON.parse(g.target_locales) : (g.target_locales || []);
            glPopulateModalTargets(targets);
            document.getElementById('gl-glossary-modal-overlay').classList.remove('hidden');
        });
    });

    // Delete button
    tbody.querySelectorAll('.gl-delete-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (!confirm('Delete this glossary and all its terms? This cannot be undone.')) return;
            try {
                const resp = await fetch(`/api/glossary/glossaries/${btn.dataset.id}`, { method: 'DELETE' });
                const data = await resp.json();
                if (data.success) {
                    glShowToast('Glossary deleted successfully.', 'fa-check-circle');
                    setTimeout(() => { const t = document.getElementById('gl-toast'); if (t) t.classList.add('hidden'); }, 3000);
                    glLoadGlossaries();
                } else {
                    alert('Failed to delete glossary: ' + (data.error || 'Unknown error'));
                }
            } catch (err) {
                alert('Failed to delete glossary.');
            }
        });
    });

    // Toggle switch (activate/deactivate)
    tbody.querySelectorAll('.gl-toggle-input').forEach(toggle => {
        toggle.addEventListener('change', async (e) => {
            e.stopPropagation();
            const glossaryId = toggle.dataset.id;
            const isActive = toggle.checked;
            const g = state.gl.glossaries.find(x => x.id === glossaryId);
            if (!g) return;
            
            try {
                const resp = await fetch(`/api/glossary/glossaries/${glossaryId}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: isActive }),
                });
                const data = await resp.json();
                if (data.success) {
                    g.is_active = isActive;
                    glShowToast(isActive ? 'Glossary activated!' : 'Glossary deactivated!', 'fa-check-circle');
                    setTimeout(() => { const t = document.getElementById('gl-toast'); if (t) t.classList.add('hidden'); }, 3000);
                    // Reload to update filter counts and ensure correct list
                    glLoadGlossaries();
        } else {
                    // Revert toggle on error
                    toggle.checked = !isActive;
                    alert('Error: ' + (data.error || 'Failed to update glossary status'));
                }
            } catch (err) {
                // Revert toggle on error
                toggle.checked = !isActive;
                alert('Failed to update glossary status.');
            }
        });
    });

}

function glPopulateModalTargets(selected) {
    const container = document.getElementById('gl-modal-targets');
    if (!container) return;
    const selectedSet = new Set(selected || []);
    let html = '';
    for (const [loc, name] of Object.entries(TARGET_LANGUAGES)) {
        const checked = selectedSet.has(loc) ? 'checked' : '';
        html += `<label class="gl-lang-check-label"><input type="checkbox" value="${loc}" ${checked}> ${escapeHtml(name)} (${loc})</label>`;
    }
    container.innerHTML = html;
}

// --- Create Glossary Drawer Functions ---

function glOpenCreateDrawer() {
    state.gl.editingGlossaryId = null;
    state.gl.drawerSelectedLanguages = new Set();
    
    // Reset form
    document.getElementById('gl-drawer-name').value = '';
    document.getElementById('gl-drawer-source').value = '';
    document.getElementById('gl-available-search').value = '';
    document.getElementById('gl-selected-search').value = '';
    
    // Clear errors
    glClearDrawerErrors();
    
    // Populate dual-list picker
    glPopulateDualListPicker();
    
    // Get elements
    const overlay = document.getElementById('gl-glossary-drawer-overlay');
    const drawer = document.getElementById('gl-glossary-drawer');
    
    // Ensure drawer starts in hidden state (off-screen to the right)
    drawer.classList.add('hidden');
    overlay.classList.add('hidden');
    
    // Show overlay
    overlay.classList.remove('hidden');
    
    // Remove any inline styles that might interfere
    drawer.style.removeProperty('transform');
    drawer.style.removeProperty('transition');
    drawer.style.removeProperty('display');
    
    // Use setTimeout to ensure the browser has rendered the initial state
    // This is the most reliable way to trigger CSS transitions
    setTimeout(() => {
        // Remove hidden class to trigger the slide-in animation from right
        drawer.classList.remove('hidden');
    }, 50);
    
    // Focus on first input after animation starts
    setTimeout(() => {
        document.getElementById('gl-drawer-name').focus();
    }, 300);
}

function glCloseCreateDrawer() {
    document.getElementById('gl-glossary-drawer-overlay').classList.add('hidden');
    document.getElementById('gl-glossary-drawer').classList.add('hidden');
    
    // Return focus to create button
    setTimeout(() => {
        document.getElementById('gl-create-btn')?.focus();
    }, 100);
}

function glPopulateDualListPicker() {
    const availableContainer = document.getElementById('gl-available-languages');
    const selectedContainer = document.getElementById('gl-selected-languages');
    
    if (!availableContainer || !selectedContainer) return;
    
    // Get all available languages (excluding source language if selected)
    const sourceLocale = document.getElementById('gl-drawer-source')?.value || '';
    const selected = state.gl.drawerSelectedLanguages || new Set();
    
    let availableHtml = '';
    for (const [loc, name] of Object.entries(TARGET_LANGUAGES)) {
        // Skip if it's the source language or already selected
        if (loc === sourceLocale || selected.has(loc)) continue;
        
        availableHtml += `
            <div class="gl-lang-option" data-locale="${loc}">
                <input type="checkbox" id="gl-avail-${loc}" value="${loc}" onchange="glToggleLanguage('${loc}')">
                <label for="gl-avail-${loc}">${escapeHtml(name)} (${loc})</label>
            </div>
        `;
    }
    
    if (availableHtml === '') {
        availableHtml = '<div class="gl-empty-selection">No available languages</div>';
    }
    availableContainer.innerHTML = availableHtml;
    
    // Update selected list
    glUpdateSelectedLanguagesList();
}

function glUpdateSelectedLanguagesList() {
    const selectedContainer = document.getElementById('gl-selected-languages');
    if (!selectedContainer) return;
    
    const selected = state.gl.drawerSelectedLanguages || new Set();
    
    if (selected.size === 0) {
        selectedContainer.innerHTML = '<div class="gl-empty-selection">No languages selected</div>';
        return;
    }
    
    let html = '';
    for (const loc of Array.from(selected).sort()) {
        const name = TARGET_LANGUAGES[loc] || loc;
        html += `
            <div class="gl-selected-lang-item" data-locale="${loc}">
                <span>${escapeHtml(name)} (${loc})</span>
                <button type="button" class="gl-remove-lang" onclick="glRemoveLanguage('${loc}')" title="Remove">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
    }
    selectedContainer.innerHTML = html;
}

// Global functions for inline handlers
window.glToggleLanguage = function(locale) {
    if (!state.gl.drawerSelectedLanguages) {
        state.gl.drawerSelectedLanguages = new Set();
    }
    
    const checkbox = document.getElementById(`gl-avail-${locale}`);
    if (checkbox?.checked) {
        state.gl.drawerSelectedLanguages.add(locale);
        } else {
        state.gl.drawerSelectedLanguages.delete(locale);
    }
    
    glPopulateDualListPicker();
    glUpdateSelectedLanguagesList();
};

window.glRemoveLanguage = function(locale) {
    if (state.gl.drawerSelectedLanguages) {
        state.gl.drawerSelectedLanguages.delete(locale);
    }
    glPopulateDualListPicker();
    glUpdateSelectedLanguagesList();
};

function glClearDrawerErrors() {
    document.getElementById('gl-error-name').style.display = 'none';
    document.getElementById('gl-error-source').style.display = 'none';
    document.getElementById('gl-error-targets').style.display = 'none';
    document.getElementById('gl-drawer-name').classList.remove('error');
    document.getElementById('gl-drawer-source').classList.remove('error');
}

function glShowDrawerError(field, message) {
    const errorEl = document.getElementById(`gl-error-${field}`);
    const inputEl = document.getElementById(`gl-drawer-${field}`);
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.style.display = 'block';
    }
    if (inputEl) {
        inputEl.classList.add('error');
    }
}

async function glCreateGlossaryFromDrawer() {
    // Clear previous errors
    glClearDrawerErrors();
    
    // Get values
    const name = document.getElementById('gl-drawer-name').value.trim();
    const sourceLocale = document.getElementById('gl-drawer-source').value;
    const selectedLanguages = Array.from(state.gl.drawerSelectedLanguages || []);
    
    // Validate
    let hasErrors = false;
    
    if (!name) {
        glShowDrawerError('name', 'Glossary name is required');
        hasErrors = true;
    }
    
    if (!sourceLocale) {
        glShowDrawerError('source', 'Term language is required');
        hasErrors = true;
    }
    
    if (selectedLanguages.length === 0) {
        glShowDrawerError('targets', 'At least one target language is required');
        hasErrors = true;
    }
    
    if (hasErrors) {
        return;
    }
    
    // Show loading state
    const createBtn = document.getElementById('gl-drawer-create');
    const originalText = createBtn.innerHTML;
    createBtn.disabled = true;
    createBtn.innerHTML = '<span class="fn-loader-inline"></span> Creating...';
    
    try {
        const resp = await fetch('/api/glossary/glossaries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                source_locale: sourceLocale,
                target_locales: selectedLanguages,
            }),
        });
        
        const data = await resp.json();
        
        if (data.success) {
            // Success - close drawer and refresh
            glCloseCreateDrawer();
            glLoadGlossaries();
            glShowToast('Glossary created successfully!', 'fa-check-circle');
            setTimeout(() => {
                const t = document.getElementById('gl-toast');
                if (t) t.classList.add('hidden');
            }, 3000);
        } else {
            // Error - show message
            glShowToast('Error: ' + (data.error || 'Unknown'), 'fa-times-circle');
            createBtn.disabled = false;
            createBtn.innerHTML = originalText;
        }
    } catch (e) {
        glShowToast('Error: ' + e.message, 'fa-times-circle');
        createBtn.disabled = false;
        createBtn.innerHTML = originalText;
    }
}

async function glSaveGlossary() {
    const name = document.getElementById('gl-modal-name').value.trim();
    if (!name) { alert('Glossary name is required.'); return; }

    const checkboxes = document.querySelectorAll('#gl-modal-targets input[type=checkbox]:checked');
    const target_locales = Array.from(checkboxes).map(cb => cb.value);
    if (target_locales.length === 0) { alert('Select at least one target language.'); return; }

    const source_locale = document.getElementById('gl-modal-source').value || 'en';

    try {
        let resp;
        if (state.gl.editingGlossaryId) {
            resp = await fetch(`/api/glossary/glossaries/${state.gl.editingGlossaryId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, source_locale, target_locales }),
            });
        } else {
            resp = await fetch('/api/glossary/glossaries', {
            method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, source_locale, target_locales }),
            });
        }
        const data = await resp.json();
        if (data.success) {
            document.getElementById('gl-glossary-modal-overlay').classList.add('hidden');
            if (state.gl.currentGlossaryId === state.gl.editingGlossaryId && state.gl.editingGlossaryId) {
                state.gl.currentGlossary = { ...state.gl.currentGlossary, name, source_locale, target_locales };
                document.getElementById('gl-current-name').textContent = name;
                glRenderTermTableHeader();
                glRenderTermTable();
            }
            glLoadGlossaries();
        } else {
            alert('Error: ' + (data.error || 'Unknown'));
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}


// --- Open Glossary -> Term View ---

async function glOpenGlossary(glossaryId) {
    state.gl.currentGlossaryId = glossaryId;
    state.gl.currentGlossary = state.gl.glossaries.find(g => g.id === glossaryId) || null;
    state.gl.terms = [];
    state.gl.selectedTermIds.clear();
    state.gl.termPage = 1;
    state.gl.termSearch = '';

    document.getElementById('gl-list-view').classList.add('hidden');
    document.getElementById('gl-term-view').classList.remove('hidden');
    document.getElementById('gl-stat-terms-wrap').style.display = '';
    document.getElementById('gl-current-name').textContent = state.gl.currentGlossary?.name || 'Glossary';
    document.getElementById('gl-term-search').value = '';

    glRenderTermTableHeader();
    await glLoadTerms();
    glLoadUsage();
}

function glRenderTermTableHeader() {
    const thead = document.getElementById('gl-term-thead');
    if (!thead) return;
    const g = state.gl.currentGlossary;
    if (!g) return;
    const targets = typeof g.target_locales === 'string' ? JSON.parse(g.target_locales) : (g.target_locales || []);

    let html = '<tr>';
    html += '<th class="tr-th-check"><input type="checkbox" id="gl-select-all" title="Select all"></th>';
    html += '<th class="tr-th-title">Source Term</th>';
    for (const loc of targets) {
        html += `<th class="tr-th-lang">${loc.toUpperCase()}</th>`;
    }
    html += '<th style="width:60px;text-align:center">Usage</th>';
    html += '<th style="width:60px;text-align:center">Actions</th>';
    html += '</tr>';
    thead.innerHTML = html;

    // Re-bind select all
    document.getElementById('gl-select-all')?.addEventListener('change', (e) => {
        const checked = e.target.checked;
        state.gl.selectedTermIds.clear();
        if (checked) {
            state.gl.terms.forEach(t => state.gl.selectedTermIds.add(t.id));
        }
        glRenderTermTable();
        glUpdateBulkBar();
    });
}


// --- Terms ---

async function glLoadTerms() {
    const tbody = document.getElementById('gl-term-tbody');
    const colCount = (state.gl.currentGlossary?.target_locales?.length || 0) + 4;
    if (tbody) tbody.innerHTML = `<tr><td colspan="${colCount}" class="empty-cell"><span class="fn-loader"></span> Loading...</td></tr>`;

    try {
        const params = new URLSearchParams({
            search: state.gl.termSearch,
            page: state.gl.termPage,
            page_size: state.gl.termPageSize,
        });
        const resp = await fetch(`/api/glossary/glossaries/${state.gl.currentGlossaryId}/terms?${params}`);
        const data = await resp.json();
        if (data.success) {
            state.gl.terms = data.terms || [];
            state.gl.termTotal = data.total || 0;
            document.getElementById('gl-stat-terms').textContent = state.gl.termTotal;
            glRenderTermTable();
            glRenderPagination();
        } else {
            if (tbody) tbody.innerHTML = `<tr><td colspan="${colCount}" class="empty-cell">Error: ${escapeHtml(data.error || 'Unknown')}</td></tr>`;
        }
    } catch (e) {
        const colCount2 = (state.gl.currentGlossary?.target_locales?.length || 0) + 4;
        if (tbody) tbody.innerHTML = `<tr><td colspan="${colCount2}" class="empty-cell">Network error</td></tr>`;
    }
}

function glRenderTermTable() {
    const tbody = document.getElementById('gl-term-tbody');
    if (!tbody) return;
    const g = state.gl.currentGlossary;
    if (!g) return;
    const targets = typeof g.target_locales === 'string' ? JSON.parse(g.target_locales) : (g.target_locales || []);
    const colCount = targets.length + 4;

    if (state.gl.terms.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${colCount}" class="empty-cell">No terms yet. Click "Add Term" to create one.</td></tr>`;
        return;
    }
    
    let html = '';
    for (const term of state.gl.terms) {
        const checked = state.gl.selectedTermIds.has(term.id) ? 'checked' : '';
        const translations = term.translations || {};
        const usage = state.gl.usage[term.id] || {};
        const artCount = usage.article_count ?? '--';
        const transCount = usage.translation_count ?? '--';

        let posBadge = '';
        if (term.part_of_speech) {
            posBadge = ` <span class="gl-pos-badge">${escapeHtml(term.part_of_speech)}</span>`;
        }

        html += `<tr class="gl-term-row">`;
        html += `<td class="tr-td-check"><input type="checkbox" class="gl-term-cb" data-id="${term.id}" ${checked}></td>`;
        html += `<td class="gl-term-source-cell">${escapeHtml(term.source_term || '')}${posBadge}</td>`;

        for (const loc of targets) {
            const trans = translations[loc] || '';
            html += trans
                ? `<td class="gl-trans-cell gl-trans-filled">${escapeHtml(trans)}</td>`
                : `<td class="gl-trans-cell gl-trans-empty">--</td>`;
        }

        html += `<td class="gl-usage-cell" title="Articles: ${artCount}, Translations: ${transCount}">
            <span class="gl-usage-badge">${artCount}</span>
            <span class="gl-usage-badge gl-usage-trans">${transCount}</span>
        </td>`;
        html += `<td class="gl-actions-cell">
            <div class="gl-actions-wrap">
                <button class="btn btn-icon gl-term-edit-btn" data-id="${term.id}" title="Edit"><i class="fas fa-edit"></i></button>
                <button class="btn btn-icon gl-term-delete-btn" data-id="${term.id}" title="Delete" style="color:#ef4444;"><i class="fas fa-trash"></i></button>
            </div>
        </td>`;
        html += `</tr>`;
    }
    tbody.innerHTML = html;

    // Bind checkboxes
    tbody.querySelectorAll('.gl-term-cb').forEach(cb => {
        cb.addEventListener('change', (e) => {
            if (e.target.checked) {
                state.gl.selectedTermIds.add(e.target.dataset.id);
            } else {
                state.gl.selectedTermIds.delete(e.target.dataset.id);
            }
            glUpdateBulkBar();
        });
    });

    // Bind edit
    tbody.querySelectorAll('.gl-term-edit-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const term = state.gl.terms.find(t => t.id === btn.dataset.id);
            if (term) glEditTerm(term);
        });
    });

    // Bind individual delete
    tbody.querySelectorAll('.gl-term-delete-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (!confirm('Delete this term? It will no longer apply during translation.')) return;
            try {
                const resp = await fetch('/api/glossary/terms/bulk-delete', {
            method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ term_ids: [btn.dataset.id] }),
                });
                const data = await resp.json();
                if (data.success) {
                    glLoadTerms();
                    glShowToast('Term deleted.', 'fa-check-circle');
                    setTimeout(() => { const t = document.getElementById('gl-toast'); if (t) t.classList.add('hidden'); }, 3000);
                } else {
                    alert('Error: ' + (data.error || 'Unknown'));
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        });
    });
    
    // Update bulk bar after rendering (pagination is updated in glLoadTerms)
    glUpdateBulkBar();
}

function glRenderPagination() {
    const totalPages = Math.max(1, Math.ceil(state.gl.termTotal / state.gl.termPageSize));
    

    // Update page info
    const info = document.getElementById('gl-page-info');
    if (info) info.textContent = `Page ${state.gl.termPage} of ${totalPages} (${state.gl.termTotal} terms)`;
    
    // Update navigation buttons
    const prevBtn = document.getElementById('gl-prev-btn');
    const nextBtn = document.getElementById('gl-next-btn');
    if (prevBtn) prevBtn.disabled = state.gl.termPage <= 1;
    if (nextBtn) nextBtn.disabled = state.gl.termPage >= totalPages;
}

function glUpdateBulkBar() {
    const count = state.gl.selectedTermIds.size;
    
    // Update delete button count
    const el = document.getElementById('gl-sel-count');
    if (el) el.textContent = count;
    
    // Update bulk delete button
    const btn = document.getElementById('gl-bulk-delete-btn');
    if (btn) btn.disabled = count === 0;
    
    // Show/hide and update "X selected" button
    const selectedCountBtn = document.getElementById('gl-selected-count-btn');
    const selectedCountDisplay = document.getElementById('gl-sel-count-display');
    if (selectedCountBtn && selectedCountDisplay) {
        if (count > 0) {
            selectedCountDisplay.textContent = count;
            selectedCountBtn.style.display = '';
        } else {
            selectedCountBtn.style.display = 'none';
        }
    }
    
}


// --- Term Drawer ---

function glOpenTermDrawer(term) {
    const g = state.gl.currentGlossary;
    if (!g) return;
    const targets = typeof g.target_locales === 'string' ? JSON.parse(g.target_locales) : (g.target_locales || []);

    // Reset fields
    document.getElementById('gl-term-source').value = term?.source_term || '';
    document.getElementById('gl-term-pos').value = term?.part_of_speech || '';
    document.getElementById('gl-term-desc').value = term?.description || '';
    document.getElementById('gl-term-image').value = term?.image_url || '';

    // Build translation fields
    const container = document.getElementById('gl-term-translations-fields');
    if (container) {
        let html = '';
        for (const loc of targets) {
            const langName = TARGET_LANGUAGES[loc] || loc;
            const val = (term?.translations || {})[loc] || '';
            html += `<div class="gl-form-group gl-trans-field">
                <label>${escapeHtml(langName)} (${loc})</label>
                <input type="text" class="gl-input gl-trans-input" data-locale="${loc}" value="${escapeHtml(val)}" placeholder="Translation...">
            </div>`;
        }
        container.innerHTML = html;
    }

    document.getElementById('gl-term-drawer-overlay').classList.remove('hidden');
    document.getElementById('gl-term-drawer').classList.remove('hidden');
}

function glCloseTermDrawer() {
    document.getElementById('gl-term-drawer-overlay').classList.add('hidden');
    document.getElementById('gl-term-drawer').classList.add('hidden');
    state.gl.editingTermId = null;
}

function glEditTerm(term) {
    state.gl.editingTermId = term.id;
    document.getElementById('gl-term-drawer-title').textContent = 'Edit Term';
    glOpenTermDrawer(term);
}

async function glSaveTerm() {
    const source_term = document.getElementById('gl-term-source').value.trim();
    if (!source_term) { alert('Source term is required.'); return; }

    const part_of_speech = document.getElementById('gl-term-pos').value;
    const description = document.getElementById('gl-term-desc').value.trim();
    const image_url = document.getElementById('gl-term-image').value.trim();

    const translations = {};
    document.querySelectorAll('.gl-trans-input').forEach(input => {
        const loc = input.dataset.locale;
        const val = input.value.trim();
        if (loc) translations[loc] = val;
    });

    try {
        let resp;
        if (state.gl.editingTermId) {
            resp = await fetch(`/api/glossary/terms/${state.gl.editingTermId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_term, part_of_speech, description, image_url, translations }),
            });
        } else {
            resp = await fetch(`/api/glossary/glossaries/${state.gl.currentGlossaryId}/terms`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_term, part_of_speech, description, image_url, translations }),
            });
        }
        const data = await resp.json();
        if (data.success) {
            glCloseTermDrawer();
            glLoadTerms();
            glShowToast(state.gl.editingTermId ? 'Term updated!' : 'Term added!', 'fa-check-circle');
            setTimeout(() => { const t = document.getElementById('gl-toast'); if (t) t.classList.add('hidden'); }, 3000);
        } else {
            // Handle duplicate term error (409 / code 23505)
            const errMsg = data.error || '';
            if (resp.status === 409 || errMsg.includes('23505') || errMsg.toLowerCase().includes('already exists') || errMsg.toLowerCase().includes('duplicate')) {
                glShowToast(`A term "${source_term}" already exists in this glossary.`, 'fa-exclamation-triangle');
                // Highlight the source term input
                const srcInput = document.getElementById('gl-term-source');
                if (srcInput) {
                    srcInput.style.borderColor = '#ef4444';
                    srcInput.focus();
                    srcInput.addEventListener('input', function resetBorder() {
                        srcInput.style.borderColor = '';
                        srcInput.removeEventListener('input', resetBorder);
                    });
                }
            } else {
                glShowToast('Error: ' + (errMsg || 'Unknown error'), 'fa-exclamation-triangle');
            }
            setTimeout(() => { const t = document.getElementById('gl-toast'); if (t) t.classList.add('hidden'); }, 5000);
        }
    } catch (e) {
        glShowToast('Error: ' + e.message, 'fa-exclamation-triangle');
        setTimeout(() => { const t = document.getElementById('gl-toast'); if (t) t.classList.add('hidden'); }, 5000);
    }
}

async function glBulkDelete() {
    const ids = Array.from(state.gl.selectedTermIds);
    if (ids.length === 0) return;
    if (!confirm(`Delete ${ids.length} selected term(s)? They will no longer apply during translation.`)) return;

    try {
        const resp = await fetch('/api/glossary/terms/bulk-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ term_ids: ids }),
        });
        const data = await resp.json();
        if (data.success) {
            state.gl.selectedTermIds.clear();
            glUpdateBulkBar();
            glLoadTerms();
            glShowToast(`Deleted ${data.deleted} term(s).`, 'fa-check-circle');
            setTimeout(() => { const t = document.getElementById('gl-toast'); if (t) t.classList.add('hidden'); }, 3000);
        } else {
            alert('Error: ' + (data.error || 'Unknown'));
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}


// --- Usage Analytics ---

async function glLoadUsage() {
    if (!state.gl.currentGlossaryId) return;
    try {
        const resp = await fetch(`/api/glossary/glossaries/${state.gl.currentGlossaryId}/usage`);
        const data = await resp.json();
        if (data.success) {
            state.gl.usage = data.usage || {};
            glRenderTermTable(); // Re-render with usage data
        }
    } catch (e) {
        console.error('Failed to load usage', e);
    }
}


// --- XLSX Import/Export ---

async function glHandleImport(e) {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    glShowToast('Importing...', 'fn-loader');

    try {
        const resp = await fetch(`/api/glossary/glossaries/${state.gl.currentGlossaryId}/import`, {
            method: 'POST',
            body: formData,
        });
        const data = await resp.json();
        if (data.success !== false) {
            const created = data.created || 0;
            const updated = data.updated || 0;
            const errors = data.errors || [];
            let msg = `Import complete: ${created} created, ${updated} updated.`;
            if (errors.length > 0) {
                msg += ` ${errors.length} error(s).`;
                console.error('Import errors:', errors);
                // Show errors in alert if there are any
                if (errors.length <= 5) {
                    alert(`Import completed with errors:\n\n${errors.join('\n')}`);
                } else {
                    alert(`Import completed with ${errors.length} errors. Check console for details.`);
                }
            }
            glShowToast(msg, created + updated > 0 ? 'fa-check-circle' : 'fa-exclamation-triangle');
            glLoadTerms();
        } else {
            const errorMsg = data.error || 'Unknown error';
            glShowToast('Import failed: ' + errorMsg, 'fa-times-circle');
            alert('Import failed: ' + errorMsg);
        }
    } catch (err) {
        glShowToast('Import error: ' + err.message, 'fa-times-circle');
    }

    // Reset file input
    e.target.value = '';
    setTimeout(() => { const t = document.getElementById('gl-toast'); if (t) t.classList.add('hidden'); }, 5000);
}

function glHandleExport() {
    if (!state.gl.currentGlossaryId) return;
    window.open(`/api/glossary/glossaries/${state.gl.currentGlossaryId}/export`, '_blank');
}


// --- Toast ---

function glShowToast(msg, iconClass) {
    const toast = document.getElementById('gl-toast');
    const icon = document.getElementById('gl-toast-icon');
    const text = document.getElementById('gl-toast-text');
    if (toast) toast.classList.remove('hidden');
    if (icon) {
        if (iconClass === 'fn-loader') {
            icon.className = '';
            icon.innerHTML = '<span class="fn-loader-inline"></span>';
        } else {
            icon.innerHTML = '';
            icon.className = `fas ${iconClass}`;
        }
    }
    if (text) text.textContent = msg;
}


// --- TARGET_LANGUAGES – mutable; refreshed from /api/languages on load ---
let TARGET_LANGUAGES = {
    "ar": "Arabic",
    "zh-CN": "Chinese - Simplified",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "it": "Italian",
    "ja": "Japanese - Japan",
    "fa": "Persian",
    "es": "Spanish",
    "th": "Thai",
    "pt-BR": "Portuguese - Brazil"
};

// Fetch active languages from backend and update TARGET_LANGUAGES
async function refreshTargetLanguages() {
    try {
        const resp = await fetch('/api/languages');
        const data = await resp.json();
        if (data.success && data.languages) {
            TARGET_LANGUAGES = data.languages;
        }
    } catch (_) {}
}

// Auto-refresh on page load
document.addEventListener('DOMContentLoaded', () => { refreshTargetLanguages(); });




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

async function initPushSection() {
    if (state.push.loaded) return;
    state.push.loaded = true;
    state.push._initDone = false;
    await refreshTargetLanguages();
    pushPopulateLangDropdown();
    pushSetupEventListeners();
    // Auto-select all languages by default
    document.querySelectorAll('.push-lang-cb').forEach(cb => { cb.checked = true; });
    const allCb = document.getElementById('push-lang-select-all');
    if (allCb) allCb.checked = true;
    state.push.locales = Object.keys(TARGET_LANGUAGES);
    const badge = document.getElementById('push-lang-badge');
    if (badge) badge.textContent = state.push.locales.length;
    state.push._initDone = true;
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

    // Pagination is now handled dynamically in pushRenderPagination()

    // Push Selected
    document.getElementById('push-selected-btn')?.addEventListener('click', () => pushStartSelected());

    // Push All Ready
    document.getElementById('push-all-ready-btn')?.addEventListener('click', () => pushStartAllReady());

    // Retry Failed
    document.getElementById('push-retry-failed-btn')?.addEventListener('click', () => pushRetryAllFailed());

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
    const jobs = articles * langs;
    // Update stat mini cards
    const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    setTxt('push-sel-article-count', articles);
    setTxt('push-sel-lang-count', langs);
    setTxt('push-sel-combo-count', jobs);
    // Update job chips in action bar
    setTxt('push-chip-articles', articles);
    setTxt('push-chip-langs', langs);
    setTxt('push-chip-jobs', jobs);
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
    if (tbody) tbody.innerHTML = `<tr><td colspan="${Math.max(colSpan, 2)}" class="empty-cell"><span class="fn-loader"></span> Loading…</td></tr>`;

    pushRenderTableHeader();

    if (state.push.locales.length === 0) {
        // No locales → just load titles
        const params = new URLSearchParams({ search: state.push.search, page: state.push.page, page_size: state.push.pageSize });
        return fetch(`/api/push/articles?${params}`)
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
        return fetch(`/api/push/articles-multi?${params}`)
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
                pushUpdateRetryButton();
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
        <th style="width:40px;padding-left:16px"><input type="checkbox" id="push-select-all" class="push-cb" title="Select all" aria-label="Select all"></th>
        <th class="push-th-title">Article Title</th>
        ${state.push.locales.map(code =>
            `<th class="push-th-lang" title="${escapeHtml(TARGET_LANGUAGES[code] || code)}">${code.toUpperCase()}</th>`
        ).join('')}
    `;
    // Bind select-all
    document.getElementById('push-select-all')?.addEventListener('change', (e) => {
        const checked = e.target.checked;
        state.push.articles.forEach(a => {
            const sid = String(a.intercom_id);
            if (checked) state.push.selectedIds.add(sid);
            else state.push.selectedIds.delete(sid);
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
        const iid = String(article.intercom_id);
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

        if (checked) tr.classList.add('push-row-selected');
        tr.innerHTML = `
            <td style="padding-left:16px"><input type="checkbox" class="push-row-cb push-cb" data-id="${iid}" ${checked ? 'checked' : ''} aria-label="Select article"></td>
            <td class="push-td-title"><a href="#" class="push-article-link" data-id="${iid}">${escapeHtml(article.title || 'Untitled')}</a></td>
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

    // Article title links — no drawer
    tbody.querySelectorAll('.push-article-link').forEach(link => {
        link.style.cursor = 'default';
        link.style.pointerEvents = 'none';
        link.style.color = 'inherit';
        link.style.textDecoration = 'none';
    });

    // Bind failed badge clicks — show popover with error + retry
    pushBindFailedBadges(tbody);
}

// ---------------------------------------------------------------------------
// Status badge (no push button — status only)
// ---------------------------------------------------------------------------
function pushRenderBadge(status, reason) {
    const map = {
        READY:               { cls: 'push-badge-ready',          label: 'Translated' },
        LIVE:                { cls: 'push-badge-live',           label: 'Live' },
        OUTDATED:            { cls: 'push-badge-outdated',       label: 'Outdated' },
        MISSING:             { cls: 'push-badge-missing',        label: 'Missing' },
        FAILED:              { cls: 'push-badge-failed',         label: 'Failed' },
        PENDING:             { cls: 'push-badge-pending',        label: 'Pushing…' },
        NEEDS_RETRANSLATION: { cls: 'push-badge-retranslation',  label: 'Re-translate' },
    };
    const d = map[status] || { cls: 'push-badge-nolang', label: '—' };
    return `<span class="push-badge ${d.cls}" title="${escapeHtml(reason || status)}"><div class="push-badge-dot"></div>${d.label}</span>`;
}

// ---------------------------------------------------------------------------
// Pagination (numbered with ellipsis)
// ---------------------------------------------------------------------------
function pushRenderPagination() {
    const totalPages = Math.max(1, Math.ceil(state.push.total / state.push.pageSize));
    const infoEl = document.getElementById('push-page-info');
    const btnsEl = document.getElementById('push-page-btns');

    if (infoEl) {
        const from = state.push.total === 0 ? 0 : (state.push.page - 1) * state.push.pageSize + 1;
        const to = Math.min(state.push.page * state.push.pageSize, state.push.total);
        infoEl.textContent = `Showing ${from} – ${to}  of  ${state.push.total} articles  ·  Page ${state.push.page} of ${totalPages}`;
    }
    if (!btnsEl) return;
    btnsEl.innerHTML = '';

    // Prev
    const prevBtn = document.createElement('button');
    prevBtn.className = 'push-page-btn';
    prevBtn.textContent = '← Prev';
    prevBtn.disabled = state.push.page <= 1;
    prevBtn.addEventListener('click', () => { if (state.push.page > 1) { state.push.page--; pushLoadArticles(); } });
    btnsEl.appendChild(prevBtn);

    // Page numbers with ellipsis
    const pages = [];
    if (totalPages <= 7) {
        for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
        pages.push(1);
        if (state.push.page > 3) pages.push('...');
        for (let i = Math.max(2, state.push.page - 1); i <= Math.min(totalPages - 1, state.push.page + 1); i++) pages.push(i);
        if (state.push.page < totalPages - 2) pages.push('...');
        pages.push(totalPages);
    }
    pages.forEach(p => {
        const btn = document.createElement('button');
        btn.className = 'push-page-btn' + (p === state.push.page ? ' push-page-active' : '');
        btn.textContent = p;
        if (p === '...') { btn.disabled = true; btn.style.cursor = 'default'; }
        else btn.addEventListener('click', () => { state.push.page = p; pushLoadArticles(); });
        btnsEl.appendChild(btn);
    });

    // Next
    const nextBtn = document.createElement('button');
    nextBtn.className = 'push-page-btn';
    nextBtn.textContent = 'Next →';
    nextBtn.disabled = state.push.page >= totalPages;
    nextBtn.addEventListener('click', () => { if (state.push.page < totalPages) { state.push.page++; pushLoadArticles(); } });
    btnsEl.appendChild(nextBtn);
}

// ---------------------------------------------------------------------------
// Push Selected
// ---------------------------------------------------------------------------
function pushStartSelected() {
    if (state.push.locales.length === 0) { showModalAlert('No Language Selected', 'Please select at least one language first.'); return; }
    if (state.push.selectedIds.size === 0) { showModalAlert('No Article Selected', 'Please select at least one article first.'); return; }

    const pairs = [];
    state.push.selectedIds.forEach(iid => {
        const article = state.push.articles.find(a => String(a.intercom_id) === String(iid));
        if (!article) return;
        const ld = article.locale_data || {};
        state.push.locales.forEach(loc => {
            const s = (ld[loc] || {}).status;
            if (s === 'READY' || s === 'OUTDATED') pairs.push({iid, locale: loc});
        });
    });

    if (pairs.length === 0) { showModalAlert('No Translations to Push', 'No translations available to push. Articles must be translated first before they can be pushed to Intercom.'); return; }
    pushShowConfirm(pairs, 'selected');
}

// ---------------------------------------------------------------------------
// Push All Ready
// ---------------------------------------------------------------------------
function pushStartAllReady() {
    if (state.push.locales.length === 0) { showModalAlert('No Language Selected', 'Please select at least one language first.'); return; }

    const pairs = [];
    state.push.articles.forEach(a => {
        const ld = a.locale_data || {};
        state.push.locales.forEach(loc => {
            const s = (ld[loc] || {}).status;
            if (s === 'READY' || s === 'OUTDATED') pairs.push({iid: a.intercom_id, locale: loc});
        });
    });

    if (pairs.length === 0) { showModalAlert('No Translations to Push', 'No translations available to push. Articles must be translated first before they can be pushed to Intercom.'); return; }
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
            <p style="color:#64748b;font-size:12px;">Only <em>Translated</em> items are included. Missing or failed translations are skipped.</p>
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
    // Re-bind failed badges and show retry button if any failed
    const tbody = document.getElementById('push-table-body');
    if (tbody) pushBindFailedBadges(tbody);
    pushUpdateRetryButton();
    // Refresh Content Hub in background so health status updates
    if (state.hub.loaded) loadHubArticles();
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
// Failed badge click — popover with error details + retry
// ---------------------------------------------------------------------------
function pushBindFailedBadges(container) {
    container.querySelectorAll('.push-td-lang').forEach(cell => {
        const badge = cell.querySelector('.push-badge-failed');
        if (!badge) return;
        badge.addEventListener('click', (e) => {
            e.stopPropagation();
            // Close any existing popover
            document.querySelectorAll('.push-fail-popover').forEach(p => p.remove());

            const iid = cell.dataset.iid;
            const locale = cell.dataset.locale;
            const article = state.push.articles.find(a => String(a.intercom_id) === String(iid));
            const reason = (article?.locale_data?.[locale]?.reason) || 'Unknown error';

            const popover = document.createElement('div');
            popover.className = 'push-fail-popover';
            popover.innerHTML = `
                <div class="fail-title">⚠ Push Failed</div>
                <div class="fail-reason">${escapeHtml(reason)}</div>
                <button class="fail-retry-btn" data-iid="${iid}" data-locale="${locale}">
                    🔄 Retry Push
                </button>
            `;
            cell.appendChild(popover);

            popover.querySelector('.fail-retry-btn').addEventListener('click', async (ev) => {
                ev.stopPropagation();
                popover.remove();
                await pushRetrySingle(iid, locale);
            });

            // Close popover when clicking outside
            const closeHandler = (ev) => {
                if (!popover.contains(ev.target) && ev.target !== badge) {
                    popover.remove();
                    document.removeEventListener('click', closeHandler);
                }
            };
            setTimeout(() => document.addEventListener('click', closeHandler), 0);
        });
    });
}

// Retry a single failed push
async function pushRetrySingle(iid, locale) {
    pushSetCellStatus(iid, locale, 'PENDING', 'Retrying…');
    try {
        const res = await fetch('/api/push/execute', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({intercom_id: iid, locale}),
        });
        const data = await res.json();
        if (data.success) {
            pushSetCellStatus(iid, locale, 'LIVE', 'Published successfully');
            pushShowToast('✓ Retry succeeded!', 'success');
        } else {
            pushSetCellStatus(iid, locale, 'FAILED', data.error || 'Push failed');
            pushShowToast('Retry failed: ' + (data.error || 'Unknown error'), 'warn');
        }
    } catch (e) {
        pushSetCellStatus(iid, locale, 'FAILED', e.message);
        pushShowToast('Retry failed: ' + e.message, 'warn');
    }
    // Re-bind failed badges after status change
    const tbody = document.getElementById('push-table-body');
    if (tbody) pushBindFailedBadges(tbody);
    pushUpdateRetryButton();
}

// Retry all failed pushes
async function pushRetryAllFailed() {
    const pairs = [];
    state.push.articles.forEach(a => {
        const ld = a.locale_data || {};
        state.push.locales.forEach(loc => {
            if ((ld[loc] || {}).status === 'FAILED') {
                pairs.push({iid: String(a.intercom_id), locale: loc});
            }
        });
    });
    if (pairs.length === 0) { pushShowToast('No failed pushes to retry.', 'warn'); return; }

    const retryBtn = document.getElementById('push-retry-failed-btn');
    if (retryBtn) { retryBtn.disabled = true; retryBtn.innerHTML = '🔄 &nbsp;Retrying…'; }

    let ok = 0, fail = 0;
    for (const {iid, locale} of pairs) {
        pushSetCellStatus(iid, locale, 'PENDING', 'Retrying…');
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
        ? `✓ All ${ok} retries succeeded!`
        : `${ok} succeeded, ${fail} still failed.`;
    pushShowToast(msg, fail === 0 ? 'success' : 'warn');

    if (retryBtn) { retryBtn.disabled = false; retryBtn.innerHTML = '🔄 &nbsp;Retry Failed'; }
    // Re-bind failed badges and update button visibility
    const tbody = document.getElementById('push-table-body');
    if (tbody) pushBindFailedBadges(tbody);
    pushUpdateRetryButton();
    if (state.hub.loaded) loadHubArticles();
}

// Show/hide "Retry Failed" button based on whether any FAILED cells exist
function pushUpdateRetryButton() {
    const retryBtn = document.getElementById('push-retry-failed-btn');
    if (!retryBtn) return;
    let hasFailed = false;
    state.push.articles.forEach(a => {
        const ld = a.locale_data || {};
        state.push.locales.forEach(loc => {
            if ((ld[loc] || {}).status === 'FAILED') hasFailed = true;
        });
    });
    retryBtn.style.display = hasFailed ? '' : 'none';
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
    body.innerHTML = '<div style="text-align:center;padding:40px;"><span class="fn-loader"></span> Loading preview…</div>';

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
function showModalAlert(title, message) {
    const overlay = document.getElementById('generic-confirm-overlay');
    const titleEl = document.getElementById('generic-confirm-title');
    const body = document.getElementById('generic-confirm-body');
    const okBtn = document.getElementById('generic-confirm-ok');
    const cancelBtn = document.getElementById('generic-confirm-cancel');
    if (!overlay || !titleEl || !body) return;
    titleEl.innerHTML = `<i class="fas fa-exclamation-triangle" style="color:var(--warning);"></i> ${escapeHtml(title)}`;
    body.innerHTML = `<p>${message}</p>`;
    if (okBtn) okBtn.style.display = 'none';
    if (cancelBtn) cancelBtn.textContent = 'OK';
    overlay.classList.remove('hidden');
    const closeHandler = () => {
        overlay.classList.add('hidden');
        if (okBtn) okBtn.style.display = '';
        if (cancelBtn) cancelBtn.textContent = 'Cancel';
    };
    if (cancelBtn) cancelBtn.onclick = closeHandler;
    const closeBtn = document.getElementById('generic-confirm-close');
    if (closeBtn) closeBtn.onclick = closeHandler;
}

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

// ===========================================================================
// Language Section
// ===========================================================================

// Map language codes → ISO 3166-1 alpha-2 country codes for flag images
const LANG_COUNTRY = {
    'ar': 'ae', 'bn-BD': 'bd', 'bs': 'ba', 'pt-BR': 'br', 'bg': 'bg',
    'ca': 'es', 'hr': 'hr', 'cs': 'cz', 'da': 'dk', 'nl': 'nl',
    'et': 'ee', 'fi': 'fi', 'fr': 'fr', 'de': 'de', 'el': 'gr',
    'he': 'il', 'hi': 'in', 'hu': 'hu', 'id': 'id', 'it': 'it',
    'ja': 'jp', 'ko': 'kr', 'lv': 'lv', 'lt': 'lt', 'ms': 'my',
    'mn': 'mn', 'nb': 'no', 'fa': 'ir', 'pl': 'pl', 'pt': 'pt',
    'ro': 'ro', 'ru': 'ru', 'sr': 'rs', 'zh-CN': 'cn', 'sl': 'si',
    'es': 'es', 'sw': 'ke', 'sv': 'se', 'th': 'th', 'zh-TW': 'tw',
    'tr': 'tr', 'uk': 'ua', 'ur': 'pk', 'vi': 'vn',
};

function langFlagImg(code, size = 28) {
    const cc = LANG_COUNTRY[code] || '';
    if (!cc) return `<span style="font-size:${size}px">\u{1F310}</span>`;
    return `<img src="https://flagcdn.com/w40/${cc}.png" srcset="https://flagcdn.com/w80/${cc}.png 2x" width="${size}" height="${Math.round(size * 0.7)}" alt="${cc}" style="border-radius:3px;object-fit:cover;vertical-align:middle" />`;
}

function initLanguageSection() {
    state.lang.loaded = true;

    // Search handler
    const searchInput = document.getElementById('lang-search');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            state.lang.search = searchInput.value.trim().toLowerCase();
            langRenderGrid();
        });
    }

    // Close any open dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.lang-card-menu') && !e.target.closest('.lang-dropdown')) {
            document.querySelectorAll('.lang-dropdown.open').forEach(d => d.classList.remove('open'));
        }
    });

    langLoadStats();
}

async function langLoadStats() {
    const grid = document.getElementById('lang-grid');
    if (!grid) return;
    grid.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted)"><span class="fn-loader"></span> Loading languages...</div>';

    try {
        const resp = await fetch('/api/languages/stats');
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Failed to load');
        state.lang.languages = data.languages || {};
        state.lang.totalArticles = data.total_articles || 0;

        // Sync the global TARGET_LANGUAGES so push/translate/glossary see new languages
        await refreshTargetLanguages();
        // Re-populate push language dropdown if already initialized
        if (state.push.loaded) pushPopulateLangDropdown();

        langRenderGrid();
    } catch (err) {
        grid.innerHTML = `<div style="text-align:center;padding:40px;color:#991b1b"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(err.message)}</div>`;
    }
}

function langRenderGrid() {
    const grid = document.getElementById('lang-grid');
    if (!grid) return;

    const langs = state.lang.languages;
    const search = state.lang.search;
    const total = state.lang.totalArticles || 1;

    let entries = Object.values(langs);
    if (search) {
        entries = entries.filter(l =>
            l.name.toLowerCase().includes(search) ||
            l.code.toLowerCase().includes(search)
        );
    }
    entries.sort((a, b) => a.name.localeCompare(b.name));

    // Build "Add Language(s)" card first
    const addCard = `
    <div class="lang-card-add" onclick="langOpenModal()">
        <i class="fas fa-plus-circle"></i>
        <span>Add Language(s)</span>
    </div>`;

    const cards = entries.map(l => {
        const translatedPct = total > 0 ? Math.round((l.translated / total) * 100) : 0;
        const pushedPct = total > 0 ? Math.round((l.pushed / total) * 100) : 0;
        const flag = langFlagImg(l.code, 32);

        return `
        <div class="lang-card" data-code="${escapeHtml(l.code)}">
            <div class="lang-card-top">
                <span class="lang-card-flag">${flag}</span>
                <button class="lang-card-menu" onclick="langToggleMenu(this, event)" title="Actions">
                    <i class="fas fa-ellipsis-v"></i>
                </button>
                <div class="lang-dropdown" id="lang-menu-${escapeHtml(l.code)}">
                    <button class="lang-dropdown-item" onclick="langAction('translate','${escapeHtml(l.code)}')">
                        <i class="fas fa-language"></i> Translate All
                    </button>
                    <button class="lang-dropdown-item" onclick="langAction('push','${escapeHtml(l.code)}')">
                        <i class="fas fa-upload"></i> Push All
                    </button>
                    <button class="lang-dropdown-item" onclick="langAction('details','${escapeHtml(l.code)}')">
                        <i class="fas fa-chart-bar"></i> View Details
                    </button>
                    <button class="lang-dropdown-item" onclick="langAction('remove','${escapeHtml(l.code)}')" style="color:#991b1b">
                        <i class="fas fa-trash-alt" style="color:#991b1b"></i> Remove
                    </button>
                </div>
            </div>
            <div class="lang-card-name">${escapeHtml(l.name)}<span class="lang-card-code">${escapeHtml(l.code)}</span></div>
            <div class="lang-progress-row">
                <div class="lang-progress-item">
                    <span class="lang-progress-label">Translated</span>
                    <div class="lang-progress-track">
                        <div class="lang-progress-bar translated" style="width:${translatedPct}%"></div>
                    </div>
                    <span class="lang-progress-pct">${translatedPct}%</span>
                </div>
                <div class="lang-progress-item">
                    <span class="lang-progress-label">Pushed</span>
                    <div class="lang-progress-track">
                        <div class="lang-progress-bar pushed" style="width:${pushedPct}%"></div>
                    </div>
                    <span class="lang-progress-pct">${pushedPct}%</span>
                </div>
            </div>
            <div class="lang-card-stats">
                <span class="lang-stat"><strong>${l.translated}</strong> / ${l.total} translated</span>
                <span class="lang-stat"><strong>${l.pushed}</strong> pushed</span>
                ${l.outdated ? `<span class="lang-stat" style="color:#b45309"><strong>${l.outdated}</strong> outdated</span>` : ''}
                ${l.failed ? `<span class="lang-stat" style="color:#991b1b"><strong>${l.failed}</strong> failed</span>` : ''}
            </div>
        </div>`;
    }).join('');

    grid.innerHTML = addCard + cards;
}

function langToggleMenu(btn, event) {
    event.stopPropagation();
    const dropdown = btn.nextElementSibling;
    // Close all others first
    document.querySelectorAll('.lang-dropdown.open').forEach(d => {
        if (d !== dropdown) d.classList.remove('open');
    });
    dropdown.classList.toggle('open');
}

function langAction(action, code) {
    document.querySelectorAll('.lang-dropdown.open').forEach(d => d.classList.remove('open'));

    switch (action) {
        case 'translate':
            switchSection('translate');
            break;
        case 'push':
            switchSection('push');
            break;
        case 'details':
            langShowDetails(code);
            break;
        case 'remove':
            langRemoveLanguage(code);
            break;
    }
}

function langShowDetails(code) {
    const l = state.lang.languages[code];
    if (!l) return;
    const total = l.total || 0;
    const translatedPct = total > 0 ? Math.round((l.translated / total) * 100) : 0;
    const pushedPct = total > 0 ? Math.round((l.pushed / total) * 100) : 0;
    const missing = total - l.translated - l.outdated - l.failed;

    alert(
        `${l.name} (${code})\n\n` +
        `Total Articles: ${total}\n` +
        `Translated: ${l.translated} (${translatedPct}%)\n` +
        `Pushed: ${l.pushed} (${pushedPct}%)\n` +
        `Outdated: ${l.outdated}\n` +
        `Failed: ${l.failed}\n` +
        `Missing: ${missing > 0 ? missing : 0}`
    );
}

let _langRemoveCode = null;

function langRemoveLanguage(code) {
    const l = state.lang.languages[code];
    const name = l ? l.name : code;
    _langRemoveCode = code;

    const flag = langFlagImg(code, 22);
    document.getElementById('lang-confirm-text').innerHTML =
        `<strong>Remove ${flag} ${escapeHtml(name)}</strong> <span style="color:var(--text-muted)">(${escapeHtml(code)})</span> from active languages?`;
    document.getElementById('lang-confirm-btn').disabled = false;
    document.getElementById('lang-confirm-btn').innerHTML = '<i class="fas fa-trash-alt"></i> Remove';
    document.getElementById('lang-confirm-overlay').classList.remove('hidden');
}

function langCloseConfirm() {
    document.getElementById('lang-confirm-overlay')?.classList.add('hidden');
    _langRemoveCode = null;
}

async function langDoRemove() {
    if (!_langRemoveCode) return;
    const btn = document.getElementById('lang-confirm-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="fn-loader-inline"></span> Removing...'; }

    try {
        const resp = await fetch(`/api/languages/${encodeURIComponent(_langRemoveCode)}/remove`, { method: 'DELETE' });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Failed');
        langCloseConfirm();
        await langLoadStats();
    } catch (err) {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-trash-alt"></i> Remove'; }
        alert('Error removing language: ' + err.message);
    }
}

// ─── Add Language Modal ─────────────────────────────────────────────────

let _langAvailable = {};       // {code: name} of languages not yet active
let _langModalSelected = new Set();

async function langOpenModal() {
    const overlay = document.getElementById('lang-modal-overlay');
    if (!overlay) return;

    // Fetch available languages
    try {
        const resp = await fetch('/api/languages/available');
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Failed');
        _langAvailable = data.available || {};
    } catch (err) {
        alert('Error loading available languages: ' + err.message);
        return;
    }

    _langModalSelected.clear();
    document.getElementById('lang-modal-search').value = '';
    overlay.classList.remove('hidden');
    langRenderModalList();
    langUpdateModalCount();
    document.getElementById('lang-modal-search').focus();
}

function langCloseModal() {
    document.getElementById('lang-modal-overlay')?.classList.add('hidden');
    _langModalSelected.clear();
}

function langRenderModalList(filter = '') {
    const listEl = document.getElementById('lang-modal-list');
    if (!listEl) return;

    let entries = Object.entries(_langAvailable).map(([code, name]) => ({ code, name }));
    if (filter) {
        entries = entries.filter(l =>
            l.name.toLowerCase().includes(filter) ||
            l.code.toLowerCase().includes(filter)
        );
    }
    entries.sort((a, b) => a.name.localeCompare(b.name));

    if (entries.length === 0) {
        listEl.innerHTML = '<div style="text-align:center;padding:30px;color:var(--text-muted)">No available languages found.</div>';
        return;
    }

    listEl.innerHTML = entries.map(l => {
        const flag = langFlagImg(l.code, 24);
        const checked = _langModalSelected.has(l.code) ? 'checked' : '';
        const selectedClass = _langModalSelected.has(l.code) ? ' selected' : '';
        return `
        <div class="lang-modal-item${selectedClass}" onclick="langModalToggle('${escapeHtml(l.code)}')">
            <input type="checkbox" ${checked} onclick="event.stopPropagation(); langModalToggle('${escapeHtml(l.code)}')" />
            <span class="lang-modal-item-flag">${flag}</span>
            <div class="lang-modal-item-info">
                <div class="lang-modal-item-name">${escapeHtml(l.name)}</div>
                <div class="lang-modal-item-code">${escapeHtml(l.code)}</div>
            </div>
        </div>`;
    }).join('');
}

function langModalToggle(code) {
    if (_langModalSelected.has(code)) {
        _langModalSelected.delete(code);
    } else {
        _langModalSelected.add(code);
    }
    const filter = (document.getElementById('lang-modal-search')?.value || '').trim().toLowerCase();
    langRenderModalList(filter);
    langUpdateModalCount();
}

function langUpdateModalCount() {
    const countEl = document.getElementById('lang-modal-count');
    const btn = document.getElementById('lang-modal-add-btn');
    const n = _langModalSelected.size;
    if (countEl) countEl.textContent = `${n} selected`;
    if (btn) {
        btn.disabled = n === 0;
        btn.textContent = n > 0 ? `Add ${n} Language${n > 1 ? 's' : ''}` : 'Add Selected';
    }
}

async function langConfirmAdd() {
    if (_langModalSelected.size === 0) return;
    const btn = document.getElementById('lang-modal-add-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Adding...'; }

    try {
        const resp = await fetch('/api/languages/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ codes: [..._langModalSelected] }),
        });
        const data = await resp.json();
        if (data.errors && data.errors.length) {
            alert('Some languages could not be added:\n' + data.errors.join('\n'));
        }
        langCloseModal();
        await langLoadStats();
    } catch (err) {
        alert('Error adding languages: ' + err.message);
        if (btn) { btn.disabled = false; btn.textContent = 'Add Selected'; }
    }
}

// Wire up modal search
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('lang-modal-search');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            const filter = searchInput.value.trim().toLowerCase();
            langRenderModalList(filter);
        });
    }
});