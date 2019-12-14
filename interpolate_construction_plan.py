"""
Create a schedule of capacity online in various tech groups:
- use tech groups from heco_outlook_2019
- start with minimum targets from heco_outlook_2019
- increase to match capacity online of each group in construction plan from
  solved optimization model
- increase in interim years in 2023-2044 to smooth step-ups in 2025, 2030, etc.
- take account of gen_build_predetermined in optimization model

Then advance BuildGen and BuildStorageEnergy proportionally from all matching
projects from next period year to satisfy the capacity target for interim years
(one by one). Be sure not to overbuild in any individual project (e.g., if
project is scheduled for reconstruction in a period year but we need more
capacity in an  earlier interim year).

Maybe do this as slices of project capacity that are online from date x through
date y: can slide the whole slice earlier as needed, but don't open a gap. Or
could be simpler: slide bottom n MW of project capacity forward; this applies to
the bottom n MW in all future years, even ...

To fill interim year:
- go through net capacity increases in next period (capacity built minus capacity retired > 0)
  - move some or all of the new build up to the current year
  - cascade to retirement year, moving up to the same amount of (re)build forward to close gap
  - keep cascading (with possibly diminishing block size) until end of study
  - this can only decrease, not increase, capacity online in a particular project
    in any future year
- repeat until interim year is filled

Will also need to slide replacement construction earlier to match actual retirement
year rather than next active period (for projects built in non-5 years, before
study or in 2022). i.e., step 1 is to start with build/operate schedule as given,
including automatic continuance of projects to 5-year mark, then shorten life
of the automatically continued projects to actual 30 year mark, cascading the
rebuilds into earlier years too.

(Set BuildStorageEnergy based on fixed energy/power ratio when needed, or maybe
just leave it blank.)

Note: we assume the following (add code to verify):
- construction plan is strictly increasing in the relevant groups
- relevant groups do not have discrete construction restrictions

Then add the BuildGen and BuildStorageEnergy values to
gen_build_predetermined.csv for each slice.
"""

import os, json, collections
import pandas as pd

base_output_path = lambda *args: os.path.join('outputs', *args)
base_input_path = lambda *args: os.path.join('inputs', *args)
new_input_path = lambda *args: os.path.join('inputs_annual', *args)

study_years = list(range(2020, 2046))
# could use actual years from study like below, but some code would need to be
# updated to find matching values from this list instead of using range()
# functions
# study_years = pd.read_csv(new_input_path('periods.csv'))['INVESTMENT_PERIOD'].to_list()

with open(base_output_path('heco_outlook.json')) as f:
    targets = json.load(f)

tech_group_power_targets = targets['tech_group_power_targets'] # existing projects are added later
tech_group_energy_targets = targets['tech_group_energy_targets']
techs_for_tech_group = targets['techs_for_tech_group']
tech_tech_group = targets['tech_tech_group']

storage_techs = [t for t in techs_for_tech_group.keys() if 'battery' in t.lower()]
assert sorted(storage_techs)==['Battery_Bulk', 'DistBattery'], \
    'storage techs are not as expected'
assert all(techs_for_tech_group[t]==[t] for t in storage_techs), \
    'Code needs to be updated for grouped storage technologies'

# get build and retirement schedule from outputs dir
# need to get periods, tech, max age, BuildGen, BuildStorageEnergy
periods = (
    pd.read_csv(base_input_path('periods.csv'))
    .rename({'INVESTMENT_PERIOD': 'period'}, axis=1)
    .set_index('period')
)
# TODO: use periods['period_start'] where needed instead of periods themselves
assert all(periods.index==periods['period_start']), \
    'New code is needed to use periods with labels that differ from period_start'

build_gen = (
    pd.read_csv(base_output_path('BuildGen.csv'))
    .rename({'GEN_BLD_YRS_1': 'gen_proj', 'GEN_BLD_YRS_2': 'bld_yr'}, axis=1)
    .set_index(['gen_proj', 'bld_yr'])['BuildGen']
)
build_storage = (
    pd.read_csv(base_output_path('BuildStorageEnergy.csv'))
    .rename({
        'STORAGE_GEN_BLD_YRS_1': 'gen_proj',
        'STORAGE_GEN_BLD_YRS_2': 'bld_yr'
    }, axis=1)
    .set_index(['gen_proj', 'bld_yr'])['BuildStorageEnergy']
)
gen_info = (
    pd.read_csv(base_input_path('generation_projects_info.csv'))
    .rename({'GENERATION_PROJECT': 'gen_proj'}, axis=1)
).set_index('gen_proj')
gen_info['tech_group'] = gen_info['gen_tech'].map(tech_tech_group)
gen_info = gen_info[gen_info['tech_group'].notna()]
existing_techs = (
    pd.read_csv(base_input_path('gen_build_predetermined.csv')) \
    .rename({'GENERATION_PROJECT': 'gen_proj'}, axis=1)
    .set_index('gen_proj')
    .join(gen_info, how='inner')
    .groupby(['build_year', 'tech_group'])['gen_predetermined_cap'].sum()
    .reset_index()
)
assert not any(existing_techs['tech_group'].str.contains('battery', case=False)), \
    "Need code to deal with predetermined battery construction"
