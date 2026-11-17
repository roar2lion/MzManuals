# ToDo

- [ ] **Minimum output levels for hydro, bio and geo.** Research a minimum hourly output (min pu) for hydro, biomass and geothermal plants, based on the region's own features, and add it to both models: `Min Stable Factor` in PLEXOS and `p_min_pu` in PyPSA.
  - **Why:** the energy-cap constraints (monthly for hydro, annual for Bio, Geo and OthRE) let these plants swing freely between 0% and their availability every hour, which overstates the system's flexibility. For example, Cahora Bassa drops to 0 MW on some hours of the sampled August days in DES 2030. Today every `HyDam_*`, `Bio_*` and `Geo_*` generator has `Min Stable Factor` = 0, no ramp limits and no minimum up or down time.
  - **Regional features to research:**
    - **Hydro:** the Zambezi's minimum downstream release; the export contract with Eskom and the minimum load of the HVDC link to Apollo; Cahora Bassa's role as the main synchronous plant in the centre of the grid; the turbine types of the existing plants.
    - **Biomass:** boiler type, and whether output is tied to a sugar mill's crushing season (bagasse).
    - **Geothermal:** flash or binary design, and how the steam field constrains output.
  - **Constraint:** each floor must stay below the plant's energy cap. In both models these plants have no on/off decisions, so a floor above the cap makes the run infeasible or overrides the cap. Current caps: Geo 54–59% a year, Bio 50% a year, hydro monthly (HyDam_Center's lowest month is about 46%).
  - **After implementing:** update slide 5 of `MasterDocs/PypsaVsPlexos Stories/Pypsa vs Plexos.pptx` and the capacity-factor energy caps section of the `pypsa-architecture` manual.
