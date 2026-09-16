# M0 Governance Bootstrap Procedure

## Objective

Establish the durable project control plane before substantive feature development.

## Procedure

1. Verify GitHub repository and active branch.
2. Inspect existing governance and architecture documents.
3. Do not overwrite established project rules without reconciliation.
4. Establish project state, requirements, architecture and roadmap records.
5. Establish AI agent rules and procedures.
6. Establish testing and checkpoint standards.
7. Establish Developer Governance UI requirements.
8. Validate that all documents agree on terminology and subsystem boundaries.
9. Commit the governance checkpoint.
10. Verify the remote commit.
11. Record the checkpoint in `.ai/HANDOFF.md`.

## M0 Acceptance Criteria

- Governance control plane exists.
- AI agent operating rules exist.
- Generic project kickoff standard exists.
- Web interception boundary is explicitly documented.
- Developer control-plane requirements are documented.
- Roadmap and milestone model are defined.
- Git rollback/recovery policy is defined.
- Bug/defect model is defined.
- Handover procedure is defined.
- No provider API integration has been introduced as a shortcut.

## Failure Handling

If any acceptance criterion cannot be verified, mark M0 `BLOCKED` and record the exact reason. Do not claim completion.
