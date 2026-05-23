# Decisions Log

Append-only log of non-trivial decisions. Each entry: `D-NNNN: Decided X because Y (YYYY-MM-DD).`

- **D-0001:** Decided to keep per-screen inline `CSS = """..."""` blocks instead of an external `CSS_PATH` `.tcss` file because the 7 blocks have no duplication and `textual run --dev` live-edit is unused (2026-05-22).
- **D-0002:** Decided to keep `call_from_thread` via `S3Screen.ui()` for worker→UI updates instead of `post_message` because Constitution §Architecture principle 4 already mandates it (2026-05-22).
