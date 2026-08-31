# K3-on-NAND Feasibility Study

## Permanent mission
Determine, rigorously in software, whether a Kimi K3 inference accelerator built on
commodity 3D NAND can achieve a structural >10x advantage in inference economics
(joules/token or tokens/$) by keeping weights inside NAND and computing weight-heavy
dot products before weights leave the die. Two candidates: (A) stock NAND + firmware
(minimum internal primitive search), (B) NAND + tiny per-plane compute unit
(LLM-on-the-Palm style, re-derived for K3's MXFP4/MXFP8). This is falsification-driven
research: do NOT optimize for making the idea look good.

## Permanent rules
- Never invent NAND specs, commands, energy numbers, latencies. Every number needs
  source/reason or is a marked sensitivity variable.
- Label every claim FACT (sourced/measured) / MODEL (derived) / HYPOTHESIS (needs real-NAND test).
- FEMU never "proves" a capability exists in real NAND.
- Do not download full K3 weights. Do not rewrite existing simulators from scratch.
- Commit after every gate. Work autonomously; document blockers and continue elsewhere.
- Units explicit everywhere (ns/us/bytes/W/J).
- Branch: `claude/k3-nand-inference-arch-2fspi1` (push with `git push -u origin <branch>`).

## Session-resume protocol
1. Read this file + RUN_STATE.md. 2. `git status` + recent log. 3. Verify current gate.
4. Continue from "Next Actions" in RUN_STATE.md — never restart the project.

@RUN_STATE.md
