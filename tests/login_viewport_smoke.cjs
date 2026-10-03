// Responsive smoke test for the unauthenticated login screen using fictional API responses.
// Install Chromium with `npx playwright install chromium`, then run `npm run test:viewport:login`.
// In constrained Linux sandboxes, set COURTLOG_USE_SPARTICUZ=1 with the optional package installed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium: playwrightChromium } = require('playwright');

const repoRoot = path.resolve(__dirname, '..');
const frontendRoot = path.join(repoRoot, 'frontend');
const outputDir = path.resolve(process.env.VIEWPORT_OUTPUT_DIR || '.local/viewport-pass');
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

async function launchBrowser() {
    if (process.env.COURTLOG_USE_SPARTICUZ === '1') {
        const module = require('@sparticuz/chromium');
        const sparticuz = module.default;
        const packageBuildDir = path.dirname(require.resolve('@sparticuz/chromium'));
        const archiveDir = path.resolve(packageBuildDir, '../bin');
        await module.inflate(path.join(archiveDir, 'al2023.tar.br'));
        process.env.LD_LIBRARY_PATH = ['/tmp/al2023/lib', process.env.LD_LIBRARY_PATH || ''].filter(Boolean).join(':');
        return playwrightChromium.launch({
            executablePath: await sparticuz.executablePath(),
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
    let browser;
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    try {
        const origin = `http://127.0.0.1:${server.address().port}`;
        browser = await launchBrowser();
        const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
        const pageErrors = [];
        page.on('pageerror', error => pageErrors.push(error.message));
        await page.route('**/api/**', async route => {
            const pathname = new URL(route.request().url()).pathname;
            const result = pathname === '/api/refresh'
                ? { status: 401, body: { detail: 'No fictional session' } }
                : { status: 200, body: pathname === '/api/config' ? { demo_mode: true } : {} };
            await route.fulfill({
                status: result.status,
                contentType: 'application/json; charset=utf-8',
                headers: { 'Cache-Control': 'no-store' },
                body: JSON.stringify(result.body)
            });
        });
        await page.goto(origin, { waitUntil: 'domcontentloaded' });

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
            await page.waitForTimeout(80);
            const metrics = await page.evaluate(() => {
                const bounds = selector => {
                    const element = document.querySelector(selector);
                    if (!element) return null;
                    const r = element.getBoundingClientRect();
                    return {
                        left: Math.round(r.left), top: Math.round(r.top),
                        right: Math.round(r.right), bottom: Math.round(r.bottom),
                        width: Math.round(r.width), height: Math.round(r.height)
                    };
                };
                return {
                    viewport: { width: window.innerWidth, height: window.innerHeight },
                    documentWidth: document.documentElement.scrollWidth,
                    overlay: bounds('#login-overlay'),
                    card: bounds('#login-overlay > .glass-panel'),
                    username: bounds('#login-username'),
                    password: bounds('#login-password'),
                    submit: bounds('#btn-login-submit')
                };
            });
            assert.ok(metrics.documentWidth <= size.width + 1, `${size.name}: login page has horizontal overflow (${metrics.documentWidth}px)`);
            assert.ok(metrics.overlay && metrics.overlay.left >= -1 && metrics.overlay.right <= size.width + 1, `${size.name}: login overlay is outside viewport`);
            assert.ok(metrics.card && metrics.card.left >= -1 && metrics.card.right <= size.width + 1 && metrics.card.top >= -1 && metrics.card.bottom <= size.height + 1, `${size.name}: login card is clipped`);
            for (const control of [metrics.username, metrics.password, metrics.submit]) {
                assert.ok(control && control.left >= metrics.card.left && control.right <= metrics.card.right && control.top >= metrics.card.top && control.bottom <= metrics.card.bottom, `${size.name}: a login control is clipped`);
            }
            assert.equal(await page.locator('label[for="login-username"]').count(), 1, 'username label should be associated with its input');
            assert.equal(await page.locator('label[for="login-password"]').count(), 1, 'password label should be associated with its input');
            measurements.push({ name: size.name, ...metrics });
            await page.screenshot({ path: path.join(outputDir, `login-${size.name}.png`) });
        }
        assert.deepEqual(pageErrors, [], `browser runtime errors: ${pageErrors.join('; ')}`);
        fs.writeFileSync(path.join(outputDir, 'login-measurements.json'), JSON.stringify(measurements, null, 2));
        console.log(`Login viewport checks passed at ${sizes.map(size => size.name).join(', ')}.`);
        console.log(`Login screenshots saved under ${outputDir}`);
    } finally {
        await browser?.close();
        await new Promise(resolve => server.close(() => resolve()));
    }
})().catch(error => {
    console.error(error);
    process.exit(1);
});
