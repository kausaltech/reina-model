# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: profile=False
# cython: linetrace=False

from collections import namedtuple
from datetime import date, timedelta

import numpy as np
import pandas as pd
from cython.parallel import prange
from faker.providers.person.fi_FI import Provider as NameProvider

from common.interventions import Intervention

cimport cython
cimport openmp
from cpython.mem cimport PyMem_Malloc, PyMem_Free  # isort:skip
from libc.stdlib cimport malloc, free  # isort:skip
from libc.string cimport memset
cimport numpy as cnp

from cythonsim.simrandom cimport RandomPool  # isort:skip

from utils.perf import PerfCounter

ctypedef int int32
ctypedef unsigned char uint8
ctypedef int int16


cdef enum SymptomSeverity:
    ASYMPTOMATIC
    MILD
    SEVERE
    CRITICAL
    FATAL


cdef enum PersonState:
    SUSCEPTIBLE
    INCUBATION
    ILLNESS
    HOSPITALIZED
    IN_ICU
    RECOVERED
    DEAD


cdef enum SimulationProblem:
    NO_PROBLEMOS
    TOO_MANY_INFECTEES
    TOO_MANY_CONTACTS
    HOSPITAL_ACCOUNTING_FAILURE
    NEGATIVE_CONTACTS
    MALLOC_FAILURE
    OTHER_FAILURE
    WRONG_STATE
    CONTACT_PROBABILITY_FAILURE
    INFECTEES_MISMATCH


cdef enum ContactPlace:
    HOME = 0
    WORK = 1
    SCHOOL = 2
    TRANSPORT = 3
    LEISURE = 4
    OTHER = 5

    ALL = 100

DEF NR_CONTACT_PLACES = 6

cdef enum PlaceOfDeath:
    DEATH_IN_HOSPITAL
    DEATH_OUTSIDE_HOSPITAL


CONTACT_PLACE_TO_STR = {
    ALL: 'all',
    HOME: 'home',
    WORK: 'work',
    SCHOOL: 'school',
    TRANSPORT: 'transport',
    LEISURE: 'leisure',
    OTHER: 'other',
}


STATE_TO_STR = {
    PersonState.SUSCEPTIBLE: 'SUSCEPTIBLE',
    PersonState.INCUBATION: 'INCUBATION',
    PersonState.ILLNESS: 'ILLNESS',
    PersonState.HOSPITALIZED: 'HOSPITALIZED',
    PersonState.IN_ICU: 'IN_ICU',
    PersonState.RECOVERED: 'RECOVERED',
    PersonState.DEAD: 'DEAD',
}
SEVERITY_TO_STR = {
    SymptomSeverity.ASYMPTOMATIC: 'ASYMPTOMATIC',
    SymptomSeverity.MILD: 'MILD',
    SymptomSeverity.SEVERE: 'SEVERE',
    SymptomSeverity.CRITICAL: 'CRITICAL',
    SymptomSeverity.FATAL: 'FATAL',
}
STR_TO_SEVERITY = {val: key for key, val in SEVERITY_TO_STR.items()}

PROBLEM_TO_STR = {
    SimulationProblem.NO_PROBLEMOS: 'No problemos',
    SimulationProblem.TOO_MANY_INFECTEES: 'Too many infectees',
    SimulationProblem.TOO_MANY_CONTACTS: 'Too many contacts',
    SimulationProblem.HOSPITAL_ACCOUNTING_FAILURE: 'Hospital accounting failure',
    SimulationProblem.NEGATIVE_CONTACTS: 'Negative number of contacts',
    SimulationProblem.MALLOC_FAILURE: 'Malloc failure',
    SimulationProblem.OTHER_FAILURE: 'Other failure',
    SimulationProblem.WRONG_STATE: 'Wrong state',
    SimulationProblem.CONTACT_PROBABILITY_FAILURE: 'Contact probability failure',
    SimulationProblem.INFECTEES_MISMATCH: 'Infectees mismatch',
}


class SimulationFailed(Exception):
    pass


DEF MAX_INFECTEES = 64
DEF MAX_CONTACTS = 128


cdef struct Person:
    int32 idx, infector
    uint8 age, has_immunity, is_infected, was_detected, queued_for_testing, \
        symptom_severity, place_of_death, state, included_in_totals, \
        variant_idx
    int16 day_of_infection, days_left, other_people_infected, other_people_exposed_today, \
        day_of_illness
    int16 max_contacts_per_day
    int16 day_of_vaccination

    float days_from_onset_to_removed
    uint8 nr_infectees
    int32 *infectees


cdef struct Contact:
    int32 person_idx
    float mask_p
    ContactPlace place


cdef void person_init(Person *self, int32 idx, uint8 age) nogil:
    self.idx = idx
    self.age = age
    self.symptom_severity = SymptomSeverity.ASYMPTOMATIC
    self.state = PersonState.SUSCEPTIBLE
    self.infector = -1
    self.infectees = NULL
    self.day_of_vaccination = -1


first_names = list(NameProvider.first_names.keys())
last_names = list(NameProvider.last_names.keys())

cdef str person_name(Person *self):
    cdef int idx = self.idx

    fn = first_names[idx % len(first_names)]
    idx /= len(first_names)
    sn = first_names[idx % len(first_names)]
    idx /= len(first_names)
    ln = last_names[idx % len(last_names)]
    idx /= len(last_names)

    return '%s %s %s (%d)' % (fn, sn, ln, self.idx)


cdef str person_str(Person *self, int today=-1):
    cdef str name = person_name(self)

    if self.infectees != NULL:
        infectees = '[%s]' % ', '.join(['%d' % self.infectees[i] for i in range(self.nr_infectees)])
    else:
        infectees = ''

    if today >= 0 and self.is_infected:
        days_ago = ' (%d days ago)' % (today - self.day_of_infection)
    else:
        days_ago = ''

    if self.queued_for_testing:
        queued = 'queued for testing, '
    else:
        queued = ''

    if self.variant_idx:
        variant_str = ' [variant %d]' % self.variant_idx
    else:
        variant_str = ''

    return '%s: %d years, infection%s on day %d%s, %s, %s, days left %d, %sdetected %d, max. contacts %d (others infected %d%s)' % (
        name, self.age, variant_str, self.day_of_infection, days_ago, STATE_TO_STR[self.state],
        SEVERITY_TO_STR[self.symptom_severity], self.days_left, queued, self.was_detected,
        self.max_contacts_per_day, self.other_people_infected, infectees
    )


cdef void person_infect(Person *self, Context context, Person *source, int variant_idx) nogil:
    self.state = PersonState.INCUBATION
    self.symptom_severity = context.disease.get_symptom_severity(self, context)
    self.days_left = context.disease.get_incubation_days(self, context)
    self.is_infected = 1
    self.day_of_infection = context.day

    if source is not NULL:
        self.infector = source.idx
        if source.infectees != NULL:
            if source.nr_infectees >= MAX_INFECTEES:
                context.set_problem(SimulationProblem.TOO_MANY_INFECTEES)
                return
            source.infectees[source.nr_infectees] = self.idx
            source.nr_infectees += 1
        variant_idx = source.variant_idx
    self.variant_idx = variant_idx

    if context.hc.testing_mode == TestingMode.ALL_WITH_SYMPTOMS_CT:
        if self.infectees != NULL:
            context.set_problem(SimulationProblem.INFECTEES_MISMATCH)
        else:
            self.infectees = <int32 *> malloc(sizeof(int32) * MAX_INFECTEES)
            if self.infectees == NULL:
                context.set_problem(SimulationProblem.MALLOC_FAILURE)

    context.pop.infect(self)


cdef bint person_expose(Person *self, Context context, Person *source, float mask_p) nogil:
    if self.is_infected or self.has_immunity:
        return False
    if context.disease.did_infect(self, context, source, mask_p):
        person_infect(self, context, source, -1)
        return True
    return False


