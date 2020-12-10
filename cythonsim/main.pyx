# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: profile=False

import numpy as np
import pandas as pd
from collections import namedtuple
from datetime import date, timedelta
from cython.parallel import prange
from faker.providers.person.fi_FI import Provider as NameProvider

cimport cython
cimport openmp
from cpython.mem cimport PyMem_Malloc, PyMem_Free
from libc.stdlib cimport malloc, free
cimport numpy as cnp

from cythonsim.simrandom cimport RandomPool

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


cdef enum ContactPlace:
    HOME
    WORK
    SCHOOL
    TRANSPORT
    LEISURE
    OTHER


CONTACT_PLACE_TO_STR = {
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
}


class SimulationFailed(Exception):
    pass


DEF MAX_INFECTEES = 64
DEF MAX_CONTACTS = 128


cdef struct Person:
    int32 idx, infector
    uint8 age, has_immunity, is_infected, was_detected, queued_for_testing, \
        symptom_severity, state, included_in_totals
    int16 day_of_infection, days_left, other_people_infected, other_people_exposed_today, \
        day_of_illness
    int16 max_contacts_per_day

    float days_from_onset_to_removed
    uint8 nr_infectees
    int32 *infectees

    openmp.omp_lock_t lock


cdef struct Contact:
    int32 person_idx
    ContactPlace place


cdef void person_init(Person *self, int32 idx, uint8 age) nogil:
    self.idx = idx
    self.age = age
    self.is_infected = 0
    self.was_detected = 0
    self.has_immunity = 0
    self.days_left = 0
    self.day_of_illness = 0
    self.day_of_infection = 0
    self.queued_for_testing = 0
    self.other_people_infected = 0
    self.included_in_totals = 0
    self.days_from_onset_to_removed = 0
    self.symptom_severity = SymptomSeverity.ASYMPTOMATIC
    self.state = PersonState.SUSCEPTIBLE
    self.nr_infectees = 0
    self.max_contacts_per_day = 0
    self.infector = -1
    self.infectees = NULL

    openmp.omp_init_lock(&self.lock)


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

    return '%s: %d years, infection on day %d%s, %s, %s, days left %d, %sdetected %d, max. contacts %d (others infected %d%s)' % (
        name, self.age, self.day_of_infection, days_ago, STATE_TO_STR[self.state],
        SEVERITY_TO_STR[self.symptom_severity], self.days_left, queued, self.was_detected,
        self.max_contacts_per_day, self.other_people_infected, infectees
    )


cdef void person_infect(Person *self, Context context, Person *source=NULL) nogil:
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

    if context.hc.testing_mode == TestingMode.ALL_WITH_SYMPTOMS_CT:
        if self.infectees != NULL:
            context.set_problem(SimulationProblem.OTHER_FAILURE)
        else:
            self.infectees = <int32 *> malloc(sizeof(int32) * MAX_INFECTEES)
            if self.infectees == NULL:
                context.set_problem(SimulationProblem.MALLOC_FAILURE)

    context.pop.infect(self)


cdef bint person_expose(Person *self, Context context, Person *source) nogil:
    if self.is_infected or self.has_immunity:
        return False
    if context.disease.did_infect(self, context, source):
        person_infect(self, context, source)
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

        if person_expose(target, context, self):
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
    # This is a way to get long-lasting immunity.
    self.state = PersonState.DEAD
    context.pop.die(self)
    person_become_removed(self, context)


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
            if self.symptom_severity in (SymptomSeverity.SEVERE, SymptomSeverity.CRITICAL, SymptomSeverity.FATAL):
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
    cdef int32 tests_run_per_day
    cdef float p_detected_anyway
    cdef float p_successful_tracing
    cdef TestingMode testing_mode
    cdef list testing_queue
    cdef openmp.omp_lock_t lock

    def __init__(self, hospital_beds, icu_units):
        self.beds = hospital_beds
        self.icu_units = icu_units
        self.available_beds = hospital_beds
        self.available_icu_units = icu_units
        self.testing_mode = TestingMode.NO_TESTING
        self.testing_queue = []
        self.tests_run_per_day = 0
        self.p_detected_anyway = 0
        self.p_successful_tracing = 1.0
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
        cdef int idx

        queue = self.testing_queue
        self.tests_run_per_day = len(queue)
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

    cdef float get(self, int kls, float default) nogil:
        cdef int idx;

        if kls < self.min_class or kls > self.max_class:
            return default
        for idx in range(self.num_classes):
            if self.classes[idx] == kls:
                return self.values[idx]
        return default

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
    'p_infection', 'p_asymptomatic', 'p_severe', 'p_critical', 'p_hospital_death',
    'p_icu_death', 'p_hospital_death_no_beds', 'p_icu_death_no_beds',
    'mean_incubation_duration',
    'mean_duration_from_onset_to_death', 'mean_duration_from_onset_to_recovery',
    'ratio_of_duration_before_hospitalisation', 'ratio_of_duration_in_ward',
)

