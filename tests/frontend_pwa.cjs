// Run via npm run test:frontend. Covers local QR generation, PWA shell policy,
// and the client rule that a scan is successful only after matching server data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');
const QRCode = require('qrcode');

const manifest = JSON.parse(fs.readFileSync('frontend/manifest.webmanifest', 'utf8'));
const packageJson = JSON.parse(fs.readFileSync('package.json', 'utf8'));
const tailwindInput = fs.readFileSync('frontend/tailwind.input.css', 'utf8');
const tailwindOutput = fs.readFileSync('frontend/tailwind.css', 'utf8');
const indexHtml = fs.readFileSync('frontend/index.html', 'utf8');
const tailwindVersion = packageJson.devDependencies.tailwindcss;
assert.match(tailwindVersion, /^4\./, 'the frontend toolchain uses Tailwind v4');
assert.equal(packageJson.devDependencies['@tailwindcss/cli'], tailwindVersion, 'Tailwind engine and CLI are pinned to matching versions');
assert.match(packageJson.scripts['build:frontend'], /tailwindcss -i frontend\/tailwind\.input\.css/);
assert.match(tailwindInput, /@import "tailwindcss" source\(none\);/);
assert.match(tailwindInput, /@source inline\("hidden\b/, 'runtime hidden-state utility remains safelisted');
for (const utility of ['.hidden{', '.font-sans{', '.font-heading{']) {
  assert.ok(tailwindOutput.includes(utility), `Tailwind v4 generated ${utility}`);
}
assert.doesNotMatch(indexHtml, /https:\/\/(?:cdn\.|fonts\.)/i, 'runtime frontend dependencies do not use external CDNs');
for (const localAsset of [
  '/static/tailwind.css',
  '/static/chart.bundle.js',
  '/static/vendor/fontawesome/css/all.min.css',
  '/static/vendor/fonts/outfit/wght.css',
  '/static/vendor/fonts/plus-jakarta-sans/wght.css',
]) {
  assert.ok(indexHtml.includes(localAsset), `page references local asset ${localAsset}`);
}
assert.ok(fs.statSync('frontend/tailwind.css').size > 0, 'Tailwind output was built locally');
assert.ok(fs.statSync('frontend/chart.bundle.js').size > 100_000, 'Chart.js is bundled locally');
assert.ok(indexHtml.indexOf('/static/chart.bundle.js') < indexHtml.indexOf('/static/app.js'), 'Chart.js loads before the application that uses it');
assert.equal(manifest.name, 'COURTLOG Sheriff Custody Check-In');
assert.equal(manifest.short_name, 'COURTLOG');
assert.equal(manifest.start_url, '/');
assert.equal(manifest.scope, '/');
assert.equal(manifest.background_color, '#0b1117', 'installed splash color matches the refreshed dark shell');
assert.equal(manifest.theme_color, '#0b1117', 'browser theme chrome matches the refreshed dark shell');
assert.ok(manifest.icons.some(icon => icon.sizes === '192x192'));
assert.ok(manifest.icons.some(icon => icon.sizes === '512x512'));
for (const icon of manifest.icons) assert.ok(fs.existsSync(`frontend${icon.src.replace('/static', '')}`));

const serviceWorker = fs.readFileSync('frontend/service-worker.js', 'utf8');
for (const localAsset of [
  '/static/tailwind.css',
  '/static/chart.bundle.js',
  '/static/vendor/fontawesome/css/all.min.css',
  '/static/vendor/fonts/outfit/files/outfit-latin-wght-normal.woff2',
  '/static/vendor/fonts/plus-jakarta-sans/files/plus-jakarta-sans-latin-wght-normal.woff2',
]) {
  assert.ok(serviceWorker.includes(localAsset), `PWA shell cache includes ${localAsset}`);
}
for (const [, path] of serviceWorker.matchAll(/"(\/static\/[^\"]+)"/g)) {
  assert.ok(fs.existsSync(`frontend${path.replace('/static', '')}`), `cached asset exists: ${path}`);
}
assert.match(serviceWorker, /courtlog-shell-v6/, 'the Tailwind v4 output invalidates the earlier static cache');
assert.match(serviceWorker, /request\.method !== "GET"/);
assert.match(serviceWorker, /url\.pathname\.startsWith\("\/api\/"\)/, 'API responses are bypassed by the shell cache');
assert.match(serviceWorker, /does not queue custody scans/i);
assert.doesNotMatch(serviceWorker, /\b(?:sync|periodicsync)\s*\(/i, 'no background/offline scan queue is installed');

const qrPayload = `courtlog:v1:${'a'.repeat(43)}`;
assert.ok(QRCode.create(qrPayload).modules.size > 20, 'the local qrcode package can encode the opaque payload');
assert.ok(!qrPayload.includes('CASE/'), 'the token format does not embed a case identifier');
const pwaSource = fs.readFileSync('frontend/c2-pwa.js', 'utf8');
assert.match(pwaSource, /QRCode\.toCanvas/);
assert.match(pwaSource, /decodeFromConstraints/);
assert.match(pwaSource, /facingMode:\s*\{\s*ideal:\s*"environment"\s*\}/);

const profile = { user_id: 'sheriff-test', role: 'Sheriff', name: 'Fictional Sheriff' };
let scanMode = 'network-error';
const calls = [];
const renderedPayloads = [];
const issuedPayload = `courtlog:v1:${'b'.repeat(43)}`;
function response(status, body = {}) {
  return { status, ok: status >= 200 && status < 300, headers: { get: () => null }, json: async () => body };
}

(async () => {
  const dom = new JSDOM(fs.readFileSync('frontend/index.html', 'utf8'), {
    url: 'https://courtlog.test/', runScripts: 'outside-only', pretendToBeVisual: true
  });
  await new Promise(resolve => dom.window.addEventListener('DOMContentLoaded', resolve, { once: true }));
  dom.window.Headers = global.Headers;
  dom.window.CourtLogPwa = {
    initialize() {}, setScanHandler() {}, setRole() {}, stopCamera() {}, startCamera() {},
    renderQrLabel: async (payload, canvas) => { renderedPayloads.push({ payload, canvasId: canvas.id }); }
  };
  dom.window.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (String(url).endsWith('/qr-label')) {
      return response(201, { qr_payload: issuedPayload, format: 'courtlog:v1' });
    }
    if (url === '/api/scan/qr') {
      if (scanMode === 'network-error') throw new TypeError('offline test');
      if (scanMode === 'denied') return response(403, { detail: 'Only the assigned Sheriff may check in this QR label' });
      return response(200, {
        case_id: 'FICTIONAL/CASE',
        scan_events: [{ staff_id: profile.user_id, location: 'Registry Desk A', timestamp: '2026-10-01T10:00:00Z' }]
      });
    }
    if (url === '/api/cases') return response(200, []);
    return response(200, {});
  };

  const context = dom.getInternalVMContext();
  new vm.Script(fs.readFileSync('frontend/app.js', 'utf8')).runInContext(context);
  const run = code => vm.runInContext(code, context);
  run(`loadDashboardData = async () => {}; updateQRDisplay = () => {};`);
  run(`authenticatedUser = ${JSON.stringify(profile)}; accessToken = 'test-access';`);

  const input = dom.window.document.getElementById('qr-payload-input');
  input.value = qrPayload;
  const networkResult = await run('handleQrTokenSubmit({preventDefault(){}})');
  assert.equal(networkResult, false);
  assert.match(dom.window.document.getElementById('scan-checkin-status').textContent, /No server confirmation/i);
  assert.doesNotMatch(dom.window.document.getElementById('scan-checkin-status').textContent, /^Check-in confirmed/i);
  assert.equal(input.value, '', 'keyboard-scanned token is cleared after submission');
  assert.equal(dom.window.localStorage.getItem('courtlog-pending-scans'), null, 'offline scans are not persisted or queued');
  const submitted = JSON.parse(calls[0].options.body);
  assert.equal(submitted.qr_payload, qrPayload);
  assert.equal(submitted.case_id, undefined, 'QR requests submit the opaque token, not a client-selected case ID');

  scanMode = 'denied';
  const denied = await run(`handleQrPayloadFromCamera(${JSON.stringify(qrPayload)})`);
  assert.equal(denied, false);
  assert.match(dom.window.document.getElementById('scan-checkin-status').textContent, /Not confirmed by CourtLOG/i);

  scanMode = 'success';
  const confirmed = await run(`handleQrPayloadFromCamera(${JSON.stringify(qrPayload)})`);
  assert.equal(confirmed, true);
  assert.match(dom.window.document.getElementById('scan-checkin-status').textContent, /^Check-in confirmed by CourtLOG/i);
  assert.equal(calls.at(-1).url, '/api/scan/qr');

  run(`authenticatedUser = { user_id: 'clerk-test', role: 'Clerk', name: 'Fictional Clerk' };`);
  const caseSelect = dom.window.document.getElementById('scan-case-id');
  caseSelect.replaceChildren(new dom.window.Option('Fictional case', 'FICTIONAL/CASE'));
  caseSelect.value = 'FICTIONAL/CASE';
  const labelCreated = await run('generateQrLabel()');
  assert.equal(labelCreated, true);
  assert.equal(calls.at(-1).url, '/api/cases/FICTIONAL/CASE/qr-label');
  assert.equal(calls.at(-1).options.body, undefined, 'label issuance sends no client-supplied case content');
  assert.deepEqual(renderedPayloads.at(-1), { payload: issuedPayload, canvasId: 'qr-label-canvas' });
  assert.equal(dom.window.document.getElementById('qr-label-canvas').dataset.caseId, 'FICTIONAL/CASE');
  assert.equal(dom.window.document.getElementById('btn-print-qr-label').disabled, false);
  assert.doesNotMatch(issuedPayload, /FICTIONAL\/CASE/);

  dom.window.close();
  console.log('Frontend PWA: local QR payload, API-only scanning, no offline queue, and confirmed-success gating passed');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
