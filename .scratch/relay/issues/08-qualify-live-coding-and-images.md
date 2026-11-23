# 08. Verify live coding and image generation in both clients

Status: ready-for-agent

Blocked by: [03](03-connect-and-activate.md)

Spec: [Route v1 for Codex Desktop and CLI](../spec.md)

Prove that an installed Route connection supports real coding and image generation through the fixed OpenAI endpoint. Produce a repeatable check and its first live results for subsequent OS qualification.

## Acceptance criteria

- [ ] Run the same tasks in all four combinations of GPT‑6.2 Sol and Astra with Codex Desktop and CLI. Confirm the intended model and selected supported effort travel through Route.
- [ ] For each combination, start with a fresh coding fixture, have Codex read and edit it, run the failing test to a pass, and answer a follow-up using the tool result. Inspect the diff and verify the test independently.
- [ ] For each combination, use a fresh workspace, generate an illustration through Route, and use it on a page. Verify the generated image exists and the rendered page actually displays it.
- [ ] Record OS, Route and client versions, model, effort, and pass/fail evidence with a test fixture. Report unavailable access or upstream errors explicitly. Missing live evidence leaves that combination unqualified.

## Comments

`python -m tests.live` prepares and verifies fresh fixtures per model/client combination. Follow-up and browser-render evidence are required in addition to file checks.

2026-11-23 · Signed-out macOS CLI Sol and Astra generated and rendered the red-kite page using the Route MCP tool. Normal-launch Desktop and cross-platform checks are pending. [Qualification record](../../../docs/api-key-only-images.md)
