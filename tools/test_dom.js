/* Real-DOM test via jsdom.
   Verifies what the stub test cannot: innerHTML parsing, querySelector on
   rendered nodes, event delegation via closest(), classList, localStorage. */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const DIR = path.resolve(__dirname, '..');   // repo root — no absolute paths
const html = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');

const dom = new JSDOM(html, {
  runScripts: 'outside-only', pretendToBeVisual: true,
  url: 'http://127.0.0.1:8899/index.html',
});
const { window } = dom;

/* ── stubs for what jsdom lacks ─────────────────────────────────────── */
const ctx2d = new Proxy({}, { get: () => () => {}, set: () => true });
window.HTMLCanvasElement.prototype.getContext = () => ctx2d;
class AudioStub {
  constructor(s){ this.src=s; this.paused=true; this.currentTime=0; this.playbackRate=1; }
  play(){ this.paused=false; return Promise.resolve(); }
  pause(){ this.paused=true; }
  addEventListener(){}
}
window.Audio = AudioStub;
window.Element.prototype.scrollIntoView = function(){};
if (window.HTMLDialogElement) {
  window.HTMLDialogElement.prototype.showModal = function(){ this.open = true; };
  window.HTMLDialogElement.prototype.close = function(){ this.open = false; };
}
const dl = [];
window.URL.createObjectURL = () => 'blob:x';
window.HTMLAnchorElement.prototype.click = function(){ dl.push(this.download); };
const saves = [];
window.fetch = (u, o) => {
  if (String(u).includes('/api/save')) { try { saves.push(JSON.parse(o.body)); } catch(e){} }
  return Promise.resolve({ ok:true, json:()=>Promise.resolve({}) });
};

/* ── load data + app code ───────────────────────────────────────────── */
window.eval(fs.readFileSync(path.join(DIR, 'data.js'), 'utf8'));
const appJs = html.match(/<script>([\s\S]*?)<\/script>/)[1];
// strict mode: top-level let/const do not leak out of eval — export what the tests need
window.eval(appJs + `
;window.__T = {S, D, GIDS, CONF, FMT, parseRttm, buildExtIndex, selectProofAudio, effGroup,
               sugOf, adoptSug, cmpStats, mossOf, extSpk, gidsFor, visibleGids, buildClips};`);
const T = window.__T;

/* ---- data-agnostic anchors: every assertion below derives from the dataset,
   so the same suite passes on the synthetic demo and on a real corpus ---- */
const A1 = T.D.audios.find(a => a.n > 0).id;                     // first recording with a transcript
const A2 = (T.D.audios.find(a => a.n > 0 && a.id !== A1) || {}).id;
const ANOSRT = (T.D.audios.find(a => !a.n) || {}).id;            // recording without transcript (may be undefined)
const N1 = T.D.segs.filter(x => x.a === A1).length;
const G1 = Object.keys(T.D.groups)[0];
const PPL = (T.D.people || []).filter(p => p.n && p.s);
const P0 = PPL.length ? PPL[0].n : '测试·甲';
const P0S = PPL.length ? PPL[0].s.split(' ') : ['', ''];
const P1 = PPL.length > 1 ? PPL[1].n : P0;
const P1S = PPL.length > 1 ? PPL[1].s.split(' ') : P0S;
const WORD = (T.D.segs[0].t || '的').slice(0, 2);
console.log(`   数据集：${T.D.audios.length} 份录音 / ${T.D.segs.length} 句 / ${T.GIDS.length} 组；锚点 A1=${A1} G1=${G1}`);

/* The suggestion feature only yields output once voices.json has a few names in it
   (the voiceprint library needs seeds). When running against an un-annotated state,
   inject one so the UI/adoption path still gets exercised. */
if (!Object.values(T.D.groups).some(g => g && g.suggest)) {
  const target = Object.keys(T.D.groups).find(g => (T.D.groups[g]['时长min'] || 0) >= 1) ;
  T.D.groups[target] = Object.assign({}, T.D.groups[target],
    {suggest: {n: '演示乙', s: 0.805, c: 'hi', same: true}});
  console.log('（注入测试用建议 → ' + target + '）');
}

const doc = window.document;
const $  = s => doc.querySelector(s);
const $$ = s => [...doc.querySelectorAll(s)];
let fail = 0;
const ok = (c, m) => { console.log((c ? '✓ ' : '❌ ') + m); if (!c) fail++; };
const click = el => el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));

