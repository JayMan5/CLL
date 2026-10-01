// Escape untrusted values only at the HTML rendering boundary.
function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[char]));
}
function safeRecord(value) {
    if (typeof value === 'string') return escapeHTML(value);
    if (Array.isArray(value)) return value.map(safeRecord);
    if (value && typeof value === 'object') {
        return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, safeRecord(item)]));
    }
    return value;
}
// Never put user-controlled identifiers inside executable JavaScript attributes.
document.addEventListener('click', event => {
    const button = event.target.closest('[data-case-action]');
    if (!button) return;
    const actions = {
        scan: shortcutQRScan, hearing: shortcutHearingLog, assign: openAssignJudgeModal,
        assignSheriff: openAssignSheriffModal, handover: openSheriffHandoverModal,
        writ: selectCaseForWrit, override: openDCROverrideModal, ruling: logJudicialRuling,
        deleteUser: deleteUserAccount, resetPassword: resetUserPassword, explain: showExplainability
    };
    const action = actions[button.dataset.caseAction];
    if (action) action(button.dataset.recordId);
});

// ===== GLOBAL STATE =====
const API_BASE = "/api";
let casesData = [];
let usersData = [];
let whatsappLogs = [];
let currentUserId = null;
let accessToken = null;
let authenticatedUser = null;
let refreshPromise = null;
let sessionExpiryHandled = false;
let demoMode = false;
let distributionChart = null;
let currentHearingOutcome = "Adjourned";
let activeOverrideCaseId = null;
let selectedWritCaseId = null;
let activeSheriffCustodyCaseId = null;
let activeSheriffCustodyMode = null;

// ===== USER PROFILES (5-Level Access Hierarchy) =====
const USER_PROFILES = {
    "usr_sheriff_01": { user_id: "usr_sheriff_01", name: "Level 1: Sheriff", role: "Sheriff", badge: "Physical File Custodian", court: "FHC Abuja Court 4", division: "Criminal", initials: "SH" },
    "usr_clerk_01": { user_id: "usr_clerk_01", name: "Level 2: Clerk", role: "Clerk", badge: "Data Entry & Event Logger", court: "FHC Abuja Court 4", division: "Criminal", initials: "CL" },
    "usr_dcr_01": { user_id: "usr_dcr_01", name: "Level 3: Deputy Chief Registrar", role: "DCR", badge: "Division Supervisor", court: "FHC Abuja", division: "Criminal", initials: "DC" },
    "usr_cr_01": { user_id: "usr_cr_01", name: "Level 4: Chief Registrar", role: "Chief Registrar", badge: "Court Administrator & Compliance Officer", court: "All Courts", division: "All Divisions", initials: "CR" },
    "usr_judge_01": { user_id: "usr_judge_01", name: "Level 5: Judge", role: "Judge", badge: "Decision Maker & Accountability Owner", court: "FHC Abuja Court 4", division: "Criminal", initials: "JG" },
};

// ===== AUTH & SESSION MANAGEMENT =====

function getActiveUser() {
    if (authenticatedUser) {
        const initials = String(authenticatedUser.name || authenticatedUser.username || "User")
            .split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join("").toUpperCase();
        return { ...authenticatedUser, initials: initials || "U" };
    }
    if (currentUserId && USER_PROFILES[currentUserId]) return USER_PROFILES[currentUserId];
    return USER_PROFILES["usr_clerk_01"];
}

async function loadAppConfig() {
    try {
        const response = await fetch(`${API_BASE}/config`, { credentials: "same-origin" });
        if (!response.ok) return;
        const config = await response.json();
        demoMode = config.demo_mode === true;
    } catch (_) {
        demoMode = false; // Fail closed: hide simulator-only UI if config cannot be read.
    }
    const status = document.getElementById("whatsapp-mode-status");
    if (status) status.textContent = demoMode ? "DEMO SIMULATOR — NOT LIVE DELIVERY" : "Simulator disabled in this environment";
    const nav = document.getElementById("nav-whatsapp");
    if (nav) nav.style.display = "none";
}

function getTheme() {
    return document.documentElement.getAttribute('data-theme') || 'dark';
}

function updateThemeIcon(theme) {
    const icon = document.getElementById('theme-icon');
    if (!icon) return;
    if (theme === 'dark') {
        icon.className = 'fa-solid fa-moon text-accent';
    } else {
        icon.className = 'fa-solid fa-sun text-amber-400';
    }
}

function getAuthHeaders() {
    const headers = { "Content-Type": "application/json" };
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    return headers;
}

function clearClientSession() {
    accessToken = null;
    authenticatedUser = null;
    currentUserId = null;
    casesData = [];
    usersData = [];
    whatsappLogs = [];
    activeSheriffCustodyCaseId = null;
    activeSheriffCustodyMode = null;
    ["cases-table-body", "dcr-approval-table-body", "judge-docket-table-body", "judgments-table-body",
        "ai-risk-table-body", "users-admin-table-body", "whatsapp-logs-container", "case-scan-history"]
        .forEach(id => document.getElementById(id)?.replaceChildren());
    ["stat-total-cases", "stat-high-risk", "stat-custody-alerts", "stat-enforcement-alerts",
        "alert-count-custody", "alert-count-enforcement", "judge-alert-count", "ai-total-cases"]
        .forEach(id => { const el = document.getElementById(id); if (el) el.textContent = "0"; });
    document.getElementById("quick-alert-bar")?.classList.add("hidden");
    ["scan-case-id", "missing-case-id", "hearing-case-id"].forEach(id => {
        const select = document.getElementById(id);
        if (select) select.replaceChildren(new Option("Select a case", ""));
    });
    ["new-case-id", "new-case-counsel", "new-case-litigant", "upload-case-id", "writ-case-id",
        "writ-sheriff-id", "reassign-case-id", "assign-judge-case-id", "assign-sheriff-case-id"]
        .forEach(id => { const input = document.getElementById(id); if (input) input.value = ""; });
    const overrideCase = document.getElementById("override-modal-case-id");
    if (overrideCase) overrideCase.textContent = "";
    document.getElementById("password-change-overlay")?.classList.add("hidden");
    document.getElementById("add-user-overlay")?.classList.add("hidden");
    document.getElementById("form-password-change")?.reset();
    document.getElementById("form-add-user")?.reset();
    document.getElementById("form-login")?.reset();
    document.getElementById("form-sheriff-custody")?.reset();
    document.getElementById("sheriff-custody-modal")?.classList.add("hidden");
    if (document.getElementById("role-switcher-select")) updateRoleUI();
    if (distributionChart) distributionChart.destroy();
    distributionChart = null;
    // Clear tokens left by older versions; tokens are no longer persisted in web storage.
    localStorage.removeItem("courtlog-access-token");
    localStorage.removeItem("courtlog-refresh-token");
    localStorage.removeItem("courtlog-active-user");
}

async function refreshSession() {
    if (refreshPromise) return refreshPromise;
    refreshPromise = (async () => {
        try {
            const response = await fetch(`${API_BASE}/refresh`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin"
            });
            if (!response.ok) return false;
            const data = await response.json();
            if (!data.access_token || !data.user) return false;
            accessToken = data.access_token;
            authenticatedUser = data.user;
            currentUserId = data.user.user_id;
            sessionExpiryHandled = false;
            return true;
        } catch (error) {
            logger(`Session refresh unavailable: ${error}`);
            return false;
        }
    })();
    try {
        return await refreshPromise;
    } finally {
        refreshPromise = null;
    }
}

async function expireClientSession() {
    if (sessionExpiryHandled) return;
    sessionExpiryHandled = true;
    try {
        await fetch(`${API_BASE}/logout`, { method: "POST", credentials: "same-origin" });
    } catch (_) { /* The server may be offline; still clear local state. */ }
    clearClientSession();
    const overlay = document.getElementById("login-overlay");
    if (overlay) overlay.classList.remove("hidden");
    showToast("Your session ended. Please sign in again.", "warning");
}

async function apiFetch(url, options = {}) {
    const protectedRoute = typeof url === "string" && url.startsWith(`${API_BASE}/`) &&
        ![`${API_BASE}/login`, `${API_BASE}/refresh`, `${API_BASE}/logout`].includes(url.split("?")[0]);
    const makeRequest = () => {
        const headers = new Headers(options.headers || {});
        if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
        else headers.delete("Authorization");
        return fetch(url, { ...options, headers, credentials: "same-origin" });
    };

    let response = await makeRequest();
    if (response.status === 401 && protectedRoute) {
        if (await refreshSession()) response = await makeRequest();
        if (response.status === 401) await expireClientSession();
    }
    if (response.status === 403 && response.headers.get("X-Password-Change-Required") === "true") {
        showPasswordChangePrompt();
    }
    return response;
}

