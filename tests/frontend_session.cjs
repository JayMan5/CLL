// Run with NODE_PATH pointing at jsdom's node_modules.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');

const profile = {
    user_id: 'usr_clerk_01', username: 'clerk', name: 'Registry Clerk',
    role: 'Clerk', badge: 'Registry Staff', court: 'FHC Abuja Court 4',
    division: 'Criminal', must_change_password: true
};
const calls = [];
const custodyPosts = [];
let refreshCount = 0;
let protectedCount = 0;
function response(status, body = {}, headers = {}) {
    const normalized = Object.fromEntries(Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]));
    return {
        status, ok: status >= 200 && status < 300,
        headers: { get: key => normalized[String(key).toLowerCase()] || null },
        json: async () => body,
        clone() { return this; }
    };
}

const dom = new JSDOM(fs.readFileSync('frontend/index.html', 'utf8'), {
    url: 'https://courtlog.test/', runScripts: 'outside-only', pretendToBeVisual: true
});
dom.window.Headers = global.Headers;
dom.window.fetch = async (url, options = {}) => {
    calls.push({url, options});
    if (url === '/api/refresh') {
        refreshCount += 1;
        if (refreshCount === 1) return response(401, {detail: 'No session'}); // initial page restore
        return response(200, {access_token: 'refreshed-access', token_type: 'bearer', user: profile});
    }
    if (url === '/api/login') return response(200, {access_token: 'login-access', token_type: 'bearer', user: profile});
    if (url === '/api/cases') return response(200, []);
    if (String(url).endsWith('/sheriffs')) return response(200, [
        {user_id:'usr_sheriff_02', name:'Assigned Test Sheriff', badge:'Fictional'},
    ]);
    if (String(url).endsWith('/assign-sheriff') || String(url).endsWith('/handover')) {
        custodyPosts.push({url, body: options.body});
        return response(200, {assigned_sheriff_id:'usr_sheriff_02'});
    }
    if (url === '/api/whatsapp/logs') return response(200, []);
    if (url === '/api/test-protected') {
        protectedCount += 1;
        return protectedCount === 1 ? response(401, {detail:'Expired'}) : response(200, {ok:true});
    }
    if (url === '/api/password-required') return response(403, {detail:'Initial password change required'}, {'X-Password-Change-Required':'true'});
    return response(200, {});
};

(async () => {
    const context = dom.getInternalVMContext();
    const ready = new Promise(resolve => dom.window.document.addEventListener('DOMContentLoaded', () => setTimeout(resolve, 0), {once:true}));
    new vm.Script(fs.readFileSync('frontend/app.js', 'utf8')).runInContext(context);
    await ready;
    assert.equal(dom.window.document.getElementById('nav-whatsapp').style.display, 'none');

    dom.window.document.getElementById('login-username').value = 'clerk';
    dom.window.document.getElementById('login-password').value = '123';
    await vm.runInContext('handleLoginSubmit({preventDefault(){}})', context);
    assert.equal(vm.runInContext('accessToken', context), 'login-access');
    vm.runInContext('switchTab("tab-whatsapp")', context);
    assert.equal(dom.window.document.getElementById('tab-whatsapp').classList.contains('hidden'), true);
    assert.equal(dom.window.document.getElementById('password-change-overlay').classList.contains('hidden'), false);
    assert.equal(dom.window.localStorage.getItem('courtlog-access-token'), null);
    assert.equal(dom.window.localStorage.getItem('courtlog-refresh-token'), null);

    const protectedResponse = await vm.runInContext('apiFetch("/api/test-protected")', context);
    assert.equal(protectedResponse.status, 200);
    assert.equal(vm.runInContext('accessToken', context), 'refreshed-access');
    const retry = calls.find(call => call.url === '/api/test-protected' && call.options.headers.get('Authorization') === 'Bearer refreshed-access');
    assert.ok(retry, 'retries the protected request with the new in-memory token');

    await vm.runInContext('apiFetch("/api/password-required")', context);
    assert.equal(dom.window.document.getElementById('password-change-overlay').classList.contains('hidden'), false);

    vm.runInContext('loadDashboardData = async () => {}', context);
    await vm.runInContext('openAssignSheriffModal("SAFE/ASSIGN")', context);
    const targetSelect = dom.window.document.getElementById('sheriff-custody-target');
    assert.equal(targetSelect.options[1].value, 'usr_sheriff_02');
    targetSelect.value = 'usr_sheriff_02';
    dom.window.document.getElementById('sheriff-custody-reason').value = 'Registry dispatch';
    await vm.runInContext('submitSheriffCustody({preventDefault(){}})', context);
    assert.ok(custodyPosts[0].url.endsWith('/api/cases/SAFE/ASSIGN/assign-sheriff'));
    assert.deepEqual(JSON.parse(custodyPosts[0].body), {
        sheriff_id:'usr_sheriff_02', reason:'Registry dispatch'
    });
    assert.equal(JSON.parse(custodyPosts[0].body).staff_id, undefined);

    await vm.runInContext('openSheriffHandoverModal("SAFE/ASSIGN")', context);
    targetSelect.value = 'usr_sheriff_02';
    dom.window.document.getElementById('sheriff-handover-location').value = 'Registry Desk A';
    dom.window.document.getElementById('sheriff-custody-reason').value = 'End of duty';
    await vm.runInContext('submitSheriffCustody({preventDefault(){}})', context);
    assert.ok(custodyPosts[1].url.endsWith('/api/cases/SAFE/ASSIGN/handover'));
    assert.deepEqual(JSON.parse(custodyPosts[1].body), {
        to_sheriff_id:'usr_sheriff_02', location:'Registry Desk A', reason:'End of duty'
    });

    await vm.runInContext('handleLogout()', context);
    assert.equal(vm.runInContext('accessToken', context), null);
    assert.ok(calls.some(call => call.url === '/api/logout'));
    console.log('Frontend session: auth lifecycle and delegated Sheriff assignment/handover passed');
    dom.window.close();
})().catch(error => { console.error(error); process.exitCode = 1; dom.window.close(); });
