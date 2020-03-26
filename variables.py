import flask
from flask import session


# Variables
VARIABLE_DEFAULTS = {
    'area_name': 'HUS',
    'country': 'Finland',
    'simulation_days': 270,
    'start_date': '2020-02-18',
    'hospital_beds': 2600,
    'icu_units': 300,
    'interventions': [
        ['test-all-with-symptoms', '2020-02-20'],
        ['test-only-severe-symptoms', '2020-03-15'],
        ['limit-mobility', '2020-03-12', 10],
        ['limit-mass-gatherings', '2020-03-12', 50],

        ['limit-mobility', '2020-03-15', 20],
        ['limit-mobility', '2020-03-20', 30],
        ['limit-mobility', '2020-03-25', 50],

        ['limit-mobility', '2020-04-01', 90],
        ['limit-mobility', '2020-04-30', 50],

        ['build-new-icu-units', '2020-04-30', 150],
        ['build-new-icu-units', '2020-05-30', 150],

        ['import-infections', '2020-02-20', 20],
        ['import-infections', '2020-03-05', 300],
        ['import-infections', '2020-03-07', 300],
        ['import-infections', '2020-03-09', 300],
        ['import-infections', '2020-03-11', 300],
        ['import-infections', '2020-03-13', 100],
        ['import-infections', '2020-03-15', 100],
    ]
}


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
    if flask.has_request_context() and var_name in session:
        out = session[var_name]
    else:
        out = VARIABLE_DEFAULTS[var_name]
    if isinstance(out, list):
        # Make a copy
        return list(out)
    return out


def reset_variable(var_name):
    if flask.has_request_context() and var_name in session:
        del session[var_name]
