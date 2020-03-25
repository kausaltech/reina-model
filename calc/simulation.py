from collections import namedtuple
import numpy as np
import pandas as pd

from . import calcfunc
from enum import IntEnum, auto
from calc.datasets import get_population_for_area, get_physical_contacts_for_country
from utils.perf import PerfCounter
from variables import set_variable, get_variable
from datetime import date, timedelta
import numba as nb


class SymptomSeverity(IntEnum):
    ASYMPTOMATIC = auto()
    MILD = auto()
    SEVERE = auto()
    CRITICAL = auto()


class PersonState(IntEnum):
    SUSCEPTIBLE = auto()
    INCUBATION = auto()
    ILLNESS = auto()
    HOSPITALIZED = auto()
    IN_ICU = auto()
    RECOVERED = auto()
    DEAD = auto()


@nb.jitclass([
    ('age', nb.int8),
    ('has_immunity', nb.int8),
    ('is_infected', nb.int8),
    ('was_detected', nb.int8),
    ('other_people_infected', nb.int16),
    ('symptom_severity', nb.int8),
    ('days_left', nb.int8),
    ('day_of_illness', nb.int8),
    ('state', nb.int8),
])
class Person:
    def __init__(self, age):
        self.age = age
        self.is_infected = 0
        self.was_detected = 0
        self.has_immunity = 0
        self.days_left = 0
        self.day_of_illness = 0
        self.other_people_infected = 0
        self.symptom_severity = SymptomSeverity.ASYMPTOMATIC
        self.state = PersonState.SUSCEPTIBLE

    def expose(self, context, source=None):
        if self.is_infected or self.has_immunity:
            return False
        if context.disease.did_infect(self, context, source):
            self.infect(context)
            return True
        return False

    def infect(self, context):
        self.state = PersonState.INCUBATION
        self.days_left = context.disease.get_incubation_days(self, context)
        self.is_infected = 1
        context.pop.infect(self)

    def detect(self, context):
        self.was_detected = 1
        context.pop.detect(self)

    def recover(self, context):
        self.state = PersonState.RECOVERED
        self.is_infected = 0
        self.has_immunity = 1
        context.pop.recover(self)

    def hospitalize(self, context):
        if self.symptom_severity == SymptomSeverity.CRITICAL:
            if not context.hc.to_icu():
                # If no ICU units are available, ...
                self.die(context)
                return
            self.state = PersonState.IN_ICU
            self.days_left = context.disease.get_icu_days(self, context)
        else:
            if not context.hc.hospitalize():
                # If no beds are available, 20 % chance to die.
                if context.random.chance(0.20):
                    self.die(context)
                else:
                    self.recover(context)
                return
            self.state = PersonState.HOSPITALIZED
            self.days_left = context.disease.get_hospitalisation_days(self, context)

        context.pop.hospitalize(self)

    def release_from_hospital(self, context):
        context.pop.release_from_hospital(self)
        if self.state == PersonState.IN_ICU:
            death = context.disease.dies_in_hospital(self, context, in_icu=True)
            context.hc.release_from_icu()
        else:
            death = context.disease.dies_in_hospital(self, context, in_icu=False)
            context.hc.release()

        if death:
            self.die(context)
        else:
            self.recover(context)

    def die(self, context):
        self.is_infected = 0
        # This is a way to get long-lasting immunity.
        self.has_immunity = 1
        self.state = PersonState.DEAD
        context.pop.die(self)

    def expose_others(self, context, nr_contacts):
        people = context.people
        for i in range(nr_contacts):
            exposee_idx = int(context.random.get() * len(people))
            if people[exposee_idx].expose(context, self):
                self.other_people_infected += 1

    def advance(self, context):
        # Every day there is a possibility for the case to be detected.
        if not self.was_detected and context.hc.is_detected(self, context):
            self.detect(context)

        if self.state == PersonState.INCUBATION:
            people_exposed = context.disease.people_exposed(self, context)
            if people_exposed:
                self.expose_others(context, people_exposed)

            self.days_left -= 1
            if self.days_left == 0:
                self.state = PersonState.ILLNESS
                self.symptom_severity = context.disease.get_symptom_severity(self, context)
                self.days_left = context.disease.get_illness_days(self, context)
        elif self.state == PersonState.ILLNESS:
            people_exposed = context.disease.people_exposed(self, context)
            if people_exposed:
                self.expose_others(context, people_exposed)

            self.day_of_illness += 1
            self.days_left -= 1
            if self.days_left == 0:
                # People with mild symptoms recover after the symptomatic period
                # and people with more severe symptoms are hospitalized.
                if self.symptom_severity in (SymptomSeverity.SEVERE, SymptomSeverity.CRITICAL):
                    self.hospitalize(context)
                else:
                    self.recover(context)
        elif self.state in (PersonState.HOSPITALIZED, PersonState.IN_ICU):
            self.days_left -= 1
            if self.days_left == 0:
                self.release_from_hospital(context)


