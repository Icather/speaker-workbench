<!-- Thanks for the PR. Three things that make it quick to review: -->

## What this changes

<!-- one paragraph -->

## Why

<!-- link an issue if there is one -->

## Checks

- [ ] `npm test` passes (both suites)
- [ ] no absolute paths introduced — everything goes through `_path()`
- [ ] **tests stay data-agnostic**: no literal counts or hard-coded recording IDs
      (derive from the data, like the `A1 / N1 / G1 / P0` anchors in `tools/test_dom.js`)
- [ ] if I changed a threshold or a measurement, the number and how it was
      obtained are in the diff (comments in `tools/sync.py` / `docs/METHOD.md`)
- [ ] if I changed the UI, I checked it in a real browser, not only in jsdom

## Notes for the reviewer

<!-- anything surprising, or anything you deliberately did NOT do -->
