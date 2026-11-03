<!-- manual-md 1 | source: content/manuals/slides-aid.json | sha256: adddef477d5e3539 -->
<!-- Edit the prose freely: headings, paragraphs, list items, table cells, entry values, and the text inside the JSON of a comment line (captions, notes). Keep the front matter, every comment line and the {#id} at the end of each heading: md_to_json uses them to rebuild the JSON. A new paragraph under a heading needs nothing extra; a new list, table or other block starts with a type comment line copied from a block of the same type. A new heading needs its own {#id} (lower case, digits, hyphens). Inline markup is the manual's own: [[term]] glossary, [@#anchor] cross-reference, $`tex`$ maths, **bold**. The Contents list, the section numbers in the headings and the <a id> line above each heading are generated: md_to_json refreshes them, edits there are ignored. -->

---
$schema: "../../schema/manual.schema.json"
id: "slides-aid"
title: "Slides Aid"
subtitle: "Reading the PyPSA model csvs: the six efforts behind its parity with PLEXOS"
description: "Companion to slide 6 of the PyPSA vs PLEXOS deck. For each of the six efforts: what PLEXOS does that PyPSA can't, how the PyPSA model works around it, and where that shows in the model csvs, with examples from the Center node."
version: "1.0"
status: "final"
updated: "2026-11-03"
authors: []
applies_to: ["PLEXOS", "PyPSA"]
publish: true
order: 30
changelog: [{"version": "1.0", "date": "2026-11-03", "changes": ["First version: the six parity efforts, each with its issue, its solution and examples from the 20 October 2026 model csvs."]}]
---

<!-- toc -->
**Contents**

- [1 Model size: milestone years and myopic blocks](#model-size)
  - [1.1 The issue](#model-size-issue)
  - [1.2 The solution](#model-size-solution)
  - [1.3 In the model csvs](#model-size-csvs)
- [2 Vintages and persistence across blocks](#vintages-persistence)
  - [2.1 The issue](#vintages-persistence-issue)
  - [2.2 The solution](#vintages-persistence-solution)
  - [2.3 In the model csvs](#vintages-persistence-csvs)
- [3 Sampled chronology with peak and energy rescaling](#sampled-chronology)
  - [3.1 The issue](#sampled-chronology-issue)
  - [3.2 The solution](#sampled-chronology-solution)
  - [3.3 In the model csvs](#sampled-chronology-csvs)
- [4 Custom constraints written into the solver](#custom-constraints)
  - [4.1 The issue](#custom-constraints-issue)
  - [4.2 The solution](#custom-constraints-solution)
  - [4.3 SNSP limits](#custom-snsp)
  - [4.4 CSP with thermal storage](#custom-csp)
  - [4.5 Capacity-factor energy caps](#custom-energy-caps)
- [5 Corridor losses, token wheeling and cross-border markets](#losses-markets)
  - [5.1 Corridors: losses and wheeling](#losses-markets-corridors)
  - [5.2 Cross-border markets](#losses-markets-markets)
- [6 Economics and availability](#economics-availability)
  - [6.1 The issue](#economics-availability-issue)
  - [6.2 The solution](#economics-availability-solution)
  - [6.3 In the model csvs](#economics-availability-csvs)
- [Appendix A The model csvs at a glance](#csv-map)
<!-- /toc -->

<a id="model-size"></a>

# 1 Model size: milestone years and myopic blocks {#model-size}
<!-- section {"sources": ["MasterDocs/ModelLog.md §2.5, §6.6, §13, §14.2", "PypsaExpansion/Scripts/V0 model creator/config.csv", "PypsaExpansion/Scripts/RunModel/config.csv", "PypsaExpansion/PypsaModel/Model csvs/investment_periods.csv, snapshots.csv"]} -->

> PLEXOS optimises all 30 years of its horizon in one solve. The free HiGHS solver can't, so the PyPSA model uses eight milestone years, solved in three myopic blocks.

<a id="model-size-issue"></a>

## 1.1 The issue {#model-size-issue}

<!-- text {"_list": true} -->
The PLEXOS [[lt-plan]] treats every year from 2023 to 2052 as an investment step and optimises all 30 together, with perfect foresight, using the commercial Gurobi solver.

A PyPSA network that copied this would need 30 investment periods, and its size grows faster than the number of periods. Every period adds its own set of sampled hours. It also adds a new [[vintage]] of every candidate ([@#vintages-persistence]), which is dispatched in every later period too: with n periods there are up to n(n + 1)/2 vintage-period pairs, 36 for 8 periods but 465 for 30.

In October 2026 tests, HiGHS solved the whole horizon at 1 sampled day per month (about 3 million rows, in 34 minutes) but stalled from 2 days per month (about 6 million rows). The model now samples 3 days per month ([@#sampled-chronology]).

<a id="model-size-solution"></a>

## 1.2 The solution {#model-size-solution}

<!-- list {"ordered": true} -->
1. **Milestone years.** The investment periods are a list of years set by the user (`milestone_years` in the V0 model creator's `config.csv`). Each milestone stands for the years until the next one, at its own year's data; the last one runs to the end of the horizon. Eight are used, placed where the inputs change.
2. **Myopic blocks.** The periods are solved in three blocks, in order: 2023–2029, 2030–2035, and 2040 with 2050 (`planning_mode = myopic` and `myopic_block_end_years = 2029 2035 2050` in RunModel's `config.csv`). Each block is a separate, smaller solve, and what it builds is locked in for the next ([@#vintages-persistence]).
3. **Block ends placed outside temporary events.** A block can't see past its last year, so a block that ends inside a short event builds for that event alone: a 2023–2030 block built 777 MW of PES solar just to get through the 2029–2030 supply crunch, which perfect foresight never builds. Block ends are therefore kept off contract ends, demand steps and steep cost declines.

<!-- table {"id": "tab-milestones", "caption": "The eight milestone years."} -->
| Milestone | Stands for | Why this year | Block |
| --- | --- | --- | --- |
| 2023 | 2023–2026 | Start of the horizon; existing fleet only | 1 |
| 2027 | 2027–2028 | Build limits open; new lines can be built from July 2027 | 1 |
| 2029 | 2029 | Demand jump: Mozal returns | 1 |
| 2030 | 2030–2031 | Last year of the contracted export to South Africa | 2 |
| 2032 | 2032–2034 | Run-of-river planned minimums; DES dam hydro; `South-Center 2027-2032` line deadline | 2 |
| 2035 | 2035–2039 | Reporting year | 2 |
| 2040 | 2040–2049 | Reporting year; 2045 was dropped so that block 3 stays solvable | 3 |
| 2050 | 2050–2052 | Reporting year; runs to the end of the horizon | 3 |

<a id="model-size-csvs"></a>

## 1.3 In the model csvs {#model-size-csvs}

<!-- list -->
- **`investment_periods.csv`** has one row per milestone: `period`, its NPV weight `objective` ([@#economics-availability]) and `years`, the number of years it stands for (4, 2, 1, 2, 3, 5, 10 and 3: 30 in all).
- **`snapshots.csv`** has 6,912 rows: 8 periods × 864 hours (12 months × 3 sampled days × 24 hours). Its `period` and `timestep` columns index every time series in the other csvs.
- **Every component name ends in a milestone year**, one row per period: e.g. `HyDam_Center_2023` … `HyDam_Center_2050` ([@#vintages-persistence]).
- **The myopic blocks are not in the csvs.** The csvs always hold the whole horizon; the block ends are applied at solve time by `myopic.py`. The saved solution (`Compiled models/{Scenario}_Solution.nc`) is restored afterwards so that it reads like a single solve of all eight periods.

<!-- text -->
More: [@pypsa-architecture#model-size|PyPSA Model Architecture, Model size].

<a id="vintages-persistence"></a>

# 2 Vintages and persistence across blocks {#vintages-persistence}
<!-- section {"sources": ["PypsaExpansion/Scripts/V0 model creator/network_builder.py", "PypsaExpansion/Scripts/RunModel/myopic.py", "PypsaExpansion/PypsaModel/Model csvs/generators.csv, global_constraints.csv", "PypsaExpansion/PypsaModel/Compiled models/DES_Solution.nc"]} -->

> We need vintages to implement PLEXOS-style phased capacity build-out across the timeline at time-varying costs, overcoming PyPSA's single-decision-per-object rule. We need clamps to allow sequential myopic blocks to start from previous solves without erasing history or resetting resource ceilings.

<a id="vintages-persistence-issue"></a>

## 2.1 The issue {#vintages-persistence-issue}

<!-- text {"_list": true} -->
In PLEXOS, an expansion candidate such as `Xp_SolarPV_Center` (new solar PV at the Center node) is one single persistent Generator object. Its `Project Start Date` defines when expansion opens, and its `Max Units Built` timeline caps cumulative build. The solver can add units at different milestone years at that year's capital cost, and units built in 2050 only incur capital annuities starting in 2050.

PyPSA gives each component only **one scalar capacity decision variable (`p_nom`)** for its entire existence. In PyPSA, `build_year` is **not** an "available from" date; it is the **exact commissioning year**. An asset with `build_year = 2030` pays its annualized capital cost in every period it is active ($2030 \le p < 2030 + \text{lifetime}$). The solver cannot "wait" to build a 2030 asset in 2050: doing so in a multi-period solve would incur 20 years of wasted capital annuities (2030–2049) for an idle plant. One component cannot be built in increments across time at time-varying capital costs.

Myopic blocks ([@#model-size]) introduce a second, critical challenge: each block is a completely separate optimization run. PyPSA has no internal function to carry solved capacities (`p_nom_opt`) forward into subsequent solves. Without explicit state management, sequential solves face two fatal traps:
- **Trap 1 (Leaving past variables unclamped):** A subsequent block (e.g. 2040–2050) only evaluates snapshots in its own window, so its objective function only bills capital costs for 2040–2050. If past vintages (`_2030`) were left unclamped, the 2050 solver could build the 2030 vintage in 2050 to dodge 20 years of historical capital annuities (paying only the 2050 annuity slice!), or retroactively delete a 2030 gas plant to avoid 2050 fixed O&M.
- **Trap 2 (Setting past builds to non-extendable):** The standard tutorial approach sets `p_nom_extendable = False` and `p_nom = p_nom_opt`. However, PyPSA's cumulative expansion limits (`tech_capacity_expansion_limit`) and custom constraints (such as CSP site potential) **only sum extendable components**. Flipping past builds to fixed assets causes the resource ceiling to completely forget that capacity was ever built, resetting site headroom and allowing subsequent blocks to overbuild past the true resource potential!

<a id="vintages-persistence-solution"></a>

## 2.2 The solution {#vintages-persistence-solution}

<!-- list -->
- **One component per milestone year (vintage).** `Xp_SolarPV_Center` becomes `Xp_SolarPV_Center_2023` … `Xp_SolarPV_Center_2050` (eight rows in `generators.csv`). Each vintage carries its own `build_year`, the technology's 30-year `lifetime`, and the specific `capital_cost` of its commissioning year. A vintage is in service in period p when build_year ≤ p < build_year + lifetime.
- **Bound together across time.** A native [[global-constraint]] (`tech_capacity_expansion_limit`) per period caps the sum of all active vintages at PLEXOS's cumulative `PotentialCapacity` ceiling. Where PLEXOS specifies a planned minimum, a second constraint sets a commitment floor.
- **No clamping within a block (or in perfect foresight).** Perfect foresight is conceptually a single block spanning the entire 30-year horizon. Within any single block solve, all years are co-optimized simultaneously, so PyPSA's native equations keep active vintages online across that block's timeline without external intervention.
- **Inter-block clamping (`myopic.py`).** To link sequential myopic blocks without falling into either trap, `myopic.py` categorizes vintages before each block solve:
  - **Past vintages (`build_year < block_start`):** Clamped to their solved values (`p_nom_min = p_nom_max = p_nom_opt`) while **retaining `p_nom_extendable = True`**. This freezes historical decisions in stone (preventing retroactively dodging CAPEX or deleting past builds) while ensuring the cumulative expansion limit continues counting them against remaining site headroom.
  - **Future vintages (`build_year > block_end`):** Pinned to zero (`p_nom_min = p_nom_max = 0`) so future assets cannot be used before their commissioning window.
  - **Current block vintages:** Open to full optimization (`p_nom_min = 0`, `p_nom_max = Potential Ceiling`).
- **Existing plants follow the same pattern with fixed rows.** `SolarPV_Center_2023` … `SolarPV_Center_2040` each hold 40.5 MW, with `lifetime` equal to the years of their period (4, 2, 1, 2, 3, 5, and 10), so each row covers exactly one period. There is no 2050 row because the existing plant retires before then.

<!-- equation {"id": "eq-potcap", "caption": "Potential limit `PotCap_Xp_SolarPV_Center_{p}`, one per period p."} -->
```math
\sum_{v:\; b_v \le p < b_v + \ell_v} P^{\text{nom}}_{v} \;\le\; \text{Potential}_{p}
```

| Symbol | Meaning | Unit |
| --- | --- | --- |
| P^{\text{nom}}_{v} | Built capacity of vintage v (`p_nom`) | MW |
| b_v,\ \ell_v | Build year and lifetime of vintage v | year |
| \text{Potential}_{p} | PLEXOS cumulative potential in period p (`constant` in global_constraints.csv) | MW |

<a id="vintages-persistence-csvs"></a>

## 2.3 In the model csvs {#vintages-persistence-csvs}

<!-- table {"id": "tab-solar-vintages", "caption": "The eight rows of `Xp_SolarPV_Center` in generators.csv (PES), with what the DES solution built.", "notes": "Every row also has `p_nom_extendable` True, `p_nom` 0, `p_nom_max` 54,420.5 MW and `lifetime` 30. The built capacity is `p_nom_opt` in Compiled models/DES_Solution.nc."} -->
| Vintage | build_year | capital_cost ($/MW-yr) | Built in DES (MW) |
| --- | --- | --- | --- |
| Xp_SolarPV_Center_2023 | 2023 | 136,892 | 0 |
| Xp_SolarPV_Center_2027 | 2027 | 94,807 | 0 |
| Xp_SolarPV_Center_2029 | 2029 | 73,764 | 1,888 |
| Xp_SolarPV_Center_2030 | 2030 | 63,243 | 692 |
| Xp_SolarPV_Center_2032 | 2032 | 60,834 | 0 |
| Xp_SolarPV_Center_2035 | 2035 | 57,221 | 1,099 |
| Xp_SolarPV_Center_2040 | 2040 | 51,197 | 1,326 |
| Xp_SolarPV_Center_2050 | 2050 | 39,151 | 8,498 |

<!-- list -->
- **The per-row maximum is deliberately loose.** Every row's `p_nom_max` in `generators.csv` is the whole potential, 54,420.5 MW; the real limit is enforced on their cumulative active sum.
- **`global_constraints.csv` holds the sum limits**: `PotCap_Xp_SolarPV_Center_2023` … `_2050`, with `type` tech_capacity_expansion_limit, `bus` Center, `carrier_attribute` SolarPV and `sense` <=. Their `constant` is 54,420.5 MW from 2027 and 0 in 2023, which is how PLEXOS's "no new build before 2027" constraint reaches PyPSA.
- **Planned minimums are `_min` rows** with `sense` >=, e.g. `PotCap_Xp_NGCCG_South_2027_min` ≥ 450 MW.
- **`generators-p_max_pu.csv` has one column per vintage** (`Xp_SolarPV_Center_2030` and so on): the hourly solar profile × availability ([@#economics-availability]).
- **Persistence shows in the solution, not in the raw model csvs.** The 2029 vintage (1,888 MW) was decided in Block 1 and held clamped through Blocks 2 and 3. In 2050, all five built vintages are in service simultaneously: 13,503 MW total, well within the 54,420.5 MW potential.
- **Clean restoration after solve (Inputs vs. Outputs).** A reader might wonder: *if `myopic.py` clamped `p_nom_min` and `p_nom_max` during the run, where does the built capacity actually live, and why restore the bounds at the end?*
  - **Inputs vs. Outputs:** In PyPSA, `p_nom_min` and `p_nom_max` are **input parameters** (the allowable range: 0 to 54,420.5 MW). The solver's optimized decision is written into **`p_nom_opt`** (the **output** variable: 1,888 MW).
  - **Why clamping was temporary:** During Blocks 2 and 3, `myopic.py` temporarily set `p_nom_min = p_nom_max = p_nom_opt` purely as an operational steering wheel to force the solver to respect earlier decisions without losing extendability.
  - **Why restoration is necessary:** Once all blocks finish, `myopic.py` restores `p_nom_min` and `p_nom_max` back to their pristine baseline (0 and 54,420.5 MW) while leaving `p_nom_opt = 1,888 MW` untouched. If it did not:
    1. *Falsified assumptions:* The saved file would show `p_nom_min = p_nom_max = 1,888 MW`, making it appear as though the user hardcoded 1,888 MW upfront rather than the model optimizing it.
    2. *Broken capacity accounting:* Downstream tools (`LtResultPreparer_Pypsa`) calculate leftover site potential by evaluating `p_nom_max - p_nom_opt`. Leaving bounds clamped at 1,888 MW would yield $1,888 - 1,888 = 0$, falsely reporting to dashboards that the site's resource potential was 100% depleted!
  - Restoring the bounds ensures the output file (`Compiled models/{Scenario}_Solution.nc`) cleanly distinguishes between what was an input assumption and what was an optimized outcome, reading identically to a single multi-period solve.

<!-- callout {"kind": "note", "title": "Reading the names"} -->
`Xp_` marks a PLEXOS expansion candidate; no prefix means existing or committed capacity. The trailing `_{year}` is the vintage, added only because PyPSA needs one component per build year.

<!-- text -->
More: [@pypsa-architecture#vintages|PyPSA Model Architecture, Milestone-wise asset declarations] and [@pypsa-architecture#foresight|Perfect foresight and myopic planning].

<a id="sampled-chronology"></a>

# 3 Sampled chronology with peak and energy rescaling {#sampled-chronology}
<!-- section {"sources": ["PypsaExpansion/Scripts/V0 model creator/README.md, Time resolution", "PypsaExpansion/PypsaModel/Model csvs/snapshots.csv, loads-p_set.csv, meta.json", "PlexoModel/Model data csv/LoadHourly_MW_Nd.Center.csv"]} -->

> Both models optimise 3 representative days per month. PyPSA had to rebuild PLEXOS's way of choosing the days and of rescaling their load to each month's true peak and energy.

<a id="sampled-chronology-issue"></a>

## 3.1 The issue {#sampled-chronology-issue}

<!-- text {"_list": true} -->
A year has 8,760 hours, and eight periods of them would be far beyond the solver. Both models therefore optimise only a few representative days, each standing for several real days.

PLEXOS's LT Plan does this with its sampled chronology (`Hourly for 3 day per month`): it picks statistically representative days, then rescales their load so that each month keeps its true peak and energy. PyPSA has no such feature. Its simple option, the same calendar days every year with the raw load, plans against a peak 1–5% too low. Neither model has a reserve margin, so the peak reaches the build decisions only through the sampled hours.

<a id="sampled-chronology-solution"></a>

## 3.2 The solution {#sampled-chronology-solution}

<!-- list {"ordered": true} -->
1. **Pick the days.** For each period and month, every day is described by its 24 hourly loads at the 3 nodes (72 numbers). Backward scenario reduction drops, one by one, the day whose removal changes the set least, until 3 remain. Each dropped day's weight goes to its nearest kept day.
2. **Rescale the load.** Each node's load on the kept days becomes a + b · load, with a and b chosen so that the weighted days reproduce the month's input energy and its peak exactly. If that would turn the shape upside down or make it negative, only the energy is matched.

<!-- equation {"id": "eq-rescale", "caption": "Rescaled load of node n in month m, and the two conditions that set a and b."} -->
```math
\hat L_{n,t} = a_{n,m} + b_{n,m}\, L_{n,t}, \qquad \sum_{t \in m} w_t\, \hat L_{n,t} = E_{n,m}, \qquad \max_{t \in m} \hat L_{n,t} = P_{n,m}
```

| Symbol | Meaning | Unit |
| --- | --- | --- |
| L_{n,t} | Input load of node n in sampled hour t | MW |
| w_t | Snapshot weight: the real days that hour's day stands for ([[snapshot-weighting]]) | h |
| E_{n,m},\ P_{n,m} | Input energy and peak of node n in month m | MWh, MW |

<!-- text -->
Solar and wind profiles are not rescaled, in either model.

<a id="sampled-chronology-csvs"></a>

## 3.3 In the model csvs {#sampled-chronology-csvs}

<!-- text -->
The Center node in July 2030:

<!-- list -->
- **`snapshots.csv`**: the 72 July 2030 rows are 17, 18 and 31 July, with `objective` and `generators` weights of 10, 10 and 11. Each sampled hour stands for that many real hours, and the three add up to July's 31 days; over a period the weights sum to 8,760 hours. The `stores` weight is 1, so storage moves hour by hour within a sampled day.
- **`meta.json`, block `time_sampling`**: `days["2030"]` lists `[7, 17, 10.0]`, `[7, 18, 10.0]` and `[7, 31, 11.0]` (month, day, weight), and `load_rescale["Center"]["2030M7"]` is `[-79.6242, 1.105437, "max+energy"]`: a = −79.6 MW, b = 1.105.
- **`loads-p_set.csv`**, column `Load_Center`, holds the rescaled load. Its July 2030 maximum is 931.9 MW and its weighted energy 410,320 MWh, both exactly the input's (`PlexoModel/Model data csv/LoadHourly_MW_Nd.Center.csv`).
- **`generators-p_max_pu.csv`** holds the solar and wind profiles of the same hours, as they are.

<!-- text -->
More: [@pypsa-architecture#time-resolution|PyPSA Model Architecture, Time resolution].

<a id="custom-constraints"></a>

# 4 Custom constraints written into the solver {#custom-constraints}
<!-- section {"sources": ["PypsaExpansion/Scripts/RunModel/snsp_constraints.py, SNSP_Constraints.md", "PypsaExpansion/Scripts/RunModel/csp_constraints.py, CSP_Constraints.md", "PypsaExpansion/Scripts/RunModel/max_cf_constraints.py, MaxCF_Constraints.md", "PypsaExpansion/PypsaModel/Model csvs/meta.json, generators.csv, storage_units.csv"]} -->

> Three PLEXOS constraint families have no PyPSA equivalent. They are written into the optimisation problem at solve time, so the csvs hold only their inputs.

<a id="custom-constraints-issue"></a>

## 4.1 The issue {#custom-constraints-issue}

<!-- text -->
PLEXOS expresses rules as Constraint objects: any variables, any coefficients, in every interval or over any period. PyPSA's native [[global-constraint]] covers far fewer shapes, mainly a capacity limit per carrier, bus and period. A component's own `e_sum_min` and `e_sum_max` are fixed MWh over its whole life. None of these can say "every hour, in each zone", tie two components together hour by hour, or cap energy per month in proportion to a capacity that is still being chosen.

<a id="custom-constraints-solution"></a>

## 4.2 The solution {#custom-constraints-solution}

<!-- text -->
Each family is written straight into PyPSA's optimisation problem (the linopy model) when a solve starts, by its own module in `PypsaExpansion/Scripts/RunModel/`, under PLEXOS's constraint names. Their inputs are stored in `meta.json`, which travels with the csvs.

<!-- callout {"kind": "warning", "title": "Not in the csvs, not in the solution file"} -->
These constraints exist only while a solve runs. `global_constraints.csv` doesn't list them, and the saved solution keeps no trace of them even where they bind. Only their inputs (`meta.json`) remain, plus, for SNSP, a file of shadow prices. See [@pypsa-architecture#constraint-visibility|Where constraints live].

<a id="custom-snsp"></a>

## 4.3 SNSP limits {#custom-snsp}

<!-- text {"_list": true} -->
**Issue.** PLEXOS caps inverter-based supply at 70% of total supply in every hour, system-wide (`Con_SnspGlobal`) and in each synchronous area, where an area may count synchronous support borrowed from a neighbour ([[snsp]]). That is an hourly, per-zone rule with extra variables for the borrowed support.

**Solution.** `snsp_constraints.py` adds, for every hour of every period, `Con_SnspGlobal`, one `Con_SnspSynchroArea_{zone}` per node, and for each neighbour a borrowed-support variable with two caps: `Con_SnspImportGenCap_{zone}_From{neighbour}` (the neighbour's synchronous output that hour) and `Con_SnspImportInterconCap_{zone}_From{neighbour}` (the corridor capacity that period).

**In the model csvs:**

<!-- list -->
- **`meta.json`, `snsp.limit`**: 0.7 for every milestone year.
- **The `carrier` column decides each component's side.** `SolarPV`, `WindOnshore`, `WindOffshore` and `Battery_4hr` (storage_units.csv) are inverter-based. Thermal, hydro and the CSP turbines are synchronous. `VoLL`, `xImport` and `xExport` count on neither side.
- **Center borrows from both neighbours**: links.csv has a `North-Center` and a `South-Center` corridor, so Center gets `Con_SnspImportGenCap_Center_FromNorth` and `Con_SnspImportGenCap_Center_FromSouth`, each with its corridor cap, summed over every corridor vintage in service.
- **After a solve**, `{Scenario}_Solution SNSP Shadow Prices.csv` holds each constraint's shadow price per hour.

<a id="custom-csp"></a>

## 4.4 CSP with thermal storage {#custom-csp}

<!-- text {"_list": true} -->
**Issue.** PLEXOS models a CSP plant as two objects tied by constraints: a turbine with thermal storage (a Battery) and a Solar Field Generator. The field charges the storage, the field is sized at the [[solar-multiple]] times the turbine, and all CSP configurations at a node share one site potential. PyPSA can't link two components hour by hour.

**Solution.** Two components on the same bus, plus three solve-time constraints in `csp_constraints.py`: `Con_CspChargeLink_{turbine}` (every hour, the storage is charged by exactly the field's output, never from the grid), `Con_CspFieldLink_{turbine}` (field MW = Solar Multiple × turbine MW) and `Con_CspPotential_{node}_{period}` (all CSP at the node within the joint ceiling).

**In the model csvs**, the 6-hour candidate at Center, 2030 vintage:

<!-- table {"id": "tab-csp", "caption": "The two halves of `Xp_SolarCSP_6hr_Center_2030` and their shared ceiling."} -->
| File | Row or key | Key values |
| --- | --- | --- |
| storage_units.csv | Xp_SolarCSP_6hr_Center_2030 | `max_hours` 6; `p_max_pu` 0.94 (availability); `p_min_pu` −2.1 (charging up to Solar Multiple 2.1 × turbine MW); `capital_cost` 754,679 $/MW-yr, the whole plant's cost |
| generators.csv | Xp_SolarCSP_6hr_SolarField_Center_2030 | `carrier` SolarCSP_6hr_SolarField; `capital_cost` 0; `p_nom_max` 86,058 MW = 2.1 × 40,980 |
| meta.json | `csp.potential.Center` | 40,980 MW from 2027 (0 in 2023): the joint ceiling |

<!-- text -->
The 12- and 15-hour configurations follow the same pattern (`p_min_pu` −4.1 and −5.1). The 0-hour configuration, `Xp_SolarCSP_0hr_Center_*`, is a plain generator that shares the same ceiling.

<a id="custom-energy-caps"></a>

## 4.5 Capacity-factor energy caps {#custom-energy-caps}

<!-- text {"_list": true} -->
**Issue.** Hydro is limited by water, Bio by fuel, Geo by its steam field. PLEXOS caps their energy, not their hourly output: `Max Capacity Factor Month` for hydro and `Max Capacity Factor Year` for Bio, Geo and OthRE. The plants can therefore run at full availability in the evening and back off at midday. PyPSA's only energy bound, `e_sum_max`, is a fixed MWh over a component's life: it can't follow a capacity that is still being chosen, or apply per month.

**Solution.** `max_cf_constraints.py` adds one constraint per PLEXOS object and month (`Con_MaxCFMonth_{object}_{year}_M{m}`) or year (`Con_MaxCF_{object}_{year}`): the weighted output of the object's vintages in service may not exceed capacity factor × their capacity × the hours of the month or year.

**In the model csvs:**

<!-- list -->
- **generators.csv**: the `HyDam_Center_*` rows have `p_max_pu` 0.96, so only availability limits an hour; there is no hourly capacity-factor cap.
- **`meta.json`, `max_cf_month.HyDam_Center`**: 0.98 in January–March, falling to 0.63 in August–October. `max_cf` holds the annual caps, e.g. `Bio_South` 0.5.
- **In the DES solution, August 2030**, Cahora Bassa (2,075 MW) uses its 63.1% budget exactly, while its hourly output ranges from 0 to 96% of capacity.

<!-- text -->
More: [@pypsa-architecture#snsp|PyPSA Model Architecture, SNSP limits], [@pypsa-architecture#csp|Solar CSP with thermal storage] and [@pypsa-architecture#energy-caps|Capacity-factor energy caps].

<a id="losses-markets"></a>

# 5 Corridor losses, token wheeling and cross-border markets {#losses-markets}
<!-- section {"sources": ["PypsaExpansion/Scripts/RunModel/intercon_losses.py, config.csv", "PypsaExpansion/Scripts/V0 model creator/README.md", "PypsaExpansion/PypsaModel/Model csvs/links.csv, generators.csv, global_constraints.csv"]} -->

> A two-way PyPSA link can't carry a loss or a flow charge, and PyPSA has no market object. Corridors are split into one-way links at solve time, and markets are emulated as generators.

<a id="losses-markets-corridors"></a>

## 5.1 Corridors: losses and wheeling {#losses-markets-corridors}

<!-- text {"_list": true} -->
**Issue.** PLEXOS loses 5% of the power sent on each internal Line (`Loss Incr` 0.05 each way) and charges 0.01 $/MWh each way (`Wheeling Charge`), a token cost whose only job is to stop the solver shipping surplus into a region that is itself in surplus. A two-way PyPSA Link applies its `efficiency` and `marginal_cost` to the signed flow: sending backwards, a 5% loss would become a 5% gain and the charge a rebate.

**Solution.** The csvs keep one lossless two-way Link per corridor vintage. At solve time `intercon_losses.py` turns each into two one-way Links: the original, now with `p_min_pu` 0, and a mirror `{name}-reverse` from bus1 to bus0. Both get `efficiency` 0.95 and `marginal_cost` 0.01 $/MWh (`intercon_loss_fraction` and `intercon_flow_cost` in RunModel's `config.csv`). The mirror copies the capacity but has no capital cost and no carrier, so the corridor is paid for and counted once; for an extendable vintage, a tie constraint (`Link-reverse_capacity_tie-{name}`) keeps both directions at the same built capacity. The results fold the pair back into one corridor, with its losses as `Line.Loss` rows.

**In the model csvs**, the South–Center corridor in links.csv:

<!-- table {"id": "tab-corridor", "caption": "The three kinds of Link rows of the South–Center corridor."} -->
| Rows | Kind | Key values |
| --- | --- | --- |
| South-Center_2023 … _2050 | Existing | Fixed `p_nom`, growing from 34.4 to 86.0 MW by 2030; `lifetime` = the years of its period |
| South-Center Candidate 1_2027 … _2050 | Generic expansion candidate | Extendable; `p_nom_max` 10,000 MW; `capital_cost` 50,430 $/MW-yr (500 $/kW over 50 years at 10%) |
| South-Center 2027-2032_2027 … _2032 | Committed line | Extendable; `carrier` = its own name; `p_nom_max` 2,502.5 MW |

<!-- list -->
- **All three kinds have `p_min_pu` −1 and no `efficiency` or `marginal_cost` column**: lossless and free until the solve splits them.
- **The committed line's window is in `global_constraints.csv`**: `CommittedCap_South-Center 2027-2032_{year}` caps its vintages at 2,502.5 MW in each period, and `CommittedCap_South-Center 2027-2032_2032_min` requires all of it by 2032.

<a id="losses-markets-markets"></a>

## 5.2 Cross-border markets {#losses-markets-markets}

<!-- text {"_list": true} -->
**Issue.** PLEXOS models cross-border trade with Market objects: a price, a MW cap on sales or purchases, and an optional yearly minimum (take-or-pay). PyPSA has no market component.

**Solution.** Each Market becomes one generator per milestone year on its node. An import (`ImportFrom{Country}_{Node}`) is an ordinary generator: 0 ≤ p ≤ cap, with `marginal_cost` = the purchase price. An export (`ExportTo{Country}_{Node}`) can only withdraw (`p_min_pu` −1, `p_max_pu` 0); since p ≤ 0, `marginal_cost` = the sale price turns every exported MWh into revenue. A yearly minimum becomes the generator's own energy bound: `e_sum_min` for an import, `e_sum_max` = −minimum for an export. Each generator is in service in one period only, so its bound applies to exactly one (weighted) year. Markets count on neither side of SNSP.

**In the model csvs** (generators.csv, Center):

<!-- list -->
- **`ExportToSouthAfrica_Center_2023` … `_2050`**: `p_nom` 1,920 MW, `p_min_pu` −1, `p_max_pu` 0, `marginal_cost` 5 $/MWh, `carrier` xExport. The 2023–2030 rows carry `e_sum_max` −9,895,380 MWh: at least 9,895 GWh a year must be exported while the contract runs. From 2032 the bound is `inf`.
- **`ImportFromSouthAfrica_Center_*`**: `p_nom` 1,920 MW, `p_min_pu` 0, `p_max_pu` 1, `marginal_cost` 120 $/MWh, `carrier` xImport.
- **Caps change from row to row where PLEXOS's do**: `ImportFromZimbabwe_Center` rises from 216 MW to 696 MW in 2029. Markets that open later simply have no earlier rows: Malawi from 2027, Zambia from 2029.

<!-- text -->
More: [@pypsa-architecture#corridors|PyPSA Model Architecture, Internodal corridors] and [@pypsa-architecture#trade|Cross-border trade].

<a id="economics-availability"></a>

# 6 Economics and availability {#economics-availability}
<!-- section {"sources": ["PypsaExpansion/Scripts/RunModel/economics.py, Economics.md", "PypsaExpansion/PypsaModel/Model csvs/investment_periods.csv, generators.csv, storage_units.csv, generators-p_max_pu.csv, generators-marginal_cost.csv, meta.json"]} -->

> PyPSA doesn't discount across periods, annualise build costs or derate for outages by itself. All three are set from PLEXOS's rules in the csvs.

<a id="economics-availability-issue"></a>

## 6.1 The issue {#economics-availability-issue}

<!-- text {"_list": true} -->
PLEXOS's LT Plan minimises the net present value of all costs at a 10% discount rate, with 2023 as year 0. It turns each build cost into a yearly charge with the capital recovery factor ([[crf]]) over the economic life, at the asset's WACC or else the discount rate, plus fixed O&M. And it derates every unit's capacity by its forced outage rate (FOR) and maintenance rate (MR).

PyPSA does none of this by itself: a period's costs count once unless the period carries a weight, `capital_cost` is used as given, and capacity is fully available unless a profile says otherwise.

<a id="economics-availability-solution"></a>

## 6.2 The solution {#economics-availability-solution}

<!-- list -->
- **Period weights.** Each period's `objective` weight is the sum of the yearly discount factors over the years it stands for, so its costs count once per year, discounted.
- **Annuities.** Each vintage's `capital_cost` is its build year's build cost × CRF, plus FO&M. PyPSA charges it in every period the vintage is in service, times that period's weight.
- **Availability.** k = 1 − FOR − MR caps every hour: `p_max_pu` = k for dispatchable plants, profile × k for solar and wind, and ±k for battery discharging and charging.
- **Editable without a rebuild.** The discount rate and each asset's cost inputs are stored in `meta.json` (block `economics`); `economics.py` recomputes the weights and capital costs from them before every solve.

<!-- equation {"id": "eq-weight", "caption": "NPV weight of period p, which stands for the years up to the next milestone p′ (2053 for the last period)."} -->
```math
w_p = \sum_{t=p}^{p'-1} (1 + r)^{-(t - 2023)}
```

<!-- equation {"id": "eq-annuity", "caption": "Annual capital cost of vintage v."} -->
```math
c_v = I_v\, \frac{r\,(1+r)^{n_v}}{(1+r)^{n_v} - 1} + F_v
```

| Symbol | Meaning | Unit |
| --- | --- | --- |
| r | WACC of the asset, else the LT Plan discount rate (10%) | fraction |
| I_v,\ F_v | Build cost and fixed O&M of vintage v | $/MW, $/MW-yr |
| n_v | Economic life (else technical life) | years |

<a id="economics-availability-csvs"></a>

## 6.3 In the model csvs {#economics-availability-csvs}

<!-- table {"id": "tab-weights", "caption": "investment_periods.csv: the NPV weight of each period.", "notes": "Check, 2023: 1 + 1.1^−1 + 1.1^−2 + 1.1^−3 = 3.487. The 2040 period weighs as much as 2035 because it stands for ten years; 2050 stands for 2050–2052 only."} -->
| period | years | objective |
| --- | --- | --- |
| 2023 | 4 | 3.487 |
| 2027 | 2 | 1.304 |
| 2029 | 1 | 0.564 |
| 2030 | 2 | 0.980 |
| 2032 | 3 | 1.160 |
| 2035 | 5 | 1.329 |
| 2040 | 10 | 1.337 |
| 2050 | 3 | 0.209 |

<!-- text {"_list": true} -->
**Capital cost of `Xp_SolarPV_Center_2030`.** `meta.json` `economics.assets` gives `[493786.0, 10863.0, 30.0, null]`: build cost $/MW, FO&M $/MW-yr, economic life and WACC (null = the 10% discount rate). CRF(10%, 30 years) = 0.10608, so 493,786 × 0.10608 + 10,863 = 63,243 $/MW-yr, the `capital_cost` in generators.csv. The 2050 vintage costs 39,151 $/MW-yr, because its build cost has fallen to 305,677 $/MW.

**Availability:**

<!-- list -->
- **`Xp_NGCCG_Center_*`**: `p_max_pu` 0.895 (FOR 4.5% + MR 6%).
- **`HyDam_Center_*`**: `p_max_pu` 0.96 (2% + 2%).
- **`Xp_SolarPV_Center_2030`** in generators-p_max_pu.csv: the solar profile × 0.96, at most 0.767.
- **`Xp_Battery_4hr_Center_2030`** in storage_units.csv: `p_max_pu` 0.94 and `p_min_pu` −0.94 (3% + 3%), so charging is derated too.
- **Running costs that change over time** are in generators-marginal_cost.csv, e.g. `Xp_Coal_South_*` rising from 45.6 $/MWh in 2023 to 51.1 $/MWh in 2050; constant ones stay in generators.csv (`Xp_NGCCG_Center_*`: 20.1 $/MWh).

<!-- text -->
More: [@pypsa-architecture#npv|PyPSA Model Architecture, Discounted objective and capital annuities] and [@pypsa-architecture#availability|Availability].

<!-- appendices -->

<a id="csv-map"></a>

# Appendix A The model csvs at a glance {#csv-map}
<!-- section {"sources": ["PypsaExpansion/PypsaModel/Model csvs/"]} -->

<!-- text -->
`PypsaExpansion/PypsaModel/Model csvs/` is the PES baseline, written from `base_model.nc` by NcCsvConverter. Its `DES/` subfolder holds only the files that differ for DES; a DES run lays them over the baseline. The rows of every time-series file follow `snapshots.csv` row by row (their first column is the row number).

<!-- table {"id": "tab-csv-map", "caption": "Files in the model csvs folder (PES, 20 October 2026)."} -->
| File | What it holds | Efforts |
| --- | --- | --- |
| buses.csv, loads.csv | The 3 nodes (South, North, Center) and one load per node | — |
| snapshots.csv | 6,912 sampled hours (8 periods × 864) and their weights | 1, 3 |
| investment_periods.csv | The 8 milestone years, their NPV weights and year counts | 1, 6 |
| generators.csv | 651 generators: existing plants, candidate vintages, markets, CSP solar fields, VoLL slack | 2, 4, 5, 6 |
| generators-p_max_pu.csv | Hourly availability of 182 generators (solar, wind and CSP field profiles × k) | 3, 6 |
| generators-marginal_cost.csv | Running costs of 88 generators that change over time | 6 |
| storage_units.csv | 102 batteries and CSP turbines with storage | 4, 6 |
| loads-p_set.csv | Hourly (rescaled) load of each node | 3 |
| links.csv | Internal corridors: existing, candidate and committed vintages | 5 |
| global_constraints.csv | 432 capacity limits: 419 `PotCap_` (potentials and planned minimums) and 13 `CommittedCap_` (committed lines) | 2, 5 |
| meta.json | Inputs of the solve-time constraints and settings: `time_sampling`, `snsp`, `csp`, `max_cf`, `max_cf_month`, `peak_load`, `economics` | 3, 4, 6 |
| network.csv | Network name and PyPSA version | — |
