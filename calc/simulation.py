from collections import namedtuple
import numpy as np
import pandas as pd

from . import calcfunc, ExecutionInterrupted
from enum import IntEnum, auto
from calc.datasets import get_population_for_area, get_physical_contacts_for_country
from utils.perf import PerfCounter
from variables import get_variable
from datetime import date, timedelta
import numba as nb


nb.runtime.nrtdynmod._disable_atomicity = 1


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
    ('idx', nb.int32),
    ('age', nb.int8),
    ('has_immunity', nb.int8),
    ('is_infected', nb.int8),
    ('was_detected', nb.int8),
    ('queued_for_testing', nb.int8),
    ('other_people_infected', nb.int16),
    ('other_people_exposed_today', nb.int16),
    ('symptom_severity', nb.int8),
    ('days_left', nb.int8),
    ('day_of_illness', nb.int8),
    ('state', nb.int8),
    ('infectees', nb.types.ListType(nb.int32)),
    ('infector', nb.int32),
])
class Person:
    def __init__(self, idx, age):
        self.idx = idx
        self.age = age
        self.is_infected = 0
        self.was_detected = 0
        self.has_immunity = 0
        self.days_left = 0
        self.day_of_illness = 0
        self.queued_for_testing = 0
        self.other_people_infected = 0
        self.symptom_severity = SymptomSeverity.ASYMPTOMATIC
        self.state = PersonState.SUSCEPTIBLE
        self.infector = -1
        self.infectees = nb.typed.List.empty_list(nb.int32)

    def expose(self, context, source=None):
        if self.is_infected or self.has_immunity:
            return False
        if context.disease.did_infect(self, context, source):
            self.infect(context, source)
            return True
        return False

    def infect(self, context, source=None):
        self.state = PersonState.INCUBATION
        self.days_left = context.disease.get_incubation_days(self, context)
        self.is_infected = 1
        if source is not None:
            self.infector = source.idx
            source.infectees.append(self.idx)

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
        if not self.was_detected:
            self.detect(context)

        if self.symptom_severity == SymptomSeverity.CRITICAL:
            if not context.hc.to_icu():
                # If no ICU units are available, ...
                self.die(context)
                return
            self.state = PersonState.IN_ICU
            self.days_left = context.disease.get_icu_days(self, context)
        else:
            if not context.hc.hospitalize():
                # If no beds are available, there's a chance to die.
                if context.disease.dies_in_hospital(self, context, in_icu=False, care_available=False):
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
            death = context.disease.dies_in_hospital(self, context, in_icu=True, care_available=True)
            context.hc.release_from_icu()
        else:
            death = context.disease.dies_in_hospital(self, context, in_icu=False, care_available=True)
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
        self.other_people_exposed_today = nr_contacts
        for i in range(nr_contacts):
            exposee_idx = int(context.random.get() * len(people))
            target = people[exposee_idx]
            if target.expose(context, self):
                self.infectees.append(exposee_idx)
                self.other_people_infected += 1

    def become_ill(self, context):
        self.state = PersonState.ILLNESS
        self.symptom_severity = context.disease.get_symptom_severity(self, context)
        self.days_left = context.disease.get_illness_days(self, context)
        if self.symptom_severity != SymptomSeverity.ASYMPTOMATIC:
            # People with symptoms seek testing (but might not get it)
            if not self.was_detected:
                context.hc.seek_testing(self, context)

    def advance(self, context):
        self.other_people_exposed_today = 0

        if self.state == PersonState.INCUBATION:
            people_exposed = context.disease.people_exposed(self, context)
            if people_exposed:
                self.expose_others(context, people_exposed)

            self.days_left -= 1
            if self.days_left == 0:
                self.become_ill(context)
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
    ALL_WITH_SYMPTOMS_CT = auto()
    ALL_WITH_SYMPTOMS = auto()
    ONLY_SEVERE_SYMPTOMS = auto()


