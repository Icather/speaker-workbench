# 现场笔记

[English](FIELD-NOTES.md) · [中文](FIELD-NOTES.zh-CN.md)

已经存在什么、这个项目借了什么、而空白究竟在哪。写于调研 GitHub、HuggingFace Spaces、Hacker News，以及（因为原语料是中文的）Bilibili 之后。

---

## 1. 生态，按层看

| 层 | 谁做得好 | 备注 |
|---|---|---|
| VAD / 切分 / 单文件说话人分离 | **`diarize`**（CPU、Apache-2.0、VoxConverse 上约 4.8 % DER）、`pyannote` 3.1 / community-1、`FunASR` | 成熟，别重写 |
| ASR + 时间戳 | WhisperX、FunASR、Qwen3-ASR | 成熟 |
| 转写 + 说话人、单文件、以服务形式提供 | **`lukeewin/FunASR_API`**（MIT） | FastAPI + MySQL + 网页界面；用的**正是**本项目起步时那个 CAM++ 权重 |
| 字幕打轴界面 | **Aegisub**（事实标准）、Subtitle Edit、ATAlign | 交互范式早就解决了 |
| 浏览器端分离标注器 | **GECKO**（Gong.io）—— 免服务端、RTTM/CTM/JSON/TSV、多系统对照 | 架构上与本工作台最接近 |
| 协作式标注 | **audino**（MIT，arXiv 2006.05236） | Docker 全家桶、JWT、角色分配 |
| 基于参考音频的辨认 | `Parva101/speaker_diarization_identification` | 需要你先提供一段声音样本 |
| **跨录音身份 + 命名 + 声纹记忆** | — | **本仓库** |

HuggingFace Spaces 上有大量 Gradio 的分离 demo，但**没有标注工作台**。在 Bilibili 搜说话人分离工具，出来的几乎全是单文件转写系统 —— 和 `FunASR_API` 一个形状。

## 2. 差别在哪

与最近的邻居之间，五个具体差别：

| 维度 | 它们 | 本项目 |
|---|---|---|
| 工作单位 | 一个音频文件 | 一**库**录音 |
| 说话人编号 | `SPEAKER_00/01/…`，每个文件各自编号 | **跨文件一致的 `P###`** |
| 认出人 | 手工改名，或者你得提供参考音频 | **自动跨录音聚类**，不需要参考 |
| 参数 | 一个默认阈值 | **在你自己的语料上实测**（`tools/calibrate.py`） |
| 是否说明局限 | 通常不说 | 量化了（见 `docs/METHOD.zh-CN.md` §5） |

最后一行不是为了自夸。两个独立的信号说明这个空白是真的：

- `diarize` 的 roadmap 把 *"Speaker identification —— 用已存嵌入识别跨会话的已知说话人"* 列为**尚未完成**。
- 同一个 README 承认 *"一个真实的说话人可能被拆到多个 SPEAKER_XX 标签上，在嘈杂的真实音频上尤其如此。"* 本仓库的两阶段聚类正是为了攻这一点，而实测的前后对比（低一致性组 26 % → 0.6 %）在 `docs/METHOD.zh-CN.md` §2。

它的作者在 Hacker News 上的直白评价也值得转述：**难的是说话人数量估计，而不是嵌入或聚类**（GMM+BIC 在 VoxConverse 上做到 51 % 完全正确，超过 8 个说话人就彻底崩掉）。

## 3. 借了什么，变成了什么

| 借来的 | 来自 | 落地为 |
|---|---|---|
| 用 RTTM 作交换格式 | pyannote / `diarize` / Kaldi / NeMo | 导出 + **导入**（导入喂给对照模式） |
| 多格式导出 | whisper-diarization-app、Subtitle Edit | TXT / SRT / VTT / CSV / RTTM / Markdown / JSON，可按单个录音或整个语料，带预览 |
| **在线登记** | arXiv 2509.18377 | `sync.py:build_enrollment()` —— 已命名的组变成质心声纹；未命名的组得到打分的建议；`Tab` 采纳 |
| 两套系统并排对照 | **GECKO** | 逐行显示原始分离器编号 + 不一致处高亮，外加一张双向混淆矩阵 |
| 字幕打轴交互 | **Aegisub** / Subtitle Edit | 波形 + 逐行列表 + 全键盘流 + 合并。*拆分*被刻意跳过了：在这类材料上字幕条中位数是 2.2 秒，只有 0.1 % 超过 20 秒，没什么可拆的 |

## 4. 故意不做的部分

| 层 | 请改用 |
|---|---|
| VAD / 切分 / 单文件说话人分离 | `diarize`（或 pyannote） |
| ASR | WhisperX / FunASR / Qwen3-ASR |
| 转写服务 | `FunASR_API` |
| 字幕编辑器 | Aegisub / Subtitle Edit |
| 带账号和角色的标注服务器 | audino，如果你需要多人协作 |

押注刻意押得很窄：上面那些都被服务得很好，而跨录音这一层完全没有被服务。
