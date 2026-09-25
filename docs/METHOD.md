# Method

How the cross-recording layer works, why it is built this way, and what the measured limits are. Everything here is reproducible from the scripts in `tools/`.

---

## 1. Data contracts

The workbench reads a small, deliberately boring set of files. Any pipeline that can emit these can be plugged in.

### `recordings/<name>.m4a` (or wav/mp3/flac/ogg/aac/opus/wma)

The filename should contain a date — `20260105_140000_standup.m4a` — because `sync.py` derives the recording **tag** from it (`0105`; several recordings on one day become `0105a`, `0105b`, …). The tag is what appears everywhere in the UI and in every export.

### `transcripts/<same stem>.moss.srt`

Plain SRT where each cue is prefixed with the diarizer's own speaker id:

```
1
00:00:00,000 --> 00:00:03,520
(Speaker 1) 今天主要过三件事：场地、预算，还有报名表。
```

The `(Speaker N)` value is kept and shown in comparison mode, but it is **never** used as the grouping — it only serves as a second opinion.

### `voiceprint/_final_map.json`

```json
{ "0105|0.00": "P001", "0105|3.85": "P002", "…": "…" }
```

Key is `"<tag>|<start seconds, 2 decimals>"`. This is the machine grouping that the human will correct.

### `voiceprint/_groups_final.json`

Per-group statistics used by the UI to sort, filter and display confidence:

| field | meaning |
|---|---|
| `段数`, `时长min` | clip count and total speaking time |
| `出现录音`, `各录音段数` | which recordings this group appears in (the `★` in the list) |
| `同录音一致性`, `跨录音一致性` | mean cosine within/across recordings — **kept separate on purpose** |
| `样本` | a few representative clips (`tag`, `t`, `text`) |

### `voiceprint/_embs_all.npz`

`emb` — an `N × 192` float32 matrix of CAM++ speaker embeddings — plus `meta`, an array of JSON strings `{"tag","start","end","moss","text"}` aligned row-by-row with `emb`.

Without this file everything still works; you just lose the name suggestions.

---

## 2. Why two-stage clustering

A single agglomerative pass over the embeddings **does not work** on this kind of material. Measured on a 96-minute far-field corpus:

- Plain `complete linkage` at a cosine distance that looks reasonable produces groups whose **centroids are 0.95–0.98 similar to each other** — i.e. one person is split into 5–6 clusters.
- `centroid`, `average` and `ward` linkage all *chain*: the largest cluster swallows the whole recording (969 clips / 105 minutes in one case).
- No single linkage threshold can merge a genuine cross-recording pair, because the two halves of one person can sit at cosine **0.579** while unrelated people reach **0.567**.

The configuration that survives is:

```
stage 1  complete linkage @ euclidean 0.90   (≈ cosine 0.595)  → over-segment into pure little clusters
stage 2  centroid linkage @ euclidean 0.60   (≈ cosine 0.82)   on the stage-1 cluster centroids
```

Stage 1 buys **purity** (no chaining), stage 2 re-joins the fragments by comparing *centroids*, which is exactly where the single-clip noise averages out.

Effect on the same corpus:

| | groups | median within-group consistency | share of low-consistency groups |
|---|---:|---:|---:|
| single stage | 329 | 0.64 | **26 %** |
| two stages | 464 | **0.72** | **0.6 %** |

> Conversion worth remembering: on unit-normalised vectors `cos = 1 - d²/2`. pyannote's documented `clustering.threshold = 0.7155` (euclidean) equals cosine **0.744** — close to the 0.82 used here, which is a useful sanity check rather than a coincidence.

---

## 3. Thresholds are measured, never guessed

`tools/calibrate.py` computes four distributions on your own corpus:

1. **same person, same recording** — split each group's clips in half and correlate the two halves
2. **different people, same recording** — all group centroids within one recording, pairwise
3. **same person, across recordings** — one centroid per (person, recording), correlated pairwise, gated on ≥5 clips per side
4. **different people, across recordings** — uses the names in `voices.json` once you have some

