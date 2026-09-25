# Contributing

[English](CONTRIBUTING.md) · [中文](CONTRIBUTING.zh-CN.md)

This file is the contract for changes. A PR that ignores it will be asked to change — not over style taste, but because the repo has two things it will not trade away: **measured numbers** and **a demo that runs anywhere**.

- **What this is** — the layer *after* diarization: aligning speaker identities **across** recordings, letting a human name them, then reusing those names.
- **What this is not** — a diarizer, a transcriber, a subtitle editor, or an annotation server. See [docs/FIELD-NOTES.md](docs/FIELD-NOTES.md) §4 for what to use instead.
- **Small is a feature.** `index.html` is one file with zero runtime dependencies. Please keep it that way.

**Contents** · [Setup](#getting-set-up) · [Where things live](#where-things-live) · [Change map](#if-you-change-x-also-do-y) · [Tests](#tests) · [Numbers](#the-one-rule-numbers-are-not-negotiable) · [Worked example](#worked-example-adding-an-export-format) · [Opening a PR](#opening-a-pr) · [Help wanted](#what-would-genuinely-help) · [Declined](#things-that-will-be-declined) · [Bugs](#reporting-a-bug) · [Security](#security--privacy) · [Style](#style)

---

## Getting set up

Three tiers — most contributions need only the first.

| you want to | you need |
|---|---|
| run the demo and poke at the UI | **nothing but a browser.** `./start.sh` (macOS/Linux) or `start.bat` (Windows) |
| run the test suite | Node 18+ and `npm install` — **jsdom is the only dependency** |
| change the data pipeline | Python 3 + `numpy`, and `ffmpeg` on `PATH` (`pypinyin` optional, enables pinyin search) |

```bash
git clone https://github.com/Icather/speaker-workbench.git && cd speaker-workbench
npm install                 # for the test suite
python tools/make_demo.py   # only if you want to regenerate the demo corpus
```

`npm test` runs both suites, and the real-DOM suite **hard-requires jsdom** — without `npm install` it dies with `Cannot find module 'jsdom'`.

### Developing against your own audio

```bash
cp config.example.json config.json      # then edit the four paths
```

`config.json` (plus `VOICE_DECK_*` env vars) and `voices.json` are git-ignored.

**`audio/` and `data.js` are not** — they are the committed demo assets that let a fresh clone open straight into a working session (README → *Quick start*). That has a sharp edge: point the pipeline at your own corpus and `tools/sync.py` will **overwrite both in place**, after which a reflexive `git add .` commits your real recordings and transcripts. `sync.py` warns before doing this, and so should you:

```bash
git status --short          # data.js and audio/ must NOT be listed here
```

**Never commit real recordings, transcripts, or voiceprint vectors** — see [Security & privacy](#security--privacy). If you need a known-good fixture, regenerate the demo instead of importing your own data:

```bash
python tools/make_demo.py
```

It is **deterministic** — the same arrays, the same transcripts, every run — so it is safe to use as a fixture in tests and bug reports.

---

## Where things live

| path | responsibility | notes |
|---|---|---|
| `index.html` | the entire UI: label / proof / compare modes, search, undo, merge, export, RTTM import | no build step, no CDN, no framework |
| `tools/sync.py` | data pipeline + `build_enrollment()` (the voiceprint library) | the only place that resolves data paths |
| `tools/serve.py` | localhost server, HTTP Range, re-syncs when audio is added | the normal way to run the app |
| `tools/make_demo.py` | generates the synthetic corpus | stdlib + numpy only |
| `tools/calibrate.py` | reproduces the suggestion thresholds on your corpus | must never invent numbers |
| `tools/inspect_embs.py` | validates artefact formats before `sync.py` runs | first thing to run on a pipeline bug |
| `tools/test_data.js` | logic suite — `vm` sandbox + DOM stubs | fast, no jsdom |
| `tools/test_dom.js` | real-DOM suite — jsdom over the actual `index.html` | catches what stubs cannot |
| `docs/METHOD.md` | data contracts, why two-stage clustering | §1 is the format spec |
| `docs/FIELD-NOTES.md` | ecosystem survey and positioning | §4 lists what is deliberately not built |

## If you change X, also do Y

The usual reason a PR stalls is a half-propagated change. This table is the checklist.

| if you change | also update |
|---|---|
| a file-format field (`_final_map.json`, `_groups_final.json`, `_embs_all.npz`, `data.js`) | `docs/METHOD.md` §1 · README *What the pipeline expects* · the checks in `tools/inspect_embs.py` · `CHANGELOG.md` |
| a threshold (`SUG` in `tools/sync.py`) | the measurement that justifies it · `tools/calibrate.py`'s printed guidance · README threshold table · `docs/METHOD.md` §3 · `CHANGELOG.md` |
| a config key, or the resolution order | `config.example.json` · README config block · `docs/METHOD.md` §6 · **all four copies of `_path()`** (`sync.py`, `serve.py`, `calibrate.py`, `inspect_embs.py` — duplicated on purpose, there is no shared package) |
| an export format | the `FMT` table in `index.html` · the export block in `tools/test_dom.js` · README export table · `CHANGELOG.md` |
| UI behaviour | `tools/test_dom.js` · and check it in a real browser (see below) |
| the demo corpus | keep `tools/make_demo.py` deterministic and free of heavy dependencies, and keep it reusing `sync.build_tags()` so demo tags match what the pipeline generates |
| anything user-visible | **both languages**: `README.md`／`README.zh-CN.md` · `CONTRIBUTING.md`／`CONTRIBUTING.zh-CN.md` · `SECURITY.md`／`SECURITY.zh-CN.md` · `CHANGELOG.md`／`CHANGELOG.zh-CN.md` · `docs/*.md`／`docs/*.zh-CN.md` |
| a command, a trap, or the test-suite split — anything an agent acts on | `AGENTS.md` — **English only, by design**: agents look for that exact filename, so a translated copy would simply never be read |

Every user-facing document is **paired**: `X.md` in English, `X.zh-CN.md` in Chinese, kept in step section by section. If you cannot write both, still open the PR and say so — it will get translated rather than rejected.

---

## Tests

### Two suites, two jobs

| suite | how | catches | cannot catch |
|---|---|---|---|
| `test_data.js` | `vm` sandbox + hand-written DOM stubs | pure logic: filtering, sorting, clip queues, formatters, undo stack | anything needing real HTML parsing |
| `test_dom.js` | jsdom over the real `index.html` | `innerHTML` parsing, `querySelector`, event delegation via `closest()`, `classList`, `localStorage`, strict-mode scoping | canvas, `<audio>`, CSS layout, network |

```bash
npm test               # both suites; the count ~140 varies with the dataset
npm run test:logic     # logic only, no jsdom needed
npm run test:dom       # real DOM only
```

**Do not write an assertion count into documentation.** Several checks are
conditional on the data — they only run when there is a cross-recording group, a
suggestion, or a recording without a transcript — so the total moves whenever the
demo changes (it has been 136 and 140). Describe what is covered instead.

### What neither suite can verify

Rendering and playback. **If you touch the UI, open it in a real browser.** This is not boilerplate — it already bit this project once: a `ReferenceError` inside an audio event listener (`onTime` was referenced before it existed) passed every stub-based test and made playback completely non-functional in the browser. Stubs that swallow `addEventListener` cannot see that class of bug.

### Three rules the suites enforce

1. **Tests stay data-agnostic.** Never assert a literal count (`=== 64`) or a hard-coded recording id. Derive anchors from the loaded data — see the `A1 / A2 / ANOSRT / N1 / G1 / P0` block at the top of `tools/test_dom.js`. The same suite must pass on the synthetic demo *and* on a real corpus.
2. **No absolute paths, ever.** Everything goes through `_path()` in `tools/sync.py` / `tools/serve.py` / `tools/calibrate.py` / `tools/inspect_embs.py`, i.e. `config.json` → `VOICE_DECK_*` env var → in-repo default. A hard-coded `D:\…` or `/Users/…` is a bug.
3. **No test may need the network, a model download, or a checked-in real corpus.** CI runs on a bare Ubuntu runner with only jsdom installed.
4. **Every shipped asset must come from `tools/make_demo.py`.** That includes diagrams, screenshots, and example text in placeholders — the last two are the easiest places to leak something without noticing. A real name in `docs/ui.svg` shipped once; it is now drawn from the demo instead.

---

## The one rule: numbers are not negotiable

The numbers in this repo carry the project: `0.83`, `0.85`, and the fact that a *single* clip scores 0.579 for the same speaker versus 0.567 for the most similar different speaker. They are why the tool asks a human instead of guessing.

- **Never change a threshold without a measurement.** `python tools/calibrate.py` reproduces the four distributions. Paste its output in the PR.
- **Do not calibrate on the bundled demo.** Its embeddings are fabricated by `make_demo.py`, so `calibrate.py` prints confident-looking nonsense against it (same-speaker ≈ 0.97, different-speaker ≈ 0.16) that says nothing about real audio. Use your own corpus.
- **Do not widen a band to make output look better.** More suggestions is not an improvement if the precision drops. The `1–2 clip groups never get more than a weak hint` rule exists precisely because those matched as high as 0.80 while overlapping the positive class.
- **Do not delete the honest-limits numbers** in the README or `docs/METHOD.md` §5. They are the product, not a disclaimer.

---

## Worked example: adding an export format

This is the most common small contribution, so here is the whole of it.

Every format is one entry in the `FMT` table in `index.html` (around line 810):

```js
xlsx: { label: 'XLSX 工作簿', ext: 'xlsx', note: 'one sheet per recording',
        fn: (scope, mode) => {
          // scope === '' for the whole corpus, or a recording id like '0105'
          // mode  === 'real' (resolved name) or 'group' (raw P### id)
          return '...file contents as a string...';
        }},
```

Helpers available inside `fn(scope, mode)`:

| helper | gives you |
|---|---|
| `rowsFor(scope)` | segment indices, in recording then time order |
| `spkName(i, mode)` | the speaker label to print (`未分派` when unassigned) |
| `fmt(t)` / `tcComma(t, ms)` | `mm:ss` / `HH:MM:SS,mmm` timestamps |
| `p2(n, w)` | zero-padding |
| `stamp()` | `YYYYMMDD` for the filename |
| `D.segs[i]` | `{a, s, e, t, m, g}` — recording, start, end, text, raw diarizer id, group |

The format chips are generated from `Object.keys(FMT)`, so **no markup changes are needed**. Then:

1. add assertions to the export block of `tools/test_dom.js` (check the header line, the timestamp shape, and the BOM if it is a spreadsheet format);
2. add a row to the README export table;
3. note it in `CHANGELOG.md`.

If the format needs a real binary encoder, reconsider: this repo has zero runtime dependencies, and `index.html` must keep working from `file://`.

---

## Opening a PR

**Open an issue first** if you are changing a data contract, a threshold, the clustering approach, or anything that adds a dependency.

**Just send the PR** for typos, docs, tests, bug fixes with an obvious cause, and new export formats.

- One topic per PR. Do not reformat code you were not otherwise touching — a large diff hides the real change.
- Branch from `main`; push to your fork. Force-pushing your own PR branch is fine.
- Commit subject in the imperative (`fix playback error in audio init`), and use the body for *why*. A few sentences are welcome when the change is subtle or the number is surprising.
- CI (`.github/workflows/test.yml`, i.e. `npm test`) must be green. Run it locally first; it takes seconds.

### Definition of done

- [ ] `npm test` passes (both suites)
- [ ] new behaviour is covered by a test — or the PR explains why it cannot be
- [ ] no absolute paths; no new runtime dependency in `index.html`
- [ ] docs updated per the [change map](#if-you-change-x-also-do-y)
- [ ] any new number comes with how it was obtained
- [ ] UI changes were checked in a real browser, not only in jsdom

---

## What would genuinely help

Roughly in order of value:

1. **Threshold measurements from a second corpus.** Different mic, different room, different language. Pasting `tools/calibrate.py` output into an issue is enough — the current cuts (0.83 / 0.85) come from a single corpus of far-field phone audio, and nobody knows how portable they are. This is the single most useful thing you can contribute.
2. **A different embedding model, measured on the same material.** ECAPA-TDNN / WeSpeaker / NeMo versus CAM++ (which is Mandarin-strong). Swapping the model is a one-line change in the reference pipeline; the measurement is the work.
3. **RTTM round-trip reports.** Export from here, import into `pyannote` / Kaldi / NeMo, and say what broke. Interop bugs are invisible from the inside.
4. **Third-party diarizer comparisons.** Anything emitting RTTM imports today. What is missing is someone reporting *where it disagrees with the manual grouping, and who was right*.
5. **UI translation.** See [Style](#style) — worth doing, but as a proper string-table PR rather than mixing languages on one screen.

## Things that will be declined

| proposal | why |
|---|---|
| Re-implementing VAD / segmentation / single-file diarization | `diarize` and `pyannote` do it better — [docs/FIELD-NOTES.md](docs/FIELD-NOTES.md) §4 |
| A server, an account, cloud sync, or a hosted demo | local-only is a privacy constraint, not an accident: voiceprints are biometric data |
| A build step, a framework, or a CDN in `index.html` | the zero-dependency single file is the whole point |
| Telemetry / analytics of any kind | same reason as the hosted demo |
| Widening thresholds, or dropping the measured limits | see [above](#the-one-rule-numbers-are-not-negotiable) |
| Word-level timestamps (CTM export) | the pipeline has none; open an issue with a use case first |

## Reporting a bug

Include the command you ran, the output of `python tools/inspect_embs.py` if it is a pipeline problem, and the browser console if it is a UI problem.

**Do not attach real recordings, real transcripts, or real voiceprint vectors.** Describe the *shape* of your data instead — that is almost always enough to reproduce a bug:

- number of recordings, clips per recording (roughly), speakers per recording (roughly)
- typical single-clip duration
- far-field (phone across a room) or close-mic?
- language
- bundled demo, or your own corpus?

If something reproduces only on your corpus, say what is different about it. `inspect_embs.py` is designed to be safe to paste verbatim.

## Security & privacy

This is a local-first tool that handles biometric data, so some bugs are privacy bugs rather than crashes. Report it as a security issue if you find any path where:

- the server binds to anything other than `127.0.0.1`
- audio, transcripts, or voiceprints are written outside the configured `out` directory
- anything makes an outbound network request
- `demo/` gains a file that is not synthetic

**Do not open a public issue with the details.** Open one titled `security report` with no technical content, and we will arrange a private channel from there.

## Style

- **Python** — 4 spaces, standard library first, `# -*- coding: utf-8 -*-` at the top.
- **JavaScript** — 2 spaces, `const`/`let`, semicolons, comments explain *why*.
- **Comments are in English** (as are all comments today). UI strings and the pipeline's console output are in Simplified Chinese, because that is who uses it; there is no i18n layer yet. When you add a string, match the file you are in — do not mix languages within one screen.
- **Comments should earn their place.** Several exist purely to record a measurement or a trap that cost real time — the noise-scaling note in `make_demo.py`, the `pushUndo` ordering note in `index.html`, the threshold justification in `tools/sync.py`. Keep them; do not "tidy" them away.
- There is no linter or formatter. Match the surrounding code.

## License

By contributing you agree your work is licensed under MIT (see [LICENSE](LICENSE)).
