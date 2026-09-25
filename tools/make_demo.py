# -*- coding: utf-8 -*-
"""Generate a fully synthetic demo dataset — no real audio, names or transcripts.

Why synthetic: voiceprints are biometric data and real meeting audio is
personal. This script invents a small club from scratch so anybody can clone
the repo and try the workbench without touching anyone's recordings.

What it produces (all deterministic, no network):
    demo/recordings/*.mp3           formant-synthesised "speech"
    demo/transcripts/*.moss.srt     diarised transcript in the expected format
    demo/voiceprint/_embs_all.npz   speaker embeddings (numpy)
    demo/voiceprint/_final_map.json segment -> group  (with deliberate flaws)
    demo/voiceprint/_groups_final.json  per-group stats used by the UI
    demo/seed_voices.json           a few already-named groups
    demo/people.json                fake name library (for the pinyin name box)

Audio is written as 32 kbps mono mp3 when ffmpeg is available (one minute of
demo ≈ 240 KB, so the repository stays small); without ffmpeg it falls back to
wav, which sync.py will transcode itself.

The deliberate flaws matter — they are what the merge and suggestion features
exist for, and they mirror a real pipeline's output:
  * P001 spans three recordings                      -> cross-recording identity
  * P005 / P008 / P010 / P012 are fragments of a
    named person in the same recording               -> over-segmentation
  * P009 and P011 have a single clip                 -> genuinely unresolvable
  * P004 carries two different raw diariser ids,
    while id 1 is shared by two groups               -> label hopping, both ways

Usage:  python tools/make_demo.py            # then: python tools/sync.py
"""
import array
import hashlib
import io
import json
import math
import os
import random
import shutil
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
DEMO = os.path.join(PROJ, "demo")
REC = os.path.join(DEMO, "recordings")
CONV = os.path.join(DEMO, "transcripts")
VP = os.path.join(DEMO, "voiceprint")

SR = 16000
BITRATE = "32k"

# ----------------------------------------------------------------- voices
# (f0 Hz, [(formant Hz, bandwidth Hz) x3]) — six clearly different timbres, so
# "is this the same voice?" is answerable by ear, which is the whole point.
VOICES = {
    "jia":  (110.0, [(620, 90), (1100, 120), (2500, 180)]),   # low male
    "yi":   (212.0, [(700, 100), (1320, 140), (2600, 200)]),  # high female
    "bing": (138.0, [(560, 85), (1000, 115), (2400, 175)]),   # mid male
    "ding": (182.0, [(660, 95), (1250, 130), (2550, 190)]),   # mid female
    "wu":   (150.0, [(590, 88), (1050, 118), (2350, 178)]),   # male, darker
    "ji":   (197.0, [(690, 98), (1290, 135), (2650, 195)]),   # female, brighter
}

