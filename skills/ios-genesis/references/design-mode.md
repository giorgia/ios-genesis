# Design Mode

There are two paths to setting `design_mode`, because the modes split on *when the designs exist*:

- **Bring-your-own designs already exist at the start.** Whether the user has existing designs is knowable during the step-0 interview, so it's captured there (see `orchestration-flow.md`'s "Step 0" - "Detect existing designs"). When the user has them, the orchestrator sets `design_mode: "bring_your_own"` and records `design_sources` at initialization, and the Architect reviews those designs in phase 1 before deciding the architecture.
- **Create-fresh designs (text / Figma / Claude Design) don't exist yet.** They'd be produced by the UI Designer in phase 2, so there's nothing for the Architect to look at, and the choice among them depends on `screens_affected`, which the Architect only determines in phase 1. This choice is therefore deferred to the Architect's checkpoint.

The rest of this doc covers the deferred (create-fresh) question. If `design_mode` was already set to `"bring_your_own"` in step 0, skip the question entirely and go straight to dispatching the UI Designer.

## When to ask (create-fresh modes)

Once the user selects "Continue to the next phase" at the Architect's checkpoint (see `checkpoints.md`):

- If `screens_affected: true` and `design_mode` is not yet set in `state.json`, ask a follow-up `AskUserQuestion` (before dispatching the UI Designer) for how the user wants UI design handled.
- If `design_mode` is already set (i.e. `"bring_your_own"` from step 0), do not ask - proceed straight to the UI Designer dispatch.
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
- **Bring your own designs**: the user already has designs (Sketch files, screenshots, an existing Figma file, an exported spec, etc.). This is normally captured in the step-0 interview (see above), in which case this question isn't reached at all; it remains here as a fallback for a user who surfaces existing designs only at the Architect checkpoint. If chosen, follow up by asking the user for the relevant file paths/URLs and record them as `design_sources` (a list of strings) in `state.json`. Records `design_mode: "bring_your_own"`. Note that when captured here rather than at step 0, the Architect has already run without seeing the designs - offer the user "Make changes first" to re-run the Architect with the designs if the architecture should account for them.

If the user doesn't express a preference, default to `design_mode: "text"`.

## Dispatching the UI Designer

Pass `design_mode` (and `design_sources` if `bring_your_own`) to the UI Designer in its dispatch prompt - see `agents/ios-ui-designer.md` for how each mode affects its output.

## Fan-out in multi-task graphs

In multi-task graphs, the design mode applies per task. The ui_designer phase dispatches one agent per projected task (`ui_impact: true`); each agent returns its design section, which the orchestrator assembles into `docs/design.md`. Per design mode:

- `figma`: each task's mockup is its own Figma file; the link is stored in that task's `results.design_reference` (superseding the single `design_mode_extra` link flow, which remains in effect for single-task graphs).
- `claude_design`: per-task paste summaries, concatenated by the orchestrator into one user handoff at the checkpoint.
- `bring_your_own`: after `design_mode` resolves to `bring_your_own` on a multi-task graph, the **orchestrator** maps each entry in `design_sources` to a task (matching by screen/feature name; on ambiguity, ask the user via `AskUserQuestion`) and writes each task's `results.design_reference` before dispatching the ui_designer wave. The Architect performs this mapping only when `design_sources` is already present in its dispatch (resumed runs where `design_mode` was set in a previous session).

Each verifier receives its task's `design_reference` (or `"none"` for modes that don't populate one).

Only `figma` links and `bring_your_own` source mappings (written to `results.design_reference` by the orchestrator before the ui_designer wave, or by the Architect on resume-with-design_sources) are persisted to `results.design_reference`; a designer report of `"none"` never overwrites an existing value. `claude_design` summaries are checkpoint-transient — concatenated into the user handoff at the checkpoint — and are not persisted to state.

## At the UI Designer's checkpoint

- **text / bring_your_own**: standard checkpoint (summary + Risks/Blockers + Continue/Make changes/Stop). For `bring_your_own`, the summary additionally notes which screens came from `design_sources` vs. were filled in by the UI Designer, per the per-screen provenance annotations in `docs/design.md` (`design_mode_extra` will be `"none"` for this mode).
- **figma**: standard checkpoint, plus the summary includes the Figma file link from the UI Designer's report (`design_mode_extra`).
- **claude_design**: standard checkpoint, plus the orchestrator additionally presents the copy-pasteable screen/flow summary from the UI Designer's report (`design_mode_extra`) along with instructions for the user to paste it into Claude Design (claude.ai) to generate visual mockups and iterate there. No automation or artifact capture happens on the orchestrator's side. "Continue" means the user is satisfied with `docs/design.md` as the spec the Developer will code against, whether or not they used Claude Design.
