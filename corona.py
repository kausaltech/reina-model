import dash
import time
from datetime import date, timedelta
from flask_session import Session
from flask_babel import Babel, lazy_gettext as _
from common import cache
from common.locale import init_locale
import uuid
import os
import dash_table
import dash_core_components as dcc
import dash_html_components as html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from threading import Thread

from calc.simulation import simulate_individuals, INTERVENTIONS
from calc import ExecutionInterrupted
from common import settings
from variables import set_variable, get_variable, reset_variable
from components.results import render_results, register_results_callbacks
from components.params import render_disease_params, register_params_callbacks


os.environ['DASH_PRUNE_ERRORS'] = 'False'
os.environ['DASH_SILENCE_ROUTES_LOGGING'] = 'False'

app_kwargs = dict(suppress_callback_exceptions=True)
if settings.URL_PREFIX:
    app_kwargs['routes_pathname_prefix'] = settings.URL_PREFIX

app = dash.Dash(__name__, **app_kwargs)
app.css.config.serve_locally = True
app.scripts.config.serve_locally = True
server = app.server
with server.app_context():
    server.config.from_object('common.settings')
    server.config['BABEL_TRANSLATION_DIRECTORIES'] = 'locale'

    cache.init_app(server)
    sess = Session()
    sess.init_app(server)
    babel = Babel(default_locale='fi')
    babel.init_app(server)
    init_locale(babel)
    register_results_callbacks(app)
    register_params_callbacks(app)


'''
### Kuinka simulaatio toimii?
Simulaatiossa mallinnetaan kuinka COVID-19 epidemia etenee sairaanhoitokapasiteetista,
testauskäytännöistä ja ihmiset liikkuvuutta rajoittavista toimenpiteistä riippuen.

Simulaation taustalla on agenttipohjainen malli, jossa käydään läpi jokainen sairastunut
koko infektio- ja sairauspolun aikana.

#### Tapahtumat
Tapahtumalistasta voi simulaation lisätä tai poistaa tapahtumia tai toimenpiteitä.

#### Katso myös
Keskustelua yhteiskehittämisestä [täällä](https://korona.kausal.tech/)

#### Tekijät
Tämä on työkalun keskeneräinen kehitysversio. Voit tutustua työkalun lähdekoodiin [GitHubissa](https://github.com/kausaltech/corona-agent-simulation)
'''


def generate_static_content():
    f = open(os.path.join(os.path.dirname(__file__), 'Docs', 'description.en.md'))
    return dcc.Markdown(children=f.read())


def interventions_to_rows():
    ivs = get_variable('interventions')
    iv_rows = []
    for iv in sorted(ivs, key=lambda x: x[1]):
        for i in INTERVENTIONS:
            if i[0] == iv[0]:
                break
        else:
            # FIXME
            continue
        if len(iv) > 2:
            val = iv[2]
        else:
            val = None
        # date=datetime.strptime(iv[1], '%Y-%m-%d').strftime("%d.%m.%y")
        # Should we display formatted date on list? Does it mess with DataTable?
        if len(i) > 2:
            unit = i[2]
        else:
            unit = None
        row = dict(date=iv[1], label=i[1], value=val, name=i[0], unit=unit)
        iv_rows.append(row)
    return iv_rows


def render_iv_card():
    ivs = interventions_to_rows()
    iv_table = dash_table.DataTable(
        id='interventions-table',
        data=ivs,
        columns=[
            {'name': _('Date'), 'id': 'date'},
            {'name': _('Event'), 'id': 'label'},
            {'name': _('Value'), 'id': 'value'},
            {'name': '', 'id': 'unit'},
        ],
        style_cell={'textAlign': 'left'},
        style_cell_conditional=[
            {
                'if': {'column_id': 'value'},
                'textAlign': 'right'
            }
        ],
        row_deletable=True,
        style_as_list_view=True,
    )

    iv_card = dbc.Card([
        dbc.CardHeader([
            html.H2(dbc.Button(
                _("Events (%(num)s)", num=len(ivs)), className="float-left mt-2",
                id="interventions-collapse-button",
            )),
        ]),
        dbc.Collapse([
            dbc.CardBody([
                iv_table,
                html.Div(dbc.Button(
                    _('Restore default events'), id='interventions-reset-defaults', color='secondary',
                    size='sm', className='mt-3'
                ), className='text-right'),
            ], className="px-5"),
            dbc.CardFooter([
                html.H6(_('Add a new event')),
                dbc.Row([
                    dbc.Col(dcc.DatePickerSingle(
                        id='new-intervention-date', display_format='YYYY-MM-DD',
                        first_day_of_week=1,
                    ), md=3),
                    dbc.Col(dcc.Dropdown(
                        id='new-intervention-id',
                        options=[{'label': i[1], 'value': i[0]} for i in INTERVENTIONS]
                    ), md=5),
                    dbc.Col(dbc.Input(
                        id='new-intervention-value', type='number', size='6'
                    ), md=2),
                    dbc.Col(dbc.Button(
                        'Lisää', id='new-intervention-add', color='primary'
                    ), md=2),
                ], form=True)
            ]),
        ], is_open=False, id='interventions-collapse'),
    ], className='mb-4')

    return iv_card