# ----------------------------------------------------------------- script
# Completely invented content about an invented club. Keep it obviously fake.
# key = recording id used internally; only the date in the filename matters to
# sync.py, which turns it into the recording tag.
SCRIPT = {
    "0105": ("20260105_140000_虚拟读书会_筹备会", [
        ("P001", "先对一下今天的议程，就三件事。"),
        ("P001", "场地和预算先过，最后说报名表。"),
        ("P001", "尽量半小时结束，大家后面还有课。"),
        ("P001", "有问题随时打断我，不用等我讲完。"),
        ("P001", "另外说一句，这次材料费走公账。"),
        ("P001", "谁先垫了都留好发票，月底一起报。"),
        ("P002", "场地我问过了，周四下午空着。"),
        ("P002", "不过要提前一天去登记。"),
        ("P002", "登记表在我这里，回头我发群里。"),
        ("P002", "另外钥匙是当天去一楼拿。"),
        ("P002", "那边管理员四点半就下班了。"),
        ("P002", "所以别拖到太晚。"),
        ("P003", "预算我大概算了一下。"),
        ("P003", "印刷加物料，四百块左右。"),
        ("P003", "要是印两版就不够了。"),
        ("P003", "我建议先按一版做。"),
        ("P003", "后面真不够再补，补一次也不麻烦。"),
        ("P006", "那先按一版做，不够再补。"),
        ("P006", "我这边可以先垫，发票留好就行。"),
        ("P006", "市场那边我熟，买起来快。"),
        ("P009", "抱歉我刚到，前面说到哪了？"),
        ("P012", "垫钱的事你跟我说一声。"),
        ("P012", "对了，桌椅是不是要另外申请？"),
    ]),
    "0108": ("20260108_140000_虚拟读书会_第二次", [
        ("P001", "上周说的几件事，我们逐条对一下。"),
        ("P001", "先说报名表，改好了吗？"),
        ("P001", "看到了，格式没问题。"),
        ("P001", "联系方式那栏放在最后是对的。"),
        ("P001", "我们不对公开，低调一点。"),
        ("P002", "场地确认了，周四两点到四点。"),
        ("P002", "钥匙要当天去一楼拿。"),
        ("P002", "我那天下午有课，谁去拿一下？"),
        ("P002", "拿了以后直接去活动室就行。"),
        ("P004", "宣传的图我出了两版。"),
        ("P004", "一版简洁，一版热闹。"),
        ("P004", "先上简洁那版吧，热闹的备用。"),
        ("P004", "字我核过两遍，没有错别字。"),
        ("P004", "尺寸是按张贴栏做的。"),
        ("P007", "摆点的物资我列了个清单。"),
        ("P007", "周二去买来得及。"),
        ("P007", "顺便看看有没有便宜的文件夹。"),
        ("P005", "清单给我看一眼。"),
        ("P005", "笔和胶带多买一点。"),
        ("P005", "上次就是不够用。"),
    ]),
    "0112": ("20260112_140000_虚拟读书会_宣传组碰头", [
        ("P004", "海报尺寸定了吗？"),
        ("P004", "定了就先送去印。"),
        ("P004", "印之前记得再校一遍字。"),
        ("P004", "这次别用太大的字号，挤得慌。"),
        ("P004", "印完拿回来我先贴一张看看。"),
        ("P006", "预算那边钱到了。"),
        ("P006", "这周可以开始买物资。"),
        ("P006", "我周四去一趟市场。"),
        ("P006", "顺便把上次欠的两卷胶带补上。"),
        ("P006", "清单我带着，不会漏。"),
        ("P007", "线上那边我也发了。"),
        ("P007", "目前报名二十来个人。"),
        ("P007", "比上次好一些。"),
        ("P008", "链接再发一次吧。"),
        ("P008", "上次那条被刷下去了。"),
        ("P011", "海报贴在东边那面墙了。"),
    ]),
    "0119": ("20260119_140000_虚拟读书会_收尾对账", [
        ("P001", "今天把账对完就结束。"),
        ("P001", "先说花了多少。"),
        ("P001", "剩下的钱退回去还是留到下次？"),
        ("P001", "我倾向于留一点当备用金。"),
        ("P001", "毕竟下学期还要用。"),
        ("P002", "一共花了三百六十七。"),
        ("P002", "留一百块当备用金吧。"),
        ("P002", "明细我整理成一张表了。"),
        ("P002", "表里连发票号都写了。"),
        ("P002", "要查哪一笔都能对上。"),
        ("P002", "以后就按这个格式记。"),
        ("P003", "表我看了，没问题。"),
        ("P003", "下次这种小额我先记着。"),
        ("P003", "免得最后对不上。"),
        ("P003", "垫的钱我下周找财务报。"),
        ("P003", "报完我发个截图在群里。"),
        ("P010", "发票我夹在文件夹里了。"),
        ("P010", "回头一起归档。"),
    ]),
}

# Which voice each group actually is. Fragments share their parent's voice —
# that is exactly why a human can merge them and the machine could not.
VOICE_OF = {
    "P001": "jia",  "P012": "jia",
    "P002": "yi",   "P005": "yi",
    "P003": "bing", "P010": "bing",
    "P004": "ding", "P008": "ding",
    "P006": "wu",   "P011": "wu",
    "P007": "ji",   "P009": "ji",
}

# What the raw diariser reported per (recording, group). Deliberately not
# one-to-one: id 1 covers two groups, id 6 is a second id for one person.
MOSS_ID = {
    ("0105", "P001"): "1", ("0105", "P002"): "2", ("0105", "P003"): "3",
    ("0105", "P006"): "5", ("0105", "P009"): "2", ("0105", "P012"): "1",
    ("0108", "P001"): "1", ("0108", "P002"): "2", ("0108", "P004"): "4",
    ("0108", "P007"): "4", ("0108", "P005"): "2",
    ("0112", "P004"): "6", ("0112", "P006"): "5", ("0112", "P007"): "4",
    ("0112", "P008"): "6", ("0112", "P011"): "5",
    ("0119", "P001"): "1", ("0119", "P002"): "2", ("0119", "P003"): "3",
    ("0119", "P010"): "3",
}

