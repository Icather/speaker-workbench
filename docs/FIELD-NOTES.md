# Field notes

[English](FIELD-NOTES.md) · [中文](FIELD-NOTES.zh-CN.md)

What already exists, what this project borrows, and where the empty space actually is. Written after surveying GitHub, HuggingFace Spaces, Hacker News and (since the original corpus is Chinese) Bilibili.

---

## 1. The ecosystem, by layer

| layer | who does it well | notes |
|---|---|---|
| VAD / segmentation / single-file diarization | **`diarize`** (CPU, Apache-2.0, ~4.8 % DER on VoxConverse), `pyannote` 3.1 / community-1, `FunASR` | mature, don't rewrite |
| ASR + timestamps | WhisperX, FunASR, Qwen3-ASR | mature |
| transcript + speaker, single file, as a service | **`lukeewin/FunASR_API`** (MIT) | FastAPI + MySQL + web UI; uses the *same* CAM++ checkpoint this project started from |
| subtitle timing UIs | **Aegisub** (the de-facto standard), Subtitle Edit, ATAlign | the interaction patterns are already solved |
| browser-side diarization editors | **GECKO** (Gong.io) — serverless, RTTM/CTM/JSON/TSV, multi-system comparison | closest architecturally to this workbench |
| collaborative annotation | **audino** (MIT, arXiv 2006.05236) | Dockerised full stack, JWT, role assignment |
| reference-audio based identification | `Parva101/speaker_diarization_identification` | requires you to supply a voice sample up front |
| **cross-recording identity + naming + voiceprint memory** | — | **this repo** |

HuggingFace Spaces carries plenty of Gradio diarization demos, but no *annotation workbench*. A Bilibili search for speaker-separation tooling returns almost entirely single-file transcription systems — the same shape as `FunASR_API`.

## 2. Where this differs

Five concrete differences from the nearest neighbours:

| dimension | they | this project |
|---|---|---|
| unit of work | one audio file | a **corpus** of recordings |
| speaker ids | `SPEAKER_00/01/…`, independent per file | **consistent `P###` across files** |
| identifying people | manual renaming, or you must supply reference audio | **automatic cross-recording clustering**, no reference needed |
| parameters | a default threshold | **measured on your own corpus** (`tools/calibrate.py`) |
| stated limits | usually unstated | quantified (see `docs/METHOD.md` §5) |

That last row is not vanity. Two independent signals say the gap is real:

- `diarize`'s roadmap lists *"Speaker identification — recognise known speakers across sessions using stored embeddings"* as **not done**.
- The same README admits *"one real speaker may be split across multiple SPEAKER_XX labels, especially on noisy real-world audio."* The two-stage clustering in this repo exists specifically to attack that, and the measured before/after (26 % → 0.6 % low-consistency groups) is in `docs/METHOD.md` §2.

Its author's blunt assessment on Hacker News is also worth repeating: **speaker-count estimation, not embedding or clustering, is the hard part** (GMM+BIC managed 51 % exact matches on VoxConverse, collapsing entirely past 8 speakers).

## 3. What was borrowed, and what it became

| borrowed | from | landed as |
|---|---|---|
| RTTM as the interchange format | pyannote / `diarize` / Kaldi / NeMo | export + **import** (import feeds comparison mode) |
| multi-format export | whisper-diarization-app, Subtitle Edit | TXT / SRT / VTT / CSV / RTTM / Markdown / JSON, scoped per recording or whole corpus, with preview |
| **online enrollment** | arXiv 2509.18377 | `sync.py:build_enrollment()` — named groups become centroid voiceprints; unnamed groups get scored suggestions; `Tab` to accept |
| side-by-side comparison of two systems | **GECKO** | per-line raw diarizer id + highlight for disagreements, plus a confusion matrix in both directions |
| subtitle-timing interaction | **Aegisub** / Subtitle Edit | waveform + per-line list + full keyboard flow + merge. *Split* was deliberately skipped: on this material the median cue is 2.2 s and only 0.1 % exceed 20 s, so there is nothing to split |

## 4. Deliberately not built

| layer | use instead |
|---|---|
| VAD / segmentation / single-file diarization | `diarize` (or pyannote) |
| ASR | WhisperX / FunASR / Qwen3-ASR |
| a transcription service | `FunASR_API` |
| a subtitle editor | Aegisub / Subtitle Edit |
| an annotation server with accounts and roles | audino, if you need multi-user |

The bet is narrow on purpose: everything above is well served, and the cross-recording layer is not served at all.