cdef class Disease:
    cdef float p_infection, p_asymptomatic, p_hospital_death
    cdef float p_icu_death_no_beds, p_hospital_death_no_beds
    cdef float mean_incubation_duration
    cdef float mean_duration_from_onset_to_death
    cdef float mean_duration_from_onset_to_recovery
    cdef float ratio_of_duration_before_hospitalisation
    cdef float ratio_of_duration_in_ward

    cdef ClassedValues p_severe
    cdef ClassedValues p_critical
    cdef ClassedValues infectiousness_over_time
    cdef ClassedValues p_icu_death

    def __init__(self,
        p_infection, p_asymptomatic, p_severe, p_critical, p_hospital_death,
        p_icu_death, p_hospital_death_no_beds, p_icu_death_no_beds,
        mean_incubation_duration,
        mean_duration_from_onset_to_death, mean_duration_from_onset_to_recovery,
        ratio_of_duration_before_hospitalisation, ratio_of_duration_in_ward,
    ):
        self.p_infection = p_infection
        self.p_asymptomatic = p_asymptomatic

        self.p_hospital_death = p_hospital_death
        self.p_hospital_death_no_beds = p_hospital_death_no_beds
        self.p_icu_death_no_beds = p_icu_death_no_beds

        self.mean_incubation_duration = mean_incubation_duration
        self.mean_duration_from_onset_to_death = mean_duration_from_onset_to_death
        self.mean_duration_from_onset_to_recovery = mean_duration_from_onset_to_recovery
        self.ratio_of_duration_in_ward = ratio_of_duration_in_ward
        self.ratio_of_duration_before_hospitalisation = ratio_of_duration_before_hospitalisation

        self.p_severe = ClassedValues(p_severe)
        self.p_critical = ClassedValues(p_critical)
        self.infectiousness_over_time = ClassedValues(INFECTIOUSNESS_OVER_TIME)
        self.p_icu_death = ClassedValues(p_icu_death)

    @classmethod
    def from_variables(cls, variables):
        args = []
        for name in DISEASE_PARAMS:
            args.append(variables[name])
        return cls(*args)


    cdef float get_infectiousness_over_time(self, int day) nogil:
        return self.infectiousness_over_time.get(day, 0) * self.p_infection


    cdef float get_source_infectiousness(self, Person *source) nogil:
        cdef int day

        if source.state == PersonState.INCUBATION:
            day = -source.days_left
        elif source.state == PersonState.ILLNESS:
            day = source.day_of_illness
        else:
            return 0
        return self.infectiousness_over_time.get(day, 0) * self.p_infection


    cdef bint did_infect(self, Person *person, Context context, Person *source) nogil:
        cdef float chance = self.get_source_infectiousness(source)
        # FIXME: Smaller chance for asymptomatic people?
        return context.random.chance(chance)


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
        cdef float chance = 0

        if person.symptom_severity == SymptomSeverity.FATAL:
            return True
        elif person.symptom_severity == SymptomSeverity.CRITICAL:
            if care_available:
                return False
            else:
                chance = self.p_icu_death_no_beds
        elif person.symptom_severity == SymptomSeverity.SEVERE:
            if care_available:
                return False
            else:
                chance = self.p_hospital_death_no_beds

        return context.random.chance(chance)


    cdef int get_incubation_days(self, Person *person, Context context) nogil:
        # gamma distribution, mean 5.1 days
        # Source: https://doi.org/10.25561/77731

        # μ = 5.1
        # cv = 0.86
        cdef float f = context.random.gamma(self.mean_incubation_duration, 0.86)
        cdef int days = round_to_int(f) # Round to nearest integer
        return days


    cdef float get_days_from_onset_to_removed(self, Person *person, Context context) nogil:
        cdef float mu, cv, f

        if person.symptom_severity == SymptomSeverity.FATAL:
            # source: https://www.imperial.ac.uk/mrc-global-infectious-disease-analysis/covid-19/report-13-europe-npi-impact/
            mu = self.mean_duration_from_onset_to_death
            cv = 0.45
        else:
            mu = self.mean_duration_from_onset_to_recovery
            cv = 0.45

        return context.random.gamma(mu, cv)

    cdef int get_illness_days(self, Person *person, Context context) nogil:
        cdef float f

        f = person.days_from_onset_to_removed
        # Asymptomatic and mild spend all of the days in the illness state.
        # Others spend the rest in hospitalization and in ICU.
        if person.symptom_severity not in (SymptomSeverity.ASYMPTOMATIC, SymptomSeverity.MILD):
            f *= self.ratio_of_duration_before_hospitalisation

        return round_to_int(f)

    cdef int get_hospitalization_days(self, Person *person, Context context) nogil:
        cdef float f

        if person.symptom_severity == SymptomSeverity.SEVERE:
            f = person.days_from_onset_to_removed * (1 - self.ratio_of_duration_before_hospitalisation)
        elif person.symptom_severity in (SymptomSeverity.FATAL, SymptomSeverity.CRITICAL):
            f = person.days_from_onset_to_removed * self.ratio_of_duration_in_ward
        else:
            f = 0

        return round_to_int(f)

    cdef int get_icu_days(self, Person *person, Context context) nogil:
        cdef float f

        if person.symptom_severity in (SymptomSeverity.FATAL, SymptomSeverity.CRITICAL):
            f = 1 - self.ratio_of_duration_in_ward - self.ratio_of_duration_before_hospitalisation
            f *= person.days_from_onset_to_removed
        else:
            f = 0

        return round_to_int(f)

    cdef SymptomSeverity get_symptom_severity(self, Person *person, Context context) nogil:
        cdef int i
        cdef float sc, cc, fc, val

        val = context.random.get()
        if val < self.p_asymptomatic:
            return SymptomSeverity.ASYMPTOMATIC

        val = (val - self.p_asymptomatic) / (1 - self.p_asymptomatic)

        sc = self.p_severe.get_greatest_lte(person.age)
        cc = self.p_critical.get_greatest_lte(person.age)
        fc = self.p_icu_death.get_greatest_lte(person.age)

        if val < fc * sc * cc:
            return SymptomSeverity.FATAL
        if val < sc * cc:
            return SymptomSeverity.CRITICAL
        if val < sc:
            return SymptomSeverity.SEVERE
        return SymptomSeverity.MILD