# Groups the demo already has names for, so the voiceprint library is not empty
# on the first run and the suggestion feature shows something.
SEED = {"P001": "演示甲", "P002": "演示乙", "P003": "演示丙",
        "P004": "演示丁", "P006": "演示戊"}

PEOPLE = [
    ("演示甲", ["组长", "主持"]),
    ("演示乙", ["场地", "记录"]),
    ("演示丙", ["预算", "对账"]),
    ("演示丁", ["宣传", "设计"]),
    ("演示戊", ["物资", "采购"]),
    ("演示己", ["线上", "报名"]),
    ("演示庚", ["摄影", "海报"]),
    ("演示辛", ["顾问", "学长"]),
]


# ----------------------------------------------------------------- text -> srt
def syllables(text):
    """Split into per-character units; punctuation adds a pause."""
    PAUSE = set("，。？！、：；")
    return [(ch, ch in PAUSE) for ch in text]


def plan(lines, start=0.0, per_char=0.155, gap=0.34, pause=0.22):
    """Return [(group, text, t0, t1)] laid out on a timeline."""
    out, t = [], start
    for grp, text in lines:
        dur = sum((pause if p else per_char) for _, p in syllables(text))
        out.append((grp, text, round(t, 2), round(t + dur, 2)))
        t += dur + gap
    return out


# ----------------------------------------------------------------- synthesis
class Reson:
    """Two-pole resonator (Klatt-style, unit DC gain)."""

    def __init__(self, f, bw, sr=SR):
        r = math.exp(-math.pi * bw / sr)
        self.a1 = 2.0 * r * math.cos(2.0 * math.pi * f / sr)
        self.a2 = -r * r
        self.g = 1.0 - self.a1 - self.a2
        self.y1 = self.y2 = 0.0

    def __call__(self, x):
        y = self.g * x + self.a1 * self.y1 + self.a2 * self.y2
        self.y2, self.y1 = self.y1, y
        return y


def render_line(text, voice, rng):
    """Synthesise one utterance -> list of floats."""
    f0, forms = VOICES[voice]
    r1 = Reson(*forms[0])
    r2 = Reson(*forms[1])
    r3 = Reson(*forms[2])
    sig = []
    phase = 0.0
    f0wob = 0.0
    for ch, is_pause in syllables(text):
        dur = 0.22 if is_pause else 0.155
        n = int(dur * SR)
        if is_pause:                       # silence at punctuation
            sig.extend([0.0] * n)
            continue
        # per-syllable slight pitch contour makes it sound less robotic
        f0wob += rng.uniform(-1.5, 1.5)
        f0wob = max(-12.0, min(12.0, f0wob))
        p = SR / (f0 + f0wob)
        # crude voiced/unvoiced split: leading 20% noisy (consonant-ish)
        nz = int(n * 0.18)
        atk = int(n * 0.12)
        rel = int(n * 0.28)
        for i in range(n):
            if i < nz:
                exc = rng.uniform(-1.0, 1.0) * 0.5
            else:
                exc = 1.0 if phase < 1.0 else 0.0
                phase += 1.0
                if phase >= p:
                    phase -= p
            v = r3(r2(r1(exc)))
            if i < atk:                    # ADSR-ish envelope
                env = i / atk
            elif i > n - rel:
                env = max(0.0, (n - i) / rel)
            else:
                env = 1.0
            sig.append(v * env * 0.42)
        phase = 0.0
    return sig


def write_wav(path, samples):
    a = array.array("h", (int(max(-1.0, min(1.0, s)) * 32000) for s in samples))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(a.tobytes())


def encode(src_wav, dst_mp3):
    """wav -> 32 kbps mono mp3. Returns True on success."""
    if not shutil.which("ffmpeg"):
        return False
    try:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", src_wav, "-ac", "1", "-ar", str(SR),
                        "-b:a", BITRATE, "-map_metadata", "-1",
                        "-fflags", "+bitexact", dst_mp3],
                       check=True)
        return True
    except Exception:
        return False