def generate_layout():
    navbar = dbc.NavbarSimple(
        children=[
            dbc.Badge("v0.1", pill=True, color="primary", className="mr-1"),
        ],
        brand=_("Corona epidemic simulator"),
        brand_href="#",
        color="primary",
        dark=True,
    )
    rows = []
    rows.append(dbc.Row([
        dbc.Col([
            html.H3(_('Forecast of the COVID-19 epidemic: %(name)s', name=get_variable('area_name'))),
            html.P(_('Exploration of the effects of interventions to the progression of the epidemic.', className="lead")),
        ], className='mb-4'),
    ], className='mt-4'))

    dp_card = render_disease_params()
    rows.append(dbc.Row([dbc.Col(dp_card)]))

    iv_card = render_iv_card()
    rows.append(dbc.Row([dbc.Col(iv_card)]))

    rows.append(dbc.Row([
        dbc.Col([
        ], width=dict(size=6, offset=3))
    ]))

    rows.append(dbc.Row([
        dbc.Col([
            html.Div(id='simulation-days-placeholder', style=dict(display='none')),
            dcc.Dropdown(
                id='simulation-days-dropdown',
                options=[dict(label=_('%(days)d days', days=x), value=x) for x in (45, 90, 180, 360)],
                value=get_variable('simulation_days'),
                searchable=False, clearable=False,
            ),
        ], width=dict(size=2, offset=0)),
        dbc.Col([
            dbc.Button(_('Run simulation'), id='run-simulation', color='primary'),
        ], width=dict(offset=3), className='text-center')
    ], className='mt-3'))

    rows.append(dbc.Row([
        dbc.Col([
            html.Div(id="simulation-results-container")
        ]),
    ], className='mt-4'))

    rows.append(dbc.Row([
        dbc.Col([
            html.Div(id='day-details-container')
        ])
    ]))

    stc = generate_static_content()

    return html.Div([
        navbar,
        dbc.Container(rows),
        dbc.Jumbotron(
            dbc.Container(stc),
            className="mt-5",
            fluid=True,
        )
    ])


app.layout = generate_layout


@app.callback(
    Output("interventions-collapse", "is_open"),
    [Input("interventions-collapse-button", "n_clicks")],
    [State("interventions-collapse", "is_open")],
)
def toggle_iv_collapse(n, is_open):
    if n:
        return not is_open
    return is_open


@app.callback(
    Output('day-details-container', 'children'),
    [Input('population-graph', 'clickData')]
)
def show_day_details(data):
    print(data)
    return html.Div()


