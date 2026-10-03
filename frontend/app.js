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
function isFileMissingRecord(caseRecord) {
    const report = caseRecord?.file_missing_report;
    if (report && typeof report === "object") return report.resolved !== true;
    return caseRecord?.file_missing === true;
}
// Never put user-controlled identifiers inside executable JavaScript attributes.
document.addEventListener('click', event => {
    const alertFilterButton = event.target.closest('[data-alert-filter]');
    if (alertFilterButton) {
        filterByAlert(alertFilterButton.dataset.alertFilter);
        return;
    }

    const button = event.target.closest('[data-case-action]');
    if (!button) return;
    const actions = {
        scan: shortcutQRScan, hearing: shortcutHearingLog, assign: openAssignJudgeModal,
        assignSheriff: openAssignSheriffModal, handover: openSheriffHandoverModal,
        writ: selectCaseForWrit, override: openDCROverrideModal, acknowledgeDCR: acknowledgeDCRReview,
        ruling: logJudicialRuling, deleteUser: deleteUserAccount, resetPassword: resetUserPassword,
        explain: showExplainability
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
    if (status) status.textContent = demoMode ? "DEMO SIMULATION — NOT LIVE" : "CHECKING SERVER CONFIGURATION";
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
        "ai-risk-table-body", "users-admin-table-body", "whatsapp-logs-container", "case-scan-history", "missing-file-history"]
        .forEach(id => document.getElementById(id)?.replaceChildren());
    ["stat-total-cases", "stat-high-risk", "stat-custody-alerts", "stat-missing-files", "stat-enforcement-alerts",
        "alert-count-custody", "alert-count-missing", "alert-count-enforcement", "judge-alert-count", "ai-total-cases"]
        .forEach(id => { const el = document.getElementById(id); if (el) el.textContent = "0"; });
    document.getElementById("quick-alert-bar")?.classList.add("hidden");
    ["scan-case-id", "missing-case-id", "found-case-id", "missing-history-case-id", "hearing-case-id"].forEach(id => {
        const select = document.getElementById(id);
        if (select) select.replaceChildren(new Option("Select a case", ""));
    });
    window.CourtLogPwa?.stopCamera();
    const qrInput = document.getElementById("qr-payload-input");
    if (qrInput) qrInput.value = "";
    const qrCanvas = document.getElementById("qr-label-canvas");
    if (qrCanvas) {
        qrCanvas.width = qrCanvas.width;
        qrCanvas.height = qrCanvas.height;
        delete qrCanvas.dataset.caseId;
    }
    const printLabelButton = document.getElementById("btn-print-qr-label");
    if (printLabelButton) printLabelButton.disabled = true;
    const qrLabelStatus = document.getElementById("qr-label-status");
    if (qrLabelStatus) qrLabelStatus.textContent = "No label generated.";
    setCustodyCheckinStatus("No check-in submitted.", "info");
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
    if (document.getElementById("app-sidebar")) updateRoleUI();
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

function setSidebarOpen(open, restoreFocus = true) {
    const toggle = document.getElementById("mobile-nav-toggle");
    const backdrop = document.getElementById("nav-backdrop");
    const sidebar = document.getElementById("app-sidebar");
    if (!toggle || !sidebar || !backdrop) return;

    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    const icon = document.getElementById("nav-toggle-icon");
    if (icon) icon.className = `fa-solid ${open ? "fa-xmark" : "fa-bars"}`;
    backdrop.classList.toggle("hidden", !open);

    if (open) {
        sidebar.querySelector(".nav-item:not(.hidden)")?.focus();
    } else if (restoreFocus) {
        toggle.focus();
    }
}

function setProfileMenuOpen(open, restoreFocus = false) {
    const toggle = document.getElementById("profile-menu-toggle");
    const menu = document.getElementById("profile-menu");
    if (!toggle || !menu) return;
    menu.classList.toggle("hidden", !open);
    toggle.setAttribute("aria-expanded", String(open));
    if (!open && restoreFocus) toggle.focus();
}

function initializeShellControls() {
    const navToggle = document.getElementById("mobile-nav-toggle");
    const navBackdrop = document.getElementById("nav-backdrop");
    const profileToggle = document.getElementById("profile-menu-toggle");
    const profileMenu = document.getElementById("profile-menu");

    navToggle?.addEventListener("click", () => {
        const open = navToggle.getAttribute("aria-expanded") !== "true";
        setProfileMenuOpen(false);
        setSidebarOpen(open);
    });
    navBackdrop?.addEventListener("click", () => setSidebarOpen(false));
    profileToggle?.addEventListener("click", () => {
        const open = profileToggle.getAttribute("aria-expanded") !== "true";
        setSidebarOpen(false, false);
        setProfileMenuOpen(open);
    });
    document.addEventListener("click", event => {
        if (profileMenu && !profileMenu.contains(event.target) && !profileToggle?.contains(event.target)) {
            setProfileMenuOpen(false);
        }
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Tab" && document.body.classList.contains("nav-open")) {
            const sidebar = document.getElementById("app-sidebar");
            const items = Array.from(sidebar?.querySelectorAll(".nav-item:not(.hidden):not(:disabled)") || []);
            const first = items[0];
            const last = items[items.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last?.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first?.focus();
            }
        }
        if (event.key !== "Escape") return;
        if (document.body.classList.contains("nav-open")) setSidebarOpen(false);
        if (profileToggle?.getAttribute("aria-expanded") === "true") setProfileMenuOpen(false, true);
    });
    window.addEventListener("resize", () => {
        if (window.innerWidth > 1024 && document.body.classList.contains("nav-open")) {
            setSidebarOpen(false, false);
        }
    });
}

// ===== APP INITIALIZATION =====
document.addEventListener("DOMContentLoaded", async function () {
    initializeShellControls();
    window.CourtLogPwa?.initialize();
    window.CourtLogPwa?.setScanHandler(handleQrPayloadFromCamera);
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
        updateRoleUI();
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
    toast.innerHTML = `<i class="fa-solid ${icons[type] || icons.info}" aria-hidden="true"></i><span>${escapeHTML(message)}</span><button type="button" aria-label="Dismiss notification" onclick="this.parentElement.remove()" class="toast-close">&times;</button>`;
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

function syncCaseRegistrationDefaults(user = getActiveUser()) {
    const panel = document.getElementById("register-case-panel");
    const courtSelect = document.getElementById("new-case-court");
    const typeSelect = document.getElementById("new-case-type");
    const canRegister = user.role === "Chief Registrar" || (user.role === "Clerk" && Boolean(user.court));

    if (panel) panel.classList.toggle("hidden", !canRegister);
    if (!courtSelect) return;

    const options = Array.from(courtSelect.options);
    if (user.role === "Clerk" && user.court) {
        let assignedOption = options.find(option => option.value === user.court);
        if (!assignedOption) {
            assignedOption = new Option(user.court, user.court);
            courtSelect.add(assignedOption);
        }
        for (const option of courtSelect.options) option.disabled = option !== assignedOption;
        courtSelect.value = user.court;
        courtSelect.disabled = true;
        courtSelect.title = "Clerks can register cases only in their assigned court.";
    } else {
        courtSelect.disabled = false;
        courtSelect.title = "Select the court for this case.";
        for (const option of courtSelect.options) option.disabled = false;
        const profileCourt = options.find(option => option.value === user.court);
        if (profileCourt) {
            courtSelect.value = profileCourt.value;
        } else if (options.some(option => option.value === "FHC Abuja Court 4")) {
            courtSelect.value = "FHC Abuja Court 4";
        }
    }

    if (typeSelect && user.role === "Clerk" && user.division === "Criminal"
        && Array.from(typeSelect.options).some(option => option.value === "Criminal")) {
        typeSelect.value = "Criminal";
    }
}

function setNavItemVisible(id, visible) {
    const item = document.getElementById(id);
    if (!item) return;
    item.classList.toggle("hidden", !visible);
    item.setAttribute("aria-hidden", String(!visible));
}

function updateNavGroups() {
    document.querySelectorAll("[data-nav-group]").forEach(group => {
        const items = Array.from(group.querySelectorAll("[data-tab]"));
        group.classList.toggle("hidden", items.length > 0 && items.every(item => item.classList.contains("hidden")));
    });
}

function canAccessTab(tabId, user = authenticatedUser) {
    if (!user) return tabId === "tab-overview";
    const role = user.role;
    const roleAccess = {
        "tab-case-register": role === "Chief Registrar" || (role === "Clerk" && Boolean(user.court)),
        "tab-qr-scan": ["Sheriff", "Clerk", "Chief Registrar"].includes(role),
        "tab-courtrooms": ["Clerk", "Judge", "Chief Registrar"].includes(role),
        "tab-execution": ["Sheriff", "Chief Registrar"].includes(role),
        "tab-dcr-console": ["DCR", "Chief Registrar"].includes(role),
        "tab-judge-docket": ["Judge", "Chief Registrar"].includes(role),
        "tab-user-admin": role === "Chief Registrar",
        "tab-whatsapp": role === "Chief Registrar"
    };
    return Object.prototype.hasOwnProperty.call(roleAccess, tabId) ? roleAccess[tabId] : true;
}

function updateRoleUI() {
    const user = authenticatedUser ? getActiveUser() : null;
    const accountName = document.getElementById("sidebar-user-name");
    const roleLabel = document.getElementById("sidebar-user-role");
    const scopeLabel = document.getElementById("active-user-scope");
    const initials = document.getElementById("active-user-initials");
    const profileToggle = document.getElementById("profile-menu-toggle");
    const registerPanel = document.getElementById("register-case-panel");

    if (!user) {
        if (accountName) accountName.textContent = "Signed out";
        if (roleLabel) roleLabel.textContent = "Not signed in";
        if (scopeLabel) scopeLabel.textContent = "Sign in to view your assigned workspace";
        if (initials) initials.textContent = "—";
        profileToggle?.setAttribute("aria-label", "Account options — signed out");
        if (profileToggle) profileToggle.disabled = true;
        setProfileMenuOpen(false);
        document.querySelectorAll("#sidebar-nav-container [data-tab]").forEach(item => {
            item.classList.toggle("hidden", item.dataset.tab !== "tab-overview");
            item.setAttribute("aria-hidden", String(item.dataset.tab !== "tab-overview"));
        });
        registerPanel?.classList.add("hidden");
        ["btn-register-case", "btn-prototype-summary", "btn-cron-sweep"].forEach(id => {
            const button = document.getElementById(id);
            if (button) button.hidden = true;
        });
        updateNavGroups();
        window.CourtLogPwa?.setRole("");
        return;
    }

    syncCaseRegistrationDefaults(user);
    if (accountName) accountName.textContent = user.name || user.username || "Account";
    if (roleLabel) roleLabel.textContent = user.role || "Staff";
    if (scopeLabel) {
        const scope = [];
        if (user.court) scope.push(user.court);
        if (user.division && user.division !== "All Divisions") scope.push(`${user.division} division`);
        scopeLabel.textContent = scope.join(" · ") || "Assigned workspace";
    }
    if (initials) initials.textContent = user.initials || "U";
    profileToggle?.setAttribute("aria-label", `Account options for ${user.name || user.username || "user"}`);
    if (profileToggle) profileToggle.disabled = false;

    const role = user.role;
    const canRegister = role === "Chief Registrar" || (role === "Clerk" && Boolean(user.court));
    const navVisibility = {
        "nav-overview": true,
        "nav-case-register": canRegister,
        "nav-qr-scan": ["Sheriff", "Clerk", "Chief Registrar"].includes(role),
        "nav-courtrooms": ["Clerk", "Judge", "Chief Registrar"].includes(role),
        "nav-execution": ["Sheriff", "Chief Registrar"].includes(role),
        "nav-dcr-console": ["DCR", "Chief Registrar"].includes(role),
        "nav-judge-docket": ["Judge", "Chief Registrar"].includes(role),
        "nav-ai-risk": true,
        "nav-user-admin": role === "Chief Registrar",
        "nav-whatsapp": role === "Chief Registrar"
    };
    Object.entries(navVisibility).forEach(([id, visible]) => setNavItemVisible(id, visible));
    updateNavGroups();

    const buttonVisibility = {
        "btn-register-case": canRegister,
        "btn-prototype-summary": ["Chief Registrar", "DCR"].includes(role),
        "btn-cron-sweep": role === "Chief Registrar"
    };
    Object.entries(buttonVisibility).forEach(([id, visible]) => {
        const button = document.getElementById(id);
        if (button) button.hidden = !visible;
    });

    const scanOperator = document.getElementById("scan-authenticated-operator");
    if (scanOperator) scanOperator.textContent = `${user.name} (${user.role})`;

    const sheriffQrTools = document.getElementById("sheriff-qr-tools");
    const qrLabelTools = document.getElementById("qr-label-tools");
    const reportMissingTools = document.getElementById("report-missing-tools");
    const resolveMissingTools = document.getElementById("resolve-missing-tools");
    const canManageMissingFiles = ["Sheriff", "Chief Registrar"].includes(role);
    if (sheriffQrTools) sheriffQrTools.classList.toggle("hidden", role !== "Sheriff");
    if (qrLabelTools) qrLabelTools.classList.toggle("hidden", !["Clerk", "Chief Registrar"].includes(role));
    if (reportMissingTools) reportMissingTools.classList.toggle("hidden", !canManageMissingFiles);
    if (resolveMissingTools) resolveMissingTools.classList.toggle("hidden", !canManageMissingFiles);
    window.CourtLogPwa?.setRole(role);

    const activePage = Array.from(document.querySelectorAll("#page-content > section"))
        .find(section => !section.classList.contains("hidden"));
    if (activePage && !canAccessTab(activePage.id, user)) switchTab("tab-overview");
}

// Logger Utility
function logger(message) {
    console.log(`[CourtLog App] ${new Date().toLocaleTimeString()} - ${message}`);
}

// Switching Tabs (Single Page App Navigation)
function switchTab(tabId) {
    if (!document.getElementById(tabId) || !canAccessTab(tabId)) {
        if (authenticatedUser && tabId !== "tab-overview") {
            showToast("That workspace is not available to your signed-in role.", "warning");
        }
        tabId = "tab-overview";
    }

    document.querySelectorAll("#page-content > section").forEach(section => {
        const active = section.id === tabId;
        section.classList.toggle("hidden", !active);
        section.setAttribute("aria-hidden", String(!active));
    });

    document.querySelectorAll("#sidebar-nav-container [data-tab]").forEach(button => {
        const active = button.dataset.tab === tabId;
        button.classList.toggle("active", active);
        if (active) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
    });

    const hadMobileNav = document.body.classList.contains("nav-open");
    setProfileMenuOpen(false);
    if (hadMobileNav) setSidebarOpen(false, false);

    const viewTitles = {
        "tab-overview": "Dashboard",
        "tab-case-register": "Register a case",
        "tab-qr-scan": "Custody check-in",
        "tab-courtrooms": "Hearing log",
        "tab-dcr-console": "DCR review queue",
        "tab-judge-docket": "Judge's docket",
        "tab-ai-risk": "Experimental risk",
        "tab-execution": "Execution work",
        "tab-user-admin": "User management",
        "tab-whatsapp": "WhatsApp activity"
    };
    const title = document.getElementById("view-title");
    if (title) title.textContent = viewTitles[tabId] || "Registry workspace";
    const pageContent = document.getElementById("page-content");
    if (pageContent) pageContent.scrollTop = 0;
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    if (hadMobileNav) title?.focus({ preventScroll: true });

    if (tabId === "tab-ai-risk" && typeof aiRiskData !== "undefined" && aiRiskData.length === 0) {
        loadAIRiskData();
    }
    if (tabId === "tab-judge-docket" && ["Judge", "Chief Registrar"].includes(authenticatedUser?.role)) {
        fetchJudgeAlerts();
    }
    if (tabId === "tab-whatsapp" && authenticatedUser?.role === "Chief Registrar") {
        loadWhatsAppStatus();
        loadWhatsAppLogs();
    }
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
        if (["Judge", "Chief Registrar"].includes(getActiveUser().role)) {
            await fetchJudgeAlerts();
        } else {
            const alertBanner = document.getElementById("judge-alert-banner");
            alertBanner?.classList.add("hidden");
            document.getElementById("judge-alert-list")?.replaceChildren();
            const alertCount = document.getElementById("judge-alert-count");
            if (alertCount) alertCount.textContent = "0";
        }
        if (authenticatedUser?.role === "Chief Registrar") {
            populateWhatsAppTestCases();
            loadWhatsAppStatus();
            loadWhatsAppLogs();
        }
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

async function loadWhatsAppStatus() {
    try {
        const response = await apiFetch(`${API_BASE}/whatsapp/status`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error("Unable to read WhatsApp configuration status");
        const statusData = await response.json();
        const status = document.getElementById("whatsapp-mode-status");
        const detail = document.getElementById("whatsapp-config-detail");
        const labels = {
            demo_simulation: "DEMO SIMULATION — NOT LIVE",
            disabled: "DELIVERY DISABLED",
            misconfigured: "CLOUD API INCOMPLETE",
            cloud_api: "META API CONFIGURED — UNVERIFIED"
        };
        if (status) status.textContent = labels[statusData.mode] || "STATUS UNAVAILABLE";
        if (detail) {
            const missing = Array.isArray(statusData.missing) && statusData.missing.length
                ? ` Missing server settings: ${statusData.missing.join(", ")}.`
                : "";
            const template = statusData.template_name ? ` Template: ${statusData.template_name}.` : "";
            detail.textContent = `${statusData.message || ""}${template}${missing} Signed webhook: ${statusData.webhook_ready ? "configured" : "not configured"}.`;
        }
    } catch (error) {
        const status = document.getElementById("whatsapp-mode-status");
        const detail = document.getElementById("whatsapp-config-detail");
        if (status) status.textContent = "STATUS UNAVAILABLE";
        if (detail) detail.textContent = "WhatsApp configuration status could not be loaded.";
        logger(`Error loading WhatsApp status: ${error}`);
    }
}

async function loadWhatsAppLogs() {
    try {
        const response = await apiFetch(`${API_BASE}/whatsapp/logs`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error("HTTP error loading logs");
        whatsappLogs = await response.json();
        renderWhatsAppLogs();
    } catch (error) {
        logger(`Error loading WhatsApp logs: ${error}`);
    }
}

function populateWhatsAppTestCases() {
    const select = document.getElementById("whatsapp-test-case");
    if (!select) return;
    const previous = select.value;
    select.replaceChildren(new Option("Select a case", ""));
    casesData.forEach(caseRecord => {
        const option = new Option(String(caseRecord.case_id || ""), String(caseRecord.case_id || ""));
        select.add(option);
    });
    if (previous && Array.from(select.options).some(option => option.value === previous)) {
        select.value = previous;
    }
}

async function handleWhatsAppPreferenceSubmit(event) {
    event.preventDefault();
    const phone = document.getElementById("whatsapp-preference-phone").value.trim();
    const status = document.getElementById("whatsapp-preference-choice").value;
    const consent_source = document.getElementById("whatsapp-consent-source").value.trim();
    const evidence_reference = document.getElementById("whatsapp-consent-reference").value.trim();
    const output = document.getElementById("whatsapp-preference-status");
    if (status === "opted_in" && !evidence_reference) {
        if (output) output.textContent = "Add the evidence reference before recording an opt-in.";
        return;
    }
    try {
        const response = await apiFetch(`${API_BASE}/whatsapp/preferences`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ phone, status, consent_source, evidence_reference: evidence_reference || null })
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || "Preference could not be saved.");
        if (output) output.textContent = `${body.status} recorded for ${body.recipient}.`;
        document.getElementById("whatsapp-preference-phone").value = "";
        document.getElementById("whatsapp-consent-source").value = "";
        document.getElementById("whatsapp-consent-reference").value = "";
        showToast(`WhatsApp preference recorded for ${body.recipient}.`, "success");
        await loadWhatsAppLogs();
    } catch (error) {
        if (output) output.textContent = error.message || "Preference could not be saved.";
        showToast(error.message || "Preference could not be saved.", "error");
    }
}

async function handleWhatsAppTestSubmit(event) {
    event.preventDefault();
    const case_id = document.getElementById("whatsapp-test-case").value;
    const recipient_role = document.getElementById("whatsapp-test-party").value;
    const output = document.getElementById("whatsapp-test-status");
    if (!case_id) {
        if (output) output.textContent = "Select a case contact first.";
        return;
    }
    try {
        const response = await apiFetch(`${API_BASE}/whatsapp/test-send`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ case_id, recipient_role })
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || "The test template was not queued.");
        if (output) output.textContent = `${body.status} to ${body.recipient}; verify the delivery log and Meta callback.`;
        showToast(`Test template ${body.status} for ${body.recipient}.`, body.status === "simulated" ? "info" : "success");
        window.setTimeout(loadWhatsAppLogs, 800);
    } catch (error) {
        if (output) output.textContent = error.message || "The test template was not sent.";
        showToast(error.message || "The test template was not sent.", "error");
    }
}

// ----------------- RENDERING & DOM INJECTION -----------------

function renderOverviewMetrics() {
    const total = casesData.length;
    const highRisk = casesData.filter(c => c.risk_flag).length;
    const custodyAlerts = casesData.filter(c => c.custody_alert).length;
    const missingFiles = casesData.filter(isFileMissingRecord).length;
    const enforcementAlerts = casesData.filter(c => c.enforcement_non_compliant).length;

    const setCount = (id, value) => {
        const element = document.getElementById(id);
        if (element) element.textContent = String(value);
    };
    setCount("stat-total-cases", total);
    setCount("stat-high-risk", highRisk);
    setCount("alert-count-custody", custodyAlerts);
    setCount("alert-count-missing", missingFiles);
    setCount("alert-count-enforcement", enforcementAlerts);

    const alertHub = document.getElementById("quick-alert-bar");
    if (alertHub) alertHub.classList.toggle("hidden", custodyAlerts + missingFiles + enforcementAlerts === 0);
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
        const missingFile = isFileMissingRecord(c);
        let ledClass = "led-green";
        if (c.risk_flag || missingFile) {
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

        // Keep distinct alerts visible even when one case has several at once.
        const alertBadges = [];
        if (missingFile) {
            alertBadges.push(`<span class="badge badge-high"><i class="fa-solid fa-folder-minus mr-1"></i> File Missing</span>`);
        }
        if (c.custody_alert) {
            alertBadges.push(`<span class="badge badge-high"><i class="fa-solid fa-triangle-exclamation mr-1"></i> Registry Idle</span>`);
        }
        if (c.enforcement_non_compliant) {
            alertBadges.push(`<span class="badge badge-mod"><i class="fa-solid fa-scale-unbalanced mr-1"></i> Execution Review Prompt</span>`);
        }
        if (alertBadges.length === 0 && c.judgment_status === "Executed") {
            alertBadges.push(`<span class="badge badge-low">Enforced</span>`);
        }
        const alertBadge = alertBadges.length
            ? `<div class="flex flex-wrap items-center justify-center gap-1">${alertBadges.join("")}</div>`
            : `<span style="color:var(--text-muted); font-weight:600">-</span>`;

        const activeUser = getActiveUser();
        const canRecordCustody = ["Sheriff", "Clerk", "Chief Registrar"].includes(activeUser.role);
        const canLogHearing = ["Clerk", "Judge", "Chief Registrar"].includes(activeUser.role);
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
                    ${canLogHearing ? `<button data-case-action="hearing" data-record-id="${c.case_id}" class="btn-secondary" style="padding:2px 8px;font-size:10px;" title="Log a hearing outcome"><i class="fa-solid fa-gavel mr-1"></i> Hearing</button>` : ''}
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
        const canCompileWrit = ["Sheriff", "Chief Registrar"].includes(getActiveUser().role);

        if (judgments.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="6" class="text-center py-8" style="color:var(--text-muted)">No delivered judgments currently meet the prototype execution review trigger.</td></tr>`;
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

            let statusBadge = `<span class="badge badge-low font-semibold">No Review Prompt</span>`;
            if (c.enforcement_non_compliant) {
                statusBadge = `<span class="badge badge-high badge-pulse font-bold"><i class="fa-solid fa-clock mr-1"></i> Review Prompt (90d+)</span>`;
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
                    ${canCompileWrit ? `<button type="button" data-case-action="writ" data-record-id="${c.case_id}" class="btn-secondary">Open writ workflow</button>` : `<span class="text-xs text-muted-th">View only</span>`}
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
    container.replaceChildren();
    if (!whatsappLogs.length) {
        const empty = document.createElement("div");
        empty.className = "text-center py-10 text-xs";
        empty.style.color = "var(--text-muted)";
        empty.textContent = "No WhatsApp activity has been recorded.";
        container.appendChild(empty);
        return;
    }

    whatsappLogs.forEach(log => {
        const card = document.createElement("div");
        card.className = "glass-panel rounded-xl p-4 space-y-2";
        const timestamp = log.created_at || log.received_at || "";
        const dateFormatted = timestamp ? new Date(timestamp).toLocaleString() : "Time unavailable";
        const recipient = log.recipient_masked || "recipient not recorded";
        const status = log.status || "unknown";
        const caseId = log.case_id || "No case reference";
        const role = log.recipient_role || "";
        const trigger = log.trigger_type || "notification";
        const template = log.template_name || "";
        const providerId = log.provider_message_id || "";
        const error = [log.error_code, log.error_message].filter(Boolean).join(": ");
        card.innerHTML = `
            <div class="flex flex-wrap items-center justify-between gap-2 text-xs pb-2" style="border-bottom:1px solid var(--border-color)">
                <span class="font-mono font-semibold text-accent"><i class="fa-brands fa-whatsapp text-emerald-th mr-1.5"></i> ${escapeHTML(recipient)}</span>
                <span class="font-medium" style="color:var(--text-muted)">${escapeHTML(dateFormatted)}</span>
                <span class="badge badge-low">${escapeHTML(status)}</span>
            </div>
            <div class="text-xs text-body">${escapeHTML(caseId)}${role ? ` · ${escapeHTML(role)}` : ""} · ${escapeHTML(trigger)}</div>
            ${template ? `<div class="text-[11px] text-body">Template: ${escapeHTML(template)} · Generic notice only; message content is not stored.</div>` : ""}
            ${providerId ? `<div class="text-[10px] font-mono text-body">Provider message ID: ${escapeHTML(providerId)}</div>` : ""}
            ${error ? `<div class="text-[11px] text-rose">${escapeHTML(error)}</div>` : ""}
        `;
        container.appendChild(card);
    });
}

function populateDropdowns() {
    const scanSelect = document.getElementById("scan-case-id");
    const hearingSelect = document.getElementById("hearing-case-id");
    const missingSelect = document.getElementById("missing-case-id");
    const foundSelect = document.getElementById("found-case-id");
    const missingHistorySelect = document.getElementById("missing-history-case-id");

    if (!scanSelect || !hearingSelect) return;

    const prevScanVal = scanSelect.value;
    const prevHearingVal = hearingSelect.value;
    const prevMissingVal = missingSelect ? missingSelect.value : "";
    const prevFoundVal = foundSelect ? foundSelect.value : "";
    const prevHistoryVal = missingHistorySelect ? missingHistorySelect.value : "";

    scanSelect.innerHTML = "";
    hearingSelect.innerHTML = "";
    if (missingSelect) missingSelect.innerHTML = "";
    if (foundSelect) {
        foundSelect.replaceChildren(new Option("Select an open missing report", ""));
    }
    if (missingHistorySelect) {
        missingHistorySelect.replaceChildren(new Option("Choose case", ""));
    }

    const sortedCases = [...casesData].sort((a, b) => a.case_id.localeCompare(b.case_id));
    sortedCases.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.case_id;
        opt.textContent = `${c.case_id} [${c.case_type} - ${c.court}]`;

        scanSelect.appendChild(opt.cloneNode(true));
        if (missingSelect) missingSelect.appendChild(opt.cloneNode(true));
        if (missingHistorySelect) missingHistorySelect.appendChild(opt.cloneNode(true));
        if (foundSelect && isFileMissingRecord(c)) foundSelect.appendChild(opt.cloneNode(true));
        if (c.judgment_status !== "Executed") hearingSelect.appendChild(opt.cloneNode(true));
    });

    if (prevScanVal && sortedCases.some(c => c.case_id === prevScanVal)) scanSelect.value = prevScanVal;
    if (prevHearingVal && sortedCases.some(c => c.case_id === prevHearingVal && c.judgment_status !== "Executed")) {
        hearingSelect.value = prevHearingVal;
    }
    if (missingSelect && prevMissingVal && sortedCases.some(c => c.case_id === prevMissingVal)) missingSelect.value = prevMissingVal;
    if (foundSelect && prevFoundVal && sortedCases.some(c => c.case_id === prevFoundVal && isFileMissingRecord(c))) {
        foundSelect.value = prevFoundVal;
    }
    if (missingHistorySelect && prevHistoryVal && sortedCases.some(c => c.case_id === prevHistoryVal)) {
        missingHistorySelect.value = prevHistoryVal;
    }

    updateQRDisplay();
    populateWhatsAppTestCases();
    renderFileMissingHistory();
}

function renderFileMissingHistory() {
    const selector = document.getElementById("missing-history-case-id");
    const container = document.getElementById("missing-file-history");
    if (!container) return;
    container.replaceChildren();

    const caseId = selector?.value || "";
    const record = casesData.find(item => item.case_id === caseId);
    if (!record) {
        const empty = document.createElement("p");
        empty.className = "text-body";
        empty.textContent = "Select a case to view its missing/found history.";
        container.appendChild(empty);
        return;
    }

    const history = Array.isArray(record.file_missing_history) ? [...record.file_missing_history] : [];
    const report = record.file_missing_report || {};
    if (report.reported_at && !history.some(event => event.action === "reported_missing")) {
        history.push({
            action: "reported_missing",
            actor_user_id: report.reported_by,
            timestamp: report.reported_at,
            last_known_location: report.last_known_location,
            notes: report.notes,
        });
    }
    if (report.resolved && report.resolved_at && !history.some(event => event.action === "found")) {
        history.push({
            action: "found",
            actor_user_id: report.resolved_by,
            timestamp: report.resolved_at,
            found_location: report.found_location,
            reason: report.resolution_reason,
        });
    }
    history.reverse();
    if (!history.length) {
        const empty = document.createElement("p");
        empty.className = "text-body";
        empty.textContent = "No missing/found events recorded for this case.";
        container.appendChild(empty);
        return;
    }

    history.forEach(event => {
        const item = document.createElement("div");
        item.className = "file-missing-history-item";
        const title = document.createElement("strong");
        title.textContent = event.action === "found" ? "File found / recovery recorded" : "File reported missing";
        const timestamp = new Date(event.timestamp || "");
        const time = document.createElement("span");
        time.textContent = Number.isNaN(timestamp.getTime()) ? "Time unavailable" : timestamp.toLocaleString();
        const actor = document.createElement("p");
        actor.textContent = `Recorded actor: ${event.actor_user_id || "Unknown"}`;
        const location = document.createElement("p");
        location.textContent = event.action === "found"
            ? `Found location: ${event.found_location || "Not recorded"}`
            : `Last known location: ${event.last_known_location || "Not recorded"}`;
        item.append(title, time, actor, location);
        const reasonText = event.action === "found" ? event.reason : event.notes;
        if (reasonText) {
            const reason = document.createElement("p");
            reason.textContent = event.action === "found" ? `Resolution reason: ${reasonText}` : `Notes: ${reasonText}`;
            item.appendChild(reason);
        }
        container.appendChild(item);
    });
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
    const submitButton = document.getElementById("btn-create-case");

    if (!case_id) return;
    if (submitButton) {
        submitButton.disabled = true;
        submitButton.dataset.originalLabel = submitButton.innerHTML;
        submitButton.innerHTML = '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Registering…';
    }
    logger(`Creating case ${case_id}...`);

    try {
        const response = await apiFetch(`${API_BASE}/cases`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ case_id, case_type, court, counsel_phone, litigant_phone })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            showToast(`Case was not registered: ${err.detail || "The server rejected the request."}`, "error");
            return;
        }

        document.getElementById("form-create-case").reset();
        syncCaseRegistrationDefaults(getActiveUser());
        await loadDashboardData();
        switchTab("tab-overview");
        showToast(`Case ${case_id} was registered by CourtLOG and is now in your worklist.`, "success");
    } catch (error) {
        logger(`Error creating case: ${error}`);
        showToast("Connection error. The case was not confirmed; check the worklist before retrying.", "error");
    } finally {
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.innerHTML = submitButton.dataset.originalLabel || '<i class="fa-solid fa-folder-plus" aria-hidden="true"></i> Register case';
            delete submitButton.dataset.originalLabel;
        }
    }
}

function setCustodyCheckinStatus(message, state = "info") {
    const status = document.getElementById("scan-checkin-status");
    if (status) {
        status.textContent = message;
        status.dataset.state = state;
    }
}

async function submitCustodyScan(endpoint, body, expectedLocation) {
    if (navigator.onLine === false) {
        const message = "Not submitted: this device is offline. CourtLOG does not queue scans; reconnect and scan again.";
        setCustodyCheckinStatus(message, "error");
        showToast(message, "error");
        return false;
    }

    setCustodyCheckinStatus("Submitting to CourtLOG… no check-in is confirmed yet.", "pending");
    try {
        const response = await apiFetch(`${API_BASE}${endpoint}`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            const errorBody = await response.json().catch(() => ({}));
            const detail = errorBody.detail || "CourtLOG did not authorize or confirm this check-in.";
            const message = `Not confirmed by CourtLOG: ${detail} Check custody history before retrying.`;
            setCustodyCheckinStatus(message, "error");
            showToast(message, "error");
            return false;
        }

        const savedCase = await response.json();
        const events = Array.isArray(savedCase?.scan_events) ? savedCase.scan_events : [];
        const latest = events[events.length - 1];
        if (!latest || latest.staff_id !== authenticatedUser?.user_id || latest.location !== expectedLocation) {
            const message = "No matching server confirmation was returned. Do not assume the check-in succeeded; verify custody history before retrying.";
            setCustodyCheckinStatus(message, "error");
            showToast(message, "error");
            return false;
        }

        setCustodyCheckinStatus("Check-in confirmed by CourtLOG for the signed-in account.", "success");
        showToast("Custody check-in confirmed by CourtLOG.", "success");
        await loadDashboardData();
        const caseSelect = document.getElementById("scan-case-id");
        if (caseSelect && savedCase.case_id && Array.from(caseSelect.options).some(option => option.value === savedCase.case_id)) {
            caseSelect.value = savedCase.case_id;
        }
        updateQRDisplay();
        return true;
    } catch (_) {
        const message = "No server confirmation received. Do not assume this check-in succeeded; check custody history before retrying. Offline scans are not queued.";
        setCustodyCheckinStatus(message, "error");
        showToast(message, "error");
        return false;
    }
}

async function handleScanSubmit(e) {
    e.preventDefault();
    const case_id = document.getElementById("scan-case-id").value;
    const location = document.getElementById("scan-location").value;
    if (!case_id) {
        showToast("Please select a case file.", "error");
        setCustodyCheckinStatus("No check-in submitted. Select an authorised case file first.", "error");
        return false;
    }
    return submitCustodyScan("/scan", { case_id, location }, location);
}

async function handleQrTokenSubmit(e) {
    e.preventDefault();
    const input = document.getElementById("qr-payload-input");
    const qr_payload = String(input?.value || "").trim();
    const location = document.getElementById("scan-location").value;
    if (input) input.value = "";
    if (!qr_payload) {
        setCustodyCheckinStatus("No QR token received. Nothing was submitted.", "error");
        return false;
    }
    return submitCustodyScan("/scan/qr", { qr_payload, location }, location);
}

async function handleQrPayloadFromCamera(payload) {
    const qr_payload = String(payload || "").trim();
    if (!qr_payload) {
        setCustodyCheckinStatus("The camera did not return a QR payload. No scan was submitted.", "error");
        return false;
    }
    const location = document.getElementById("scan-location").value;
    return submitCustodyScan("/scan/qr", { qr_payload, location }, location);
}

function startQrCamera() {
    if (authenticatedUser?.role !== "Sheriff") {
        setCustodyCheckinStatus("Camera check-in requires a signed-in Sheriff account.", "error");
        return false;
    }
    return window.CourtLogPwa?.startCamera();
}

function stopQrCamera() {
    window.CourtLogPwa?.stopCamera();
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
            alert(`Hearing was not recorded. ${err.detail || "The request could not be completed."}`);
            await loadDashboardData();
            return;
        }

        await loadDashboardData();
        showToast(`Hearing outcome recorded for case ${case_id}. Messaging, if configured, is handled separately.`, "success");
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
        tableBody.innerHTML = `<tr><td colspan="6" class="text-center py-8" style="color:var(--text-muted)">No cases currently meet the configured application review trigger.</td></tr>`;
        return;
    }

    dcrCases.map(safeRecord).forEach(c => {
        const reviewPending = c.dcr_approval_required === true;
        let status = reviewPending
            ? `<span class="badge ${c.dcr_auto_escalated ? 'badge-high' : 'badge-mod'} font-semibold">${c.dcr_auto_escalated ? 'In-app escalation recorded' : 'Review pending'}</span>`
            : `<span class="badge badge-low font-semibold">Trigger reached; no request pending</span>`;
        if (reviewPending && c.dcr_acknowledged_at) {
            status += `<div class="mt-1 text-[10px] text-body">Acknowledged by ${c.dcr_acknowledged_by || 'reviewer'} at ${c.dcr_acknowledged_at}; approval remains pending.</div>`;
        } else if (reviewPending) {
            status += `<div class="mt-1 text-[10px] text-body">Awaiting acknowledgement. This case remains blocked.</div>`;
        } else {
            status += `<div class="mt-1 text-[10px] text-body">No DCR review request has been recorded.</div>`;
        }
        if (reviewPending && c.dcr_auto_escalated && c.dcr_escalated_at) {
            status += `<div class="mt-1 text-[10px] text-body">Recorded ${c.dcr_escalated_at}; no external notice sent.</div>`;
        }

        const actionButtons = reviewPending
            ? `<div class="flex flex-col items-end gap-1">
                <button data-case-action="acknowledgeDCR" data-record-id="${c.case_id}" class="btn-secondary text-xs py-1 px-3">${c.dcr_acknowledged_at ? 'Update acknowledgement' : 'Acknowledge'}</button>
                <button data-case-action="override" data-record-id="${c.case_id}" class="btn-primary bg-amber-600 hover:bg-amber-700 text-xs py-1 px-3"><i class="fa-solid fa-shield-halved mr-1"></i> Record decision</button>
            </div>`
            : `<span class="text-xs text-body">No action pending</span>`;

        const row = document.createElement("tr");
        row.innerHTML = `
            <td class="py-3 px-4 font-mono font-bold text-heading">${c.case_id}</td>
            <td class="py-3 px-4">${c.case_type} (${c.assigned_division || 'Criminal'})</td>
            <td class="py-3 px-4">${c.court}</td>
            <td class="py-3 px-4 text-center font-bold text-heading">${c.adjournment_count}</td>
            <td class="py-3 px-4 text-center">${status}</td>
            <td class="py-3 px-4 text-right">${actionButtons}</td>
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
    const caseId = activeOverrideCaseId;
    const reason = document.getElementById("dcr-override-reason-input").value.trim();
    if (!reason) {
        showToast("Please enter the decision reason.", "error");
        return;
    }

    try {
        const response = await apiFetch(`${API_BASE}/cases/${caseId}/dcr-override`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ exceptional_reason: reason })
        });

        if (!response.ok) {
            const err = await response.json();
            showToast(`Failed to record review decision: ${err.detail || 'Permission denied'}`, "error");
            return;
        }

        closeDCROverrideModal();
        await loadDashboardData();
        showToast(`Decision recorded for case ${caseId}; review request closed.`, "success");
    } catch (error) {
        logger(`DCR review decision error: ${error}`);
        showToast("Network error while recording the DCR review decision.", "error");
    }
}

async function acknowledgeDCRReview(caseId) {
    const note = prompt(`Add a short acknowledgement note for the pending review on ${caseId}:`);
    if (!note || !note.trim()) return;

    try {
        const response = await apiFetch(`${API_BASE}/cases/${caseId}/dcr-acknowledge`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ note: note.trim() })
        });
        if (!response.ok) {
            const err = await response.json();
            showToast(`Could not acknowledge review: ${err.detail || 'Permission denied'}`, "error");
            return;
        }
        await loadDashboardData();
        showToast(`Acknowledgement recorded for ${caseId}; approval is still pending.`, "success");
    } catch (error) {
        logger(`DCR acknowledgement error: ${error}`);
        showToast("Network error while recording the acknowledgement.", "error");
    }
}