async function handleLoginSubmit(event) {
    event.preventDefault();
    const username = document.getElementById("login-username").value.trim();
    const password = document.getElementById("login-password").value;
    const errorMsg = document.getElementById("login-error-msg");
    const errorText = document.getElementById("login-error-text");
    const submitBtn = document.getElementById("btn-login-submit");

    if (!username || !password) return;

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Authenticating...';

    try {
        const response = await fetch(`${API_BASE}/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ username, password })
        });

        if (!response.ok) {
            const err = await response.json();
            errorText.textContent = err.detail || "Invalid username or password.";
            errorMsg.classList.remove("hidden");
            return;
        }

        const data = await response.json();
        if (!data.access_token || !data.user) throw new Error("Invalid sign-in response");
        accessToken = data.access_token;
        authenticatedUser = data.user;
        currentUserId = data.user.user_id;
        sessionExpiryHandled = false;
        localStorage.removeItem("courtlog-access-token");
        localStorage.removeItem("courtlog-refresh-token");
        localStorage.removeItem("courtlog-active-user");

        errorMsg.classList.add("hidden");
        document.getElementById("login-overlay").classList.add("hidden");
        updateRoleUI();
        if (authenticatedUser.must_change_password) {
            showPasswordChangePrompt();
            return;
        }
        await loadDashboardData();
        if (authenticatedUser.role === "Chief Registrar") await loadUsersData();

        logger(`Authenticated as ${getActiveUser().name} (${getActiveUser().role})`);
    } catch (error) {
        errorText.textContent = "Connection error. Is the server running?";
        errorMsg.classList.remove("hidden");
        logger(`Login error: ${error}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-right-to-bracket"></i> Sign In to Portal';
    }
}

async function handleLogout() {
    try {
        await fetch(`${API_BASE}/logout`, { method: "POST", credentials: "same-origin" });
    } catch (error) {
        logger(`Server logout unavailable: ${error}`);
    }
    clearClientSession();
    document.getElementById("login-overlay").classList.remove("hidden");
    document.getElementById("password-change-overlay")?.classList.add("hidden");
    document.getElementById("add-user-overlay")?.classList.add("hidden");
    const form = document.getElementById("form-login");
    if (form) form.reset();
    switchTab("tab-overview");
    logger("User logged out.");
}

function changeActiveRole(userId) {
    // Authorization belongs to the signed-in account; a browser-side selector cannot switch roles.
    if (!authenticatedUser || userId !== authenticatedUser.user_id) {
        updateRoleUI();
    }
}

function showPasswordChangePrompt() {
    const overlay = document.getElementById("password-change-overlay");
    if (overlay) overlay.classList.remove("hidden");
    document.getElementById("password-current")?.focus();
}

async function submitPasswordChange(event) {
    event.preventDefault();
    const error = document.getElementById("password-change-error");
    const current = document.getElementById("password-current").value;
    const next = document.getElementById("password-new").value;
    const confirmNext = document.getElementById("password-confirm").value;
    if (next !== confirmNext) {
        error.textContent = "The new password and confirmation do not match.";
        error.classList.remove("hidden");
        return;
    }
    const button = document.getElementById("btn-password-change-submit");
    button.disabled = true;
    try {
        const response = await apiFetch(`${API_BASE}/users/me/password`, {
            method: "POST", headers: getAuthHeaders(),
            body: JSON.stringify({ current_password: current, new_password: next })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            error.textContent = data.detail || "Password change failed.";
            error.classList.remove("hidden");
            return;
        }
        document.getElementById("form-password-change").reset();
        document.getElementById("password-change-overlay").classList.add("hidden");
        showToast("Password changed. Sign in with your new password.", "success");
        await handleLogout();
    } catch (err) {
        error.textContent = "Connection error while changing your password.";
        error.classList.remove("hidden");
    } finally {
        button.disabled = false;
    }
}

function updateSimulationClock() {
    const clockEl = document.getElementById("simulation-clock");
    if (!clockEl) return;
    const now = new Date();
    clockEl.textContent = now.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
}

// ===== APP INITIALIZATION =====
document.addEventListener("DOMContentLoaded", async function () {
    // Discard bearer/refresh tokens from pre-cookie versions; identity is re-derived from the server.
    localStorage.removeItem("courtlog-access-token");
    localStorage.removeItem("courtlog-refresh-token");
    localStorage.removeItem("courtlog-active-user");
    await loadAppConfig();
    updateSimulationClock();

    if (await refreshSession()) {
        document.getElementById("login-overlay").classList.add("hidden");
        updateRoleUI();
        if (authenticatedUser.must_change_password) {
            showPasswordChangePrompt();
            return;
        }
        await loadDashboardData();
        if (authenticatedUser.role === "Chief Registrar") await loadUsersData();
    } else {
        document.getElementById("login-overlay").classList.remove("hidden");
    }
});

// ===== UI UTILITIES =====

function animateOpenModal(id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.remove("hidden");
    const panel = m.querySelector('.glass-panel') || m.firstElementChild;
    if (panel) {
        panel.style.animation = "modalSpring 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.2) forwards";
    }
}
function animateCloseModal(id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.add("hidden");
}
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) { console.warn("Toast container not found"); return; }
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    const icons = { success: "fa-circle-check", error: "fa-circle-xmark", warning: "fa-triangle-exclamation", info: "fa-circle-info" };
    toast.innerHTML = `<i class="fa-solid ${icons[type] || icons.info}"></i><span>${escapeHTML(message)}</span><button onclick="this.parentElement.remove()" class="toast-close">&times;</button>`;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("toast-visible"));
    setTimeout(() => { toast.classList.remove("toast-visible"); setTimeout(() => toast.remove(), 400); }, 4000);
}
// ===== THEME SYSTEM =====
(function initTheme() {
    const saved = localStorage.getItem('courtlog-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    document.addEventListener('DOMContentLoaded', () => updateThemeIcon(saved));
})();

function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('courtlog-theme', next);
    updateThemeIcon(next);
    // Re-render chart with updated theme colors
    if (distributionChart) {
        distributionChart.destroy();
        distributionChart = null;
    }
    renderChart();
}

function updateRoleUI() {
    const user = getActiveUser();
    const select = document.getElementById("role-switcher-select");
    if (select) {
        if (user.user_id && !Array.from(select.options).some(option => option.value === user.user_id)) {
            const option = document.createElement("option");
            option.value = user.user_id;
            option.textContent = `${user.role}: ${user.name}`;
            select.appendChild(option);
        }
        select.value = user.user_id || "";
        select.disabled = true;
        select.title = "Access level is determined by the authenticated account.";
    }

    document.getElementById("sidebar-user-name").textContent = user.name;
    document.getElementById("sidebar-user-role").textContent = user.badge;
    document.getElementById("active-user-initials").textContent = user.initials;
    const scanOperator = document.getElementById("scan-authenticated-operator");
    if (scanOperator) {
        scanOperator.textContent = authenticatedUser?.user_id ? `${user.name} (${user.role})` : "No authenticated account";
    }

    // Toggle tab permissions according to Permission Matrix
    const role = user.role;

    const navCustody = document.getElementById("nav-qr-scan");
    const navDCR = document.getElementById("nav-dcr-console");
    const navJudge = document.getElementById("nav-judge-docket");
    const navUserAdmin = document.getElementById("nav-user-admin");
    const navWhatsApp = document.getElementById("nav-whatsapp");
    const btnNJC = document.getElementById("btn-njc-export");

    if (navCustody) navCustody.style.display = ["Sheriff", "Clerk", "Chief Registrar"].includes(role) ? "flex" : "none";
    if (navDCR) navDCR.style.display = (role === "DCR" || role === "Chief Registrar") ? "flex" : "none";
    if (navJudge) navJudge.style.display = (role === "Judge" || role === "Chief Registrar") ? "flex" : "none";
    if (navUserAdmin) navUserAdmin.style.display = (role === "Chief Registrar") ? "flex" : "none";
    if (navWhatsApp) navWhatsApp.style.display = (demoMode && role === "Chief Registrar") ? "flex" : "none";
    if (btnNJC) btnNJC.style.display = (role === "Chief Registrar" || role === "DCR") ? "inline-flex" : "none";
}

// Logger Utility
function logger(message) {
    console.log(`[CourtLog App] ${new Date().toLocaleTimeString()} - ${message}`);
}

// Switching Tabs (Single Page App Navigation)
function switchTab(tabId) {
    if (tabId === "tab-whatsapp" && (!demoMode || authenticatedUser?.role !== "Chief Registrar")) {
        tabId = "tab-overview";
    }
    if (tabId === "tab-qr-scan" && !["Sheriff", "Clerk", "Chief Registrar"].includes(authenticatedUser?.role)) {
        tabId = "tab-overview";
    }
    document.querySelectorAll("main > div > section").forEach(section => {
        section.classList.add("hidden");
    });

    const targetSection = document.getElementById(tabId);
    if (targetSection) targetSection.classList.remove("hidden");

    document.querySelectorAll(".sidebar nav button").forEach(btn => {
        btn.className = 'nav-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left font-medium';
    });

    const activeBtn = Array.from(document.querySelectorAll(".sidebar nav button")).find(btn => {
        return btn.getAttribute("onclick") && btn.getAttribute("onclick").includes(tabId);
    });

    if (activeBtn) {
        activeBtn.className = 'nav-item active w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left font-medium';
    }

    // Auto-load data for AI Risk tab on first visit
    if (tabId === 'tab-ai-risk' && typeof aiRiskData !== 'undefined' && aiRiskData.length === 0) {
        loadAIRiskData();
    }

    const viewTitles = {
        "tab-overview": "Registry Performance Hub",
        "tab-qr-scan": "Custody Check-In (Simulation)",
        "tab-courtrooms": "Clerk Call-Over Logger",
        "tab-dcr-console": "DCR Division Supervisor Hub",
        "tab-judge-docket": "My Assigned Judicial Docket",
        "tab-ai-risk": "AI Delay-Risk Intelligence",
        "tab-execution": "Post-Judgment Execution & Compliance",
        "tab-user-admin": "Judiciary User Administration",
        "tab-whatsapp": "WhatsApp Webhook Simulation Stream"
    };
    document.getElementById("view-title").textContent = viewTitles[tabId] || "Registry Hub";
}

// ----------------- API INGESTION & DATA BINDING -----------------

async function loadDashboardData() {
    try {
        const response = await apiFetch(`${API_BASE}/cases`, {
            headers: getAuthHeaders()
        });
        if (!response.ok) throw new Error("HTTP error loading cases");

        casesData = await response.json();
        logger(`Loaded ${casesData.length} cases.`);

        renderOverviewMetrics();
        renderHeatmapTable(casesData);
        renderDCRTable();
        renderJudgeDocketTable();
        populateDropdowns();
        renderExecutionTable();
        renderChart();
        if (demoMode && authenticatedUser?.role === "Chief Registrar") loadWhatsAppLogs();
    } catch (error) {
        logger(`Error loading dashboard: ${error}`);
    }
}

async function loadUsersData() {
    try {
        const response = await apiFetch(`${API_BASE}/users`, {
            headers: getAuthHeaders()
        });
        if (!response.ok) return;
        usersData = await response.json();
        renderUsersAdminTable();
    } catch (error) {
        logger(`Error loading users: ${error}`);
    }
}

async function loadWhatsAppLogs() {
    try {
        const response = await apiFetch(`${API_BASE}/whatsapp/logs`, {
            headers: getAuthHeaders()
        });
        if (!response.ok) throw new Error("HTTP error loading logs");

        whatsappLogs = await response.json();
        renderWhatsAppLogs();
    } catch (error) {
        logger(`Error loading WhatsApp logs: ${error}`);
    }
}

// ----------------- RENDERING & DOM INJECTION -----------------

function renderOverviewMetrics() {
    // 1. Calculations
    const total = casesData.length;
    const highRisk = casesData.filter(c => c.risk_flag).length;
    const custodyAlerts = casesData.filter(c => c.custody_alert).length;
    const enforcementAlerts = casesData.filter(c => c.enforcement_non_compliant).length;

    // 2. DOM updates
    document.getElementById("stat-total-cases").textContent = total;
    document.getElementById("stat-high-risk").textContent = highRisk;
    document.getElementById("stat-custody-alerts").textContent = custodyAlerts;
    document.getElementById("stat-enforcement-alerts").textContent = enforcementAlerts;

    document.getElementById("alert-count-custody").textContent = custodyAlerts;
    document.getElementById("alert-count-enforcement").textContent = enforcementAlerts;

    // Toggle overall warning hub visibility
    const alertHub = document.getElementById("quick-alert-bar");
    if (custodyAlerts > 0 || enforcementAlerts > 0) {
        alertHub.classList.remove("hidden");
    } else {
        alertHub.classList.add("hidden");
    }
}

