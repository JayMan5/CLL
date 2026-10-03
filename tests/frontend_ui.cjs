// Run via npm run test:frontend. Covers shell navigation, role-aware UI, and dashboard alerts.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync('frontend/index.html', 'utf8');
const css = fs.readFileSync('frontend/index.css', 'utf8');
assert.match(html, /href="#main-content">Skip to main content/);
assert.match(css, /\.login-input\.th-input\s*\{\s*padding:\s*0\.625rem\s+0\.75rem\s+0\.625rem\s+2\.5rem;/, 'login input padding leaves a clear icon gutter');
assert.doesNotMatch(html, /id="role-switcher-select"/, 'the shell does not imply users can switch roles');
assert.match(html, /browser controls the native confirmation/);
assert.match(html, /COURTLOG Sheriff Custody Check-In/);
assert.match(html, /id="pwa-install-status" class="install-status"/);
const pwaSource = fs.readFileSync('frontend/c2-pwa.js', 'utf8');
assert.match(pwaSource, /beforeinstallprompt/);
assert.match(pwaSource, /installButton\.addEventListener\("click"/);
assert.equal((html.match(/id="pwa-install-status"/g) || []).length, 1, 'there is one global install status region');

function response(status, body = {}) {
    return {
        status, ok: status >= 200 && status < 300,
        headers: { get: () => null },
        json: async () => body,
        clone() { return this; }
    };
}

const dom = new JSDOM(html, {
    url: 'https://courtlog.test/', runScripts: 'outside-only', pretendToBeVisual: true
});
dom.window.Headers = global.Headers;
dom.window.CourtLogPwa = { initialize() {}, setRole() {}, setScanHandler() {}, stopCamera() {} };
dom.window.fetch = async url => {
    if (url === '/api/config') return response(200, { demo_mode: false });
    if (url === '/api/refresh') return response(401, { detail: 'No session' });
    return response(200, {});
};

(async () => {
    const context = dom.getInternalVMContext();
    const ready = new Promise(resolve => dom.window.document.addEventListener('DOMContentLoaded', () => setTimeout(resolve, 0), { once: true }));
    new vm.Script(fs.readFileSync('frontend/app.js', 'utf8')).runInContext(context);
    await ready;
    const doc = dom.window.document;
    const run = code => vm.runInContext(code, context);

    for (const id of ['login-username', 'login-password']) {
        assert.ok(doc.getElementById(id).classList.contains('login-input'), `${id} reserves space for its leading icon`);
    }
    assert.equal(doc.getElementById('profile-menu-toggle').getAttribute('aria-expanded'), 'false');
    assert.ok(doc.querySelectorAll('[data-nav-group]').length >= 3);
    assert.equal(doc.getElementById('tab-case-register').classList.contains('hidden'), true);

    run(`authenticatedUser = ${JSON.stringify({
        user_id: 'clerk-ui-test', username: 'clerk', name: 'Registry Clerk', role: 'Clerk',
        badge: 'Registry Staff', court: 'FHC Abuja Court 4', division: 'Criminal', must_change_password: false
    })}; currentUserId = authenticatedUser.user_id; updateRoleUI()`);
    assert.equal(doc.getElementById('sidebar-user-role').textContent, 'Clerk');
    assert.equal(doc.getElementById('active-user-scope').textContent, 'FHC Abuja Court 4 · Criminal division');
    assert.equal(doc.getElementById('nav-case-register').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('btn-register-case').hidden, false);
    assert.equal(doc.getElementById('nav-courtrooms').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('nav-execution').classList.contains('hidden'), true);
    assert.equal(doc.getElementById('nav-whatsapp').classList.contains('hidden'), true);

    run('switchTab("tab-case-register")');
    assert.equal(doc.getElementById('tab-case-register').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('nav-case-register').getAttribute('aria-current'), 'page');
    assert.equal(doc.getElementById('view-title').textContent, 'Register a case');

    run('authenticatedUser.role = "Sheriff"; updateRoleUI()');
    assert.equal(doc.getElementById('nav-case-register').classList.contains('hidden'), true);
    assert.equal(doc.getElementById('nav-courtrooms').classList.contains('hidden'), true);
    assert.equal(doc.getElementById('nav-execution').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('btn-register-case').hidden, true);
    assert.equal(doc.getElementById('tab-overview').classList.contains('hidden'), false, 'role changes redirect away from an unavailable page');
    run('switchTab("tab-user-admin")');
    assert.equal(doc.getElementById('tab-user-admin').classList.contains('hidden'), true, 'direct tab navigation cannot reveal Chief Registrar screens');

    run('authenticatedUser.role = "Judge"; updateRoleUI()');
    assert.equal(doc.getElementById('nav-judge-docket').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('nav-courtrooms').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('nav-execution').classList.contains('hidden'), true);
    run('authenticatedUser.role = "DCR"; updateRoleUI()');
    assert.equal(doc.getElementById('nav-dcr-console').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('nav-courtrooms').classList.contains('hidden'), true);
    run('authenticatedUser.role = "Chief Registrar"; updateRoleUI()');
    assert.equal(doc.getElementById('nav-user-admin').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('nav-whatsapp').classList.contains('hidden'), false);

    const profileToggle = doc.getElementById('profile-menu-toggle');
    profileToggle.click();
    assert.equal(profileToggle.getAttribute('aria-expanded'), 'true');
    assert.equal(doc.getElementById('profile-menu').classList.contains('hidden'), false);
    doc.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    assert.equal(profileToggle.getAttribute('aria-expanded'), 'false');
    assert.equal(doc.getElementById('profile-menu').classList.contains('hidden'), true);

    const navToggle = doc.getElementById('mobile-nav-toggle');
    navToggle.click();
    assert.equal(navToggle.getAttribute('aria-expanded'), 'true');
    assert.equal(doc.body.classList.contains('nav-open'), true);
    assert.equal(doc.getElementById('nav-backdrop').classList.contains('hidden'), false);
    const visibleNavItems = [...doc.querySelectorAll('#sidebar-nav-container .nav-item:not(.hidden)')];
    assert.equal(doc.activeElement, visibleNavItems[0], 'opening the drawer moves focus to navigation');
    visibleNavItems.at(-1).focus();
    doc.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    assert.equal(doc.activeElement, visibleNavItems[0], 'drawer tab order remains contained while open');
    doc.getElementById('nav-backdrop').click();
    assert.equal(navToggle.getAttribute('aria-expanded'), 'false');
    assert.equal(doc.body.classList.contains('nav-open'), false);

    run(`casesData = [
        { case_id: 'FICTIONAL/1', risk_flag: true, custody_alert: true, file_missing: false, enforcement_non_compliant: false },
        { case_id: 'FICTIONAL/2', risk_flag: false, custody_alert: false, file_missing: true, enforcement_non_compliant: true }
    ]; renderOverviewMetrics()`);
    assert.equal(doc.getElementById('stat-total-cases').textContent, '2');
    assert.equal(doc.getElementById('stat-high-risk').textContent, '1');
    assert.equal(doc.getElementById('alert-count-custody').textContent, '1');
    assert.equal(doc.getElementById('alert-count-missing').textContent, '1');
    assert.equal(doc.getElementById('alert-count-enforcement').textContent, '1');
    assert.equal(doc.getElementById('quick-alert-bar').classList.contains('hidden'), false);
    run('casesData = []; renderOverviewMetrics()');
    assert.equal(doc.getElementById('quick-alert-bar').classList.contains('hidden'), true);

    console.log('Frontend UI: role-aware navigation, accessible menus, dashboard hierarchy, and alert counts passed');
    dom.window.close();
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
    dom.window.close();
});
