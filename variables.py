import flask
from flask import session


# Variables
VARIABLE_DEFAULTS = {
    'population': 5500000,
    'area_name': 'HUS',
    'initial_infected': 1000,
    'initial_recovered': 200,
    'simulation_days': 365,
    'r0': 2.0,
    'infectious_days': 14,
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
    if flask.has_request_context():
        if var_name in session:
            return session[var_name]
    return VARIABLE_DEFAULTS[var_name]
