// ============================================================
// FundedNext Translation Hub - Frontend Application
// ============================================================

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

// Intercept all fetch calls to /api/ to add auth header automatically
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
    return _originalFetch.call(this, url, options);
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
        page: 1,
        pageSize: 25,
        total: 0,
        totalWords: 0,
        search: '',
        healthFilter: 'ALL',
        sortBy: 'attention',
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
        termPageSize: 25,
        termTotal: 0,
        termSearch: '',
        termSearchTimeout: null,
        editingGlossaryId: null,
        editingTermId: null,
        usage: {},
        drawerSelectedLanguages: new Set(),
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
            const isPassword = inp.type === 'password';
            inp.type = isPassword ? 'text' : 'password';
            toggle.innerHTML = isPassword ? '<i class="fas fa-eye-slash"></i>' : '<i class="fas fa-eye"></i>';
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

// ─── Admin panel ──────────────────────────────────────────
let adminState = { loaded: false, admins: [], tableExists: true };

async function initAdminSection() {
    if (adminState.loaded) { loadAdmins(); return; }
    adminState.loaded = true;

    // Check table
    try {
        const resp = await fetch('/api/auth/admins-table', { headers: authHeaders() });
        const data = await resp.json();
        if (!data.exists) {
            adminState.tableExists = false;
            const banner = document.getElementById('admin-setup-banner');
            const sqlPre = document.getElementById('admin-setup-sql');
            if (banner) banner.classList.remove('hidden');
            if (sqlPre) sqlPre.textContent = data.sql || '';
        }
    } catch (e) { /* ignore */ }

    // Copy SQL button
    const copyBtn = document.getElementById('admin-copy-sql');
    if (copyBtn) {
        copyBtn.addEventListener('click', () => {
            const sql = document.getElementById('admin-setup-sql').textContent;
            navigator.clipboard.writeText(sql);
            copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            setTimeout(() => { copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy SQL'; }, 2000);
        });
    }

    // Auto-create table button
    const autoCreateBtn = document.getElementById('admin-auto-create');
    if (autoCreateBtn) {
        autoCreateBtn.addEventListener('click', async () => {
            autoCreateBtn.disabled = true;
            autoCreateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...';
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
            autoCreateBtn.innerHTML = '<i class="fas fa-magic"></i> Auto-Create Table';
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
            addBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Adding...';

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
            addBtn.innerHTML = '<i class="fas fa-plus"></i> Add Admin';
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
    } catch (e) {
        adminState.admins = [];
    }

    // Always show super admin row at top
    const superAdmin = authState.user && authState.user.role === 'super_admin' ? authState.user : null;

    let html = '';

    // Super admin row (not deletable)
    if (superAdmin) {
        html += `<tr>
            <td><strong>${escapeHtml(superAdmin.name)}</strong></td>
            <td>${escapeHtml(superAdmin.email)}</td>
            <td><span class="admin-role-badge super_admin">Super Admin</span></td>
            <td><span class="admin-status-badge active">Active</span></td>
            <td>—</td>
            <td><span style="color:#94a3b8;font-size:12px;">Protected</span></td>
        </tr>`;
    }

    // Other admins
    if (adminState.admins.length === 0) {
        html += `<tr><td colspan="6" style="text-align:center;padding:20px;color:#94a3b8;">No other admins yet. Add one above.</td></tr>`;
    } else {
        for (const admin of adminState.admins) {
            const created = admin.created_at ? new Date(admin.created_at).toLocaleDateString() : '—';
            const statusClass = admin.is_active ? 'active' : 'inactive';
            const statusText = admin.is_active ? 'Active' : 'Inactive';
            html += `<tr data-admin-id="${admin.id}">
                <td>${escapeHtml(admin.name || '')}</td>
                <td>${escapeHtml(admin.email)}</td>
                <td><span class="admin-role-badge ${admin.role}">${admin.role}</span></td>
                <td><span class="admin-status-badge ${statusClass}">${statusText}</span></td>
                <td>${created}</td>
                <td>
                    <button class="admin-action-btn" title="Toggle Active" onclick="adminToggleActive(${admin.id}, ${!admin.is_active})">
                        <i class="fas fa-${admin.is_active ? 'ban' : 'check-circle'}"></i>
                    </button>
                    <button class="admin-action-btn delete" title="Delete" onclick="adminDelete(${admin.id})">
                        <i class="fas fa-trash"></i>
                    </button>
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
        'content-hub': 'Content Hub',
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
                case 'glossary':
                    await glLoadGlossaries();
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
    try {
        const response = await fetch('/api/dashboard/stats');
        if (!response.ok) throw new Error('Stats endpoint not available');
        const data = await response.json();
        if (data.success) {
            state.dashboardStats = data;
            renderDashboard(data);
        }
    } catch (error) {
        console.warn('Dashboard stats:', error.message);
        // If endpoint not available, render with placeholder data
        renderDashboard(getPlaceholderStats());
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
    setStatValue('stat-changed-week', formatNumber(data.changed_this_week || 0));
    setStatValue('stat-cost-month', '$' + (data.cost_month || 0).toFixed(2));

    // Charts
    renderChangesChart('week', data);
    renderCostChart('week', data);

    // Ranking table
    renderRankingTable(data.top_articles || []);

    // Recent activity
    renderActivityFeed(data.recent_activities || []);
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
                label: 'FAQ Changes',
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
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
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

    let labels, values;
    if (period === 'month') {
        labels = data.cost_monthly_labels || generateMonthLabels();
        values = data.cost_monthly || generateZeros(labels.length);
        } else {
        labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        values = data.cost_weekly || [0, 0, 0, 0, 0, 0, 0];
    }

    state.costChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Cost ($)',
                data: values,
                borderColor: '#dc2626',
                backgroundColor: 'rgba(220, 38, 38, 0.08)',
                fill: true,
                tension: 0.4,
                pointBackgroundColor: '#dc2626',
                pointRadius: 4,
                pointHoverRadius: 6,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: v => '$' + v.toFixed(2),
                        font: { size: 11 },
                        color: '#94a3b8'
                    },
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
        tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">No article change data available yet. Start translating to see rankings.</td></tr>';
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
            <td><span class="changes-badge"><i class="fas fa-arrow-up" style="font-size:10px"></i> ${article.changes || 0}</span></td>
            <td style="font-size:12px;color:#94a3b8;">${article.last_updated || '--'}</td>
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

    // Status badge click handlers
    const statTotal = document.getElementById('pull-stat-total');
    const statUpToDate = document.getElementById('pull-stat-uptodate');
    const statNeedsUpdate = document.getElementById('pull-stat-needsupdate');
    const statNever = document.getElementById('pull-stat-never');
    const statFailed = document.getElementById('pull-stat-failed');

    if (statTotal) {
        statTotal.closest('.pull-stat-chip')?.addEventListener('click', () => {
            state.pull.statusFilter = '';
            if (statusFilter) statusFilter.value = '';
            state.pull.page = 1;
            loadPullArticles();
            updatePullStatusBadges();
        });
    }
    if (statUpToDate) {
        statUpToDate.closest('.pull-stat-chip')?.addEventListener('click', () => {
            state.pull.statusFilter = 'up_to_date';
            if (statusFilter) statusFilter.value = 'up_to_date';
            state.pull.page = 1;
            loadPullArticles();
            updatePullStatusBadges();
        });
    }
    if (statNeedsUpdate) {
        statNeedsUpdate.closest('.pull-stat-chip')?.addEventListener('click', () => {
            state.pull.statusFilter = 'needs_update';
            if (statusFilter) statusFilter.value = 'needs_update';
            state.pull.page = 1;
            loadPullArticles();
            updatePullStatusBadges();
        });
    }
    if (statNever) {
        statNever.closest('.pull-stat-chip')?.addEventListener('click', () => {
            state.pull.statusFilter = 'never_pulled';
            if (statusFilter) statusFilter.value = 'never_pulled';
            state.pull.page = 1;
            loadPullArticles();
            updatePullStatusBadges();
        });
    }
    if (statFailed) {
        statFailed.closest('.pull-stat-chip')?.addEventListener('click', () => {
            state.pull.statusFilter = 'failed';
            if (statusFilter) statusFilter.value = 'failed';
            state.pull.page = 1;
            loadPullArticles();
            updatePullStatusBadges();
        });
    }

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

    // Pagination
    const prevBtn = document.getElementById('pull-prev-btn');
    const nextBtn = document.getElementById('pull-next-btn');
    if (prevBtn) prevBtn.addEventListener('click', () => { if (state.pull.page > 1) { state.pull.page--; loadPullArticles(); } });
    if (nextBtn) nextBtn.addEventListener('click', () => {
        const maxPage = Math.ceil(state.pull.total / state.pull.pageSize) || 1;
        if (state.pull.page < maxPage) { state.pull.page++; loadPullArticles(); }
    });

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
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...'; }
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
            setVal('pull-stat-total', data.total || 0);
            setVal('pull-stat-uptodate', data.up_to_date || 0);
            setVal('pull-stat-needsupdate', data.needs_update || 0);
            setVal('pull-stat-never', data.never_pulled || 0);
            setVal('pull-stat-failed', data.failed || 0);
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
    // Remove active class from all badges
    document.querySelectorAll('.pull-stat-chip').forEach(chip => {
        chip.classList.remove('pull-stat-chip-active');
    });
    
    // Add active class to the badge matching current filter
    const filter = state.pull.statusFilter || '';
    let activeChip = null;
    if (filter === '') {
        activeChip = document.getElementById('pull-stat-total')?.closest('.pull-stat-chip');
    } else if (filter === 'up_to_date') {
        activeChip = document.getElementById('pull-stat-uptodate')?.closest('.pull-stat-chip');
    } else if (filter === 'needs_update') {
        activeChip = document.getElementById('pull-stat-needsupdate')?.closest('.pull-stat-chip');
    } else if (filter === 'never_pulled') {
        activeChip = document.getElementById('pull-stat-never')?.closest('.pull-stat-chip');
    } else if (filter === 'failed') {
        activeChip = document.getElementById('pull-stat-failed')?.closest('.pull-stat-chip');
    }
    
    if (activeChip) {
        activeChip.classList.add('pull-stat-chip-active');
    }
}

async function loadPullArticles() {
    if (!state.pull.tableExists) return;
    const tbody = document.getElementById('pull-table-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="empty-cell"><i class="fas fa-spinner fa-spin"></i> Loading...</td></tr>';

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

        const tr = document.createElement('tr');
        if (isPulling) tr.classList.add('row-pulling');

        tr.innerHTML = `
            <td><input type="checkbox" data-iid="${iid}" ${checked ? 'checked' : ''} ${isPulling ? 'disabled' : ''}></td>
            <td><div class="pull-article-title" title="${escapeHtml(article.title || '')}">${escapeHtml(article.title || 'Untitled')}</div></td>
            <td>${renderPullBadge(needsPull)}</td>
            <td><span class="pull-state-badge pull-state-${(article.state || 'draft').toLowerCase()}">${escapeHtml(article.state || 'draft')}</span></td>
            <td class="pull-date-cell">${formatPullDate(article.pulled_at)}</td>
            <td class="pull-date-cell">${formatPullDate(article.source_updated_at)}</td>
        `;

        // Checkbox handler
        const cb = tr.querySelector('input[type="checkbox"]');
        cb.addEventListener('change', () => {
            if (cb.checked) {
                state.pull.selectedIds.add(iid);
            } else {
                state.pull.selectedIds.delete(iid);
            }
            updatePullSelectedCount();
            // Update select-all checkbox
            const selectAll = document.getElementById('pull-select-all');
            if (selectAll) selectAll.checked = state.pull.articles.every(a => state.pull.selectedIds.has(a.intercom_id));
        });

        tbody.appendChild(tr);
    });

    // Update select-all checkbox state
    const selectAll = document.getElementById('pull-select-all');
    if (selectAll) selectAll.checked = state.pull.articles.length > 0 && state.pull.articles.every(a => state.pull.selectedIds.has(a.intercom_id));

    updatePullSelectedCount();
}

function renderPullBadge(status) {
    const map = {
        'up_to_date':        '<span class="pull-badge pull-badge-uptodate"><i class="fas fa-check-circle"></i> Up to Date</span>',
        'updated_in_source': '<span class="pull-badge pull-badge-updated"><i class="fas fa-exclamation-triangle"></i> Needs Update</span>',
        'never_pulled':      '<span class="pull-badge pull-badge-never"><i class="far fa-circle"></i> Never Pulled</span>',
        'failed':            '<span class="pull-badge pull-badge-failed"><i class="fas fa-times-circle"></i> Pull Failed</span>',
        'pulling':           '<span class="pull-badge pull-badge-pulling"><i class="fas fa-spinner fa-spin"></i> Pulling...</span>',
    };
    return map[status] || map['never_pulled'];
}

function formatPullDate(isoStr) {
    if (!isoStr) return '<span style="color:#cbd5e1">—</span>';
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
    const infoEl = document.getElementById('pull-page-info');
    const prevBtn = document.getElementById('pull-prev-btn');
    const nextBtn = document.getElementById('pull-next-btn');

    if (infoEl) {
        const from = state.pull.total === 0 ? 0 : (state.pull.page - 1) * state.pull.pageSize + 1;
        const to = Math.min(state.pull.page * state.pull.pageSize, state.pull.total);
        infoEl.textContent = `Showing ${from}–${to} of ${state.pull.total} articles (Page ${state.pull.page} of ${maxPage})`;
    }
    if (prevBtn) prevBtn.disabled = state.pull.page <= 1;
    if (nextBtn) nextBtn.disabled = state.pull.page >= maxPage;
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
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...'; }
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
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-sync-alt"></i> Sync Source List'; }
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
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Pulling...'; }
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
        } else {
            showPullToast('Pull failed: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (err) {
        showPullToast('Pull failed: ' + err.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-cloud-download-alt"></i> Pull Selected (<span id="pull-selected-count">0</span>)'; }
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
        if (icon) icon.className = 'fas fa-check-circle';
    } else if (type === 'error') {
        toast.classList.add('toast-error');
        if (icon) icon.className = 'fas fa-exclamation-circle';
        } else {
        if (icon) icon.className = 'fas fa-spinner fa-spin';
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
    // Filter buttons
    document.querySelectorAll('.ch-filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.ch-filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.hub.healthFilter = btn.getAttribute('data-health');
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
                if (checked) state.hub.selectedIds.add(a.intercom_id);
                else state.hub.selectedIds.delete(a.intercom_id);
            });
            renderHubTable();
            updateHubBulkBar();
        });
    }

    // Pagination
    const prevBtn = document.getElementById('ch-prev-btn');
    const nextBtn = document.getElementById('ch-next-btn');
    if (prevBtn) prevBtn.addEventListener('click', () => { if (state.hub.page > 1) { state.hub.page--; loadHubArticles(); } });
    if (nextBtn) nextBtn.addEventListener('click', () => {
        const maxPage = Math.ceil(state.hub.total / state.hub.pageSize) || 1;
        if (state.hub.page < maxPage) { state.hub.page++; loadHubArticles(); }
    });

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
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="empty-cell"><i class="fas fa-spinner fa-spin"></i> Loading articles...</td></tr>';

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
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">No articles match this filter. Try syncing from the <strong>Pull</strong> section first.</td></tr>';
        return;
    }
    
    tbody.innerHTML = '';
    state.hub.articles.forEach(article => {
        const iid = article.intercom_id;
        const checked = state.hub.selectedIds.has(iid);
        const health = article.health || 'NEEDS_PULL';
        const rowClass = {
            'NEEDS_PULL': 'ch-row-needs-pull',
            'OUTDATED': 'ch-row-outdated',
            'NEEDS_TRANSLATION': 'ch-row-needs-translation',
        }[health] || '';

        const tr = document.createElement('tr');
        if (rowClass) tr.classList.add(rowClass);

        tr.innerHTML = `
            <td><input type="checkbox" data-iid="${iid}" ${checked ? 'checked' : ''}></td>
            <td class="ch-title-cell">
                <span class="ch-article-title" title="${escapeHtml(article.title || '')}">${escapeHtml(article.title || 'Untitled')}</span>
                <span class="ch-article-path">${article.collection_name ? escapeHtml(article.collection_name) + ' <i class="fas fa-chevron-right"></i> Article' : 'Article'}</span>
            </td>
            <td class="ch-word-cell">${article.source_updated_relative || '—'}</td>
            <td>${article.pulled ? '<span class="ch-pulled-yes">✓</span>' : '<span class="ch-pulled-no">—</span>'}</td>
            <td>${renderLangChips(article.lang_statuses || {})}</td>
            <td style="text-align:center">${renderHealthBadge(health)}</td>
        `;

        // Checkbox
        const cb = tr.querySelector('input[type="checkbox"]');
        cb.addEventListener('click', (e) => e.stopPropagation());
        cb.addEventListener('change', () => {
            if (cb.checked) state.hub.selectedIds.add(iid);
            else state.hub.selectedIds.delete(iid);
            updateHubBulkBar();
            const selectAll = document.getElementById('ch-select-all');
            if (selectAll) selectAll.checked = state.hub.articles.every(a => state.hub.selectedIds.has(a.intercom_id));
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
        'NEEDS_PULL':        '<span class="ch-health-badge ch-health-NEEDS_PULL"><i class="fas fa-cloud-download-alt"></i> Needs Pull</span>',
        'OUTDATED':          '<span class="ch-health-badge ch-health-OUTDATED"><i class="fas fa-exclamation-triangle"></i> Outdated</span>',
        'NEEDS_TRANSLATION': '<span class="ch-health-badge ch-health-NEEDS_TRANSLATION"><i class="fas fa-globe"></i> Needs Translation</span>',
        'NEEDS_PUSH':        '<span class="ch-health-badge ch-health-NEEDS_PUSH"><i class="fas fa-cloud-upload-alt"></i> Ready to Push</span>',
        'COMPLETE':          '<span class="ch-health-badge ch-health-COMPLETE"><i class="fas fa-check-circle"></i> Complete</span>',
        'FAILED':            '<span class="ch-health-badge ch-health-FAILED"><i class="fas fa-times-circle"></i> Failed</span>',
    };
    return map[health] || map['NEEDS_PULL'];
}

function renderHubPagination() {
    const maxPage = Math.ceil(state.hub.total / state.hub.pageSize) || 1;
    const infoEl = document.getElementById('ch-page-info');
    const prevBtn = document.getElementById('ch-prev-btn');
    const nextBtn = document.getElementById('ch-next-btn');

    if (infoEl) {
        const from = state.hub.total === 0 ? 0 : (state.hub.page - 1) * state.hub.pageSize + 1;
        const to = Math.min(state.hub.page * state.hub.pageSize, state.hub.total);
        infoEl.textContent = `Showing ${from}–${to} of ${state.hub.total} articles (Page ${state.hub.page} of ${maxPage})`;
    }
    if (prevBtn) prevBtn.disabled = state.hub.page <= 1;
    if (nextBtn) nextBtn.disabled = state.hub.page >= maxPage;
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
    body.innerHTML = '<div style="text-align:center;padding:40px;"><i class="fas fa-spinner fa-spin" style="font-size:24px;color:#94a3b8;"></i></div>';

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
function hubBulkAction(actionType) {
    const ids = Array.from(state.hub.selectedIds);
    if (ids.length === 0) return;

    if (actionType === 'pull') {
        // Switch to Pull section and trigger pull for these IDs
        switchSection('pull');
        // Give Pull section time to init, then set selection
        setTimeout(() => {
            ids.forEach(id => state.pull.selectedIds.add(id));
            updatePullSelectedCount();
            renderPullTable();
        }, 500);
    } else if (actionType === 'translate') {
        switchSection('translate');
        // Pre-select articles in translate section
        setTimeout(() => {
            ids.forEach(id => state.tr.selectedArticles.add(id));
            trUpdateActionBar();
            trRenderTable();
        }, 500);
    } else if (actionType === 'push') {
        switchSection('push');
        // Pre-select articles in push section
        setTimeout(() => {
            ids.forEach(id => state.push.selectedIds.add(id));
            pushUpdateJobCounter();
            pushUpdateActionButtons();
            pushRenderTable();
        }, 500);
    }
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

    // Filter buttons
    document.querySelectorAll('#tr-filter-bar .tr-filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#tr-filter-bar .tr-filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.tr.statusFilter = btn.dataset.status || 'ALL';
            state.tr.page = 1;
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

    // Pagination
    const prevBtn = document.getElementById('tr-prev-btn');
    const nextBtn = document.getElementById('tr-next-btn');
    if (prevBtn) prevBtn.addEventListener('click', () => { if (state.tr.page > 1) { state.tr.page--; trLoadArticles(); } });
    if (nextBtn) nextBtn.addEventListener('click', () => {
        const maxPage = Math.ceil(state.tr.total / state.tr.pageSize);
        if (state.tr.page < maxPage) { state.tr.page++; trLoadArticles(); }
    });

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
    if (tbody) tbody.innerHTML = '<tr><td colspan="20" class="empty-cell"><i class="fas fa-spinner fa-spin"></i> Loading...</td></tr>';

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
    const el = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
    el('tr-count-ALL', c.ALL || 0);
    el('tr-count-NEEDS', (c.NOT_STARTED || 0) + (c.OUTDATED || 0));
    el('tr-count-OUTDATED', c.OUTDATED || 0);
    el('tr-count-INPROGRESS', c.IN_PROGRESS || 0);
    el('tr-count-TRANSLATED', (c.TRANSLATED || 0) + (c.APPROVED || 0));
    el('tr-count-FAILED', c.FAILED || 0);
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
            <td><input type="checkbox" class="tr-row-cb" data-id="${a.intercom_id}" ${isSelected ? 'checked' : ''}></td>
            <td>
                <span class="tr-article-title" data-id="${a.intercom_id}">${escapeHtml(a.title)}</span>
                <span class="tr-article-collection">${escapeHtml(a.collection_name || 'Uncategorized')}</span>
            </td>`;
        for (const [loc] of langs) {
            const st = (a.lang_statuses && a.lang_statuses[loc]) || 'NOT_STARTED';
            bodyHtml += `<td class="tr-cell-lang">${trStatusChip(st)}</td>`;
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
        'NOT_STARTED': { cls: 'not-started', label: 'New' },
        'IN_PROGRESS': { cls: 'in-progress', label: 'Translating' },
        'OUTDATED':    { cls: 'outdated', label: 'Outdated' },
        'TRANSLATED':  { cls: 'translated', label: 'Done' },
        'APPROVED':    { cls: 'approved', label: 'Approved' },
        'FAILED':      { cls: 'failed', label: 'Failed' },
    };
    const m = map[status] || map['NOT_STARTED'];
    return `<span class="tr-status-chip ${m.cls}">${m.label}</span>`;
}


function trRenderPagination() {
    const maxPage = Math.max(1, Math.ceil(state.tr.total / state.tr.pageSize));
    const info = document.getElementById('tr-page-info');
    const prevBtn = document.getElementById('tr-prev-btn');
    const nextBtn = document.getElementById('tr-next-btn');
    if (info) info.textContent = `Page ${state.tr.page} of ${maxPage} (${state.tr.total} articles)`;
    if (prevBtn) prevBtn.disabled = state.tr.page <= 1;
    if (nextBtn) nextBtn.disabled = state.tr.page >= maxPage;
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
    trShowToast('Translating...', 'fa-spinner fa-spin');

    try {
        const resp = await fetch('/api/translate-hub/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ intercom_ids: articleIds, locales: locales }),
        });
        const data = await resp.json();
        if (data.success) {
            const msg = `Completed: ${data.completed} success, ${data.failed} failed out of ${data.total_jobs} jobs.`;
            trShowToast(msg, data.failed > 0 ? 'fa-exclamation-triangle' : 'fa-check-circle');
        } else {
            trShowToast(`Error: ${data.error || 'Unknown'}`, 'fa-times-circle');
        }
    } catch (e) {
        trShowToast(`Network error: ${e.message}`, 'fa-times-circle');
    }

    state.tr.translating = false;
    state.tr.selectedArticles.clear();
    trUpdateActionBar();
    // Reload data to refresh statuses
    setTimeout(() => trLoadArticles(), 1000);
    // Auto-hide toast after 6 seconds
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

    trShowToast('Finding missing translations...', 'fa-spinner fa-spin');

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
                    <i class="fas fa-magic"></i> This will translate all NOT_STARTED and OUTDATED articles.
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
    if (drawerBody) drawerBody.innerHTML = '<div style="text-align:center;padding:40px;"><i class="fas fa-spinner fa-spin" style="font-size:2rem;color:var(--text-muted);"></i></div>';
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
    trShowToast(`Translating to ${state.tr.languages[locale] || locale}...`, 'fa-spinner fa-spin');

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
    if (icon) { icon.className = `fas ${iconClass}`; }
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
        glShowToast('Creating tables...', 'fa-spinner fa-spin');
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
    document.querySelectorAll('.tr-filter-btn[data-filter]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tr-filter-btn').forEach(b => b.classList.remove('active'));
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
            glShowToast('Importing...', 'fa-spinner fa-spin');
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
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="empty-cell"><i class="fas fa-spinner fa-spin"></i> Loading...</td></tr>';

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

function glRenderFilterCounts() {
    // Update filter button counts (would need separate API calls or compute from current data)
    // For now, just show active state
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
    createBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...';
    
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
    if (tbody) tbody.innerHTML = `<tr><td colspan="${colCount}" class="empty-cell"><i class="fas fa-spinner fa-spin"></i> Loading...</td></tr>`;

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

    glShowToast('Importing...', 'fa-spinner fa-spin');

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
    if (icon) icon.className = `fas ${iconClass}`;
    if (text) text.textContent = msg;
}


// --- Expose TARGET_LANGUAGES for glossary modal ---
const TARGET_LANGUAGES = {
    "ar": "Arabic (UAE)",
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