cdef struct ContactProbability:
    ContactPlace place
    int contact_age_min, contact_age_max
    double cum_p


cdef struct AgeContactProbabilities:
    ContactProbability *probabilities
    int count


cdef class ContactMatrix:
    cdef object contact_df  # pandas.DataFrame
    cdef double[::1] nr_contacts_by_age
    cdef AgeContactProbabilities *p_by_age
    cdef int nr_ages

    def __init__(self, contacts_per_day, nr_ages):
        cdef int age

        self.nr_contacts_by_age = np.zeros(nr_ages, dtype=np.double)
        self.contact_df = contacts_per_day.copy(deep=True)
        self.nr_ages = nr_ages

        cdef AgeContactProbabilities *acp
        self.p_by_age = <AgeContactProbabilities *> PyMem_Malloc(nr_ages * sizeof(AgeContactProbabilities))

        s = self.contact_df.groupby('participant_age').size()
        for (age_min, age_max), count in s.items():
            for age in range(age_min, age_max + 1):
                acp = self.p_by_age + age
                acp.count = count
                acp.probabilities = <ContactProbability *> PyMem_Malloc(acp.count * sizeof(ContactProbability))

        self.generate_probability_matrix()

    def generate_probability_matrix(self):
        cdef int age, i
        cdef AgeContactProbabilities *acp
        cdef ContactProbability *cp

        for age in range(self.nr_ages):
            acp = self.p_by_age + age
            acp.count = 0

        df = self.contact_df

        total_contacts = df.groupby('participant_age')['contacts'].sum()
        for (age_min, age_max), count in total_contacts.items():
            for age in range(age_min, age_max + 1):
                self.nr_contacts_by_age[age] = count

        df = df.set_index(['place_type', 'participant_age', 'contact_age']).sort_index()
        df = df.unstack('participant_age')
        df.columns = df.columns.droplevel(0)

        df = df.divide(total_contacts, axis=1).cumsum()

        str_to_place = {val: key for key, val in CONTACT_PLACE_TO_STR.items()}

        for col in df.columns:
            age_min, age_max = col
            s = df[col]
            for (place, (contact_age_min, contact_age_max)), cum_p in s.items():
                for age in range(age_min, age_max + 1):
                    acp = self.p_by_age + age
                    cp = acp.probabilities + acp.count
                    cp.place = str_to_place[place]
                    cp.contact_age_min = contact_age_min
                    cp.contact_age_max = contact_age_max
                    cp.cum_p = cum_p
                    acp.count += 1

    def __dealloc__(self):
        cdef AgeContactProbabilities *acp
        cdef int i

        for i in range(self.nr_ages):
            acp = self.p_by_age + i
            PyMem_Free(acp.probabilities)

        PyMem_Free(self.p_by_age)

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

        context.problem = SimulationProblem.OTHER_FAILURE
        return NULL

    @cython.cdivision(True)
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
        in_icu, dead, susceptible, recovered
    cdef int nr_ages

    cdef ContactMatrix contact_matrix

    # Effects of interventions
    cdef int limit_mass_gatherings
    cdef float population_mobility_factor

    def __init__(self, age_structure, contacts_per_day):
        self.nr_ages = age_structure.index.max() + 1

        age_counts = np.empty(self.nr_ages, dtype=np.int32)
        for age, count in age_structure.items():
            age_counts[age] = count

        self.limit_mass_gatherings = 0
        self.population_mobility_factor = 1.0

        self._init_stats(age_counts)
        self._create_agents(age_counts)

        self.contact_matrix = ContactMatrix(contacts_per_day, self.nr_ages)

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

        i_incubating = ipc.incubating
        i_recovered_without_symptoms = i_incubating + ipc.recovered_without_illness()
        i_dead = i_recovered_without_symptoms + ipc.dead
        i_in_icu = i_dead + ipc.in_icu
        i_in_ward = i_in_icu + ipc.in_ward

        for i in range(ipc.were_incubating()):
            person = self.get_random_person(context)
            # to start with, take all people who were infected at some point
            # at simulation start time and infect them.
            person_infect(person, context)

            if i < i_incubating:
                # these people have no symptoms yet
                continue
            if i < i_recovered_without_symptoms:
                person_recover(person, context)
                continue

            # Everyone from this point on became ill
            person_become_ill(person, context)

            if i < i_dead:
                # some of them didn't make it
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

    @cython.cdivision(True)
    cdef Person * get_random_person(self, Context context) nogil:
        cdef int idx = context.random.getint() % self.total_people
        return self.people + idx

    @cython.cdivision(True)
    cdef int get_contacts(self, Person *person, Contact *contacts, Context context, float factor=1.0, int limit=100) nogil:
        # Contacts per day follows a lognormal distribution with
        # mean at `avg_contacts_per_day`.
        cdef float f = factor * self.population_mobility_factor

        if self.limit_mass_gatherings and self.limit_mass_gatherings < limit:
            limit = self.limit_mass_gatherings

        cdef int nr_contacts

        nr_contacts = self.contact_matrix.get_nr_contacts(person, context, f, limit)
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

        return nr_contacts

    cdef void infect(self, Person * person) nogil:
        age = person.age
        self.susceptible[age] -= 1
        self.infected[age] += 1
        self.all_infected[age] += 1

    cdef void recover(self, Person * person) nogil:
        cdef int age = person.age
        self.infected[age] -= 1
        self.recovered[age] += 1
        if person.was_detected:
            self.detected[age] -= 1

    cdef void detect(self, Person * person) nogil:
        cdef int age = person.age
        self.detected[age] += 1
        self.all_detected[age] += 1

    cdef void hospitalize(self, Person * person) nogil:
        self.hospitalized[person.age] += 1

    cdef void transfer_to_icu(self, Person * person) nogil:
        self.in_icu[person.age] += 1

    cdef void release_from_icu(self, Person * person) nogil:
        self.in_icu[person.age] -= 1

    cdef void release_from_hospital(self, Person * person) nogil:
        self.hospitalized[person.age] -= 1

    cdef void die(self, Person * person) nogil:
        cdef int age = person.age
        self.infected[age] -= 1
        self.dead[age] += 1
        if person.was_detected:
            self.detected[age] -= 1


