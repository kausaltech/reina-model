import multiprocessing
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import numpy as np

from calc import ExecutionInterrupted, calcfunc
from calc.datasets import (
    get_contacts_for_country, get_initial_population_condition,
    get_population_for_area,
)
from common.interventions import Intervention, iv_tuple_to_obj, get_active_interventions
from cythonsim import model
from utils.perf import PerfCounter

POP_ATTRS = [
    'susceptible',
    'vaccinated',
    'infected',
    'detected',
    'all_detected',
    'in_ward',
    'in_icu',
    'dead',
    'non_hospital_deaths',
    'recovered',
    'all_infected',
    'new_infections',
]
EXPOSURES_ATTRS = [
    'exposures_home',
    'exposures_work',
    'exposures_school',
    'exposures_transport',
    'exposures_leisure',
    'exposures_other',
]
STATE_ATTRS = [
    'exposed_per_day',
    'available_hospital_beds',
    'available_icu_units',
    'total_icu_units',
    'ct_cases_per_day',
    'r',
    'mobility_limitation',
]


def create_disease_params(variables):
    kwargs = {}
    for key in model.DISEASE_PARAMS:
        val = variables[key]
        if key.startswith('p_') or key.startswith('ratio_'):
            if isinstance(val, list):
                val = [(age, sev / 100) for age, sev in val]
            else:
                val = val / 100
        kwargs[key] = val

    return kwargs


@calcfunc(funcs=[get_contacts_for_country])
def get_nr_of_contacts():
    df = get_contacts_for_country()
    df = df.drop(columns='place_type').groupby('participant_age').sum()
    s = df.sum(axis=1)
    idx = list(s.index.map(lambda x: tuple([int(y) for y in x.split('-')])))
    s.index = idx
    return s.sort_index()


@calcfunc(funcs=[get_contacts_for_country])
def get_contacts_per_day():
    df = get_contacts_for_country()
    df = pd.melt(
        df,
        id_vars=['place_type', 'participant_age'],
        var_name='contact_age',
        value_name='contacts'
    )
    df['participant_age'] = df['participant_age'].map(
        lambda x: tuple([int(y) for y in x.split('-')])
    )
    df['contact_age'] = df['contact_age'].map(lambda x: tuple([int(y) for y in x.split('-')]))

    df = pd.DataFrame(
        [
            (t.place_type, p, t.contact_age, t.contacts) for t in df.itertuples()
            for p in range(t.participant_age[0], t.participant_age[1] + 1)
        ],
        columns=['place_type', 'participant_age', 'contact_age', 'contacts']
    )
    # df = pd.DataFrame(
    #    [(t.place_type, t.participant_age, c, t.contacts / (t.contact_age[1] - t.contact_age[0] + 1)) for t in df.itertuples() for c in range(t.contact_age[0], t.contact_age[1] + 1)],
    #    columns=['place_type', 'participant_age', 'contact_age', 'contacts']
    # )

    return df


@calcfunc(
    variables=['max_age']
)
def make_age_groups(variables):
    age_map = []
    for i in range(0, variables['max_age'] + 1):
        grp = i // 10
        if grp >= 8:
            s = '80+'
        else:
            s = '%d–%d' % (grp * 10, grp * 10 + 9)
        age_map.append(s)

    return age_map


@calcfunc(
    funcs=[make_age_groups, get_population_for_area],
)
def get_age_grouped_population():
    ags = list(make_age_groups())
    df = get_population_for_area()
    df = pd.DataFrame(df.sum(axis=1), columns=['count'])
    df['ag'] = df.index.map(lambda x: ags[x])
    df = df.groupby('ag')['count'].sum()
    return df


