# SEC-bench Agent Notes

This file defines repository-specific guidance for agents working on SEC-bench, with extra attention to formal verification and symbolic execution workflows.

## Scope

- Treat SEC-bench as a Docker-first benchmark. The code that an evaluated agent interacts with lives in the evaluation container, not in the host-side `projects/` cache.
- Use this document when adding support for advanced analysis tools such as KLEE, Frama-C, or other heavyweight program analysis frameworks.

## Core Rules

- If the functionality you want to implement already has a fully equivalent implementation in the current SEC-bench codebase, reuse that implementation instead of duplicating it.
- Every newly added function must include an English docstring.
- Keep changes minimal and localized. Do not introduce a parallel pipeline when the existing preprocessing, image-building, or evaluation pipeline can be extended directly.

## Execution Model

- SEC-bench instances are executed inside evaluation Docker images.
- Host-side repository clones under `projects/` are preprocessing artifacts and are not the primary runtime environment for evaluated agents.
- Preserve the existing container contract:
  - `WORKDIR` must continue to point to the instance repository work directory.
  - `/testcase` is the standard location for patches, PoCs, and auxiliary files.
  - `/usr/local/bin/secb` is the standard helper entrypoint for `build`, `repro`, and `patch`.

## Preferred Extension Points

- For heavy tools such as KLEE and Frama-C, prefer extending the evaluation image build process instead of installing packages at agent runtime.
- Reuse and extend the existing image-building flow before adding new build scripts:
  - `secb/evaluator/templates/Dockerfile.eval.base.j2`
  - `secb/evaluator/templates/Dockerfile.eval.instance.j2`
  - `secb/evaluator/build_eval_instances.py`
- Keep compatibility with the existing image naming convention: `<image_prefix>.<instance_id>:patch` and `<image_prefix>.<instance_id>:poc`.
- If you need a custom toolchain, prefer building a derived evaluation base image and then rebuilding instance images on top of it.

## Formal Verification And Symbolic Execution Guidance

- Do not assume KLEE, Frama-C, SMT solvers, or LLVM toolchains are available in the official verified images unless the code explicitly installs them.
- Pin versions for heavyweight analysis tools and document toolchain assumptions clearly, especially for:
  - LLVM/Clang compatibility
  - Solver dependencies
  - OCaml/opam dependencies
  - Architecture-specific requirements
- Prefer deterministic installation steps in Dockerfiles over ad hoc bootstrap logic in runtime scripts.
- Keep analysis wrappers thin. Generic orchestration logic should live in reusable helpers instead of being copied into instance-specific code.

## Reuse Before Reinventing

- Before adding a helper, search for an existing equivalent in the repository and reuse it if the behavior is the same.
- Prefer extending current mechanisms over creating alternatives. Examples:
  - Extend the current Docker template flow instead of creating a second image-generation path.
  - Reuse existing evaluation result handling instead of inventing a new output schema.
  - Reuse existing helper-script conventions instead of adding a different container control entrypoint.

## Output And Observability

- Keep existing SEC-bench result contracts stable unless a change is explicitly required.
- When adding debug or tracing output for advanced analysis tools, write it to the existing artifact/output flow rather than introducing hidden state.
- Avoid silent behavior changes. If a verification or symbolic execution step alters benchmark assumptions, make that explicit in code and documentation.

## Validation Expectations

- Validate image changes on a single instance before scaling to many instances.
- After modifying the image or helper logic, confirm the standard SEC-bench workflow still behaves correctly:
  - image build succeeds
  - `secb build` still works
  - `secb repro` still works for PoC-oriented flows
  - `secb patch` still works for patch-oriented flows
- Do not break the existing preprocessing or evaluation pipeline while adding advanced analysis tooling.

## Python Implementation Notes

- Every new Python function must have an English docstring.
- New docstrings should describe purpose, inputs, outputs, and any important side effects when they are not obvious.
- Prefer small reusable helpers over large monolithic functions, but do not split code unnecessarily when a single existing helper already matches the required behavior.