cdef void person_expose_others(Person *self, Context context) nogil:
    cdef Contact[MAX_CONTACTS] contacts
    cdef Person *people = context.pop.people
    cdef int32 *infectees
    cdef int nr_contacts, exposee_idx, total, i
    cdef Person *target

    nr_contacts = context.disease.get_exposed_people(self, contacts, context)
    self.other_people_exposed_today = nr_contacts
    if nr_contacts == 0:
        return
    if nr_contacts < 0:
        context.set_problem(SimulationProblem.NEGATIVE_CONTACTS, self)
        return

    if nr_contacts > self.max_contacts_per_day:
        self.max_contacts_per_day = nr_contacts

    self.other_people_exposed_today = nr_contacts

    infectees = self.infectees
    for i in range(nr_contacts):
        exposee_idx = contacts[i].person_idx
        target = &people[exposee_idx]

        # with gil:
        #     print('%s\n-> %s' % (person_str(self), person_str(target)))

        if person_expose(target, context, self, contacts[i].mask_p):
            if infectees != NULL:
                if self.other_people_infected >= MAX_INFECTEES:
                    context.set_problem(SimulationProblem.TOO_MANY_INFECTEES, self)
                    break
                infectees[self.other_people_infected] = exposee_idx
            self.other_people_infected += 1


cdef void person_become_ill(Person *self, Context context) nogil:
    self.state = PersonState.ILLNESS
    self.days_from_onset_to_removed = context.disease.get_days_from_onset_to_removed(self, context)
    self.days_left = context.disease.get_illness_days(self, context)
    if self.symptom_severity != SymptomSeverity.ASYMPTOMATIC:
        # People with symptoms seek testing (but might not get it)
        if not self.was_detected:
            context.hc.seek_testing(self, context)


cdef void person_detect(Person *self, Context context) nogil:
    self.was_detected = 1
    context.pop.detect(self)


cdef void person_become_removed(Person *self, Context context) nogil:
    self.is_infected = 0
    self.has_immunity = 1

    if self.infectees != NULL:
        free(self.infectees)
        self.infectees = NULL


cdef void person_dealloc(Person *self) nogil:
    if self.infectees != NULL:
        free(self.infectees)


cdef void person_recover(Person *self, Context context) nogil:
    self.state = PersonState.RECOVERED
    person_become_removed(self, context)
    context.pop.recover(self)


cdef void person_hospitalize(Person *self, Context context) nogil:
    if not self.was_detected:
        # People seeking hospital treatment are always detected
        # FIXME: Might not be the case
        person_detect(self, context)

    if not context.hc.hospitalize(self):
        # If no beds are available, there's a chance to die.
        if context.disease.dies_in_hospital(self, context, care_available=False):
            person_die(self, context)
        else:
            person_recover(self, context)
        return

    self.days_left = context.disease.get_hospitalization_days(self, context)
    self.state = PersonState.HOSPITALIZED

    context.pop.hospitalize(self)


cdef void person_transfer_to_icu(Person *self, Context context) nogil:
    if not context.hc.to_icu():
        # If no ICU units are available, there's a chance to die.
        if context.disease.dies_in_hospital(self, context, care_available=False):
            context.pop.release_from_hospital(self)
            person_die(self, context)
            return

    self.days_left = context.disease.get_icu_days(self, context)
    self.state = PersonState.IN_ICU

    context.pop.transfer_to_icu(self)


cdef void person_release_from_hospital(Person *self, Context context) nogil:
    context.pop.release_from_hospital(self)

    if self.state == PersonState.IN_ICU:
        death = context.disease.dies_in_hospital(self, context, care_available=True)
        context.pop.release_from_icu(self)
        context.hc.release_from_icu()
    else:
        death = context.disease.dies_in_hospital(self, context, care_available=True)
        context.hc.release()

    if death:
        person_die(self, context)
    else:
        person_recover(self, context)


cdef void person_die(Person *self, Context context) nogil:
    self.state = PersonState.DEAD
    context.pop.die(self)
    # This is a way to get long-lasting immunity.
    person_become_removed(self, context)


cdef bint person_vaccinate(Person *self, Context context) nogil:
    """Vaccinates a person.

    Will return False if the person cannot be vaccinated, True otherwise.
    """

    if self.state == PersonState.DEAD or self.day_of_vaccination >= 0:
        return False

    # Do not vaccinate detected cases. (Hospitalized patients are always detected.)
    if self.was_detected:
        return False

    self.day_of_vaccination = context.day
    context.pop.vaccinate(self)
    return True


cdef void person_advance(Person *self, Context context) nogil:
    cdef int people_exposed
    self.other_people_exposed_today = 0

    if self.state == PersonState.INCUBATION:
        # If we were infected before in the iteration loop, we wait until
        # tomorrow before we start advancing in the illness.
        if self.day_of_infection == context.day:
            return
        person_expose_others(self, context)
        if self.days_left > 0:
            self.days_left -= 1
        if self.days_left == 0:
            person_become_ill(self, context)
    elif self.state == PersonState.ILLNESS:
        person_expose_others(self, context)
        self.day_of_illness += 1
        if self.days_left > 0:
            self.days_left -= 1
        if self.days_left == 0:
            # People with mild symptoms recover after the symptomatic period
            # and people with more severe symptoms are hospitalized.
            # Some people with fatal symptoms die at home or in a place of care.
            if self.symptom_severity == SymptomSeverity.FATAL and self.place_of_death == PlaceOfDeath.DEATH_OUTSIDE_HOSPITAL:
                person_die(self, context)
            elif self.symptom_severity in (SymptomSeverity.SEVERE, SymptomSeverity.CRITICAL, SymptomSeverity.FATAL):
                person_hospitalize(self, context)
            else:
                person_recover(self, context)
    elif self.state == PersonState.HOSPITALIZED:
        if self.days_left > 0:
            self.days_left -= 1
        if self.days_left == 0:
            # People with critical symptoms will be transferred to ICU care
            # after a period in a non-iCU hospital care.
            if self.symptom_severity in (SymptomSeverity.CRITICAL, SymptomSeverity.FATAL):
                person_transfer_to_icu(self, context)
            else:
                person_release_from_hospital(self, context)
    elif self.state == PersonState.IN_ICU:
        if self.days_left > 0:
            self.days_left -= 1
        if self.days_left == 0:
            person_release_from_hospital(self, context)


cdef enum TestingMode:
    NO_TESTING
    ALL_WITH_SYMPTOMS_CT
    ALL_WITH_SYMPTOMS
    ONLY_SEVERE_SYMPTOMS


DEF TESTING_TRACE = False


