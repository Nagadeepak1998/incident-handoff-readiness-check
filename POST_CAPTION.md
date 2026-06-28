Built a small incident handoff checker today.

The idea is simple: before an incident moves to another owner or shift, make sure the handoff includes the timeline, impact, current owner, next action, mitigation, evidence links, customer comms state, and rollback or follow-up notes.

I kept it dependency-free and added safe/risky fixtures plus unit tests so the behavior is easy to run and explain.
