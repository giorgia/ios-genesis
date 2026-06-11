# Design Mode

`screens_affected` is determined by the Architect (phase 1), so the orchestrator can't ask about design mode during its own interview (phase 0).

## When to ask

Once the user selects "Continue to the next phase" at the Architect's checkpoint (see `checkpoints.md`):

- If `screens_affected: true` and `design_mode` is not yet set in `state.json`, ask a follow-up `AskUserQuestion` (before dispatching the UI Designer) for how the user wants UI design handled.
- If `screens_affected: false`, skip this question entirely - `design_mode` stays unset, and the UI Designer phase is skipped (go straight to `developer`).
- This applies the same way to both `new_app` and `feature_addition`, even though new apps will almost always report `screens_affected: true`.
- If the user picks "Make changes first" or "Stop here" at the Architect checkpoint, defer this question until a later "Continue" is selected.

## Before offering Figma

Check whether the Figma MCP server is available (e.g. whether `mcp__claude_ai_Figma__*` tools are present in this session). If not, omit the "Figma" option from the question below (text-only and Claude Design remain available).

## The question

Ask via `AskUserQuestion`, with these options (recommend "Text-only"):

- **Text-only (default/recommended)**: the UI Designer writes `docs/design.md` only (screen list, navigation, SwiftUI view hierarchy/component breakdown). Records `design_mode: "text"`.
- **Figma** (omit if unavailable, see above): in addition to `docs/design.md`, the UI Designer generates mockups in Figma. Records `design_mode: "figma"`.
- **Claude Design (manual)**: the UI Designer writes `docs/design.md` as in text-only. Records `design_mode: "claude_design"`.
- **Bring your own designs**: the user already has designs (Sketch files, screenshots, an existing Figma file, an exported spec, etc.). If chosen, follow up by asking the user for the relevant file paths/URLs and record them as `design_sources` (a list of strings) in `state.json`. Records `design_mode: "bring_your_own"`.

If the user doesn't express a preference, default to `design_mode: "text"`.

## Dispatching the UI Designer

Pass `design_mode` (and `design_sources` if `bring_your_own`) to the UI Designer in its dispatch prompt - see `agents/ios-ui-designer.md` for how each mode affects its output.

## At the UI Designer's checkpoint

- **text / bring_your_own**: standard checkpoint (summary + Risks/Blockers + Continue/Make changes/Stop). For `bring_your_own`, the summary additionally notes which screens came from `design_sources` vs. were filled in by the UI Designer (per its report's `design_mode_extra` / provenance notes in `docs/design.md`).
- **figma**: standard checkpoint, plus the summary includes the Figma file link from the UI Designer's report (`design_mode_extra`).
- **claude_design**: standard checkpoint, plus the orchestrator additionally presents the copy-pasteable screen/flow summary from the UI Designer's report (`design_mode_extra`) along with instructions for the user to paste it into Claude Design (claude.ai) to generate visual mockups and iterate there. No automation or artifact capture happens on the orchestrator's side. "Continue" means the user is satisfied with `docs/design.md` as the spec the Developer will code against, whether or not they used Claude Design.