gen_max_age = gen_info['gen_max_age']
gen_tech_group = gen_info['tech_group']
tech_group_max_age = (
    gen_info.groupby('tech_group')['gen_max_age'].agg(['min', 'max', 'mean'])
)
assert all(tech_group_max_age['min'] == tech_group_max_age['max']), \
    "Some technologies have mixed ages."
tech_group_max_age = tech_group_max_age['mean']

# append existing techs to tech_group_power_targets
tech_group_power_targets = (
    [[y, t, q] for i, y, t, q in existing_techs.itertuples()]
    + tech_group_power_targets
)

# 1. fill in all scheduled builds
# 2. check for extended retirements and slide forward
# 3. when to make the outer envelope?
# **** problem: if generation is expected to retire late and we move it to the
# correct year (which we must do, since the annual production cost model will
# not apply the life-extension), then we may create a capacity shortfall for a
# few years; for now we just assume there will be enough later builds to fill it.


# Calculate the capacity level for each tech_group

# set minimum capacity:
# early years:
# - existing capacity + HECO outlook (early build and replacements)
#   - may be more than Switch plan b/c early builds in HECO outlook get
#     scheduled into next study period
# later years:
# - Switch capacity plan

# HECO planned capacity, including pre-existing (may be a little earlier than
# Switch because Switch groups individual years into the following investment
# period)
heco_power_targets = (
    pd.DataFrame(index=techs_for_tech_group.keys(), columns=study_years)
    .fillna(0.0)
)
heco_energy_targets = (
    pd.DataFrame(index=storage_techs, columns=study_years)
    .fillna(0.0)
)
for heco_targets, group_targets in [
    (heco_power_targets, tech_group_power_targets),
    (heco_energy_targets, tech_group_energy_targets)
]:
    for year, tech_group, target in group_targets:
        # year, tech_group, target = tech_group_power_targets[0]
        first_year = max(year, study_years[0])
        last_year = min(
            year + tech_group_max_age[tech_group] - 1,
            study_years[-1]
        )
        heco_targets.loc[tech_group, first_year:last_year] += target

# Capacity built in optimization model (includes pre-existing capacity)
switch_power_targets = (
    pd.DataFrame(index=techs_for_tech_group.keys(), columns=study_years)
    .fillna(0.0)
)
switch_energy_targets = (
    pd.DataFrame(index=storage_techs, columns=study_years)
    .fillna(0.0)
)

for build_info, switch_targets in [
    (build_gen, switch_power_targets),
    (build_storage, switch_energy_targets)
]:
    for (gen, year), target in build_info.items():
        # (gen, year), target = list(build_gen.items())[3]
        # (gen, year), target = list(build_gen.items())[2]
        # (gen, year), target = list(build_gen.items())[6]
        if gen not in gen_info.index:
            # this gen is not in a tech_group, ignore it
            continue
        first_year = max(year, study_years[0])
        last_year = year + gen_max_age[gen] - 1
        # extend to next period or end of study, as Switch does
        if last_year < periods.index[-1]:
            last_year = periods.index[
                periods.index.get_loc(last_year + 1, method='backfill')
            ] - 1
        else:
            last_year = study_years[-1]
        switch_targets.loc[gen_tech_group[gen], first_year:last_year] += target

# use maximum target from each source as the active target
power_targets = pd.concat([switch_power_targets, heco_power_targets]).max(level=0)
energy_targets = pd.concat([switch_energy_targets, heco_energy_targets]).max(level=0)
# power_targets.loc['Battery_Bulk', :]
# energy_targets.loc['Battery_Bulk', :]
# switch_power_targets.loc['Battery_Bulk', :]
# switch_energy_targets.loc['Battery_Bulk', :]

