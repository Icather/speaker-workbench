# AGENTS.md

Operational context for coding agents working in this repository. Humans want
[`README.md`](README.md); this file holds the things that would clutter it —
exact commands, the traps that have already cost time, and what to update when
you change something.

## What this is

The layer *after* diarization: aligning speaker identities **across** recordings
and remembering their names. `index.html` is the entire UI (one file, zero
runtime dependencies, no build step); `tools/sync.py` is the pipeline.

It is **not** a diarizer, transcriber, subtitle editor, or annotation server.
Do not add those — see [`docs/FIELD-NOTES.md`](docs/FIELD-NOTES.md) §4.

## ⚠️ The one thing you must not get wrong

**Never commit real recordings, transcripts, voiceprint vectors, or names taken
from them.** That is the single rule this project exists around; every other
convention here is negotiable.

The trap is that `audio/`, `data.js` and `speakers.json` **are git-tracked** —
they are the committed *synthetic* demo, which is what lets a fresh clone open
a working session. So if the pipeline has been pointed at a real corpus,
`tools/sync.py` **overwrites those three paths in place**, and a reflexive
`git add -A` stages personal data without anything looking wrong.

Check before every commit:

```bash
git status --short        # audio/, data.js, speakers.json must NOT appear
git diff --cached --stat  # and re-read this before you commit
```

If they appear, unstage them and regenerate the synthetic demo:

```bash
git restore --staged audio data.js speakers.json
python tools/make_demo.py && python tools/sync.py
```

Every public asset — diagrams, screenshots, placeholder text, test fixtures,
example names, example pinyin — **must come from `tools/make_demo.py`**. If you
need an example, generate it; do not type a plausible-looking one. A real name
once shipped in `docs/ui.svg` exactly that way, and a real name/email-prefix/
full-name-romanisation example once shipped in both READMEs.

## Commands

```bash
npm install                    # jsdom — test-only dependency
npm test                       # both suites
npm run test:logic             # no jsdom needed; seconds
npm run test:dom               # real DOM via jsdom
python tools/make_demo.py      # regenerate the synthetic corpus (~1.6 s)
python tools/sync.py           # rebuild data.js + audio/ (+ suggestions)
python tools/serve.py          # localhost, HTTP Range, live re-sync
python tools/inspect_embs.py   # validate artefacts BEFORE sync.py
python tools/calibrate.py      # reproduce the threshold distributions
```

`npm run test:dom` hard-requires jsdom — without `npm install` it dies with
`Cannot find module 'jsdom'`. Pipeline work needs Python 3 + `numpy`, and
`ffmpeg` on `PATH`. Nothing needs the network.

## Tests

| suite | catches | cannot catch |
|---|---|---|
| `tools/test_data.js` | pure logic, via a `vm` sandbox + hand-written DOM stubs | anything needing real HTML parsing |
| `tools/test_dom.js` | real HTML parsing, `querySelector`, event delegation, `classList`, `localStorage` | canvas, `<audio>`, CSS layout, network |

**Write data-agnostic assertions.** Never assert a literal count (`=== 64`,
`=== 140`) or a hard-coded recording id — several checks are conditional on the
dataset, so the total moves whenever the demo changes (it has been 136 and 140).
Derive anchors from the loaded data instead; see the `A1 / A2 / ANOSRT / N1 /
G1 / P0` block at the top of `tools/test_dom.js`.

**Never write the assertion count into documentation.** Describe what is
covered.

**Neither suite can verify rendering or playback.** If you touch the UI, open it
in a real browser. A `ReferenceError` inside an audio event listener once passed
every stub-based test while making playback completely non-functional.

## Traps that have already cost time

- **`_path()` exists in four files** — `tools/sync.py`, `serve.py`,
  `calibrate.py`, `inspect_embs.py`. Duplicated deliberately (no shared
  package). Change the resolution order in one, change all four.
