# ADR-012 · Agents and the workflow in code, self-hosted in Container Apps

**Status:** accepted · **Date:** 2026-10-31

## Context

Folium has one workflow and two agents, the `Normalizer` inside the workflow and the read-only `Assistant`. The workflow
reads originals from Blob Storage, is driven by a Service Bus consumer, keeps its checkpoints and the invoices in Cosmos DB, and
pauses for people who sign in with Entra ID and hold app roles. Microsoft Foundry can also define prompt agents and workflows
in the portal, or run hosted agents.

## Options

1. **Agents and workflows defined in Foundry** (portal or prompt agents). Versioned outside the repository, out of reach of the
   evaluation gate on pull requests, and with the review state in a service we do not query.
2. **Foundry Hosted Agents.** Microsoft runs the container and its sessions. The workflow would still need our queue, our
   storage and our authorisation, from another runtime.
3. **Agent Framework in code, self-hosted** (guide 8.1): the app owns routes, identity, authorisation and storage.

## Decision

Option 3. The agents and the workflow are Python in `app/`, with their prompts in `app/prompts/`, and run inside the Container
App that serves the API. Foundry provides the model deployment `gpt-5-mini` with its guardrail, Document Intelligence and
Prompt Shields, called with Entra ID through `FoundryChatClient` and the Azure SDKs. Nothing is created in Foundry.

`agent-framework-hosting` is not added. Its `AgentState` and `WorkflowState` map protocol ids to sessions and checkpoints; Folium
exposes no agent protocol, and the one mapping it needs, from an invoice and a request id to the pending checkpoint, is the
three-line rule of [ADR-001](001-graph-workflow.md), which must also authorise the caller first.

## Consequences

- A prompt or workflow change is a pull request that the evaluation gate checks against the baseline (phase 3).
- The same image runs the API, the queue consumer and the agents; scaling, identity and network are the Container App's.
- Moving to Foundry Hosted Agents later would only change where the container runs, not the code.
