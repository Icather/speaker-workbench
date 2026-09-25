# -*- coding: utf-8 -*-
"""Voice-labeling workbench — data pipeline.

Scans recordings + transcripts + voiceprint grouping and emits:
  <OUT>/audio/<tag>.mp3   browser-friendly audio (16 kHz mono, 32 kbps)
  <OUT>/data.js           window.TAPE_DATA = {...}   (audios, segments, groups, waveforms)

Usage:
  python sync.py                 # incremental (only new/changed)
  python sync.py --force         # rebuild audio + waveforms
  python sync.py --data-only     # skip audio transcoding / waveform extraction
"""
import base64
import io
import json
import os
import re
import subprocess
import sys
import time

import numpy as np

try:
    from pypinyin import lazy_pinyin, Style
except ImportError:                       # pinyin search degrades to Chinese-only
    lazy_pinyin = None

# ---------------------------------------------------------------- config
# Nothing here is tied to one machine: paths come from config.json (next to
# this project) or VOICE_DECK_* environment variables, and fall back to the
# in-project demo layout.
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)

CFG_FILE = "config.json"


def _load_cfg():
    fp = os.path.join(PROJ, CFG_FILE)
    if os.path.exists(fp):
        try:
            return json.load(io.open(fp, encoding="utf-8"))
        except Exception as e:
            print("  ! %s 解析失败，回退默认路径：%s" % (CFG_FILE, e))
    return {}


CFG = _load_cfg()


def _path(key, default):
    """config.json > VOICE_DECK_<KEY> env var > default; relative to PROJ."""
    v = os.environ.get("VOICE_DECK_" + key.upper()) or CFG.get(key) or default
    return v if os.path.isabs(v) else os.path.normpath(os.path.join(PROJ, v))


REC = _path("recordings", "demo/recordings")
CONV = _path("transcripts", "demo/transcripts")
VOICE = _path("voiceprint", "demo/voiceprint")
OUT = _path("out", ".")
AUDIO = os.path.join(OUT, "audio")

FINAL_MAP = os.path.join(VOICE, "_final_map.json")
GROUPS = os.path.join(VOICE, "_groups_final.json")
VOICES = os.path.join(OUT, "voices.json")
ROSTER = os.path.join(VOICE, "_roster.json")
PEOPLE_EXTRA = _path("people", "people_extra.json")
if not os.path.exists(PEOPLE_EXTRA):          # demo fallback
    _alt = os.path.join(PROJ, "demo", "people.json")
    if os.path.exists(_alt):
        PEOPLE_EXTRA = _alt
EMBS = os.path.join(VOICE, "_embs_all.npz")
SPEAKERS = os.path.join(OUT, "speakers.json")

# 建议名（online enrollment）阈值 —— 由 tools/calibrate_suggest.py 在这批录音上实测得到，
# 不是拍脑袋。实测（质心余弦）：
#   同录音 真同人 0.834–0.985 ｜ 同录音 真异人 675 对: 中位 0.444 / p95 0.712 / 最大 0.822
#     → 分界在 0.828，取 0.83
#   跨录音 真同人（两侧均 ≥5 段）0.913–0.936 ｜ 跨录音真异人真值尚缺（需先认人）
#     → 取 0.85（比同场更严，因为跨录音缺阴对照）
# ★ 必须分开：同录音的相似度基线天生就高，混用一个阈值会让假的淹没真的
SUG = {
    "same":  {"hi": 0.83, "lo": 0.76},     # 建议组与声纹库该人出现在同一份录音
    "cross": {"hi": 0.85, "lo": 0.70},     # 只出现在别的录音 → 真·跨录音认人
}
# ★ 样本不足的组永远只能拿"弱提示"：1–2 段的质心≈单段，
#   而实测单段在这批远场录音上几乎无区分度（同人 0.579 vs 最像的异人 0.567）
FEW_SEG = 3
MAXSEG_PER_PERSON = 80

AUDIO_EXT = (".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".opus", ".wma")
MP3_BITRATE = "32k"
WAVE_WIN_MS = 200          # one waveform sample per 200 ms

FORCE = "--force" in sys.argv
DATA_ONLY = "--data-only" in sys.argv


# ---------------------------------------------------------------- discovery
def date_of(stem):
    """Extract YYYYMMDD from a recording filename; None when unknown."""
    m = re.match(r"(\d{4})(\d{2})(\d{2})[_ ]", stem)
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", stem)
    if m:
        return "%s%02d%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{4})(\d{1,2})月(\d{1,2})日", stem)
    if m:
        return "%s%02d%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{4})(\d{2})(\d{2})$", stem)
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    return None


