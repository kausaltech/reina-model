import hashlib
import json
import os
from contextlib import contextmanager

import flask
from flask import session

VARIABLE_OVERRIDE_SETS = {
    'turku': {
        'area_name': 'Varsinais-Suomi',
        'area_name_long': 'Varsinais-Suomen sairaanhoitopiiri',
        'hospital_beds': 900,
        'icu_units': 55,
        # 'start_date': '2020-09-01',
        'interventions': [
            ['test-all-with-symptoms', '2020-02-20'],
            ['test-only-severe-symptoms', '2020-03-15', 25],
            ['test-only-severe-symptoms', '2020-03-23', 50],
            ['test-all-with-symptoms', '2020-04-01'],
            ['test-with-contact-tracing', '2020-06-01', 10],
            ['test-with-contact-tracing', '2020-07-01', 20],
            ['test-with-contact-tracing', '2020-09-01', 60],
            # ['test-with-contact-tracing', '2020-12-01', 60],

            ['limit-mobility', '2020-03-23', 100, 7, 25, 'school'],
            ['limit-mobility', '2020-08-12', 0, 7, 25, 'school'],
            ['limit-mobility', '2020-12-19', 100, 7, 25, 'school'],
            ['limit-mobility', '2021-01-07', 0, 7, 25, 'school'],
            ['limit-mobility', '2021-01-07', 0, 7, 12, 'school'],
            ['limit-mobility', '2021-01-07', 100, 13, 25, 'school'],

            ['limit-mobility', '2020-03-15', 10, None, None, 'leisure'],
            ['limit-mobility', '2020-03-18', 20, None, None, 'leisure'],
            ['limit-mobility', '2020-03-20', 30, None, None, 'leisure'],
            ['limit-mobility', '2020-03-24', 40, None, None, 'leisure'],
            ['limit-mobility', '2020-03-30', 45, None, None, 'leisure'],
            ['limit-mobility', '2020-04-13', 50, None, None, 'leisure'],
            ['limit-mobility', '2020-04-20', 40, None, None, 'leisure'],
            ['limit-mobility', '2020-05-11', 30, None, None, 'leisure'],
            ['limit-mobility', '2020-06-01', 20, None, None, 'leisure'],
            ['limit-mobility', '2020-10-31', 10, None, None, 'leisure'],
            ['limit-mobility', '2020-12-11', 15, None, None, 'leisure'],

            ['limit-mobility', '2020-03-17', 10, None, None, 'work'],
            ['limit-mobility', '2020-03-19', 20, None, None, 'work'],
            ['limit-mobility', '2020-03-22', 30, None, None, 'work'],
            ['limit-mobility', '2020-03-26', 35, None, None, 'work'],
            ['limit-mobility', '2020-03-26', 35, None, None, 'work'],
            ['limit-mobility', '2020-04-09', 40, None, None, 'work'],
            ['limit-mobility', '2020-04-13', 50, None, None, 'work'],
            ['limit-mobility', '2020-04-20', 40, None, None, 'work'],
            ['limit-mobility', '2020-05-13', 30, None, None, 'work'],
            ['limit-mobility', '2020-06-01', 15, None, None, 'work'],
            ['limit-mobility', '2020-06-19', 30, None, None, 'work'],
            ['limit-mobility', '2020-06-19', 30, None, None, 'work'],
            ['limit-mobility', '2020-06-19', 30, None, None, 'work'],
            ['limit-mobility', '2020-07-01', 35, None, None, 'work'],
            ['limit-mobility', '2020-08-13', 25, None, None, 'work'],
            ['limit-mobility', '2020-08-24', 20, None, None, 'work'],
            ['limit-mobility', '2020-09-11', 15, None, None, 'work'],
            ['limit-mobility', '2020-10-14', 20, None, None, 'work'],
            ['limit-mobility', '2020-10-23', 10, None, None, 'work'],
            ['limit-mobility', '2020-12-14', 20, None, None, 'work'],

            ['limit-mobility', '2020-03-17', 20, None, None, 'transport'],
            ['limit-mobility', '2020-03-22', 40, None, None, 'transport'],
            ['limit-mobility', '2020-03-22', 40, None, None, 'transport'],
            ['limit-mobility', '2020-04-04', 50, None, None, 'transport'],
            ['limit-mobility', '2020-08-15', 10, None, None, 'transport'],
            ['limit-mobility', '2020-10-10', 20, None, None, 'transport'],
            ['limit-mobility', '2020-10-16', 25, None, None, 'transport'],
            ['limit-mobility', '2020-11-16', 30, None, None, 'transport'],
            ['limit-mobility', '2020-12-12', 40, None, None, 'transport'],

            ['wear-masks', '2020-09-01', 30, None, None, 'transport'],
            ['wear-masks', '2020-10-01', 35, None, None, 'transport'],
            ['wear-masks', '2020-11-01', 40, None, None, 'transport'],
            # Protect over 65-year-olds
            # ['wear-masks', '2020-10-01', 40, 65, None],

            # Overall mobility limitation
            ['limit-mobility', '2020-03-20', 10],
            ['limit-mobility', '2020-04-04', 20],
            ['limit-mobility', '2020-05-15', 30],
            ['limit-mobility', '2020-06-01', 35],  # summer effect?
            ['limit-mobility', '2020-08-05', 10],
            ['limit-mobility', '2020-08-15', 10],
            ['limit-mobility', '2020-09-01', 0],

            ['import-infections', '2020-03-01', 10],
            ['import-infections', '2020-03-07', 5],
            ['import-infections', '2020-03-09', 5],
            ['import-infections', '2020-07-15', 15],
            ['import-infections', '2020-08-01', 10],
            ['import-infections', '2020-09-01', 10],
            ['import-infections', '2020-09-15', 10],
            ['import-infections', '2020-10-01', 20],
            ['import-infections', '2020-10-13', 20],
            ['import-infections', '2020-10-15', 20],
            ['import-infections', '2020-10-18', 20],
            ['import-infections', '2020-11-01', 5],
            ['import-infections', '2020-11-07', 15],
            ['import-infections', '2020-11-15', 30],
            ['import-infections', '2020-11-22', 25],
            ['import-infections', '2020-12-01', 25],
        ],
        # Commenting these away for now, until we decide on whether to use
        # setting initial state or interventions to set state for start date
        #'incubating_at_simulation_start': 150,
        #'ill_at_simulation_start': 50,
        #'recovered_at_simulation_start': 1000
    },
}
_variable_override_set = os.getenv('VARIABLE_OVERRIDE_SET')
if _variable_override_set:
    assert _variable_override_set in VARIABLE_OVERRIDE_SETS


