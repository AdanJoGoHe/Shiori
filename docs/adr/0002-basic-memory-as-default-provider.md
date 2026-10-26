# ADR-0002: Use Basic Memory behind a replaceable retrieval adapter

- Status: Proposed
- Date: 2026-10-11
- Related: docs/specification.md

## Context
Three agents need reusable memory while personal and employer data remain isolated and readable independently of an AI product.

## Decision
Use Basic Memory behind a replaceable retrieval adapter.

## Alternatives considered
A host-specific opaque memory store would couple portability and privacy to one product.

## Consequences
Readable local state and explicit boundaries require integration tests, schema maintenance and honest capability reporting.

## Validation / reconsideration trigger
Revisit if real-host tests show the selected provider or lifecycle cannot satisfy the relevant acceptance criteria. Approval status stays Proposed until explicitly accepted.
