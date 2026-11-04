# App Review — Notes for <version>

`asc_sync.py` sends the block between the two `---` lines to App Review Information → Notes. **4,000 characters at most** (`asc_sync.py check` counts it). Everything outside the block is for humans.

> Attach the screen recording (App Review Information → Attachment) before submitting, if the notes say one is attached.

---
Hello, and thank you for reviewing <App>.

1. How to try it
<the shortest path to the core feature; a demo account if sign-in is needed (credentials go in App Store Connect's sign-in fields, never here)>

2. Hardware or permissions
<what needs a physical device or an accessory, and what the app does without it>

3. Devices tested
<the exact devices and OS versions this build was tested on; must match what was actually run>

4. New in this version
<features App Review might question, and why they comply: extensions, unusual APIs, third-party content, on-device models>
---

Checks before syncing:
- Every claim matches the shipping build (no feature behind a DEBUG flag, no unreleased flow).
- The device line matches the recorded test run.
- No other platform's logo or UI is described as part of the app.
