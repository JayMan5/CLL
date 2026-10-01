// Run: NODE_PATH=/path/to/node_modules node tests/frontend_security.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');
const dom = new JSDOM(fs.readFileSync('frontend/index.html', 'utf8'), {
    url: 'https://courtlog.test/', runScripts: 'outside-only', pretendToBeVisual: true
});
const ctx = dom.getInternalVMContext();
new vm.Script(fs.readFileSync('frontend/app.js', 'utf8')).runInContext(ctx);
const run = code => new vm.Script(code).runInContext(ctx);
const attack = `x');window.stolen=true;//<img src=x onerror=alert(1)>`;
const record = {case_id: attack, case_type: attack, court: attack, scan_events: [],
    adjournment_count: 0, days_since_filing: 1, delay_risk_score: 0.1, judgment_status: 'Pending'};
run(`renderHeatmapTable([${JSON.stringify(record)}])`);
const table = dom.window.document.getElementById('cases-table-body');
assert.equal(table.querySelector('img'), null);
const scan = table.querySelector('[data-case-action="scan"]');
assert.equal(scan.getAttribute('onclick'), null);
assert.equal(scan.dataset.recordId, attack);
run('shortcutQRScan = id => { window.selectedId = id; }');
scan.dispatchEvent(new dom.window.MouseEvent('click', {bubbles: true}));
assert.equal(dom.window.selectedId, attack);
assert.equal(dom.window.stolen, undefined);
run(`whatsappLogs = [{received_at: new Date().toISOString(), payload: {to: ${JSON.stringify(attack)}, simulated_text: ${JSON.stringify(attack)}}}]; renderWhatsAppLogs()`);
assert.equal(dom.window.document.querySelector('#whatsapp-logs-container img'), null);
run(`showToast(${JSON.stringify(attack)})`);
assert.equal(dom.window.document.querySelector('#toast-container img'), null);
run(`casesData = [${JSON.stringify({...record, case_id:'SAFE/1', case_title:attack})}]; showWritModal('SAFE/1','Garnishee Order',${JSON.stringify(attack)},${JSON.stringify(attack)})`);
assert.equal(dom.window.document.querySelector('#modal-writ-content img'), null);
console.log('Frontend security: 4 rendering boundaries and delegated identifier handling passed');
dom.window.close();
