// 用法：
//   node render.mjs stills 0.9,2.6,3.9,6.0,7.5,9.4,11,13.5,15,16.9   → stills/s_<t>.png
//   node render.mjs frames <shard> <shards> <totalFrames>          → frames/f00000.png …
import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';
const require = createRequire('/opt/npm-tools/node_modules/');
const { chromium } = require('playwright');

const [, , mode, a, b, c, layerArg] = process.argv;
const layer = layerArg || process.env.LAYER || 'front';
const here = path.dirname(new URL(import.meta.url).pathname);
const browser = await chromium.launch({
  executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  args: ['--force-color-profile=srgb', '--disable-lcd-text', '--font-render-hinting=none'],
});
const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
await page.goto('file://' + path.join(here, 'overlay.html') + '?layer=' + layer);
await page.evaluate(() => document.fonts.ready);

const shot = async (t, file) => {
  await page.evaluate((t) => window.render(t), t);
  await page.screenshot({ path: file, omitBackground: true, type: 'png' });
};

if (mode === 'stills') {
  fs.mkdirSync(path.join(here, 'stills'), { recursive: true });
  for (const t of a.split(',').map(Number)) await shot(t, path.join(here, 'stills', `${layer}_${t.toFixed(2)}.png`));
} else {
  const shard = Number(a), shards = Number(b), total = Number(c);
  const fdir = path.join(here, 'frames_' + layer);
  fs.mkdirSync(fdir, { recursive: true });
  for (let i = shard; i < total; i += shards) {
    const f = path.join(fdir, `f${String(i).padStart(5, '0')}.png`);
    if (!fs.existsSync(f)) await shot(i / 30, f);
  }
}
await browser.close();
