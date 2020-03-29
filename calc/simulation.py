from calc import calcfunc, ExecutionInterrupted
import numpy as np
import pandas as pd

from cythonsim import simc
from utils.perf import PerfCounter
from calc.datasets import get_population_for_area, get_physical_contacts_for_country
from datetime import date, timedelta


INTERVENTIONS = [
    ('test-all-with-symptoms', 'Testataan kaikki oirehtivat'),
    ('test-only-severe-symptoms', 'Testataan ainoastaan vakavasti oirehtivat'),
    ('test-with-contact-tracing', 'Testataan kaikki oirehtivat sekä määritetään tartuntaketjut'),
    ('limit-mobility', 'Rajoitetaan väestön liikkuvuutta', '%'),
    ('limit-mass-gatherings', 'Rajoitetaan kokoontumisia', 'kontaktia (max.)'),
    ('import-infections', 'Alueelle tulee infektioita', 'kpl'),
    ('import-infections-per-day', 'Alueelle tulee päivittäin uusia infektioita', 'kpl/pv'),
    ('build-new-hospital-beds', 'Rakennetaan uusia sairaansijoja', 'kpl'),
    ('build-new-icu-units', 'Rakennetaan uusia tehohoitopaikkoja', 'kpl'),
]


POP_ATTRS = [
    'susceptible', 'infected', 'all_detected', 'hospitalized',
    'dead', 'recovered',
]
STATE_ATTRS = [
    'exposed_per_day', 'hospital_beds', 'icu_units', 'tests_run_per_day', 'r', 'sim_time_ms',
]


@calcfunc(
    variables=[
        'simulation_days', 'interventions', 'start_date',
        'hospital_beds', 'icu_units',
        'p_infection', 'p_asymptomatic', 'p_critical', 'p_severe',
        'p_icu_death', 'p_hospital_death', 'p_hospital_death_no_beds',
        'p_icu_death_no_beds',
    ],
)
def simulate_individuals(variables, step_callback=None):
    pc = PerfCounter()

    df = get_population_for_area().sum(axis=1)
    ages = df.index.values
    counts = df.values
    avg_contacts_per_day = get_physical_contacts_for_country()
    hc_cap = (variables['hospital_beds'], variables['icu_units'])

    max_age = max(ages)
    age_counts = np.array(np.zeros(max_age + 1, dtype=np.int32))
    for age, count in zip(ages, counts):
        age_counts[age] = count

    pop = simc.Population(age_counts, list(avg_contacts_per_day.items()))
    hc = simc.HealthcareSystem(hc_cap[0], hc_cap[1])

    sevvar = variables['p_severe']
    sev_arr = [(age, sev / 100) for age, sev in sevvar]

    disease = simc.Disease(
        p_infection=variables['p_infection'] / 100,
        p_asymptomatic=variables['p_asymptomatic'] / 100,
        p_severe=sev_arr,
        p_critical=variables['p_critical'] / 100,
        p_hospital_death=variables['p_hospital_death'] / 100,
        p_icu_death=variables['p_icu_death'] / 100,
        p_hospital_death_no_beds=variables['p_hospital_death_no_beds'] / 100,
        p_icu_death_no_beds=variables['p_icu_death_no_beds'] / 100,
    )
    context = simc.Context(pop, age_counts, hc, disease, start_date=variables['start_date'])
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

    if False:
        import matplotlib.pyplot as plt
        sample = context.sample(0)
        s = pd.Series(sample)
        fig = plt.figure()
        print(s.mean())
        c = s.value_counts().sort_index()
        for a, b in c.iteritems():
            print('    (%d, %.2f),' % (a, b))
        plt.plot(c)
        plt.show()
        exit()

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


if __name__ == '__main__':
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
