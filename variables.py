import hashlib
import json
import os
from contextlib import contextmanager

import flask
from flask import session

VARIABLE_OVERRIDE_SETS = {
    'turku': {
        'area_name': 'Turku',
        'area_name_long': 'Turun kaupunki',
        'hospital_beds': 900,
        'icu_units': 55,
        # 'start_date': '2020-09-01',
        'interventions': [
            ['test-all-with-symptoms', '2020-02-20'],
            ['test-only-severe-symptoms', '2020-03-15', 30],
            ['test-only-severe-symptoms', '2020-03-25', 80],
            ['test-only-severe-symptoms', '2020-03-25', 80],
            ['test-all-with-symptoms', '2020-04-01'],
            #['test-only-severe-symptoms', '2020-05-01', 80],
            #['test-only-severe-symptoms', '2020-06-01', 80],
            #['test-all-with-symptoms', '2020-06-20'],
            ['test-with-contact-tracing', '2020-07-01', 20],
            ['test-with-contact-tracing', '2020-09-01', 70],
            ['test-with-contact-tracing', '2020-12-01', 60],
            ['test-with-contact-tracing', '2020-12-14', 70],
            # ['test-with-contact-tracing', '2020-12-01', 60],

            # Elementary school
            ['limit-mobility', '2020-03-23', 0, 7, 12, 'school'],
            ['limit-mobility', '2020-05-30', 100, 7, 12, 'school'],
            ['limit-mobility', '2020-08-12', 0, 7, 12, 'school'],
            ['limit-mobility', '2020-11-01', 10, 7, 12, 'school'],
            ['limit-mobility', '2020-11-15', 0, 7, 12, 'school'],
            ['limit-mobility', '2021-01-07', 0, 7, 12, 'school'],

            # Junior high school
            ['limit-mobility', '2020-03-23', 100, 13, 15, 'school'],
            ['limit-mobility', '2020-05-30', 100, 13, 15, 'school'],
            ['limit-mobility', '2020-08-12', 0, 13, 15, 'school'],
            ['limit-mobility', '2020-11-01', 20, 13, 15, 'school'],
            ['limit-mobility', '2020-11-21', 0, 13, 15, 'school'],
            ['limit-mobility', '2020-12-01', 20, 13, 15, 'school'],
            ['limit-mobility', '2020-12-16', 100, 13, 15, 'school'],
            ['limit-mobility', '2021-01-07', 0, 13, 15, 'school'],

            # Upper secondary level
            ['limit-mobility', '2020-03-23', 100, 16, 18, 'school'],
            ['limit-mobility', '2020-05-30', 100, 16, 18, 'school'],
            ['limit-mobility', '2020-08-12', 0, 16, 18, 'school'],
            ['limit-mobility', '2020-11-01', 45, 16, 18, 'school'],
            ['limit-mobility', '2020-12-07', 70, 16, 18, 'school'],
            ['limit-mobility', '2020-12-19', 100, 16, 18, 'school'],
            ['limit-mobility', '2021-01-07', 70, 16, 18, 'school'],

            # Higher education
            ['limit-mobility', '2020-03-23', 100, 19, None, 'school'],
            ['limit-mobility', '2020-08-12', 80, 19, None, 'school'],

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


            ['wear-masks', '2020-03-15', 80, 65, None],
            ['wear-masks', '2020-09-15', 90, 65, None],

            ['wear-masks', '2020-10-01', 20, None, None, 'transport'],
            ['wear-masks', '2020-10-01', 20, None, None, 'leisure'],
            ['wear-masks', '2020-10-01', 20, None, None, 'work'],
            ['wear-masks', '2020-10-01', 20, None, None, 'other'],
            ['wear-masks', '2020-10-01', 90, 65, None],

            ['wear-masks', '2020-11-01', 40, None, None, 'transport'],
            ['wear-masks', '2020-11-01', 40, None, None, 'leisure'],
            ['wear-masks', '2020-11-01', 40, None, None, 'work'],
            ['wear-masks', '2020-11-01', 40, None, None, 'other'],
            ['wear-masks', '2020-11-01', 90, 65, None],

            ['wear-masks', '2020-12-01', 70, None, None, 'transport'],
            ['wear-masks', '2020-12-01', 70, None, None, 'leisure'],
            ['wear-masks', '2020-12-01', 70, None, None, 'work'],
            ['wear-masks', '2020-12-01', 70, None, None, 'other'],
            ['wear-masks', '2020-12-01', 90, 65, None],

            # Overall mobility limitation
            ['limit-mobility', '2020-03-20', 20],
            ['limit-mobility', '2020-04-04', 15],
            ['limit-mobility', '2020-04-15', 20],
            ['limit-mobility', '2020-05-01', 30],
            ['limit-mobility', '2020-05-15', 60],
            ['limit-mobility', '2020-08-05', 10],
            ['limit-mobility', '2020-08-15', 0],
            ['limit-mobility', '2020-09-15', 0],

            # Vaccinate healthcare professionals
            ['vaccinate', '2021-01-01', 250, 22, 29],
            ['vaccinate', '2021-01-01', 250, 30, 39],
            ['vaccinate', '2021-01-01', 250, 40, 49],
            ['vaccinate', '2021-01-01', 250, 50, 59],
            ['vaccinate', '2021-01-01', 250, 60, 64],

            ['vaccinate', '2021-01-31', 0, 22, 29],
            ['vaccinate', '2021-01-31', 0, 30, 39],
            ['vaccinate', '2021-01-31', 0, 40, 49],
            ['vaccinate', '2021-01-31', 0, 50, 59],
            ['vaccinate', '2021-01-31', 0, 60, 64],

            # Elderly
            ['vaccinate', '2021-01-01', 1250, 80, None],
            ['vaccinate', '2021-02-01', 2500, 80, None],
            ['vaccinate', '2021-03-01', 0, 80, None],
            ['vaccinate', '2021-03-01', 5000, 70, None],

            ['import-infections', '2020-03-01', 10],
            ['import-infections-weekly', '2020-03-01', 10],
            ['import-infections-weekly', '2020-03-15', 10],
            ['import-infections-weekly', '2020-04-01', 10],
            ['import-infections-weekly', '2020-06-01', 5],

            ['import-infections', '2020-07-15', 15],
            ['import-infections', '2020-08-01', 10],
            ['import-infections-weekly', '2020-09-01', 5],
            ['import-infections-weekly', '2020-09-15', 30],
            ['import-infections-weekly', '2020-10-01', 50],
            ['import-infections-weekly', '2020-11-01', 120],
            ['import-infections-weekly', '2020-11-15', 150],
            ['import-infections-weekly', '2020-12-01', 240],
        ],
        'scenarios': [
            {
                'id': 'default',
                'label': 'Oletus',
                'description': """Nykytiedon mukaiset toimenpiteet toteutuvat.""",
            }, {
                'id': 'astra-zeneca',
                'label': 'Astra Zeneca -rokote',
                'description': """Astra Zeneca -yritys saa myyntiluvan ja rokottamista lisätään.""",
                'add_interventions': [
                    ['vaccinate', '2021-03-01', 2000, 25, 55],
                ],
            }, {
                'id': 'b117-variant',
                'label': 'Tarttuvampi variantti',
                'description': """Alueelle on tullut tarttuvampaa virusvarianttia.""",
                'add_interventions': [
                    ['import-infections', '2020-12-15', 30, 'b1.1.7'],
                ],
            }
        ],

        # Commenting these away for now, until we decide on whether to use
        # setting initial state or interventions to set state for start date
        # 'incubating_at_simulation_start': 150,
        # 'ill_at_simulation_start': 50,
        # 'recovered_at_simulation_start': 1000
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

    'infectiousness_multiplier': 0.55,

    # Overall chance to become infected after being exposed.
    # from Zhang et al., https://science.sciencemag.org/content/early/2020/05/04/science.abb8001
    #
    # This is modified by viral load of the infector, which
    # depends on the day of the illness.
    #
    # Parameters copied from Covasim (https://github.com/InstituteforDiseaseModeling/covasim/blob/master/covasim/parameters.py)
    'p_susceptibility': [
        [0, 34.0],
        [10, 67.0],
        [20, 100.0],
        [30, 100.0],
        [40, 100.0],
        [50, 100.0],
        [60, 124.0],
        [70, 147.0],
        [80, 147.0],
        [90, 147.0],
    ],
    # Probability modifier for an asymptomatic person to spread the infection
    # https://www.medrxiv.org/content/10.1101/2020.11.04.20225573v1
    'p_asymptomatic_infection': 0.8,

    # Probabilities updated from covasim: https://github.com/InstituteforDiseaseModeling/covasim
    # Overall probability of developing symptoms (based on https://www.medrxiv.org/content/10.1101/2020.03.24.20043018v1.full.pdf, scaled for overall symptomaticity)
    'p_symptomatic': [
        [0, 50.0],
        [10, 55.0],
        [20, 60.0],
        [30, 65.0],
        [40, 70.0],
        [50, 75.0],
        [60, 80.0],
        [70, 85.0],
        [80, 90.0],
        [90, 90.0],
    ],
    # Overall probability of developing severe symptoms (derived from Table 1 of https://www.imperial.ac.uk/media/imperial-college/medicine/mrc-gida/2020-03-16-COVID19-Report-9.pdf)
    'p_severe': [
        [0, 0.0500],
        [10, 0.1650],
        [20, 0.7200],
        [30, 2.0800],
        [40, 3.4300],
        [50, 7.6500],
        [60, 13.2800],
        [70, 20.6550],
        [80, 24.5700],
        [90, 24.5700],
    ],

    # Overall probability of developing critical symptoms (derived from Table 1 of https://www.imperial.ac.uk/media/imperial-college/medicine/mrc-gida/2020-03-16-COVID19-Report-9.pdf)
    'p_critical': [
        [0, 0.0030],
        [10, 0.0080],
        [20, 0.0360],
        [30, 0.1040],
        [40, 0.2160],
        [50, 0.9330],
        [60, 3.6390],
        [70, 8.9230],
        [80, 17.4200],
        [90, 17.4200],
    ],
    # Overall probability of dying -- from O'Driscoll et al., https://www.nature.com/articles/s41586-020-2918-0; last data point from Brazeau et al., https://www.imperial.ac.uk/mrc-global-infectious-disease-analysis/covid-19/report-34-ifr/
    # Model assumes the death happens through a hospitalization period.
    'p_fatal': [
        [0, 0.0020],
        [10, 0.0020],
        [20, 0.0100],
        [30, 0.0320],
        [40, 0.0980],
        [50, 0.2650],
        [60, 0.7660],
        [70, 2.4390],
        [80, 8.2920],
        [90, 16.1900],
    ],

    # Increased probability of dying outside a hospital (e.g. care-home deaths)
    'p_death_outside_hospital': [
        [0, 0.0],
        [10, 0.0],
        [20, 0.0],
        [30, 0.0],
        [40, 0.0],
        [50, 0.0],
        [60, 1.0],
        [70, 6.0],
        [80, 50.0],
        [90, 55.0]
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

    # Age class weights for imported infections
    'imported_infection_ages': [
        [0, 15.0],
        [20, 40.0],
        [40, 40.0],
        [60, 5.0],
        [70, 0],
    ],

    'incubating_at_simulation_start': 0,
    'ill_at_simulation_start': 0,
    'recovered_at_simulation_start': 0,

    'interventions': [
        ['test-all-with-symptoms', '2020-02-20'],
        ['test-only-severe-symptoms', '2020-03-15', 25],
        ['test-only-severe-symptoms', '2020-03-30', 50],
        ['test-only-severe-symptoms', '2020-04-15', 70],
        ['test-with-contact-tracing', '2020-06-15', 30],
        ['test-with-contact-tracing', '2020-09-15', 30],

        ['limit-mobility', '2020-03-15', 80, 0, 70, 'other'],
        ['limit-mobility', '2020-08-15', 50, 0, 70, 'other'],
        ['limit-mobility', '2020-04-01', 5],
        ['limit-mobility', '2020-05-01', 20],
        ['limit-mobility', '2020-07-01', 10],
        ['limit-mobility', '2020-09-01', 10],
        ['limit-mobility', '2020-09-15', 10],
        ['limit-mobility', '2020-10-01', 0],

        ['wear-masks', '2020-07-01', 80, 65, None, None],

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

        ['limit-mobility', '2020-03-12', 0, 7, 12, 'school'],
        ['limit-mobility', '2020-04-01', 100, 19, None, 'school'],
        ['limit-mobility', '2020-05-30', 100, 7, 12, 'school'],
        ['limit-mobility', '2020-05-30', 100, 13, 15, 'school'],
        ['limit-mobility', '2020-05-30', 100, 16, 18, 'school'],
        ['limit-mobility', '2020-08-12', 0, 7, 12, 'school'],
        ['limit-mobility', '2020-08-12', 0, 13, 15, 'school'],
        ['limit-mobility', '2020-08-12', 0, 16, 18, 'school'],
        ['limit-mobility', '2020-08-12', 20, 19, None, 'school'],

        # FIXME: Fully remove import interventions
        ['import-infections', '2020-02-22', 20],
        ['import-infections', '2020-03-05', 50],
        ['import-infections', '2020-03-07', 80],
        ['import-infections', '2020-03-09', 120],
        ['import-infections', '2020-03-11', 80],
        ['import-infections', '2020-03-13', 20],
        ['import-infections', '2020-03-15', 20],
        ['import-infections-weekly', '2020-07-01', 50],
        ['import-infections', '2020-08-15', 50],
        ['import-infections', '2020-09-01', 100],
        ['import-infections', '2020-09-07', 100],
        ['import-infections', '2020-09-15', 100],
        ['import-infections', '2020-10-01', 50],
        ['import-infections', '2020-10-15', 100],
        ['import-infections', '2020-11-01', 100],
        ['import-infections', '2020-11-15', 100],
    ],
    'variants': [
        {
            'name': 'b1.1.7',
        },
    ],
    'scenarios': [
        {
            'id': 'default',
            'label': 'Oletus',
            'description': """Nykytiedon mukaiset toimenpiteet toteutuvat.""",
        }
    ],
    'active_scenario': 'default',

    # Used for sampling the model
    'sample_limit_mobility': 0,
    # Used for Monte Carlo simulation
    'random_seed': 0
}

# Variant has 50 % higher infectiousness
VARIABLE_DEFAULTS['variants'][0]['infectiousness_multiplier'] = \
    VARIABLE_DEFAULTS['infectiousness_multiplier'] * 1.5

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


def get_session_variables():
    out = {}
    for var_name in VARIABLE_DEFAULTS.keys():
        if var_name in session:
            out[var_name] = session[var_name]
    return out


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
