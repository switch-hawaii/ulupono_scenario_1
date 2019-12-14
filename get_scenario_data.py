#!/usr/bin/env python

from __future__ import print_function, division
import sys, os, argparse

import switch_model.hawaii.scenario_data as scenario_data


parser = argparse.ArgumentParser()
parser.add_argument('--skip-cf', action='store_true', default=False,
    help='Skip writing variable capacity factors file (for faster execution)')
parser.add_argument('--skip-ev-bids', action='store_true', default=False,
    help='Skip writing EV charging bids file (for faster execution)')
# default is daily slice samples for all but 4 days in 2007-08
parser.add_argument('--slice-count', type=int, default=0, # default=727,
    help='Number of slices to generate for post-optimization evaluation.')
parser.add_argument('--tiny-only', action='store_true', default=False,
    help='Only prepare inputs for the tiny scenario for testing.')

cmd_line_args = parser.parse_args()

# settings used for the base scenario
# (these will be passed as arguments when the queries are run)

print("""
TODO (soon):
+ use newer DER/DESS forecast
+ use newer EV charging cycle
* interim technique for O&M:
  + use O&M costs from AEO 1996
  * apply to HECO generation in 2017 (EIA) and compare to total O&M reported by
    HECO on FERC Form 1, and split off a portion to use as "non-indexed O&M"
+ interim technique for PPAs:
  + for now, assume no capacity payment
  + calculate fuel expenditure for 2018 (if any) based on our fuel price data
    and EIA production and fuel consumption (form 923)
  + use fixed and variable O&M costs as above
  + adjust the capital cost to get PPA to match PUC PPAs in 2018
    + see p. 66 of https://puc.hawaii.gov/wp-content/uploads/2018/12/FY18-PUC-Annual-Report_FINAL.pdf

- use all available weather for post-optimization evaluation
+ Request O&M and historical PPA data and current load forecast from HECO
  - will Kalaeloa contract be renewed? PUC lists it as expired in 10/31/17
    - this article says they're on month-to-month while negotiating:
      - https://www.hawaiinewsnow.com/story/31931002/time-running-out-on-kalaeloa-partners-25-year-contract-with-heco/
  - do PPAs have capacity payments, curtailment terms, escalators over time and/or fuel-cost indexing?
    - AES is inflation-indexed; Kalaeloa is pegged to asian crude prices: p. 7 of http://www.hei.com/interactive/newlookandfeel/1031123/annualreport2018.pdf
    - what about Tesoro Hawaii and Hawaii Cogen, which burn waste oil?
    - what about current wind and solar?
    - total expenditure on AES, Kalaeloa, HPOWER and aggregated wind and solar PPAs is shown on p. 105 of http://www.hei.com/interactive/newlookandfeel/1031123/annualreport2018.pdf
      - we could check that against production at each one in 2016-2018 to see if price varies between years
+ Report EV MWh for use in RIST PIMs
+ check HECO's data submissions, see if they answer all earlier questions

+ separate total PPA cost into intermittent (wind/solar) projects and all other
  + just add column identifying intermittent vs. not
+ disaggregate cost reporting (incl. ppa items) by vintage (extra column)
  + supports PIM assuming x percent of a year's new PPAs is savings vs PUC benchmark, of which y percent is returnable
  + PIM will need to key off tech start year to find the recent starts
  + probably create an inner loop over relevant build years for each tech
  + will need to assign some values by vintage:
    + amortization cost, fixed o&m, additions, retirements, capital outlay
  + will need to allocate some values across vintages (by share of existing capacity):
    + fuel, variable o&m, emissions

- convert AES to a PPA cost? (include it as fixed and variable O&M; but this doesn't allow fuel switching...)

* also note: the current k-means re-creation code does not recreate dates with
  the same weights each time; we should fix this or assign matching dates more
  directly

- (0 days) exclude thermal technologies in get_scenario_data.py instead of editing the outputs or implementing in heco_outlook
  - adjust exclude technology rule to pull in the existing plants (e.g., exclude new schofield will still allow the existing one)
- (0.75 day) break existing wind and solar projects into individual projects with performance matching EIA and capital cost and/or fixed O&M that reproduce their PPA costs (rebuildable at future costs)
- derate or restrict use of AES and Kalaeloa to match historical levels
- (0.5 day) Add plants that are in EIA tables but not in Switch
    - a few small solar plants
    - two cogen thermal plants
      - Tesoro Hawaii (18.5 MW, owned by PAR Petroleum LLC) and Hawaii Cogen (9.6 MW, owned by Island Energy Services / IES Downstream LLC)
      - these run at almost exactly 100% cap factor (2018 Tesoro was 94.7% and Hawaii Cogen was 110.3%)
      - model as baseload at the average level or 100%, like H-POWER
      - use heat rate and fuel based on EIA reporting of "elec fuel consumption"
      - use PPA cost from PUC annual report 2018 p. 66
        - $.1175 * 14 hours + $.1173 * 10 hours for Hawaii Cogen
        - $ 0.1166 * 14 + $0.1168 * 10 hours for Par Hawaii
        - assume constant real cost? or index to LSFO cost? (they burn waste oil and gas)
        - either set the fuel cost to get the right total cost or make fuel free and put the cost into variable O&M
      - assume they shutdown when refineries do (like Kalaeloa requirements)
  - will all of them retire by 2022?
- (0.5 day) Apply maintenance outages from Switch-GE comparison, as specified in documentation
- (1.5 day) benchmark system using 2017 data and revise our system
    - Check whether we run plants differently from actual experience
        - force commitment of all "baseload" plants if needed
    - Check whether we should adjust our heat rates for AES and other plants to match EIA reporting
      - EIA data for AES coal plant show heat rate around 10.95, but we use GE rate of 17.6.
      - Check EIA vs. Switch heat rates for other plants.
      - are we running these plants differently from actual practice?
      - are GE heat rates wrong?
- (0.25 day) Why are Oahu plants burning biodiesel in 2020 according to pbr summary?
- (0.5 day) use weighting study data to check whether optimizing worst day with 0% weight, 1/727 weight, all-closest-days weight or halfway between gives best plan
  - why is PBR scenario feasible with no new thermal but weighting study isn't?
- (1 day) Do better per-MMBtu fuel cost comparison between Switch and HECO 10k in "../Switch-HECO-DBEDT cost comparisons.xlsx"
  - use 2018 test case
  - include only HECO production from LSFO, not cogen IPPs
  - also check for other explanations noted in draft e-mail to Erin Sowerby around 11/10/19 but not finished
- (0.25 day) use clean transportation plan BAU charging times for light-duty EVs instead of Paritosh's
- (0.5 day) use advanced EV module for heavy-duty vehicles (ignoring heavy duty vehicles for now)

TODO (later):
- Don't allow construction of CC152 until 2022 or 2025 (hasn't been proposed or gotten permits yet)
- move approved wind/solar projects from heco outlook to existing capacity (and assign specific locations)
- maybe extend Switch to model combined solar+storage; use this for RFP projects and DER+DESS forecast
x maybe input future RE costs as PPAs instead of capital/O&M and back end aggregation
x HECO says in PSIP (vol. 1 p. 4-3) that they will convert Honolulu 8 & 9 to synchronous condensers in 2021; we don't model this cost or effect (voltage support and inertia)

Outstanding questions:
.- Will CBRE Phase 1 solar enter service in 2020?
.- Should we reduce DER forecast in light of HECO's projected shortfall reported in CBRE proceeding?
*** they don't know how much wind and/or solar they'll get in phase 2, could have both
.- How much solar should we expect on Oahu in CBRE Phase 2 and when?
.- Do we expect any wind on Oahu in CBRE Phase 2, and if so, when?
.- Is Na Pua Makani wind project 24 MW or 27 MW? (see https://www.napuamakanihawaii.org/fact-sheet/ vs PSIP and https://www.hawaiianelectric.com/clean-energy-hawaii/our-clean-energy-portfolio/renewable-project-status-board)
.- Will RFP Phase 2 include any wind or just solar?
.- How much storage is expected to be procured with RFP Phase 2 solar?
.- The PSIP included 90 MW of contingency battery in 2019, but that doesn't seem to be moving ahead. Should we assume this has been abandoned?
.- Can we get the business-as-usual charging profiles for light-duty EVs that HECO used for the Electrification of Transport study?
- Should Switch prioritize the best distributed PV locations or choose randomly?
- Should we include multi-month hydrogen storage in the scenario (currently don't)?
- Should we include Lake Wilson pumped storage hydro in the scenario (currently do)?
""")