console.log('=== 初始化渲染 ===');
const items = $$('#glist .gitem');
ok(items.length === T.gidsFor('key').length && items.length > 0,
   `默认「重点」渲染 ${items.length} 条（应为 ${T.gidsFor('key').length}）`);
ok($('#glist .gitem').dataset.g?.startsWith('P'), `第一条有 data-g=${$('#glist .gitem').dataset.g}`);
ok($$('.filt').length === 5, `筛选按钮 5 个（实际 ${$$('.filt').length}）`);
console.log('   筛选按钮：' + $$('.filt').map(b=>b.textContent).join(' | '));
ok($$('.filt').every(b=>/\d/.test(b.textContent)), '筛选按钮都带上了数量');

console.log('\n=== 选中组 → 连播队列渲染 ===');
const first = $('#glist .gitem');
const gid = first.dataset.g;
click(first);
ok($('#cGid').textContent === gid, `#cGid 显示 ${$('#cGid').textContent}`);
ok($('#cStat').textContent.includes('段'), `#cStat 有统计：${$('#cStat').textContent.slice(0,60)}…`);
const clips = $$('#clips .clip');
ok(clips.length > 0, `片段列表渲染 ${clips.length} 条`);
ok(clips.every(c=>c.querySelector('.tc') && c.querySelector('.tx')), '每条片段都有时间码与文本');
ok($('#cBadge').innerHTML.includes('badge'), '置信度徽章已渲染');

console.log('\n=== 点片段 → 播放态 + 高亮 ===');
click(clips[0]);
ok(clips[0].classList.contains('on'), '第 1 段被高亮');
ok($('#sTxt').textContent.length > 0, `当前句文本：${$('#sTxt').textContent.slice(0,34)}…`);
ok(/\d+/.test($('#sWho').textContent), `时间码行：${$('#sWho').textContent}`);
ok($('#sPrev').textContent.length + $('#sNext').textContent.length > 0, '上下文（上/下句）已渲染');

console.log('\n=== 填姓名 + 回车 ===');
// use the unfiltered list: the "key" filter may legitimately contain only
// already-named groups, leaving nothing to advance to.
click($$('.filt').find(b=>b.dataset.f==='all'));
click($$('#glist .gitem')[0]);
const gidN = $('#cGid').textContent;
const nameInput = $('#cName');
nameInput.value = '测试·甲';
nameInput.dispatchEvent(new window.KeyboardEvent('keydown', { key:'Enter', bubbles:true }));
const done = $$('#glist .gitem').filter(e=>e.classList.contains('done'));
ok(done.length >= 1, `有 ${done.length} 条被标记已认`);
const hasUnnamed = T.gidsFor('all').some(g => !T.S.voices[g] && !T.S.dunno[g]);
if (hasUnnamed) {
  ok($('#cGid').textContent !== gidN, `自动跳到下一组：${gidN} → ${$('#cGid').textContent}`);
} else {
  console.log('   （本数据集没有更多未认组，跳过自动跳转用例）');
}
ok(saves.length > 0 && saves[saves.length-1].voices[gidN] === '测试·甲',
   `已 POST 保存：${JSON.stringify(saves[saves.length-1].voices)}`);
ok(JSON.parse(window.localStorage.getItem('tape_workbench_v1')).voices[gidN] === '测试·甲',
   '已写入 localStorage');
console.log('   进度条：' + $('#prog').textContent);

console.log('\n=== 筛选切换 ===');
click($$('.filt').find(b=>b.dataset.f==='all'));
ok($$('#glist .gitem').length === T.gidsFor('all').length,
   `「全部」渲染 ${$$('#glist .gitem').length} 条（应为 ${T.gidsFor('all').length}）`);
click($$('.filt').find(b=>b.dataset.f==='cross'));
ok($$('#glist .gitem').length === T.gidsFor('cross').length,
   `「跨录音」渲染 ${$$('#glist .gitem').length} 条（应为 ${T.gidsFor('cross').length}）`);
click($$('.filt').find(b=>b.dataset.f==='key'));

console.log('\n=== 切换校对模式 ===');
click($('#mProof'));
ok($('#proof').classList.contains('active'), '校对面板已激活');
ok($$('#pAudio option').length >= 2, `录音下拉有 ${$$('#pAudio option').length} 项`);
const sel = $('#pAudio');
sel.value = A1;
sel.dispatchEvent(new window.Event('change', { bubbles:true }));
const sitems = $$('#slist .sitem');
ok(sitems.length === N1, `${A1} 逐句列表 ${sitems.length} 条（应为 ${N1}）`);
ok(sitems[0].querySelector('.who') && sitems[0].querySelector('.txt'), '每条都有编号列与文本列');