function renderHeatmapTable(cases) {
    const tableBody = document.getElementById("cases-table-body");
    tableBody.innerHTML = "";

    if (cases.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" class="text-center py-8" style="color:var(--text-muted)">No matching cases found in directory.</td></tr>`;
        return;
    }

    cases.map(safeRecord).forEach(c => {
        // Find latest scan location
        let lastScanLocation = "N/A";
        let lastScanTime = "";
        if (c.scan_events && c.scan_events.length > 0) {
            const latest = c.scan_events[c.scan_events.length - 1];
            lastScanLocation = latest.location;
            lastScanTime = new Date(latest.timestamp).toLocaleDateString();
        }

        // LED dot color
        let ledClass = "led-green";
        if (c.risk_flag) {
            ledClass = "led-red";
        } else if (c.custody_alert || c.enforcement_non_compliant) {
            ledClass = "led-amber";
        }

        // Risk badge
        let riskBadgeClass = "badge badge-low";
        let riskScoreStyle = `color:var(--emerald)`;
        let riskLabel = "Low";
        if (c.risk_flag) {
            riskBadgeClass = "badge badge-high badge-pulse";
            riskScoreStyle = `color:var(--rose); font-weight:700`;
            riskLabel = "High";
        } else if (c.delay_risk_score >= 0.40) {
            riskBadgeClass = "badge badge-mod";
            riskScoreStyle = `color:var(--amber)`;
            riskLabel = "Mod";
        }

        // Registry Alert Badge
        let alertBadge = `<span style="color:var(--text-muted); font-weight:600">-</span>`;
        if (c.custody_alert) {
            alertBadge = `<span class="badge badge-high"><i class="fa-solid fa-triangle-exclamation mr-1"></i> Registry Idle</span>`;
        } else if (c.enforcement_non_compliant) {
            alertBadge = `<span class="badge badge-mod"><i class="fa-solid fa-scale-unbalanced mr-1"></i> Sheriff Overdue</span>`;
        } else if (c.judgment_status === "Executed") {
            alertBadge = `<span class="badge badge-low">Enforced</span>`;
        }

        const activeUser = getActiveUser();
        const canRecordCustody = ["Sheriff", "Clerk", "Chief Registrar"].includes(activeUser.role);
        const canAssignSheriff = ["Clerk", "Chief Registrar"].includes(activeUser.role);
        const canHandoverCustody = activeUser.role === "Sheriff" && c.assigned_sheriff_id === activeUser.user_id;
        const row = document.createElement("tr");
        row.innerHTML = `
            <td class="py-3 px-4 font-mono font-bold text-heading tracking-wider"><span class="led-dot ${ledClass}"></span>${c.case_id}</td>
            <td class="py-3 px-4" style="color:var(--text-secondary)">${c.case_type}</td>
            <td class="py-3 px-4">
                <div class="font-medium text-heading">${c.court}</div>
                <div class="text-[10px] flex items-center gap-1 mt-0.5" style="color:var(--text-muted)">
                    <i class="fa-solid fa-location-dot text-accent"></i> ${lastScanLocation} (${lastScanTime})
                </div>
            </td>
            <td class="py-3 px-4 text-center font-bold text-heading">${c.adjournment_count}</td>
            <td class="py-3 px-4 text-center font-mono font-semibold">${c.days_since_filing} days</td>
            <td class="py-3 px-4 text-center">
                <div class="flex items-center justify-center gap-2">
                    <span class="text-xs" style="${riskScoreStyle}">${(c.delay_risk_score * 100).toFixed(0)}%</span>
                    <span class="${riskBadgeClass}">
                        ${riskLabel}
                    </span>
                </div>
            </td>
            <td class="py-3 px-4 text-center">${alertBadge}</td>
            <td class="py-3 px-4 text-right">
                <div class="flex items-center justify-end gap-2">
                    ${canRecordCustody ? `<button data-case-action="scan" data-record-id="${c.case_id}" class="btn-secondary" style="padding:2px 8px;font-size:10px;" title="Record a custody check-in"><i class="fa-solid fa-location-dot mr-1"></i> Check-In</button>` : ''}
                    ${activeUser.role !== 'Sheriff' ? `<button data-case-action="hearing" data-record-id="${c.case_id}" class="btn-secondary" style="padding:2px 8px;font-size:10px;" title="Log Hearing"><i class="fa-solid fa-gavel mr-1"></i> Log</button>` : ''}
                    ${canAssignSheriff ? `<button data-case-action="assignSheriff" data-record-id="${c.case_id}" class="btn-secondary" style="padding:2px 8px;font-size:10px; color:var(--accent)" title="Assign or reassign Sheriff custody"><i class="fa-solid fa-person-walking-arrow-right mr-1"></i> Custody</button>` : ''}
                    ${canHandoverCustody ? `<button data-case-action="handover" data-record-id="${c.case_id}" class="btn-secondary" style="padding:2px 8px;font-size:10px; color:var(--amber)" title="Hand over file custody"><i class="fa-solid fa-right-left mr-1"></i> Hand Over</button>` : ''}
                    ${activeUser.role === 'Chief Registrar' ? `<button data-case-action="assign" data-record-id="${c.case_id}" class="btn-secondary" style="padding:2px 8px;font-size:10px; color:var(--purple-400)" title="Assign Judge"><i class="fa-solid fa-scale-balanced mr-1"></i> Assign</button>` : ''}
                </div>
            </td>
        `;
        tableBody.appendChild(row);
    });
}

