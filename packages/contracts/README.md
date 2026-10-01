# caf-contracts
Pure interface contracts (C0-C6) using Pydantic models. Zero external I/O.

`caf_contracts.models` and top-level exports remain the current compatible contracts.
Import `caf_contracts.future_v1` explicitly for the `shared-study.v1` C0/C2/C4/C5/C6
drafts: official hierarchy/source context, complete questions and answers, revision-bound
student review, target/version-scoped scores, and ownership/published responses.
They have no endpoint or ORM bindings and do not authenticate or authorize requests.
Verification counts are read-only computed output fields; `model_dump(round_trip=True)`
omits them when serializing model input.
