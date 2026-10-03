// Real Chromium viewport smoke test with entirely fictional API responses.
// Install Chromium with `npx playwright install chromium`, then run `npm run test:viewport`.
// In constrained Linux sandboxes, the optional @sparticuz/chromium path is supported by
// setting COURTLOG_USE_SPARTICUZ=1 (it is not an application dependency).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium: playwrightChromium } = require('playwright');

const repoRoot = path.resolve(__dirname, '..');
const frontendRoot = path.join(repoRoot, 'frontend');
const outputDir = path.resolve(process.env.VIEWPORT_OUTPUT_DIR || '.local/viewport-pass');
const fictionalUser = {
    user_id: 'usr_cr_01', username: 'cr', name: 'Fictional Chief Registrar',
    role: 'Chief Registrar', badge: 'Fictional test profile', court: 'All Courts',
    division: 'All Divisions', initials: 'CR', must_change_password: false
};
const fictionalCases = [
    {
        case_id: 'DEMO/CUSTODY-001', case_type: 'Fictional Criminal', court: 'Demo Court A',
        adjournment_count: 2, days_since_filing: 120, delay_risk_score: 0.31,
        risk_flag: false, custody_alert: true, file_missing: false,
        enforcement_non_compliant: false, judgment_status: 'Pending',
        assigned_sheriff_id: 'usr_sheriff_01', scan_events: [], hearing_log: [], execution_log: [],
    },
    {
        case_id: 'DEMO/EXECUTION-002', case_type: 'Fictional Civil', court: 'Demo Court B',
        adjournment_count: 1, days_since_filing: 240, delay_risk_score: 0.46,
        risk_flag: false, custody_alert: false, file_missing: false,
        enforcement_non_compliant: true, judgment_status: 'Delivered',
        assigned_sheriff_id: 'usr_sheriff_01', scan_events: [], hearing_log: [], execution_log: [],
    },
    {
        case_id: 'DEMO/MISSING-003', case_type: 'Fictional Commercial', court: 'Demo Court C',
        adjournment_count: 0, days_since_filing: 30, delay_risk_score: 0.12,
        risk_flag: false, custody_alert: false, file_missing: true,
        file_missing_report: { resolved: false, reported_at: '2026-10-03T08:00:00Z' },
        enforcement_non_compliant: false, judgment_status: 'Pending',
        assigned_sheriff_id: 'usr_sheriff_01', scan_events: [], hearing_log: [], execution_log: [],
    },
    {
        case_id: 'DEMO/CLEAR-004', case_type: 'Fictional Family', court: 'Demo Court D',
        adjournment_count: 0, days_since_filing: 10, delay_risk_score: 0.08,
        risk_flag: false, custody_alert: false, file_missing: false,
        enforcement_non_compliant: false, judgment_status: 'Pending',
        assigned_sheriff_id: 'usr_sheriff_01', scan_events: [], hearing_log: [], execution_log: [],
    }
];

const mimeTypes = {
    '.css': 'text/css; charset=utf-8', '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8',
    '.webmanifest': 'application/manifest+json', '.png': 'image/png', '.svg': 'image/svg+xml',
    '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.txt': 'text/plain; charset=utf-8'
};

function serveStatic(requestPath, response) {
    const localPath = requestPath === '/' ? 'index.html'
        : requestPath === '/service-worker.js' ? 'service-worker.js'
        : requestPath.startsWith('/static/') ? requestPath.slice('/static/'.length)
        : null;
    if (!localPath) {
        response.writeHead(404).end('Not found');
        return;
    }
    const resolved = path.resolve(frontendRoot, localPath);
    if (!resolved.startsWith(frontendRoot + path.sep) && resolved !== path.join(frontendRoot, 'index.html')) {
        response.writeHead(400).end('Invalid asset path');
        return;
    }
    fs.readFile(resolved, (error, contents) => {
        if (error) {
            response.writeHead(404).end('Asset not found');
            return;
        }
        response.writeHead(200, {
            'Content-Type': mimeTypes[path.extname(resolved)] || 'application/octet-stream',
            'Cache-Control': requestPath === '/service-worker.js' ? 'no-cache' : 'public, max-age=0'
        });
        response.end(contents);
    });
}

function mockApi(route) {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/refresh') return { status: 401, body: { detail: 'No test session' } };
    if (pathname === '/api/login') return { status: 200, body: { access_token: 'fictional-test-token', token_type: 'bearer', user: fictionalUser } };
    if (pathname === '/api/config') return { status: 200, body: { demo_mode: true } };
    if (pathname === '/api/cases') return { status: 200, body: fictionalCases };
    if (pathname === '/api/users') return { status: 200, body: [
        { user_id: 'usr_cr_01', name: 'Fictional Chief Registrar', role: 'Chief Registrar', court: 'All Courts', division: 'All Divisions' },
        { user_id: 'usr_clerk_01', name: 'Fictional Clerk', role: 'Clerk', court: 'Demo Court A', division: 'Criminal' },
        { user_id: 'usr_sheriff_01', name: 'Fictional Sheriff', role: 'Sheriff', court: 'Demo Court A', division: 'Criminal' }
    ] };
    if (pathname === '/api/judge/alerts') return { status: 200, body: { alerts: [], total_alerts: 0 } };
    if (pathname === '/api/whatsapp/status') return { status: 200, body: {
        mode: 'demo_simulation', ready: false, enabled: false, demo_mode: true,
        webhook_ready: false, consent_store_ready: false, missing: [],
        message: 'Demo mode only. No messages are sent to WhatsApp.'
    } };
    if (pathname === '/api/whatsapp/logs') return { status: 200, body: [] };
    if (pathname === '/api/logout') return { status: 200, body: { status: 'logged_out' } };
    return { status: 200, body: {} };
}

