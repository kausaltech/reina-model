from dataclasses import dataclass
from flask_babel import lazy_gettext as _


@dataclass
class Scenario:
    id: str
    name: str
    description: str
    interventions: list
    variables: dict = None


SCENARIOS = [
    Scenario(
        id='default',
        name='Nykymeno',
        description='''Säilytetään nykyiset rajoitukset ja testauskäytäntö.''',
        interventions=[],
        variables={
            'simulation_days': 360
        }
    ),
    Scenario(
        id='summer-boogie',
        name='Kesähöllennys',
        description='''Höllennetään nykyisiä rajoituksia hieman juhannuksesta lähtien.''',
        interventions=[
            ['limit-mobility', '2020-06-20', 30],
        ],
        variables={
            'simulation_days': 360
        }
    ),
    Scenario(
        id='hammer-and-testing',
        name='Moukari + suurennuslasi',
        description='''Säilytetään nykyiset rajoitukset, mutta laajennetaan testausta kaikkiin oirehtiviin.''',
        interventions=[
            ['test-with-contact-tracing', '2020-05-01']
        ],
        variables={
            'simulation_days': 180
        }
    ),
    Scenario(
        id='hammer-and-dance',
        name='Moukari ja tanssi',
        description='''Laajennetaan testausta, tehdään kontaktien jäljitystä ja tasapainotellaan rajoitusten kanssa.''',
        interventions=[
            ['test-with-contact-tracing', '2020-05-01'],
            ['limit-mobility', '2020-05-01', 20],
            ['limit-mobility', '2020-06-24', 40],
            ['limit-mobility', '2020-08-15', 20],
            ['limit-mobility', '2020-10-01', 30],
        ],
        variables={
            'simulation_days': 360
        }
    ),
]