# now need to smooth LargePV, OnshoreWind, OffshoreWind and Battery_Bulk
# (leave DistPV and DistBattery on current schedule).
# Then reschedule construction for these techs to match the power_targets.
# All other techs: follow construction plan given by Switch (with different
# construction plans or techs it might be necessary to shift reconstruction
# earlier for techs built in off-years, i.e., pre-existing or built in 2022,
# with retirement (and rebuilding) on off year)

# interpolate these targets after 2022 to avoid stairsteps
interpolate_tech_groups = ['LargePV', 'OnshoreWind', 'OffshoreWind', 'Battery_Bulk']
# meet these targets as-is, without interpolation
non_interpolate_tech_groups = ['DistPV', 'DistBattery']
# all others will be built as scheduled by the optimization model

# only consider relevant technologies
power_targets = power_targets.loc[
    interpolate_tech_groups + non_interpolate_tech_groups, :
]

for targets in [power_targets, energy_targets]:
    assert all(
        targets.loc[t, :].is_monotonic_increasing
        for t in targets.index
    ), "This script requires that all targets are increasing from year to year."

    # drop inter-period targets after 2022, then interpolate between periods
    period_2022 = periods.index.get_loc(2022)
    interp_groups = [g for g in interpolate_tech_groups if g in targets.index]
    for prev, current in zip(periods.index[period_2022:-1], periods.index[period_2022+1:]):
        if prev >= current - 1:
            continue # nothing to interpolate
        targets.loc[interp_groups, prev+1:current-1] = float('nan')
    for tech_group in interp_groups:
        targets.loc[tech_group, :] = targets.loc[tech_group, :].interpolate()

# adjust construction plans to meet targets
# To increase construction in early year:
# - go through net capacity increases in next period (capacity built minus capacity retired > 0)
#   - move some or all of the new build up to the current year
#   - cascade to retirement year, moving up to the same amount of (re)build forward to close gap
#   - keep cascading (with possibly diminishing block size) until end of study
#   - this can only decrease, not increase, capacity online in a particular project
#     in any future year
# - repeat until interim year is filled

# Find additions and retirements in Switch in each period, taking account of the
# life-extensions used in the optimization model.
# Then slide the end points forward to eliminate the life extensions (because
# those won't be used in the production cost model).
# Then slide excess capacity forward as needed to meet the targets.

def move_build(build, gen_proj, cap, from_year, to_year):
    """
    Move construction of cap MW of gen_proj from from_year to to_year,
    also moving any reconstructions of the same or less capacity currently
    scheduled for the retirement year.

    gen_proj = 'Oahu_Battery_Bulk'
    tech_group = 'Battery_Bulk'
    cap = 75
    from_year = 2020
    to_year = from_year - 3
    build = collections.defaultdict(lambda: collections.defaultdict(float))
    build[tech_group, from_year][gen_proj] = 100
    build[tech_group, from_year+gen_max_age[gen_proj]][gen_proj] = 50

    move_build(build, gen_proj, cap, from_year, to_year)

    defaultdict(<function __main__.<lambda>()>,
            {('Battery_Bulk', 2020): defaultdict(float,
                         {'Oahu_Battery_Bulk': 25}),
             ('Battery_Bulk', 2035): defaultdict(float,
                         {'Oahu_Battery_Bulk': 0}),
             ('Battery_Bulk', 2017): defaultdict(float,
                         {'Oahu_Battery_Bulk': 75.0}),
             ('Battery_Bulk', 2032): defaultdict(float,
                         {'Oahu_Battery_Bulk': 50.0})})

    # 2032 capacity will retire in 2047; shift to 2030 and get some rebuild
    move_build(build, gen_proj, 30, 2032, 2030)
    defaultdict(<function __main__.<lambda>()>,
                {('Battery_Bulk', 2020): defaultdict(float,
                             {'Oahu_Battery_Bulk': 25}),
                 ('Battery_Bulk', 2035): defaultdict(float,
                             {'Oahu_Battery_Bulk': 0}),
                 ('Battery_Bulk', 2017): defaultdict(float,
                             {'Oahu_Battery_Bulk': 75.0}),
                 ('Battery_Bulk', 2032): defaultdict(float,
                             {'Oahu_Battery_Bulk': 20.0}),
                 ('Battery_Bulk', 2030): defaultdict(float,
                             {'Oahu_Battery_Bulk': 30.0}),
                 ('Battery_Bulk', 2045): defaultdict(float,
                             {'Oahu_Battery_Bulk': 30.0})})
    """
    tech_group = gen_tech_group[gen_proj]
    retire_year = from_year + gen_max_age[gen_proj]
    new_retire_year = retire_year + (to_year - from_year)
    build[tech_group, from_year][gen_proj] -= cap
    build[tech_group, to_year][gen_proj] += cap
    if retire_year <= study_years[-1]:
        # how much of this was scheduled to be rebuilt in the original
        # retirement year?
        cascade_cap = min(cap, build[tech_group, retire_year][gen_proj])
        # move that amount up to the new retirement year
        move_build(build, gen_proj, cascade_cap, retire_year, new_retire_year)
    elif new_retire_year <= study_years[-1]:
        # reconstruct projects that have been moved earlier, creating gaps at
        # the end of the study
        build[tech_group, new_retire_year][gen_proj] += cap
    print(
        "Moved {} units of {} from {} to {}."
        .format(cap, gen_proj, from_year, to_year)
    )
    return build

