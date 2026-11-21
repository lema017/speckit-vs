---
description: "Stop hook of the agent: send it back once when work is about to end outside the catalog"
scripts:
  py: scripts/python/capabilities.py stop-check
---

# Capability Stop Check

Not a command for the agent. The agent's `Stop` hook runs the script of this file by itself, with no model, each time the agent is about to end its turn.

It sends the agent back, with one paragraph, when the branch holds work outside the catalog:

- a spec or a record with no open task whose delta was not folded;
- product code that no change of the catalog records.

A spec still being built is left alone: its flow ends in the fold. `stop_check` in `capabilities-config.yml` chooses `warn` (once, and not again while nothing changes), `block` (at every stop) or `off`. Whatever goes wrong, the session ends as it would without it.