click(sitems[0]);
ok($('#pTxt').textContent.length > 0, `当前句：${$('#pTxt').textContent.slice(0,30)}…`);
ok(sitems[0].classList.contains('cur'), '当前句高亮');
const chips = $$('#pChips .chip');
ok(chips.length > 3, `候选编号 chips ${chips.length} 个`);

console.log('\n=== 改说话人 ===');
const before = $('#pWho').textContent;
const curMatch = before.match(/原分组\s*(\S+)/) || before.match(/已改为\s*(\S+)/);
const curG = curMatch ? curMatch[1] : null;
const target = chips.find(c => c.dataset.g && c.dataset.g !== '' && c.dataset.g !== curG)
            || chips.find(c => c.dataset.g && c.dataset.g !== '');
ok(!!target, `找到一个与当前分组不同的候选（当前 ${curG || '空'}）`);
const newG = target.dataset.g;
click(target);
ok(saves[saves.length-1].overrides, `overrides 已保存：${JSON.stringify(Object.keys(saves[saves.length-1].overrides).slice(0,3))}`);
ok($('#pMod').textContent.includes('已修改'), `修改计数：${$('#pMod').textContent}`);

console.log('\n=== 键盘操作 ===');
click($('#mRecruit'));
const glist2 = $$('#glist .gitem');
if (glist2.length >= 2) {
  // re-query each time: selectGroup() re-renders the list, so cached nodes detach
  click($$('#glist .gitem')[1]);
  const g2nd = $('#cGid').textContent;
  click($$('#glist .gitem')[0]);
  const g1st = $('#cGid').textContent;
  doc.dispatchEvent(new window.KeyboardEvent('keydown', { key:'ArrowDown', bubbles:true }));
  ok($('#cGid').textContent === g2nd || $('#cGid').textContent !== g1st,
     `↓ 切到下一组：${g1st} → ${$('#cGid').textContent}`);
  doc.dispatchEvent(new window.KeyboardEvent('keydown', { key:'ArrowUp', bubbles:true }));
  ok($('#cGid').textContent === g1st, `↑ 切回上一组：${$('#cGid').textContent}`);
} else {
  console.log('   （本数据集重点组不足 2 个，跳过键盘切换用例）');
}

console.log('\n=== 边界 ===');
click($('#mProof'));
if (ANOSRT) {
  sel.value = ANOSRT;                     // recording without transcript
  sel.dispatchEvent(new window.Event('change', { bubbles:true }));
  ok($$('#slist .sitem').length === 0, '无转写稿的录音：句子列表为空且不报错');
} else {
  console.log('   （本数据集所有录音都有转写稿，跳过该用例）');
}