// ----------------- JUDGE DOCKET CONSOLE -----------------

function renderJudgeDocketTable() {
    const tableBody = document.getElementById("judge-docket-table-body");
    if (!tableBody) return;
    tableBody.innerHTML = "";

    const user = getActiveUser();
    const judgeCases = casesData.filter(c => user.role === "Chief Registrar" || c.assigned_judge_id === user.user_id);

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

// ----------------- PROTOTYPE SUMMARY EXPORT -----------------

async function exportPrototypeSummary() {
    try {
        const response = await apiFetch(`${API_BASE}/export/prototype-summary`, {
            headers: getAuthHeaders()
        });

        if (!response.ok) {
            const err = await response.json();
            showToast(`Prototype summary export failed: ${err.detail || 'Permission denied'}`, "error");
            return;
        }

        const report = await response.json();
        document.getElementById("prototype-report-json-view").textContent = JSON.stringify(report, null, 2);
        animateOpenModal("prototype-summary-modal");
    } catch (error) {
        logger(`Prototype summary export error: ${error}`);
        showToast("Network error generating the prototype summary.", "error");
    }
}

function closePrototypeReportModal() {
    animateCloseModal("prototype-summary-modal");
}

function downloadPrototypeSummary() {
    const text = document.getElementById("prototype-report-json-view").textContent;
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `COURTLOG_Prototype_Summary_${new Date().toISOString().split('T')[0]}.json`;
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
}

// Update selected case reference and locally rendered custody history.
function updateQRDisplay() {
    const selector = document.getElementById("scan-case-id");
    const caseId = selector?.value || "";
    const selected = document.getElementById("qr-display-suit");
    if (selected) selected.textContent = caseId || "No case selected";

    const canvas = document.getElementById("qr-label-canvas");
    if (canvas?.dataset.caseId && canvas.dataset.caseId !== caseId) {
        canvas.width = canvas.width;
        canvas.height = canvas.height;
        delete canvas.dataset.caseId;
        const printButton = document.getElementById("btn-print-qr-label");
        if (printButton) printButton.disabled = true;
        const status = document.getElementById("qr-label-status");
        if (status) status.textContent = "Selection changed. Generate a new label before printing.";
    }

    const targetCase = casesData.find(c => c.case_id === caseId);
    const logsContainer = document.getElementById("case-scan-history");
    if (!logsContainer) return;
    logsContainer.replaceChildren();

    if (targetCase && Array.isArray(targetCase.scan_events) && targetCase.scan_events.length > 0) {
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
        const empty = document.createElement("div");
        empty.className = "text-center py-4";
        empty.style.color = "var(--text-muted)";
        empty.textContent = "No scan checkpoint logs recorded.";
        logsContainer.appendChild(empty);
    }
}

async function generateQrLabel() {
    const caseId = document.getElementById("scan-case-id")?.value || "";
    const role = authenticatedUser?.role;
    if (!["Clerk", "Chief Registrar"].includes(role)) {
        showToast("QR labels can only be issued by registry staff.", "error");
        return false;
    }
    if (!caseId) {
        showToast("Select an authorised case before generating a label.", "error");
        return false;
    }
    if (!window.CourtLogPwa || !document.getElementById("qr-label-canvas")) {
        setCustodyCheckinStatus("Local QR generation is unavailable in this browser.", "error");
        return false;
    }

    const button = document.getElementById("btn-generate-qr-label");
    const status = document.getElementById("qr-label-status");
    if (button) button.disabled = true;
    if (status) status.textContent = "Requesting an opaque label token from CourtLOG…";
    try {
        const casePath = caseId.split("/").map(encodeURIComponent).join("/");
        const response = await apiFetch(`${API_BASE}/cases/${casePath}/qr-label`, {
            method: "POST",
            headers: getAuthHeaders()
        });
        if (!response.ok) {
            const errorBody = await response.json().catch(() => ({}));
            throw new Error(errorBody.detail || "CourtLOG could not issue this label.");
        }
        const result = await response.json();
        const canvas = document.getElementById("qr-label-canvas");
        await window.CourtLogPwa.renderQrLabel(result.qr_payload, canvas);
        canvas.dataset.caseId = caseId;
        const printButton = document.getElementById("btn-print-qr-label");
        if (printButton) printButton.disabled = false;
        if (status) status.textContent = "Opaque label ready. The QR was rendered on this device; the printed label contains no case details.";
        showToast("Opaque QR label generated locally.", "success");
        return true;
    } catch (error) {
        if (status) status.textContent = `Label not ready: ${error.message || "QR generation failed."}`;
        showToast(error.message || "QR label generation failed.", "error");
        return false;
    } finally {
        if (button) button.disabled = false;
    }
}

function printQrLabel() {
    const selectedCase = document.getElementById("scan-case-id")?.value || "";
    const canvas = document.getElementById("qr-label-canvas");
    if (!selectedCase || !canvas?.dataset.caseId || canvas.dataset.caseId !== selectedCase) {
        showToast("Generate a label for the currently selected case before printing.", "error");
        return false;
    }
    window.print();
    return true;
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
}

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
        + '<div class="hdr"><div><h2>COURTLOG</h2><div class="sub">Prototype Draft — Not Issued</div></div><div class="dt">' + dateStr + '</div></div>'
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
            matchStatus = c.custody_alert || isFileMissingRecord(c) || c.enforcement_non_compliant;
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
    if (statusSelect) statusSelect.value = "ALERTS";
    const riskSelect = document.getElementById("filter-risk");
    if (riskSelect) riskSelect.value = "ALL";
    const search = document.getElementById("global-search");
    if (search) search.value = "";

    // Filter specifically by alert type
    let filtered;
    if (type === 'custody') {
        filtered = casesData.filter(c => c.custody_alert === true);
    } else if (type === 'enforcement') {
        filtered = casesData.filter(c => c.enforcement_non_compliant === true);
    } else if (type === 'missing') {
        filtered = casesData.filter(isFileMissingRecord);
    } else {
        filtered = casesData.filter(c => c.custody_alert || isFileMissingRecord(c) || c.enforcement_non_compliant);
    }

    renderHeatmapTable(filtered);

    // The worklist is a content-card, not a glass-panel. Scroll to the actual section
    // so the filtered rows are visible after the dashboard's priority cards.
    const worklist = document.getElementById("cases-directory");
    const heading = document.getElementById("cases-heading");
    if (worklist) {
        const reduceMotion = typeof window.matchMedia === "function" &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        worklist.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
        heading?.focus({ preventScroll: true });
    }
}

