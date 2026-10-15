// Squeeze a built page: every inline script through terser (names that
// onclick="" attributes call stay as they are - only local names shrink),
// every <style> through csso, and the indentation of the markup dropped.
// Usage: node deploy/minify_page.js in.html out.html
const fs = require('fs');
const path = require('path');
const req = m => { try { return require(m); } catch (e) { return require(path.join(require('child_process').execSync('npm root -g').toString().trim(), m)); } };
const { minify } = req('terser');
const csso = req('csso');
(async () => {
  const [inp, out] = process.argv.slice(2);
  let s = fs.readFileSync(inp, 'utf8');
  const parts = [];
  const re = /<script(\s[^>]*)?>([\s\S]*?)<\/script>|<style(\s[^>]*)?>([\s\S]*?)<\/style>|<(pre|textarea)(\s[^>]*)?>[\s\S]*?<\/\5>/gi;
  let last = 0, m;
  while ((m = re.exec(s))) {
    parts.push({ html: s.slice(last, m.index) });
    if (m[2] !== undefined) {
      const attrs = m[1] || '';
      const code = m[2];
      if (/\bsrc=/.test(attrs) || /type=["'](?!text\/javascript|module)/i.test(attrs) || !code.trim()) parts.push({ raw: m[0] });
      else {
        const r = await minify(code, { compress: { passes: 2, keep_fargs: true, keep_fnames: true, keep_classnames: true, toplevel: false, unused: true },
                                       mangle: { toplevel: false, keep_fnames: true }, format: { inline_script: true, comments: false }, ecma: 2020 });
        parts.push({ raw: `<script${attrs}>${r.code}</script>` });
      }
    } else if (m[4] !== undefined) {
      parts.push({ raw: `<style${m[3] || ''}>${csso.minify(m[4], { restructure: false }).css}</style>` });
    } else parts.push({ raw: m[0] });
    last = re.lastIndex;
  }
  parts.push({ html: s.slice(last) });
  const res = parts.map(p => p.raw !== undefined ? p.raw : p.html.replace(/<!--(?!\[if)[\s\S]*?-->/g, '').replace(/\n[ \t]+/g, '\n').replace(/\n{2,}/g, '\n')).join('');
  fs.writeFileSync(out, res);
  console.log(`minified ${Math.round(s.length / 1024)} KB -> ${Math.round(res.length / 1024)} KB`);
})().catch(e => { console.error('minify failed:', e.message); process.exit(1); });