class TestingMode(IntEnum):
    NO_TESTING = auto()
    ALL_WITH_SYMPTOMS = auto()
    ONLY_SEVERE_SYMPTOMS = auto()


@nb.jitclass([
    ('beds', nb.int32),
    ('icu_units', nb.int32),
    ('available_beds', nb.int32),
    ('available_icu_units', nb.int32),
    ('testing_mode', nb.int32),
])
class HealthcareSystem:
    def __init__(self, beds, icu_units):
        self.beds = beds
        self.icu_units = icu_units
        self.available_beds = beds
        self.available_icu_units = icu_units
        self.testing_mode = TestingMode.NO_TESTING

    def hospitalize(self):
        if self.available_beds == 0:
            return False
        self.available_beds -= 1
        return True

    def set_testing_mode(self, mode):
        self.testing_mode = mode

    def is_detected(self, person, context):
        if self.testing_mode == TestingMode.NO_TESTING:
            raise Exception()
            return False

        if person.state == PersonState.INCUBATION:
            return False

        if person.state == PersonState.ILLNESS:
            if self.testing_mode == TestingMode.ALL_WITH_SYMPTOMS:
                if person.symptom_severity == SymptomSeverity.ASYMPTOMATIC:
                    return False

                return True

            if self.testing_mode == TestingMode.ONLY_SEVERE_SYMPTOMS:
                if person.symptom_severity in (SymptomSeverity.CRITICAL, SymptomSeverity.SEVERE):
                    return True
                elif context.random.chance(0.02):
                    # Small percentage of mild cases are detected anyway
                    # (such as healthcare workers).
                    return True
                else:
                    return False

            raise Exception()

        if person.state in (PersonState.HOSPITALIZED, PersonState.IN_ICU):
            return True
        return False

    def release(self):
        self.available_beds += 1
        assert self.available_beds <= self.beds

    def to_icu(self):
        if self.available_icu_units == 0:
            return False
        self.available_icu_units -= 1
        return True

    def release_from_icu(self):
        self.available_icu_units += 1
        assert self.available_icu_units <= self.icu_units


# Overall chance to become infected after being exposed.
# This is modified by viral load of the infector, which
# depends on the day of the illness.
INFECTION_CHANCE = 0.30

# Chance to have mild symptoms (not be fully asymptomatic)
MILD_CHANCE = 0.50

# Ratio of all infected people that require hospitalization
# (more than mild symptoms)
SEVERE_CHANCE_BY_AGE = (
    (0, 0.0),
    (10, 0.04),
    (20, 1.1),
    (30, 3.4),
    (40, 4.3),
    (50, 8.2),
    (60, 11.8),
    (70, 16.6),
    (80, 18.4)
)

# Ratio of people that are hospitalized and will also need
# ICU care.
ICU_CHANCE = 0.25


# The infectiousness profile of the pathogen over time.
# Day 0 is the symptom onset day.
# Source: https://www.medrxiv.org/content/10.1101/2020.03.15.20036707v2.full.pdf
INFECTIOUSNESS_OVER_TIME = (
    (-2, 0.12),
    (-1, 0.29),
    (0, 0.27),
    (1, 0.07),
    (2, 0.05),
    (3, 0.04),
    (4, 0.03),
    (5, 0.02),
    (6, 0.02),
    (7, 0.01),
    (8, 0.01),
    (9, 0.01),
    (10, 0.01),
)


