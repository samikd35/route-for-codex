# Route v1 for Codex Desktop and CLI

Status: ready-for-agent

Spec review: Approved for ticketing.

## Problem statement

A developer has an OpenAI API key that can run the GPT model they want. They need a local relay to use that credential with Codex Desktop and CLI. They want to enter the key once and keep using Codex to read files, edit code, run tests, and generate images. They also want control over which model receives their code and when the relay is active.

## Solution

Install Route on the developer’s computer. **Connect** in the setup window and `route connect` in the terminal use the same connection. The only required input is the developer’s API key. After Route verifies a tool call through the selected GPT model, the developer can activate Route for both clients.

Codex sends Responses API requests to a local Caddy relay. Route authenticates to OpenAI, then streams the model’s events back to Codex. Codex runs local tools under the developer’s existing permissions. File excerpts and tool results included in a request reach OpenAI. [Architecture diagram](../../architecture.svg)

## User stories

1. As a desktop developer, I want to connect from a setup window so that I can use Route when I launch Codex normally.
2. As a CLI developer, I want to connect from the terminal so that I can use the same relay and credential across both clients.
3. As a first-time user, I want a working default model and effort so that I only need to enter my key.
4. As a developer with an existing model preference, I want to keep my selection and switch models or effort in Codex so that I control how my task runs.
5. As a developer with a project-scoped key, I want the picker to list my eligible models and their reasoning efforts so that I can choose one my project can use.
6. As a developer enabling Route, I want setup to verify a complete tool call so that I can choose when to trust it with new Codex sessions.
7. As a developer working in a project, I want Codex to read, edit, run tests, and use the results in a follow-up so that I can finish a coding task in one conversation.
8. As a developer building a page, I want Codex to generate an illustration and place it in the page so that I can see the finished result.
9. As a developer rotating credentials, I want the replacement key to apply immediately so that I know which credential is being used, including when it fails.
10. As a developer disconnecting Route, I want my previous settings restored and my later edits preserved so that I can keep working in Codex.
11. As a returning developer, I want to reconnect with my saved key or explicitly forget it so that I control what stays on the device.
12. As a developer without secure storage, I want a session-only connection so that I can use Route without persisting a secret.
13. As a developer logging in, I want Route to respect my last connection state and wait for a locked credential store so that startup does not interrupt me.
14. As a developer stopping a task or losing a connection, I want the interruption to reach the other side so that an unwanted request does not keep running through Route or get replayed by the relay.
15. As a developer installing Route, I want to see which platforms have passed the Desktop, CLI, and performance checks so that I can choose a verified release for my OS.

## Implementation decisions

### Model selection and request handling

