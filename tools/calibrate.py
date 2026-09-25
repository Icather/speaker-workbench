# -*- coding: utf-8 -*-
"""Calibrate the suggestion thresholds used by sync.py's online enrollment.

Why this exists: a threshold picked by intuition is worthless. We measure, on
this project's own recordings, how separable "same person across recordings"
is from "different person across recordings" — then set the cut in the gap.

Method — leave-one-recording-out:
  * For a person seen in >= 2 recordings, build one centroid per recording,
    then correlate each pair.  That directly measures the *cross-recording*
    case the suggestion feature has to solve.
  * Negative control: centroids of *different* people, same recording, so we
    can see the false-match floor.

Usage:  python calibrate_suggest.py
"""
import io
import json
import os
import sys

import numpy as np

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


VOICE = _path("voiceprint", "demo/voiceprint")
EMBS = os.path.join(VOICE, "_embs_all.npz")
FMAP = os.path.join(VOICE, "_final_map.json")
OUT = _path("out", ".")
VOICES = os.path.join(OUT, "voices.json")
PRESET = os.path.join(OUT, "seed_voices.json")

# a clip-level centroid needs enough clips to be meaningful
MIN_SEG = 5

# Current live thresholds (must stay in sync with sync.py)
# keep in sync with sync.py
SUG = {"same": {"hi": 0.83, "lo": 0.76}, "cross": {"hi": 0.85, "lo": 0.70}}