@nb.jitclass([])
class Disease:
    def __init__(self):
        pass

    def get_source_infectiousness(self, source):
        if source.state == PersonState.INCUBATION:
            day = -source.days_left
        elif source.state == PersonState.ILLNESS:
            day = source.day_of_illness
        else:
            raise Exception()

        for illness_day, chance in INFECTIOUSNESS_OVER_TIME:
            if day < illness_day:
                return 0
            if day == illness_day:
                return INFECTION_CHANCE * chance
        return 0

    def did_infect(self, person, context, source):
        chance = INFECTION_CHANCE
        if source.symptom_severity == SymptomSeverity.ASYMPTOMATIC:
            chance /= 2.0
        return context.random.chance(chance)

    def people_exposed(self, person, context):
        if person.state == PersonState.INCUBATION:
            # Infectious one day before onset of symptoms
            if person.days_left == 1:
                return context.pop.contacts_per_day(person, context)
            else:
                return 0
        elif person.state == PersonState.ILLNESS:
            # Detected people are quarantined
            if person.was_detected:
                return 0

            # Asymptomatic people infect others without knowing it
            if person.symptom_severity == SymptomSeverity.ASYMPTOMATIC:
                return context.pop.contacts_per_day(person, context)
            else:
                # People with mild or more severe symptoms restrict their movement
                return context.pop.contacts_per_day(person, context, factor=0.5, limit=5)

        raise Exception()

    def dies_in_hospital(self, person, context, in_icu):
        if in_icu:
            return context.random.chance(0.20)
        else:
            return context.random.chance(0.10)

    def get_incubation_days(self, person, context):
        # lognormal distribution, mode on 5 days
        # Source: https://www.medrxiv.org/content/10.1101/2020.03.15.20036707v2.full.pdf
        days = 1 + int(np.random.lognormal(1.0, 0.5) * 4)
        if days > 14:
            days = 14
        return days

    def get_illness_days(self, person, context):
        return 7

    def get_hospitalisation_days(self, person, context):
        return 14

    def get_icu_days(self, person, context):
        return 21

    def get_symptom_severity(self, person, context):
        val = context.random.get()
        for age, severe_chance in SEVERE_CHANCE_BY_AGE:
            if person.age < age + 10:
                break

        severe_chance /= 100
        if val < severe_chance * ICU_CHANCE:
            return SymptomSeverity.CRITICAL
        if val < severe_chance:
            return SymptomSeverity.SEVERE
        if val < MILD_CHANCE:
            return SymptomSeverity.MILD
        return SymptomSeverity.ASYMPTOMATIC


ModelState = namedtuple('ModelState', [
    'susceptible', 'infected', 'detected', 'all_detected',
    'hospitalized', 'dead', 'recovered',
    'available_hospital_beds', 'available_icu_units',
    'r'
])


@nb.jitclass([
    ('infected', nb.int32[:]),
    ('detected', nb.int32[:]),
    ('all_detected', nb.int32[:]),
    ('hospitalized', nb.int32[:]),
    ('dead', nb.int32[:]),
    ('susceptible', nb.int32[:]),
    ('recovered', nb.int32[:]),
    ('avg_contacts_per_day', nb.float32[:]),
    ('limit_mass_gatherings', nb.int32),
    ('population_mobility_factor', nb.float32),
])
class Population:
    def __init__(self, age_counts, avg_contacts_per_day):
        nr_ages = age_counts.size
        self.susceptible = age_counts.copy()
        # np.array(age_counts, dtype=np.int32)
        self.infected = np.zeros(nr_ages, dtype=np.int32)
        self.detected = np.zeros(nr_ages, dtype=np.int32)
        self.all_detected = np.zeros(nr_ages, dtype=np.int32)
        self.recovered = np.zeros(nr_ages, dtype=np.int32)
        self.hospitalized = np.zeros(nr_ages, dtype=np.int32)
        self.dead = np.zeros(nr_ages, dtype=np.int32)
        self.avg_contacts_per_day = avg_contacts_per_day.copy()
        self.limit_mass_gatherings = 0
        self.population_mobility_factor = 1.0

    def contacts_per_day(self, person, context, factor=1.0, limit=None):
        # Contacts per day follows a lognormal distribution with
        # mean at `avg_contacts_per_day`.
        factor *= self.population_mobility_factor
        contacts = int(np.random.lognormal() * self.avg_contacts_per_day[person.age] * factor)
        if self.limit_mass_gatherings:
            if contacts > self.limit_mass_gatherings:
                contacts = self.limit_mass_gatherings
        if limit is not None and contacts > limit:
            contacts = limit
        return contacts

    def infect(self, person):
        self.susceptible[person.age] -= 1
        self.infected[person.age] += 1

    def recover(self, person):
        self.infected[person.age] -= 1
        self.recovered[person.age] += 1
        if person.was_detected:
            self.detected[person.age] -= 1

    def detect(self, person):
        self.detected[person.age] += 1
        self.all_detected[person.age] += 1

    def hospitalize(self, person):
        self.hospitalized[person.age] += 1

    def release_from_hospital(self, person):
        self.hospitalized[person.age] -= 1

    def die(self, person):
        self.infected[person.age] -= 1
        self.dead[person.age] += 1
        if person.was_detected:
            self.detected[person.age] -= 1