- Use the fixed OpenAI Responses endpoint. GPT‑6 is the minimum generation for the model picker, including Luna, Terra, Sol, and Astra. A later release becomes eligible when the developer’s key lists its actual model ID and the Codex catalog identifies it as compatible with Responses streaming and tool calls. Each entry exposes its own supported reasoning efforts. [OpenAI model catalog](https://developers.openai.com/api/docs/models)
- During setup and key replacement, use the current key with `GET /v1/models`. Match the returned IDs to capability metadata for the installed Codex version and supply the matching entries to Desktop and CLI. If discovery fails, surface the error. If the intersection is empty, explain that this key has no discoverable compatible GPT‑6-or-later model. Discovery requires no inference probes. [OpenAI model discovery](https://developers.openai.com/api/reference/resources/models/methods/list) · [Codex gateway catalogs](https://learn.chatgpt.com/docs/enterprise/roll-out-a-gateway#implement-the-catalog-endpoint)
- Preserve an existing eligible model and supported effort. For a first session without an eligible selection, default to `gpt-6.2-sol` at `medium` if available. Otherwise ask the developer to pick from the eligible list. Run the connection test only for the selection. Inference continues through Caddy to `https://api.openai.com/v1/responses`.
- Bundle Caddy as a per-user service bound to loopback. Register one shared Codex provider. A credential helper supplies either client with a local token, including Desktop launched outside a terminal. Only the relay uses the upstream key to authenticate requests to OpenAI.
- Preserve the model request body, streamed events, tool-call IDs and matching results, conversation continuation, and upstream error status. Surface model-access errors and let the developer choose another model. Distinguish a stopped relay, rejected key, rate limit, and interrupted stream. Keep credentials out of configuration files and logs. Omit request bodies and tool output from diagnostics by default.
- If the upstream stream breaks mid-response, report the interruption to Codex. Any retry originates with Codex or the developer. When the developer presses **Stop**, immediately close the corresponding upstream request.

### Setup and credentials

| Action | Required behavior |
| --- | --- |
| Connect and test | Test only the selected model. The first request asks it to call a setup tool that generates a fresh random value in memory. The second sends that value back under the matching call ID. Pass when the completed stream contains the exact value in the final answer. The check uses two API requests and requires no shell command or project file. |
| Activate | After the test passes, offer **Use Route by default**. Selecting it makes Route the provider for new local sessions in Desktop and CLI. Preserve the previous settings. |
| Store the key | Bind the saved key to the preset upstream in the local OS credential store. If secure storage is unavailable, offer session-only use and hold the key in memory for that connection. |
| Replace the key | Use the replacement immediately for every new upstream request, including the connection test and tool results. An existing stream can finish under the old key. If the replacement fails, show the error and keep it selected. |
| Disconnect | Stop the relay and invalidate its local token. For each setting Route changed, restore its previous value only if its current value still matches what Route wrote. Restore absence when the setting was previously absent. Preserve later developer edits. Discard a session-only key. With a saved key, show “Disconnected. Your API key is saved on this device.” and offer **Reconnect** and **Forget API key**. |
| Reconnect | Use the saved key and generate a fresh local token. Run the full connection check on initial setup, key change, or explicit **Test connection**. Reconnecting with the same saved key skips the check. Surface access changes on the next real request. |
| Log in after restart | Automatically reconnect only if the developer left Route connected with a saved key. An explicit disconnect persists. Session-only use requires entering the key again. If the credential store is locked, show **Waiting for unlock** quietly. Offer the OS unlock prompt on next use if needed, then reconnect. |
| Forget API key | Disconnect an active relay and delete Route’s saved copy from this device. The upstream key remains valid at OpenAI. |

## Testing decisions

Test the installed product by sending real Codex requests through bundled Caddy and observing the client, upstream, and workspace. A deterministic local streaming provider makes call IDs, credential changes, interruption timing, and latency repeatable. The live OpenAI endpoint establishes actual model and tool compatibility.

| Release check | Passing evidence |
| --- | --- |
| Local authentication and tool loop | Reject an invalid local token before the test provider receives a request. In a real Codex session, read a random value from a fixture, edit the fixture, run a test, and answer a follow-up using the earlier tool result. Verify the call ID round trip. |
| Setup and recovery | Exercise Desktop from its normal launcher and CLI from a fresh terminal. Verify the two-request setup check, explicit activation, key rotation during an open stream, and a rejected replacement. Verify settings restoration, rejection of the old token after reconnect, session-only use, locked-store login, and local deletion after Forget. |
| Cancellation and interruption | From each client, press **Stop** while the test provider is streaming and observe the upstream disconnect before generation finishes. Separately, drop the upstream stream after a tool call reaches Codex. Codex detects the interruption and Route sends no replay request. |
| Model discovery | In both clients, check the picker with keys or fixtures exposing different model subsets and effort levels. Cover Luna, Terra, Sol, Astra, unavailable IDs, pre‑GPT‑6 IDs, a key without the default Sol model, and an empty eligible list. An access error on inference leaves the selected model in place. |
| Live models and coding | GPT‑6.2 Sol and GPT‑6.2 Astra are the v1 end-to-end reference models. For each, use the live relay to read and edit a fixture, run its test to a passing result, answer a follow-up, and pass the live image check in Desktop and CLI. Other eligible models can be selected and tested individually during setup. |
| Live image generation | In a fresh workspace for each client, generate an illustration through Route and use it in a page. Verify that the generated file exists and the rendered page displays that image. Both clients must pass. |
| Relay latency | From the same client, send matched pairs of identical requests to the same deterministic local provider, one directly and one through Route. Time each from sending until receipt of the first complete streamed event. For each pair, subtract the direct time from the relayed time. The 95th percentile of those differences must be **at most 50 ms**. Also compare total duration on matched direct and relayed live requests. |

macOS, Windows, and Linux qualify independently. Publish readiness per OS. A platform can ship when Desktop and CLI pass its v1 checks, including the live image task, and its relay meets the latency target.

## Out of scope

User-configured endpoints, models older than GPT‑6, models that cannot drive a Codex tool session, Ollama, local inference, automatic model routing, inference protocol translation, and a Route-operated cloud service are outside v1.

## Further notes

The earlier real-CLI check verified one shell-tool round trip with a test relay and simulated upstream. Qualification of bundled Caddy, the live endpoint, image generation, latency, and each OS remains pending. This spec is the input for ticketing after product approval. [Architecture decisions and existing evidence](../../ARCHITECTURE.md)
