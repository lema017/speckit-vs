# Slice by Slice Bundle

A bundle of this fork that installs the workflow that builds the slices of a slice map one after another.

## What it provides

- **Sliced workflow** (`workflows/sliced`) — a resumable loop over the slices of a map. Each round:
  1. `next-slice` asks the project which slice comes now.
  2. `approve-slice` gate — approve to build that slice, reject to stop.
  3. `specify` writes the spec of the slice.
  4. `review-spec` gate — shows the size of the slice against its budget. Approve to go on, reject to stop.
  5. `plan`, `tasks` and `implement`.

  The loop ends when every slice of the map is delivered. If a slice was started and is not delivered, the ones that depend on it wait: the `wait-for-delivery` gate says which, and asks again once you finish it.

  **A slice over its budget.** The walk measures the slice after `specify` and after `tasks`. Over the budget, a gate shows the numbers and asks:

  - **Approve** plans or builds the slice as it is. The walk records in `slice-budget.json`, next to the spec, that its size was accepted at that gate.
  - **Reject** stops the walk. Split the slice with `/speckit.capabilities.size`, or accept it there with a reason in your own words, and finish that slice by hand.

  After `specify` this gate stands in for `review-spec`. After `tasks` it is one more gate, and only when the tasks went over.

## It needs

- The `capabilities` extension, 0.7.0 or later. `specify init` installs it by default.
- A slice map under `specs/_slices/`. `/speckit.specify` writes one when a request holds several slices, and `/speckit.capabilities.slice` writes one on its own.

## Install

```bash
specify bundle add sliced
```

## Run the workflow

```bash
specify workflow run sliced --input map=login
```

`map` is the name of the map under `specs/_slices/`. Leave it out when only one map has a slice to build.

The gates ask in the terminal. Without a terminal the run pauses at each gate, and `specify workflow resume <run id>` goes on from there.

See the [capabilities guide](../../docs/how-to/capabilities.md#one-spec-one-slice) for what a slice is.