- **Thresholds are measured, never guessed.** `SUG` in `tools/sync.py` encodes
  `0.83` (same-recording) and `0.85` (cross-recording). Do not change either
  without a measurement from `python tools/calibrate.py` on a **real** corpus,
  and paste its output in the PR.
- **Do not calibrate on the bundled demo.** Its embeddings are fabricated, so
  `calibrate.py` prints confident nonsense against it (same-speaker ≈ 0.97,
  different-speaker ≈ 0.16).
- **Do not widen a band to produce more suggestions.** More suggestions with
  worse precision is not an improvement. The "1–2 clip groups never get more
  than a weak hint" rule exists because those matched as high as 0.80 while
  overlapping the positive class.
- **No absolute paths, ever.** A hard-coded `D:\…` or `/Users/…` is a bug.
- **`index.html` must keep working from `file://`** and must not gain a build
  step, a framework, a CDN, or a runtime dependency.
- **The demo must stay deterministic** — same arrays, same transcripts, every
  run. It is used as a test fixture, so `tools/make_demo.py` must keep reusing
  `sync.build_tags()` and stay free of heavy dependencies.
- Comments that record a measurement or a trap are load-bearing (the
  noise-scaling note in `make_demo.py`, the `pushUndo` ordering note in
  `index.html`, the threshold justification in `tools/sync.py`). Do not
  "tidy" them away.

## What to update when you change something

| you changed | also update |
|---|---|
| a file-format field (`_final_map.json`, `_groups_final.json`, `_embs_all.npz`, `data.js`) | `docs/METHOD.md` §1 · the checks in `tools/inspect_embs.py` · `CHANGELOG.md` |
| a threshold | the measurement · `tools/calibrate.py` guidance · the README threshold table · `docs/METHOD.md` §3 |
| a config key or the resolution order | `config.example.json` · README config block · `docs/METHOD.md` §6 · **all four `_path()` copies** |
| an export format | the `FMT` table in `index.html` · the export block in `tools/test_dom.js` · the README export table |
| UI behaviour | `tools/test_dom.js` · and check it in a real browser |
| **anything user-visible** | **both languages** — see below |

## Languages

Every user-facing document is **paired**: `README.md` / `README.zh-CN.md`,
`CONTRIBUTING.md` / `CONTRIBUTING.zh-CN.md`, `SECURITY.md` / `SECURITY.zh-CN.md`,
`CHANGELOG.md` / `CHANGELOG.zh-CN.md`, `docs/METHOD.md` / `docs/METHOD.zh-CN.md`,
`docs/FIELD-NOTES.md` / `docs/FIELD-NOTES.zh-CN.md`. Keep them in step section
by section, and keep doc-to-doc links inside a Chinese file pointing at the
Chinese counterpart.

- **Code comments: English.** UI strings and pipeline console output:
  Simplified Chinese. Do not mix languages within one screen.
- Python: 4 spaces, stdlib first, `# -*- coding: utf-8 -*-` at the top.
- JavaScript: 2 spaces, `const`/`let`, semicolons, comments explain *why*.
- There is no linter or formatter. Match the surrounding code.

## Out of scope — do not add

A server, accounts, cloud sync, a hosted demo, telemetry of any kind,
VAD/segmentation/single-file diarization, a build step, or word-level timestamps
(no use case has been demonstrated). Local-only is a privacy constraint, not an
accident: voiceprints are biometric data. Reasons in
[`docs/FIELD-NOTES.md`](docs/FIELD-NOTES.md) §4 and
[`CONTRIBUTING.md`](CONTRIBUTING.md#things-that-will-be-declined).

## Before you say you are done

- [ ] `npm test` passes
- [ ] `git status --short` lists no `audio/`, `data.js`, `speakers.json`
- [ ] no absolute paths; `index.html` gained no runtime dependency
- [ ] docs updated per the table above, **in both languages**
- [ ] any new number comes with how it was obtained
- [ ] UI changes checked in a real browser, not only in jsdom
- [ ] every new public asset came from `tools/make_demo.py`
