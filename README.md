# speaker-workbench

[English](README.md) · [中文](README.zh-CN.md)

[![tests](https://github.com/Icather/speaker-workbench/actions/workflows/test.yml/badge.svg)](https://github.com/Icather/speaker-workbench/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![runtime deps: none](https://img.shields.io/badge/runtime%20deps-none-success)](#quick-start)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**Turn `SPEAKER_00 / SPEAKER_01` into actual names — across a whole corpus of recordings, not one file at a time.**

Existing diarization tools stop at anonymous speaker IDs, and every file gets its own numbering. This is a small, dependency-free workbench for the step *after* diarization: aligning speaker identities **across** recordings, letting a human confirm who is who, and then reusing those confirmations to label new audio automatically.

![the workbench](docs/ui.svg)

<sub>Layout diagram drawn from `index.html` — not a screenshot. The shipped interface is in Simplified Chinese; `label · proof · compare` are modes, not separate tools.</sub>

---

## Why not just use pyannote / diarize / WhisperX?

Say you have 10 meeting recordings of the same people. `pyannote`, `diarize` or `WhisperX` will happily tell you that recording 3 has four speakers. They will not tell you that *speaker 2 in recording 3 is the same person as speaker 0 in recording 7*, and they certainly will not tell you that person's name.

That gap is not accidental — it is an open problem. The author of [`diarize`](https://github.com/FoxNoseTech/diarize) lists *"Speaker identification — recognise known speakers across sessions using stored embeddings"* on the roadmap, and notes that *"one real speaker may be split across multiple SPEAKER_XX labels, especially on noisy real-world audio"*.

| | single-file diarization | cross-recording identity | remembers names | no account, offline | review UI |
|---|---|---|---|---|---|
| [`diarize`](https://github.com/FoxNoseTech/diarize) | ✅ CPU-only | ✗ *(roadmap)* | ✗ | ✅ | ✗ |
| [`pyannote.audio`](https://github.com/pyannote/pyannote-audio) | ✅ | ✗ | ✗ | ✅ *(gated weights need a HF token)* | ✗ |
| [`WhisperX`](https://github.com/m-bain/whisperX) | ✅ *(wraps pyannote)* | ✗ | ✗ | ✅ *(same token)* | ✗ |
| [`GECKO`](https://github.com/gong-io/gecko) | ✗ | ✗ | ✗ | ✅ | ✅ *(single file; deprecated Nov 2025)* |
| [`audino`](https://github.com/readbeyond/audino) | ✗ | ✗ | ✗ | self-hosted | ✅ *(multi-user)* |
| **speaker-workbench** | **✗ — use the rows above** | **✅** | **✅** | ✅ | ✅ |

The bet is narrow on purpose: every other row is well served, the bottom one is not served at all. So the pipeline is split, and only the last stage is ours:

![pipeline](docs/pipeline.svg)

---

## Quick start

Everything runs offline and needs no account. The browser UI has **zero dependencies** — no build step, no CDN, no framework.

**Try it without installing anything:** <https://icather.github.io/speaker-workbench/> — the same synthetic corpus, served from this repo. Your annotations go to the browser's `localStorage`; the *write to disk* endpoint only exists when you run it locally.

```bash
git clone https://github.com/Icather/speaker-workbench.git && cd speaker-workbench

# Windows
start.bat
# macOS / Linux
./start.sh
```

| you want to | you need |
|---|---|
| try the UI | a browser — or the [hosted demo](https://icather.github.io/speaker-workbench/) |
| run the test suite | Node 18+, then `npm install` (jsdom is the only dependency) |
| run the data pipeline | Python 3.9+, `numpy`, and `ffmpeg` on `PATH` (`pypinyin` optional — enables pinyin search) |

The repo ships with a **fully synthetic demo** (invented people, formant-synthesised speech, fabricated transcripts — see `tools/make_demo.py`): 4 recordings, 77 lines, 12 groups, 6 voices, committed as 32 kbps mp3. It opens straight into a working session and needs no ffmpeg. Regenerating it is deterministic — the same audio, transcripts and voiceprints every time.

It is **committed on purpose** — which is why `audio/` and `data.js` are tracked rather than git-ignored. Convenient for a clone, hazardous if you later point the pipeline at your own corpus: those two paths get overwritten in place, and the next `git add .` stages your real recordings. `sync.py` warns when it is about to do this; see [CONTRIBUTING](CONTRIBUTING.md#developing-against-your-own-audio).

> The demo is deliberately imperfect, because a real pipeline's output is. One speaker spans three of the four recordings, four groups are fragments of somebody already named (what *merge* is for), two groups have a single clip and are genuinely unresolvable, and one person carries two different raw diariser ids while one id covers two different groups. The *suggest-a-name* feature has both of its confidence bands on show: one strong suggestion and four weak hints.

---

## How it works

1. **Segment** — you run `diarize` / `pyannote` / `FunASR` yourself. Its output becomes the transcript this tool reads: standard SRT with `(Speaker N)` prefixed to each line.
2. **Slice and embed** — clips of 2–12 s are cut per cue and encoded to a 192-dim **CAM++** voiceprint (`iic/speech_campplus_sv_zh-cn_16k-common`, 3D-Speaker, ~28 MB).
3. **Cluster in two stages** — `complete` linkage first to get pure mini-clusters, then `centroid` linkage to merge those. One stage measurably does not work: a *single* clip of the same person across two recordings scores **0.579**, and the most similar *different* speaker scores **0.567** — no single threshold separates those. See [docs/METHOD.md](docs/METHOD.md) §2.
4. **Name, then reuse** — you confirm identities in the UI; every confirmed group becomes a centroid voiceprint in `speakers.json`, and unnamed groups are matched against that library (`sync.py:build_enrollment()`).

Steps 1–2 are swappable — any diarizer that can produce the transcript format, and any embedding model that emits a fixed-length vector per clip, will do. The formats are in [docs/METHOD.md](docs/METHOD.md) §1 and checked by `python tools/inspect_embs.py`.

---

## What it does

### 1. Label mode — the main event

Click a speaker group and the page plays **every clip of that voice across all recordings, back to back** (1.6 s of lead-in, 15 s per clip, auto-advance). Most people are identifiable within 5–10 seconds, so 3–4 clips is usually enough.

- Full keyboard flow: `space` play · `↑↓` next group · `enter` save & advance · `S` skip · `X` can't-tell · `L` loop one clip · `Tab` accept suggestion
- Name box is **fuzzy + pinyin**: type `演`, `ysj` or `yanshijia` and get the same person. Candidates render as `name_tag1_tag2…`
- Waveforms: full-file overview plus a ±25 s zoom of the current clip
- Playback speed 0.75×–1.5× for hard sections

### 2. Proof mode — fix what the machine got wrong

Walk a transcript line by line; click a chip (or press `1`–`9`) to reassign a line to another speaker. Edits are stored separately from the automatic grouping, so nothing is lost.

### 3. Comparison mode — see where two systems disagree

`⇄ compare` shows the raw diarizer's own speaker IDs next to your grouping, highlighting lines where they differ. `📊 analysis` produces the confusion matrix in both directions:

- one diarizer ID → N groups (it merged different people)
- one group → N diarizer IDs (label hopping)

### 4. Online enrollment — it starts naming people for you

Every group you name is collapsed into a **centroid voiceprint** and stored in `speakers.json`. On the next sync, unnamed groups are compared against that library and get a suggestion.

![suggest](docs/suggest.svg)

**The thresholds are measured, not guessed.** `tools/calibrate.py` reproduces this table on your own data:

| scenario | measured cosine | threshold |
|---|---|---|
| same person · same recording | 0.834 – 0.985 | `same.hi = 0.83` |
| **different people · same recording** (n=675) | median 0.444, p95 0.712, **max 0.822** | ← cut at 0.828 |
| same person · across recordings (both ≥5 clips) | 0.913 – 0.936 | `cross.hi = 0.85` |
| 1–2 clip groups | up to 0.80 — **overlaps the positive class** | *never more than a weak hint* |

> Why two thresholds: within one recording everybody shares the room and the mic, so the similarity floor is naturally high. A single threshold tuned for cross-recording work will flood you with false positives. This was learned the hard way (39 suggestions, all wrong).

### 5. Export & interop

| format | why |
|---|---|
| **RTTM** | the lingua franca of diarization — `pyannote`, `diarize`, Kaldi, NeMo all read and write it |
| SRT / VTT | subtitles (`<v name>` tags for VTT) |
| CSV | spreadsheets (BOM included so Excel opens UTF-8 correctly) |
| TXT / Markdown | reading |
| voices.json | the annotation itself, for round-tripping |

You can also **import** an RTTM from another tool and diff it against your grouping.

---

## Using your own recordings

```bash
cp config.example.json config.json
```

```jsonc
{
  "recordings":  "/path/to/audio",          // .m4a .mp3 .wav .flac .ogg .aac .opus .wma
  "transcripts": "/path/to/transcripts",    // <same-stem>.moss.srt
  "voiceprint":  "/path/to/voiceprint-out", // _final_map.json / _groups_final.json / _embs_all.npz
  "out":         "."                        // where data.js / audio/ / voices.json go
}
```

Relative paths resolve against the repo root; `VOICE_DECK_RECORDINGS` etc. override the file. With no `config.json` at all, the built-in demo layout is used.

### What the pipeline expects

| input | meaning |
|---|---|
| audio files | any of the extensions above, filename should contain a date (`20260105_…`) — that becomes the recording tag |
| `*.moss.srt` | diarised transcript: standard SRT with `(Speaker N)` prefixed to each line |
| `_final_map.json` | `{"<tag>\|<start>": "P001", …}` — segment to group |
| `_groups_final.json` | per-group stats used by the UI (`段数`, `时长min`, `出现录音`, `单一致性` …) |
| `_embs_all.npz` | `emb` (N×192) + `meta` (JSON strings) — optional; without it everything works except suggestions |

Run `python tools/inspect_embs.py` **before** the first sync. It validates each of those four inputs in turn and names the exact key that does not line up — a mismatch fail silently and shows up as an empty page.

The reference pipeline that produces those files (CAM++ voiceprints + two-stage agglomerative clustering) is documented in **[docs/METHOD.md](docs/METHOD.md)**.

### Day-to-day commands

```bash
python tools/make_demo.py     # regenerate the synthetic demo set
python tools/sync.py          # rebuild data.js + audio/ (+ suggestions)  [needs numpy + ffmpeg]
python tools/serve.py         # local server with HTTP Range; opens the browser
python tools/calibrate.py     # measure the suggestion thresholds on your data
python tools/inspect_embs.py  # validate artefact formats before syncing
npm test                      # both suites (~140 checks; needs `npm install`)
npm run test:logic            # logic suite only — no jsdom needed
npm run test:dom              # real-DOM suite only
```

Both test suites are **data-agnostic** — they assert invariants rather than fixed counts, so they pass on the demo set and on a real corpus alike.

---

## Honest limits

These numbers come from real far-field phone recordings and are the reason this tool asks a human for every decision:

- **Single clips carry almost no identity information.** Cross-recording same-speaker similarity on a *single* clip was 0.579, while the most similar *different* speaker scored 0.567. The distributions overlap — one clip can never settle it.
- **Multi-clip centroids do work.** Same person, ≥5 clips on both sides: 0.913–0.936.
- **Quiet, brief speakers stay anonymous.** Someone who talks for 15 seconds in one recording cannot be resolved. Don't spend time on them.
- **Two different people with similar timbre are indistinguishable to this pipeline.** Voiceprints answer *"is this the same voice?"*, not *"which of these two similar voices is it?"*. A human must listen.
- **Content similarity is not identity.** Two groups that both "host and introduce the same person" measured 0.478 — i.e. clearly different people.

So the workflow is *machine proposes, human decides*, and the UI is built for exactly that: one keystroke per decision, undo everywhere, and every suggestion carries its score and confidence band.

## Use something else if…

| you need | use |
|---|---|
| overlapping-speech detection | `pyannote` — this tool labels at most one speaker per segment, inherited from the diarizer |
| word-level timestamps | not produced anywhere in this pipeline |
| multi-user annotation with accounts and roles | [`audino`](https://github.com/readbeyond/audino) |
| live / streaming diarization | nothing here is streaming; every step is file-based |
| a hosted service | the whole point is that it stays local — see [Privacy](#privacy) |

## Roadmap

Deliberately short, and mostly about turning assertions into measurements:

- **Threshold measurements from a second corpus.** The 0.83 / 0.85 cuts come from one corpus of far-field phone audio. Nobody knows how portable they are; `tools/calibrate.py` output from your recordings would settle it.
- **Alternative embedding models, measured head-to-head.** CAM++ is Mandarin-strong; ECAPA-TDNN / WeSpeaker / NeMo numbers on the same material would be a welcome data point.
- **UI translation.** The interface is Simplified Chinese only, with no string table yet.

---

## Credits / related work

- [`diarize`](https://github.com/FoxNoseTech/diarize) — CPU diarization, Apache-2.0; its two documented gaps motivated the cross-recording layer here
- [`GECKO`](https://github.com/gong-io/gecko) (Gong.io) — in-browser diarization editor; the multi-system comparison view is modelled on it
- [`audino`](https://github.com/readbeyond/audino) (MIT) — collaborative annotation
- `Aegisub` / `Subtitle Edit` — the subtitle-timing interaction patterns (waveform, per-line shortcuts, merge/split)
- [arXiv:2509.18377](https://arxiv.org/abs/2509.18377) — *online enrollment* for speaker identification
- `3D-Speaker` / CAM++ — the Chinese speaker-embedding model used by the reference pipeline
- Method details and the free/open tool survey live in **[docs/METHOD.md](docs/METHOD.md)** and **[docs/FIELD-NOTES.md](docs/FIELD-NOTES.md)**

---

## Privacy

Voiceprints are biometric data, and diarised transcripts are about real people. This tool is designed to keep both **local**: the server binds to `127.0.0.1`, audio never leaves the machine, no telemetry, no network calls.

The demo ships with **synthetic** audio (formant synthesis) and **invented** names — `tools/make_demo.py` generates it from scratch. If you fork this, keep real recordings and real embeddings out of the repository.

## License

MIT — see [LICENSE](LICENSE).

Runtime dependencies are permissive or absent: `numpy` (BSD-3), `pypinyin` (MIT), `jsdom` (MIT, tests only). `ffmpeg` is only needed by the pipeline and is licensed separately (LGPL-2.1+ or GPL depending on the build). The browser UI loads nothing at all.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — it is short, and it explains the two rules the test suite enforces and why no threshold may change without a measurement.