# EIA-based forecasts, mid-range hydrogen prices, NREL ATB reference technology prices,
# PSIP pre-existing construction, various batteries (LS can provide shifting and reserves),
# 10% DR, no LNG, optimal EV charging, full EV adoption

args = dict(
    # directory to store data in
    inputs_dir='inputs',
    # skip writing capacity factors file if specified (for speed)
    skip_cf = cmd_line_args.skip_cf,
    skip_ev_bids = cmd_line_args.skip_ev_bids,
    # use heat rate curves for all thermal plants
    use_incremental_heat_rates=True,
    # could be 'tiny', 'rps', 'rps_mini' or possibly '2007', '2016test', 'rps_test_45', or 'main'
    # '2020_2025' is two 5-year periods, with 24 days per period, starting in 2020 and 2025
    # "2020_2045_23_2_2" is 5 5-year periods, 6 days per period before 2045, 12 days per period in 2045, 12 h/day
    # time_sample = "2020_2045_23_2_2", # 6 mo/year before 2045
    # time_sample = "k_means_5_12_2",  # representative days, 5-year periods, 12 sample days per period, 2-hour spacing
    # time_sample = "k_means_5_24",  # representative days, 5-year periods, 12 sample days per period, 1-hour spacing
    # time_sample="k_means_5_24_2",  # representative days, 5-year periods, 12 sample days per period, 2-hour spacing
    # time_sample="k_means_5_16+_2",  # representative days, 5-year periods, 16+tough sample days per period, 2-hour spacing
    # time_sample="k_means_235_12+_2",  # representative days, 2/3/5-year periods, 12+tough sample days per period, 2-hour spacing
    time_sample="k_means_daily_235_12+_2",  # representative days, 2/3/5-year periods, 12+tough sample days per period, 2-hour spacing
    # subset of load zones to model
    load_zones = ('Oahu',),
    # "hist"=pseudo-historical, "med"="Moved by Passion", "flat"=2015 levels, "PSIP_2016_04"=PSIP 4/16
    # PSIP_2016_12 matches PSIP report but not PSIP modeling, not well documented but seems reasonable
    # in early years and flatter in later years, with no clear justification for that trend.
    # PSIP_2016_12_calib_2018 matches PSIP report but rescales peak and average in all
    # years by a constant value that gets them to match FERC data in 2018
    load_scen_id = "PSIP_2016_12_calib_2018",
    # "PSIP_2016_12"=PSIP 12/16; ATB_2018_low, ATB_2018_mid, ATB_2018_high = NREL ATB data; ATB_2018_flat=unchanged after 2018
    tech_scen_id='ATB_2019_mid',
    # tech_scen_id='PSIP_2016_12',
    # '1'=low, '2'=high, '3'=reference, 'EIA_ref'=EIA-derived reference level, 'hedged'=2020-2030 prices from Hawaii Gas
    fuel_scen_id='AEO_2019_Reference',
    # note: 'unhedged_2016_11_22' is basically the same as 'PSIP_2016_09', but derived directly from EIA and includes various LNG options
    # Blazing a Bold Frontier, Stuck in the Middle, No Burning Desire, Full Adoption,
    # Business as Usual, (omitted or None=none)
    # ev_scenario = 'PSIP 2016-12',  # PSIP scenario
    # ev_scenario = 'Full Adoption',   # 100% by 2045, to match Mayors' commitments
    ev_scenario = 'EoT 2018',   # 55% by 2045 from HECO Electrification of Transport study (2018)
    ev_charge_profile = 'EoT_2018_avg',  # hourly average of 2030 profile from HECO Electrificaiton of Transport Study
    # should the must_run flag be converted to set minimum commitment for existing plants?
    enable_must_run = 0,
    # list of technologies to exclude (currently CentralFixedPV, because we don't have the logic
    # in place yet to choose between CentralFixedPV and CentralTrackingPV at each site)
    # Lake_Wilson is excluded because we don't have the custom code yet to prevent
    # zero-crossing reserve provision
    exclude_technologies = ('CentralFixedPV', 'Lake_Wilson'), # 'CC_152', 'IC_Barge', 'IC_MCBH', 'IC_Schofield',
    base_financial_year = 2020,
    interest_rate = 0.06,
    discount_rate = 0.03,
    # used to convert nominal costs in the tables to real costs in the base year
    # (generally only shifting by a few years, e.g., 2016 to 2020)
    inflation_rate = 0.020,
    # maximum type of reserves that can be provided by each technology (if restricted);
    # should be a list of tuples of (technology, reserve_type); if not specified, we assume
    # each technology can provide all types of reserves; reserve_type should be "none",
    # "contingency" or "reserve"
    max_reserve_capability=[('Battery_Conting', 'contingency')],
)

