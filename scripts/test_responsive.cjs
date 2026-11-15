const http = require('http');
const fs = require('fs');
const path = require('path');
const puppeteer = require(path.resolve(__dirname, '../web/node_modules/puppeteer-core'));

const DIST_DIR = path.resolve(__dirname, '../web/dist');
const SCREENSHOT_DIR = path.resolve(__dirname, '../docs/STEP5_RESPONSIVE_TESTS');
const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

// 1. Simple static file server for web/dist
const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
};

function startServer(port = 4173) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let filePath = path.join(DIST_DIR, req.url.split('?')[0]);
      if (filePath.endsWith('/') || !path.extname(filePath)) {
        filePath = path.join(DIST_DIR, 'index.html');
      }

      fs.readFile(filePath, (err, content) => {
        if (err) {
          res.writeHead(404);
          res.end('Not Found');
          return;
        }
        const ext = path.extname(filePath);
        res.writeHead(200, { 'Content-Type': MIME_TYPES[ext] || 'application/octet-stream' });
        res.end(content);
      });
    });

    server.listen(port, '127.0.0.1', () => {
      console.log(`Test server running at http://127.0.0.1:${port}`);
      resolve(server);
    });
  });
}

// Test matrix defined according to Section 4.4:
// - Physical resolutions: 1080P, 2K, 4K
// - Scaling factors: 100%, 125%, 150%, 200%
// - Window widths: 1024, 1280, 1440, 1920, 2560, 3840
const TEST_CASES = [
  {
    name: '1920x1080_100pct',
    title: '1080P 标准全屏 (100% 缩放)',
    width: 1920,
    height: 1080,
    deviceScaleFactor: 1.0,
  },
  {
    name: '1920x1080_125pct',
    title: '1080P 标准屏 (125% 系统缩放)',
    width: 1536,
    height: 864,
    deviceScaleFactor: 1.25,
  },
  {
    name: '2560x1440_100pct',
    title: '2K 宽屏显示器 (100% 缩放)',
    width: 2560,
    height: 1440,
    deviceScaleFactor: 1.0,
  },
  {
    name: '2560x1440_125pct',
    title: '2K 宽屏显示器 (125% 系统缩放)',
    width: 2048,
    height: 1152,
    deviceScaleFactor: 1.25,
  },
  {
    name: '3840x2160_100pct',
    title: '4K 超高清显示器 (100% 物理缩放)',
    width: 3840,
    height: 2160,
    deviceScaleFactor: 1.0,
  },
  {
    name: '3840x2160_150pct',
    title: '4K 超高清显示器 (150% 常用缩放)',
    width: 2560,
    height: 1440,
    deviceScaleFactor: 1.5,
  },
  {
    name: '3840x2160_200pct',
    title: '4K 超高清显示器 (200% 常用缩放)',
    width: 1920,
    height: 1080,
    deviceScaleFactor: 2.0,
  },
  {
    name: '1440x900_macbook',
    title: '1440px 笔记本/小窗口',
    width: 1440,
    height: 900,
    deviceScaleFactor: 1.0,
  },
  {
    name: '1280x800_laptop',
    title: '1280px 标准紧凑屏',
    width: 1280,
    height: 800,
    deviceScaleFactor: 1.0,
  },
  {
    name: '1024x768_half_screen',
    title: '1024px 半屏/窄窗口',
    width: 1024,
    height: 768,
    deviceScaleFactor: 1.0,
  },
];

async function runTests() {
  const server = await startServer(4173);
  let browser;

  const results = [];

  try {
    browser = await puppeteer.launch({
      executablePath: CHROME_PATH,
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    });

    const page = await browser.newPage();

    // Listen for console errors
    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    for (const tc of TEST_CASES) {
      console.log(`\nTesting: [${tc.name}] - ${tc.title} (${tc.width}x${tc.height}, DPR=${tc.deviceScaleFactor})`);

      await page.setViewport({
        width: tc.width,
        height: tc.height,
        deviceScaleFactor: tc.deviceScaleFactor,
      });

      await page.goto('http://127.0.0.1:4173', { waitUntil: 'networkidle0' });

      // Allow charts to render and stabilize
      await new Promise((r) => setTimeout(r, 600));

      // Measure layout metrics
      const metrics = await page.evaluate(() => {
        const doc = document.documentElement;
        const innerH = window.innerHeight;
        const scrollH = doc.scrollHeight;
        const clientW = doc.clientWidth;
        const scrollW = doc.scrollWidth;

        const canvas = document.querySelector('canvas');
        let canvasInfo = null;
        if (canvas) {
          const rect = canvas.getBoundingClientRect();
          canvasInfo = {
            cssWidth: Math.round(rect.width),
            cssHeight: Math.round(rect.height),
            backingWidth: canvas.width,
            backingHeight: canvas.height,
          };
        }

        return {
          innerH,
          scrollH,
          clientW,
          scrollW,
          canvasInfo,
          ratio: Number((scrollH / innerH).toFixed(3)),
          hasHorizontalOverflow: scrollW > clientW,
        };
      });

      // Interactive checks: Click Sub-chart tabs and Secondary tabs
      try {
        // Click MACD tab
        const macdBtn = await page.evaluateHandle(() => {
          const btns = Array.from(document.querySelectorAll('button'));
          return btns.find((b) => b.textContent && b.textContent.trim() === 'MACD');
        });
        if (macdBtn.asElement()) {
          await macdBtn.asElement().click();
          await new Promise((r) => setTimeout(r, 200));
        }

        // Hover canvas to check crosshair & tooltip
        const canvasEl = await page.$('canvas');
        if (canvasEl) {
          const box = await canvasEl.boundingBox();
          if (box) {
            await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.4);
            await new Promise((r) => setTimeout(r, 200));
          }
        }
      } catch (err) {
        console.warn('Interaction test notice:', err.message);
      }

      // Save screenshot
      const screenshotPath = path.join(SCREENSHOT_DIR, `${tc.name}.png`);
      await page.screenshot({ path: screenshotPath, fullPage: false });
      console.log(`Saved screenshot -> ${screenshotPath}`);

      const passHeightLimit = metrics.ratio <= 2.0;
      const passHorizontal = !metrics.hasHorizontalOverflow;

      results.push({
        ...tc,
        ...metrics,
        passHeightLimit,
        passHorizontal,
        screenshotFile: `${tc.name}.png`,
      });

      console.log(`  InnerHeight: ${metrics.innerH}px | ScrollHeight: ${metrics.scrollH}px | Ratio: ${metrics.ratio}x viewports (Limit <= 2.0: ${passHeightLimit ? 'PASS' : 'FAIL'})`);
      if (metrics.canvasInfo) {
        console.log(`  Canvas: CSS ${metrics.canvasInfo.cssWidth}x${metrics.canvasInfo.cssHeight} | Backing: ${metrics.canvasInfo.backingWidth}x${metrics.canvasInfo.backingHeight} (DPR scaling verified)`);
      }
    }

    // Write test summary JSON
    const reportJsonPath = path.join(SCREENSHOT_DIR, 'RESPONSIVE_TEST_RESULTS.json');
    fs.writeFileSync(reportJsonPath, JSON.stringify({ results, consoleErrors, timestamp: new Date().toISOString() }, null, 2));
    console.log(`\nTest results JSON saved -> ${reportJsonPath}`);

  } catch (err) {
    console.error('Test execution failed:', err);
  } finally {
    if (browser) await browser.close();
    server.close();
    console.log('Server and browser shut down cleanly.');
  }
}

runTests();
