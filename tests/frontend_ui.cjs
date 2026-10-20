// Run via npm run test:frontend. Covers shell navigation, role-aware UI, and dashboard alerts.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync('frontend/index.html', 'utf8');
const css = fs.readFileSync('frontend/index.css', 'utf8');
assert.match(html, /href="#main-content">Skip to main content/);
assert.match(css, /#form-login #login-username,\s*#form-login #login-password\s*\{\s*padding:\s*0\.625rem\s+0\.75rem\s+0\.625rem\s+2\.75rem\s*!important;/, 'login input padding overrides utility classes and leaves a clear icon gutter');
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
    if (url === '/api/config') return response(200, {
        demo_mode: false, synthetic_duration_demo_available: false, paid_features: { court_clerk: false }
    });
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
    const durationDemoPanel = doc.getElementById('synthetic-duration-demo-panel');
    assert.ok(durationDemoPanel, 'the synthetic duration demo panel exists in the risk workspace');
    assert.equal(durationDemoPanel.classList.contains('hidden'), true, 'the panel stays hidden without a demo artifact');
    assert.equal(doc.querySelector('#synthetic-duration-demo-form [name="case_id"]'), null,
        'the synthetic form cannot select or submit an application case');
    assert.deepEqual(Array.from(run('PILOT_ROLE_OPTIONS')), [
        'Chief Judge', 'Chief Registrar', 'Deputy Chief Registrar', 'Registrar',
        'Filing Clerk', 'Registry Clerk', 'Court Clerk', 'Bailiff', 'Sheriff', 'Presiding Judge'
    ]);
    for (const deferredRole of ['Cashier / Fees Clerk', 'Counsel', "Counsel's Clerk", 'Appellate Justice']) {
        assert.equal([...doc.getElementById('new-user-role').options].some(option => option.value === deferredRole), false);
    }

    for (const id of ['login-username', 'login-password']) {
        assert.ok(doc.getElementById(id).classList.contains('login-input'), `${id} reserves space for its leading icon`);
    }
    assert.equal(doc.getElementById('profile-menu-toggle').getAttribute('aria-expanded'), 'false');
    assert.ok(doc.querySelectorAll('[data-nav-group]').length >= 3);
    assert.equal(doc.getElementById('tab-case-register').classList.contains('hidden'), true);
    assert.equal(doc.getElementById('form-upload-doc').closest('details').classList.contains('hidden'), true);

    run(`authenticatedUser = ${JSON.stringify({
        user_id: 'clerk-ui-test', username: 'clerk', name: 'Pilot Filing Clerk', role: 'Filing Clerk',
        badge: 'Filing and case registration', court: 'FHC Abuja Court 4', division: 'Criminal', must_change_password: false
    })}; currentUserId = authenticatedUser.user_id; updateRoleUI()`);
    assert.equal(doc.getElementById('sidebar-user-role').textContent, 'Filing Clerk');
    assert.equal(doc.getElementById('active-user-scope').textContent, 'FHC Abuja Court 4 · Criminal division');
    assert.equal(doc.getElementById('nav-case-register').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('btn-register-case').hidden, false);
    assert.equal(doc.getElementById('form-upload-doc').closest('details').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('nav-courtrooms').classList.contains('hidden'), true);
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
    assert.equal(doc.getElementById('form-upload-doc').closest('details').classList.contains('hidden'), true);
    assert.equal(doc.getElementById('tab-overview').classList.contains('hidden'), false, 'role changes redirect away from an unavailable page');
    run('switchTab("tab-user-admin")');
    assert.equal(doc.getElementById('tab-user-admin').classList.contains('hidden'), true, 'direct tab navigation cannot reveal Chief Registrar screens');

    run('authenticatedUser.role = "Presiding Judge"; updateRoleUI()');
    assert.equal(doc.getElementById('nav-judge-docket').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('nav-courtrooms').classList.contains('hidden'), true);
    assert.equal(doc.getElementById('nav-execution').classList.contains('hidden'), true);
    run('authenticatedUser.role = "Deputy Chief Registrar"; updateRoleUI()');
    assert.equal(doc.getElementById('nav-dcr-console').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('nav-courtrooms').classList.contains('hidden'), true);
    run('authenticatedUser.role = "Chief Registrar"; updateRoleUI()');
    assert.equal(doc.getElementById('nav-user-admin').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('nav-whatsapp').classList.contains('hidden'), true);
    run('authenticatedUser.role = "Registrar"; updateRoleUI()');
    assert.equal(doc.getElementById('nav-user-admin').classList.contains('hidden'), true);
    assert.equal(doc.getElementById('nav-whatsapp').classList.contains('hidden'), false);
    run('authenticatedUser.role = "Registry Clerk"; updateRoleUI()');
    assert.equal(doc.getElementById('form-upload-doc').closest('details').classList.contains('hidden'), false);
    run('authenticatedUser.role = "Court Clerk"; updateRoleUI()');
    assert.equal(doc.getElementById('form-upload-doc').closest('details').classList.contains('hidden'), true);
    assert.equal(doc.getElementById('new-user-role').options[
        [...doc.getElementById('new-user-role').options].findIndex(option => option.value === 'Court Clerk')
    ].disabled, true, 'Court Clerk assignment stays disabled without entitlement');
    assert.equal(doc.getElementById('nav-courtrooms').classList.contains('hidden'), true);
    const courtClerkOption = doc.querySelector('#new-user-role option[value="Court Clerk"]');
    assert.equal(courtClerkOption.disabled, true);
    run('paidFeatures.court_clerk = true; updateCourtClerkEntitlementUI(); updateRoleUI()');
    assert.equal(courtClerkOption.disabled, false);
    assert.equal(doc.getElementById('nav-courtrooms').classList.contains('hidden'), false);
    run('paidFeatures.court_clerk = false; updateCourtClerkEntitlementUI(); updateRoleUI()');
    assert.equal(courtClerkOption.disabled, true);
    assert.equal(doc.getElementById('nav-courtrooms').classList.contains('hidden'), true);

    assert.ok(doc.getElementById('change-user-division-overlay'), 'the Chief Registrar division editor is available');
    assert.deepEqual(
        [...doc.getElementById('change-user-division-select').options].map(option => option.value),
        ['', 'Criminal', 'Civil'],
        'the division editor offers only a specific Criminal or Civil assignment, never All Divisions'
    );
    run(`currentUserId = 'cr-ui-test'; usersData = [{
        user_id: 'ui-filing-clerk', username: 'ui.filing', name: 'Fictional Filing Clerk',
        role: 'Filing Clerk', badge: 'Synthetic', court: 'FHC Abuja Court 4', division: 'Criminal'
    }]; renderUsersAdminTable()`);
    const divisionButton = doc.querySelector('#users-admin-table-body [data-case-action="changeUserDivision"]');
    assert.ok(divisionButton, 'division-scoped staff get a division management action');
    divisionButton.click();
    assert.equal(doc.getElementById('change-user-division-overlay').classList.contains('hidden'), false);
    assert.equal(doc.getElementById('change-user-division-current').textContent, 'Criminal');
    assert.equal(doc.getElementById('change-user-division-court').textContent, 'FHC Abuja Court 4');
    doc.getElementById('change-user-division-select').value = 'Civil';
    doc.getElementById('change-user-division-reason').value = 'Synthetic test transfer';
    run('syncChangeUserDivisionSubmit()');
    assert.equal(doc.getElementById('btn-change-user-division-submit').disabled, false);
    run('closeChangeUserDivisionModal()');
    run(`usersData = [{
        user_id: 'ui-registrar', username: 'ui.registrar', name: 'Fictional Registrar',
        role: 'Registrar', badge: 'Synthetic', court: 'FHC Abuja Court 4', division: 'All Divisions'
    }]; renderUsersAdminTable()`);
    assert.equal(doc.querySelector('#users-admin-table-body [data-case-action="changeUserDivision"]'), null,
        'court-wide roles do not display a misleading division control');
    run(`usersData = [{
        user_id: 'ui-court-clerk', username: 'ui.court.clerk', name: 'Fictional Court Clerk',
        role: 'Court Clerk', badge: 'Synthetic', court: 'FHC Abuja Court 4', division: 'Criminal'
    }]; renderUsersAdminTable()`);
    assert.equal(doc.querySelector('#users-admin-table-body [data-case-action="changeUserDivision"]'), null,
        'an unentitled Court Clerk stays unavailable in division management');

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

    const alertCases = [
        { case_id: 'FICTIONAL/CUSTODY', custody_alert: true, risk_flag: true },
        { case_id: 'FICTIONAL/EXECUTION', enforcement_non_compliant: true },
        { case_id: 'FICTIONAL/MISSING', file_missing: true },
        { case_id: 'FICTIONAL/CLEAR' }
    ].map(record => ({
        case_type: 'Criminal', court: 'FHC Abuja Court 4', adjournment_count: 1,
        days_since_filing: 7, delay_risk_score: 0.2, custody_alert: false,
        file_missing: false, enforcement_non_compliant: false, risk_flag: false,
        scan_events: [], ...record
    }));
    run(`casesData = ${JSON.stringify(alertCases)}; renderOverviewMetrics(); renderHeatmapTable(casesData)`);
    assert.equal(doc.getElementById('stat-total-cases').textContent, '4');
    assert.equal(doc.getElementById('stat-high-risk').textContent, '1');
    assert.equal(doc.getElementById('alert-count-custody').textContent, '1');
    assert.equal(doc.getElementById('alert-count-missing').textContent, '1');
    assert.equal(doc.getElementById('alert-count-enforcement').textContent, '1');
    assert.equal(doc.getElementById('quick-alert-bar').classList.contains('hidden'), false);

    const worklist = doc.getElementById('cases-directory');
    const scrollRequests = [];
    worklist.scrollIntoView = options => scrollRequests.push(options);
    const visibleCaseIds = () => [...doc.querySelectorAll('#cases-table-body > tr > td:first-child')]
        .map(cell => cell.textContent.trim());
    for (const [type, expectedCaseId] of [
        ['custody', 'FICTIONAL/CUSTODY'],
        ['enforcement', 'FICTIONAL/EXECUTION'],
        ['missing', 'FICTIONAL/MISSING']
    ]) {
        doc.querySelector(`[data-alert-filter="${type}"]`).click();
        assert.deepEqual(visibleCaseIds(), [expectedCaseId], `${type} review action shows only its related cases`);
        assert.equal(doc.getElementById('filter-status').value, 'ALERTS');
        assert.equal(doc.getElementById('filter-risk').value, 'ALL');
        assert.equal(doc.getElementById('global-search').value, '');
        assert.equal(doc.activeElement.id, 'cases-heading', `${type} review action moves keyboard focus to the worklist`);
    }
    assert.equal(scrollRequests.length, 3, 'each review action scrolls the worklist into view');
    assert.ok(scrollRequests.every(options => options.block === 'start'));

    run('casesData = []; renderOverviewMetrics()');
    assert.equal(doc.getElementById('quick-alert-bar').classList.contains('hidden'), true);

    run(`authenticatedUser = {
        user_id: 'duration-demo-dcr', username: 'demo.dcr', name: 'Fictional Demo DCR',
        role: 'Deputy Chief Registrar', court: 'Synthetic Court A', division: 'All Divisions'
    }; currentUserId = authenticatedUser.user_id; demoMode = true;
    syntheticDurationDemoAvailable = true; updateRoleUI(); updateSyntheticDurationDemoUI()`);
    assert.equal(durationDemoPanel.classList.contains('hidden'), false,
        'the duration form is shown only when demo mode and a validated artifact are enabled');
    const durationRecency = doc.getElementById('duration-demo-event-recency');
    durationRecency.value = '901';
    await run('submitSyntheticDurationDemo({ preventDefault() {} })');
    assert.match(doc.getElementById('duration-demo-result').textContent, /cannot exceed days since filing/);
    assert.equal(dom.window.__durationDemoRequest, undefined, 'invalid fictional feature combinations are rejected before the API call');

    durationRecency.value = '120';
    run(`apiFetch = async (url, options) => {
        window.__durationDemoRequest = { url, options };
        return { ok: true, status: 200, json: async () => ({ estimated_days_to_next_progress: 46.4 }) };
    }`);
    await run('submitSyntheticDurationDemo({ preventDefault() {} })');
    assert.equal(dom.window.__durationDemoRequest.url, '/api/predict/duration-demo');
    assert.deepEqual(JSON.parse(dom.window.__durationDemoRequest.options.body), {
        adjournment_count: 3,
        days_since_filing: 900,
        days_since_last_event: 120,
        case_type: 'Fictional Land Matter',
        court: 'Synthetic Court C'
    });
    assert.match(doc.getElementById('duration-demo-result').textContent, /Synthetic-only estimate: 46\.4 days/);
    assert.match(doc.getElementById('duration-demo-result').textContent, /real court outcome/);

    run(`aiRiskData = [{
        case_id: 'SYNTHETIC-DURATION-DEMO/2026/001',
        case_title: 'Fictional Duration Demo Matter 001',
        case_type: 'Fictional Civil Claim', court: 'FHC Abuja Court 4',
        adjournment_count: 2, days_since_filing: 120, delay_risk_score: 0.55,
        estimated_days_to_next_progress: 46.4,
        duration_prediction_source: 'synthetic_duration_demo_pipeline',
        judgment_status: 'Pending', prediction_source: 'heuristic'
    }]; renderAIRiskDashboard()`);
    const durationRow = doc.querySelector('#ai-risk-table-body tr');
    assert.match(doc.getElementById('ai-risk-table-heading').textContent, /New Synthetic Duration Demo Cases/);
    assert.equal(durationRow.cells[1].textContent, 'SYNTHETIC-DURATION-DEMO/2026/001');
    assert.equal(durationRow.cells[7].textContent, '46.4 days');

    run('aiRiskData = []; renderAIRiskDashboard()');
    assert.equal(doc.getElementById('ai-total-cases').textContent, '0');
    assert.match(doc.getElementById('ai-risk-table-body').textContent, /No eligible fictional duration-demo cases/);
    assert.doesNotMatch(doc.getElementById('ai-risk-table-body').textContent, /SYNTHETIC-DURATION-DEMO\/2026\/001/,
        'empty refresh clears previously displayed cases instead of leaving stale rows');

    run('syntheticDurationDemoAvailable = false; updateSyntheticDurationDemoUI()');
    assert.equal(durationDemoPanel.classList.contains('hidden'), true, 'the panel hides when the validated demo artifact is unavailable');
    console.log('Frontend UI: role-aware navigation, accessible menus, demo-only duration form, dashboard hierarchy, and alert counts passed');
    dom.window.close();
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
    dom.window.close();
});