# electrolyzer data from centralized current electrolyzer scenario version 3.1 in
# http://www.hydrogen.energy.gov/h2a_prod_studies.html ->
# "Current Central Hydrogen Production from PEM Electrolysis version 3.101.xlsm"
# and
# "Future Central Hydrogen Production from PEM Electrolysis version 3.101.xlsm" (2025)
# (cited by 46719.pdf)
# note: we neglect land costs because they are small and can be recovered later
# TODO: move electrolyzer refurbishment costs from fixed to variable

# liquifier and tank data from http://www.nrel.gov/docs/fy99osti/25106.pdf

# fuel cell data from http://www.nrel.gov/docs/fy10osti/46719.pdf

# note: the article below shows 44% efficiency converting electricity to liquid
# fuels, then 30% efficiency converting to traction (would be similar for electricity),
# so power -> liquid fuel -> power would probably be less efficient than
# power -> hydrogen -> power. On the other hand, it would avoid the fuel cell
# investments and/or could be used to make fuel for air/sea freight, so may be
# worth considering eventually. (solar at $1/W with 28% cf would cost
# https://www.greencarreports.com/news/1113175_electric-cars-win-on-energy-efficiency-vs-hydrogen-gasoline-diesel-analysis
# https://twitter.com/lithiumpowerlpi/status/911003718891454464