function renderExecutionTable() {
    const tableBody = document.getElementById("judgments-table-body");
    if (!tableBody) return;
    tableBody.innerHTML = "";

    try {
        const judgments = casesData.filter(c => c.judgment_status === "Delivered" || c.judgment_status === "Judgment Delivered");

        if (judgments.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="6" class="text-center py-8" style="color:var(--text-muted)">No judgments awaiting enforcement compliance.</td></tr>`;
            return;
        }

        judgments.map(safeRecord).forEach(c => {
            // Calculate dynamic delivery date
            let deliveryDate = "N/A";
            const deliveryEvent = (c.execution_log || []).find(e => e.action && e.action.includes("Delivered"));
            if (deliveryEvent) {
                deliveryDate = new Date(deliveryEvent.date).toLocaleDateString();
            } else if (c.filing_date) {
                deliveryDate = new Date(c.filing_date).toLocaleDateString();
            }

            let statusBadge = `<span class="badge badge-low font-semibold">Compliant</span>`;
            if (c.enforcement_non_compliant) {
                statusBadge = `<span class="badge badge-high badge-pulse font-bold"><i class="fa-solid fa-clock mr-1"></i> Overdue (90d+)</span>`;
            }

            const enforceActions = (c.execution_log || []).filter(e => e.action && !e.action.includes("Delivered"));
            const latestEnforceAction = enforceActions.length > 0 ? enforceActions[enforceActions.length - 1].action : "No Writ Lodged";

            const row = document.createElement("tr");
            row.innerHTML = `
                <td class="py-3 px-3 font-mono font-bold text-heading">${c.case_id || 'N/A'}</td>
                <td class="py-3 px-3" style="color:var(--text-muted)">${c.case_type || 'N/A'}</td>
                <td class="py-3 px-3">${deliveryDate}</td>
                <td class="py-3 px-3 text-center font-mono font-bold text-heading">${c.days_since_filing || 0} days</td>
                <td class="py-3 px-3 text-center">
                    <div class="space-y-1">
                        <div>${statusBadge}</div>
                        <div class="text-[9px] font-mono" style="color:var(--text-muted)">${latestEnforceAction}</div>
                    </div>
                </td>
                <td class="py-3 px-3 text-right">
                    <button data-case-action="writ" data-record-id="${c.case_id}" class="btn-primary" style="font-size:10px; padding:4px 12px;">
                        Compile Writ
                    </button>
                </td>
            `;
            tableBody.appendChild(row);
        });
    } catch (error) {
        console.error("Error in renderExecutionTable:", error);
        tableBody.innerHTML = `<tr><td colspan="6" class="text-center py-8" style="color:red">Error: ${escapeHTML(error.message)}</td></tr>`;
    }
}

function renderWhatsAppLogs() {
    const container = document.getElementById("whatsapp-logs-container");
    if (!container) return;

    if (whatsappLogs.length === 0) {
        return; // keeps placeholder
    }

    container.innerHTML = "";
    whatsappLogs.map(safeRecord).forEach(log => {
        const payload = log.payload;
        const msgText = payload.simulated_text || "N/A";
        const dateFormatted = new Date(log.received_at).toLocaleTimeString();

        const card = document.createElement("div");
        card.className = "glass-panel rounded-xl p-4 space-y-3";
        card.innerHTML = `
            <div class="flex items-center justify-between text-xs pb-2" style="border-bottom:1px solid var(--border-color)">
                <span class="font-mono font-semibold text-accent"><i class="fa-brands fa-whatsapp text-emerald-th mr-1.5"></i> TO: ${payload.to}</span>
                <span class="font-medium" style="color:var(--text-muted)">${dateFormatted}</span>
            </div>
            
            <div class="rounded-lg p-2.5 text-xs leading-relaxed font-sans" style="background:var(--bg-body); border-left:2px solid var(--emerald); color:var(--text-secondary)">
                ${msgText}
            </div>
            
            <details class="text-[10px] font-mono" style="color:var(--text-muted)">
                <summary class="cursor-pointer hover:underline" style="color:var(--text-secondary)">View Raw API POST JSON Payload</summary>
                <pre class="mt-2 p-3 rounded-lg overflow-x-auto text-[9px]" style="background:var(--bg-body); border:1px solid var(--border-color); color:var(--emerald)">${JSON.stringify(payload, null, 2)}</pre>
            </details>
        `;
        container.appendChild(card);
    });
}

function populateDropdowns() {
    const scanSelect = document.getElementById("scan-case-id");
    const hearingSelect = document.getElementById("hearing-case-id");
    const missingSelect = document.getElementById("missing-case-id");

    if (!scanSelect || !hearingSelect) return;

    // Save current values to restore them after re-populating
    const prevScanVal = scanSelect.value;
    const prevHearingVal = hearingSelect.value;
    const prevMissingVal = missingSelect ? missingSelect.value : "";

    scanSelect.innerHTML = "";
    hearingSelect.innerHTML = "";
    if (missingSelect) missingSelect.innerHTML = "";

    // Sort cases by case_id for readability
    const sortedCases = [...casesData].sort((a, b) => a.case_id.localeCompare(b.case_id));

    sortedCases.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.case_id;
        opt.textContent = `${c.case_id} [${c.case_type} - ${c.court}]`;

        scanSelect.appendChild(opt.cloneNode(true));
        if (missingSelect) missingSelect.appendChild(opt.cloneNode(true));
        // Clerks can only log hearings for Pending cases or Delivered (to enforce)
        if (c.judgment_status !== "Executed") {
            hearingSelect.appendChild(opt.cloneNode(true));
        }
    });

    // Restore selection if valid, else pick first
    if (prevScanVal && sortedCases.some(c => c.case_id === prevScanVal)) {
        scanSelect.value = prevScanVal;
    }
    if (prevHearingVal && sortedCases.some(c => c.case_id === prevHearingVal && c.judgment_status !== "Executed")) {
        hearingSelect.value = prevHearingVal;
    }
    if (missingSelect && prevMissingVal && sortedCases.some(c => c.case_id === prevMissingVal)) {
        missingSelect.value = prevMissingVal;
    }

    // Update scanner / logger previews
    updateQRDisplay();
    updateHearingLogDetails();
}

// ----------------- CHARTS & ANALYTICS -----------------

function renderChart() {
    const ctx = document.getElementById("chart-delay-distribution");
    if (!ctx) return;

    const isDark = getTheme() === 'dark';

    // Aggregate data: average delay risk score per Case Type
    const categories = ["Criminal", "Civil", "Commercial", "Land/Property", "Family/Probate", "Constitutional/Fundamental Rights", "Election Petition", "Admiralty"];
    const riskAverages = categories.map(cat => {
        const catCases = casesData.filter(c => c.case_type === cat);
        if (catCases.length === 0) return 0;
        const totalRisk = catCases.reduce((sum, c) => sum + c.delay_risk_score, 0);
        return Math.round((totalRisk / catCases.length) * 100);
    });

    if (distributionChart) {
        distributionChart.data.datasets[0].data = riskAverages;
        distributionChart.update();
        return;
    }

    // Theme-aware colors
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.06)';
    const tickColor = isDark ? '#A3A3A3' : '#6B7280';

    distributionChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: categories,
            datasets: [{
                label: 'Avg Delay-Risk Probability (%)',
                data: riskAverages,
                backgroundColor: [
                    'rgba(16, 185, 129, 0.5)',   // Criminal - green
                    'rgba(245, 158, 11, 0.5)',   // Civil - amber
                    'rgba(59, 130, 246, 0.5)',   // Commercial - blue
                    'rgba(244, 63, 94, 0.5)',    // Land/Property - rose
                    'rgba(16, 185, 129, 0.3)',   // Family/Probate - green light
                    'rgba(168, 85, 247, 0.5)',   // Constitutional - purple
                    'rgba(244, 63, 94, 0.35)',   // Election Petition - rose light
                    'rgba(107, 114, 128, 0.4)'   // Admiralty - grey
                ],
                borderColor: [
                    '#10B981',
                    '#F59E0B',
                    '#3B82F6',
                    '#F43F5E',
                    '#10B981',
                    '#A855F7',
                    '#F43F5E',
                    '#6B7280'
                ],
                borderWidth: 2,
                borderRadius: 8,
                barPercentage: 0.6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return `Average Risk: ${context.raw}%`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: {
                        color: gridColor
                    },
                    ticks: {
                        color: tickColor,
                        font: {
                            family: 'Outfit'
                        }
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: tickColor,
                        font: {
                            family: 'Outfit',
                            size: 11
                        }
                    }
                }
            }
        }
    });
}

// ----------------- USER SUBMIT HANDLERS & RBAC ENFORCEMENT -----------------

async function handleCreateCase(e) {
    e.preventDefault();
    const case_id = document.getElementById("new-case-id").value.trim();
    const case_type = document.getElementById("new-case-type").value;
    const court = document.getElementById("new-case-court").value;
    const counsel_phone = document.getElementById("new-case-counsel").value.trim();
    const litigant_phone = document.getElementById("new-case-litigant").value.trim();

    if (!case_id) return;

    logger(`Creating case ${case_id}...`);

    try {
        const response = await apiFetch(`${API_BASE}/cases`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ case_id, case_type, court, counsel_phone, litigant_phone })
        });

        if (!response.ok) {
            const err = await response.json();
            alert(`Permission Denied / Case Failed: ${err.detail || "Server error"}`);
            return;
        }

        document.getElementById("form-create-case").reset();
        await loadDashboardData();
        alert(`Case file ${case_id} cataloged and initialized successfully!`);
    } catch (error) {
        logger(`Error creating case: ${error}`);
    }
}

async function handleScanSubmit(e) {
    e.preventDefault();
    const case_id = document.getElementById("scan-case-id").value;
    const location = document.getElementById("scan-location").value;

    if (!case_id) {
        showToast("Please select a case file.", "error");
        return;
    }

    logger(`Submitting custody check-in for case ${case_id} at ${location}`);

    try {
        const response = await apiFetch(`${API_BASE}/scan`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ case_id, location })
        });

        if (!response.ok) {
            const err = await response.json();
            showToast(err.detail || "Custody check-in failed.", "error");
            return;
        }

        await loadDashboardData();
        updateQRDisplay();

        const scanBtn = document.querySelector("#form-qr-scan button[type='submit']");
        const origText = scanBtn.innerHTML;
        scanBtn.innerHTML = `<i class="fa-solid fa-circle-check"></i> Scan Success!`;
        scanBtn.style.background = '#059669';
        setTimeout(() => {
            scanBtn.innerHTML = origText;
            scanBtn.style.background = '';
        }, 1500);

    } catch (error) {
        logger(`Scan submission error: ${error}`);
    }
}

async function handleHearingSubmit(e) {
    e.preventDefault();
    const case_id = document.getElementById("hearing-case-id").value;
    const outcome = currentHearingOutcome;
    const next_date_val = outcome === "Adjourned"
        ? document.getElementById("hearing-next-date").value
        : document.getElementById("hearing-heard-next-date").value;

    const reason_code = outcome === "Adjourned"
        ? document.getElementById("hearing-reason").value
        : document.getElementById("heard-reason").value;

    if (!case_id) return;
    if (outcome === "Adjourned" && !next_date_val) {
        alert("Please select the next hearing calendar date for adjournment.");
        return;
    }

    let next_date = "";
    if (next_date_val) {
        next_date = new Date(next_date_val).toISOString();
    } else {
        next_date = new Date().toISOString();
    }

    logger(`Submitting hearing outcome for case ${case_id}: ${outcome}`);

    try {
        const response = await apiFetch(`${API_BASE}/cases/${case_id}/hearings`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ outcome, reason_code, next_date })
        });

        if (!response.ok) {
            const err = await response.json();
            alert(`🚨 5TH ADJOURNMENT HARD BLOCKED BY SYSTEM:\n${err.detail || "Hearing logging failed."}\n\nCase has been auto-escalated to the DCR Approval Queue.`);
            await loadDashboardData();
            return;
        }

        await loadDashboardData();
        alert(`Hearing outcome logged successfully! WhatsApp simulation payload sent for case ${case_id}.`);
    } catch (error) {
        logger(`Hearing logging error: ${error}`);
    }
}

// ----------------- DCR APPROVAL QUEUE & OVERRIDES -----------------

function renderDCRTable() {
    const tableBody = document.getElementById("dcr-approval-table-body");
    if (!tableBody) return;
    tableBody.innerHTML = "";

    const dcrCases = casesData.filter(c => c.dcr_approval_required || c.adjournment_count >= 4);

    if (dcrCases.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="6" class="text-center py-8" style="color:var(--text-muted)">No cases currently pending DCR 5th adjournment exception review.</td></tr>`;
        return;
    }

    dcrCases.map(safeRecord).forEach(c => {
        const isBlocked = c.dcr_approval_required || (c.adjournment_count >= 4 && !c.dcr_override_reason);
        let statusBadge = isBlocked
            ? `<span class="badge badge-high badge-pulse font-bold"><i class="fa-solid fa-ban mr-1"></i> 5th Adj. Blocked</span>`
            : `<span class="badge badge-low font-semibold"><i class="fa-solid fa-circle-check mr-1"></i> DCR Approved</span>`;

        let actionBtn = isBlocked
            ? `<button data-case-action="override" data-record-id="${c.case_id}" class="btn-primary bg-amber-600 hover:bg-amber-700 text-xs py-1 px-3"><i class="fa-solid fa-shield-halved mr-1"></i> Review & Approve</button>`
            : `<span class="text-xs text-emerald-400 font-mono"><i class="fa-solid fa-lock-open"></i> Unblocked</span>`;

        const row = document.createElement("tr");
        row.innerHTML = `
            <td class="py-3 px-4 font-mono font-bold text-heading">${c.case_id}</td>
            <td class="py-3 px-4">${c.case_type} (${c.assigned_division || 'Criminal'})</td>
            <td class="py-3 px-4">${c.court}</td>
            <td class="py-3 px-4 text-center font-bold text-rose">${c.adjournment_count} / 4</td>
            <td class="py-3 px-4 text-center">${statusBadge}</td>
            <td class="py-3 px-4 text-right">${actionBtn}</td>
        `;
        tableBody.appendChild(row);
    });
}

function openDCROverrideModal(caseId) {
    activeOverrideCaseId = caseId;
    document.getElementById("override-modal-case-id").textContent = caseId;
    animateOpenModal("dcr-override-modal");
}

function closeDCROverrideModal() {
    animateCloseModal("dcr-override-modal");
    activeOverrideCaseId = null;
}

async function submitDCROverride() {
    if (!activeOverrideCaseId) return;
    const reason = document.getElementById("dcr-override-reason-input").value.trim();
    if (!reason) {
        alert("Please enter the DCR exceptional approval reason.");
        return;
    }

    try {
        const response = await apiFetch(`${API_BASE}/cases/${activeOverrideCaseId}/dcr-override`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ exceptional_reason: reason })
        });

        if (!response.ok) {
            const err = await response.json();
            alert(`Failed DCR override: ${err.detail || 'Permission denied'}`);
            return;
        }

        closeDCROverrideModal();
        await loadDashboardData();
        alert(`Case ${activeOverrideCaseId} successfully approved and unblocked by Deputy Chief Registrar!`);
    } catch (error) {
        logger(`DCR Override error: ${error}`);
    }
}

// ----------------- JUDGE DOCKET CONSOLE -----------------

function renderJudgeDocketTable() {
    const tableBody = document.getElementById("judge-docket-table-body");
    if (!tableBody) return;
    tableBody.innerHTML = "";

    const user = getActiveUser();
    const judgeCases = casesData.filter(c => user.role === "Chief Registrar" || c.assigned_judge_id === user.user_id);

    const alertCountElem = document.getElementById("judge-alert-count");
    if (alertCountElem) alertCountElem.textContent = judgeCases.filter(c => c.risk_flag || c.adjournment_count >= 4).length;

    if (judgeCases.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="6" class="text-center py-8" style="color:var(--text-muted)">No active cases assigned to your judicial docket.</td></tr>`;
        return;
    }

    judgeCases.map(safeRecord).forEach(c => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td class="py-3 px-4 font-mono font-bold text-heading">${c.case_id}</td>
            <td class="py-3 px-4">${c.case_type}</td>
            <td class="py-3 px-4 text-center font-bold text-heading">${c.adjournment_count}</td>
            <td class="py-3 px-4 text-center font-mono">${c.days_since_filing} d</td>
            <td class="py-3 px-4 text-center"><span class="badge ${c.risk_flag ? 'badge-high' : 'badge-low'}">${(c.delay_risk_score * 100).toFixed(0)}%</span></td>
            <td class="py-3 px-4 text-right">
                <button data-case-action="ruling" data-record-id="${c.case_id}" class="btn-primary text-xs py-1 px-3"><i class="fa-solid fa-gavel mr-1"></i> Deliver Ruling</button>
            </td>
        `;
        tableBody.appendChild(row);
    });
}