// ----------------- BACKGROUND SYNC DRIVER (CRON SIM) -----------------

async function triggerCronCompliance() {
    logger("Triggering manual prototype workflow sweep...");
    const cronIcon = document.getElementById("cron-icon");
    const sweepButton = document.getElementById("btn-cron-sweep");

    if (cronIcon) cronIcon.classList.add("animate-spin");
    if (sweepButton) sweepButton.disabled = true;

    try {
        const response = await apiFetch(`${API_BASE}/cron`, { method: "POST", headers: getAuthHeaders() });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.detail || "Workflow sweep was not completed.");

        logger(`Workflow sweep complete. Idle custody prompts: ${result.stats.custody_alerts}; missing files: ${result.stats.missing_file_alerts}; 90-day execution review prompts: ${result.stats.execution_review_prompts}`);
        await loadDashboardData();
        showToast(`Prototype sweep complete: ${result.stats.custody_alerts} idle-custody prompts, ${result.stats.missing_file_alerts} open missing-file reports, and ${result.stats.execution_review_prompts} execution review prompts.`, "success");
    } catch (error) {
        logger(`Error running workflow sweep: ${error}`);
        showToast(error.message || "Workflow sweep failed. No completion was confirmed.", "error");
    } finally {
        if (cronIcon) cronIcon.classList.remove("animate-spin");
        if (sweepButton) sweepButton.disabled = false;
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

    const casePath = caseId.split("/").map(encodeURIComponent).join("/");
    let response;
    try {
        response = await apiFetch(`${API_BASE}/cases/${casePath}/report-missing`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ last_known_location: location, notes: notes })
        });
    } catch (_) {
        showToast("Network error reporting missing file.", "error");
        return;
    }
    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        showToast(errorBody.detail || "Failed to report missing file.", "error");
        return;
    }

    showToast(`Case ${caseId} marked missing. The alert remains open until recovery is recorded.`, "success");
    document.getElementById("form-report-missing").reset();
    try {
        await loadDashboardData();
        const historySelect = document.getElementById("missing-history-case-id");
        if (historySelect && Array.from(historySelect.options).some(option => option.value === caseId)) {
            historySelect.value = caseId;
        }
        renderFileMissingHistory();
    } catch (_) {
        showToast("Missing-file report was recorded, but the dashboard refresh failed. Reload to verify.", "warning");
    }
}