@calcfunc(
    variables=list(model.DISEASE_PARAMS) + [
        'simulation_days',
        'interventions',
        'active_scenario',
        'scenarios',
        'start_date',
        'hospital_beds',
        'icu_units',
        'random_seed',
        'max_age',
        'imported_infection_ages',
    ],
    funcs=[get_contacts_per_day, get_population_for_area],
    filedeps=[model.__file__],
)
def simulate_individuals(variables, step_callback=None, callback_day_interval=1):
    pc = PerfCounter()

    age_structure = get_population_for_area().sum(axis=1)
    ipc = get_initial_population_condition()

    age_to_group = make_age_groups()

    age_groups = list(np.unique(age_to_group))
    pop_params = dict(
        age_structure=age_structure,
        contacts_per_day=get_contacts_per_day(),
        initial_population_condition=ipc,
        age_groups=dict(labels=age_groups, age_indices=[age_groups.index(x) for x in age_to_group]),
        imported_infection_ages=variables['imported_infection_ages'],
    )

    df = get_contacts_per_day()

    hc_params = dict(hospital_beds=variables['hospital_beds'], icu_units=variables['icu_units'])
    disease_params = create_disease_params(variables)
    context = model.Context(
        population_params=pop_params,
        healthcare_params=hc_params,
        disease_params=disease_params,
        start_date=variables['start_date'],
        random_seed=variables['random_seed']
    )
    start_date = date.fromisoformat(variables['start_date'])

    ivs = get_active_interventions(variables)
    for iv in ivs:
        context.add_intervention(iv)

    pc.measure()

    days = variables['simulation_days']

    date_index = pd.date_range(start_date, periods=days)
    df = pd.DataFrame(
        columns=POP_ATTRS + STATE_ATTRS + EXPOSURES_ATTRS + ['us_per_infected'],
        index=date_index,
    )

    ag_array = np.empty((days, len(POP_ATTRS), len(age_groups)), dtype='i')

    for day in range(days):
        s = context.generate_state()

        today_date = (start_date + timedelta(days=day)).isoformat()

        for idx, attr in enumerate(POP_ATTRS):
            ag_array[day, idx, :] = s[attr]

        rec = {attr: s[attr].sum() for attr in POP_ATTRS}

        for state_attr in STATE_ATTRS:
            rec[state_attr] = s[state_attr]

        for place, nr in s['daily_contacts'].items():
            key = 'exposures_%s' % place
            assert key in df.columns
            rec[key] = nr

        rec['us_per_infected'] = pc.measure() * 1000 / rec['infected'] if rec['infected'] else 0

        if False:
            st = '\n%-15s' % today_date
            for ag in age_groups:
                st += '%8s' % ag
            print(st)
            for attr in ('all_detected', 'in_ward', 'dead', 'cum_icu'):
                st = '%-15s' % attr
                t = s[attr].sum()
                for val in s[attr]:
                    st += '%8.2f' % ((val / t) * 100)
                print(st)

        if False:
            dead = context.get_population_stats('dead')
            all_infected = context.get_population_stats('all_infected')
            detected = context.get_population_stats('all_detected')

            age_groups = pd.interval_range(0, 80, freq=10, closed='left')
            age_groups = age_groups.append(pd.Index([pd.Interval(80, 100, closed='left')]))

            s = pd.Series(dead)
            dead_by_age = s.groupby(pd.cut(s.index, age_groups)).sum()
            dead_by_age.name = 'dead'

            s = pd.Series(all_infected)
            infected_by_age = s.groupby(pd.cut(s.index, age_groups)).sum()
            infected_by_age.scenario_name = 'infected'

            s = pd.Series(detected)
            detected_by_age = s.groupby(pd.cut(s.index, age_groups)).sum()
            detected_by_age.name = 'detected'

            print(dead_by_age / sum(dead_by_age) * 100)
            print(infected_by_age / sum(infected_by_age) * 100)
            print(detected_by_age / sum(detected_by_age) * 100)

            #zdf = pd.DataFrame(dead_by_age)
            #zdf['infected'] = infected_by_age
            #zdf['ifr'] = zdf.dead.divide(zdf.infected.replace(0, np.inf)) * 100
            #print(zdf)

        df.loc[today_date] = rec

        by_age_group = POP_ATTRS

        if step_callback is not None and (day % callback_day_interval == 0 or day == range(days) - 1):
            ret = step_callback(df)
            if not ret:
                raise ExecutionInterrupted()

        context.iterate()
        if False:
            import cProfile
            import pstats
            cProfile.runctx("context.iterate()", globals(), locals(), "profile.prof")
            s = pstats.Stats("profile.prof")
            s.strip_dirs().sort_stats("cumtime").print_stats()

    arr = ag_array.flatten()
    adf = pd.DataFrame(
        arr,
        index=pd.MultiIndex.from_product(
            [date_index, POP_ATTRS, age_groups],
            names=['date', 'attr', 'age_group']
        ),
        columns=['pop']
    )
    adf = adf.unstack('attr').unstack('age_group')
    adf.columns = adf.columns.droplevel()

    return df, adf


