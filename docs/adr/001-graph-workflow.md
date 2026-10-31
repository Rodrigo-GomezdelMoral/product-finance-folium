# ADR-001 · A graph workflow per invoice, paused for review through checkpoints

**Status:** accepted · **Date:** 2026-10-31

## Context

Every invoice goes through the same steps: Document Intelligence reads it, Prompt Shields screens its text, a model fills
what the reading left empty, the REQ-04 rules and the REQ-05 duplicate checks run, and a person reviews it. The review
can come minutes or days later, from another replica, after a deployment. If Prompt Shields finds an attack, the model must
not see the document at all.

## Options

1. **Plain async functions** called in order by the queue consumer, with the review state kept by hand in Cosmos DB. No
   framework, but the pause, the resume, the replay after a crash and the routing on the shield result are all our code.
2. **The functional workflow API** (`@workflow`, `@step`). Plain Python control flow and `ctx.request_info` too, but it is
   experimental, and it resumes a review by re-executing the function from the top with cached `@step` results: any code
   outside a step runs again, and the routing on the shield result is an `if` inside a function, not a declared edge.
3. **An orchestration** (sequential, handoff). Built for conversations between agents; here there is one agent and five
   functions.
4. **A graph workflow** (`WorkflowBuilder`): one executor per step, a conditional edge on the shield result, and
   `ctx.request_info` for the review, with checkpoints at every superstep.

## Decision

Option 4, built in `app/workflow.py`:

- Executors `extract`, `shield`, `normalize`, `validate`, `dedupe` and `review`. Only `normalize` calls a model
  ([ADR-002](002-one-agent-where-a-function-cannot.md)), from inside a function executor rather than as an `AgentExecutor`
  (guide 3.7): the cross-check and the fallback on a model failure belong to the same step, and an `AgentExecutor` would add a
  superstep and carry the conversation, with the document text, in every later checkpoint.
- Two conditional edges leave `shield`: to `normalize` when no attack is found, straight to `validate` when one is, with a
  `possible_injection` finding.
- `review` asks with `ctx.request_info(ReviewRequest, ReviewDecision)`. Its `@response_handler` records each correction
  (field, before, after, who, when), re-runs the REQ-04 rules on the corrected data, and then approves, rejects or sends the
  invoice to the lead again. A clerk's approval of an invoice with an open finding, and a rejection without the lead and a
  reason, become a new request for the lead: the workflow never approves what the rules block.
- **One workflow instance per invoice,** built by `build(invoice_id, services)` and named `invoice-<id>`, as guide 3.6 asks.
  The name is the partition of its checkpoints (`/workflow_name` in Cosmos DB).
- **Resume** (`resume`) lists the invoice's checkpoints, keeps those at the highest `iteration_count`, and loads the one whose
  pending requests contain the request id. Since 1.13.0 a checkpoint is written when responses are delivered too, at the
  same iteration as the pause, so the iteration count alone cannot pick it and the timestamp alone cannot either. A request
  that is no longer pending at the top, because it was answered or replaced, returns nothing: an approval happens once.
- **The request id is untrusted.** The lookup is scoped to the invoice's own checkpoints, so a request id from another
  invoice finds nothing. Phase 4 authorises the caller against the invoice before calling `resume`.
- **Checkpoint types are allow-listed** (`CHECKPOINT_TYPES`), because file and Cosmos DB storages restore with a restricted
  unpickler. The document text travels between executors only until `dedupe`, so the pause checkpoint does not carry it.

## Consequences

- A crash between the review request and the answer loses nothing: a test kills the process that ran the workflow, a fresh
  workflow resumes from the checkpoint and approves exactly once, and a second answer to the same request is refused.
- The graph's topology is fixed, so checkpoints written by one deployment restore in the next. The ablation of phase 3 runs
  the same graph with the normaliser switched off, not a different graph.
- A run writes the entry checkpoint and one per superstep: seven when an invoice reaches review, nine once it is approved,
  two of them at iteration 6 (the pause and the delivered answer). Phase 7 measures their request units in Cosmos DB
  serverless.