cdef class HealthcareSystem:
    cdef int32 beds, icu_units, available_beds, available_icu_units
    cdef int32 ct_cases_per_day
    cdef float p_detected_anyway
    cdef float p_successful_tracing
    cdef TestingMode testing_mode
    cdef list testing_queue
    cdef list vaccinations
    cdef openmp.omp_lock_t lock

    def __init__(self, hospital_beds, icu_units):
        self.beds = hospital_beds
        self.icu_units = icu_units
        self.available_beds = hospital_beds
        self.available_icu_units = icu_units
        self.testing_mode = TestingMode.NO_TESTING
        self.testing_queue = []
        self.ct_cases_per_day = 0
        self.p_detected_anyway = 0
        self.p_successful_tracing = 1.0
        self.vaccinations = []
        openmp.omp_init_lock(&self.lock)

    cdef bint queue_for_testing(self, int person_idx, Context context, float p_success) nogil:
        cdef Person *p = context.pop.people + person_idx
        if p.state == PersonState.DEAD or p.was_detected or p.queued_for_testing:
            return False

        # There is a chance we might not catch this person in contact tracing
        if not context.random.chance(p_success):
            return False

        p.queued_for_testing = 1
        with gil:
            self.testing_queue.append(person_idx)
            IF TESTING_TRACE:
                context.trace('added to test queue', person_idx=person_idx)
        return True

    cdef bint should_trace_contacts(self, Context context) nogil:
        if self.testing_mode == TestingMode.ALL_WITH_SYMPTOMS_CT:
            return True
        return False

    cdef void perform_contact_tracing(self, int person_idx, Context context, int level) nogil:
        cdef Person *p = context.pop.people + person_idx
        cdef int infectee_idx
        if level > 1:
            return

        IF TESTING_TRACE:
            with gil:
                test_trace('%sContact tracing %s' % (level * '  ', person_name(p)))

        if p.infector >= 0:
            if self.queue_for_testing(p.infector, context, self.p_successful_tracing):
                self.perform_contact_tracing(p.infector, context, level + 1)
        if p.infectees != NULL:
            for i in range(p.nr_infectees):
                infectee_idx = p.infectees[i]
                if self.queue_for_testing(infectee_idx, context, self.p_successful_tracing):
                    self.perform_contact_tracing(infectee_idx, context, level + 1)

    cdef iterate(self, Context context):
        cdef Person *person
        cdef int idx, nr

        queue = self.testing_queue
        self.ct_cases_per_day = len(queue)
        self.testing_queue = []

        # Run tests
        for idx in queue:
            person = context.pop.people + idx
            if not person.queued_for_testing:
                raise Exception()
            person.queued_for_testing = 0

            if not person.is_infected or person.was_detected:
                IF TESTING_TRACE:
                    raise Exception(person_str(person))

            if not self.is_detected(person, context):
                IF TESTING_TRACE:
                    raise Exception(person_str(person))

            # Infection is detected
            IF TESTING_TRACE:
                context.trace('detected', person_idx=person.idx)
            person_detect(person, context)
            if self.testing_mode == TestingMode.ALL_WITH_SYMPTOMS_CT:
                # With contact tracing we queue the infector and the
                # infectees for testing.
                # FIXME: Simulate non-perfect contact tracing?
                self.perform_contact_tracing(idx, context, 0)

        pop_max_age = context.pop.nr_ages - 1
        for v in self.vaccinations:
            if not v['nr_daily']:
                continue
            min_age = v['min_age']
            max_age = v['max_age']
            if min_age == None:
                min_age = 0
            if max_age == None:
                max_age = pop_max_age
            nr = v['nr_daily']
            self.vaccinate_people(nr, min_age, max_age, context)

    cdef void vaccinate_people(self, int nr_to_vaccinate, int min_age, int max_age, Context context) nogil:
        cdef Person *person
        cdef int idx_start, idx_end, idx, vaccinated

        idx_start = context.pop.age_start[min_age]
        if max_age < context.pop.nr_ages - 1:
            idx_end = context.pop.age_start[max_age + 1]
        else:
            idx_end = context.pop.total_people

        vaccinated = 0
        # Start vaccinating systematically from the oldest age group
        idx = idx_end - 1

        # More to vaccinate than we have agents?
        if nr_to_vaccinate > idx_end - idx_start:
            nr_to_vaccinate = idx_end - idx_start

        while vaccinated < nr_to_vaccinate and idx >= idx_start:
            person = context.pop.people + context.pop.people_sorted_by_age[idx]
            idx -= 1
            if not person_vaccinate(person, context):
                continue
            vaccinated += 1

    def start_vaccinating(self, daily_vaccinations, min_age, max_age, context):
        for v in self.vaccinations:
            if min_age != v.get('min_age') or max_age != v.get('max_age'):
                continue
            break
        else:
            v = dict(min_age=min_age, max_age=max_age)
            self.vaccinations.append(v)
        v['nr_daily'] = daily_vaccinations

    cdef void seek_testing(self, Person *person, Context context) nogil:
        IF TESTING_TRACE:
            with gil:
                context.trace('seeks testing', person_idx=person.idx)

        queue_for_testing = False
        if self.testing_mode in (TestingMode.ALL_WITH_SYMPTOMS, TestingMode.ALL_WITH_SYMPTOMS_CT):
            queue_for_testing = True
        elif self.testing_mode == TestingMode.ONLY_SEVERE_SYMPTOMS:
            if person.symptom_severity in (SymptomSeverity.SEVERE, SymptomSeverity.CRITICAL, SymptomSeverity.FATAL):
                queue_for_testing = True
            elif context.random.chance(self.p_detected_anyway):
                # Some people get tests anyway (healthcare workers etc.)
                queue_for_testing = True

                # with gil:
                #    print('Day %d. Seek testing and got it' % context.day)
                #    person_str(person)

        if queue_for_testing:
            self.queue_for_testing(person.idx, context, 1)

    cdef bint hospitalize(self, Person *person) nogil:
        if self.available_beds == 0:
            return False
        self.available_beds -= 1
        return True

    def set_testing_mode(self, mode, p=1.0):
        self.testing_mode = mode
        if mode == TestingMode.ALL_WITH_SYMPTOMS_CT:
            self.p_successful_tracing = p
        elif mode == TestingMode.ONLY_SEVERE_SYMPTOMS:
            self.p_detected_anyway = p

    cdef bint is_detected(self, Person *person, Context context) nogil:
        # Person needs to have viral load in order to be detected
        if context.disease.get_source_infectiousness(person):
            # FIXME: Factor in sensitivity?
            return True

        if person.state in (PersonState.HOSPITALIZED, PersonState.IN_ICU):
            return True
        return False

    cdef void release(self) nogil:
        self.available_beds += 1

    cdef bint to_icu(self) nogil:
        self.available_beds += 1
        if self.available_icu_units == 0:
            return False
        self.available_icu_units -= 1
        return True

    cdef void release_from_icu(self) nogil:
        self.available_icu_units += 1


# The infectiousness profile of the pathogen over time.
# Day 0 is the symptom onset day.

# Source: The timing of COVID-19 transmission (Luca et al.)
# https://doi.org/10.1101/2020.09.04.20188516)
# https://www.medrxiv.org/content/10.1101/2020.09.04.20188516v2.full.pdf
INFECTIOUSNESS_OVER_TIME = (
    (-10, 0.00183),
    (-9, 0.00280),
    (-8, 0.00446),
    (-7, 0.00742),
    (-6, 0.01291),
    (-5, 0.02350),
    (-4, 0.04419),
    (-3, 0.08247),
    (-2, 0.14018),
    (-1, 0.19032),
    (0, 0.18539),
    (1, 0.13091),
    (2, 0.07538),
    (3, 0.04018),
    (4, 0.02144),
    (5, 0.01185),
    (6, 0.00686),
    (7, 0.00415),
    (8, 0.00262),
    (9, 0.00172),
    (10, 0.00117),
)

cdef struct ClassifiedValues:
    int *classes
    float *values
    int num_classes, min_class, max_class


cdef void cv_init(ClassifiedValues *self, object pairs):
    self.num_classes = len(pairs)
    self.classes = <int *> PyMem_Malloc(self.num_classes * sizeof(int))
    self.values = <float *> PyMem_Malloc(self.num_classes * sizeof(float))
    self.min_class = 0x7fffffff
    self.max_class = 0
    for idx, (kls, val) in enumerate(pairs):
        self.classes[idx] = kls
        self.values[idx] = val
        if kls < self.min_class:
            self.min_class = kls
        if kls > self.max_class:
            self.max_class = kls


cdef void cv_free(ClassifiedValues *cv):
    PyMem_Free(cv.classes)
    PyMem_Free(cv.values)


cdef float cv_get(ClassifiedValues *cv, int kls, float default) nogil:
    cdef int idx;

    if kls < cv.min_class or kls > cv.max_class:
        return default
    for idx in range(cv.num_classes):
        if cv.classes[idx] == kls:
            return cv.values[idx]
    return default


cdef float cv_get_greatest_lte(ClassifiedValues *cv, int kls) nogil:
    """Returns the greatest value less-than-or-equal to the given class"""
    cdef int idx = 0
    cdef float last

    for idx in range(cv.num_classes):
        if cv.classes[idx] > kls:
            idx -= 1
            break
    return cv.values[idx]


cdef class ClassedValues:
    cdef int[::1] classes
    cdef float[::1] values
    cdef int num_classes, min_class, max_class

    def __init__(self, pairs):
        self.num_classes = len(pairs)
        self.classes = np.array([x[0] for x in pairs], dtype='i')
        self.values = np.array([x[1] for x in pairs], dtype='f')
        self.min_class = min(self.classes)
        self.max_class = max(self.classes)

    @cython.initializedcheck(False)
    cdef float get(self, int kls, float default) nogil:
        cdef int idx;

        if kls < self.min_class or kls > self.max_class:
            return default
        for idx in range(self.num_classes):
            if self.classes[idx] == kls:
                return self.values[idx]
        return default

    @cython.initializedcheck(False)
    cdef float get_greatest_lte(self, int kls) nogil:
        """Returns the greatest value less-than-or-equal to the given class"""
        cdef int idx = 0
        cdef float last

        for idx in range(len(self.classes)):
            if self.classes[idx] > kls:
                idx -= 1
                break
        return self.values[idx]

    def print(self):
        for i in range(len(self.classes)):
            print('%d: %f' % (self.classes[i], self.values[i]))