def build_tags():
    """Assign stable tags: MMDD, plus a/b/c when several recordings share a day."""
    items = []
    for fn in sorted(os.listdir(REC)):
        ext = os.path.splitext(fn)[1].lower()
        if ext not in AUDIO_EXT:
            continue
        stem = fn[:-len(ext)]
        d = date_of(stem)
        mt = os.path.getmtime(os.path.join(REC, fn))
        items.append({"fn": fn, "stem": stem, "date": d, "mtime": mt})
    # sort: date first (unknown dates fall back to mtime order), then filename time prefix
    items.sort(key=lambda x: (x["date"] or "99999999", x["stem"]))
    byday = {}
    for it in items:
        key = it["date"] or ("X%d" % it["mtime"])
        byday.setdefault(key, []).append(it)
    for key, lst in byday.items():
        for i, it in enumerate(lst):
            if it["date"]:
                mmdd = it["date"][4:]
                it["tag"] = mmdd + ("" if len(lst) == 1 else chr(ord("a") + i))
            else:
                it["tag"] = "u%d" % it["mtime"]
    return items


# ---------------------------------------------------------------- audio
def ffprobe_dur(path):
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", path],
                           capture_output=True, text=True, timeout=60)
        return round(float(p.stdout.strip()), 2)
    except Exception:
        return 0.0


def to_mp3(src, dst):
    # -fflags +bitexact strips the "encoder=Lavf<version>" container tag: it is a
    # build fingerprint of the machine that transcoded the file, and it also makes
    # the output reproducible across ffmpeg versions.
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src,
                    "-ac", "1", "-ar", "16000", "-b:a", MP3_BITRATE,
                    "-map_metadata", "-1", "-fflags", "+bitexact", dst], check=True)


