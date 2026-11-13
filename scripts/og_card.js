// 링크 미리보기 로고 카드(1200×630) — 군산각 templates/assets/brand/og-card.png와 같은 배치. 일러스트 없이 상징+이름+주소.
// node og_card.js <out.png> <상징.svg> <한글 앞> <각> <로마자 앞> <gak> <도메인> <pretendard.css 절대경로> <강조색 #hex>
// 예: node og_card.js templates/assets/brand/og-card.png $PWD/templates/assets/brand/daegugak-symbol.svg 대구 각 Daegu gak daegu.webforai.kr $PWD/templates/assets/vendor/pretendard/pretendard.css "#9C493B"
// Playwright: require("playwright") (이미 깔려 있음). 강조색은 그 사이트 css의 --brand(없으면 .wm-em 색).
const { chromium } = require('playwright');
const fs = require('fs');
// args: outPng symbolSvg nameHead nameTail latinHead latinTail domain fontCss
const [out, sym, kh, kt, lh, lt, dom, css, em] = process.argv.slice(2);
const svg = fs.readFileSync(sym, 'utf8').replace('<svg ', '<svg class="sym" ');
const html = `<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="file://${css}">
<style>html,body{margin:0}body{width:1200px;height:630px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:34px;background:#F2F7FD;font-family:Pretendard,sans-serif}
.row{display:flex;align-items:center;gap:44px}.sym{width:auto;height:300px;display:block}
.t{display:flex;flex-direction:column;gap:6px}.k{font-weight:700;font-size:150px;line-height:1;letter-spacing:-.04em;color:#172033}.l{font-weight:700;font-size:62px;line-height:1.05;letter-spacing:-.01em;color:#172033}
.em{color:${em || '#2F6FC9'}}.dom{margin:0;font-size:30px;font-weight:400;color:#5F6878;letter-spacing:.01em}</style></head><body>
<div class="row">${svg}<div class="t"><div class="k">${kh}<span class="em">${kt}</span></div><div class="l">${lh}<span class="em">${lt}</span></div></div></div>
<p class="dom">${dom}</p></body></html>`;
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1200, height: 630 } });
  const f = out.replace(/\.png$/, '.html'); fs.writeFileSync(f, html); await p.goto('file://' + f, { waitUntil: 'load' }); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(300);
  await p.screenshot({ path: out }); await b.close();
})();
