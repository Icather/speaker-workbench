/* Logic test for 声纹标注台 — DOM stubs + vm sandbox. */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const DIR = path.resolve(__dirname, '..');   // repo root — no absolute paths

/* ---------- DOM stubs ---------- */
const ctx2d = { fillRect(){}, fillText(){}, strokeRect(){}, beginPath(){},
                moveTo(){}, lineTo(){}, stroke(){}, clearRect(){} };
function mkEl(tag) {
  const el = {
    tagName: (tag || 'div').toUpperCase(), textContent: '', innerHTML: '', value: '',
    style: {}, dataset: {}, open: false, width: 0, height: 0,
    clientWidth: 800, clientHeight: 120,
    classList: { _s: new Set(), add(x){this._s.add(x);}, remove(x){this._s.delete(x);},
                 toggle(x,f){ f?this._s.add(x):this._s.delete(x); return !!f; },
                 contains(x){return this._s.has(x);} },
    appendChild(){}, removeChild(){}, click(){}, focus(){}, select(){}, close(){},
    showModal(){}, scrollIntoView(){}, setAttribute(){}, removeAttribute(){},
    addEventListener(){}, removeEventListener(){},
    querySelector(){ return null; }, querySelectorAll(){ return []; },
    getBoundingClientRect(){ return { width: 800, height: 120, left: 0, top: 0 }; },
    getContext(){ return ctx2d; },
  };
  return el;
}
const EL = {};
const document_ = {
  getElementById: id => EL[id] || (EL[id] = mkEl('div')),
  querySelectorAll: () => [], querySelector: () => null,
  createElement: mkEl, addEventListener(){}, title: '', body: mkEl('body'),
};
class AudioStub {
  constructor(src){ this.src = src; this.paused = true; this.currentTime = 0;
                    this.playbackRate = 1; this.ended = false; }
  play(){ this.paused = false; return Promise.resolve(); }
  pause(){ this.paused = true; }
  addEventListener(){}
}
const store = {};
const sandbox = {
  console, setTimeout, clearTimeout, setInterval, clearInterval,
  document: document_, window: { addEventListener(){}, TAPE_DATA: null, location:{protocol:'file:'} },
  location: { protocol: 'file:' }, localStorage: {
    getItem: k => (k in store ? store[k] : null), setItem: (k,v) => { store[k]=v; },
    removeItem: k => { delete store[k]; } },
  Audio: AudioStub, atob, btoa, fetch: () => Promise.resolve({}),
  Blob: function(){}, URL: { createObjectURL: () => 'blob:x' },
  FileReader: function(){ this.readAsText = ()=>{}; },
  navigator: { userAgent: 'node' },
};
sandbox.window.document = document_;
sandbox.globalThis = sandbox;
const ctx = vm.createContext(sandbox);

/* ---------- load data + app code ---------- */
vm.runInContext(fs.readFileSync(path.join(DIR, 'data.js'), 'utf8'), ctx, {filename:'data.js'});

// browsers auto-expose every element id as a global — emulate that
const htmlSrc = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
for (const m of htmlSrc.matchAll(/id="([^"]+)"/g)) {
  ctx[m[1]] = document_.getElementById(m[1]);
}

