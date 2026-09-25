# 参与贡献

[English](CONTRIBUTING.md) · [中文](CONTRIBUTING.zh-CN.md)

这份文件是变更的契约。无视它的 PR 会被要求改 —— 不是因为风格口味，而是因为这个仓库有两样东西它不肯拿来交换：**实测出来的数字**，和**一个在哪都能跑起来的 demo**。

- **这是什么** —— 说话人分离*之后*的那一层：把身份**跨**录音对齐，让人来命名，然后复用这些名字。
- **这不是什么** —— 不是分离器、不是转写器、不是字幕编辑器、也不是标注服务器。替代品看 [docs/FIELD-NOTES.zh-CN.md](docs/FIELD-NOTES.zh-CN.md) §4。
- **「小」本身是特性。** `index.html` 是一个文件、零运行时依赖。请保持这样。

**目录** · [准备](#准备) · [文件都在哪](#文件都在哪) · [改动对照表](#改动对照表) · [测试](#测试) · [唯一铁律](#唯一铁律数字不可商量) · [完整示例](#完整示例新增一种导出格式) · [提-pr](#提-pr) · [真正能帮上忙的事](#真正能帮上忙的事) · [会被拒绝的提议](#会被拒绝的提议) · [报告-bug](#报告-bug) · [安全与隐私](#安全与隐私) · [风格](#风格)

---

## 准备

三层，多数贡献只需要第一层。

| 你想做什么 | 你需要什么 |
|---|---|
| 跑起来点一点界面 | **只需要一个浏览器。** `./start.sh`（macOS/Linux）或 `start.bat`（Windows） |
| 跑测试套件 | Node 18+ 与 `npm install` —— **jsdom 是唯一的依赖** |
| 改数据管线 | Python 3 + `numpy`，以及 `PATH` 里的 `ffmpeg`（`pypinyin` 可选，装上才有拼音搜索） |

```bash
git clone https://github.com/Icather/speaker-workbench.git && cd speaker-workbench
npm install                 # 跑测试才需要
python tools/make_demo.py   # 只有想重新生成 demo 语料时才需要
```

`npm test` 会跑两个套件，其中真 DOM 套件**强依赖 jsdom** —— 没跑 `npm install` 会直接死在 `Cannot find module 'jsdom'`。

### 拿自己的音频来开发

```bash
cp config.example.json config.json      # 然后把那四个路径改掉
```

`config.json`（以及 `VOICE_DECK_*` 环境变量）和 `voices.json` 是被 gitignore 的。

**但 `audio/` 和 `data.js` 不是** —— 它们是提交进仓库的 demo 资产，好让一个刚 clone 下来的目录直接就能开会话（见 README → *快速开始*）。这有个锋利的地方：一旦把管线指向你自己的语料，`tools/sync.py` 就会**就地覆盖这两个路径**，紧接着一句下意识的 `git add .` 就把你的真实录音和真实转写提交上去了。`sync.py` 在这么做之前会警告，你也该自己看一眼：

```bash
git status --short          # data.js 和 audio/ 不该出现在这里
```

**绝不提交真实录音、真实转写或真实声纹向量** —— 见 [安全与隐私](#安全与隐私)。需要一个可靠的测试样本，就重新生成 demo，别把自己的数据搬进来：

```bash
python tools/make_demo.py
```

它是**确定性的** —— 每次跑出来的数组、转写完全相同 —— 所以可以放心当测试和 bug 报告里的固定样本。

---

## 文件都在哪

| 路径 | 职责 | 备注 |
|---|---|---|
| `index.html` | 全部界面：认人 / 校对 / 对照三种模式、搜索、撤销、合并、导出、RTTM 导入 | 无构建、无 CDN、无框架 |
| `tools/sync.py` | 数据管线 + `build_enrollment()`（声纹库） | 唯一负责解析数据路径的地方 |
| `tools/serve.py` | 本地服务、HTTP Range、加了音频自动重同步 | 正常运行本应用的方式 |
| `tools/make_demo.py` | 生成合成语料 | 只用标准库 + numpy |
| `tools/calibrate.py` | 在你的语料上复现建议名的阈值分布 | 绝不许编造数字 |
| `tools/inspect_embs.py` | 在 `sync.py` 跑之前校验产物格式 | 管线出问题第一个该跑的东西 |
| `tools/test_data.js` | 逻辑套件 —— `vm` 沙箱 + DOM 桩 | 快，不需要 jsdom |
| `tools/test_dom.js` | 真 DOM 套件 —— 用 jsdom 加载真实的 `index.html` | 能抓到桩抓不到的东西 |
| `docs/METHOD.zh-CN.md` | 数据契约、为什么用两阶段聚类 | §1 就是格式规范 |
| `docs/FIELD-NOTES.zh-CN.md` | 生态调研与定位 | §4 列了故意不做的东西 |

## 改动对照表

一个 PR 卡住的常见原因，是改动只传播了一半。这张表就是检查清单。

| 如果你改了 | 也要一并更新 |
|---|---|
| 某个文件格式的字段（`_final_map.json`、`_groups_final.json`、`_embs_all.npz`、`data.js`） | `docs/METHOD.md` §1 · README 的 *管线期望什么* · `tools/inspect_embs.py` 里的校验 · `CHANGELOG.md` |
| 某个阈值（`tools/sync.py` 里的 `SUG`） | 支撑它的那次测量 · `tools/calibrate.py` 打印的说明 · README 的阈值表 · `docs/METHOD.md` §3 · `CHANGELOG.md` |
| 某个配置项，或路径解析顺序 | `config.example.json` · README 的配置段 · `docs/METHOD.md` §6 · **`_path()` 的全部四份拷贝**（`sync.py`、`serve.py`、`calibrate.py`、`inspect_embs.py` —— 故意重复，没有共享包） |
| 某种导出格式 | `index.html` 里的 `FMT` 表 · `tools/test_dom.js` 的导出断言块 · README 的导出表 · `CHANGELOG.md` |
| 界面行为 | `tools/test_dom.js` · 并在**真实浏览器**里看一眼（见下） |
| demo 语料 | 保持 `tools/make_demo.py` 确定性、不引入重依赖，并继续复用 `sync.build_tags()`，让 demo 的编号与管线生成的编号一致 |
| 任何用户可见的东西 | **中英两版**都得改：`README.md`／`README.zh-CN.md` · `CONTRIBUTING.md`／`CONTRIBUTING.zh-CN.md` · `SECURITY.md`／`SECURITY.zh-CN.md` · `CHANGELOG.md`／`CHANGELOG.zh-CN.md` · `docs/*.md`／`docs/*.zh-CN.md` |

所有面向用户的文档都是**成对**的：`X.md` 是英文，`X.zh-CN.md` 是中文，两份内容一一对应。**如果你写不了两种语言，照样把 PR 发出来并说明** —— 它会被人翻译，而不是被拒掉。

---

## 测试

### 两个套件，两种职责

| 套件 | 怎么跑 | 能抓到 | 抓不到 |
|---|---|---|---|
| `test_data.js` | `vm` 沙箱 + 手写 DOM 桩 | 纯逻辑：筛选、排序、播放队列、格式化器、撤销栈 | 任何需要真实 HTML 解析的东西 |
| `test_dom.js` | jsdom 加载真实的 `index.html` | `innerHTML` 解析、`querySelector`、经 `closest()` 的事件委托、`classList`、`localStorage`、严格模式作用域 | canvas、`<audio>`、CSS 布局、网络 |

```bash
npm test               # 两个套件都跑；断言数约 140，随数据变化
npm run test:logic     # 只跑逻辑，不需要 jsdom
npm run test:dom       # 只跑真 DOM
```

**不要把断言数量写进文档。** 有些检查是**依赖数据**的 —— 只有存在跨录音组、存在建议名、或存在没有转写的录音时才会跑 —— 所以 demo 一变总数就变（历史上出现过 136 和 140）。要写就写**覆盖了什么**。

### 两个套件都验证不了的东西

渲染与播放。**只要你动了界面，就在真实浏览器里打开它。** 这不是客套话 —— 这个项目已经被它咬过一次：音频事件监听器里一个 `ReferenceError`（`onTime` 在被定义之前就被引用了）通过了所有基于桩的测试，却让浏览器里的播放彻底不工作。那些把 `addEventListener` 吞掉的桩，看不见这一类 bug。

### 套件强制的四条规则

1. **测试必须与数据无关。** 绝不断言写死的数量（`=== 64`）或写死的录音编号。锚点从加载的数据里推导 —— 见 `tools/test_dom.js` 顶部的 `A1 / A2 / ANOSRT / N1 / G1 / P0` 区块。同一套测试必须既能在合成 demo 上过，也能在真实语料上过。
2. **绝不出现绝对路径。** 一切都要经过 `tools/sync.py` / `tools/serve.py` / `tools/calibrate.py` / `tools/inspect_embs.py` 里的 `_path()`，也就是 `config.json` → `VOICE_DECK_*` 环境变量 → 仓库内默认值。写死一个 `D:\…` 或 `/Users/…` 就是 bug。
3. **任何测试都不许需要网络、模型下载，或签进仓库的真实语料。** CI 跑在一个光秃秃的 Ubuntu runner 上，只装了 jsdom。
4. **每一个对外发布的资产都必须由 `tools/make_demo.py` 产出。** 包括示意图、截图，以及输入框 placeholder 里的示例文字 —— 后两者是最容易在没察觉的情况下泄漏东西的地方。`docs/ui.svg` 曾经发布过一份带真实姓名的版本；现在它是按 demo 画的。README 里的拼音示例也曾经用过真实姓名、真实邮箱前缀和真实姓名拼音。

---

## 唯一铁律：数字不可商量

这个仓库里的数字撑起了整个项目：`0.83`、`0.85`，以及"**单段**音频的同人得分是 0.579、而最相似的异人是 0.567"这个事实。正因为它们，这个工具选择问人，而不是猜。

- **没有测量就不要改阈值。** `python tools/calibrate.py` 能复现那四个分布。把它的输出贴进 PR。
- **不要在自带的 demo 上做校准。** 它的声纹是 `make_demo.py` 造出来的，所以 `calibrate.py` 会在它上面打出一堆看起来很确信的废话（同人 ≈ 0.97、异人 ≈ 0.16），和真实音频毫无关系。用你自己的语料。
- **不要为了让输出好看而放宽区间。** 建议变多但准确率下降，那不是改进。「1–2 段的组永远只给弱提示」这条规则之所以存在，正是因为那些组能匹配到 0.80 那么高，却和正样本重叠。
- **不要删掉那些诚实的局限数字**（README 和 `docs/METHOD.md` §5 里的）。它们是产品本身，不是免责声明。

---

## 完整示例：新增一种导出格式

这是最常见的小贡献，所以把全过程写在这里。

每种格式就是 `index.html` 里 `FMT` 表的一项（大约在第 810 行）：

```js
xlsx: { label: 'XLSX 工作簿', ext: 'xlsx', note: 'one sheet per recording',
        fn: (scope, mode) => {
          // scope === '' 表示整个语料，或某个录音编号如 '0105'
          // mode  === 'real'（已认出的名字）或 'group'（原始 P### 编号）
          return '...文件内容，字符串...';
        }},
```

`fn(scope, mode)` 里可用的辅助函数：

| 辅助函数 | 给你什么 |
|---|---|
| `rowsFor(scope)` | 段落下标，按录音、再按时间排序 |
| `spkName(i, mode)` | 要打印的说话人标签（未分派时为 `未分派`） |
| `fmt(t)` / `tcComma(t, ms)` | `mm:ss` / `HH:MM:SS,mmm` 时间戳 |
| `p2(n, w)` | 补零 |
| `stamp()` | 文件名用的 `YYYYMMDD` |
| `D.segs[i]` | `{a, s, e, t, m, g}` —— 录音、起点、终点、文本、原始分离器编号、组 |

格式按钮是从 `Object.keys(FMT)` 生成的，所以**不需要改任何标记**。然后：

1. 在 `tools/test_dom.js` 的导出断言块里加断言（检查表头行、时间戳形状，如果是表格类格式还要检查 BOM）；
2. 在 README 的导出表里加一行；
3. 在 `CHANGELOG.md` 里记一笔。

如果这个格式需要真正的二进制编码器，请重新考虑：这个仓库零运行时依赖，而且 `index.html` 必须能从 `file://` 直接打开。

---

## 提 PR

**先开 issue** —— 如果你要改数据契约、阈值、聚类方式，或任何会引入依赖的东西。

**直接发 PR 就行** —— 错别字、文档、测试、原因明确的 bug 修复、以及新增导出格式。

- 一个 PR 一个主题。不要去重排你本来没动的代码 —— 巨大的 diff 会盖掉真正的改动。
- 从 `main` 开分支，推到你的 fork。给自己的 PR 分支 force-push 没问题。
- commit 标题用祈使句（`fix playback error in audio init`），把**为什么**写进正文。改动微妙、或数字反直觉时，多写几句是受欢迎的。
- CI（`.github/workflows/test.yml`，即 `npm test`）必须是绿的。先在本地跑一遍，只要几秒。

### 完成的定义

- [ ] `npm test` 通过（两个套件）
- [ ] 新行为有测试覆盖 —— 或者 PR 里说明为什么做不到
- [ ] 没有绝对路径；`index.html` 没有新增运行时依赖
- [ ] 按[改动对照表](#改动对照表)更新了文档（中英两版）
- [ ] 任何新出现的数字，都附上它怎么来的
- [ ] 界面改动在真实浏览器里看过，而不只在 jsdom 里

---

## 真正能帮上忙的事

大致按价值排序：

1. **第二个语料上的阈值测量。** 不同的麦克风、不同的房间、不同的语言。把 `tools/calibrate.py` 的输出贴进 issue 就够了 —— 现在那两个切点（0.83 / 0.85）来自**单一**一份远场手机录音语料，没人知道它们有多可移植。这是你能贡献的**最有价值**的一件事。
2. **换一个嵌入模型，并在同样的材料上测量。** ECAPA-TDNN / WeSpeaker / NeMo 对比 CAM++（后者对中文较强）。在参考管线里换模型是一行的事；真正的工作量在测量。
3. **RTTM 往返报告。** 从这里导出，导入 `pyannote` / Kaldi / NeMo，然后说说哪里坏了。互操作的 bug 从内部是看不见的。
4. **第三方分离器对照。** 任何能输出 RTTM 的东西现在都能导入。缺的是有人说清**它在哪里和人工分组不一致，以及谁是对的**。
5. **界面翻译。** 见[风格](#风格) —— 值得做，但要作为一份正式的字符串表 PR，而不是在一个屏幕里混两种语言。

## 会被拒绝的提议

| 提议 | 为什么 |
|---|---|
| 重新实现 VAD / 切分 / 单文件说话人分离 | `diarize` 和 `pyannote` 做得更好 —— [docs/FIELD-NOTES.zh-CN.md](docs/FIELD-NOTES.zh-CN.md) §4 |
| 服务器、账号、云同步，或托管的 demo 站点 | 纯本地是隐私约束，不是偶然：声纹属于生物识别数据 |
| 在 `index.html` 里加构建步骤、框架或 CDN | 零依赖的单文件就是这件事的全部意义 |
| 任何形式的遥测 / 统计 | 理由同"托管站点" |
| 放宽阈值，或删掉那些实测的局限 | 见[上面的铁律](#唯一铁律数字不可商量) |
| 词级时间戳（CTM 导出） | 管线里没有；先用一个具体用例开 issue |

## 报告 bug

写清你跑的命令；如果是管线问题，附上 `python tools/inspect_embs.py` 的输出；如果是界面问题，附上浏览器控制台。

**不要附带真实录音、真实转写或真实声纹向量。** 描述你数据的**形状**就行 —— 那几乎总是足够复现一个 bug：

- 录音份数、每份大致多少句、每份大致几个说话人
- 单段的典型时长
- 远场（手机隔着房间录）还是近场麦克风？
- 什么语言
- 用的是自带 demo 还是自己的语料？

如果某个问题只在你的语料上复现，说说它特别在哪。`inspect_embs.py` 的设计目标就是可以原样粘贴。

## 安全与隐私

这是一个处理生物识别数据的纯本地工具，所以有些 bug 是隐私问题而不是崩溃。如果你发现下面任何一条路径，请按安全问题上报：

- 服务绑定到了 `127.0.0.1` 以外的地址
- 音频、转写或声纹被写到配置的 `out` 目录之外
- 有任何东西发起了出站网络请求
- `demo/` 里混进了非合成的文件

**不要开一个带细节的公开 issue。** 开一个标题为 `security report`、正文不含技术内容的 issue，我们会从那里安排一条私有渠道。

## 风格

- **Python** —— 4 空格缩进，标准库优先，文件顶部 `# -*- coding: utf-8 -*-`。
- **JavaScript** —— 2 空格缩进，`const`/`let`，带分号，注释解释**为什么**。
- **注释用英文**（目前所有注释都是）。界面文案和管线的控制台输出用简体中文 —— 因为用它的就是这些人。**目前还没有 i18n 层**；当你新增一条文案时，跟随你所在文件的语言，不要在同一个屏幕里混用。
- **注释要值得占那几行。** 有几条存在的唯一目的，是记录一次测量或一个花了真实时间才踩到的坑 —— `make_demo.py` 里的噪声尺度说明、`index.html` 里 `pushUndo` 的顺序说明、`tools/sync.py` 里的阈值依据。留着它们，别"顺手整理"掉。
- 没有 linter，也没有 formatter。跟着周围的代码写。

## 许可

贡献即表示你同意你的工作按 MIT 授权（见 [LICENSE](LICENSE)）。