# Variables
#
# Default variables are per-instance and can be configured using
# VARIABLE_OVERRIDE_SET.
VARIABLE_DEFAULTS = {
    'area_name': 'HUS',
    'area_name_long': 'Helsingin ja Uudenmaan sairaanhoitopiiri',
    'country': 'FI',
    'max_age': 100,
    'simulation_days': 465,
    'start_date': '2020-02-18',
    'hospital_beds': 2600,
    'icu_units': 300,

    #
    # Disease parameters
    #

    'p_mask_protects_wearer': 45.0,  # %
    'p_mask_protects_others': 90.0,  # %

    # Chance to be asymptomatic
    'p_asymptomatic': 50.0,  # %

    'infectiousness_multiplier': 1.5,

    # Overall chance to become infected after being exposed.
    # This is modified by viral load of the infector, which
    # depends on the day of the illness.
    'p_infection': [
        [0, 5.0],
        [10, 7.0],
        [20, 18.0],
        [30, 18.0],
        [40, 18.0],
        [50, 18.0],
        [60, 22.0],
        [70, 25.0],
        [80, 70.0],
    ],

    # Chance to die after regular hospital care
    'p_hospital_death': 0.0,  # %
    # Chance to die after ICU care
    'p_icu_death': [
        [0, 40.0],
        [10, 40.0],
        [20, 50.0],
        [30, 50.0],
        [40, 50.0],
        [50, 50.0],
        [60, 50.0],
        [70, 50.0],
        [80, 50.0]
    ],
    'p_death_outside_hospital': [
        [0, 0.0],
        [10, 0.0],
        [20, 0.0],
        [30, 0.0],
        [40, 0.0],
        [50, 0.0],
        [60, 0.0],
        [70, 40.0],
        [80, 50.0]
    ],
    # Chance to die if no hospital beds are available (but not
    # needing ICU care)
    'p_hospital_death_no_beds': 20.0,  # %
    # Chance to die if no ICU care units are available
    'p_icu_death_no_beds': 100.0,  # %

    'mean_incubation_duration': 5.1,
    'mean_duration_from_onset_to_death': 18.8,
    'mean_duration_from_onset_to_recovery': 21.0,

    'ratio_of_duration_before_hospitalisation': 30.0,  # %
    'ratio_of_duration_in_ward': 15.0,  # %

    'incubating_at_simulation_start': 0,
    'ill_at_simulation_start': 0,
    'recovered_at_simulation_start': 0,

    # Ratio of all symptomatic people that require hospitalization
    # (more than mild symptoms) by age group
    # Numbers scaled, because source assumes 50% asymptomatic people.
    # Source: https://www.medrxiv.org/content/10.1101/2020.03.09.20033357v1.full.pdf
    #'p_severe': [
    #    [0, 0.0],
    #    [10, 0.0816],
    #    [20, 2.08],
    #    [30, 6.86],
    #    [40, 8.5],
    #    [50, 16.32],
    #    [60, 23.6],
    #    [70, 33.2],
    #    [80, 36.8]
    #],
    'p_severe': [
        [0, 0.0],
        [10, 0.0816],
        [20, 2.08/2],
        [30, 6.86/2],
        [40, 8.5/2],
        [50, 16.32/2],
        [60, 23.6/2],
        [70, 33.2],
        [80, 36.8],
    ],

    # Ratio of hospitalized cases requiring critical (ICU) care
    # Source: https://www.imperial.ac.uk/media/imperial-college/medicine/sph/ide/gida-fellowships/Imperial-College-COVID19-NPI-modelling-16-03-2020.pdf
    'p_critical': [
        [0, 5.0],
        [10, 5.0],
        [20, 5.0],
        [30, 5.0],
        [40, 6.3],
        [50, 12.2],
        [60, 27.4],
        [70, 43.2],
        [80, 70.9]
    ],
    'interventions': [
        ['test-all-with-symptoms', '2020-02-20'],
        ['test-only-severe-symptoms', '2020-03-15', 25],
        ['test-only-severe-symptoms', '2020-03-30', 50],
        ['test-only-severe-symptoms', '2020-04-15', 70],
        ['test-all-with-symptoms', '2020-05-01'],
        ['test-with-contact-tracing', '2020-06-15', 30],
        ['test-with-contact-tracing', '2020-09-15', 50],

        # ['limit-mass-gatherings', '2020-03-12', 50],

        ['limit-mobility', '2020-03-15', 80, 0, 70, 'other'],
        ['limit-mobility', '2020-08-15', 50, 0, 70, 'other'],
        ['limit-mobility', '2020-08-15', 50, 0, 70, 'other'],
        ['limit-mobility', '2020-04-01', 10],
        ['limit-mobility', '2020-05-01', 25],
        ['limit-mobility', '2020-05-15', 30],
        ['limit-mobility', '2020-09-01', 20],
        ['limit-mobility', '2020-09-15', 10],
        ['limit-mobility', '2020-10-01', 0],

        ['wear-masks', '2020-09-15', 50, 65, None, None],

        ['limit-mobility', '2020-03-15', 10, None, None, 'leisure'],
        ['limit-mobility', '2020-03-22', 40, None, None, 'leisure'],
        ['limit-mobility', '2020-03-29', 50, None, None, 'leisure'],
        ['limit-mobility', '2020-05-17', 40, None, None, 'leisure'],
        #['limit-mobility', '2020-05-31', 30, None, None, 'leisure'],
        #['limit-mobility', '2020-06-28', 15, None, None, 'leisure'],
        # ['limit-mobility', '2020-08-10', 10, None, None, 'leisure'],
        ['limit-mobility', '2020-10-09', 15, None, None, 'leisure'],
        ['limit-mobility', '2020-11-30', 20, None, None, 'leisure'],

        ['limit-mobility', '2020-03-15', 10, None, None, 'work'],
        ['limit-mobility', '2020-03-20', 30, None, None, 'work'],
        ['limit-mobility', '2020-03-23', 40, None, None, 'work'],
        ['limit-mobility', '2020-04-07', 50, None, None, 'work'],
        ['limit-mobility', '2020-05-10', 40, None, None, 'work'],
        ['limit-mobility', '2020-06-06', 30, None, None, 'work'],
        ['limit-mobility', '2020-06-26', 40, None, None, 'work'],
        ['limit-mobility', '2020-08-11', 35, None, None, 'work'],
        ['limit-mobility', '2020-08-19', 30, None, None, 'work'],
        ['limit-mobility', '2020-09-09', 25, None, None, 'work'],
        ['limit-mobility', '2020-09-23', 20, None, None, 'work'],
        ['limit-mobility', '2020-12-07', 25, None, None, 'work'],

        ['limit-mobility', '2020-03-19', 40, None, None, 'transport'],
        ['limit-mobility', '2020-03-28', 60, None, None, 'transport'],
        ['limit-mobility', '2020-05-23', 50, None, None, 'transport'],
        ['limit-mobility', '2020-06-08', 40, None, None, 'transport'],
        ['limit-mobility', '2020-09-01', 30, None, None, 'transport'],
        ['limit-mobility', '2020-11-20', 40, None, None, 'transport'],

        ['limit-mobility', '2020-03-12', 0, 7, 15, 'school'],
        ['limit-mobility', '2020-05-30', 100, 7, 15, 'school'],
        ['limit-mobility', '2020-08-12', 0, 7, 15, 'school'],

        # FIXME: Fully remove import interventions
        ['import-infections', '2020-02-22', 20],
        ['import-infections', '2020-03-05', 50],
        ['import-infections', '2020-03-07', 80],
        ['import-infections', '2020-03-09', 160],
        ['import-infections', '2020-03-11', 120],
        ['import-infections', '2020-03-13', 20],
        ['import-infections', '2020-03-15', 20],
        ['import-infections', '2020-08-15', 50],
        ['import-infections', '2020-09-01', 150],
        ['import-infections', '2020-09-07', 150],
        ['import-infections', '2020-09-15', 150],
        ['import-infections', '2020-10-01', 50],
        ['import-infections', '2020-10-15', 100],
        ['import-infections', '2020-11-01', 100],
        ['import-infections', '2020-11-15', 100],
    ],
    'variants': [],
    'preset_scenario': 'default',

    # Used for sampling the model
    'sample_limit_mobility': 0,
    # Used for Monte Carlo simulation
    'random_seed': 0
}
if _variable_override_set:
    VARIABLE_DEFAULTS.update(VARIABLE_OVERRIDE_SETS[_variable_override_set])