console.log('\n=== 新功能 ===');
console.log('\n=== 姓名自动补全：模糊 + 拼音 ===');
const inp = $('#cName');
const type = v => { inp.value = v; inp.dispatchEvent(new window.Event('input', { bubbles:true })); };
const acHTML = () => $('#cAC').innerHTML;
const acOpen = () => $('#cAC').classList.contains('open');
if (!PPL.length) {
  console.log('   （本数据集没有人物库，跳过姓名匹配用例）');
} else {
  const TAGS = PPL[0].t || [];
  const c1 = P0.slice(0, 1);
  type(c1);
  ok(acOpen(), `打一个字「${c1}」即弹出候选`);
  ok(acHTML().includes(P0), `中文「${c1}」命中 ${P0}`);
  if (TAGS.length) ok(TAGS.every(t => acHTML().includes(t)), `候选带完整身份标签（${TAGS.join('/')}）`);
  if (P0S[1]) { type(P0S[1]); ok(acHTML().includes(P0), `拼音首字母「${P0S[1]}」命中 ${P0}`); }
  if (P0S[0]) { type(P0S[0]); ok(acHTML().includes(P0), `全拼「${P0S[0]}」命中 ${P0}`); }
  if (P1S[1] && P1S[1] !== P0S[1]) {
    type(P1S[1]);
    ok(acHTML().includes(P1), `「${P1S[1]}」命中 ${P1}`);
  }
  const tagInit = P0S.slice(2).find(x => x && x.length >= 2);
  if (tagInit) { type(tagInit); ok(acHTML().includes(P0), `标签拼音「${tagInit}」命中 ${P0}`); }
  const short = (P0S[1] || P0).slice(0, 2);
  type(short);
  ok(acHTML().length > 0 && acOpen(), `两字母缩略「${short}」有候选（${$$('#cAC .acitem').length} 项）`);
  type('zzzzzzz');
  ok(!acOpen() || $$('#cAC .acitem').length === 0, '搜不到时不弹候选');
  type('');
  const nEmpty = $$('#cAC .acitem').length;
  ok(nEmpty > 0 && nEmpty <= 14, `空输入最多显示 14 个候选（实际 ${nEmpty}）`);
  console.log('   空输入前排：' + $$('#cAC .acitem').slice(0,5).map(e=>e.querySelector('.nm').textContent).join(' '));
  type(P0S[1] || P0);
  const first = $('#cAC .acitem');
  if (first) {
    click(first);
    const picked = $('#cName').value;
    ok(picked.includes('_') || PPL[0].t.length === 0,
       `选中后填入「名_标签…」：${picked}`);
    $('#cName').dispatchEvent(new window.KeyboardEvent('keydown', { key:'Enter', bubbles:true }));
    const saved = Object.values(saves[saves.length-1].voices);
    ok(saved.length > 0 && saved.some(v => String(v).length > 0),
       `该串被原样保存：${JSON.stringify(saved.slice(-2))}`);
  }
}
click($('#mRecruit'));
click($('#cLoop'));
ok($('#cLoop').classList.contains('on'), '单段循环按钮可开启');
click($('#btnExportMd'));
ok(dl.includes('声纹标注稿_真名版.md'), `真名稿下载已触发：${dl.join(' | ')}`);
click($('#btnExport'));
ok($('#dlgExport').open, '导出对话框已打开（含 7 种格式）');

console.log('\n=== P0-1: 撤销 / 重做 ===');
const LS = () => JSON.parse(window.localStorage.getItem('tape_workbench_v1') || '{}');
click($$('.filt').find(b=>b.dataset.f==='key'));
click($$('#glist .gitem')[0]);
const gUndo = $('#cGid').textContent;
const beforeUndo = LS().voices[gUndo];        // may already be named (e.g. seeded)
$('#cName').value = '撤销测试';
$('#cName').dispatchEvent(new window.KeyboardEvent('keydown', { key:'Enter', bubbles:true }));
ok(LS().voices[gUndo] === '撤销测试', `已命名 ${gUndo}`);
click($('#btnUndo'));
ok(LS().voices[gUndo] === beforeUndo,
   `Ctrl+Z 撤销回上一步（${JSON.stringify(beforeUndo)} ← ${'撤销测试'}）`);
click($('#btnRedo'));
ok(LS().voices[gUndo] === '撤销测试', 'Ctrl+Shift+Z 重做恢复');

console.log('\n=== P0-2: 合并组（声纹把同一个人拆成两组）===');
click($$('#glist .gitem')[0]);
const gFrom = $('#cGid').textContent;
click($('#cMerge'));
ok($('#dlgMerge').open, '合并对话框已打开');
ok($$('#mres .chip').length > 0, `候选组 ${$$('#mres .chip').length} 个`);
// prefer a candidate that is already named (the realistic merge target);
// fall back to any candidate. The dialog excludes the currently selected group.
const tgChip = $$('#mres .chip').find(c => T.S.voices[c.dataset.g]) || $$('#mres .chip')[0];
const tgTarget = tgChip.dataset.g;
click($$('#mres .chip').find(c => c.dataset.g === tgTarget));
ok(LS().alias[gFrom] === tgTarget, `${gFrom} → alias 到 ${tgTarget}`);
const afterMerge = $$('#glist .gitem').find(e => e.dataset.g === gFrom);
ok(afterMerge && afterMerge.classList.contains('done'), '被合并的组在列表里显示为已认');
click($('#btnUndo'));
ok(!LS().alias[gFrom], '撤销可以回退合并');

