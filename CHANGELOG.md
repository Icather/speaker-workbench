# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is [SemVer](https://semver.org/).

## [Unreleased]

Nothing yet.

## [0.1.0] — 2026-09-25

First public release. Extracted from a private tool that was being used to resolve speaker identities across a 10-recording, ~7-hour far-field corpus.

> Everything here went through a privacy pass **before** publication: the demo
> corpus is synthetic, every diagram is generated from it, and the one artefact
> that had been drawn from real data was caught and replaced — see *Fixed*.

### Added

**Workbench** (`index.html`, single file, zero runtime dependencies)

- **Label mode** — plays every clip of one speaker group back to back, across all recordings, with 1.6 s of lead-in and a 15 s per-clip cap
- **Proof mode** — per-line speaker reassignment, stored separately from the automatic grouping
- **Comparison mode** — raw diarizer IDs beside the grouping, disagreements highlighted, plus a bidirectional confusion matrix
- Full keyboard flow, undo/redo (150 steps), search (text / group / name), merge groups, single-clip loop, 0.75×–1.5× speed
- Name box with fuzzy + pinyin matching and identity tags (`name_tag1_tag2…`)
- Waveforms: whole-file overview plus a ±25 s zoom

**Voiceprint library — online enrollment** (`tools/sync.py:build_enrollment`)

- Named groups are collapsed into centroid voiceprints and stored in `speakers.json`
- Unnamed groups are scored against that library and get a suggestion, accepted with one keystroke
- **Two-tier thresholds measured on real far-field audio**: same-recording `hi = 0.83`, cross-recording `hi = 0.85`, and 1–2-clip groups capped at "weak hint" regardless of score

**Interop**

- Export: RTTM (10-column), SRT, VTT (with `<v name>` tags), CSV (BOM for Excel), TXT, Markdown, `voices.json`
- Import: RTTM (feeds comparison mode), `voices.json`
- Scope selectable per recording or over the whole corpus, with a live preview

**Pipeline** (`tools/sync.py`, `tools/serve.py`)

- Config-driven paths: `config.json` → `VOICE_DECK_*` env vars → in-repo demo default
- Localhost server with HTTP `Range` support (206) so audio seeking is instant
- Auto-detects new recordings/transcripts and refreshes incrementally
- Multi-extension input: `.m4a .mp3 .wav .flac .ogg .aac .opus .wma`

**Tooling**

- `tools/make_demo.py` — fully synthetic demo corpus; formant-synthesised speech (pure stdlib), invented people, fabricated transcripts. ~1.6 s to generate.
- `tools/calibrate.py` — reproduces the four threshold distributions on any corpus
- `tools/inspect_embs.py` — validates artefact formats before sync, and pinpoints `tag|start` key mismatches
- Two data-agnostic test suites (logic in a `vm` sandbox, plus real DOM via jsdom) wired into CI; the number of checks varies with the dataset

**Docs** — written during the pre-release pass, after reading the READMEs of the
neighbouring projects (`diarize`, `WhisperX`, `pyannote.audio`, `audino`) to see
what they get right

- `docs/ui.svg` — a labelled layout diagram of the workbench, so the project has a visual without shipping a screenshot (and therefore without shipping anyone's recordings)
- `docs/METHOD.md` and `docs/FIELD-NOTES.md` — the method, and the measured field notes behind the thresholds
- README: a capability comparison against `pyannote` / `diarize` / `WhisperX` / `GECKO` / `audino`; a four-step *how it works*; *use something else if…*; a short roadmap; runtime dependency licences; inline environment requirements
- CONTRIBUTING: an *if you change X, also do Y* change map; the division of labour between the two test suites **and what neither can catch**; a worked example for adding an export format; a definition-of-done checklist; a reporting path for privacy-class bugs

### Changed

- Diagrams are readable on GitHub's dark theme — mid-grey base plus a `prefers-color-scheme` override. The base was `#3a3a3a` text, which was effectively invisible on `#0d1117`
- `tools/calibrate.py` no longer looks credible on the bundled demo: it prints a prominent warning, because the synthetic voiceprints make same-person similarity come out ≈0.97 and different-person ≈0.16, neither of which happens on real audio
- **The demo corpus is bigger and 5× smaller.** 4 recordings / 77 lines / 12 groups / 6 voices, committed as 32 kbps mp3 (662 KB) instead of wav (3.1 MB). `sync.py` already skips transcoding when `audio/<tag>.mp3` exists, so a clone still needs no ffmpeg. The extra material matters: with 5 short groups nothing reached an `A` confidence badge and the "A 级" filter was empty, which made the demo look broken. It now shows A2 / B3 / C+5 / C2 and both confidence bands of suggestion (one 💡 and four weak `?` hints).
- Group fragments now share their parent's voice, so merging them is something a listener can actually verify by ear.
- `tools/sync.py` now warns before overwriting git-tracked demo assets (`audio/`, `data.js`) — the trap described in CONTRIBUTING, where pointing the pipeline at your own corpus silently stages real recordings for commit.

### Fixed

All of the following were caught **before** the first public release, i.e. no
published version ever contained them. They are recorded because the *class* of
mistake is the one this project has to be most careful about.

- **`docs/ui.svg` leaked real data.** The first version was drawn from the private workbench this project came from, so it carried four real names, a real class name, the source corpus size, and a verbatim quote from a real recording. It is now generated from the bundled demo (`make_demo.py`), which also makes it consistent with what a reader sees after cloning. The same cleanup removed two placeholders in `index.html` that used a real name as the example, one in the test suite, and later a pinyin example in both READMEs that used a real surname, a real email prefix and a real full-name romanisation.
- **`start.sh` was not executable** (`100644`). Windows has no execute bit, and git will not infer one, so a fresh Linux/macOS clone could not run `./start.sh` — the exact command the README gives. Fixed with `git update-index --chmod=+x`.
- The documented test count was wrong, and then wrong again: it said 100, then 136, and the demo change moved it to 140. The number varies because several checks are conditional on the data, so the docs no longer quote one and CONTRIBUTING explains why.

### Recorded limits

- A single clip carries essentially no identity information (same speaker 0.579 vs most-similar different speaker 0.567 — overlapping distributions)
- Speakers with 1–2 clips cannot be resolved
- Two different people with similar timbre are indistinguishable; a human must listen
- Content similarity is not identity (two groups both "hosting the same person" measured 0.478)

### Notes

- No `torch`, no model downloads, no network access at runtime. The embedding-extraction step lives outside this repo; `docs/METHOD.md` §1 and §6 document the interface.
- The bundled demo is synthetic by design — voiceprints are biometric data and real meeting audio is personal.