cdef inline int round_to_int(float f) nogil:
    return <int> (f + 0.5)


DISEASE_PARAMS = (
    'p_susceptibility', 'p_symptomatic', 'p_severe', 'p_critical', 'p_hospital_death',
    'p_fatal', 'p_hospital_death_no_beds', 'p_icu_death_no_beds',
    'p_death_outside_hospital', 'p_asymptomatic_infection',
    'infectiousness_multiplier', 'mean_incubation_duration',
    'mean_duration_from_onset_to_death', 'mean_duration_from_onset_to_recovery',
    'ratio_of_duration_before_hospitalisation', 'ratio_of_duration_in_ward',
    'p_mask_protects_wearer', 'p_mask_protects_others', 'variants',
)

cdef struct Variant:
    float p_hospital_death
    float p_icu_death_no_beds, p_hospital_death_no_beds
    float mean_incubation_duration
    float mean_duration_from_onset_to_death
    float mean_duration_from_onset_to_recovery
    float ratio_of_duration_before_hospitalisation
    float ratio_of_duration_in_ward
    float infectiousness_multiplier
    float p_asymptomatic_infection

    ClassifiedValues p_susceptibility
    ClassifiedValues p_symptomatic
    ClassifiedValues p_severe
    ClassifiedValues p_critical
    ClassifiedValues p_fatal
    ClassifiedValues p_death_outside_hospital
    ClassifiedValues infectiousness_over_time

    float p_mask_protects_wearer
    float p_mask_protects_others

cdef variant_init(Variant *self, object params):
    self.p_hospital_death = params['p_hospital_death']
    self.p_hospital_death_no_beds = params['p_hospital_death_no_beds']
    self.p_icu_death_no_beds = params['p_icu_death_no_beds']
    self.infectiousness_multiplier = params['infectiousness_multiplier']
    self.p_asymptomatic_infection = params['p_asymptomatic_infection']

    self.mean_incubation_duration = params['mean_incubation_duration']
    self.mean_duration_from_onset_to_death = params['mean_duration_from_onset_to_death']
    self.mean_duration_from_onset_to_recovery = params['mean_duration_from_onset_to_recovery']
    self.ratio_of_duration_in_ward = params['ratio_of_duration_in_ward']
    self.ratio_of_duration_before_hospitalisation = params['ratio_of_duration_before_hospitalisation']

    cv_init(&self.p_susceptibility, params['p_susceptibility'])
    cv_init(&self.p_symptomatic, params['p_symptomatic'])
    cv_init(&self.p_severe, params['p_severe'])
    cv_init(&self.p_critical, params['p_critical'])
    cv_init(&self.p_fatal, params['p_fatal'])
    cv_init(&self.p_death_outside_hospital, params['p_death_outside_hospital'])

    self.p_mask_protects_others = params['p_mask_protects_others']
    self.p_mask_protects_wearer = params['p_mask_protects_wearer']

    cv_init(&self.infectiousness_over_time, INFECTIOUSNESS_OVER_TIME)


cdef variant_free(Variant *self):
    cv_free(&self.p_susceptibility)
    cv_free(&self.p_symptomatic)
    cv_free(&self.p_severe)
    cv_free(&self.p_critical)
    cv_free(&self.p_fatal)
    cv_free(&self.p_death_outside_hospital)
    cv_free(&self.infectiousness_over_time)


cdef class Disease:
    cdef Variant *variants
    cdef object variant_names
    cdef int nr_variants

    def __init__(self, params):
        self.variant_names = []
        self.nr_variants = 1 + len(params['variants'])
        self.variants = <Variant *> PyMem_Malloc(sizeof(Variant) * self.nr_variants)

        # Wild-type
        variant_init(&self.variants[0], params)
        self.variant_names.append('wild-type')

        for idx, variant in enumerate(params['variants']):
            v_params = params.copy()
            v_params.update(variant)
            variant_init(&self.variants[idx + 1], v_params)
            self.variant_names.append(variant['name'])

    def __dealloc__(self):
        for idx in range(self.nr_variants):
            variant_free(&self.variants[idx])
        PyMem_Free(self.variants)

    @classmethod
    def from_variables(cls, variables):
        args = []
        for name in DISEASE_PARAMS:
            args.append(variables[name])
        return cls(*args)

    cdef float get_source_infectiousness(self, Person *source) nogil:
        cdef int day
        cdef ClassifiedValues *iot

        if source.state == PersonState.INCUBATION:
            day = -source.days_left
        elif source.state == PersonState.ILLNESS:
            day = source.day_of_illness
        else:
            return 0
        iot = &self.variants[source.variant_idx].infectiousness_over_time
        return cv_get(iot, day, 0)

    cdef bint did_infect(self, Person *person, Context context, Person *source, float mask_p) nogil:
        cdef float source_infectiousness = self.get_source_infectiousness(source)
        cdef Variant *variant = &self.variants[source.variant_idx]
        cdef float p_susceptibility
        cdef bint infection
        cdef float p, a, b

        p_susceptibility = cv_get_greatest_lte(&variant.p_susceptibility, person.age)

        if source.symptom_severity == SymptomSeverity.ASYMPTOMATIC:
            source_infectiousness *= variant.p_asymptomatic_infection

        p = source_infectiousness * p_susceptibility * variant.infectiousness_multiplier
        infection = context.random.chance(p)
        if not infection:
            return False

        # If infection would've happened, let's see if masks saved the day.
        if mask_p:
            # (A or B) = p(A) + p(B) - p(A and B)
            a = mask_p * variant.p_mask_protects_others
            b = mask_p * variant.p_mask_protects_wearer
            p = a + b - a * b
            if context.random.chance(p):
                return False

        return True

    cdef int get_exposed_people(self, Person *person, Contact *contacts, Context context) nogil:
        # Detected people are quarantined
        if person.was_detected:
            return 0

        # If we are not infectious today, we expose 0 people.
        if not self.get_source_infectiousness(person):
            return 0

        if person.state == PersonState.INCUBATION:
            return context.pop.get_contacts(person, contacts, context)
        elif person.state == PersonState.ILLNESS:
            # Asymptomatic people infect others without knowing it
            if person.symptom_severity == SymptomSeverity.ASYMPTOMATIC:
                return context.pop.get_contacts(person, contacts, context)
            else:
                # People with mild or more severe symptoms restrict their movement
                return context.pop.get_contacts(person, contacts, context, factor=0.5, limit=5)

        return 0

    cdef bint dies_in_hospital(self, Person *person, Context context, bint care_available) nogil:
        cdef Variant *variant = &self.variants[person.variant_idx]
        cdef float chance = 0

        if person.symptom_severity == SymptomSeverity.FATAL:
            return True
        elif person.symptom_severity == SymptomSeverity.CRITICAL:
            if care_available:
                return False
            else:
                chance = variant.p_icu_death_no_beds
        elif person.symptom_severity == SymptomSeverity.SEVERE:
            if care_available:
                return False
            else:
                chance = variant.p_hospital_death_no_beds

        return context.random.chance(chance)


    cdef int get_incubation_days(self, Person *person, Context context) nogil:
        # gamma distribution, mean 5.1 days
        # Source: https://doi.org/10.25561/77731

        # μ = 5.1
        # cv = 0.86
        cdef Variant *variant = &self.variants[person.variant_idx]
        cdef float f = context.random.gamma(variant.mean_incubation_duration, 0.86)
        cdef int days = round_to_int(f)  # Round to nearest integer
        return days


    cdef float get_days_from_onset_to_removed(self, Person *person, Context context) nogil:
        cdef float mu, cv, f
        cdef Variant *variant = &self.variants[person.variant_idx]

        if person.symptom_severity == SymptomSeverity.FATAL:
            # source: https://www.imperial.ac.uk/mrc-global-infectious-disease-analysis/covid-19/report-13-europe-npi-impact/
            mu = variant.mean_duration_from_onset_to_death
            cv = 0.45
        else:
            mu = variant.mean_duration_from_onset_to_recovery
            cv = 0.45

        return context.random.gamma(mu, cv)


    cdef int get_illness_days(self, Person *person, Context context) nogil:
        cdef Variant *variant = &self.variants[person.variant_idx]
        cdef float f

        f = person.days_from_onset_to_removed
        # Asymptomatic and mild spend all of the days in the illness state.
        # Others spend the rest in hospitalization and in ICU.
        if person.symptom_severity not in (SymptomSeverity.ASYMPTOMATIC, SymptomSeverity.MILD):
            f *= variant.ratio_of_duration_before_hospitalisation

        return round_to_int(f)

    cdef int get_hospitalization_days(self, Person *person, Context context) nogil:
        cdef Variant *variant = &self.variants[person.variant_idx]
        cdef float f

        if person.symptom_severity == SymptomSeverity.SEVERE:
            f = person.days_from_onset_to_removed * (1 - variant.ratio_of_duration_before_hospitalisation)
        elif person.symptom_severity in (SymptomSeverity.FATAL, SymptomSeverity.CRITICAL):
            f = person.days_from_onset_to_removed * variant.ratio_of_duration_in_ward
        else:
            f = 0

        return round_to_int(f)

    cdef int get_icu_days(self, Person *person, Context context) nogil:
        cdef Variant *variant = &self.variants[person.variant_idx]
        cdef float f

        if person.symptom_severity in (SymptomSeverity.FATAL, SymptomSeverity.CRITICAL):
            f = 1 - variant.ratio_of_duration_in_ward - variant.ratio_of_duration_before_hospitalisation
            f *= person.days_from_onset_to_removed
        else:
            f = 0

        return round_to_int(f)

    @cython.cdivision(True)
    cdef SymptomSeverity get_symptom_severity(self, Person *person, Context context) nogil:
        cdef Variant *variant = &self.variants[person.variant_idx]
        cdef SymptomSeverity severity
        cdef int i, days
        cdef float syc, sc, cc, fc, ohc, dohc, val, vmod

        val = context.random.get()

        vmod = 1.0
        if person.day_of_vaccination >= 0:
            days = context.day - person.day_of_vaccination
            # FIXME: Parametrize
            if days > 14:
                vmod *= (1 - 0.90)  # Efficacy of 90 %

        syc = cv_get_greatest_lte(&variant.p_symptomatic, person.age)
        if val >= syc:
            return SymptomSeverity.ASYMPTOMATIC

        sc = cv_get_greatest_lte(&variant.p_severe, person.age)
        if val >= sc * vmod:
            return SymptomSeverity.MILD

        cc = cv_get_greatest_lte(&variant.p_critical, person.age)
        if val >= cc * vmod:
            return SymptomSeverity.SEVERE

        fc = cv_get_greatest_lte(&variant.p_fatal, person.age)
        if val >= fc * vmod:
            return SymptomSeverity.CRITICAL

        person.place_of_death = PlaceOfDeath.DEATH_IN_HOSPITAL
        dohc = cv_get_greatest_lte(&variant.p_death_outside_hospital, person.age)
        if dohc:
            if context.random.chance(dohc):
                person.place_of_death = PlaceOfDeath.DEATH_OUTSIDE_HOSPITAL

        return SymptomSeverity.FATAL