def clean_build_dict(build):
    """ strip out zero-value records from the build dict """
    for k, d in list(build.items()):
        for g, q in list(d.items()):
            if not q:
                del d[g]
        if not d:
            del build[k]

# store by proj, but later need to find all projects in a particular
# tech_group that have capacity available in a particular year, so structure
# should be
# build = {(tech_group, year): {gen1: amt, gen2: amt, ...}, ...}
# retire = check build[tech_group, year-max_age][gen1]
# To update: set build[tech_group, year][gen1]
build_gen_dict = collections.defaultdict(lambda: collections.defaultdict(float))
build_storage_dict = collections.defaultdict(lambda: collections.defaultdict(float))
for (gen, year), cap in build_gen.items():
    if gen in gen_info.index and cap > 0:
        build_gen_dict[gen_tech_group[gen], year][gen] += cap
for (gen, year), cap in build_storage.items():
    if gen in gen_info.index and cap > 0:
        build_storage_dict[gen_tech_group[gen], year][gen] += cap

for build, build_targets in [
    (build_gen_dict, power_targets),
    (build_storage_dict, energy_targets)
]:
    # Find mid-period retirements and shift the subsequent reconstruction earlier
    to_fix = []  # tuple of gen_proj, capacity, old build date, new build date
    for prev_period, cur_period in zip(periods.index[:-1], periods.index[1:]):
        for gen in gen_info.index:
            # prev_period = 2040; cur_period = 2045; gen = 'Oahu_OnshoreWind_OnWind_Kahuku'; y = 2011
            age = gen_max_age[gen]
            tech_group = gen_tech_group[gen]
            # build years that could have had service extended to this period
            ext_build_years = list(range(prev_period - age + 1, cur_period - age))
            shiftable_cap = build[tech_group, cur_period][gen]
            for y in ext_build_years:
                if shiftable_cap == 0:
                    break # no possibility of shifting any more
                shift_cap = min(build[tech_group, y][gen], shiftable_cap)
                if shift_cap > 0:
                    # shift this much capacity from current period to correct rebuild year
                    to_fix.append((gen, shift_cap, cur_period, y+age))
                    # update tally of remaining shiftable capacity
                    shiftable_cap -= shift_cap
    clean_build_dict(build)

    # update build plan as needed (must start at latest build date so those get
    # attached to the previous build and then move earlier when that gets moved up)
    for gen, cap, from_year, to_year in sorted(to_fix, key=lambda x: x[2], reverse=True):
        move_build(build, gen, cap, from_year, to_year)

    # update to meet target...
    # tech_group = 'LargePV'; target_year = 2020; target_cap = 175.69; age = 30

    for tech_group, targets in build_targets.iterrows():
        age = tech_group_max_age[tech_group]
        for target_year, target_cap in targets.items():
            actual_cap = sum(
                sum(d.values())
                for (tg, y), d in build.items()
                if tg == tech_group and y <= target_year < y + age
            )
            if actual_cap > target_cap:
                print(
                    "WARNING: installed {} capacity in {} is "
                    "{}, which exceeds target of {}."
                    .format(tech_group, target_year, actual_cap, target_cap)
                )
            # elif actual_cap == target_cap:
            #     print(
            #         "installed {} capacity in {} is {}, which equals the target."
            #         .format(tech_group, target_year, actual_cap)
            #     )
            elif actual_cap < target_cap:
                print(
                    "installed {} capacity in {} is "
                    "{}, which is below target of {}."
                    .format(tech_group, target_year, actual_cap, target_cap)
                )

            # find later installations (not reconstructions) in this tech_group
            # and shift them earlier
            for year in range(target_year+1, study_years[-1]+1):
                for gen, cap in build[tech_group, year].items():
                    if actual_cap >= target_cap:
                        break  # finished adjusting
                    cap_added = cap - build[tech_group, year-gen_max_age[gen]][gen]
                    if cap_added > 0:
                        shift_cap = min(cap_added, target_cap-actual_cap)
                        move_build(build, gen, shift_cap, year, target_year)
                        actual_cap += shift_cap
    clean_build_dict(build)

