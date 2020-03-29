import json
import flask
import hashlib
from flask import session


# Variables
VARIABLE_DEFAULTS = {
    'area_name': 'HUS',
    'country': 'Finland',
    'simulation_days': 270,
    'start_date': '2020-02-18',
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
    'p_infection': 25.0,  # %

    # For people having at least severe symptoms, chance to
    # have critical symptoms (and requiring ICU care).
    'p_critical': 25.0,  # %

    # Chance to die after regular hospital care
    'p_hospital_death': 10.0,  # %
    # Chance to die after ICU care
    'p_icu_death': 20.0,  # %
    # Chance to die if no hospital beds are available (but not
    # needing ICU care)
    'p_hospital_death_no_beds': 20.0,  # %
    # Chance to die if no ICU care units are available
    'p_icu_death_no_beds': 100.0,  # %

    # Ratio of all infected people that require hospitalization
    # (more than mild symptoms) by age group
    # https://www.medrxiv.org/content/10.1101/2020.03.09.20033357v1.full.pdf
    'p_severe': [
        [0, 0.0],
        [10, 0.04],
        [20, 1.1],
        [30, 3.4],
        [40, 4.3],
        [50, 8.2],
        [60, 11.8],
        [70, 16.6],
        [80, 18.4]
    ],

    'interventions': [
        ['test-all-with-symptoms', '2020-02-20'],
        ['test-only-severe-symptoms', '2020-03-15'],

        ['limit-mobility', '2020-03-12', 10],
        ['limit-mass-gatherings', '2020-03-12', 50],

        ['limit-mobility', '2020-03-15', 20],
        ['limit-mobility', '2020-03-20', 30],
        ['limit-mobility', '2020-03-27', 35],

        ['build-new-icu-units', '2020-04-30', 150],
        ['build-new-icu-units', '2020-05-30', 150],

        ['import-infections', '2020-02-20', 20],
        ['import-infections', '2020-03-05', 30],
        ['import-infections', '2020-03-07', 30],
        ['import-infections', '2020-03-09', 30],
        ['import-infections', '2020-03-11', 30],
        ['import-infections', '2020-03-13', 10],
        ['import-infections', '2020-03-15', 10],
    ]
}


# Make a hash of the default variables so that when they change,
# we will reset everybody's custom session variables.
DEFAULT_VARIABLE_HASH = hashlib.md5(json.dumps(VARIABLE_DEFAULTS).encode('utf8')).hexdigest()


def set_variable(var_name, value):
    assert var_name in VARIABLE_DEFAULTS
    assert isinstance(value, type(VARIABLE_DEFAULTS[var_name]))

    if value != VARIABLE_DEFAULTS[var_name]:
        assert flask.has_request_context()

    if value == VARIABLE_DEFAULTS[var_name]:
        if var_name in session:
            del session[var_name]
        return

    session[var_name] = value


def get_variable(var_name):
    out = None
    if flask.has_request_context():
        if session.get('default_variable_hash', '') != DEFAULT_VARIABLE_HASH:
            reset_variables()
        if var_name in session:
            out = session[var_name]
    if out is None:
        out = VARIABLE_DEFAULTS[var_name]
    if isinstance(out, list):
        # Make a copy
        return list(out)
    return out


def reset_variable(var_name):
    if flask.has_request_context() and var_name in session:
        del session[var_name]


def reset_variables():
    print('reset to defaults')
    session['default_variable_hash'] = DEFAULT_VARIABLE_HASH
    for var_name in VARIABLE_DEFAULTS.keys():
        if var_name not in session:
            continue
        del session[var_name]