cdef struct ContactProbability:
    ContactPlace place
    int contact_age_min, contact_age_max
    double cum_p
    float mask_p


cdef struct AgeContactProbabilities:
    ContactProbability *probabilities
    int count


cdef class MobilityFactor:
    cdef public ContactPlace place
    cdef public int min_age
    cdef public int max_age
    cdef public float mobility_factor

    def __init__(self, place, min_age, max_age, mobility_factor):
        self.place = place
        self.min_age = min_age
        self.max_age = max_age
        self.mobility_factor = mobility_factor


cdef class ContactMatrix:
    cdef object contact_df  # pandas.DataFrame
    cdef object mask_probabilities  # pandas.DataFrame
    cdef double[::1] nr_contacts_by_age
    cdef AgeContactProbabilities *p_by_age
    cdef int nr_ages
    cdef list mobility_factors

    cdef float mobility_factor
    cdef object stats  # pandas.DataFrame

    def __init__(self, contacts_per_day, nr_ages):
        cdef int age

        self.nr_contacts_by_age = np.zeros(nr_ages, dtype=np.double)
        self.contact_df = contacts_per_day.copy(deep=True)
        self.nr_ages = nr_ages
        self.mobility_factor = 1.0
        self.mobility_factors = []

        cdef AgeContactProbabilities *acp
        self.p_by_age = <AgeContactProbabilities *> PyMem_Malloc(nr_ages * sizeof(AgeContactProbabilities))

        s = self.contact_df.groupby('participant_age').size()
        for age, count in s.items():
            acp = self.p_by_age + age
            acp.count = count
            acp.probabilities = <ContactProbability *> PyMem_Malloc(acp.count * sizeof(ContactProbability))

        self.generate_mask_probability_matrix()
        self.generate_contact_probabilities()

    def generate_contact_statistics(self, df):
        # df = df.groupby(['place_type', 'participant_age']).sum().reset_index()
        age_groups = pd.interval_range(0, 80, freq=10, closed='left')
        age_groups = age_groups.append(pd.Index([pd.Interval(80, 101, closed='left')]))
        df = df.copy()
        df['pgrp'] = pd.cut(df['participant_age'], age_groups)
        df = df.groupby(['place_type', 'pgrp', 'contact_age'])['contacts'].mean().reset_index()
        df = df.rename(columns=dict(pgrp='participant_age'))
        df['cgrp'] = pd.cut(df['contact_age'].map(lambda x: x[0]), age_groups)
        df = df.groupby(['participant_age', 'cgrp', 'place_type'])['contacts'].sum().reset_index()
        df = df.rename(columns=dict(cgrp='contact_age'))
        df = df[['participant_age', 'contact_age', 'place_type', 'contacts']]
        self.stats = df

        df = df.groupby(['participant_age', 'contact_age'])['contacts'].sum().unstack('contact_age')
        df.columns = df.columns.to_list()
        df.columns = df.columns.to_tuples()
        df['total'] = df.sum(axis=1)
        print(df)

        df = self.stats
        df = df[df.participant_age == pd.Interval(30, 40, closed='left')]
        df = df.groupby(['place_type', 'contact_age']).sum().unstack('contact_age')
        print(df)

    def generate_mask_probability_matrix(self):
        places = list(CONTACT_PLACE_TO_STR.values())
        places.remove('all')
        ages = range(self.nr_ages)
        self.mask_probabilities = pd.DataFrame(0.0, index=ages, columns=places)

    def generate_contact_probabilities(self):
        cdef int age, i
        cdef AgeContactProbabilities *acp
        cdef ContactProbability *cp

        # pc = PerfCounter('cp', show_time_to_last=True)

        for age in range(self.nr_ages):
            acp = self.p_by_age + age
            acp.count = 0

        df = self.contact_df.copy()
        # pc.display('copy')

        for mf in self.mobility_factors:
            if mf.mobility_factor == 1.0:
                continue
            filters = (df.participant_age >= mf.min_age) & (df.participant_age <= mf.max_age)
            if mf.place != ContactPlace.ALL:
                filters &= df.place_type == CONTACT_PLACE_TO_STR[mf.place]
            df.loc[filters, 'contacts'] *= mf.mobility_factor
        # pc.display('apply mf')

        # self.generate_contact_statistics(df)

        total_contacts = df.groupby('participant_age')['contacts'].sum()
        for age, count in total_contacts.items():
            self.nr_contacts_by_age[age] = count

        df = df.set_index(['place_type', 'participant_age', 'contact_age']).sort_index()
        df = df.unstack('participant_age')
        df.columns = df.columns.droplevel(0)

        df = df.divide(total_contacts, axis=1).cumsum()

        str_to_place = {val: key for key, val in CONTACT_PLACE_TO_STR.items()}

        # pc.display('mangle')

        for age in df.columns:
            s = df[age].to_dict()
            mask_probabilities = self.mask_probabilities.iloc[age].to_dict()

            for (place, (contact_age_min, contact_age_max)), cum_p in s.items():
                acp = self.p_by_age + age
                cp = acp.probabilities + acp.count
                cp.place = str_to_place[place]
                cp.contact_age_min = contact_age_min
                cp.contact_age_max = contact_age_max
                cp.cum_p = cum_p
                cp.mask_p = mask_probabilities[place]
                acp.count += 1

        # pc.display('generate acp')


    def __dealloc__(self):
        cdef AgeContactProbabilities *acp
        cdef int i

        for i in range(self.nr_ages):
            acp = self.p_by_age + i
            PyMem_Free(acp.probabilities)

        PyMem_Free(self.p_by_age)

    def set_mobility_factor(self, factor, place=None, min_age=None, max_age=None):
        self.mobility_factor = factor
        if place == None:
            place = ContactPlace.ALL
        if min_age == None:
            min_age = 0
        if max_age == None:
            max_age = self.nr_ages - 1
        for mf in self.mobility_factors:
            if mf.place == place and mf.min_age == min_age and mf.max_age == max_age:
                mf.mobility_factor = factor
                break
        else:
            mf = MobilityFactor(place, min_age, max_age, factor)
            self.mobility_factors.append(mf)

        self.generate_contact_probabilities()

    def set_mask_probability(self, p, place=None, min_age=None, max_age=None):
        if min_age == None:
            min_age = 0
        if max_age == None:
            max_age = self.nr_ages - 1

        df = self.mask_probabilities
        filters = (df.index >= min_age) & (df.index <= max_age)
        if place == None:
            places = list(CONTACT_PLACE_TO_STR.keys())
            places.remove(ContactPlace.ALL)
        else:
            places = [place]

        places_str = [CONTACT_PLACE_TO_STR[x] for x in places]
        df.loc[filters, places_str] = p

    cdef ContactProbability * get_one_contact(self, Person *person, Context context) nogil:
        cdef AgeContactProbabilities *acp
        cdef ContactProbability *cp
        cdef double p
        cdef int age, i

        acp = self.p_by_age + person.age
        p = context.random.get()
        for i in range(acp.count):
            cp = acp.probabilities + i
            if p < cp.cum_p:
                return cp

        context.problem = SimulationProblem.CONTACT_PROBABILITY_FAILURE
        return NULL

    @cython.cdivision(True)
    @cython.initializedcheck(False)
    cdef int get_nr_contacts(self, Person *person, Context context, float factor, int limit) nogil:
        cdef float f

        f = context.random.lognormal(0, 0.5) * self.nr_contacts_by_age[person.age]
        f *= factor
        if f < 1:
            f = 1
        cdef int nr_contacts = <int> f - 1

        if nr_contacts > limit:
            nr_contacts = limit

        return nr_contacts