async function handleFileFoundSubmit(e) {
    e.preventDefault();
    const caseId = document.getElementById("found-case-id").value;
    const foundLocation = document.getElementById("found-location").value.trim();
    const reason = document.getElementById("found-reason").value.trim();
    if (!caseId) {
        showToast("Select an open missing-file report first.", "error");
        return;
    }

    const casePath = caseId.split("/").map(encodeURIComponent).join("/");
    let response;
    try {
        response = await apiFetch(`${API_BASE}/cases/${casePath}/found`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: JSON.stringify({ found_location: foundLocation, reason })
        });
    } catch (_) {
        showToast("No server confirmation received. Verify the missing-file history before retrying.", "error");
        return;
    }
    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        showToast(errorBody.detail || "File recovery was not recorded.", "error");
        return;
    }

    showToast(`Case ${caseId} file found; missing alert resolved by CourtLOG.`, "success");
    document.getElementById("form-file-found").reset();
    try {
        await loadDashboardData();
        const historySelect = document.getElementById("missing-history-case-id");
        if (historySelect && Array.from(historySelect.options).some(option => option.value === caseId)) {
            historySelect.value = caseId;
        }
        renderFileMissingHistory();
    } catch (_) {
        showToast("Recovery was recorded, but the dashboard refresh failed. Reload to verify current status.", "warning");
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
            document.getElementById("prototype-report-json-view").textContent = JSON.stringify(data, null, 2);
            animateOpenModal("prototype-summary-modal");
            // Reuse the prototype summary modal for the weekly workflow summary
        } else {
            const err = await response.json();
            showToast(err.detail || "Failed to generate report.", "error");
        }
    } catch (error) {
        showToast("Network error generating weekly report.", "error");
    }
}

