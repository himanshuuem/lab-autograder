const { chromium } = require('playwright');
const fs = require('fs');
const SCENES = require('./scenes.js');
const D = require('./durations.json');
const U = 'http://localhost:8001';
const W = 1440, H = 900;

const OVERLAY = () => {
  const css = `
  #__cur{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;transform:translate(-3px,-2px);transition:transform .05s;filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}
  .__rip{position:fixed;z-index:2147483646;pointer-events:none;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;border:3px solid #6366f1;background:rgba(99,102,241,.25);animation:__rip .7s ease-out forwards}
  @keyframes __rip{to{transform:scale(4.5);opacity:0}}
  .__ring{position:fixed;z-index:2147483645;pointer-events:none;border:3px solid #f59e0b;border-radius:12px;box-shadow:0 0 0 6px rgba(245,158,11,.18);animation:__pulse 1.4s ease-in-out infinite}
  @keyframes __pulse{50%{box-shadow:0 0 0 12px rgba(245,158,11,.08)}}
  #__cap{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:2147483644;width:min(1180px,calc(100% - 48px));pointer-events:none;
    background:rgba(15,16,24,.88);backdrop-filter:blur(8px);color:#fff;border-radius:16px;padding:14px 22px 16px;font:500 19px/1.45 Inter,system-ui,sans-serif;
    box-shadow:0 12px 40px rgba(0,0,0,.3);transition:opacity .3s}
  #__cap .st{display:inline-block;font-size:12.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#c7d2fe;background:rgba(99,102,241,.35);border-radius:999px;padding:3px 10px;margin-bottom:6px}
  #__cap .tx{min-height:2.9em}
  #__card{position:fixed;inset:0;z-index:2147483643;display:flex;align-items:center;justify-content:center;flex-direction:column;
    background:radial-gradient(1200px 700px at 20% 10%,#4338ca 0%,transparent 60%),radial-gradient(900px 600px at 90% 90%,#7c3aed 0%,transparent 55%),#0d0e12;color:#fff;font-family:Inter,system-ui,sans-serif;transition:opacity .6s;padding-bottom:110px}
  #__card h1{font-size:76px;font-weight:800;letter-spacing:-.03em;margin:0}
  #__card h2{font-size:44px;font-weight:800;letter-spacing:-.02em;margin:0 0 36px}
  #__card p.sub{font-size:26px;color:#c7d2fe;margin:14px 0 30px;font-weight:500}
  #__card .tick{display:inline-flex;width:84px;height:84px;border-radius:22px;background:#6366f1;align-items:center;justify-content:center;font-size:50px;margin-bottom:26px;box-shadow:0 20px 60px rgba(99,102,241,.6)}
  #__card .badges span{display:inline-block;margin:0 6px;padding:8px 18px;border-radius:999px;background:rgba(255,255,255,.1);font-size:18px;font-weight:600}
  #__card .grid{display:grid;grid-template-columns:repeat(3,330px);gap:18px}
  #__card .grid div{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);border-radius:18px;padding:20px 22px;opacity:.12;transform:translateY(12px);transition:all .6s}
  #__card .grid div.on{opacity:1;transform:none;background:rgba(99,102,241,.22);border-color:rgba(165,180,252,.5)}
  #__card .grid b{display:block;font-size:30px;color:#a5b4fc;margin-bottom:6px}
  #__card .grid i{font-style:normal;font-size:21px;font-weight:700}
  #__card .grid small{display:block;font-size:15px;color:#c7d2fe;margin-top:6px;line-height:1.4}
  #__card pre{font:600 24px/1.7 'JetBrains Mono',monospace;background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.15);border-radius:16px;padding:22px 34px;margin:0 0 26px;text-align:left}
  #__card pre em{color:#86efac;font-style:normal}`;
  const init = () => {
    if (document.getElementById('__cur')) return;
    const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
    const c = document.createElement('div'); c.id = '__cur';
    c.innerHTML = `<svg viewBox="0 0 24 24" width="26" height="26"><path d="M3 2l7.5 19 2.6-7.9L21 10.5z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
    document.body.appendChild(c);
    const cap = document.createElement('div'); cap.id = '__cap'; cap.style.opacity = 0;
    cap.innerHTML = '<div class="st"></div><div class="tx"></div>'; document.body.appendChild(cap);
    addEventListener('mousemove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', (e) => {
      const r = document.createElement('div'); r.className = '__rip'; r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
      document.body.appendChild(r); setTimeout(() => r.remove(), 800);
      c.style.transform = 'translate(-3px,-2px) scale(.82)'; setTimeout(() => (c.style.transform = 'translate(-3px,-2px)'), 160);
    }, true);
    let timers = [];
    window.__cap = (step, text, ms) => {
      timers.forEach(clearTimeout); timers = [];
      cap.style.opacity = 1; cap.querySelector('.st').textContent = step;
      const parts = text.match(/[^.!?:]+[.!?:]*\s*/g).reduce((a, p) => { // short chunks, ~120 chars
        if (a.length && (a[a.length - 1] + p).length < 125) a[a.length - 1] += p; else a.push(p); return a; }, []);
      const total = parts.reduce((n, p) => n + p.length, 0); let t = 0;
      parts.forEach((p) => { timers.push(setTimeout(() => (cap.querySelector('.tx').textContent = p.trim()), t)); t += ms * p.length / total; });
    };
    const mk = document.createElement('div');
    Object.assign(mk.style, { position: 'fixed', right: '0', bottom: '0', width: '8px', height: '8px', zIndex: 2147483647, background: 'rgb(0,0,0)', pointerEvents: 'none' });
    document.body.appendChild(mk);
    window.__mark = (i) => { const g = 20 + i * 12; mk.style.background = `rgb(${g},${g},${g})`; };
    window.__card = (html) => {
      let k = document.getElementById('__card');
      if (!html) { if (k) { k.style.opacity = 0; setTimeout(() => k.remove(), 650); } return; }
      if (!k) { k = document.createElement('div'); k.id = '__card'; document.body.appendChild(k); }
      k.innerHTML = html; k.style.opacity = 1;
    };
    window.__ring = (sel, ms = 2500, pad = 6) => {
      const el = typeof sel === 'string' ? document.querySelector(sel) : sel; if (!el) return;
      const b = el.getBoundingClientRect(); const r = document.createElement('div'); r.className = '__ring';
      Object.assign(r.style, { left: b.left - pad + 'px', top: b.top - pad + 'px', width: b.width + 2 * pad + 'px', height: b.height + 2 * pad + 'px' });
      document.body.appendChild(r); setTimeout(() => r.remove(), ms);
    };
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
};

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, colorScheme: 'light',
    recordVideo: { dir: 'raw', size: { width: W, height: H } }, permissions: ['clipboard-read', 'clipboard-write'], acceptDownloads: true });
  await ctx.addInitScript(OVERLAY);
  const t0 = Date.now();
  const page = await ctx.newPage();
  page.on('dialog', (d) => d.dismiss());
  const wait = (ms) => page.waitForTimeout(ms);
  const offsets = [];
  let mx = W / 2, my = H / 2;

  async function moveTo(target, { steps = 28, dx = 0.5, dy = 0.5 } = {}) {
    const loc = typeof target === 'string' ? page.locator(target).first() : target;
    await loc.evaluate((e) => e.scrollIntoView({ behavior: 'smooth', block: 'nearest' })).catch(() => {});
    await wait(350);
    const b = await loc.boundingBox(); if (!b) return null;
    const x = b.x + b.width * dx, y = b.y + b.height * dy;
    await page.mouse.move(x, y, { steps }); mx = x; my = y; return loc;
  }
  async function click(target, opts) {
    const loc = await moveTo(target, opts); if (!loc) return console.log('MISS', target);
    await wait(250); await page.mouse.down(); await wait(90); await page.mouse.up(); await wait(400);
  }
  async function hover(target, ms = 900, ring = false) {
    const loc = await moveTo(target); if (!loc) return console.log('MISS', target);
    if (ring) await loc.evaluate((e, ms) => window.__ring(e, ms), ms + 400);
    await wait(ms);
  }
  const ring = (sel, ms = 2500) => page.evaluate(([s, m]) => window.__ring(s, m), [sel, ms]);
  const type = async (text, delay = 85) => page.keyboard.type(text, { delay });
  const scrollTo = async (y) => { await page.evaluate((y) => window.scrollTo({ top: y, behavior: 'smooth' }), y); await wait(900); };
  const scrollEl = async (sel, block = 'start') => { await page.locator(sel).first().evaluate((e, b) => e.scrollIntoView({ behavior: 'smooth', block: b }), block); await wait(1000); };
  const row = (name) => page.locator('tr[data-href]', { hasText: name }).first();
  let AID = null;

  async function scene(id, fn) {
    const [, step, text] = SCENES.find((s) => s[0] === id);
    const ms = D[id] * 1000;
    const start = Date.now() - t0; offsets.push([id, start / 1000]);
    await page.evaluate((i) => window.__mark(i), SCENES.findIndex((s) => s[0] === id));
    await page.evaluate(([a, b, c]) => window.__cap(a, b, c), [step, text, ms]);
    await fn();
    const rem = ms + 800 - (Date.now() - t0 - start);
    if (rem > 0) await wait(rem);
    console.log(id, 'start', (start / 1000).toFixed(1), 'len', ((Date.now() - t0 - start) / 1000).toFixed(1));
  }

  await page.goto(U); await page.waitForSelector('#login-form'); await wait(400);
  await page.mouse.move(mx, my);

  await scene('intro', async () => {
    await page.evaluate(() => window.__card(`<div class="tick">✓</div><h1>Lab Grader</h1>
      <p class="sub">Auto-grading for programming lab assignments from Google Classroom</p>
      <div class="badges"><span>C</span><span>C++</span><span>Python</span><span>Java</span></div>`));
  });
  await scene('how', async () => {
    const steps = [['1', 'Fetch', 'PDF, Word, Google Docs, screenshots and code files from Classroom'],
      ['2', 'Extract & repair', 'One program per question; fixes Word damage; OCR on screenshots'],
      ['3', 'Run in sandbox', 'Isolated Docker containers against your test cases'],
      ['4', 'Verify outputs', 'Pasted output vs. what the code really prints'],
      ['5', 'Similarity', 'Every pair compared, even with renamed variables'],
      ['6', 'Review & publish', 'Dashboard, CSV export, grades back to Classroom']];
    await page.evaluate((st) => window.__card(`<h2>How it works</h2><div class="grid">${st.map(([n, t, d]) => `<div><b>${n}</b><i>${t}</i><small>${d}</small></div>`).join('')}</div>`), steps);
    const at = [0.08, 0.27, 0.48, 0.62, 0.76, 0.88]; // where each step is spoken
    let prev = 0;
    for (let i = 0; i < 6; i++) {
      await wait((at[i] - prev) * D.how * 1000); prev = at[i];
      await page.evaluate((i) => document.querySelectorAll('#__card .grid div')[i].classList.add('on'), i);
    }
  });
  await scene('login', async () => {
    await page.evaluate(() => window.__card(null)); await wait(900);
    await ring('#login .login-card', 2500); await wait(1800);
    await click('input[name=username]'); await type('ta');
    await click('input[name=password]'); await type('demo1234', 70);
    await wait(500);
    await click('#login-form button');
    await page.waitForSelector('#app:not(.hidden)'); await page.waitForSelector('.bento', { timeout: 30000 });
  });
  await scene('home', async () => {
    await wait(600);
    for (const t of await page.locator('.bento > .tile').all()) await hover(t, 1300, true);
    await hover('#h-q', 900, true); await hover('#h-status', 800, true); await hover('#h-sort', 800, true);
    await hover('a.arow', 1200, true);
  });
  await scene('refresh', async () => {
    await click('#sync'); await wait(2200);
    await hover('#courses', 2000, true);
    await hover('#courses a[href^="#/a/"]', 1500);
  });
  await scene('cmdk', async () => {
    await click('#open-cmdk'); await wait(800);
    await type('Sorting', 120); await wait(1600);
    await page.keyboard.press('Enter');
    await page.waitForSelector('#grade');
    AID = (await page.evaluate(() => location.hash)).match(/#\/a\/(\d+)/)[1];
  });
  await scene('assign', async () => {
    await wait(700);
    await hover('#grade', 1700, true); await hover('a[href$="export.csv"]', 1400, true); await hover('#publish', 1400, true);
    await hover('.tabs', 2200, true);
  });
  await scene('tests', async () => {
    await click('.tab[data-tab=tests]'); await page.waitForSelector('#import'); await wait(800);
    await click('#import');
    await page.waitForSelector('.qblock', { timeout: 30000 }); await wait(1500);
    await hover('.qblock', 2500, true);
    await hover('.qblock tr[data-t] textarea', 1200);
    await hover('.qblock tr[data-t] input[type=checkbox]', 1800, true);
    await scrollEl('.qblock >> nth=1', 'center'); await wait(1500);
    await scrollEl('#addq', 'center'); await hover('#addq', 1500, true);
    await scrollTo(0);
  });
  await scene('settings', async () => {
    await click('.tab[data-tab=settings]'); await page.waitForSelector('#settings'); await wait(800);
    for (const f of (await page.locator('#settings label').all()).slice(0, 5)) { await hover(f, 1300, true); }
    await hover('#settings button[type=submit]', 1000, true);
    await scrollTo(0);
  });
  await scene('grade', async () => {
    await click('.tab[data-tab=results]'); await wait(1200);
    await click('#grade');
    await page.waitForSelector('#job .job[data-status=done]', { timeout: 120000 });
    await wait(1200);
  });
  await scene('results', async () => {
    await hover('.summary > div >> nth=0', 1300, true); await hover('.summary > div >> nth=1', 1300, true);
    await hover('.summary .review', 1500, true); await hover('.summary > div >> nth=3', 1200, true);
    await hover('.summary .hist', 1800, true);
    await scrollEl('.chips', 'start');
    await hover(row('Ananya Bose'), 1600, true);
    await hover(row('Kunal Ghosh'), 1800, true);
  });
  await scene('filters', async () => {
    await click('.chip[data-f=review]'); await wait(1500);
    await hover(row('Kunal Ghosh'), 2000, true); await hover(row('Ishita Roy'), 2200, true);
    await click('.chip[data-f=all]'); await wait(600);
    await click('.sort[data-sort=score]'); await wait(1600);
    await click('input.search'); await type('Aman', 140); await wait(1500);
  });
  await scene('student', async () => {
    await click(row('Aman Gupta')); await page.waitForSelector('#ovr'); await wait(1200);
    await hover('.sheet:has-text("Things to check")', 3500, true);
    await scrollEl('section:has-text("Question 2")', 'start'); await wait(600);
    await hover('section:has-text("Question 2") .run-head', 1500, true);
    await moveTo('section:has-text("Question 2") pre, section:has-text("Question 2") table'); await wait(2000);
  });
  await scene('feedback', async () => {
    await scrollEl('#fb', 'center'); await hover('#fb', 2200, true);
    await click('#copyfb'); await wait(1500);
    await scrollTo(0); await wait(400);
    await click('#ovr input'); await type('15', 200); await wait(500);
    await click('#ovr button[type=submit]'); await wait(1800);
    await click('#reviewed'); await wait(1500);
  });
  await scene('repair', async () => {
    await page.evaluate((a) => (location.hash = `#/a/${a}/results`), AID); await page.waitForSelector('tr[data-href]'); await wait(800);
    await click(row('Sneha Paul')); await page.waitForSelector('#ovr'); await wait(1200);
    await hover('p:has-text("While reading the submission")', 2500, true);
    await hover('text=Fixed: auto-capitalised', 2500, true);
    await click('[data-fix] >> nth=0'); await wait(2500);
    await hover('[data-save]', 1500, true);
    await click('[data-cancel]'); await wait(800);
  });
  await scene('similar', async () => {
    await page.evaluate((a) => (location.hash = `#/a/${a}/results`), AID); await page.waitForSelector('.tab[data-tab=similarity]'); await wait(600);
    await click('.tab[data-tab=similarity]'); await page.waitForSelector('.sim-group'); await wait(1200);
    await hover('.sim-group >> nth=0', 1500, true);
    await click('.sim-row >> nth=0'); await wait(1200);
    await click('a[href^="#/p/"] >> nth=0'); await page.waitForSelector('[data-v=cleared]'); await wait(1500);
    await hover('.sheet:has-text("Rohit Mondal") >> nth=-1', 2500);
    await click('[data-pair] >> nth=1'); await wait(2000);
    await hover('[data-v=confirmed]', 1200, true);
    await click('[data-v=cleared]'); await wait(1500);
  });
  await scene('publish', async () => {
    await page.evaluate((a) => (location.hash = `#/a/${a}/results`), AID); await page.waitForSelector('#publish'); await wait(800);
    await click('a[href$="export.csv"]'); await wait(2500);
    await hover('#publish', 3500, true);
    await hover('#job, .summary', 1500);
  });
  await scene('extras', async () => {
    await scrollTo(0);
    await click('#me'); await wait(1200);
    await hover('#svc', 1400, true);
    await click('[data-theme-pick=dark]'); await wait(2200);
    await click('[data-theme-pick=light]'); await wait(800);
    await click('#svc'); await page.waitForSelector('text=Code sandbox'); await wait(3000);
    await click('#admin-link'); await wait(3500);
  });
  await scene('outro', async () => {
    await page.evaluate(() => window.__card(`<div class="tick">✓</div><h2>Get started</h2>
      <pre><em>$</em> make up\n<em>→</em> open http://localhost:8000</pre>
      <div class="badges"><span>Sign in</span><span>Refresh from Classroom</span><span>Check tests</span><span>Grade all</span></div>`));
  });
  await wait(1500);

  fs.writeFileSync('offsets.json', JSON.stringify(offsets));
  const vpath = await page.video().path();
  await ctx.close(); await browser.close();
  fs.writeFileSync('rawpath.txt', vpath);
  console.log('video', vpath);
})();
