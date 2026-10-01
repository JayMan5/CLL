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

    dom.window.document.getElementById('login-username').value = 'clerk';
    dom.window.document.getElementById('login-password').value = '123';
    await vm.runInContext('handleLoginSubmit({preventDefault(){}})', context);
    assert.equal(vm.runInContext('accessToken', context), 'login-access');
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

    await vm.runInContext('handleLogout()', context);
    assert.equal(vm.runInContext('accessToken', context), null);
    assert.ok(calls.some(call => call.url === '/api/logout'));
    console.log('Frontend session: cookie-backed restore, login, refresh retry, forced-change prompt and logout passed');
    dom.window.close();
})().catch(error => { console.error(error); process.exitCode = 1; dom.window.close(); });