inflate_1995 = (1.0+args["inflation_rate"])**(args["base_financial_year"]-1995)
inflate_2007 = (1.0+args["inflation_rate"])**(args["base_financial_year"]-2007)
inflate_2008 = (1.0+args["inflation_rate"])**(args["base_financial_year"]-2008)
h2_lhv_mj_per_kg = 120.21   # from http://hydrogen.pnl.gov/tools/lower-and-higher-heating-values-fuels
h2_mwh_per_kg = h2_lhv_mj_per_kg / 3600     # (3600 MJ/MWh)

current_electrolyzer_kg_per_mwh=1000.0/54.3    # (1000 kWh/1 MWh)(1kg/54.3 kWh)   # TMP_Usage
current_electrolyzer_mw = 50000.0 * (1.0/current_electrolyzer_kg_per_mwh) * (1.0/24.0)   # (kg/day) * (MWh/kg) * (day/h)    # design_cap cell
future_electrolyzer_kg_per_mwh=1000.0/50.2    # TMP_Usage cell
future_electrolyzer_mw = 50000.0 * (1.0/future_electrolyzer_kg_per_mwh) * (1.0/24.0)   # (kg/day) * (MWh/kg) * (day/h)    # design_cap cell

current_hydrogen_args = dict(
    hydrogen_electrolyzer_capital_cost_per_mw=144641663*inflate_2007/current_electrolyzer_mw,        # depr_cap cell
    hydrogen_electrolyzer_fixed_cost_per_mw_year=7134560.0*inflate_2007/current_electrolyzer_mw,         # fixed cell
    hydrogen_electrolyzer_variable_cost_per_kg=0.0,       # they only count electricity as variable cost
    hydrogen_electrolyzer_kg_per_mwh=current_electrolyzer_kg_per_mwh,
    hydrogen_electrolyzer_life_years=40,                      # plant_life cell

    hydrogen_fuel_cell_capital_cost_per_mw=813000*inflate_2008,   # 46719.pdf
    hydrogen_fuel_cell_fixed_cost_per_mw_year=27000*inflate_2008,   # 46719.pdf
    hydrogen_fuel_cell_variable_cost_per_mwh=0.0, # not listed in 46719.pdf; we should estimate a wear-and-tear factor
    hydrogen_fuel_cell_mwh_per_kg=0.53*h2_mwh_per_kg,   # efficiency from 46719.pdf
    hydrogen_fuel_cell_life_years=15,   # 46719.pdf

    hydrogen_liquifier_capital_cost_per_kg_per_hour=inflate_1995*25600,       # 25106.pdf p. 18, for 1500 kg/h plant, approx. 100 MW
    hydrogen_liquifier_fixed_cost_per_kg_hour_year=0.0,   # unknown, assumed low
    hydrogen_liquifier_variable_cost_per_kg=0.0,      # 25106.pdf p. 23 counts tank, equipment and electricity, but those are covered elsewhere
    hydrogen_liquifier_mwh_per_kg=10.0/1000.0,        # middle of 8-12 range from 25106.pdf p. 23
    hydrogen_liquifier_life_years=30,             # unknown, assumed long

    liquid_hydrogen_tank_capital_cost_per_kg=inflate_1995*18,         # 25106.pdf p. 20, for 300000 kg vessel
    liquid_hydrogen_tank_minimum_size_kg=300000,                       # corresponds to price above; cost/kg might be 800/volume^0.3
    liquid_hydrogen_tank_life_years=40,                       # unknown, assumed long
)

