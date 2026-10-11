# HARDWARE_GATES.md — remaining unknowns and the cheapest experiment for each

For each open question: what evidence would resolve it, and the **cheapest** experiment —
ordered so the *first* dollar spent attacks the *fundamental physical* question, not normal
SSD operation.

| # | Unknown | Evidence that resolves it | Cheapest experiment | Cost |
|---|---|---|---|---|
| G1 | Can the *specific* NAND do **read-level shift** (shifted-Vref sensing) via Set Feature? | The NAND datasheet's read-retry / feature-address table **for the exact Micron part on the board**. | **Read the datasheet** (free, under NDA/Micron). No hardware. | $0 |
| G2 | Does shifted-Vref sensing yield usable analog-ish multi-level info (MCFlash-style)? | On a board you own: program known patterns, sweep read-level via `EFh` Set Feature (already in `setFT` SM), observe how the returned bits change vs. shift. | One Cosmos+ (or any board exposing Set-Feature read-retry), ~dozens of reads. **No new silicon.** | board only |
| G3 | Does the die support **multi-wordline sensing** (operand AND/OR on one bitline)? | Characterization: drive 2+ WLs active in one sense. **Not possible via any standard command** → needs a modified read SM *and* the die to tolerate it. | Add an experimental read state machine in RTL that asserts a non-standard WL-bias sequence, on a sacrificial board; compare output to the AND/OR of two programmed pages. **High effort, may brick, may simply not work.** | board + RTL weeks |
| G4 | Latch-level Boolean (XOR/XNOR/count) inside die | A vendor/test-mode command set for the part (almost never public) | Only resolvable with NDA vendor docs or a NAND test chip. No external-command experiment exists. | NDA / N/A |
| G5 | Analog current-sum / sense-amp / ADC tap | Die-internal node routed off-chip | **Requires a custom NAND test chip / de-lidded probing** — not a commodity-part experiment. | prohibitive |
| G6 | Aggregate NAND **read bandwidth** actually achievable | Measure sustained multi-channel/multi-plane read GB/s on the board | Run the stock FTL's read path, time a large sequential read. Confirms the §2 bandwidth wall directly. | board only |

## Reading of the gate structure

- **G1–G2 and G6 are cheap and decisive**, and they attack the only physically-reachable
  lever (shifted-Vref sensing) and the dominant wall (bandwidth). A datasheet + one board
  answers "is there *any* analog-ish compute signal to exploit, and is bandwidth as bad as
  predicted?" without silicon risk.
- **G3 is the true make-or-break for the Flash-Cosmos dream** and it is expensive, risky, and
  likely negative on a commodity part — and even success only yields *binary* ops, still short
  of MXFP4 and still sense-bandwidth-bound (K3_FEASIBILITY §2–§3).
- **G4–G5 are not resolvable by external commands at all** — they are silicon/NDA gates. No
  amount of OpenSSD firmware/RTL work reaches them.

## What would change the recommendation

The feasibility verdict flips only if **all** of: (a) G1 shows rich per-step read-level
control, (b) G2 shows reliable multi-level analog extraction on the exact part, (c) a
bit-plane MXFP4 scheme closes to within a usable factor of the latency budget, **and** (d) the
capacity + bandwidth walls (which are independent of any in-NAND trick) are somehow sidestepped
(e.g., a radically different, much smaller target model). On the stated K3 workload, (d) alone
already fails by 3–4 orders of magnitude.