# Variable overrides that are set later programmatically
_variable_overrides = {}

# Make a hash of the default variables so that when they change,
# we will reset everybody's custom session variables.
DEFAULT_VARIABLE_HASH = hashlib.md5(json.dumps(VARIABLE_DEFAULTS).encode('utf8')).hexdigest()

_allow_variable_set = False


def set_variable(var_name, value):
    assert var_name in VARIABLE_DEFAULTS
    assert isinstance(value, type(VARIABLE_DEFAULTS[var_name]))

    if not flask.has_request_context():
        if not _allow_variable_set:
            raise Exception('Should not set variable outside of request context')
        _variable_overrides[var_name] = value
        return

    if value == VARIABLE_DEFAULTS[var_name]:
        if var_name in session:
            del session[var_name]
        return

    session[var_name] = value


def get_variable(var_name, var_store=None):
    out = None

    if var_store is not None:
        out = var_store.get(var_name)
    elif flask.has_request_context():
        if session.get('default_variable_hash', '') != DEFAULT_VARIABLE_HASH:
            reset_variables()
        if var_name in session:
            out = session[var_name]
    elif var_name in _variable_overrides:
        out = _variable_overrides[var_name]

    if out is None:
        out = VARIABLE_DEFAULTS[var_name]

    if isinstance(out, list):
        # Make a copy
        return list(out)

    return out


def reset_variable(var_name):
    if flask.has_request_context():
        if var_name in session:
            del session[var_name]
    else:
        if var_name in _variable_overrides:
            del _variable_overrides[var_name]


def reset_variables():
    if flask.has_request_context():
        session['default_variable_hash'] = DEFAULT_VARIABLE_HASH
        for var_name in VARIABLE_DEFAULTS.keys():
            if var_name not in session:
                continue
            del session[var_name]
    else:
        _variable_overrides.clear()


def copy_variables():
    out = {}
    for var_name in VARIABLE_DEFAULTS.keys():
        out[var_name] = get_variable(var_name)
    return out


@contextmanager
def allow_set_variable():
    global _allow_variable_set

    old = _allow_variable_set
    _allow_variable_set = True
    try:
        yield None
    finally:
        _allow_variable_set = old
