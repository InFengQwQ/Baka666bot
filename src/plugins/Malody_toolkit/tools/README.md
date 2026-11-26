# Runtime tools

Only source scripts are tracked here (`inverse.py`, `tojack.py`).

The binary tools used by the Malody conversion and replay commands are
downloaded by `scripts/fetch-assets.py` and ignored by git:

- `ManiaReplayMaster.jar` — replay renderer (Java, Apache-2.0), from the
  `replay-renderer-2.4.0` release
- `ma2om.exe`, `ncm2mp3.exe`, `prontom.exe` — Windows conversion tools,
  from the `assets-2026.11.26` release; the Linux image runs them through
  wine
- `mp32ogg.exe`, `ncm2ogg.exe`, `DragUnzip.exe` — no longer used or
  downloaded; the same work is done by ffmpeg and by Python's `zipfile`

The manifest in `scripts/` pins the source, size and SHA-256 for each
downloaded file. `tool_path()` resolves this directory, or
`BAKA_TOOLS_DIR` when it is set.