let app = htmlSrc;
app = app.match(/<script>([\s\S]*?)<\/script>/)[1];
app = app.replace(/^\(function boot\(\)\{[\s\S]*$/m, '');   // strip boot() IIFE
const exportTail = `
globalThis.__T = {D,S,CONF,RANK,GIDS,sortGids,visibleGids,buildClips,segsByGroup,segsByAudio,
  nameOf,isDone,esc,fmt,effGroup,keyOf,candGroups,AUD,REF:null};
`;
try { vm.runInContext(app + exportTail, ctx, {filename:'app.js'}); }
catch (e) { console.log('❌ app 代码执行失败：', e.message); process.exit(1); }

/* ---------- assertions ---------- */
const T = ctx.__T;
let fail = 0;
const ok = (cond, msg) => { console.log((cond ? '✓ ' : '❌ ') + msg); if(!cond) fail++; };

console.log('=== 数据完整性 ===');
// Deliberately data-agnostic: the same test must pass on the demo set and on
// a real corpus, so we assert invariants instead of magic numbers.
ok(T.D.audios.length >= 1, `录音 ${T.D.audios.length} 份`);
ok(T.D.segs.length >= 1, `句段 ${T.D.segs.length}`);
ok(T.GIDS.length >= 1, `声纹组 ${T.GIDS.length}`);

const gset = new Set(T.GIDS);
const badG = T.D.segs.filter(s => s.g && !gset.has(s.g));
ok(badG.length === 0, `所有 segs.g 都能在 groups 里找到（越界 ${badG.length}）`);

const noClipGroup = T.GIDS.filter(g => !(T.segsByGroup[g] || []).length);
ok(noClipGroup.length === 0, `每个组至少有一段（空组 ${noClipGroup.length}）`);

console.log('\n=== 置信度分布 ===');
const cnt = {A:0,B:0,C:0};
T.GIDS.forEach(g => cnt[T.CONF[g]]++);
console.log(`   A=${cnt.A} B=${cnt.B} C=${cnt.C}`);
ok(cnt.A + cnt.B + cnt.C === T.GIDS.length, `置信度分档覆盖全部组（A+B+C=${cnt.A + cnt.B + cnt.C}）`);

console.log('\n=== 筛选与排序 ===');
for (const f of ['key','A','AB','cross','undone','all']) {
  T.S.filt = f;
  const l = T.visibleGids();
  console.log(`   filt=${f.padEnd(7)} → ${l.length} 组`);
  ok(l.length > 0, `filt=${f} 非空`);
}
T.S.filt = 'all';
const all = T.visibleGids();
const undoneFirst = all.every((g,i) => i===0 || !(T.isDone(all[i-1]) && !T.isDone(g)));
ok(undoneFirst, '未认的组排在前面');
const durDesc = (() => {   // within A-rank & same cross-count, duration descends
  for (let i=1;i<all.length;i++){
    const a=all[i-1], b=all[i];
    const ga=T.D.groups[a], gb=T.D.groups[b];
    const sameRank = T.CONF[a]===T.CONF[b] && (ga['出现录音'].length===gb['出现录音'].length)
                     && !T.isDone(a) && !T.isDone(b);
    if (sameRank && ga['时长min'] < gb['时长min']) return false;
  }
  return true;
})();
ok(durDesc, '同级同跨度内按总时长降序');

console.log('\n=== 连播队列 ===');
for (const g of all.slice(0, 6)) {
  const c = T.buildClips(g);
  const recs = [...new Set(c.map(x=>x.a))].join(',');
  const solid = c.filter(x => x.e - x.s >= 1.2).length;
  console.log(`   ${g}  片段 ${String(c.length).padStart(3)}  录音 [${recs}]  实心段 ${solid}`);
  ok(c.length > 0, `${g} 有片段`);
  ok(c.every(x => x.s < x.e), `${g} 时间区间合法`);
  ok(c.every(x => T.AUD[x.a]), `${g} 每段的录音都存在`);
}
const cross = all.find(g => T.D.groups[g]['出现录音'].length >= 2);
if (cross) {
  const cc = T.buildClips(cross);
  const seen = new Set(cc.map(x=>x.a));
  ok(seen.size >= 2, `跨录音组 ${cross} 的连播队列真的跨了 ${seen.size} 份录音`);
} else {
  console.log('   （本数据集没有跨录音组，跳过）');
}

console.log('\n=== 工具函数 ===');
ok(T.fmt(0) === '00:00', `fmt(0)=${T.fmt(0)}`);
ok(T.fmt(95) === '01:35', `fmt(95)=${T.fmt(95)}`);
ok(T.fmt(3725) === '1:02:05', `fmt(3725)=${T.fmt(3725)}`);
ok(T.esc('<a>&"') === '&lt;a&gt;&amp;&quot;', `esc 转义正确`);
ok(T.keyOf(0).includes('|'), `keyOf 形如 tag|start（${T.keyOf(0)}）`);

console.log('\n=== 校对模式候选 ===');
T.S.pAid = T.D.audios.find(a => a.n > 0).id;
const cand = T.candGroups();
console.log(`   ${T.S.pAid} 的候选组 ${cand.length} 个，前 8：${cand.slice(0,8).join(' ')}`);
ok(cand.length > 0, '候选组列表非空');

console.log('\n=== 每个录音的句数与组数 ===');
for (const a of T.D.audios) {
  const n = (T.segsByAudio[a.id] || []).length;
  const gs = new Set((T.segsByAudio[a.id]||[]).map(i=>T.effGroup(i)).filter(Boolean));
  console.log(`   ${a.id.padEnd(6)} ${String(n).padStart(4)} 句  ${String(gs.size).padStart(4)} 组  ${a.hasSrt?'':'⚠️无转写稿'}`);
}

console.log(fail === 0 ? '\n✅ 全部通过' : `\n❌ ${fail} 项失败`);
process.exit(fail === 0 ? 0 : 1);
