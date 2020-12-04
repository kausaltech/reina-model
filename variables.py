
import datetime
import hashlib
import json
import os
from contextlib import contextmanager

import flask
from flask import session

LONG_AREA_NAMES = {
    'HUS': 'Helsingin ja Uudenmaan sairaanhoitopiiri',
    'Varsinais-Suomi': 'Varsinais-Suomen sairaanhoitopiiri'
}
_area_name = os.getenv('AREA_NAME', 'HUS')
_start_date = os.getenv('START_DATE', '2020-08-01')

def days_after(iso_datestr: str, days: int):
    """
    Returns a date string that represent a date that is number of
    days after or before the date string that is given as first parameter

    >>> days_after('2020-01-01', 3)
    '2020-01-04'

    >>> days_after('2020-01-01', -1)
    '2019-12-31'

    >>> days_after('2020-01-01', 0)
    '2020-01-01'
    """
    date = datetime.date.fromisoformat(iso_datestr)
    result_date = date + datetime.timedelta(days=days)
    return result_date.isoformat()

# Variables
VARIABLE_DEFAULTS = {
    'area_name': _area_name,
    'area_name_long': LONG_AREA_NAMES[_area_name],
    'country': 'FI',
    'max_age': 100,
    'simulation_days': 365,
    'start_date': _start_date,
    'hospital_beds': 2600,
    'icu_units': 300,

    #
    # Disease parameters
    #

    # Chance to be asymptomatic
    'p_asymptomatic': 50.0,  # %

    # Overall chance to become infected after being exposed.
    # This is modified by viral load of the infector, which
    # depends on the day of the illness.
    'p_infection': 30.0,  # %

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

    # Ratio of all symptomatic people that require hospitalization
    # (more than mild symptoms) by age group
    # Numbers scaled, because source assumes 50% asymptomatic people.
    # Source: https://www.medrxiv.org/content/10.1101/2020.03.09.20033357v1.full.pdf
    'p_severe': [
        [0, 0.0],
        [10, 0.0816],
        [20, 2.08],
        [30, 6.86],
        [40, 8.5],
        [50, 16.32],
        [60, 23.6],
        [70, 33.2],
        [80, 36.8]
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
        ['test-all-with-symptoms', days_after(_start_date, 2)],
        ['test-only-severe-symptoms', days_after(_start_date, 26), 25],

        # ['limit-mass-gatherings', days_after(_start_date, 23), 50],

        ['limit-mobility', days_after(_start_date, 23), 10],
        ['limit-mobility', days_after(_start_date, 28), 20],
        ['limit-mobility', days_after(_start_date, 31), 30],
        ['limit-mobility', days_after(_start_date, 33), 35],
        ['limit-mobility', days_after(_start_date, 39), 50],
        ['limit-mobility', days_after(_start_date, 47), 55],

        ['build-new-icu-units', days_after(_start_date, 72), 150],
        ['build-new-icu-units', days_after(_start_date, 102), 150],

        # FIXME: Fully remove import interventions
        ['import-infections', days_after(_start_date, 4), 5],
        ['import-infections', days_after(_start_date, 16), 20],
        ['import-infections', days_after(_start_date, 18), 120],
        ['import-infections', days_after(_start_date, 20), 120],
        ['import-infections', days_after(_start_date, 22), 80],
        ['import-infections', days_after(_start_date, 24), 20],
        ['import-infections', days_after(_start_date, 26), 20],
    ],

    'preset_scenario': 'default',

    # Used for sampling the model
    'sample_limit_mobility': 0,
    # Used for Monte Carlo simulation
    'random_seed': 0
}


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