@app.callback(
    Output('interventions-table', 'data'),
    [
        Input('interventions-table', 'data_timestamp'),
        Input('interventions-reset-defaults', 'n_clicks'),
        Input('new-intervention-add', 'n_clicks'),
    ], [
        State('interventions-table', 'data'),
        State('new-intervention-date', 'date'),
        State('new-intervention-id', 'value'),
        State('new-intervention-value', 'value'),
    ]
)
def interventions_callback(ts, reset_clicks, add_intervention_clicks, rows, new_date, new_id, new_val):
    ctx = dash.callback_context
    is_reset = False
    if ctx.triggered:
        c_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if reset_clicks is not None and c_id == 'interventions-reset-defaults':
            reset_variable('interventions')
            is_reset = True
        if add_intervention_clicks is not None and c_id == 'new-intervention-add':
            d = date.fromisoformat(new_date)
            sstart = date.fromisoformat(get_variable('start_date'))
            if d < sstart or d > sstart + timedelta(days=get_variable('simulation_days')):
                raise dash.exceptions.PreventUpdate()

            if new_id in ('test-all-with-symptoms', 'test-only-severe-symptoms', 'test-with-contact-tracing'):
                new_val = None
            elif new_id in ('limit-mobility',):
                if new_val > 100 or new_val < 0:
                    raise dash.exceptions.PreventUpdate()
            elif new_id in ('limit-mass-gatherings', 'import-infections', 'build-new-icu-units', 'build-new-hospital-beds'):
                if new_val < 0:
                    raise dash.exceptions.PreventUpdate()
            else:
                raise dash.exceptions.PreventUpdate()

            rows.append(dict(name=new_id, date=d.isoformat(), value=new_val))

    if not is_reset:
        ivs = []
        for row in sorted(rows, key=lambda x: x['date']):
            ivs.append([row['name'], row['date'], row['value']])
        set_variable('interventions', ivs)

    rows = interventions_to_rows()
    return rows


process_pool = {}


class SimulationThread(Thread):
    def __init__(self, *args, **kwargs):
        self.variables = kwargs.pop('variables')
        super().__init__(*args, **kwargs)
        self.uuid = str(uuid.uuid4())

    def start(self):
        print('%s: start process' % self.uuid)
        super().start()

    def run(self):
        from common import cache

        process_pool[self.ident] = self

        self.last_results = None
        print('%s: run process' % self.uuid)

        def step_callback(df, force=False):
            now = time.time()
            if force or self.last_results is None or now - self.last_results > 0.5:
                cache.set('thread-%s-results' % self.uuid, df, timeout=30)
                print('%s: step callback' % self.uuid)
                self.last_results = now

            if cache.get('thread-%s-kill' % self.uuid):
                return False
            return True

        try:
            df = simulate_individuals(step_callback=step_callback, variable_store=self.variables)
        except ExecutionInterrupted:
            print('%s: process cancelled' % self.uuid)
        else:
            print('%s: computation finished' % self.uuid)
            step_callback(df, force=True)

        cache.set('thread-%s-finished' % self.uuid, True)
        print('%s: process finished' % self.uuid)

        del process_pool[self.ident]


@app.callback(
    [
        Output('simulation-output-results', 'children'),
        Output('simulation-output-interval', 'disabled'),
        Output('simulation-output-interval', 'interval'),
    ], [Input('simulation-output-interval', 'n_intervals')]
)
def update_simulation_results(n_intervals):
    from flask import session

    thread_id = session.get('thread_id', None)
    if thread_id is None:
        raise dash.exceptions.PreventUpdate()

    df = cache.get('thread-%s-results' % thread_id)
    if df is None:
        raise dash.exceptions.PreventUpdate()

    if cache.get('thread-%s-finished' % thread_id):
        # When the computation thread is finished, stop polling.
        print('thread finished, disabling')
        disabled = True
    else:
        print('thread not finished, updating')
        disabled = False
    out = render_results(df)
    return [out, disabled, 500]


@app.callback(
    Output('simulation-results-container', 'children'),
    [
        Input('run-simulation', 'n_clicks'),
        Input('simulation-days-dropdown', 'value')
    ],
)
def run_simulation_callback(n_clicks, simulation_days):
    from flask import session
    from common import cache

    print('run simulation (days %d)' % simulation_days)
    set_variable('simulation_days', simulation_days)

    df = simulate_individuals(only_if_in_cache=True)
    if df is not None:
        return render_results(df)

    existing_thread_id = session.get('thread_id', None)
    if existing_thread_id:
        cache.set('thread-%s-kill' % existing_thread_id, True)

    process = SimulationThread(variables=session.copy())
    session['thread_id'] = process.uuid
    process.start()

    return [
        dcc.Interval(id='simulation-output-interval', interval=100, max_intervals=60),
        html.Div(id='simulation-output-results'),
    ]


if __name__ == '__main__':
    # Write the process pid to a file for easier profiling with py-spy
    with open('.corona.pid', 'w') as pid_file:
        pid_file.write(str(os.getpid()))
    app.run_server(debug=True, port=8123)
