---
name: prevent-patchwork-technical-debt
description: Prevent patchwork technical debt by evaluating fixes against system invariants, ownership boundaries, state and contract authority, failure semantics, and removal cost. Use when designing or reviewing bug fixes, hotfixes, retries, fallbacks, guards, compatibility shims, duplicate validation, shadow state, incident mitigations, or any solution that works but may be accumulating special cases instead of removing the root cause.
---

# Prevent Patchwork Technical Debt

Define **patchwork technical debt** as a fix that makes the observed symptom disappear by adding downstream conditions, retries, duplicated state, compatibility behavior, or exception paths without restoring the violated invariant at its source.

Aim for a durable fix: restore the invariant in the component that owns it, keep one source of truth, make failure explicit, and minimize new states and branches.

## Establish the invariant

Before editing code:

1. State the behavior that must always hold, independent of the reported example.
2. Reconstruct the causal chain from input to failure.
3. Identify the earliest transition where actual behavior violates the invariant.
4. Name the component that owns that transition, state, or contract.
5. Separate the root cause from downstream symptoms and missing diagnostics.

Do not choose a solution from the final error message alone.

## Apply the patchwork test

Treat a proposed fix as patchwork when one or more answers are yes without a boundary-based justification:

- Would the new guard, retry, or fallback be unnecessary if the owning invariant held?
- Does the fix create a second source of truth or require two representations to stay synchronized manually?
- Does it add a special case for one caller, runtime, identifier, error string, or execution order?
- Does it retry an unchanged deterministic operation?
- Does it catch a broad failure and convert it into success, empty data, a default value, or another backend?
- Does it duplicate validation or business rules outside the component that owns them?
- Does it preserve an invalid intermediate state and teach more consumers to tolerate it?
- Does it obscure lost work by measuring only the items that reached a later stage?
- Does the compatibility path lack an owner, observability, a removal condition, or a bounded lifetime?
- Would removing the workaround later require another migration because callers have begun depending on it?

Redesign the fix when these questions reveal avoidable coupling or permanent exceptional behavior.

## Design the durable fix

Prefer changes that:

- make the invariant executable through types, schemas, transactions, state machines, ownership APIs, or validation at the authoritative boundary;
- eliminate invalid states instead of detecting them repeatedly downstream;
- establish one canonical contract or state representation and derive adapters from it;
- make writes atomic or idempotent where interruption and repetition are expected;
- preserve causal error information and require explicit terminal outcomes;
- classify transient and deterministic failures before applying bounded retry;
- keep adapters thin and avoid runtime-specific semantics;
- remove obsolete branches and compatibility behavior made unnecessary by the repair;
- reduce or hold constant the number of concepts, states, and synchronization points.

Do not force all validation into one layer. Keep input-shape validation at system boundaries and domain invariants in the domain owner; avoid copying the same rule into every caller.

## Handle emergency mitigation

Allow a compensating workaround only when immediate containment is necessary and the root fix cannot safely ship in the same change. Require all of the following:

- a narrow and explicit scope;
- observable activation and failure metrics;
- bounded retries, duration, or affected population;
- reversibility without data loss;
- regression coverage for both the mitigation and the underlying failure;
- a named owner and durable follow-up direction;
- a concrete removal condition, not “remove later.”

Describe the mitigation as containment, not as root-cause completion.

## Verify the solution

Verify at three levels:

1. **Reproduction:** Prove the original failure before the change and its absence after the change.
2. **Invariant:** Test the general rule at the owning layer, including boundary, partial-state, interruption, repetition, and concurrency cases as relevant.
3. **Architecture:** Confirm that the change does not introduce duplicate truth, hidden fallback, unbounded retry, silent data loss, or a new permanent lifecycle branch.

Prefer a smaller invariant-focused test matrix over many example-specific tests. Keep one regression for the incident and broader tests for the underlying rule.

## Review the debt delta

Before declaring completion, compare before and after:

- number of states and terminal outcomes;
- number of sources of truth;
- number of conditional branches and retry paths;
- number of components containing the same rule;
- amount of runtime-specific or caller-specific behavior;
- observability of failure and recovery;
- cost of deleting compatibility code.

Reject a fix that resolves the example while increasing these costs without a necessary architectural reason.

## Report the decision

State:

- the invariant and its owning layer;
- the root cause and evidence;
- whether the change is a durable fix or temporary containment;
- special states, branches, retries, or compatibility paths added and why they are necessary;
- tests that prove the invariant;
- remaining debt, owner, and removal condition.