async function logJudicialRuling(caseId) {
    if (!confirm(`Deliver final judgment / ruling for case ${caseId}? This will stop the case delay timer.`)) return;

    try {
        const response = await apiFetch(`${API_BASE}/cases/${caseId}/hearings`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({
                outcome: "Heard",
                reason_code: "Judgment Delivered",
                next_date: new Date().toISOString()
            })
        });

        if (!response.ok) {
            const err = await response.json();
            alert(`Error delivering ruling: ${err.detail || 'Permission denied'}`);
            return;
        }

        await loadDashboardData();
        alert(`Judgment delivered for ${caseId}. Case timer successfully closed!`);
    } catch (error) {
        logger(`Error logging ruling: ${error}`);
    }
}

// ----------------- USER ADMIN CONSOLE -----------------

function renderUsersAdminTable() {
    const tableBody = document.getElementById("users-admin-table-body");
    if (!tableBody) return;
    tableBody.innerHTML = "";

    if (usersData.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="7" class="text-center py-8" style="color:var(--text-muted)">No active user profiles loaded.</td></tr>`;
        return;
    }

    usersData.map(safeRecord).forEach(u => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td class="py-3 px-4 font-mono text-heading">${u.user_id}</td>
            <td class="py-3 px-4 font-mono">${u.username || "—"}</td>
            <td class="py-3 px-4 font-bold text-heading">${u.name}</td>
            <td class="py-3 px-4"><span class="badge badge-low">${u.role}</span></td>
            <td class="py-3 px-4" style="color:var(--text-secondary)">${u.badge}</td>
            <td class="py-3 px-4">${u.division || 'All'}</td>
            <td class="py-3 px-4 text-right whitespace-nowrap">
                ${u.user_id !== currentUserId ? `<button data-case-action="resetPassword" data-record-id="${u.user_id}" title="Issue temporary password" class="btn-secondary text-xs py-1 px-2.5"><i class="fa-solid fa-key"></i></button>` : ""}
                <button data-case-action="deleteUser" data-record-id="${u.user_id}" class="btn-secondary text-xs text-rose hover:bg-rose-900/20 py-1 px-2.5"><i class="fa-solid fa-trash"></i></button>
            </td>
        `;
        tableBody.appendChild(row);
    });
}

function openAddUserModal() {
    const overlay = document.getElementById("add-user-overlay");
    if (overlay) overlay.classList.remove("hidden");
    document.getElementById("new-user-name")?.focus();
}

function closeAddUserModal() {
    document.getElementById("add-user-overlay")?.classList.add("hidden");
    document.getElementById("add-user-error")?.classList.add("hidden");
}