def waveform(src, win_ms=WAVE_WIN_MS, sr=8000):
    """Peak-envelope waveform, base64 of one byte per window (0-255)."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src,
                        "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                       capture_output=True)
    a = np.frombuffer(p.stdout, dtype="<i2").astype(np.float32) / 32768.0
    win = int(sr * win_ms / 1000)
    n = len(a) // win
    if n == 0:
        return ""
    blk = a[:n * win].reshape(n, win)
    rms = np.sqrt((blk ** 2).mean(axis=1))
    ref = np.percentile(rms, 99.5)
    if ref <= 0:
        ref = 1.0
    q = np.clip(rms / ref * 255.0, 0, 255).astype(np.uint8)
    return base64.b64encode(q.tobytes()).decode("ascii")


# ---------------------------------------------------------------- people
def pystr(name, tags):
    """Build the pinyin search blob: full pinyin + initials for the name,
    initials only for tags (keeps data.js small)."""
    if lazy_pinyin is None:
        return ""
    out = []
    if name:
        out.append("".join(lazy_pinyin(name)))
        out.append("".join(lazy_pinyin(name, style=Style.FIRST_LETTER)))
    for t in tags:
        if t:
            out.append("".join(lazy_pinyin(t, style=Style.FIRST_LETTER)))
    return " ".join(out).lower()


def build_people():
    """Name candidates for the autocomplete: roster + hand-curated VIP list."""
    people = {}
    if os.path.exists(ROSTER):
        try:
            r = json.load(io.open(ROSTER, encoding="utf-8"))
            for n, v in r.items():
                tags = [t for t in (v.get("班级"), v.get("专业")) if t]
                people[n] = {"n": n, "t": tags, "pri": 10, "s": pystr(n, tags)}
        except Exception as e:
            print("  ! _roster.json 读取失败：%s" % e)
    if os.path.exists(PEOPLE_EXTRA):
        try:
            ex = json.load(io.open(PEOPLE_EXTRA, encoding="utf-8"))
            for q in ex.get("people", []):
                if not q.get("n"):
                    continue
                tags = q.get("t", [])
                people[q["n"]] = {"n": q["n"], "t": tags, "pri": q.get("pri", 50),
                                   "s": pystr(q["n"], tags)}
        except Exception as e:
            print("  ! people_extra.json 解析失败：%s" % e)
    out = sorted(people.values(), key=lambda x: (-x["pri"], x["n"]))
    print("  人物库 %d 人（其中重点 %d）" % (len(out), sum(1 for x in out if x["pri"] >= 50)))
    return out


# ------------------------------------------------ speakers (online enrollment)
def _l2(m):
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def _resolve(g, alias):
    """Follow alias chain (merges) to the canonical group id."""
    seen = set()
    while g in alias and g not in seen:
        seen.add(g)
        g = alias[g]
    return g


def load_embs():
    """-> (normed embeddings (N,192), meta list) or (None, None)."""
    if not os.path.exists(EMBS):
        return None, None
    try:
        z = np.load(EMBS, allow_pickle=True)
        emb = z["emb"].astype(np.float32)
        meta = [json.loads(x) for x in z["meta"]]
        return _l2(emb), meta
    except Exception as e:
        print("  ! _embs_all.npz 读取失败：%s" % e)
        return None, None


def build_enrollment(seg2grp, state):
    """Online enrollment.

    Turns every group you have already named into a *centroid voiceprint*,
    then compares each still-unnamed group against that library to propose a
    name.  This is the piece no off-the-shelf diarizer ships (they stop at
    SPEAKER_00/01 and never learn identities across recordings).

    Returns (speakers_meta, suggestions)
      speakers.json : {name: {"n": samples, "v": [192 floats]}}
      suggestions   : {group: {"n": name, "s": score, "c": "hi"|"lo"}}
    """
    E, meta = load_embs()
    if E is None:
        return {}, {}
    voices = state.get("voices", {}) or {}
    alias = state.get("alias", {}) or {}

    bygrp, n_rows = {}, 0
    for i, m in enumerate(meta):
        g = seg2grp.get("%s|%.2f" % (m["tag"], m["start"]))
        if g:
            bygrp.setdefault(g, []).append(i)
        n_rows += 1

    # 1) one centroid per already-named person
    per = {}
    for g, rows in bygrp.items():
        nm = voices.get(_resolve(g, alias))
        if nm:
            per.setdefault(nm, []).extend(rows)
    names, cents, meta_out, p_tags = [], [], {}, {}
    for nm, rows in per.items():
        if len(rows) > MAXSEG_PER_PERSON:                 # even sampling, avoid one huge group dominating
            step = len(rows) / float(MAXSEG_PER_PERSON)
            rows = [rows[int(k * step)] for k in range(MAXSEG_PER_PERSON)]
        if len(rows) < 2:                                 # a single clip is not enough to enrol
            continue
        v = E[rows].mean(axis=0)
        v = v / (np.linalg.norm(v) + 1e-9)
        names.append(nm)
        cents.append(v)
        p_tags[nm] = sorted({meta[r]["tag"] for r in rows})
        meta_out[nm] = {"n": len(rows), "tags": p_tags[nm],
                        "v": [round(float(x), 4) for x in v]}
    if not cents:
        print("  声纹库：尚无已认的人（先在①认人模式里标几个人，这里就会自动建库）")
        return {}, {}

    C = np.vstack(cents)                                   # (P,192) already unit-norm

    # 2) propose names for the unnamed groups (layered thresholds)
    sugg = {}
    for g, rows in sorted(bygrp.items()):
        if voices.get(_resolve(g, alias)):
            continue                                       # already named → no suggestion
        if len(rows) > MAXSEG_PER_PERSON:
            step = len(rows) / float(MAXSEG_PER_PERSON)
            rows = [rows[int(k * step)] for k in range(MAXSEG_PER_PERSON)]
        v = E[rows].mean(axis=0)
        v = v / (np.linalg.norm(v) + 1e-9)
        sims = C.dot(v)
        gtags = {meta[r]["tag"] for r in rows}
        enough = len(rows) >= FEW_SEG
        hit = None
        for j in np.argsort(-sims)[:3]:                    # consider the 3 closest people, not just #1
            nm = names[int(j)]
            same = bool(gtags & set(p_tags[nm]))
            band = SUG["same"] if same else SUG["cross"]
            s = float(sims[int(j)])
            if s >= band["hi"] and enough:
                hit = (nm, s, "hi", same); break
            if s >= band["lo"] and hit is None:
                hit = (nm, s, "lo", same)
        if hit:
            nm, s, c, same = hit
            sugg[g] = {"n": nm, "s": round(s, 3), "c": c, "same": same}

    with io.open(SPEAKERS, "w", encoding="utf-8") as f:
        json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"),
                   "thresholds": SUG,
                   "people": meta_out}, f, ensure_ascii=False, indent=1)
    print("  声纹库：%d 人（共 %d 段）；建议名 %d 个（高信 %d / 弱提示 %d）"
          % (len(names), sum(v["n"] for v in meta_out.values()), len(sugg),
             sum(1 for x in sugg.values() if x["c"] == "hi"),
             sum(1 for x in sugg.values() if x["c"] == "lo")))
    return meta_out, sugg


# ---------------------------------------------------------------- transcript
def ts(t):
    h, m, s = t.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_moss(path):
    """[(start, end, text, moss_speaker_id)]"""
    out = []
    if not os.path.exists(path):
        return out
    raw = io.open(path, encoding="utf-8").read().strip()
    for b in raw.split("\n\n"):
        L = b.strip().split("\n")
        if len(L) < 3:
            continue
        m = re.match(r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)", L[1])
        if not m:
            continue
        sp = re.match(r"\(Speaker\s*(\d+)\)\s*(.*)", " ".join(L[2:]))
        out.append((ts(m.group(1)), ts(m.group(2)),
                    (sp.group(2) if sp else " ".join(L[2:])).strip(),
                    (sp.group(1) if sp else "")))
    return out


def warn_if_overwriting_tracked():
    """★ 本项目最容易踩的那个隐私坑：`audio/` 与 `data.js` **不是** git-ignored。

    它们是刻意提交的 demo 资产 —— 好处是一个空 clone 打开就能用；代价是当管线指向
    **你自己的语料**时，本脚本会**就地覆盖**这两个已被跟踪的路径，之后一句
    `git add .` 就把真实录音和真实转写提交上去了。而 CONTRIBUTING 里写的恰恰是
    "Never commit real recordings"。所以写入之前先把这件事说清楚。
    """
    try:
        p = subprocess.run(["git", "ls-files", "--", "data.js", "audio"],
                           capture_output=True, cwd=OUT)
        tracked = [l for l in p.stdout.decode("utf-8", "replace").split("\n") if l.strip()]
    except Exception:
        return
    if not tracked:
        return
    print("\n" + "!" * 70)
    print("⚠️  即将覆盖 **已被 git 跟踪** 的 demo 资产（%d 个）：" % len(tracked))
    for t in tracked[:6]:
        print("      %s" % t)
    if len(tracked) > 6:
        print("      … 其余 %d 个" % (len(tracked) - 6))
    print("    若这次用的是你自己的真实录音 / 转写，跑完后**不要**提交这两个路径：")
    print("        git status --short      # data.js 与 audio/ 不应出现在输出里")
    print("    要把 demo 恢复成合成数据：python tools/make_demo.py && python tools/sync.py")
    print("!" * 70 + "\n")


def main():
    warn_if_overwriting_tracked()
    os.makedirs(AUDIO, exist_ok=True)
    items = build_tags()
    print("发现 %d 份录音" % len(items))

    seg2grp = json.load(io.open(FINAL_MAP, encoding="utf-8")) if os.path.exists(FINAL_MAP) else {}
    groups = json.load(io.open(GROUPS, encoding="utf-8")) if os.path.exists(GROUPS) else {}
    state = {}
    if os.path.exists(VOICES):
        try:
            rawst = json.load(io.open(VOICES, encoding="utf-8"))
            if isinstance(rawst, dict):
                # new format: {voices:{...}, overrides:{...}, dunno:{...}}
                # legacy format: {P001:"name", ...}
                state = rawst if ("voices" in rawst or "overrides" in rawst) else {"voices": rawst}
        except Exception as e:
            print("  ! voices.json 解析失败：%s" % e)

    audios, segs, waves = [], [], {}
    t0 = time.time()
    for it in items:
        tag = it["tag"]
        src = os.path.join(REC, it["fn"])
        mp3 = os.path.join(AUDIO, tag + ".mp3")
        if not DATA_ONLY and (FORCE or not os.path.exists(mp3)):
            to_mp3(src, mp3)
            print("  转码 %-8s -> %s (%.1f MB)" % (tag, os.path.basename(mp3),
                                                  os.path.getsize(mp3) / 1e6))
        # prefer the transcoded file: the source may have been removed to save space
        dur = ffprobe_dur(mp3 if os.path.exists(mp3) else src)
        srt = os.path.join(CONV, it["stem"] + ".moss.srt")
        recs = parse_moss(srt)
        for s, e, t, m in recs:
            segs.append({"a": tag, "s": round(s, 2), "e": round(e, 2),
                         "t": t, "m": m,
                         "g": seg2grp.get("%s|%.2f" % (tag, s), "")})
        audios.append({
            "id": tag, "title": it["stem"], "file": "audio/%s.mp3" % tag,
            "dur": dur, "n": len(recs), "hasSrt": len(recs) > 0,
        })
        if not DATA_ONLY:
            waves[tag] = waveform(src)

    spk, sugg = build_enrollment(seg2grp, state)
    for g, sg in sugg.items():                 # annotate a copy — never touch the source groups file
        if g in groups:
            groups[g] = dict(groups[g], suggest=sg)

    data = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "audios": audios,
        "segs": segs,
        "groups": groups,
        "waves": waves,
        "voices": state.get("voices", {}),
        "state": state,
        "people": build_people(),
        "speakers": spk,
        "suggest": sugg,
    }
    js = "window.TAPE_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    with io.open(os.path.join(OUT, "data.js"), "w", encoding="utf-8") as f:
        f.write(js)
    print("\n数据：%d 份录音 / %d 段 / %d 组" % (len(audios), len(segs), len(groups)))
    print("data.js %.0f KB   （用时 %.0fs）" % (len(js.encode("utf-8")) / 1024, time.time() - t0))
    missing = [a["id"] for a in audios if not a["hasSrt"]]
    if missing:
        print("⚠️ 以下录音尚无转写稿（页面会显示为空）：%s" % ", ".join(missing))


if __name__ == "__main__":
    main()