@nb.jitclass([
    ('idx', nb.int32),
    ('data', nb.float64[:]),
])
class RandomPool:
    def __init__(self):
        np.random.seed(1234)

    def get(self):
        return np.random.random()

    def chance(self, p):
        val = self.get()
        return val < p


@nb.jitclass([
    ('day', nb.int32),
    ('name', nb.types.string),
    ('value', nb.int32),
])
class Intervention:
    def __init__(self, day, name, value):
        self.day = day
        self.name = name
        self.value = value


@nb.jitclass([
    ('pop', Population.class_type.instance_type),
    ('hc', HealthcareSystem.class_type.instance_type),
    ('disease', Disease.class_type.instance_type),
    ('random', RandomPool.class_type.instance_type),
    ('day', nb.int32),
    ('people', nb.types.ListType(Person.class_type.instance_type)),
    ('interventions', nb.types.ListType(Intervention.class_type.instance_type)),
    ('start_date', nb.types.string)
])
class Context:
    def __init__(self, pop, people, hc, disease, start_date):
        self.pop = pop
        self.people = people
        self.hc = hc
        self.disease = disease
        self.random = RandomPool()
        self.start_date = start_date
        self.day = 0

    def _calculate_r(self):
        total_infectors = 0
        total_infections = 0
        for person in self.people:
            if not person.is_infected or person.state != PersonState.ILLNESS:
                continue

            total_infectors += 1
            total_infections += person.other_people_infected

        if not total_infectors:
            return 0

        return total_infections / total_infectors

    def generate_state(self):
        p = self.pop
        hc = self.hc
        s = ModelState(
            infected=p.infected, susceptible=p.susceptible,
            recovered=p.recovered, hospitalized=p.hospitalized,
            detected=p.detected, all_detected=p.all_detected,
            dead=p.dead,
            available_icu_units=hc.available_icu_units,
            available_hospital_beds=hc.available_beds,
            r=self._calculate_r(),
        )
        return s

    def apply_intervention(self, intervention):
        if intervention.name == 'test-all-with-symptoms':
            # Start testing everyone who shows even mild symptoms
            self.hc.set_testing_mode(TestingMode.ALL_WITH_SYMPTOMS)
        elif intervention.name == 'test-only-severe-symptoms':
            # Test only those who show severe or critical symptoms
            self.hc.set_testing_mode(TestingMode.ONLY_SEVERE_SYMPTOMS)
        elif intervention.name == 'import-infections':
            # Introduct infections from elsewhere
            count = intervention.value
            for i in range(count):
                idx = int(self.random.get() * len(self.people))
                self.people[idx].infect(self)
        elif intervention.name == 'limit-mass-gatherings':
            self.pop.limit_mass_gatherings = intervention.value
        elif intervention.name == 'limit-mobility':
            self.pop.population_mobility_factor = (100 - intervention.value) / 100.0
        else:
            raise Exception()

    def iterate(self):
        for intervention in self.interventions:
            if intervention.day == self.day:
                print(intervention.name)
                self.apply_intervention(intervention)

        people = self.people
        for person in people:
            if not person.is_infected:
                continue

            person.advance(self)

        self.day += 1


def make_iv(context, intervention, date_str=None, value=None):
    if date_str is not None:
        day = (date.fromisoformat(date_str) - date.fromisoformat(context.start_date)).days
    else:
        day = 0
    return Intervention(day, intervention, value or 0)


@nb.jit(nopython=True)
def create_population(age_counts):
    pop = nb.typed.List()
    for age, count in enumerate(age_counts):
        for i in range(count):
            pop.append(Person(age))
    return pop