async function fetchJudgeAlerts() {
    const banner = document.getElementById("judge-alert-banner");
    const list = document.getElementById("judge-alert-list");
    const count = document.getElementById("judge-alert-count");
    if (!banner || !list || !count) return;

    try {
        const response = await apiFetch(`${API_BASE}/judge/alerts`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const alerts = Array.isArray(data.alerts) ? data.alerts : [];
        const labels = {
            HEARING_24HR: "Upcoming hearing",
            ADJOURNMENT_REVIEW: "Adjournment review prompt",
            EXPERIMENTAL_DELAY_RISK: "Experimental delay-risk indicator",
            FILE_MISSING: "Physical file alert",
        };
        list.replaceChildren();
        count.textContent = String(alerts.length);
        banner.classList.toggle("hidden", alerts.length === 0);

        alerts.forEach(alert => {
            const item = document.createElement("div");
            item.className = "rounded-lg border border-color bg-input p-3";
            const title = document.createElement("p");
            title.className = "font-semibold text-heading";
            title.textContent = labels[alert.type] || "Docket prompt";
            const detail = document.createElement("p");
            detail.className = "mt-1 text-xs text-body";
            detail.textContent = `${alert.case_id || "Case"}: ${alert.message || "Review current case information."}`;
            item.append(title, detail);
            list.appendChild(item);
        });
    } catch (error) {
        list.replaceChildren();
        const status = document.createElement("p");
        status.className = "text-xs text-body";
        status.textContent = "Operational alerts could not be loaded. Refresh the docket or contact the registry administrator.";
        list.appendChild(status);
        count.textContent = "—";
        banner.classList.remove("hidden");
        logger(`Failed to fetch judge alerts: ${error}`);
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
        showToast(`Experimental delay-risk scores recalculated for ${aiRiskData.length} scoped cases`, 'success');
    } catch (error) {
        logger(`Experimental delay-risk load error: ${error}`);
        showToast('Failed to load experimental delay-risk scores', 'error');
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
    const pct = (Number(c.delay_risk_score || 0) * 100).toFixed(1);
    const sourceLabels = {
        trained_pipeline: "Trained preprocessing pipeline",
        legacy_model: "Legacy model and encoder artifact",
        heuristic: "Deterministic heuristic fallback (no model loaded)",
        heuristic_after_model_error: "Heuristic fallback after model inference error"
    };
    const source = sourceLabels[c.prediction_source] || "Source not recorded for this older score";
    const msg = `═══ EXPERIMENTAL DELAY-RISK SCORE ═══\n\nCase: ${c.case_id}\nPrototype score: ${pct}%\nEstimate source: ${source}\nStatus: ${c.judgment_status}\n\n── Inputs used ──\nCase type: ${c.case_type}\nCourt: ${c.court}\nRecorded case-level adjournments: ${c.adjournment_count}\nDays since filing: ${c.days_since_filing}\n\nThis is a feature summary, not a causal or model-attribution explanation. Training rows and labels are synthetic and rule-generated; the score has not been independently validated against real court outcomes.\n\nThe 70% display threshold is experimental only. This score is not a legal finding and must not determine a hearing, custody, enforcement, or judicial decision.`;
    alert(msg);
}