Measured on a real 10-recording far-field corpus (attached to the project this was extracted from):

| scenario | n | median | p95 | max / min |
|---|---:|---:|---:|---:|
| same person · same recording | 31 | 0.944 | — | min **0.834** |
| different people · same recording | 675 | 0.444 | 0.712 | max **0.822** |
| same person · across recordings (≥5 clips both sides) | — | 0.925 | — | 0.913 – 0.936 |
| 1–2 clip groups (cross-recording) | 42 | 0.69 | — | max 0.80 |

The same-recording cut is therefore **0.828**; we use 0.83. The cross-recording cut is set more conservatively at 0.85 because the negative class there lacks ground truth.

**The trap this avoided:** the first implementation used one threshold (0.72) for everything and produced **39 suggestions, every one of them wrong** — because most candidate groups were *within* a single recording, where the similarity floor is naturally higher. Separate the bands.

**The second trap:** 1–2 clip groups reach 0.80 while genuine same-speaker pairs start at 0.913 — but the *noise* floor for tiny groups overlaps the positive class, so small groups are capped at "weak hint" regardless of their score.

---

## 4. Voiceprint library (online enrollment)

`sync.py:build_enrollment()`:

1. For every group you have named, gather its clips (even-sampled to at most 80, so one huge group cannot dominate), average the embeddings, L2-normalise → one **centroid voiceprint** per person. Stored in `speakers.json` together with the recordings that person appears in.
2. For every still-unnamed group, compute the same centroid and compare against the whole library. Take the three nearest people; accept the first that clears its band.
3. Write the result into `data.js` as `groups[g].suggest = {n, s, c, same}` and let the UI show `💡` (high) or `?` (weak).

Everything is a pure cosine comparison against a stored mean — no training, no fine-tuning, no model fitting. That is also how production systems do it.

---

## 5. Honest limits

| limit | evidence |
|---|---|
| single clips carry essentially no identity | same person across recordings: **0.579**; most similar *different* person: **0.567** |
| brief speakers cannot be resolved | someone with 1–2 clips can only ever get a weak hint |
| similar timbres are indistinguishable | the pipeline answers "same voice?", not "which of these two similar voices?" |
| content similarity ≠ identity | two groups both "hosting and introducing the same person": **0.478** |
| ~3.6 minutes of a 96-minute recording had no usable speech at all | three independent transcripts agreed; level metering confirmed it was silence, not transcription loss |

The UI is built around accepting these limits: machine proposes, human decides, one keystroke per decision, undo everywhere.

---

## 6. Producing these files from your own audio

The workbench is the *last* mile, so this repo intentionally carries no heavy dependencies: no `torch`, no model downloads, and the whole test suite runs in CI on plain Node.

The reference extraction pipeline for the corpus this was built on does:

```
for each recording:
    ffmpeg  -ar 16000 -ac 1                      # normalise
    slice   per SRT cue, keep cues of 2–12 s     # clip length sweet spot
    model   iic/speech_campplus_sv_zh-cn_16k-common   (3D-Speaker, ~28 MB)
    emit    emb (N × 192), meta (JSON per row)

then:
    stage 1  complete linkage @ euclidean 0.90   → pure mini-clusters
    stage 2  centroid linkage @ euclidean 0.60   → merge their centroids
    emit     _final_map.json, _groups_final.json
```

Any embedding model works as long as it produces a fixed-length vector per clip; CAM++ is simply a strong, small, Chinese-first choice (ECAPA-TDNN / WeSpeaker are drop-in equivalents).

**Before running `sync.py`, validate your artefacts:**

```bash
python tools/inspect_embs.py
```

It checks the four inputs one at a time, verifies that `meta` rows line up with `emb`, and — most importantly — that your `"<tag>|<start>"` keys actually match between `_embs_all.npz` and `_final_map.json`. A mismatch there is the single most common cause of a "why is the page empty" report, because it fails silently.

`tools/make_demo.py` is a small, dependency-free worked example of every one of these formats (it writes a real `_embs_all.npz` from synthesised voiceprints).