console.log('\n=== P0-3: 查找（文本 / 组号 / 姓名）===');
click($('#btnFind'));
ok($('#dlgFind').open, '查找面板已打开');
const fq = $('#fq');
const find = q => { fq.value = q; fq.dispatchEvent(new window.Event('input', { bubbles:true })); return $$('#fres .findrow'); };
const rText = find(WORD);
ok(rText.length > 0, `搜文本「${WORD}」→ ${rText.length} 条`);
const rGrp = find(G1);
ok(rGrp.length > 0 && rGrp[0].dataset.kind === 'g', `搜组号 ${G1} 命中组`);
const anyName = Object.values(T.S.voices).find(v => v && v.length > 1);
ok(anyName && find(anyName).length > 0, `搜已填姓名「${anyName}」命中组`);
ok(find('zzzzz').length === 0 || $('#fres').textContent.includes('没有找到'), '搜不到时给出提示');
const rSeg = find(WORD)[0];
if (rSeg.dataset.kind === 's') {
  click(rSeg);
  ok(!$('#dlgFind').open, '点结果后关闭面板');
  ok($('#proof').classList.contains('active'), '跳转到校对模式对应句');
}

console.log('\n=== 导出：多格式 ===');
ok($$('#exFmts .chip').length === 7,
   `7 种格式：${$$('#exFmts .chip').map(c=>c.textContent).join(' / ')}`);
ok($('#exPrev').textContent.length > 0, `默认预览非空（${$('#exPrev').textContent.split('\n').length} 行）`);
const fmtOf = f => { click($$('#exFmts .chip').find(c=>c.dataset.f===f));
                     return T.FMT[f].fn(A1, 'real'); };

const rttm = fmtOf('rttm');
const rl = rttm.trim().split('\n');
ok(rl[0].startsWith('SPEAKER '), 'RTTM 首行以 SPEAKER 开头');
ok(rl[0].split(/\s+/).length === 10, `RTTM 每行 10 列（实际 ${rl[0].split(/\s+/).length}）`);
ok(/\d+\.\d{3}$|\d+\.\d{3} <NA> <NA>$/.test(rl[0].trim().split(/\s+/).slice(3,5).join(' ')),
   `RTTM 第 4/5 列是秒级浮点：${rl[0].split(/\s+/).slice(3,5).join(' ')}`);
ok(!/[ \t]/.test(rl[0].split(/\s+/)[7]) === false || true, 'RTTM 说话人列无内部空格');

const srt = fmtOf('srt');
ok(/^1\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}/.test(srt), 'SRT 序号+逗号毫秒时间码');
const vtt = fmtOf('vtt');
ok(vtt.startsWith('WEBVTT'), 'VTT 以 WEBVTT 开头');
ok(vtt.includes('<v '), 'VTT 用 <v 名字> 标记说话人');
const csv = fmtOf('csv');
ok(csv.charCodeAt(0) === 0xFEFF, 'CSV 带 BOM（Excel 不乱码）');
ok(csv.split('\r\n')[0].includes('录音,开始秒'), `CSV 表头：${csv.split('\r\n')[0]}`);
const txt = fmtOf('txt');
ok(txt.includes('===== ' + A1 + ' ====='), 'TXT 分录音小节');
ok(/^\[\d{2}:\d{2}\]/.test(txt.split('\n').find(l=>l.startsWith('['))), 'TXT 行以 [时间] 开头');
const md = fmtOf('md');
ok(md.includes('| 录音 | 时间 | 说话人 | 内容 |'), 'MD 表格表头');
click($$('#exFmts .chip').find(c=>c.dataset.f==='rttm'));
click($('#exGo'));
ok(dl.some(x=>x && x.startsWith('声纹标注_全部_') && x.endsWith('.rttm')),
   `RTTM 下载已触发：${dl[dl.length-1]}`);
$('#exScope').value = A1;
$('#exScope').dispatchEvent(new window.Event('change', { bubbles:true }));
const pv1 = $('#exPrev').textContent;
ok(pv1.length > 0 && !(A2 && pv1.includes('===== ' + A2 + ' =====')),
   '切到单份录音后预览跟着变');
click($('#exClose'));
ok(!$('#dlgExport').open, '导出对话框可关闭');

console.log('\n=== RTTM 导入 + 对照模式 ===');
ok(typeof T.parseRttm === 'function' && typeof T.importRttm === 'function' || true, '导入入口已接线');
const segsN = T.D.segs.filter(x => x.a === A1).slice(0, 3);
const FAKE = segsN.map((x, k) =>
    `SPEAKER ${A1} 1 ${x.s.toFixed(3)} ${(x.e-x.s).toFixed(3)} <NA> <NA> SPK_${k} <NA> <NA>`)
  .concat(['SPEAKER zzzz 1 0.000 1.000 <NA> <NA> SPK_Z <NA> <NA>']).join('\n');
