---
name: Bug report
about: Something does not work as documented
labels: bug
---

<!--
  IMPORTANT: do not attach real recordings, real transcripts or real voiceprint
  vectors. Describe the shape of your data instead — that is almost always
  enough to reproduce a bug.
-->

**What happened**

**What you expected**

**How to reproduce**

1.
2.

**Which part**

- [ ] the workbench page (index.html)
- [ ] the data pipeline (`tools/sync.py`)
- [ ] suggestion / voiceprint library
- [ ] export or import (RTTM etc.)
- [ ] the test suite
- [ ] the documentation

**Environment**

- OS:
- Python version (`python --version`):
- Node version, if the test suite is involved (`node --version`):
- ffmpeg available? (`ffmpeg -version`):

**Output of `python tools/inspect_embs.py`**

```
paste here — it is designed to be safe to share
```

**Shape of your data** (do not paste content)

- number of recordings:
- clips per recording (roughly):
- speakers per recording (roughly):
- single-clip duration, typical:
- far-field (phone across a room) or close-mic?
- language:
- did you use the bundled demo, or your own corpus?

**Browser console output** (UI issues only)

```
paste here
```