@calcfunc(
    variables=list(model.DISEASE_PARAMS) + [
        'sample_limit_mobility',
        'max_age',
    ],
    funcs=[get_contacts_for_country],
    filedeps=[model.__file__],
)
def sample_model_parameters(what, age, severity=None, variables=None):
    age_to_group = make_age_groups()
    max_age = variables['max_age']
    age_structure = pd.Series([1] * (max_age + 1), index=range(0, max_age + 1))
    age_groups = list(np.unique(age_to_group))
    pop_params = dict(
        age_structure=age_structure,
        contacts_per_day=get_contacts_per_day(),
        age_groups=dict(labels=age_groups, age_indices=[age_groups.index(x) for x in age_to_group])
    )
    hc_params = dict(hospital_beds=0, icu_units=0)
    disease_params = create_disease_params(variables)
    context = model.Context(
        population_params=pop_params,
        healthcare_params=hc_params,
        disease_params=disease_params,
        start_date='2020-01-01',
    )

    if variables['sample_limit_mobility'] != 0:
        context.apply_intervention('limit-mobility', variables['sample_limit_mobility'])

    samples = context.sample(what, age, severity)

    if what == 'infectiousness':
        s = pd.Series(index=samples['day'], data=samples['val'])
        s = s[s != 0].sort_index()
        return s

    s = pd.Series(samples)
    c = s.value_counts().sort_index()
    if what == 'symptom_severity':
        c.index = c.index.map(model.SEVERITY_TO_STR)

    if True:
        c /= c.sum()
        for a, b in c.iteritems():
            # print('    (%d, %.2f),' % (a, b))
            print('    (%s, %.2f),' % (a, b))
        import matplotlib.pyplot as plt
        fig = plt.figure()
        print('Mean: %f, median: %f' % (s.mean(), s.median()))
        plt.plot(c)
        plt.show()

    return c


@calcfunc(funcs=[simulate_individuals])
def simulate_monte_carlo(seed):
    from variables import allow_set_variable, get_variable, set_variable

    with allow_set_variable():
        set_variable('random_seed', seed)
        print(seed)
        df = simulate_individuals(skip_cache=True)
        df['run'] = seed

    return df


def run_monte_carlo(scenario_name):
    from scenarios import SCENARIOS
    from variables import allow_set_variable

    for scenario in SCENARIOS:
        if scenario.id == scenario_name:
            break
    else:
        raise Exception('Scenario not found')

    with allow_set_variable():
        scenario.apply()

    print(scenario.id)
    with multiprocessing.Pool(processes=8) as pool:
        dfs = pool.map(simulate_monte_carlo, range(1000))

    df = pd.concat(dfs)
    df.index.name = 'date'
    df = df.reset_index()
    df['scenario'] = scenario.id
    df.to_csv('reina_%s.csv' % scenario.id, index=False)

    return df


if __name__ == '__main__':
    if False:
        from variables import allow_set_variable, get_variable, set_variable
        with allow_set_variable():
            set_variable('simulation_days', 50)
            df = simulate_individuals()
            exit()
    if False:
        from scenarios import SCENARIOS
        for scenario in SCENARIOS:
            df = run_monte_carlo(scenario.id)
            print(df[df.date == df.date.max()])
            last = df[df.date == df.date.max()]
            print(last.dead.describe(percentiles=[.25, .5, .75]))
        exit()

    if False:
        sample_model_parameters('symptom_severity', 90)
        exit()

    if True:
        from variables import allow_set_variable, set_variable

        header = '%-10s' % 'day'
        state_attrs = STATE_ATTRS
        state_attrs.remove('available_hospital_beds')
        state_attrs.remove('available_icu_units')
        state_attrs.remove('total_icu_units')
        state_attrs.remove('mobility_limitation')
        state_attrs.remove('exposed_per_day')
        for attr in POP_ATTRS + state_attrs + ['exposures', 'us_per_infected']:
            header += '%15s' % attr
        print(header)

        def step_callback(df):
            rec = df.dropna().iloc[-1]

            s = '%-12s' % rec.name.date().isoformat()
            for attr in POP_ATTRS:
                s += '%15d' % rec[attr]

            for attr in ['ct_cases_per_day']:
                s += '%15d' % rec[attr]
            s += '%13.2f' % rec['r']
            contacts = 0
            for x in rec.index:
                if 'exposures_' in x:
                    contacts += rec[x]
            s += '%15d' % contacts
            if rec['infected']:
                s += '%13.2f' % rec['us_per_infected']
            print(s)
            return True

        with allow_set_variable():
            # set_variable('simulation_days', 465)

            def run_simulation():
                df, adf = simulate_individuals(step_callback=step_callback, skip_cache=True)
                print(adf)

            if False:
                import cProfile
                import pstats
                cProfile.runctx("run_simulation()", globals(), locals(), "profile.prof")
                s = pstats.Stats("profile.prof")
                s.strip_dirs().sort_stats("cumtime").print_stats()
            else:
                run_simulation()

    if False:
        from calc.datasets import get_detected_cases
        from variables import allow_set_variable, get_variable, set_variable

        with allow_set_variable():
            set_variable('simulation_days', 50)
            df = simulate_individuals(skip_cache=True)
            df = df[['all_infected', 'all_detected']]
            cdf = get_detected_cases()
            cdf.index = pd.DatetimeIndex(cdf.index)
            df['confirmed'] = cdf['confirmed']
            print(df)