# export as predetermined build schedule for an extensive model (could instead
# be done for multiple one-year models)
# set a predetermined value for all possible build years
build_costs = (
    pd.read_csv(new_input_path('gen_build_costs.csv'))
    .set_index(['GENERATION_PROJECT', 'build_year'])
)
gen_build_predetermined = (
    pd.read_csv(new_input_path('gen_build_predetermined.csv'))
    .set_index(['GENERATION_PROJECT', 'build_year'])
    .reindex(build_costs.index)  # set a value for every possible build year
    .fillna(0.0)
)
gen_build_predetermined['gen_predetermined_storage_energy_mwh'] = float('nan')
# start with original construction plan
for (gen, year), cap in build_gen.items():
    gen_build_predetermined.loc[(gen, year), 'gen_predetermined_cap'] = cap
for (gen, year), cap in build_storage.items():
    gen_build_predetermined.loc[(gen, year), 'gen_predetermined_storage_energy_mwh'] = cap
# update interpolated projects
for gen, tech_group in gen_tech_group.items():
    for year in study_years:
        cap = build_gen_dict[tech_group, year][gen]
        gen_build_predetermined.loc[(gen, year), 'gen_predetermined_cap'] = cap
        if tech_group in storage_techs:
            gen_build_predetermined.loc[(gen, year), 'gen_predetermined_storage_energy_mwh'] \
            = build_storage_dict[tech_group, year][gen]

# gen_build_predetermined.loc['Oahu_Battery_Bulk', :]
# build_storage['Oahu_Battery_Bulk']
# build_gen['Oahu_Battery_Bulk']

# check that we're actually hitting the targets
power_online = power_targets.copy()
power_online.loc[:, :] = 0.0
energy_online = energy_targets.copy()
energy_online.loc[:, :] = 0.0
for (gen, year), (power_cap, energy_cap) in gen_build_predetermined.iterrows():
    tech_group = gen_tech_group.get(gen, None)
    if tech_group in power_online.index:
        power_online.loc[tech_group, year:year+gen_max_age[gen]-1] += power_cap
    if tech_group in energy_online.index:
        energy_online.loc[tech_group, year:year+gen_max_age[gen]-1] += energy_cap
assert (power_online - power_targets).abs().max().max() < 0.001, "some targets were missed"
assert (energy_online - energy_targets).abs().max().max() < 0.001, "some targets were missed"

# # check that there's never excess development
# gen_cap_online = pd.DataFrame(index=gen_info.index, columns=study_years).fillna(0.0)
# for (gen, year), (power_cap, energy_cap) in gen_build_predetermined.iterrows():
#     if gen in gen_cap_online.index:
#         gen_cap_online.loc[gen, year:year+gen_max_age[gen]-1] += power_cap
# assert gen_cap_online.sub(gen_info['gen_capacity_limit_mw'], axis=0).max().max() < 0.000000001, "some capacity limits were exceeded"
# max is 5.6e-14, which should be within rounding error

# trim any minor excess development; report major errors
for (gen, year), (power_cap, energy_cap) in gen_build_predetermined.iterrows():
    if gen in gen_max_age:
        cap_online = (
            gen_build_predetermined
            .loc[(gen, slice(year-gen_max_age[gen]+1, year)), 'gen_predetermined_cap']
            .sum()
        )
        max_cap = gen_info.loc[gen, 'gen_capacity_limit_mw']
        excess_cap = cap_online - max_cap
        if excess_cap > 0.00001:
            raise ValueError(
                'Excess capacity scheduled for {} in {}: {} > {}.'
                .format(gen, year, cap_online, max_cap)
            )
        elif excess_cap > 0:
            # make a small adjustment
            gen_build_predetermined.loc[(gen, year), 'gen_predetermined_cap'] \
                -= excess_cap
            print(
                'Reduced construction of {} in {} from {} to {}.'
                .format(gen, year, power_cap, power_cap-excess_cap)
            )

gen_build_predetermined.to_csv(
    new_input_path('gen_build_predetermined_adjusted.csv'),
    na_rep='.'
)
