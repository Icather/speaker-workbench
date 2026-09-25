# -*- coding: utf-8 -*-
"""Check that your voiceprint artefacts match the format this workbench expects.

Run this right after pointing config.json at your own pipeline output — it
catches the format mistakes that would otherwise show up as a silently empty UI.

    python tools/inspect_embs.py

Everything is optional: without _embs_all.npz the workbench still runs, you just
lose the name suggestions. This script tells you exactly which parts are usable.
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)


def _cfg():
    fp = os.path.join(PROJ, "config.json")
    if os.path.exists(fp):
        try:
            return json.load(io.open(fp, encoding="utf-8"))
        except Exception:
            pass
    return {}


CFG = _cfg()


def _path(key, default):
    v = os.environ.get("VOICE_DECK_" + key.upper()) or CFG.get(key) or default
    return v if os.path.isabs(v) else os.path.normpath(os.path.join(PROJ, v))


REC = _path("recordings", "demo/recordings")
CONV = _path("transcripts", "demo/transcripts")
VOICE = _path("voiceprint", "demo/voiceprint")
OUT = _path("out", ".")

EMBS = os.path.join(VOICE, "_embs_all.npz")
FMAP = os.path.join(VOICE, "_final_map.json")
GROUPS = os.path.join(VOICE, "_groups_final.json")

AUDIO_EXT = (".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".opus", ".wma")

problems = []
notes = []


def ok(msg):
    print("  ✓ " + msg)


def bad(msg):
    print("  ✗ " + msg)
    problems.append(msg)


def warn(msg):
    print("  ! " + msg)
    notes.append(msg)


def main():
    print("=" * 62)
    print("  speaker-workbench — data check")
    print("=" * 62)
    print("  recordings : %s" % REC)
    print("  transcripts: %s" % CONV)
    print("  voiceprint : %s" % VOICE)
    print("  out        : %s" % OUT)

    # ---------------- recordings + transcripts ----------------
    print("\n[1] recordings & transcripts")
    if not os.path.isdir(REC):
        bad("recordings directory does not exist")
        recs = []
    else:
        recs = sorted(f for f in os.listdir(REC) if os.path.splitext(f)[1].lower() in AUDIO_EXT)
        if recs:
            ok("%d audio file(s): %s" % (len(recs), ", ".join(recs[:6]) + ("…" if len(recs) > 6 else "")))
        else:
            bad("no audio files with a recognised extension")

    stems = [os.path.splitext(f)[0] for f in recs]
    with_srt = [s for s in stems if os.path.exists(os.path.join(CONV, s + ".moss.srt"))]
    if stems:
        if len(with_srt) == len(stems):
            ok("every recording has a .moss.srt transcript")
        elif with_srt:
            warn("%d/%d have transcripts; the rest will show up empty in proof mode: %s"
                 % (len(with_srt), len(stems),
                    ", ".join(s[:18] for s in stems if s not in with_srt)))
        else:
            bad("no matching <stem>.moss.srt found in the transcripts directory")

    # sample one cue so a formatting mistake is obvious
    for s in with_srt[:1]:
        p = os.path.join(CONV, s + ".moss.srt")
        head = io.open(p, encoding="utf-8").read(400)
        if "(Speaker" in head:
            ok("transcript uses the expected '(Speaker N)' prefix")
        else:
            bad("%s.moss.srt has no '(Speaker N)' prefix — the pipeline will split "
                "correctly but comparison mode will be blank" % s)

    # ---------------- final map ----------------
    print("\n[2] _final_map.json (segment -> group)")
    fmap = {}
    if not os.path.exists(FMAP):
        bad("missing — every segment will be unassigned")
    else:
        try:
            fmap = json.load(io.open(FMAP, encoding="utf-8"))
        except Exception as e:
            bad("cannot parse: %s" % e)
        if fmap:
            k = next(iter(fmap))
            ok("%d entries; sample key %r -> %r" % (len(fmap), k, fmap[k]))
            if "|" not in k:
                bad("keys must be '<tag>|<start with 2 decimals>'")
            tags = {kk.split("|")[0] for kk in fmap}
            ok("covers %d recording tag(s): %s" % (len(tags), ", ".join(sorted(tags)[:8])))

    # ---------------- groups ----------------
    print("\n[3] _groups_final.json (per-group stats)")
    groups = {}
    need = ("段数", "时长min", "出现录音")
    if not os.path.exists(GROUPS):
        bad("missing — the group list will be empty")
    else:
        try:
            groups = json.load(io.open(GROUPS, encoding="utf-8"))
        except Exception as e:
            bad("cannot parse: %s" % e)
        if groups:
            g0 = next(iter(groups))
            missing = [f for f in need if f not in groups[g0]]
            if missing:
                bad("group %s is missing required fields: %s" % (g0, missing))
            else:
                ok("%d groups, required fields present" % len(groups))
            extra = [f for f in ("同录音一致性", "跨录音一致性") if f not in groups[g0]]
            if extra:
                warn("optional confidence fields absent (%s) — sorting and the A/B/C badges "
                     "will fall back to defaults" % ", ".join(extra))

    # ---------------- embeddings ----------------
    print("\n[4] _embs_all.npz (embeddings) — optional, enables name suggestions")
    if not os.path.exists(EMBS):
        warn("not found. Everything works except 'suggest a name'. "
             "See docs/METHOD.md §1 for the format.")
        return report()

    try:
        import numpy as np
    except ImportError:
        warn("numpy is not installed, cannot inspect the archive")
        return report()

    try:
        z = np.load(EMBS, allow_pickle=True)
    except Exception as e:
        bad("cannot open: %s" % e)
        return report()

    if "emb" not in z or "meta" not in z:
        bad("archive must contain 'emb' and 'meta'")
        return report()

    emb, meta = z["emb"], z["meta"]
    ok("emb %s %s ｜ meta %d rows" % (emb.shape, emb.dtype, len(meta)))
    if len(meta) != emb.shape[0]:
        bad("meta has %d rows but emb has %d" % (len(meta), emb.shape[0]))
    if emb.shape[1] != 192:
        warn("expected 192 dimensions (CAM++), got %d — suggestions still work, "
             "but keep this in mind if you switch models" % emb.shape[1])

    try:
        m0 = json.loads(meta[0])
        ok("meta sample: %s" % json.dumps(m0, ensure_ascii=False)[:110])
        missing = [f for f in ("tag", "start") if f not in m0]
        if missing:
            bad("meta rows must contain 'tag' and 'start' (missing %s)" % missing)
    except Exception as e:
        bad("meta rows must be JSON strings: %s" % e)

    if fmap:
        hit = 0
        for x in meta:
            try:
                m = json.loads(x)
                if fmap.get("%s|%.2f" % (m["tag"], m["start"])):
                    hit += 1
            except Exception:
                pass
        pct = 100.0 * hit / max(1, len(meta))
        if pct > 90:
            ok("%.0f%% of embeddings map to a group" % pct)
        elif pct > 0:
            warn("only %.0f%% of embeddings map to a group — check that 'start' values "
                 "match the keys in _final_map.json exactly (2 decimals)" % pct)
        else:
            bad("no embedding maps to a group — the 'tag|start' keys do not line up")

    return report()


def report():
    print("\n" + "=" * 62)
    if problems:
        print("  %d problem(s) found — fix these first:" % len(problems))
        for p in problems:
            print("    · " + p)
    else:
        print("  No blocking problems. Run:  python tools/sync.py")
    if notes:
        print("\n  %d note(s):" % len(notes))
        for n in notes:
            print("    · " + n)
    print("=" * 62)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