cdef class Intervention:
    cdef public int day
    cdef public str name
    cdef public int value

    def __init__(self, day, name, value):
        self.day = day
        self.name = name
        self.value = value


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
        self.disease = Disease(**disease_params)
        self.hc = HealthcareSystem(**healthcare_params)

        self.start_date = start_date
        self.day = 0
        self.interventions = []
        self.cross_border_mobility_factor = 1.0

        # Per day
        self.total_infectors = 0
        self.total_infections = 0
        self.exposed_per_day = 0

        if ipc:
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

    def add_intervention(self, day, name, value):
        if value is None:
            value = 0
        self.interventions.append(Intervention(day, name, value))


    def generate_state(self):
        p = self.pop
        hc = self.hc
        r = self.total_infections / self.total_infectors if self.total_infectors > 5 else 0
        s = dict(
            infected=p.infected, susceptible=p.susceptible,
            all_infected=p.all_infected,
            recovered=p.recovered, hospitalized=p.hospitalized,
            in_icu=p.in_icu,
            detected=p.detected, all_detected=p.all_detected,
            dead=p.dead,
            available_icu_units=hc.available_icu_units,
            available_hospital_beds=hc.available_beds,
            total_icu_units=hc.icu_units,
            r=r,
            exposed_per_day=self.exposed_per_day,
            tests_run_per_day=self.hc.tests_run_per_day,
            mobility_limitation=1 - self.pop.population_mobility_factor,
        )
        return s

    def get_population_stats(self, what):
        if what == 'dead':
            return np.array(self.pop.dead)
        if what == 'all_infected':
            return np.array(self.pop.all_infected)
        raise Exception()

    def infect_people(self, count):
        cdef int idx
        cdef Person * person

        for i in range(count):
            person = self.pop.get_random_person(self)
            person_infect(person, self)

    def apply_intervention(self, name, value):
        if name == 'test-all-with-symptoms':
            # Start testing everyone who shows even mild symptoms
            self.hc.set_testing_mode(TestingMode.ALL_WITH_SYMPTOMS)
        elif name == 'test-only-severe-symptoms':
            # Test only those who show severe or critical symptoms
            self.hc.set_testing_mode(TestingMode.ONLY_SEVERE_SYMPTOMS, value / 100.0)
        elif name == 'test-with-contact-tracing':
            # Test only those who show severe or critical symptoms
            self.hc.set_testing_mode(TestingMode.ALL_WITH_SYMPTOMS_CT, value / 100.0)
        elif name == 'build-new-icu-units':
            self.hc.icu_units += value
            self.hc.available_icu_units += value
        elif name == 'build-new-hospital-beds':
            self.hc.beds += value
            self.hc.available_beds += value
        elif name == 'import-infections':
            # Introduct infections from elsewhere
            count = value
            self.infect_people(count)
        elif name == 'limit-cross-border-mobility':
            # Introduct infections from elsewhere
            self.context.cross_border_mobility_factor = (100 - value) / 100.0
        elif name == 'limit-mass-gatherings':
            self.pop.limit_mass_gatherings = value
        elif name == 'limit-mobility':
            self.pop.population_mobility_factor = (100 - value) / 100.0
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
        for intervention in self.interventions:
            if intervention.day == self.day:
                # print(intervention.name)
                self.apply_intervention(intervention.name, intervention.value)

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
                    out[i] = self.disease.get_symptom_severity(&p, self)
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