cdef class Population:
    # Agents
    cdef Person *people
    cdef int total_people

    # Indexes
    cdef int32[::1] people_sorted_by_age
    cdef int32[::1] age_start

    # Stats
    cdef int[::1] infected, detected, all_detected, all_infected, hospitalized, \
        in_icu, cum_hospitalized, cum_icu, dead, susceptible, recovered, vaccinated
    cdef int nr_ages

    cdef int[::1] daily_contacts
    cdef cnp.ndarray age_groups

    cdef ContactMatrix contact_matrix

    cdef list weekly_infections
    # Effects of interventions
    cdef int limit_mass_gatherings

    def __init__(self, age_structure, contacts_per_day, age_groups):
        self.nr_ages = age_structure.index.max() + 1

        age_counts = np.empty(self.nr_ages, dtype=np.int32)
        for age, count in age_structure.items():
            age_counts[age] = count

        self.limit_mass_gatherings = 0

        self._init_stats(age_counts)
        self._create_agents(age_counts)

        self.weekly_infections = []
        self.contact_matrix = ContactMatrix(contacts_per_day, self.nr_ages)

        """
        grps = dict()
        c = 0
        for age, grp in age_groups:
            if grp not in grps:
                grps[grp] = c
                c += 1
        self.age_groups_idx = np.array()

        self.age_groups = np.array([x[1] for x in age_groups])
        """

    def _init_stats(self, age_counts):
        cdef int nr_ages = self.nr_ages

        self.susceptible = age_counts
        self.infected = np.zeros(nr_ages, dtype=np.int32)
        self.detected = np.zeros(nr_ages, dtype=np.int32)
        self.all_detected = np.zeros(nr_ages, dtype=np.int32)
        self.all_infected = np.zeros(nr_ages, dtype=np.int32)
        self.recovered = np.zeros(nr_ages, dtype=np.int32)
        self.hospitalized = np.zeros(nr_ages, dtype=np.int32)
        self.in_icu = np.zeros(nr_ages, dtype=np.int32)
        self.dead = np.zeros(nr_ages, dtype=np.int32)
        self.vaccinated = np.zeros(nr_ages, dtype=np.int32)
        self.daily_contacts = np.zeros(NR_CONTACT_PLACES, dtype=np.int32)

    cdef void _free_people(self) nogil:
        cdef Person * p

        for i in range(self.total_people):
            p = &self.people[i]
            person_dealloc(p)

    def __dealloc__(self):
        self._free_people()
        PyMem_Free(self.people)

    cdef _create_agents(self, age_counts):
        cdef int idx, person_idx, age
        cdef Person * p
        cdef cnp.ndarray[int] people_idx

        total = 0
        for age, count in enumerate(age_counts):
            total += count

        self.people_sorted_by_age = np.empty(total, dtype=np.int32)
        self.age_start = np.empty(self.nr_ages, dtype=np.int32)

        # Initialize list of people in random order
        people_idx = np.array(np.arange(0, total), dtype='i')
        np.random.shuffle(people_idx)

        people = <Person *> PyMem_Malloc(total * sizeof(Person))
        memset(people, 0, total * sizeof(Person))
        idx = 0
        for age, count in enumerate(age_counts):
            self.age_start[age] = idx
            for i in range(count):
                person_idx = people_idx[idx]
                p = people + person_idx
                person_init(p, person_idx, age)
                self.people_sorted_by_age[idx] = person_idx
                idx += 1
        self.total_people = total
        self.people = people

    def set_initial_state(self, ipc, Context context):
        cdef Person * person
        cdef int age

        i_incubating = ipc.incubating
        i_recovered_without_symptoms = i_incubating + ipc.recovered_without_illness()
        i_ill_at_home = i_recovered_without_symptoms + ipc.ill
        i_dead = i_ill_at_home + ipc.dead
        i_in_icu = i_dead + ipc.in_icu
        i_in_ward = i_in_icu + ipc.in_ward

        for i in range(ipc.were_incubating()):
            person = self.get_random_person(context)
            # to start with, take all people who were infected at some point
            # at simulation start time and infect them.
            # TODO: We want to scatter the infection progression, not have
            # everyone who is ill or incubating at simulation start to be at
            # the first day.
            person_infect(person, context, NULL, 0)

            if i < i_incubating:
                # these people have no symptoms yet
                continue
            if i < i_recovered_without_symptoms:
                person_recover(person, context)
                continue

            # Everyone from this point on became ill
            person_become_ill(person, context)

            if i < i_ill_at_home:
                # these people are ill in the beginning of simulation,
                # but not hospitalized
                continue

            if i < i_dead:
                # these people didn't make it
                person_die(person, context)
                continue

            if i < i_in_icu:
                # these people are in icu at simulation start
                person_hospitalize(person, context)
                person_transfer_to_icu(person, context)
                continue

            if i < i_in_ward:
                # these people are in hospital but not icu at simulation start
                person_hospitalize(person, context)
                continue

            # the rest recovered on their own at some point
            person_recover(person, context)

        for age in range(100):
            self.all_detected[age] = 0

        for i in range(ipc.confirmed_cases):
            # let's just spread these along all age groups
            # the age distribution of detected cases is not in any case used
            # in UI. TODO: for model validation, we need the age distribution.
            # We'd need to get case data for simulation start date
            # to set this correctly
            age = (100 + i) % 100
            self.all_detected[age] += 1

    @cython.cdivision(True)
    cdef Person * get_random_person(self, Context context) nogil:
        cdef int idx = context.random.getint() % self.total_people
        return self.people + idx

    @cython.cdivision(True)
    @cython.initializedcheck(False)
    cdef int get_contacts(self, Person *person, Contact *contacts, Context context, float factor=1.0, int limit=100) nogil:
        if self.limit_mass_gatherings and self.limit_mass_gatherings < limit:
            limit = self.limit_mass_gatherings

        cdef int nr_contacts
        # Contacts per day follows a lognormal distribution with
        # mean at `avg_contacts_per_day`.
        nr_contacts = self.contact_matrix.get_nr_contacts(person, context, factor, limit)
        if nr_contacts > MAX_CONTACTS:
            context.problem = SimulationProblem.TOO_MANY_CONTACTS
            return 0

        cdef Contact *c
        cdef ContactProbability *cp
        cdef int i, person_idx, idx_start, idx_end
        for i in range(nr_contacts):
            cp = self.contact_matrix.get_one_contact(person, context)
            if cp == NULL:
                continue
            idx_start = self.age_start[cp.contact_age_min]
            if cp.contact_age_max < self.nr_ages - 1:
                idx_end = self.age_start[cp.contact_age_max + 1]
            else:
                idx_end = self.total_people

            person_idx = self.people_sorted_by_age[idx_start + context.random.getint() % (idx_end - idx_start)]

            c = contacts + i
            c.person_idx = person_idx
            c.place = cp.place
            c.mask_p = cp.mask_p

            self.daily_contacts[<int> c.place] += 1

        return nr_contacts

    @cython.initializedcheck(False)
    cdef void infect(self, Person * person) nogil:
        age = person.age
        self.susceptible[age] -= 1
        self.infected[age] += 1
        self.all_infected[age] += 1

    @cython.initializedcheck(False)
    cdef void recover(self, Person * person) nogil:
        cdef int age = person.age
        self.infected[age] -= 1
        self.recovered[age] += 1
        if person.was_detected:
            self.detected[age] -= 1

    @cython.initializedcheck(False)
    cdef void detect(self, Person * person) nogil:
        cdef int age = person.age
        self.detected[age] += 1
        self.all_detected[age] += 1

    @cython.initializedcheck(False)
    cdef void hospitalize(self, Person * person) nogil:
        self.hospitalized[person.age] += 1

    @cython.initializedcheck(False)
    cdef void transfer_to_icu(self, Person * person) nogil:
        self.in_icu[person.age] += 1

    @cython.initializedcheck(False)
    cdef void release_from_icu(self, Person * person) nogil:
        self.in_icu[person.age] -= 1

    @cython.initializedcheck(False)
    cdef void release_from_hospital(self, Person * person) nogil:
        self.hospitalized[person.age] -= 1

    @cython.initializedcheck(False)
    cdef void die(self, Person * person) nogil:
        cdef int age = person.age
        self.infected[age] -= 1
        self.dead[age] += 1
        if person.was_detected:
            self.detected[age] -= 1

    @cython.initializedcheck(False)
    cdef void vaccinate(self, Person * person) nogil:
        self.vaccinated[person.age] += 1
        # FIXME: Change if vaccination changes transmission
        # if person.state == PersonState.SUSCEPTIBLE:
        #    self.susceptible[person.age] -= 1

    cdef infect_people(self, int count, int variant, Context context):
        cdef int idx
        cdef Person * person

        for i in range(count):
            for x in range(10):
                person = self.get_random_person(context)
                if person.state == PersonState.SUSCEPTIBLE:
                    break
            else:
                print('Unable to find person to infect')
                continue
            person_infect(person, context, NULL, variant)

    cdef infect_weekly(self, int amount, int variant, Context context):
        for w in self.weekly_infections:
            if w['variant'] == variant:
                break
        else:
            w = dict(variant=variant)
            self.weekly_infections.append(w)
        w['amount'] = amount

    cdef infect_people_daily(self, Context context):
        cdef float leftover
        cdef int amount_today

        for w in self.weekly_infections:
            leftover = w.get('leftover', 0.0) + w['amount'] / 7
            amount_today = <int> leftover

            if amount_today:
                self.infect_people(amount_today, w['variant'], context)
                leftover -= amount_today
            w['leftover'] = leftover

    cdef init_day(self, Context context):
        for i in range(NR_CONTACT_PLACES):
            self.daily_contacts[i] = 0
        self.infect_people_daily(context)


