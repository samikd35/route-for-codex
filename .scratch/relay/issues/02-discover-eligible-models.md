# 02. Show the current key’s eligible models and efforts in Codex

Status: ready-for-agent

Blocked by: None.

Spec: [Route v1 for Codex Desktop and CLI](../spec.md)

A developer sees the GPT‑6-or-later models their project can use in Desktop and CLI. This slice can be exercised independently by pointing both clients at a test catalog and using fixture discovery responses.

## Acceptance criteria

- [ ] List models with the current key and intersect the actual returned IDs with the installed client version’s catalog of Responses streaming and tool-call capabilities. Discovery sends no inference requests.
- [ ] With fixtures covering Luna, Terra, Sol, and Astra, verify that each picker offers just the eligible IDs and each model’s supported efforts. Include a newer compatible release, a pre‑GPT‑6 entry, an incompatible model, and a model absent from the key’s list.
- [ ] Preserve an existing eligible choice and supported effort. With no eligible selection, default to GPT‑6.2 Sol at medium if available. Otherwise present the eligible list for an explicit choice.
- [ ] Distinguish a failed discovery request from successful discovery with no eligible models. With two different keys, verify the catalog shown belongs to the current key.

## Comments

`route/models.py` intersects key discovery with the installed CLI catalog; selection and subsets are covered by `tests/test_setup.py`. Both real client pickers still require inspection, including compatibility when Desktop and CLI versions differ.
