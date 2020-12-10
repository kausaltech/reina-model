import multiprocessing
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from cythonsim import model
from flask_babel import lazy_gettext as _

from calc import ExecutionInterrupted, calcfunc
from calc.datasets import (get_contacts_for_country,
                           get_initial_population_condition,
                           get_population_for_area)
from utils.perf import PerfCounter


@dataclass
class Intervention:
    name: str
    label: str
    unit: str = None


INTERVENTIONS = [
    Intervention('test-all-with-symptoms', _('Test all with symptoms')),
    Intervention('test-only-severe-symptoms', _('Test people only with severe symptoms, given percentage of mild cases are detected'), '%'),
    Intervention('test-with-contact-tracing', _('Test all with symptoms and perform contact tracing with given accuracy'), '%'),
    Intervention('limit-mobility', _('Limit population mobility'), '%'),
    # Intervention('limit-mass-gatherings', _('Limit mass gatherings'), _('max. contacts')),
    Intervention('import-infections', _('Import infections'), _('infections')),
    # Intervention('import-infections-per-day', _('Import new infections daily'), _('infections/day')),
    Intervention('build-new-hospital-beds', _('Build new hospital beds'), _('beds')),
    Intervention('build-new-icu-units', _('Build new ICU units'), _('units')),
]


POP_ATTRS = [
    'susceptible', 'infected', 'all_detected', 'hospitalized', 'in_icu',
    'dead', 'recovered', 'all_infected',
]
STATE_ATTRS = [
    'exposed_per_day', 'available_hospital_beds', 'available_icu_units',
    'total_icu_units', 'tests_run_per_day', 'r', 'mobility_limitation',
]


def create_disease_params(variables):
    kwargs = {}
    for key in model.DISEASE_PARAMS:
        val = variables[key]
        if key in ('p_infection', 'p_severe', 'p_critical', 'p_icu_death'):
            val = [(age, sev / 100) for age, sev in val]
        elif key.startswith('p_') or key.startswith('ratio_'):
            val = val / 100
        kwargs[key] = val

    return kwargs


@calcfunc(
    funcs=[get_contacts_for_country]
)
def get_nr_of_contacts():
    df = get_contacts_for_country()
    df = df.drop(columns='place_type').groupby('participant_age').sum()
    s = df.sum(axis=1)
    idx = list(s.index.map(lambda x: tuple([int(y) for y in x.split('-')])))
    s.index = idx
    return s.sort_index()


@calcfunc(
    funcs=[get_contacts_for_country]
)
def get_contacts_per_day():
    df = get_contacts_for_country()
    df = pd.melt(df, id_vars=['place_type', 'participant_age'], var_name='contact_age', value_name='contacts')
    df['participant_age'] = df['participant_age'].map(lambda x: tuple([int(y) for y in x.split('-')]))
    df['contact_age'] = df['contact_age'].map(lambda x: tuple([int(y) for y in x.split('-')]))

    return df


@calcfunc(
    variables=list(model.DISEASE_PARAMS) + [
        'simulation_days', 'interventions', 'start_date',
        'hospital_beds', 'icu_units',
        'random_seed',
    ],
    funcs=[get_contacts_per_day, get_population_for_area],
    filedeps=[model.__file__],
)
def simulate_individuals(variables, step_callback=None):
    pc = PerfCounter()

    age_structure = get_population_for_area().sum(axis=1)
    ipc = get_initial_population_condition()
    pop_params = dict(
        age_structure=age_structure,
        contacts_per_day=get_contacts_per_day(),
        initial_population_condition=ipc
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

    for iv in variables['interventions']:
        d = (date.fromisoformat(iv[1]) - start_date).days
        if len(iv) > 2:
            val = iv[2]
        else:
            val = 0
        context.add_intervention(d, iv[0], val)
    pc.measure()

    days = variables['simulation_days']

    df = pd.DataFrame(
        columns=POP_ATTRS + STATE_ATTRS + ['us_per_infected'],
        index=pd.date_range(start_date, periods=days)
    )
    for day in range(days):
        s = context.generate_state()

        rec = {attr: sum(s[attr]) for attr in POP_ATTRS}
        for state_attr in STATE_ATTRS:
            rec[state_attr] = s[state_attr]

        rec['us_per_infected'] = pc.measure() * 1000 / rec['infected'] if rec['infected'] else 0

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

        d = start_date + timedelta(days=day)
        df.loc[d.isoformat()] = rec

        if step_callback is not None:
            ret = step_callback(df)
            if not ret:
                raise ExecutionInterrupted()

        context.iterate()
        if False:
            import cProfile
            import pstats
            cProfile.runctx("context.iterate()", globals(), locals(), "profile.prof")
            s = pstats.Stats("profile.prof")
            s.strip_dirs().sort_stats("time").print_stats()

    return df


@calcfunc(
    variables=list(model.DISEASE_PARAMS) + [
        'sample_limit_mobility', 'max_age',
    ],
    funcs=[get_contacts_for_country],
    filedeps=[model.__file__],
)
def sample_model_parameters(what, age, severity=None, variables=None):
    max_age = variables['max_age']
    age_structure = pd.Series([1] * (max_age + 1), index=range(0, max_age + 1))
    pop_params = dict(
        age_structure=age_structure,
        contacts_per_day=get_contacts_per_day(),
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

    if False:
        # c /= c.sum()
        for a, b in c.iteritems():
            print('    (%d, %.2f),' % (a, b))
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
        sample_model_parameters('contacts_per_day', 50)
        exit()

    if True:
        from variables import allow_set_variable, set_variable

        header = '%-12s' % 'day'
        for attr in POP_ATTRS + STATE_ATTRS + ['us_per_infected']:
            header += '%15s' % attr
        print(header)

        def step_callback(df):
            rec = df.dropna().iloc[-1]

            s = '%-12s' % rec.name.date().isoformat()
            for attr in POP_ATTRS:
                s += '%15d' % rec[attr]

            for attr in ['exposed_per_day', 'available_hospital_beds', 'available_icu_units', 'tests_run_per_day']:
                s += '%15d' % rec[attr]
            s += '%13.2f' % rec['r']
            if rec['infected']:
                s += '%13.2f' % rec['us_per_infected']
            print(s)
            return True

        with allow_set_variable():
            set_variable('simulation_days', 180)
            simulate_individuals(step_callback=step_callback, skip_cache=True)

    if False:
        from variables import allow_set_variable, get_variable, set_variable

        from calc.datasets import get_detected_cases

        with allow_set_variable():
            set_variable('simulation_days', 50)
            df = simulate_individuals(skip_cache=True)
            df = df[['all_infected', 'all_detected']]
            cdf = get_detected_cases()
            cdf.index = pd.DatetimeIndex(cdf.index)
            df['confirmed'] = cdf['confirmed']
            print(df)