cdef class Context:
    cdef public Population pop
    cdef public HealthcareSystem hc
    cdef public Disease disease
    cdef public RandomPool random
    cdef SimulationProblem problem
    cdef Person * problem_person
    cdef int day
    cdef list interventions
    cdef str start_date
    cdef int total_infections, total_infectors, exposed_per_day
    cdef float cross_border_mobility_factor

    def __init__(self, population_params, healthcare_params, disease_params, str start_date, int random_seed=4321):
        self.random = RandomPool(random_seed)

        self.problem = SimulationProblem.NO_PROBLEMOS
        self.problem_person = NULL

        ipc = population_params.pop('initial_population_condition', None)
        self.pop = Population(**population_params)
        self.disease = Disease(disease_params)
        self.hc = HealthcareSystem(**healthcare_params)

        self.start_date = start_date
        self.day = 0
        self.interventions = []
        self.cross_border_mobility_factor = 1.0

        # Per day
        self.total_infectors = 0
        self.total_infections = 0
        self.exposed_per_day = 0

        if ipc and ipc.has_initial_state():
            self.pop.set_initial_state(ipc, self)

    cdef void set_problem(self, SimulationProblem problem, Person *p = NULL) nogil:
        self.problem = problem
        self.problem_person = p

    cdef str _get_log_msg(self, str s, int person_idx):
        cdef str ps
        cdef Person *p

        if person_idx >= 0:
            person = self.pop.people + person_idx
            ps = '[' + person_name(person) + '] '
        else:
            ps = ''
        return 'Day %d. %s%s' % (self.day, ps, s)

    cdef void error(self, str s, int person_idx=-1):
        cdef str out = self._get_log_msg(s, person_idx)
        print('[ERROR] %s' % out)

    cdef void trace(self, str s, int person_idx=-1):
        cdef str out = self._get_log_msg(s, person_idx)
        print(out)

    def get_date_for_today(self):
        d = date.fromisoformat(self.start_date)
        return (d + timedelta(days=self.day)).isoformat()

    def add_intervention(self, iv):
        self.interventions.append(iv)

    def generate_state(self):
        p = self.pop
        hc = self.hc
        # self.generate_age_grouped_state(p.infected)
        r = self.total_infections / self.total_infectors if self.total_infectors > 5 else 0
        s = dict(
            infected=p.infected, susceptible=p.susceptible,
            all_infected=p.all_infected,
            recovered=p.recovered, hospitalized=p.hospitalized,
            in_icu=p.in_icu,
            detected=p.detected, all_detected=p.all_detected,
            dead=p.dead, vaccinated=p.vaccinated,
            available_icu_units=hc.available_icu_units,
            available_hospital_beds=hc.available_beds,
            total_icu_units=hc.icu_units,
            r=r,
            exposed_per_day=self.exposed_per_day,
            ct_cases_per_day=self.hc.ct_cases_per_day,
            mobility_limitation=1 - self.pop.contact_matrix.mobility_factor,
        )
        daily_contacts = {}
        for i in range(NR_CONTACT_PLACES):
            daily_contacts[CONTACT_PLACE_TO_STR[i]] = self.pop.daily_contacts[i]
        s['daily_contacts'] = daily_contacts
        return s

    def get_population_stats(self, what):
        if what == 'dead':
            return np.array(self.pop.dead)
        if what == 'all_infected':
            return np.array(self.pop.all_infected)
        if what == 'all_detected':
            return np.array(self.pop.all_detected)
        raise Exception()

    def find_variant(self, variant_str):
        if variant_str is None:
            variant_idx = 0
        else:
            for idx, vn in enumerate(self.disease.variant_names):
                if variant_str == vn:
                    variant_idx = idx
                    break
            else:
                raise Exception('Variant %s not found' % variant_str)
        return variant_idx

    def apply_intervention(self, iv):
        params = iv.get_param_values()
        if iv.type == 'test-all-with-symptoms':
            # Start testing everyone who shows even mild symptoms
            self.hc.set_testing_mode(TestingMode.ALL_WITH_SYMPTOMS)
        elif iv.type == 'test-only-severe-symptoms':
            # Test only those who show severe or critical symptoms
            self.hc.set_testing_mode(TestingMode.ONLY_SEVERE_SYMPTOMS, params['mild_detection_rate'] / 100.0)
        elif iv.type == 'test-with-contact-tracing':
            # Test only those who show severe or critical symptoms
            self.hc.set_testing_mode(TestingMode.ALL_WITH_SYMPTOMS_CT, params['efficiency'] / 100.0)
        elif iv.type == 'build-new-icu-units':
            self.hc.icu_units += params['units']
            self.hc.available_icu_units += params['units']
        elif iv.type == 'build-new-hospital-beds':
            self.hc.beds += params['beds']
            self.hc.available_beds += params['beds']
        elif iv.type == 'import-infections':
            # Introduce infections from elsewhere
            self.pop.infect_people(params['amount'], self.find_variant(params.get('variant')), self)
        elif iv.type == 'import-infections-weekly':
            # Introduce infections from elsewhere
            self.pop.infect_weekly(params['weekly_amount'], self.find_variant(params.get('variant')), self)
        # elif iv.type == 'limit-cross-border-mobility':
        #    # Introduce infections from elsewhere
        #    self.context.cross_border_mobility_factor = (100 - value) / 100.0
        # elif iv.type == 'limit-mass-gatherings':
        #    self.pop.limit_mass_gatherings = value
        elif iv.type == 'limit-mobility':
            reduction = params['reduction']
            reduction = (100 - reduction) / 100.0

            min_age = params.get('min_age')
            max_age = params.get('max_age')

            str_to_place = {val: key for key, val in CONTACT_PLACE_TO_STR.items()}
            place = params.get('place')
            if place is not None:
                place = str_to_place[place]

            self.pop.contact_matrix.set_mobility_factor(
                factor=reduction,
                min_age=min_age,
                max_age=max_age,
                place=place,
            )
        elif iv.type == 'wear-masks':
            p = params['share_of_contacts'] / 100.0
            min_age = params.get('min_age')
            max_age = params.get('max_age')

            str_to_place = {val: key for key, val in CONTACT_PLACE_TO_STR.items()}
            place = params.get('place')
            if place is not None:
                place = str_to_place[place]

            self.pop.contact_matrix.set_mask_probability(
                p=p,
                min_age=min_age,
                max_age=max_age,
                place=place,
            )
        elif iv.type == 'vaccinate':
            nr = params['weekly_vaccinations'] / 7
            min_age = params.get('min_age')
            max_age = params.get('max_age')

            self.hc.start_vaccinating(nr, min_age, max_age, self)
        else:
            raise Exception()

    cdef void import_infections(self):
        cdef int count = 20

        for i in range(count):
            pass

    cdef inline void _process_person(self, Person *person) nogil:
        if person.state in (PersonState.RECOVERED, PersonState.DEAD) and not person.included_in_totals:
            self.total_infectors += 1
            self.total_infections += person.other_people_infected
            person.included_in_totals = 1

        if not person.is_infected:
            return

        person_advance(person, self)

        self.exposed_per_day += person.other_people_exposed_today

    @cython.cdivision(True)
    cdef void _iterate_people(self) nogil:
        cdef int total_people = self.pop.total_people
        cdef Person *people = self.pop.people
        cdef int i, start_idx, person_idx
        cdef Person *person

        start_idx = self.random.getint() % total_people
        for i in range(total_people):
            person_idx = (start_idx + i) % total_people
            person = people + person_idx
            self._process_person(person)

    cdef void _iterate(self):
        self.pop.init_day(self)
        self.import_infections()

        self.total_infectors = 0
        self.total_infections = 0
        self.exposed_per_day = 0

        self.hc.iterate(self)

        self._iterate_people()

        #if self.get_date_for_today() == '2020-05-16':
        #    self.dump_state()

        self.day += 1

    def iterate(self):
        today = self.get_date_for_today()
        for iv in self.interventions:
            if iv.date == today:
                self.apply_intervention(iv)
        self._iterate()
        if self.problem != SimulationProblem.NO_PROBLEMOS:
            raise SimulationFailed(PROBLEM_TO_STR[self.problem])

    cdef void _dump_people_in_state(self, PersonState state):
        cdef Person *p
        cdef int i

        for i in range(self.total_people):
            p = self.pop.people + i
            if p.state == state:
                print(person_str(p, self.day))

    cdef void dump_state(self):
        cdef Person *p
        cdef int i, max_contacts = 0
        cdef cnp.ndarray[int] mc = np.empty(self.total_people, dtype='i')

        for state in (PersonState.INCUBATION, PersonState.ILLNESS, PersonState.HOSPITALIZED, PersonState.IN_ICU):
            print('%s:\n' % STATE_TO_STR[state])
            self._dump_people_in_state(state)
            print('=' * 80)
            print()

        for i in range(self.total_people):
            p = self.pop.people + i
            mc[i] = p.max_contacts_per_day
        print('Max. contacts per day:')
        for c1, c2 in pd.Series(mc).value_counts().sort_index().items():
            print('%4d %d' % (c1, c2))

    cpdef sample(self, str what, int age, str severity=None):
        cdef int sample_size = 10000
        cdef Person p = self.pop.people[0]
        cdef cnp.ndarray[int] out
        cdef int i

        p.age = age
        if severity is not None:
            p.symptom_severity = STR_TO_SEVERITY[severity]
        else:
            p.symptom_severity = SymptomSeverity.MILD

        SUPPORTED = set([
            'infectiousness', 'contacts_per_day', 'symptom_severity', 'incubation_period',
            'illness_period', 'hospitalization_period', 'icu_period', 'onset_to_removed_period',
        ])
        if what not in SUPPORTED:
            raise Exception('unknown sample type. supported: %s' % ', '.join(SUPPORTED))

        if what == 'infectiousness':
            days = list(range(-100, 100))
            vals = [self.disease.get_infectiousness_over_time(day) for day in days]
            ret = np.rec.fromarrays((days, vals), names=('day', 'val'))
            return ret

        cdef Contact contacts[MAX_CONTACTS]

        out = np.empty(sample_size, dtype='i')
        with nogil:
            if what == 'contacts_per_day':
                for i in range(sample_size):
                    out[i] = self.pop.get_contacts(&p, contacts, self)
            elif what == 'symptom_severity':
                for i in range(sample_size):
                    self.disease.get_symptom_severity(&p, self)
                    out[i] = p.symptom_severity
            elif what == 'incubation_period':
                for i in range(sample_size):
                    out[i] = self.disease.get_incubation_days(&p, self)
            elif what == 'illness_period':
                for i in range(sample_size):
                    p.days_from_onset_to_removed = self.disease.get_days_from_onset_to_removed(&p, self)
                    out[i] = self.disease.get_illness_days(&p, self)
            elif what == 'hospitalization_period':
                for i in range(sample_size):
                    p.days_from_onset_to_removed = self.disease.get_days_from_onset_to_removed(&p, self)
                    out[i] = self.disease.get_hospitalization_days(&p, self)
            elif what == 'icu_period':
                for i in range(sample_size):
                    p.days_from_onset_to_removed = self.disease.get_days_from_onset_to_removed(&p, self)
                    out[i] = self.disease.get_icu_days(&p, self)
            elif what == 'onset_to_removed_period':
                for i in range(sample_size):
                    out[i] = round_to_int(self.disease.get_days_from_onset_to_removed(&p, self))

        return out


def make_iv(context, intervention, date_str=None, value=None):
    if date_str is not None:
        day = (date.fromisoformat(date_str) - date.fromisoformat(context.start_date)).days
    else:
        day = 0
    return Intervention(day, intervention, value or 0)