# future hydrogen costs
future_hydrogen_args = current_hydrogen_args.copy()
future_hydrogen_args.update(
    hydrogen_electrolyzer_capital_cost_per_mw=58369966*inflate_2007/future_electrolyzer_mw,        # depr_cap cell
    hydrogen_electrolyzer_fixed_cost_per_mw_year=3560447*inflate_2007/future_electrolyzer_mw,         # fixed cell
    hydrogen_electrolyzer_variable_cost_per_kg=0.0,       # they only count electricity as variable cost
    hydrogen_electrolyzer_kg_per_mwh=future_electrolyzer_kg_per_mwh,
    hydrogen_electrolyzer_life_years=40,                      # plant_life cell

    # table 5, p. 13 of 46719.pdf, low-cost
    # ('The value of $434/kW for the low-cost case is consistent with projected values for stationary fuel cells')
    hydrogen_fuel_cell_capital_cost_per_mw=434000*inflate_2008,
    hydrogen_fuel_cell_fixed_cost_per_mw_year=20000*inflate_2008,
    hydrogen_fuel_cell_variable_cost_per_mwh=0.0, # not listed in 46719.pdf; we should estimate a wear-and-tear factor
    hydrogen_fuel_cell_mwh_per_kg=0.58*h2_mwh_per_kg,
    hydrogen_fuel_cell_life_years=26,
)

mid_hydrogen_args = {
    key: 0.5 * (current_hydrogen_args[key] + future_hydrogen_args[key])
    for key in future_hydrogen_args.keys()
}
args.update(future_hydrogen_args)

args.update(
    pumped_hydro_headers=[
        'ph_project_id', 'ph_load_zone', 'ph_capital_cost_per_mw',
        'ph_project_life', 'ph_fixed_om_percent',
        'ph_efficiency', 'ph_inflow_mw', 'ph_max_capacity_mw'],
    pumped_hydro_projects=[
        ['Lake_Wilson', 'Oahu', 2800*1000+35e6/150, 50, 0.015, 0.77, 10, 150],
    ]
)

# TODO: move this into the data import system
args.update(
    rps_targets = {2015: 0.15, 2020: 0.30, 2030: 0.40, 2040: 0.70, 2045: 1.00}
)
rps_2030 = {2020: 0.4, 2025: 0.7, 2030: 1.0}

def write_inputs(args, **alt_args):
    all_args = args.copy()
    all_args.update(alt_args)
    scenario_data.write_tables(all_args)

# write regular scenario
write_inputs(args)

# tiny scenario for testing
write_inputs(args, inputs_dir='inputs_tiny', time_sample='tiny')

# non-worst-day (could be used to experiment with weighting, but wasn't)
# write_inputs(
#     args,
#     inputs_dir='inputs_non_worst',
#     time_sample=args['time_sample'].replace('+', '')
# )

# annual model for post-optimization evaluation (may be too big to solve)
write_inputs(
    args,
    inputs_dir='inputs_annual',
    time_sample=args['time_sample'].replace('_235_', '_1_') # .replace('_2', '')
)