@nb.jitclass([
    ('beds', nb.int32),
    ('icu_units', nb.int32),
    ('available_beds', nb.int32),
    ('available_icu_units', nb.int32),
    ('testing_mode', nb.int32),
    ('tests_run_per_day', nb.int32),
    ('testing_queue', nb.types.ListType(nb.int32)),
])
class HealthcareSystem:
    def __init__(self, beds, icu_units):
        self.beds = beds
        self.icu_units = icu_units
        self.available_beds = beds
        self.available_icu_units = icu_units
        self.testing_mode = TestingMode.NO_TESTING
        self.testing_queue = nb.typed.List.empty_list(nb.int32)
        self.tests_run_per_day = 0

    def queue_for_testing(self, person_idx, context):
        p = context.people[person_idx]
        if p.state == PersonState.DEAD or p.was_detected or p.queued_for_testing:
            return False
        p.queued_for_testing = 1
        self.testing_queue.append(person_idx)
        return True

    def perform_contact_tracing(self, person, context):
        contacts = nb.typed.List.empty_list(nb.int32)

        contacts.append(person.infector)
        for idx in person.infectees:
            contacts.append(idx)

        for i in range(3):
            next_contacts = nb.typed.List.empty_list(nb.int32)
            for idx in contacts:
                if idx < 0:
                    continue
                if not self.queue_for_testing(idx, context):
                    continue

                p = context.people[idx]
                next_contacts.append(p.infector)
                for pi in p.infectees:
                    next_contacts.append(pi)

            contacts = next_contacts

    def iterate(self, context):
        people = context.people

        queue = self.testing_queue
        self.tests_run_per_day = len(queue)
        self.testing_queue = nb.typed.List.empty_list(nb.int32)

        # Run tests
        for idx in queue:
            person = people[idx]
            if not person.queued_for_testing:
                raise Exception()
            person.queued_for_testing = 1

            if not person.is_infected or person.was_detected:
                continue

            if not self.is_detected(person, context):
                continue

            # Infection is detected
            person.detect(context)
            if self.testing_mode == TestingMode.ALL_WITH_SYMPTOMS_CT:
                # With contact tracing we queue the infector and the
                # infectees for testing.
                # FIXME: Simulate non-perfect contact tracing?
                self.perform_contact_tracing(person, context)

    def seek_testing(self, person, context):
        queue_for_testing = False
        if self.testing_mode in (TestingMode.ALL_WITH_SYMPTOMS, TestingMode.ALL_WITH_SYMPTOMS_CT):
            queue_for_testing = True
        elif self.testing_mode == TestingMode.ONLY_SEVERE_SYMPTOMS:
            if person.symptom_severity in (SymptomSeverity.SEVERE, SymptomSeverity.CRITICAL):
                queue_for_testing = True
            elif context.random.chance(.02):
                # Some people get tests anyway (healthcare workers etc.)
                queue_for_testing = True
        else:
            raise Exception()
        if queue_for_testing:
            self.queue_for_testing(person.idx, context)

    def hospitalize(self):
        if self.available_beds == 0:
            return False
        self.available_beds -= 1
        return True

    def set_testing_mode(self, mode):
        self.testing_mode = mode

    def is_detected(self, person, context):
        # Person needs to have viral load in order to be detected
        if context.disease.get_source_infectiousness(person):
            # FIXME: Factor in sensitivity?
            return True

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


