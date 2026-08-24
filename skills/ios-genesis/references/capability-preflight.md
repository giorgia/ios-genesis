# Capability Preflight

The single authority for **detecting optional MCP integrations** and reporting what this run can and cannot do. Runs once, at the start of every run, before the Step 0 interview. `design-mode.md` and `interactive-verification.md` consume its result rather than each detecting for themselves.

## Why detection is by basename, never by prefix

An MCP tool's full identifier is `mcp__<server>__<tool>`, where `<server>` is **whatever name the user gave the server in their MCP config**. It is not stable, not guessable, and not the same across machines — a Figma server can register as `mcp__claude_ai_Figma__*`, `mcp__Figma__*`, or a UUID like `mcp__5ded3e79-9af2-4225-9696-e472a03ac8f1__*`.

Detection therefore matches on the **tool basename** — the segment after the final `__` — and never on the prefix. Two releases were silently degraded by getting this wrong (v0.5.0 matched a literal `describe_ui` that XcodeBuildMCP had renamed to `snapshot_ui`; the Figma check matched a literal `mcp__claude_ai_Figma__` prefix that does not match a UUID registration), so this rule is not a style preference.

## What it checks

| Capability | Present when the session exposes | Consumed by |
|---|---|---|
| `figma` | a tool with basename `use_figma` **and** one with basename `get_screenshot` | `design-mode.md` (whether to offer the Figma option) |
| `ui_read` | a tool with basename `snapshot_ui`, or `describe_ui` on older XcodeBuildMCP releases | `interactive-verification.md` (passed to verifiers as `ui_read_tool`) |
| `ui_act` | a tool with basename `tap` | `interactive-verification.md` |

`interactive: true` requires **both** `ui_read` and `ui_act`. XcodeBuildMCP ships UI automation as a separate `ui-automation` workflow that is off by default, so a session commonly exposes the simulator tools and even `snapshot_ui` while `tap` is absent.

Record the **full matched tool name** for each capability, not just the basename — the verifier is dispatched with `ui_read_tool` set to the name that actually exists, and calls exactly that.

## The grant gap

Detection and *access* are two different things, and only detection is prefix-independent.

Subagent `tools:` frontmatter supports server-level wildcards (`mcp__<server>__*`) but has no way to express "any MCP server, whatever it is called" — `mcp__*` is valid only in `disallowedTools`. So `ios-ui-designer` and `ios-visual-verifier` grant a fixed set of plausible server names, and a server registered under an unexpected name is **detected but not reachable** by the agent that needs it.

The preflight must therefore compare detection against the grants and report that gap explicitly. Granted patterns:

- `ios-ui-designer`: `mcp__claude_ai_Figma__*`, `mcp__Figma__*`, `mcp__figma__*`
- `ios-visual-verifier`: the Figma patterns above, plus `mcp__XcodeBuildMCP__*`, `mcp__xcodebuildmcp__*`

## Output — report it at run start, not at the phase that needs it

Print a short capability block before the Step 0 interview. The point is that a missing integration is visible **while the user is still at the keyboard deciding what to build**, not four phases later when the design or verification phase quietly degrades.

```
Capabilities for this run
  ✔ XcodeBuildMCP   snapshot_ui + tap detected — interactive flow verification ON
  ⚠ Figma           connected as mcp__5ded3e79-…__use_figma
                    Detected, but no agent grant matches that server name, so the
                    UI Designer cannot reach it. Either rename the server to
                    `Figma` in your MCP config, or add the prefix to the
                    `tools:` line of agents/ios-ui-designer.md. The Figma design
                    mode is unavailable until then.
  — Figma           not connected — Figma design mode unavailable
```

Three states per capability, and each gets a distinct line:

- **Detected and granted** (`✔`) — usable; the consuming doc proceeds normally.
- **Detected but not granted** (`⚠`) — the failure this preflight exists to catch. Name the actual registered prefix and both fixes. Treat the capability as unavailable for the run, and append an `open_risks` entry so it also surfaces at every checkpoint.
- **Not detected** (`—`) — genuinely absent. One line, no risk entry; this is the normal, supported degrade path (`design-mode.md` omits the Figma option; `interactive-verification.md` sets `interactive: false`).

Persist the result to `state.json` as `capabilities` so a resumed run reports the same thing, and re-run the preflight on resume — the user's MCP config may have changed between sessions, which is exactly when a run silently changes behavior today.

## What the preflight never does

- It never installs, configures, or enables anything. It reports and tells the user the fix. (See the substitution prohibition in `interactive-verification.md`.)
- It never fails a run. Every capability here is optional; absence degrades a phase, never blocks one.