# Lombardia
AGES = [0, 10, 20, 30, 40, 50, 60, 70, 80]
LOMBARDIA_POP = [884414, 961237, 982354, 1187594, 1591034, 1566175, 1182159, 994236, 711371]
LOMBARDIA_CONTACTS = 25
LOMBARDIA_HC_CAP = (25000, 720)


@calcfunc(
    variables=['simulation_days']
)
def simulate_individuals(variables):
    pc = PerfCounter()
    if True:
        df = get_population_for_area().sum(axis=1)
        ages = df.index.values
        counts = df.values
        avg_contacts_per_day = get_physical_contacts_for_country()
        hc_cap = (2600, 300)
    else:
        ages = tuple(AGES)
        counts = tuple(LOMBARDIA_POP)
        avg_contacts_per_day = LOMBARDIA_CONTACTS
        hc_cap = LOMBARDIA_HC_CAP

    max_age = max(ages)
    age_counts = np.array(np.zeros(max_age + 1, dtype=np.int32))
    for age, count in zip(ages, counts):
        age_counts[age] = count

    people = create_population(age_counts)

    avg_contacts = np.array(avg_contacts_per_day.values, dtype=np.float32)
    assert avg_contacts.size == max_age + 1

    pop = Population(age_counts, avg_contacts)
    hc = HealthcareSystem(hc_cap[0], hc_cap[1])
    disease = Disease()
    context = Context(pop, people, hc, disease, start_date='2020-02-18')

    ivs = nb.typed.List()
    ivs.append(make_iv(context, 'test-all-with-symptoms'))
    ivs.append(make_iv(context, 'test-only-severe-symptoms', '2020-03-15'))

    ivs.append(make_iv(context, 'limit-mobility', '2020-03-12', value=20))
    ivs.append(make_iv(context, 'limit-mass-gatherings', '2020-03-12', value=50))
    ivs.append(make_iv(context, 'limit-mass-gatherings', '2020-03-18', value=10))

    ivs.append(make_iv(context, 'limit-mobility', '2020-03-26', value=30))

    ivs.append(make_iv(context, 'import-infections', '2020-02-20', value=20))
    ivs.append(make_iv(context, 'import-infections', '2020-03-05', value=300))
    ivs.append(make_iv(context, 'import-infections', '2020-03-07', value=300))
    ivs.append(make_iv(context, 'import-infections', '2020-03-09', value=300))
    ivs.append(make_iv(context, 'import-infections', '2020-03-11', value=300))
    ivs.append(make_iv(context, 'import-infections', '2020-03-13', value=100))
    ivs.append(make_iv(context, 'import-infections', '2020-03-15', value=100))

    #ivs.append(make_iv(context, 'limit-mobility', '2020-08-01', value=0))
    #ivs.append(make_iv(context, 'limit-mass-gatherings', '2020-08-01', value=0))

    context.interventions = ivs

    pc.display('after init')
    states = []

    POP_ATTRS = [
        'susceptible', 'infected', 'all_detected', 'hospitalized',
        'dead', 'recovered'
    ]
    STATE_ATTRS = [
        'hospital_beds', 'icu_units', 'r'
    ]

    header = '%-12s' % 'day'
    for attr in POP_ATTRS + STATE_ATTRS:
        header += '%15s' % attr
    print(header)

    for day in range(variables['simulation_days']):
        state = context.generate_state()

        rec = {attr: sum(getattr(state, attr)) for attr in POP_ATTRS}
        rec['hospital_beds'] = state.available_hospital_beds
        rec['icu_units'] = state.available_icu_units
        rec['r'] = state.r

        s = '%-12s' % (date.fromisoformat(context.start_date) + timedelta(days=context.day)).isoformat()
        for attr in POP_ATTRS:
            s += '%15d' % rec[attr]

        for attr in ['hospital_beds', 'icu_units']:
            s += '%15d' % rec[attr]
        s += '%13.2f' % rec['r']
        print(s)
        states.append(rec)
        context.iterate()

    return pd.DataFrame.from_records(
        states,
        index=pd.date_range(start=context.start_date, periods=len(states)),
        columns=POP_ATTRS + STATE_ATTRS,
    )


if __name__ == '__main__':
    df = simulate_individuals()
    df['total'] = df.infected + df.recovered + df.susceptible + df.dead
    df['cfr'] = df.dead / (df.infected + df.recovered)
    pd.set_option('display.max_rows', 200)
    print(df)