@nb.jitclass([
    ('p_infection', nb.float32),
    ('p_asymptomatic', nb.float32),
    ('p_critical', nb.float32),
    ('p_hospital_death', nb.float32),
    ('p_icu_death', nb.float32),
    ('p_hospital_death_no_beds', nb.float32),
    ('p_icu_death_no_beds', nb.float32),
    ('p_severe', nb.float32[:, :]),
])
class Disease:
    def __init__(
        self, p_infection, p_asymptomatic, p_severe, p_critical, p_hospital_death,
        p_icu_death, p_hospital_death_no_beds, p_icu_death_no_beds
    ):
        self.p_infection = p_infection
        self.p_asymptomatic = p_asymptomatic
        self.p_critical = p_critical
        self.p_severe = p_severe

        self.p_hospital_death = p_hospital_death
        self.p_icu_death = p_icu_death
        self.p_hospital_death_no_beds = p_hospital_death_no_beds
        self.p_icu_death_no_beds = p_icu_death_no_beds

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
                return self.p_infection * chance
        return 0

    def did_infect(self, person, context, source):
        chance = self.get_source_infectiousness(source)
        # FIXME: Smaller chance for asymptomatic people?
        return context.random.chance(chance)

    def people_exposed(self, person, context):
        # Detected people are quarantined
        if person.was_detected:
            return 0

        # If we are not infectious today, we expose 0 people.
        if not self.get_source_infectiousness(person):
            return 0

        if person.state == PersonState.INCUBATION:
            return context.pop.contacts_per_day(person, context)
        elif person.state == PersonState.ILLNESS:
            # Asymptomatic people infect others without knowing it
            if person.symptom_severity == SymptomSeverity.ASYMPTOMATIC:
                return context.pop.contacts_per_day(person, context)
            else:
                # People with mild or more severe symptoms restrict their movement
                return context.pop.contacts_per_day(person, context, factor=0.5, limit=5)

        raise Exception()

    def dies_in_hospital(self, person, context, in_icu, care_available):
        if in_icu:
            if care_available:
                chance = self.p_icu_death
            else:
                chance = self.p_icu_death_no_beds
        else:
            if care_available:
                chance = self.p_hospital_death
            else:
                chance = self.p_hospital_death_no_beds

        return context.random.chance(chance)

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
        severe_chance = 0.0
        for i in range(self.p_severe.size // 2):
            age, sc = self.p_severe[i]
            if age > person.age:
                break
            severe_chance = sc

        if val < severe_chance * self.p_critical:
            return SymptomSeverity.CRITICAL
        if val < severe_chance:
            return SymptomSeverity.SEVERE
        if val < 1 - self.p_asymptomatic:
            return SymptomSeverity.MILD
        return SymptomSeverity.ASYMPTOMATIC


MODEL_STATE_FIELDS = [
    'susceptible', 'infected', 'detected', 'all_detected',
    'hospitalized', 'dead', 'recovered',
    'available_hospital_beds', 'available_icu_units',
    'r', 'exposed_per_day', 'tests_run_per_day',
]
ModelState = namedtuple('ModelState', MODEL_STATE_FIELDS)


@nb.jitclass([
    ('infected', nb.int32[::1]),
    ('detected', nb.int32[::1]),
    ('all_detected', nb.int32[::1]),
    ('hospitalized', nb.int32[::1]),
    ('dead', nb.int32[::1]),
    ('susceptible', nb.int32[::1]),
    ('recovered', nb.int32[::1]),
    ('avg_contacts_per_day', nb.float32[::1]),
    ('limit_mass_gatherings', nb.int32),
    ('population_mobility_factor', nb.float32),
])
class Population:
    def __init__(self, age_counts, avg_contacts_per_day):
        nr_ages = age_counts.size
        self.susceptible = age_counts.copy()

        self.infected = np.zeros(nr_ages, dtype=np.int32)
        self.detected = np.zeros(nr_ages, dtype=np.int32)
        self.all_detected = np.zeros(nr_ages, dtype=np.int32)
        self.recovered = np.zeros(nr_ages, dtype=np.int32)
        self.hospitalized = np.zeros(nr_ages, dtype=np.int32)
        self.dead = np.zeros(nr_ages, dtype=np.int32)
        self.avg_contacts_per_day = avg_contacts_per_day.copy()
        self.limit_mass_gatherings = 0
        self.population_mobility_factor = 1.0

    def contacts_per_day(self, person, context, factor=1.0, limit=100):
        # Contacts per day follows a lognormal distribution with
        # mean at `avg_contacts_per_day`.
        factor *= self.population_mobility_factor
        contacts = int(np.random.lognormal(1.0, 0.7) * self.avg_contacts_per_day[person.age] * factor)
        if self.limit_mass_gatherings:
            if contacts > self.limit_mass_gatherings:
                contacts = self.limit_mass_gatherings
        if contacts > limit:
            contacts = limit
        return contacts

    def infect(self, person):
        age = person.age
        self.susceptible[age] -= 1
        self.infected[age] += 1

    def recover(self, person):
        age = person.age
        self.infected[age] -= 1
        self.recovered[age] += 1
        if person.was_detected:
            self.detected[age] -= 1

    def detect(self, person):
        age = person.age
        self.detected[age] += 1
        self.all_detected[age] += 1

    def hospitalize(self, person):
        self.hospitalized[person.age] += 1

    def release_from_hospital(self, person):
        self.hospitalized[person.age] -= 1

    def die(self, person):
        age = person.age
        self.infected[age] -= 1
        self.dead[age] += 1
        if person.was_detected:
            self.detected[age] -= 1


@nb.jitclass([])
class RandomPool:
    def __init__(self):
        np.random.seed(1234)

    def get(self):
        return np.random.random()

    def chance(self, p):
        if p == 1.0:
            return True
        elif p == 0:
            return False

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
    ('start_date', nb.types.string),
    ('total_infections', nb.int32),
    ('total_infectors', nb.int32),
    ('exposed_per_day', nb.int32),
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

        # Per day
        self.total_infectors = 0
        self.total_infections = 0
        self.exposed_per_day = 0

    def generate_state(self):
        p = self.pop
        hc = self.hc
        r = self.total_infections / self.total_infectors if self.total_infectors else 0
        s = ModelState(
            infected=p.infected, susceptible=p.susceptible,
            recovered=p.recovered, hospitalized=p.hospitalized,
            detected=p.detected, all_detected=p.all_detected,
            dead=p.dead,
            available_icu_units=hc.available_icu_units,
            available_hospital_beds=hc.available_beds,
            r=r,
            exposed_per_day=self.exposed_per_day,
            tests_run_per_day=self.hc.tests_run_per_day,
        )
        return s

    def apply_intervention(self, intervention):
        if intervention.name == 'test-all-with-symptoms':
            # Start testing everyone who shows even mild symptoms
            self.hc.set_testing_mode(TestingMode.ALL_WITH_SYMPTOMS)
        elif intervention.name == 'test-only-severe-symptoms':
            # Test only those who show severe or critical symptoms
            self.hc.set_testing_mode(TestingMode.ONLY_SEVERE_SYMPTOMS)
        elif intervention.name == 'test-with-contact-tracing':
            # Test only those who show severe or critical symptoms
            self.hc.set_testing_mode(TestingMode.ALL_WITH_SYMPTOMS_CT)
        elif intervention.name == 'build-new-icu-units':
            self.hc.icu_units += intervention.value
            self.hc.available_icu_units += intervention.value
        elif intervention.name == 'build-new-hospital-beds':
            self.hc.beds += intervention.value
            self.hc.available_beds += intervention.value
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

        self.total_infectors = 0
        self.total_infections = 0
        self.exposed_per_day = 0

        self.hc.iterate(self)

        people = self.people
        for person in people:
            if not person.is_infected:
                continue

            person.advance(self)

            self.exposed_per_day += person.other_people_exposed_today

            if person.state != PersonState.ILLNESS:
                continue

            self.total_infectors += 1
            self.total_infections += person.other_people_infected

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
    idx = 0
    for age, count in enumerate(age_counts):
        for i in range(count):
            pop.append(Person(idx, age))
            idx += 1
    return pop


INTERVENTIONS = [
    ('test-all-with-symptoms', 'Testataan kaikki oirehtivat'),
    ('test-only-severe-symptoms', 'Testataan ainoastaan vakavasti oirehtivat'),
    ('test-with-contact-tracing', 'Testataan kaikki oirehtivat sekä määritetään tartuntaketjut'),
    ('limit-mobility', 'Rajoitetaan väestön liikkuvuutta', '%'),
    ('limit-mass-gatherings', 'Rajoitetaan kokoontumisia', 'kontaktia (max.)'),
    ('import-infections', 'Alueelle tulee infektioita', 'kpl'),
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

    people = create_population(age_counts)

    avg_contacts = np.array(avg_contacts_per_day.values, dtype=np.float32)
    assert avg_contacts.size == max_age + 1

    pop = Population(age_counts, avg_contacts)
    hc = HealthcareSystem(hc_cap[0], hc_cap[1])

    sevvar = variables['p_severe']
    sev_arr = np.ndarray((len(sevvar), 2), dtype=np.float32)
    for idx, (age, sev) in enumerate(sevvar):
        sev_arr[idx] = (age, sev / 100)

    disease = Disease(
        p_infection=variables['p_infection'] / 100,
        p_asymptomatic=variables['p_asymptomatic'] / 100,
        p_severe=sev_arr,
        p_critical=variables['p_critical'] / 100,
        p_hospital_death=variables['p_hospital_death'] / 100,
        p_icu_death=variables['p_icu_death'] / 100,
        p_hospital_death_no_beds=variables['p_hospital_death_no_beds'] / 100,
        p_icu_death_no_beds=variables['p_icu_death_no_beds'] / 100,
    )
    context = Context(pop, people, hc, disease, start_date=variables['start_date'])
    start_date = date.fromisoformat(variables['start_date'])

    ivs = nb.typed.List()

    for iv in variables['interventions']:
        iv_id = iv[0]
        iv_date = iv[1]
        if len(iv) > 2:
            iv_value = iv[2]
        else:
            iv_value = None
        # Extremely awkward, but Numba poses some limitations.
        ivs.append(make_iv(context, iv_id, iv_date, value=iv_value))

    context.interventions = ivs

    pc.display('after init')

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
