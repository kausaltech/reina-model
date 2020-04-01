from dataclasses import dataclass
from calc import calcfunc, ExecutionInterrupted
import numpy as np
import pandas as pd
from flask_babel import lazy_gettext as _

from cythonsim import model
from utils.perf import PerfCounter
from calc.datasets import get_population_for_area, get_contacts_for_country
from datetime import date, timedelta


@dataclass
class Intervention:
    name: str
    label: str
    unit: str = None


INTERVENTIONS = [
    Intervention('test-all-with-symptoms', _('Test all with symptoms')),
    Intervention('test-only-severe-symptoms', _('Test people only with severe symptoms')),
    Intervention('test-with-contact-tracing', _('Test all with symptoms and perform contact tracing')),
    Intervention('limit-mobility', _('Limit population mobility'), '%'),
    Intervention('limit-mass-gatherings', _('Limit mass gatherings'), _('max. contacts')),
    Intervention('import-infections', _('Import infections'), _('infections')),
    Intervention('import-infections-per-day', _('Import new infections daily'), _('infections/day')),
    Intervention('build-new-hospital-beds', _('Build new hospital beds'), _('beds')),
    Intervention('build-new-icu-units', _('Build new ICU units'), _('units')),
]


POP_ATTRS = [
    'susceptible', 'infected', 'all_detected', 'hospitalized', 'in_icu',
    'dead', 'recovered', 'all_infected',
]
STATE_ATTRS = [
    'exposed_per_day', 'hospital_beds', 'icu_units', 'tests_run_per_day', 'r', 'sim_time_ms',
]


def create_disease(variables):
    kwargs = {}
    for key in model.DISEASE_PARAMS:
        val = variables[key]
        if key in ('p_severe', 'p_critical'):
            val = [(age, sev / 100) for age, sev in val]
        elif key.startswith('p_'):
            val = val / 100
        kwargs[key] = val

    disease = model.Disease.from_variables(kwargs)
    return disease


@calcfunc(
    variables=list(model.DISEASE_PARAMS) + [
        'simulation_days', 'interventions', 'start_date',
        'hospital_beds', 'icu_units', 'p_detected_anyway',
    ],
    funcs=[get_contacts_for_country]
)
def simulate_individuals(variables, step_callback=None):
    pc = PerfCounter()

    df = get_population_for_area().sum(axis=1)
    ages = df.index.values
    counts = df.values
    avg_contacts_per_day = get_contacts_for_country()
    hc_cap = (variables['hospital_beds'], variables['icu_units'])

    max_age = max(ages)
    age_counts = np.array(np.zeros(max_age + 1, dtype=np.int32))
    for age, count in zip(ages, counts):
        age_counts[age] = count

    pop = model.Population(age_counts, list(avg_contacts_per_day.items()))
    hc = model.HealthcareSystem(
        beds=hc_cap[0], icu_units=hc_cap[1],
        p_detected_anyway=variables['p_detected_anyway'] / 100
    )
    disease = create_disease(variables)
    context = model.Context(pop, hc, disease, start_date=variables['start_date'])
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
        columns=POP_ATTRS + STATE_ATTRS,
        index=pd.date_range(start_date, periods=days)
    )

    for day in range(days):
        state = context.generate_state()

        rec = {attr: sum(getattr(state, attr)) for attr in POP_ATTRS}
        rec['hospital_beds'] = state.available_hospital_beds
        rec['icu_units'] = state.available_icu_units
        rec['r'] = state.r
        rec['exposed_per_day'] = state.exposed_per_day
        rec['tests_run_per_day'] = state.tests_run_per_day
        rec['sim_time_ms'] = pc.measure()

        d = start_date + timedelta(days=day)
        df.loc[d] = rec

        if step_callback is not None:
            ret = step_callback(df)
            if not ret:
                raise ExecutionInterrupted()

        context.iterate()
        # cProfile.runctx("context.iterate()", globals(), locals(), "profile.prof")
        # s = pstats.Stats("profile.prof")
        # s.strip_dirs().sort_stats("time").print_stats()

    return df


@calcfunc(
    variables=list(model.DISEASE_PARAMS) + [
        'p_detected_anyway',
    ],
    funcs=[get_contacts_for_country]
)
def sample_model_parameters(what, age, variables):
    avg_contacts_per_day = get_contacts_for_country()
    age_counts = [1]
    pop = model.Population(age_counts, list(avg_contacts_per_day.items()))
    hc = model.HealthcareSystem(
        beds=0, icu_units=0,
        p_detected_anyway=variables['p_detected_anyway'] / 100
    )
    disease = create_disease(variables)
    context = model.Context(pop, hc, disease, start_date='2020-01-01')

    samples = context.sample(what, age)

    if what == 'infectiousness':
        s = pd.Series(index=samples['day'], data=samples['val'])
        s = s[s != 0].sort_index()
        return s

    s = pd.Series(samples)
    c = s.value_counts().sort_index()
    if what == 'symptom_severity':
        c.index = c.index.map(model.SEVERITY_TO_STR)

    if False:
        for a, b in c.iteritems():
            print('    (%d, %.2f),' % (a, b))
        import matplotlib.pyplot as plt
        fig = plt.figure()
        print(s.mean())
        plt.plot(c)
        plt.show()

    return c


if __name__ == '__main__':
    #sample_model_parameters('icu_period', 50)
    #exit()

    header = '%-12s' % 'day'
    for attr in POP_ATTRS + STATE_ATTRS:
        header += '%15s' % attr
    print(header)

    def step_callback(df):
        rec = df.dropna().iloc[-1]

        s = '%-12s' % rec.name.date().isoformat()
        for attr in POP_ATTRS:
            s += '%15d' % rec[attr]

        for attr in ['exposed_per_day', 'hospital_beds', 'icu_units', 'tests_run_per_day']:
            s += '%15d' % rec[attr]
        s += '%13.2f' % rec['r']
        if rec['infected']:
            s += '%13.2f' % (rec['sim_time_ms'] * 1000 / rec['infected'])
        print(s)
        return True

    simulate_individuals(step_callback=step_callback, skip_cache=True)