async function submitAddUserForm(event) {
    event.preventDefault();
    const userData = {
        name: document.getElementById("new-user-name").value.trim(),
        username: document.getElementById("new-user-username").value.trim(),
        initial_password: document.getElementById("new-user-password").value,
        role: document.getElementById("new-user-role").value,
        badge: document.getElementById("new-user-badge").value.trim(),
        court: document.getElementById("new-user-court").value.trim(),
        division: document.getElementById("new-user-division").value.trim()
    };
    const button = document.getElementById("btn-add-user-submit");
    button.disabled = true;
    try {
        const response = await apiFetch(`${API_BASE}/users`, {
            method: "POST", headers: getAuthHeaders(), body: JSON.stringify(userData)
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            const error = document.getElementById("add-user-error");
            error.textContent = result.detail || "Account creation failed.";
            error.classList.remove("hidden");
            return;
        }
        document.getElementById("form-add-user").reset();
        closeAddUserModal();
        await loadUsersData();
        showToast(`Account ${result.username} created. Deliver the temporary password securely; a change is required at first sign-in.`, "success");
    } catch (error) {
        const errorEl = document.getElementById("add-user-error");
        errorEl.textContent = "Connection error while creating account.";
        errorEl.classList.remove("hidden");
        logger(`Error adding user: ${error}`);
    } finally {
        button.disabled = false;
    }
}

async function resetUserPassword(userId) {
    const temporaryPassword = prompt("Set a one-time temporary password (12–72 characters). Deliver it through an approved channel:");
    if (!temporaryPassword) return;
    if (temporaryPassword.length < 12 || new TextEncoder().encode(temporaryPassword).length > 72) {
        alert("Temporary password must be 12–72 UTF-8 bytes.");
        return;
    }
    if (!confirm(`Reset the password for ${userId} and revoke their current sessions?`)) return;
    try {
        const response = await apiFetch(`${API_BASE}/users/${userId}/reset-password`, {
            method: "POST", headers: getAuthHeaders(),
            body: JSON.stringify({ temporary_password: temporaryPassword })
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            alert(`Password reset failed: ${result.detail || "Permission denied"}`);
            return;
        }
        showToast(`Temporary credential set for ${userId}. The user must change it at next sign-in.`, "success");
    } catch (error) {
        logger(`Error resetting password: ${error}`);
    }
}

async function deleteUserAccount(userId) {
    if (!confirm(`Delete user account ${userId}?`)) return;
    try {
        const response = await apiFetch(`${API_BASE}/users/${userId}`, {
            method: "DELETE",
            headers: getAuthHeaders()
        });
        if (!response.ok) {
            const err = await response.json();
            alert(`Failed deleting user: ${err.detail || 'Permission denied'}`);
            return;
        }
        await loadUsersData();
    } catch (error) {
        logger(`Error deleting user: ${error}`);
    }
}

// ----------------- 1-CLICK NJC COMPLIANCE EXPORT -----------------

async function exportNJCReport() {
    try {
        const response = await apiFetch(`${API_BASE}/export/njc`, {
            headers: getAuthHeaders()
        });

        if (!response.ok) {
            const err = await response.json();
            alert(`NJC Export Failed: ${err.detail || 'Permission denied'}`);
            return;
        }

        const report = await response.json();
        document.getElementById("njc-report-json-view").textContent = JSON.stringify(report, null, 2);
        animateOpenModal("njc-modal");
    } catch (error) {
        logger(`NJC export error: ${error}`);
    }
}

function closeNJCModal() {
    animateCloseModal("njc-modal");
}

function downloadNJCFile() {
    const text = document.getElementById("njc-report-json-view").textContent;
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `NJC_Monthly_Delay_Compliance_Report_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

// ----------------- SIDEBAR & UTILITIES -----------------

// Shortcut buttons on overview table
function shortcutQRScan(caseId) {
    switchTab("tab-qr-scan");
    document.getElementById("scan-case-id").value = caseId;
    updateQRDisplay();
}

function shortcutHearingLog(caseId) {
    switchTab("tab-courtrooms");
    document.getElementById("hearing-case-id").value = caseId;
    updateHearingLogDetails();
}

// Local custody-history preview. QR generation/capture is not implemented yet.
function updateQRDisplay() {
    const caseId = document.getElementById("scan-case-id").value;
    if (!caseId) return;

    document.getElementById("qr-display-suit").textContent = caseId;

    // Bind chain of custody logs to preview
    const targetCase = casesData.find(c => c.case_id === caseId);
    const logsContainer = document.getElementById("case-scan-history");
    logsContainer.innerHTML = "";

    if (targetCase && targetCase.scan_events && targetCase.scan_events.length > 0) {
        [...targetCase.scan_events].reverse().map(safeRecord).forEach(scan => {
            const dt = new Date(scan.timestamp).toLocaleDateString() + " " + new Date(scan.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const item = document.createElement("div");
            item.className = "flex justify-between items-center text-[10px] py-1";
            item.style.borderBottom = '1px solid var(--border-color)';
            item.innerHTML = `
                <span><i class="fa-solid fa-location-arrow text-accent mr-1"></i> ${scan.location}</span>
                <span style="color:var(--text-muted)" class="font-mono">${dt} (recorded actor: ${scan.staff_id})</span>
            `;
            logsContainer.appendChild(item);
        });
    } else {
        logsContainer.innerHTML = `<div class="text-center py-4" style="color:var(--text-muted)">No scan checkpoint logs recorded.</div>`;
    }
}

// Interactive Call-Over Logging outcome selectors
function selectOutcome(outcome) {
    currentHearingOutcome = outcome;
    const btnHeard = document.getElementById("outcome-heard");
    const btnAdjourned = document.getElementById("outcome-adjourned");
    const adjournedPanel = document.getElementById("adjournment-panel");
    const heardPanel = document.getElementById("heard-panel");

    if (outcome === "Adjourned") {
        btnAdjourned.className = "outcome-btn selected";
        btnHeard.className = "outcome-btn";
        adjournedPanel.classList.remove("hidden");
        heardPanel.classList.add("hidden");
    } else {
        btnHeard.className = "outcome-btn selected";
        btnAdjourned.className = "outcome-btn";
        adjournedPanel.classList.add("hidden");
        heardPanel.classList.remove("hidden");
    }
    updateHearingLogDetails();
}

function updateHearingLogDetails() {
    const caseId = document.getElementById("hearing-case-id").value;
    if (!caseId) return;

    const outcome = currentHearingOutcome;
    let nextDateVal = "";
    let reason = "";

    if (outcome === "Adjourned") {
        nextDateVal = document.getElementById("hearing-next-date").value;
        reason = document.getElementById("hearing-reason").value;
    } else {
        nextDateVal = document.getElementById("hearing-heard-next-date").value;
        reason = document.getElementById("heard-reason").value;
    }

    // Inject previews
    document.getElementById("preview-suit-id").textContent = caseId;
    document.getElementById("preview-next-date").textContent = nextDateVal || "[next-date]";
    document.getElementById("preview-reason").textContent = reason;
}

// Attach change listeners to live preview blocks
document.getElementById("hearing-reason").addEventListener("change", updateHearingLogDetails);
document.getElementById("hearing-next-date").addEventListener("input", updateHearingLogDetails);
document.getElementById("heard-reason").addEventListener("change", updateHearingLogDetails);
document.getElementById("hearing-heard-next-date").addEventListener("input", updateHearingLogDetails);

// ----------------- ENFORCEMENT & WRITS ENGINE -----------------

function selectCaseForWrit(caseId) {
    selectedWritCaseId = caseId;
    const input = document.getElementById("writ-case-id");
    const btn = document.getElementById("btn-generate-writ");

    input.value = caseId;
    input.style.opacity = '1';

    // Enable button
    btn.disabled = false;
    btn.className = 'btn-primary w-full';
    btn.style.opacity = '1';
    btn.style.cursor = 'pointer';
}

async function generateWritForm() {
    const caseId = selectedWritCaseId;
    if (!caseId) return;

    const writType = document.getElementById("writ-type").value;
    const sheriffId = document.getElementById("writ-sheriff-id").value.trim();
    const extraDetails = document.getElementById("writ-extra-details").value.trim();

    if (!sheriffId) {
        alert("Please enter sheriff staff identifier ID.");
        return;
    }

    logger(`Generating writ ${writType} for case ${caseId}`);

    // Call enforcement endpoint to register execution action
    try {
        const action = `${writType} Issued for ${extraDetails}`;
        const response = await apiFetch(`${API_BASE}/cases/${caseId}/execution`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ action, sheriff_id: sheriffId })
        });

        if (!response.ok) throw new Error("Execution check-in failed");

        await loadDashboardData();

        // Show PDF writ compilation Modal
        showWritModal(caseId, writType, extraDetails, sheriffId);

    } catch (error) {
        logger(`Execution registry error: ${error}`);
    }
}


// ===== WRIT GENERATION — FORM 27 (Sheriffs and Civil Process Act, Cap. S6, LFN 2004) =====

function showWritModal(caseId, writType, extraDetails, sheriffId) {
    const targetCase = casesData.find(c => c.case_id === caseId);
    if (!targetCase) return;
    const modal = document.getElementById("writ-modal");
    const title = document.getElementById("modal-writ-title");
    const content = document.getElementById("modal-writ-content");
    title.textContent = writType;

    let plaintiff = "……………………………………";
    let defendant = "……………………………………";
    if (targetCase.case_title) {
        const parts = targetCase.case_title.split(/\s+v\.?\s+|\s+vs\.?\s+/i);
        if (parts.length === 2) { plaintiff = parts[0].trim().toUpperCase(); defendant = parts[1].trim().toUpperCase(); }
        else { plaintiff = targetCase.case_title.toUpperCase(); }
    }

    const now = new Date();
    const dayNum = now.getDate();
    const monthName = now.toLocaleDateString('en-GB', { month: 'long' });
    const year = now.getFullYear();
    const dateStr = dayNum + ' ' + monthName + ', ' + year;
    const sfx = (dayNum >= 11 && dayNum <= 13) ? 'th' : [null,'st','nd','rd'][dayNum%10] || 'th';

    caseId = escapeHTML(caseId);
    plaintiff = escapeHTML(plaintiff);
    defendant = escapeHTML(defendant);
    extraDetails = escapeHTML(extraDetails.toUpperCase());
    sheriffId = escapeHTML(sheriffId);
    let docHTML = "";

    if (writType === "Writ of Fi Fa") {
        docHTML = '<div style="text-align:center;font-weight:bold;font-size:15px;margin-bottom:4px;">FORM 27</div>'
        + '<div style="text-align:center;font-style:italic;font-size:10px;margin-bottom:20px;">(Order VII Rule 1 — Sheriffs and Civil Process Act, Cap. S6, LFN 2004)</div>'
        + '<div style="text-align:center;font-weight:bold;font-size:13px;text-transform:uppercase;margin-bottom:4px;">IN THE HIGH COURT OF THE FEDERAL CAPITAL TERRITORY<br>STATE OF NIGERIA</div>'
        + '<div style="text-align:center;font-weight:bold;font-size:12px;text-transform:uppercase;margin-bottom:4px;">IN THE ABUJA JUDICIAL DIVISION</div>'
        + '<div style="text-align:center;font-weight:bold;font-size:12px;text-transform:uppercase;margin-bottom:16px;">HOLDEN AT ABUJA</div>'
        + '<div style="margin-bottom:16px;"><strong>SUIT NO:</strong> ' + caseId + '</div>'
        + '<div style="margin-bottom:4px;"><strong>BETWEEN</strong></div>'
        + '<div style="padding-left:24px;font-weight:bold;margin-bottom:4px;">' + plaintiff + '</div>'
        + '<div style="padding-left:48px;margin-bottom:12px;"><strong>JUDGMENT CREDITOR</strong></div>'
        + '<div style="text-align:center;margin-bottom:12px;"><strong>AND</strong></div>'
        + '<div style="padding-left:24px;font-weight:bold;margin-bottom:4px;">' + defendant + '</div>'
        + '<div style="padding-left:48px;margin-bottom:20px;"><strong>JUDGMENT DEBTOR</strong></div>'
        + '<hr style="border:none;border-top:2px solid black;margin-bottom:20px;">'
        + '<div style="text-align:center;font-weight:bold;font-size:14px;text-transform:uppercase;margin-bottom:4px;">WRIT OF FIERI FACIAS</div>'
        + '<div style="text-align:center;font-weight:bold;font-size:11px;text-transform:uppercase;margin-bottom:16px;">(WRIT OF FI. FA. AGAINST GOODS AND CHATTELS)</div>'
        + '<div style="text-align:center;font-weight:bold;margin-bottom:16px;">COMMONWEALTH OF NIGERIA<br>FEDERAL CAPITAL TERRITORY</div>'
        + '<p style="margin-bottom:12px;text-align:justify;"><strong>TO THE SHERIFF/DEPUTY SHERIFF OF THE HIGH COURT OF THE FEDERAL CAPITAL TERRITORY, OR TO ANY AUTHORISED BAILIFF OF THE COURT:</strong></p>'
        + '<p style="margin-bottom:12px;text-align:justify;">WHEREAS on the ' + dayNum + sfx + ' day of ' + monthName + ', ' + year + ', in an action in the High Court of the Federal Capital Territory, in the Abuja Judicial Division, between <strong>' + plaintiff + '</strong> (Judgment Creditor) and <strong>' + defendant + '</strong> (Judgment Debtor), it was adjudged that the said Judgment Creditor do recover against the said Judgment Debtor the sum awarded together with costs of this action;</p>'
        + '<p style="margin-bottom:12px;text-align:justify;">AND WHEREAS it appears by an affidavit filed herein that the said Judgment Debtor has not paid the said sum or any part thereof, and that there remains due and owing to the Judgment Creditor the full judgment amount together with interest thereon at the prescribed rate until payment;</p>'
        + '<p style="margin-bottom:12px;text-align:justify;">NOW THIS IS TO COMMAND YOU that of the goods, chattels and other property of the said Judgment Debtor, <strong>' + defendant + '</strong>, within your jurisdiction, you cause to be made the amount so remaining due, together with interest as aforesaid and your lawful fees, levies and expenses for the execution of this Writ;</p>'
        + '<p style="margin-bottom:12px;text-align:justify;">AND THAT YOU DO PAY the sum so made, less your lawful fees and expenses, to the said Judgment Creditor or to the Registrar of this Honourable Court, and that you do forthwith, and in any event not later than 30 days from the date of execution, make a return to this Court endorsed on or annexed to this Writ, showing in what manner you have executed the same;</p>'
        + '<p style="margin-bottom:20px;text-align:justify;"><strong>AND FOR SO DOING this shall be your sufficient Warrant and Authority.</strong></p>'
        + '<p style="margin-bottom:24px;">DATED at Abuja this ' + dayNum + sfx + ' day of ' + monthName + ', ' + year + '</p>'
        + '<div style="margin-top:40px;text-align:center;"><div style="border-top:1px solid black;width:250px;margin:0 auto;padding-top:4px;"><strong>REGISTRAR</strong><br><em>High Court of the Federal Capital Territory</em></div></div>'
        + '<p style="margin-top:24px;">This Writ was issued by the Lodge Officer (ID: ' + sheriffId + ')</p>'
        + '<p>on behalf of the Judgment Creditor.</p>'
        + '<hr style="border:none;border-top:2px solid black;margin:24px 0;">'
        + '<div style="font-weight:bold;font-size:13px;margin-bottom:12px;">RETURN OF SERVICE / EXECUTION</div>'
        + '<p style="margin-bottom:12px;">I hereby certify that I have executed this Writ of Fi. Fa. as follows:</p>'
        + '<div style="border-bottom:1px solid #999;margin-bottom:8px;min-height:20px;"></div>'
        + '<div style="border-bottom:1px solid #999;margin-bottom:8px;min-height:20px;"></div>'
        + '<div style="border-bottom:1px solid #999;margin-bottom:16px;min-height:20px;"></div>'
        + '<p><strong>Amount realised:</strong> ₦……………………………………</p>'
        + '<p><strong>Sheriff\'s/Bailiff\'s fees and expenses:</strong> ₦……………………………………</p>'
        + '<p style="margin-bottom:24px;"><strong>Net amount payable to Judgment Creditor:</strong> ₦……………………………………</p>'
        + '<div style="margin-top:40px;"><div style="border-top:1px solid black;width:250px;padding-top:4px;"><strong>SHERIFF / DEPUTY SHERIFF / BAILIFF</strong></div><p style="margin-top:8px;">Date: ……………………………………</p></div>';
    } else {
        docHTML = '<div style="text-align:center;font-weight:bold;font-size:14px;text-decoration:underline;margin-bottom:24px;text-transform:uppercase;">GARNISHEE PROCEEDING DOCUMENT</div>'
        + '<div style="display:flex;justify-content:space-between;font-weight:bold;margin-bottom:16px;text-transform:uppercase;"><span>Case No: ' + caseId + '</span><span>Date: ' + dateStr + '</span></div>'
        + '<div style="text-align:justify;">'
        + '<h4 style="font-weight:bold;border-bottom:1px solid #999;padding-bottom:4px;margin:16px 0 8px 0;">RECITALS / PREAMBLE</h4>'
        + '<p>WHEREAS, judgment has been rendered by the High Court of the Federal Capital Territory in the case of <strong>' + caseId + '</strong>, in favor of <strong>' + plaintiff + '</strong> (hereinafter referred to as the "Judgment Creditor") against <strong>' + defendant + '</strong> (hereinafter referred to as the "Judgment Debtor"), for the Judgment Sum.</p>'
        + '<p>AND WHEREAS, the Judgment Creditor has applied for a Garnishee Order Nisi pursuant to the judgment.</p>'
        + '<h4 style="font-weight:bold;border-bottom:1px solid #999;padding-bottom:4px;margin:24px 0 8px 0;">DEFINITIONS</h4>'
        + '<ul style="list-style:disc;padding-left:20px;"><li><strong>"Garnishee"</strong>: A third party holding money or property belonging to the Judgment Debtor.</li><li><strong>"Court"</strong>: The High Court of the FCT.</li><li><strong>"Judgment Sum"</strong>: The total amount awarded, inclusive of costs and interest.</li></ul>'
        + '<h4 style="font-weight:bold;border-bottom:1px solid #999;padding-bottom:4px;margin:24px 0 8px 0;">1. IDENTIFICATION OF PARTIES</h4>'
        + '<p>1.1. Judgment Creditor: <strong>' + plaintiff + '</strong></p><p>1.2. Judgment Debtor: <strong>' + defendant + '</strong></p><p>1.3. Garnishee: <strong>' + extraDetails + '</strong></p>'
        + '<h4 style="font-weight:bold;border-bottom:1px solid #999;padding-bottom:4px;margin:24px 0 8px 0;">2. GARNISHEE PROCEEDINGS</h4>'
        + '<p>2.1. The Judgment Creditor commences Garnishee proceedings against the Garnishee in accordance with the relevant laws of the Federal Republic of Nigeria.</p>'
        + '<p>2.2. The Judgment Creditor seeks to recover the Judgment Sum from the Garnishee.</p>'
        + '<h4 style="font-weight:bold;border-bottom:1px solid #999;padding-bottom:4px;margin:24px 0 8px 0;">3. COURT ORDERS</h4>'
        + '<p>3.1. A Garnishee Order Nisi is hereby sought against the Garnishee.</p><p>3.2. The Garnishee is required to appear before the Court to show cause why the funds should not be used to satisfy the Judgment Sum.</p>'
        + '<h4 style="font-weight:bold;border-bottom:1px solid #999;padding-bottom:4px;margin:24px 0 8px 0;">EXECUTION BLOCK</h4>'
        + '<p>This document shall be executed by the Sheriff on behalf of the Judgment Creditor. Signed at Abuja on ' + dateStr + '.</p>'
        + '<div style="padding-top:48px;display:flex;justify-content:space-between;margin-top:24px;"><div style="text-align:center;width:192px;"><div style="border-top:1px solid #555;font-weight:bold;padding-top:4px;text-transform:uppercase;">SHERIFF</div><p style="font-size:10px;margin-top:4px;">ID: ' + sheriffId + '</p></div></div>'
        + '</div>';
    }

    content.innerHTML = docHTML;
    modal.classList.remove("hidden");
}

function closeWritModal() {
    animateCloseModal("writ-modal");
}

function printWrit() {
    const contentEl = document.getElementById("modal-writ-content");
    if (!contentEl) return;
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });

    const printWindow = window.open('', '_blank');
    if (!printWindow) { alert('Pop-up blocked! Please allow pop-ups for this site to print.'); return; }

    const css = '@page{margin:1.5cm}*{margin:0;padding:0;box-sizing:border-box}'
        + 'body{font-family:"Times New Roman",Times,serif;font-size:12px;line-height:1.7;color:black;background:white}'
        + '.hdr{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid black;padding-bottom:10px;margin-bottom:24px}'
        + '.hdr h2{font-weight:800;font-size:22px;letter-spacing:4px;margin:0;line-height:1}'
        + '.hdr .sub{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:2px;margin-top:4px}'
        + '.hdr .dt{font-size:11px;font-family:monospace;font-weight:700}'
        + 'h4{page-break-after:avoid;break-after:avoid}hr{page-break-after:avoid}p{margin-bottom:6px}strong{font-weight:bold}em{font-style:italic}';

    const html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>COURTLOG</title><style>' + css + '</style></head><body>'
        + '<div class="hdr"><div><h2>COURTLOG</h2><div class="sub">Official Registry Document</div></div><div class="dt">' + dateStr + '</div></div>'
        + contentEl.innerHTML
        + '<script>window.onload=function(){setTimeout(function(){window.print()},300)}<\/script></body></html>';

    printWindow.document.write(html);
    printWindow.document.close();
}


// ----------------- CORE SEARCH & FILTER CONTROLS -----------------

function filterCases() {
    const query = document.getElementById("global-search").value.toLowerCase();
    const status = document.getElementById("filter-status").value;
    const risk = document.getElementById("filter-risk").value;

    const filtered = casesData.filter(c => {
        // Query Match
        const matchQuery = c.case_id.toLowerCase().includes(query) ||
            c.case_type.toLowerCase().includes(query) ||
            c.court.toLowerCase().includes(query);

        // Status Match
        let matchStatus = true;
        if (status === "ALERTS") {
            matchStatus = c.custody_alert || c.enforcement_non_compliant;
        } else if (status !== "ALL") {
            matchStatus = c.judgment_status === status;
        }

        // Risk Match
        let matchRisk = true;
        if (risk === "HIGH") {
            matchRisk = c.risk_flag;
        } else if (risk === "MED") {
            matchRisk = c.delay_risk_score >= 0.40 && !c.risk_flag;
        } else if (risk === "LOW") {
            matchRisk = c.delay_risk_score < 0.40;
        }

        return matchQuery && matchStatus && matchRisk;
    });

    renderHeatmapTable(filtered);
}

function resetFilters() {
    document.getElementById("global-search").value = "";
    document.getElementById("filter-status").value = "ALL";
    document.getElementById("filter-risk").value = "ALL";
    renderHeatmapTable(casesData);
}

function filterByAlert(type) {
    switchTab("tab-overview");
    const statusSelect = document.getElementById("filter-status");
    statusSelect.value = "ALERTS";

    // Filter specifically by alert type
    let filtered;
    if (type === 'custody') {
        filtered = casesData.filter(c => c.custody_alert === true);
    } else if (type === 'enforcement') {
        filtered = casesData.filter(c => c.enforcement_non_compliant === true);
    } else {
        filtered = casesData.filter(c => c.custody_alert || c.enforcement_non_compliant);
    }

    renderHeatmapTable(filtered);

    // Scroll to the table
    setTimeout(() => {
        const table = document.getElementById("cases-table-body");
        if (table) {
            const panel = table.closest('.glass-panel');
            if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, 150);
}

// ----------------- BACKGROUND SYNC DRIVER (CRON SIM) -----------------

async function triggerCronCompliance() {
    logger("Triggering manual cron compliance sweep...");
    const cronIcon = document.getElementById("cron-icon");

    cronIcon.classList.add("animate-spin");

    try {
        const response = await apiFetch(`${API_BASE}/cron`, { method: "POST", headers: getAuthHeaders() });
        if (!response.ok) throw new Error("Cron sweep endpoint failed");

        const result = await response.json();
        logger(`Compliance sweep complete. Total Alerts: ${result.stats.custody_alerts + result.stats.non_compliant_enforcements}`);

        await loadDashboardData();

        // Display summary dialog
        alert(`Compliance Sweep Complete!\n---------------------------------\nRegistry Custody Alerts: ${result.stats.custody_alerts}\nEnforcement Non-Compliances: ${result.stats.non_compliant_enforcements}\nHigh Risk Delay Files: ${result.stats.high_risk_delay_cases}`);

    } catch (error) {
        logger(`Error running cron sweep: ${error}`);
    } finally {
        cronIcon.classList.remove("animate-spin");
    }
}

// ================== NEW RBAC FEATURE HANDLERS ==================

// Report Missing File (Sheriff)
async function handleReportMissing(e) {
    e.preventDefault();
    const caseId = document.getElementById("missing-case-id").value;
    const location = document.getElementById("missing-location").value;
    const notes = document.getElementById("missing-notes").value;

    if (!caseId) {
        showToast("Please select a case ID.", "error");
        return;
    }

    try {
        const response = await apiFetch(`${API_BASE}/cases/${caseId}/report-missing`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ last_known_location: location, notes: notes })
        });

        if (response.ok) {
            showToast(`Case ${caseId} reported missing.`, "success");
            document.getElementById("form-report-missing").reset();
            await loadDashboardData();
        } else {
            const err = await response.json();
            showToast(err.detail || "Failed to report missing file.", "error");
        }
    } catch (error) {
        showToast("Network error reporting missing file.", "error");
    }
}

// Case Reassignment (DCR / CR)
function openReassignModal(caseId = "") {
    document.getElementById("reassign-case-id").value = caseId;
    animateOpenModal("reassign-modal");
}

function closeReassignModal() {
    animateCloseModal("reassign-modal");
}

async function submitReassignCase(e) {
    e.preventDefault();
    const caseId = document.getElementById("reassign-case-id").value;
    const division = document.getElementById("reassign-division").value;
    const court = document.getElementById("reassign-court").value;
    const reason = document.getElementById("reassign-reason").value;

    try {
        const response = await apiFetch(`${API_BASE}/cases/${caseId}/reassign`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ new_division: division || null, new_court: court || null, reason: reason })
        });

        if (response.ok) {
            showToast(`Case ${caseId} reassigned successfully.`, "success");
            closeReassignModal();
            await loadDashboardData();
        } else {
            const err = await response.json();
            showToast(err.detail || "Failed to reassign case.", "error");
        }
    } catch (error) {
        showToast("Network error reassigning case.", "error");
    }
}

// Assign Judge (CR)
function openAssignJudgeModal(caseId = "") {
    document.getElementById("assign-judge-case-id").value = caseId;
    animateOpenModal("assign-judge-modal");
}

function closeAssignJudgeModal() {
    animateCloseModal("assign-judge-modal");
}

async function submitAssignJudge(e) {
    e.preventDefault();
    const caseId = document.getElementById("assign-judge-case-id").value;
    const judgeId = document.getElementById("assign-judge-id").value;
    const reason = document.getElementById("assign-judge-reason").value;

    try {
        const response = await apiFetch(`${API_BASE}/cases/${caseId}/assign-judge`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ judge_id: judgeId, reason: reason })
        });

        if (response.ok) {
            showToast(`Judge ${judgeId} assigned to ${caseId}.`, "success");
            closeAssignJudgeModal();
            await loadDashboardData();
        } else {
            const err = await response.json();
            showToast(err.detail || "Failed to assign judge.", "error");
        }
    } catch (error) {
        showToast("Network error assigning judge.", "error");
    }
}

function openAssignSheriffModal(caseId = "") {
    return openSheriffCustodyModal(caseId, "assign");
}

function openSheriffHandoverModal(caseId = "") {
    return openSheriffCustodyModal(caseId, "handover");
}

async function openSheriffCustodyModal(caseId, mode) {
    if (!caseId) {
        showToast("Select a case file before managing custody.", "error");
        return;
    }
    activeSheriffCustodyCaseId = caseId;
    activeSheriffCustodyMode = mode;

    const handover = mode === "handover";
    const form = document.getElementById("form-sheriff-custody");
    const caseInput = document.getElementById("assign-sheriff-case-id");
    const title = document.getElementById("sheriff-custody-title");
    const help = document.getElementById("sheriff-custody-help");
    const locationField = document.getElementById("sheriff-handover-location-field");
    const locationSelect = document.getElementById("sheriff-handover-location");
    const reasonInput = document.getElementById("sheriff-custody-reason");
    const targetSelect = document.getElementById("sheriff-custody-target");
    const submitButton = document.getElementById("sheriff-custody-submit");

    form.reset();
    caseInput.value = caseId;
    title.textContent = handover ? "Hand Over Case Custody" : "Assign Sheriff Custody";
    help.textContent = handover
        ? "Choose another active Sheriff assigned to this court. This records the authenticated handover actor and transfers case visibility."
        : "Choose an active Sheriff assigned to this case's court. Only the assigned Sheriff will receive physical-custody access.";
    locationField.classList.toggle("hidden", !handover);
    locationSelect.required = handover;
    reasonInput.value = handover ? "End of duty handover" : "Registry dispatch";
    targetSelect.replaceChildren(new Option("Loading eligible Sheriffs…", ""));
    targetSelect.disabled = true;
    submitButton.disabled = true;
    submitButton.textContent = handover ? "Record Handover" : "Assign Sheriff";
    animateOpenModal("sheriff-custody-modal");

    try {
        const response = await apiFetch(`${API_BASE}/cases/${caseId}/sheriffs`, {
            method: "GET",
            headers: getAuthHeaders()
        });
        if (activeSheriffCustodyCaseId !== caseId || activeSheriffCustodyMode !== mode) return;
        const result = await response.json();
        if (!response.ok) {
            showToast(result.detail || "Unable to load eligible Sheriffs.", "error");
            closeSheriffCustodyModal();
            return;
        }

        targetSelect.replaceChildren(new Option("Select a Sheriff", ""));
        result.forEach(sheriff => {
            const option = document.createElement("option");
            option.value = sheriff.user_id;
            option.textContent = `${sheriff.name} (${sheriff.user_id})`;
            targetSelect.appendChild(option);
        });
        if (result.length === 0) {
            targetSelect.replaceChildren(new Option("No eligible Sheriff for this court", ""));
        }
        targetSelect.disabled = result.length === 0;
        submitButton.disabled = result.length === 0;
    } catch (error) {
        if (activeSheriffCustodyCaseId === caseId && activeSheriffCustodyMode === mode) {
            showToast("Network error loading eligible Sheriffs.", "error");
            closeSheriffCustodyModal();
        }
    }
}

function closeSheriffCustodyModal() {
    activeSheriffCustodyCaseId = null;
    activeSheriffCustodyMode = null;
    animateCloseModal("sheriff-custody-modal");
    document.getElementById("form-sheriff-custody")?.reset();
}

async function submitSheriffCustody(event) {
    event.preventDefault();
    const caseId = activeSheriffCustodyCaseId;
    const mode = activeSheriffCustodyMode;
    const sheriffId = document.getElementById("sheriff-custody-target").value;
    const reason = document.getElementById("sheriff-custody-reason").value.trim();
    const location = document.getElementById("sheriff-handover-location").value;
    if (!caseId || !mode || !sheriffId || !reason) return;

    const endpoint = mode === "handover" ? "handover" : "assign-sheriff";
    const payload = mode === "handover"
        ? { to_sheriff_id: sheriffId, location, reason }
        : { sheriff_id: sheriffId, reason };
    try {
        const response = await apiFetch(`${API_BASE}/cases/${caseId}/${endpoint}`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            showToast(mode === "handover"
                ? `Custody handed over to ${sheriffId}.`
                : `Sheriff ${sheriffId} assigned to ${caseId}.`, "success");
            closeSheriffCustodyModal();
            await loadDashboardData();
        } else {
            const err = await response.json();
            showToast(err.detail || "Unable to update case custody.", "error");
        }
    } catch (error) {
        showToast("Network error updating case custody.", "error");
    }
}

// Record document metadata (Clerk); binary file storage is not implemented yet.
async function handleUploadDocument(e) {
    e.preventDefault();
    const caseId = document.getElementById("upload-case-id").value.trim();
    const docType = document.getElementById("upload-doc-type").value;
    const title = document.getElementById("upload-title").value.trim();
    const filename = document.getElementById("upload-filename").value.trim();

    try {
        const response = await apiFetch(`${API_BASE}/cases/${caseId}/documents`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ document_type: docType, title: title, filename: filename, notes: "" })
        });

        if (response.ok) {
            showToast(`Document metadata recorded for ${caseId}; file storage is not enabled yet.`, "success");
            document.getElementById("form-upload-doc").reset();
            await loadDashboardData();
        } else {
            const err = await response.json();
            showToast(err.detail || "Failed to record document metadata.", "error");
        }
    } catch (error) {
        showToast("Network error recording document metadata.", "error");
    }
}

// DCR Weekly Report
async function generateDCRWeeklyReport() {
    try {
        const response = await apiFetch(`${API_BASE}/export/dcr-weekly`, {
            headers: getAuthHeaders()
        });

        if (response.ok) {
            const data = await response.json();
            document.getElementById("njc-report-json-view").textContent = JSON.stringify(data, null, 2);
            animateOpenModal("njc-modal");
            // Reuse the NJC modal view for displaying the JSON report for simplicity
        } else {
            const err = await response.json();
            showToast(err.detail || "Failed to generate report.", "error");
        }
    } catch (error) {
        showToast("Network error generating weekly report.", "error");
    }
}

async function fetchJudgeAlerts() {
    try {
        const response = await apiFetch(`${API_BASE}/judge/alerts`, { headers: getAuthHeaders() });
        if (response.ok) {
            const data = await response.json();
            const alertCount = document.getElementById("judge-alert-count");
            if (alertCount) {
                alertCount.textContent = data.total_alerts;
                if (data.total_alerts > 0) {
                    alertCount.parentElement.parentElement.parentElement.classList.remove("hidden");
                } else {
                    alertCount.parentElement.parentElement.parentElement.classList.add("hidden");
                }
            }
        }
    } catch (e) {
        console.error("Failed to fetch judge alerts");
    }
}

// ----------------- MODULE 3: AI RISK INTELLIGENCE DASHBOARD -----------------

let aiRiskData = [];

async function loadAIRiskData() {
    try {
        const response = await apiFetch(`${API_BASE}/predict/batch`, {
            headers: getAuthHeaders()
        });
        if (!response.ok) throw new Error('Batch predict failed');
        aiRiskData = await response.json();
        renderAIRiskDashboard();
        showToast(`AI model re-scored ${aiRiskData.length} cases`, 'success');
    } catch (error) {
        logger(`AI Risk load error: ${error}`);
        showToast('Failed to load AI predictions', 'error');
    }
}

function renderAIRiskDashboard() {
    const data = aiRiskData;
    if (!data.length) return;

    const high = data.filter(c => c.delay_risk_score > 0.70);
    const medium = data.filter(c => c.delay_risk_score >= 0.40 && c.delay_risk_score <= 0.70);
    const low = data.filter(c => c.delay_risk_score < 0.40);

    // Summary cards
    document.getElementById('ai-total-cases').textContent = data.length;
    document.getElementById('ai-high-count').textContent = high.length;
    document.getElementById('ai-medium-count').textContent = medium.length;
    document.getElementById('ai-low-count').textContent = low.length;

    // Risk distribution bar
    const total = data.length;
    const barEl = document.getElementById('ai-risk-bar');
    const hPct = ((high.length / total) * 100).toFixed(1);
    const mPct = ((medium.length / total) * 100).toFixed(1);
    const lPct = ((low.length / total) * 100).toFixed(1);
    barEl.innerHTML = `
        <div style="width:${hPct}%;background:linear-gradient(90deg,#dc2626,#ef4444);transition:width 0.6s ease;" title="High: ${hPct}%"></div>
        <div style="width:${mPct}%;background:linear-gradient(90deg,#d97706,#f59e0b);transition:width 0.6s ease;" title="Medium: ${mPct}%"></div>
        <div style="width:${lPct}%;background:linear-gradient(90deg,#16a34a,#22c55e);transition:width 0.6s ease;" title="Low: ${lPct}%"></div>
    `;

    // Table rows
    const tbody = document.getElementById('ai-risk-table-body');
    tbody.innerHTML = data.map(safeRecord).map(c => {
        const score = c.delay_risk_score;
        const pct = (score * 100).toFixed(1);
        let riskLabel, riskColor, riskIcon, barBg;
        if (score > 0.70) {
            riskLabel = 'HIGH'; riskColor = '#ef4444'; riskIcon = 'fa-circle-exclamation'; barBg = 'linear-gradient(90deg,#dc2626,#ef4444)';
        } else if (score >= 0.40) {
            riskLabel = 'MEDIUM'; riskColor = '#f59e0b'; riskIcon = 'fa-triangle-exclamation'; barBg = 'linear-gradient(90deg,#d97706,#f59e0b)';
        } else {
            riskLabel = 'LOW'; riskColor = '#22c55e'; riskIcon = 'fa-circle-check'; barBg = 'linear-gradient(90deg,#16a34a,#22c55e)';
        }
        return `<tr>
            <td><span style="display:inline-flex;align-items:center;gap:6px;color:${riskColor};font-weight:700;font-size:12px;">
                <i class="fa-solid ${riskIcon}"></i> ${riskLabel}</span></td>
            <td class="font-semibold text-heading">${c.case_id}</td>
            <td>${c.case_type}</td>
            <td>${c.court}</td>
            <td class="text-center">${c.adjournment_count}</td>
            <td class="text-center">${c.days_since_filing}</td>
            <td class="text-center">
                <div style="display:flex;align-items:center;gap:8px;justify-content:center;">
                    <div style="flex:1;max-width:80px;height:8px;border-radius:4px;background:rgba(255,255,255,0.08);overflow:hidden;">
                        <div style="width:${pct}%;height:100%;border-radius:4px;background:${barBg};transition:width 0.4s ease;"></div>
                    </div>
                    <span style="color:${riskColor};font-weight:700;font-size:12px;min-width:42px;">${pct}%</span>
                </div>
            </td>
            <td><span class="text-xs px-2 py-1 rounded-full font-semibold" style="background:rgba(255,255,255,0.06);">${c.judgment_status}</span></td>
            <td class="text-center">
                <button data-case-action="explain" data-record-id="${c.case_id}" class="text-xs px-2 py-1 rounded-lg font-semibold"
                    style="background:rgba(139,92,246,0.15);color:#a78bfa;border:1px solid rgba(139,92,246,0.3);cursor:pointer;">
                    <i class="fa-solid fa-magnifying-glass-chart"></i> Why?
                </button>
            </td>
        </tr>`;
    }).join('');
}

function showExplainability(caseId) {
    const c = aiRiskData.find(x => x.case_id === caseId);
    if (!c) return;
    const score = c.delay_risk_score;
    const pct = (score * 100).toFixed(1);
    const factors = [];
    if (c.adjournment_count >= 4) factors.push(`🔴 ${c.adjournment_count} adjournments (high — approaching statutory limit)`);
    else if (c.adjournment_count >= 2) factors.push(`🟡 ${c.adjournment_count} adjournments (moderate delay signal)`);
    else factors.push(`🟢 ${c.adjournment_count} adjournment(s) (within normal range)`);
    if (c.days_since_filing > 365) factors.push(`🔴 ${c.days_since_filing} days since filing (over 1 year — strong delay indicator)`);
    else if (c.days_since_filing > 180) factors.push(`🟡 ${c.days_since_filing} days since filing (6+ months — moderate risk)`);
    else factors.push(`🟢 ${c.days_since_filing} days since filing (recent — low delay signal)`);
    if (['Land Dispute', 'Constitutional Rights', 'Admiralty'].includes(c.case_type)) {
        factors.push(`🟡 Case type "${c.case_type}" historically has higher delay rates`);
    } else {
        factors.push(`🟢 Case type "${c.case_type}" has typical progression rates`);
    }
    const msg = `═══ AI DELAY-RISK EXPLAINABILITY ═══\n\nCase: ${c.case_id}\nRisk Score: ${pct}%\nStatus: ${c.judgment_status}\n\n── Contributing Factors ──\n${factors.join('\n')}\n\n── Model ──\nLogistic Regression trained on 3,000+ Nigerian court records.\nFeatures: case_type, court, adjournment_count, days_since_filing\nThreshold: >70% = High Risk flag`;
    alert(msg);
}