def l2(m):
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def main():
    if not os.path.exists(EMBS):
        print("缺少 %s" % EMBS)
        return 1

    # ★ The bundled demo's embeddings are fabricated by make_demo.py, so every
    #   number below would be meaningless — and dangerously plausible-looking
    #   (same-speaker ~0.97, different-speaker ~0.16). Say so loudly: a
    #   threshold set from this output would be worse than one set by intuition.
    _demo = os.path.normcase(os.path.normpath(os.path.join(PROJ, "demo")))
    if os.path.normcase(os.path.normpath(VOICE)).startswith(_demo):
        print("!" * 70)
        print("  !! SYNTHETIC DATA — the numbers below mean NOTHING.")
        print("     合成的 demo 数据 —— 下面的数字没有任何意义，不要用它设阈值。")
        print("  The demo's voiceprints are invented by tools/make_demo.py, so")
        print("  same-person similarity comes out absurdly high (≈0.97) and")
        print("  different-person absurdly low (≈0.16). Neither happens on real audio.")
        print("")
        print("  To get usable numbers: copy config.example.json to config.json,")
        print("  point it at your own voiceprint output, and run this again.")
        print("!" * 70)
        print()
    z = np.load(EMBS, allow_pickle=True)
    E = l2(z["emb"].astype(np.float32))
    meta = [json.loads(x) for x in z["meta"]]
    fmap = json.load(io.open(FMAP, encoding="utf-8"))

    # (group, recording) -> row indices
    gt = {}
    for i, m in enumerate(meta):
        g = fmap.get("%s|%.2f" % (m["tag"], m["start"]))
        if g:
            gt.setdefault((g, m["tag"]), []).append(i)

    bygrp = {}
    for (g, tag), rows in gt.items():
        bygrp.setdefault(g, {})[tag] = rows

    # ---------- 1) within-person, ACROSS recordings (the real target) --------
    print("=" * 68)
    print("① 同一个人 · 跨录音（这正是「建议名」要解决的场景）")
    print("=" * 68)
    cross_pos, cross_weak = [], []
    for g, tags in sorted(bygrp.items()):
        if len(tags) < 2:
            continue
        cent = {t: E[r].mean(axis=0) for t, r in tags.items()}
        cent = {t: v / (np.linalg.norm(v) + 1e-9) for t, v in cent.items()}
        ts = sorted(cent)
        for a in range(len(ts)):
            for b in range(a + 1, len(ts)):
                s = float(cent[ts[a]] @ cent[ts[b]])
                both = min(len(tags[ts[a]]), len(tags[ts[b]]))
                if both >= MIN_SEG:
                    cross_pos.append(s)
                else:
                    cross_weak.append((g, ts[a], ts[b], s, both))
                    continue
                print("   %s  %s↔%s  %d段/%d段   cos=%.3f"
                      % (g, ts[a], ts[b], len(tags[ts[a]]), len(tags[ts[b]]), s))
    if cross_weak:
        ws = sorted(x[3] for x in cross_weak)
        print("   —— 被 MIN_SEG=%d 门槛挡掉的 %d 对（单侧 <5 段，不可信）"
              % (MIN_SEG, len(cross_weak)))
        print("      它们的 cos 中位 %.3f、最大 %.3f —— 与真同人的区间重叠，所以不能采信"
              % (float(np.median(ws)), ws[-1]))

    # ---------- 2) same recording, same person (upper reference) -------------
    print()
    print("=" * 68)
    print("② 同一个人 · 同一份录音（把该录音的段对半切，比对两个半区）")
    print("=" * 68)
    same_pos = []
    for g, tags in sorted(bygrp.items()):
        for t, rows in tags.items():
            if len(rows) < 6:
                continue
            h = len(rows) // 2
            a, b = E[rows[:h]].mean(axis=0), E[rows[h:]].mean(axis=0)
            a /= (np.linalg.norm(a) + 1e-9)
            b /= (np.linalg.norm(b) + 1e-9)
            s = float(a @ b)
            same_pos.append(s)
            print("   %s  %s   %d+%d 段   cos=%.3f" % (g, t, h, len(rows) - h, s))

    # ---------- 3) negative control: different people ------------------------
    print()
    print("=" * 68)
    print("③ 不同的人（阴对照）—— 每一份录音里各组的质心两两比对")
    print("=" * 68)
    neg = []
    for t in sorted({m["tag"] for m in meta}):
        cs = []
        for g, tags in bygrp.items():
            rows = tags.get(t)
            if rows and len(rows) >= 3:
                v = E[rows].mean(axis=0)
                cs.append((g, v / (np.linalg.norm(v) + 1e-9)))
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                s = float(cs[i][1] @ cs[j][1])
                neg.append(s)
    if neg:
        neg.sort()
        print("   对数 %d ｜ 中位 %.3f ｜ p95 %.3f ｜ 最大 %.3f"
              % (len(neg), float(np.median(neg)), float(np.percentile(neg, 95)), neg[-1]))

    # ---------- 4) negative control: different people, ACROSS recordings -----
    print()
    print("=" * 68)
    print("④ 不同的人 · 跨录音（阴对照，用已命名的人做真值）")
    print("=" * 68)
    vpath = VOICES if os.path.exists(VOICES) else PRESET
    named = {}
    try:
        st = json.load(io.open(vpath, encoding="utf-8"))
        named = st.get("voices", {}) or {}
    except Exception:
        pass
    if not named:
        print("   （%s 里还没有已命名的人）" % os.path.basename(vpath))
    else:
        alias = {}
        try:
            alias = (json.load(io.open(vpath, encoding="utf-8")).get("alias") or {})
        except Exception:
            pass

        def resolve(g):
            seen = set()
            while g in alias and g not in seen:
                seen.add(g); g = alias[g]
            return g

        per = {}
        for g, tags in bygrp.items():
            nm = named.get(resolve(g))
            if not nm:
                continue
            for t, rows in tags.items():
                if len(rows) >= 3:
                    per.setdefault(nm, {})[t] = rows
        ppl = {}
        for nm, tags in per.items():
            ppl[nm] = {t: (lambda v: v / (np.linalg.norm(v) + 1e-9))(E[r].mean(axis=0))
                       for t, r in tags.items()}
        print("   真值人物：%s" % "、".join("%s(%s)" % (n, "/".join(sorted(p)))
                                          for n, p in sorted(ppl.items())))
        cross_neg, same_neg = [], []
        ks = sorted(ppl)
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                a, b = ks[i], ks[j]
                for ta, va in ppl[a].items():
                    for tb, vb in ppl[b].items():
                        s = float(va @ vb)
                        (same_neg if ta == tb else cross_neg).append((a, b, ta, tb, s))
        for lst, label in ((same_neg, "同录音"), (cross_neg, "跨录音")):
            if not lst:
                continue
            vs = sorted(x[4] for x in lst)
            print("   异人·%s  n=%d  中位 %.3f  最大 %.3f" % (label, len(lst), float(np.median(vs)), vs[-1]))
            for a, b, ta, tb, s in sorted(lst, key=lambda x: -x[4])[:4]:
                print("      %s(%s) vs %s(%s)  cos=%.3f" % (a, ta, b, tb, s))

    # ---------- 5) verdict ---------------------------------------------------
    print()
    print("=" * 68)
    print("结论")
    print("=" * 68)
    if cross_pos:
        print("   跨录音·同人   n=%d  中位 %.3f  p10 %.3f  最小 %.3f"
              % (len(cross_pos), float(np.median(cross_pos)),
                 float(np.percentile(cross_pos, 10)), min(cross_pos)))
    if same_pos:
        print("   同录音·同人   n=%d  中位 %.3f  最小 %.3f"
              % (len(same_pos), float(np.median(same_pos)), min(same_pos)))
    if neg:
        print("   同录音·异人   n=%d  p95 %.3f  最大 %.3f"
              % (len(neg), float(np.percentile(neg, 95)), neg[-1]))
    print()
    print("   在用阈值：同场 hi=%.2f ｜ 跨场 hi=%.2f" % (SUG["same"]["hi"], SUG["cross"]["hi"]))
    if cross_pos:
        ok = sum(1 for s in cross_pos if s >= SUG["cross"]["hi"])
        print("   → 跨录音同人里，能过跨场阈值的：%d/%d" % (ok, len(cross_pos)))
    print("""
   怎么读这张表（★ 这是阈值唯一的依据）：
     同录音·异人 最大 ≈ %.3f   ← 同场吼错人的地板
     同录音·同人 最小 ≈ %.3f   ← 同场同一人的天花板参考
     → 同场阈值必须落在两者之间：建议 0.83
     跨录音·同人（样本≥%d）≈ %.3f–%.3f
     → 跨场阈值取稍低于下沿：建议 0.85
   注意 1–2 段的「跨录音匹配」即使到 0.80 也不可信——与真同人区间重叠，这就是
   「单段在远场录音上没有区分度」的直接后果。
""" % (max(x[4] for x in same_neg) if 'same_neg' in dir() and same_neg else float('nan'),
       min(same_pos) if same_pos else float('nan'),
       MIN_SEG, min(cross_pos) if cross_pos else float('nan'),
       max(cross_pos) if cross_pos else float('nan')))
    return 0


if __name__ == "__main__":
    sys.exit(main())