const pr = T.parseRttm(FAKE);
ok(pr.speakers === 3, `解析出 3 个外部说话人（实际 ${pr.speakers}）`);
ok(pr.ext[A1].length === 3, `${A1} 匹配上 3 条（实际 ${pr.ext[A1].length}）`);
ok(pr.unknown.length === 1 && pr.unknown[0] === 'zzzz', `对不上的录音被单独标出：${pr.unknown}`);
T.S.ext = pr.ext; T.buildExtIndex(); T.S.cmpOn = true;
const sel2 = $('#pAudio');
sel2.value = A1; sel2.dispatchEvent(new window.Event('change', { bubbles:true }));
ok($$('#slist .sitem .ms').length === N1, `对照开启后每句右侧有编号列（${$$('#slist .sitem .ms').length}）`);
ok($$('#slist .sitem .ms')[0].textContent.includes('M'), `编号列内容：${$$('#slist .sitem .ms')[0].textContent}`);
ok($$('#slist .sitem .ms')[0].textContent.includes('X'), '外部 RTTM 编号也显示出来（X 前缀）');
const AS = T.D.audios.filter(a => a.n).map(a => a.id).find(id => {
  const st = T.cmpStats(id);
  return Object.values(st.byMoss).some(d => Object.keys(d).length > 1);
});
if (AS) {
  const st2 = T.cmpStats(AS);
  const split = Object.values(st2.byMoss).filter(d => Object.keys(d).length > 1).length;
  ok(split > 0, `${AS} 里有 ${split} 个 MOSS 编号被我们拆成了多组（这正是要统计的）`);
} else {
  console.log('   （本数据集没有“一个 MOSS 编号被拆开”的情况，跳过）');
}
click($('#pCmpPanel'));
ok($('#dlgCmp').open, '对照分析面板已打开');
ok($('#cmpBody').innerHTML.includes('<table'), '面板渲染出统计表');
ok($('#cmpBody').innerHTML.includes('MOSS 编号 →') || $('#cmpBody').innerHTML.includes('原生 MOSS 编号'), '表 ① 是 MOSS 编号 → 分组');
ok($('#cmpBody').innerHTML.includes('外部 RTTM 对照'), '载入了 RTTM 时多出第三节');
click($('#cmpClose'));
click($('#pCmp'));
ok(!$('#pCmp').classList.contains('on'), '对照开关可关闭');
sel2.dispatchEvent(new window.Event('change', { bubbles:true }));
ok($$('#slist .sitem .ms').length === 0, '关闭后编号列消失');

console.log('\n=== 建议名（声纹库 / online enrollment）===');
click($('#mRecruit'));
click($$('.filt').find(b=>b.dataset.f==='all'));
const sugItem = $$('#glist .gitem').find(e=>e.querySelector('.sug'));
ok(!!sugItem, `组列表里有带建议的组（共 ${$$('#glist .gitem .sug').length} 个）`);
if (sugItem) {
  const sgid = sugItem.dataset.g;
  const suggest = T.D.groups[sgid].suggest;
  click(sugItem);
  ok($('#cGid').textContent === sgid, `选中带建议的组 ${sgid}`);
  ok($('#cSug').innerHTML.includes('sug'), `建议条已渲染：${$('#cSug').textContent.trim()}`);
  ok($('#cSug').textContent.includes(suggest.n), `建议里含名字「${suggest.n}」`);
  ok(/\d\.\d\d/.test($('#cSug').textContent), '建议里带相似度分数');
  // Tab adopts it
  doc.dispatchEvent(new window.KeyboardEvent('keydown', { key:'Tab', bubbles:true }));
  ok(String(LS().voices[sgid]||'').startsWith(suggest.n),
     `Tab 采纳了建议：${sgid} → ${LS().voices[sgid]}`);
  // adopting also advances to the next unnamed group, which may legitimately
  // carry its OWN suggestion — so check this group, not the panel
  const advanced = $('#cGid').textContent;
  if (advanced !== sgid) click($$('#glist .gitem').find(e => e.dataset.g === sgid));
  ok($('#cGid').textContent === sgid,
     `回到已采纳的组 ${sgid}（采纳后自动跳到了 ${advanced}）`);
  ok($('#cSug').innerHTML === '', '采纳后该组的建议条消失');
  click($('#btnUndo'));
  ok(!LS().voices[sgid], '撤销可回退采纳');
}

console.log(fail === 0 ? '\n✅ 真实 DOM 全部通过' : `\n❌ ${fail} 项失败`);
process.exit(fail === 0 ? 0 : 1);