async function launchBrowser() {
    if (process.env.COURTLOG_USE_SPARTICUZ === '1') {
        // Optional local-only path for environments where Playwright's browser CDN is blocked.
        const module = require('@sparticuz/chromium');
        const sparticuz = module.default;
        const packageBuildDir = path.dirname(require.resolve('@sparticuz/chromium'));
        const archiveDir = path.resolve(packageBuildDir, '../bin');
        await module.inflate(path.join(archiveDir, 'al2023.tar.br'));
        process.env.LD_LIBRARY_PATH = ['/tmp/al2023/lib', process.env.LD_LIBRARY_PATH || ''].filter(Boolean).join(':');
        const executablePath = await sparticuz.executablePath();
        return playwrightChromium.launch({
            executablePath,
            args: sparticuz.args,
            headless: true
        });
    }
    return playwrightChromium.launch({ headless: true });
}

(async () => {
    fs.mkdirSync(outputDir, { recursive: true });
    const server = http.createServer((request, response) => {
        serveStatic(new URL(request.url, 'http://127.0.0.1').pathname, response);
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const origin = `http://127.0.0.1:${server.address().port}`;
    const browser = await launchBrowser();
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.route('**/api/**', async route => {
        const result = mockApi(route);
        await route.fulfill({
            status: result.status,
            contentType: 'application/json; charset=utf-8',
            headers: { 'Cache-Control': 'no-store' },
            body: JSON.stringify(result.body)
        });
    });
    await page.goto(origin, { waitUntil: 'domcontentloaded' });
    await page.locator('#login-username').fill('fictional-cr');
    await page.locator('#login-password').fill('fictional-only');
    await page.locator('#btn-login-submit').click();
    await page.locator('#login-overlay').waitFor({ state: 'hidden' });
    await page.waitForFunction(() => document.querySelector('#stat-total-cases')?.textContent === '4');

    const sizes = [
        { name: '390x844', width: 390, height: 844 },
        { name: '768x1024', width: 768, height: 1024 },
        { name: '1024x768', width: 1024, height: 768 },
        { name: '1366x768', width: 1366, height: 768 },
        { name: '1600x900', width: 1600, height: 900 }
    ];
    const measurements = [];
    for (const size of sizes) {
        await page.setViewportSize({ width: size.width, height: size.height });
        await page.waitForTimeout(100);
        const metrics = await page.evaluate(() => {
            const rect = selector => {
                const element = document.querySelector(selector);
                if (!element) return null;
                const box = element.getBoundingClientRect();
                return { left: Math.round(box.left), right: Math.round(box.right), width: Math.round(box.width), height: Math.round(box.height) };
            };
            return {
                viewport: window.innerWidth,
                documentWidth: document.documentElement.scrollWidth,
                bodyWidth: document.body.scrollWidth,
                header: rect('.app-header'),
                roleContext: rect('.role-context'),
                attentionGrid: rect('.attention-grid'),
                worklist: rect('#cases-directory'),
                tableViewport: rect('.table-scroll'),
                tableWidth: document.querySelector('.case-table')?.scrollWidth || 0,
                horizontalTableOverflow: (document.querySelector('.table-scroll')?.scrollWidth || 0) > (document.querySelector('.table-scroll')?.clientWidth || 0)
            };
        });
        assert.ok(metrics.documentWidth <= size.width + 1, `${size.name}: page has horizontal overflow (${metrics.documentWidth}px)`);
        assert.ok(metrics.header && metrics.header.left >= -1 && metrics.header.right <= size.width + 1, `${size.name}: header is outside viewport`);
        assert.ok(metrics.worklist && metrics.worklist.left >= -1 && metrics.worklist.right <= size.width + 1, `${size.name}: worklist is outside viewport`);
        assert.equal(metrics.horizontalTableOverflow, metrics.tableWidth > metrics.tableViewport.width + 1, `${size.name}: table overflow should stay inside its scroll wrapper`);
        measurements.push({ ...size, ...metrics });
        await page.screenshot({ path: path.join(outputDir, `dashboard-${size.name}.png`) });
        await page.screenshot({ path: path.join(outputDir, `dashboard-${size.name}-full.png`), fullPage: true });
    }

    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => { const content = document.querySelector('#page-content'); if (content) content.scrollTop = 0; });
    await page.locator('#btn-register-case').click();
    await page.locator('#tab-case-register').waitFor({ state: 'visible' });
    const phoneFormMetrics = await page.evaluate(() => ({
        viewport: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        panel: (() => { const r = document.querySelector('#register-case-panel').getBoundingClientRect(); return { left: r.left, right: r.right }; })(),
        controls: Array.from(document.querySelectorAll('#form-create-case input, #form-create-case select')).map(element => {
            const r = element.getBoundingClientRect(); return { id: element.id, left: r.left, right: r.right };
        }),
        requiredMarkOffsets: Array.from(document.querySelectorAll('#form-create-case .required-mark')).map(mark =>
            mark.getBoundingClientRect().top - mark.closest('label').getBoundingClientRect().top)
    }));
    assert.ok(phoneFormMetrics.documentWidth <= 391, '390x844: registration form creates page-wide horizontal overflow');
    assert.ok(phoneFormMetrics.panel.left >= -1 && phoneFormMetrics.panel.right <= 391, '390x844: registration panel is outside viewport');
    assert.ok(phoneFormMetrics.controls.every(control => control.left >= -1 && control.right <= 391), '390x844: a registration control is clipped');
    assert.ok(phoneFormMetrics.requiredMarkOffsets.every(offset => offset < 3), '390x844: required marks should remain inline with field labels');
    await page.screenshot({ path: path.join(outputDir, 'register-form-390x844.png') });

    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(100);
    const tabletFormMetrics = await page.evaluate(() => ({
        viewport: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        panel: (() => { const r = document.querySelector('#register-case-panel').getBoundingClientRect(); return { left: r.left, right: r.right }; })(),
        controls: Array.from(document.querySelectorAll('#form-create-case input, #form-create-case select')).map(element => {
            const r = element.getBoundingClientRect(); return { id: element.id, left: r.left, right: r.right };
        }),
        requiredMarkOffsets: Array.from(document.querySelectorAll('#form-create-case .required-mark')).map(mark =>
            mark.getBoundingClientRect().top - mark.closest('label').getBoundingClientRect().top)
    }));
    assert.ok(tabletFormMetrics.documentWidth <= 769, '768x1024: registration form creates page-wide horizontal overflow');
    assert.ok(tabletFormMetrics.panel.left >= -1 && tabletFormMetrics.panel.right <= 769, '768x1024: registration panel is outside viewport');
    assert.ok(tabletFormMetrics.controls.every(control => control.left >= -1 && control.right <= 769), '768x1024: a registration control is clipped');
    assert.ok(tabletFormMetrics.requiredMarkOffsets.every(offset => offset < 3), '768x1024: required marks should remain inline with field labels');
    await page.screenshot({ path: path.join(outputDir, 'register-form-768x1024.png') });
    await page.getByRole('button', { name: /Back to dashboard/ }).click();
    await page.locator('#tab-overview').waitFor({ state: 'visible' });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => { const content = document.querySelector('#page-content'); if (content) content.scrollTop = 0; });
    await page.locator('#mobile-nav-toggle').click();
    assert.equal(await page.locator('body').evaluate(element => element.classList.contains('nav-open')), true);
    await page.waitForTimeout(300); // let the drawer's 220 ms slide transition settle before geometry/screenshot checks
    const navMetrics = await page.evaluate(() => {
        const rect = selector => {
            const element = document.querySelector(selector);
            const box = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            return { left: box.left, right: box.right, width: box.width, paddingLeft: style.paddingLeft, transform: style.transform };
        };
        return { scrollX: window.scrollX, viewport: window.innerWidth, sidebar: rect('#app-sidebar'), brand: rect('.sidebar-brand'), nav: rect('.sidebar-nav'), firstNavItem: rect('.nav-item') };
    });
    console.log('Mobile navigation geometry:', JSON.stringify(navMetrics));
    assert.ok(navMetrics.sidebar.left >= -1 && navMetrics.sidebar.right <= navMetrics.viewport + 1, 'mobile drawer should remain within the viewport');
    assert.ok(navMetrics.firstNavItem.left >= navMetrics.sidebar.left && navMetrics.firstNavItem.right <= navMetrics.sidebar.right, 'mobile navigation items should remain inside the drawer');
    await page.screenshot({ path: path.join(outputDir, 'mobile-navigation-open.png') });
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('body').evaluate(element => element.classList.contains('nav-open')), false);

    await page.evaluate(() => { const content = document.querySelector('#page-content'); if (content) content.scrollTop = 0; });
    await page.getByRole('button', { name: /Review custody list/ }).click();
    assert.equal(await page.locator('#filter-status').inputValue(), 'ALERTS');
    assert.match(await page.locator('#cases-table-body tr').first().innerText(), /DEMO\/CUSTODY-001/);
    assert.equal(await page.locator('#cases-heading').evaluate(element => document.activeElement === element), true);
    assert.deepEqual(pageErrors, [], `browser runtime errors: ${pageErrors.join('; ')}`);

    fs.writeFileSync(path.join(outputDir, 'measurements.json'), JSON.stringify(measurements, null, 2));
    console.log(JSON.stringify(measurements, null, 2));
    console.log(`Viewport screenshots saved under ${outputDir}`);
    await browser.close();
    await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
})().catch(error => {
    console.error(error);
    process.exit(1);
});