def tstr(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def load_sync_tags():
    """Reuse sync.py's own tag rule so demo tags match what the pipeline expects.

    Instead of inventing identifiers we write the demo recordings first, then ask
    sync.py to name them — whatever it would call them is what we use.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("vw_sync", os.path.join(HERE, "sync.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return {it["stem"]: it["tag"] for it in m.build_tags()}


def main():
    for d in (REC, CONV, VP):
        os.makedirs(d, exist_ok=True)
    rng = random.Random(20260105)          # deterministic

    # mp3 is the committed form; fall back to wav when ffmpeg is absent
    use_mp3 = bool(shutil.which("ffmpeg"))
    ext = ".mp3" if use_mp3 else ".wav"

    # Touch placeholders first so sync.py can assign tags; the real audio lands
    # in a second pass, under exactly those names.
    stems = [(v[0], k) for k, v in SCRIPT.items()]      # v[0] is already the stem
    for stem, _ in stems:
        open(os.path.join(REC, stem + ext), "wb").close()
    TAGS = load_sync_tags()
    print("  sync 认出的 tag：%s" % TAGS)
    print("  音频格式：%s%s" % (ext, "" if use_mp3 else "  （没有 ffmpeg，回退 wav）"))

    meta = []          # embedding meta rows
    seg_group = {}     # "tag|start" -> group
    tmp_wavs = []

    for stem, key in stems:
        tag = TAGS[stem]
        lines = SCRIPT[key][1]
        rows = plan(lines)
        total = rows[-1][3] + 0.6
        print("  合成 %s（%.0f 秒，%d 句，%d 组）…"
              % (tag, total, len(lines), len({g for g, _ in lines})))
        track = [0.0] * int(total * SR)
        srt = []
        for i, (grp, text, t0, t1) in enumerate(rows, 1):
            utt = render_line(text, VOICE_OF[grp], rng)
            off = int(t0 * SR)
            for k, v in enumerate(utt):
                if off + k < len(track):
                    track[off + k] += v
            moss = MOSS_ID[(key, grp)]
            seg_group["%s|%.2f" % (tag, t0)] = grp
            srt.append((i, t0, t1, moss, text))
            meta.append({"tag": tag, "start": round(t0, 2), "end": round(t1, 2),
                         "moss": moss, "text": text, "g": grp})

        if use_mp3:
            tmp = os.path.join(REC, ".tmp_" + stem + ".wav")
            write_wav(tmp, track)
            tmp_wavs.append(tmp)
            if not encode(tmp, os.path.join(REC, stem + ".mp3")):
                print("  ! 转码失败，保留 wav：%s" % stem)
                os.replace(tmp, os.path.join(REC, stem + ".wav"))
        else:
            write_wav(os.path.join(REC, stem + ".wav"), track)

        with io.open(os.path.join(CONV, stem + ".moss.srt"), "w", encoding="utf-8") as f:
            for i, t0, t1, moss, text in srt:
                f.write("%d\n%s --> %s\n(Speaker %s) %s\n\n"
                        % (i, tstr(t0), tstr(t1), moss, text))

    for t in tmp_wavs:                      # the wav was only an intermediate
        if os.path.exists(t):
            os.remove(t)

    # ---------------- embeddings: prototype + noise, per group ------------
    try:
        import numpy as np
    except ImportError:
        print("！没有 numpy —— 跳过 _embs_all.npz（工作台仍可用，只是没有“建议名”）")
        np = None

    if np is not None:
        DIM = 192
        protos = {}
        # Groups that are the SAME person must share a prototype: derive it from
        # the voice, not from the group, so fragments really do look alike.
        for g in sorted({m["g"] for m in meta}):
            seed = int(hashlib.md5(VOICE_OF[g].encode()).hexdigest()[:8], 16)
            r = np.random.RandomState(seed)
            v = r.randn(DIM).astype(np.float32)
            protos[g] = v / np.linalg.norm(v)
        # NB: the perturbation must be normalised first. A raw randn is ~1.0 per
        # dimension while a unit prototype is only ~1/sqrt(D) ~= 0.072 per
        # dimension, so an un-normalised "0.22" noise would swamp the signal.
        common = np.random.RandomState(7).randn(DIM).astype(np.float32)
        common /= np.linalg.norm(common)          # shared channel/room effect
        emb = np.zeros((len(meta), DIM), dtype=np.float32)
        for i, m in enumerate(meta):
            nz = np.random.RandomState(1000 + i).randn(DIM).astype(np.float32)
            nz /= (np.linalg.norm(nz) + 1e-9)
            v = protos[m["g"]] + nz * 0.35 + common * 0.45
            emb[i] = v / (np.linalg.norm(v) + 1e-9)
        np.savez_compressed(os.path.join(VP, "_embs_all.npz"),
                            emb=emb, meta=np.array([json.dumps(m, ensure_ascii=False)
                                                    for m in meta]))
        print("  合成声纹 %d 段 × %d 维" % emb.shape)

    # ---------------- _final_map.json ------------------------------------
    with io.open(os.path.join(VP, "_final_map.json"), "w", encoding="utf-8") as f:
        json.dump(seg_group, f, ensure_ascii=False, indent=1)

    # ---------------- _groups_final.json (stats mirroring the real pipeline)
    groups = {}
    for g in sorted({m["g"] for m in meta}):
        rows = [i for i, m in enumerate(meta) if m["g"] == g]
        by_tag = {}
        for i in rows:
            by_tag.setdefault(meta[i]["tag"], []).append(i)
        dur = sum(meta[i]["end"] - meta[i]["start"] for i in rows)
        stats = {"时长min": round(dur / 60, 2), "段数": len(rows),
                 "出现录音": sorted(by_tag),
                 "各录音段数": {k: len(v) for k, v in by_tag.items()}}
        if np is not None and len(rows) > 1:
            sub = emb[rows]
            s = sub @ sub.T
            n = len(rows)
            within, cross = [], []
            for a in range(n):
                for b in range(a + 1, n):
                    v = float(s[a, b])
                    if meta[rows[a]]["tag"] == meta[rows[b]]["tag"]:
                        within.append(v)
                    else:
                        cross.append(v)
            allv = within + cross
            stats["组内一致性"] = round(sum(allv) / len(allv), 3)
            stats["同录音一致性"] = round(sum(within) / len(within), 3) if within else None
            stats["跨录音一致性"] = round(sum(cross) / len(cross), 3) if cross else None
        else:
            stats["组内一致性"] = None
            stats["同录音一致性"] = None
            stats["跨录音一致性"] = None
        samples = []
        for i in rows[:10]:
            m = meta[i]
            mm, ss = divmod(int(m["start"]), 60)
            samples.append({"tag": m["tag"], "t": "%02d:%02d" % (mm, ss),
                            "start": m["start"], "end": m["end"],
                            "moss": int(m["moss"]), "text": m["text"]})
        stats["样本"] = samples
        groups[g] = stats
    with io.open(os.path.join(VP, "_groups_final.json"), "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=1)

    # A seed annotation, so the suggestion feature is visible on the first run:
    # the four fragments should come back as "演示乙 / 演示丁 / 演示丙 / 演示甲".
    with io.open(os.path.join(DEMO, "seed_voices.json"), "w", encoding="utf-8") as f:
        json.dump({"voices": SEED, "overrides": {}, "dunno": {}, "alias": {}},
                  f, ensure_ascii=False, indent=1)

    # Fake name library — makes the name box (fuzzy + pinyin) demonstrable.
    with io.open(os.path.join(DEMO, "people.json"), "w", encoding="utf-8") as f:
        json.dump({"people": [{"n": n, "t": t + ["演示人物"], "pri": 90}
                              for n, t in PEOPLE]},
                  f, ensure_ascii=False, indent=1)

    n_groups = len({m["g"] for m in meta})
    print("\n✅ demo 数据已生成：")
    print("   %d 份录音 / %d 句 / %d 组 / 6 个说话人" % (len(stems), len(meta), n_groups))
    print("   %s  (音频，%.1f MB)" % (REC, sum(
        os.path.getsize(os.path.join(REC, f)) for f in os.listdir(REC)) / 1e6))
    print("   %s  (转写稿)" % CONV)
    print("   %s  (声纹产物)" % VP)
    print("\n下一步：  python tools/sync.py    然后    python tools/serve.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
