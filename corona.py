import dash
import time
from datetime import date, timedelta
from flask_session import Session
from common import cache
import uuid
import os
import numpy as np
import dash_table
from dash_table.Format import Format, Scheme
import dash_core_components as dcc
import dash_html_components as html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from utils.colors import THEME_COLORS
from threading import Thread

from calc.simulation import simulate_individuals, INTERVENTIONS
from calc.datasets import get_detected_cases
from calc import ExecutionInterrupted
from common import settings
from components.cards import GraphCard
from components.graphs import make_layout
from variables import set_variable, get_variable, reset_variable


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

    cache.init_app(server)
    sess = Session()
    sess.init_app(server)

markdown_text = '''
### Kuinka simulaatio toimii?
Simulaatiossa mallinnetaan kuinka COVID-19 epidemia etenee sairaanhoitokapasiteetista,
testauskäytännöistä ja ihmiset liikkuvuutta rajoittavista toimenpiteistä riippuen.

Simulaation taustalla on agenttipohjainen malli, jossa käydään läpi jokainen sairastunut
koko infektio- ja sairauspolun aikana.

#### Oletusarvot
**HUS alueen väestö:** 1 645 000

#### Tapahtumat
Tapahtumalistasta voi simulaation lisätä tai poistaa tapahtumia tai toimenpiteitä.

#### Katso myös
Keskustelua yhteiskehittämisestä [täällä](https://korona.kausal.tech/)

#### Tekijät
Tämä on työkalun keskeneräinen kehitysversio. Voit tutustua työkalun lähdekoodiin [GitHubissa](https://github.com/kausaltech/corona-agent-simulation)
'''


def generate_static_content():
    return dcc.Markdown(children=markdown_text)


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


DISEASE_PARAMS = (
    ('p_asymptomatic', 'Osuus tartunnan saaneista, jotka jäävät oireettomiksi', '%',),
    ('p_infection', 'Todennäköisyys, että taudille altistunut saa tartunnan', '%',),
    ('p_critical', 'Osuus vakavasti oirehtivista, jotka tarvitsevat tehohoitoa', '%',),
    ('p_icu_death', 'Tehohoitoa tarvitsevien osuus, joka kuolee tehohoitojakson päätteeksi', '%'),
    ('p_hospital_death', 'Sairaalahoitoa tarvitsevista osuus, joka kuolee sairaalahoidon päätteeksi', '%'),
    ('p_hospital_death_no_beds', 'Sairaalahoitoa tarvitsevien osuus, joka kuolee jos sairaalapaikkaa ei ole vapaana', '%'),
    ('p_icu_death_no_beds', 'Tehohoitoa tarvitsevien osuus, joka kuolee jos tehohoitopaikkaa ei ole vapaana', '%'),
    # ('p_severe', 'Sairaalahoitoa tarvitsevien osuus kaikista tartunnan saaneista ikäryhmittäin', '%'),
)


def render_disease_params():
    rows = []
    for pid, label, unit in DISEASE_PARAMS:
        val = get_variable(pid)
        rows.append(dict(id=pid, label=label, value=val, unit=unit))

    value_fmt = {
        'locale': dict(decimal=',')
    }

    dp_table = dash_table.DataTable(
        id='disease-params-table',
        data=rows,
        columns=[
            {'name': 'Kuvaus', 'id': 'label'},
            {
                'name': 'Arvo',
                'id': 'value',
                'editable': True,
                'format': value_fmt,
                'type': 'numeric',
                'validation': dict(allow_null=False),
            },
            {'name': '', 'id': 'unit'},
        ],
        style_cell={'textAlign': 'left'},
        style_cell_conditional=[
            {
                'if': {'column_id': 'value'},
                'textAlign': 'right'
            }
        ],
        style_as_list_view=True,
    )

    card = dbc.Card([
        dbc.CardHeader([
            html.H2(dbc.Button(
                "Taudin oletukset", className="float-left mt-2",
                id="disease-collapse-button",
            )),
        ]),
        dbc.Collapse([
            dbc.CardBody([
                dp_table,
                html.Div(dbc.Button(
                    'Palauta oletusarvot', id='disease-params-reset-defaults', color='secondary',
                    size='sm', className='mt-3'
                ), className='text-right'),
            ], className="px-5"),
        ], is_open=False, id='disease-collapse'),
    ], className='mb-4')

    return card


def render_iv_card():
    ivs = interventions_to_rows()
    iv_table = dash_table.DataTable(
        id='interventions-table',
        data=ivs,
        columns=[
            {'name': 'Päivämäärä', 'id': 'date'},
            {'name': 'Tapahtuma', 'id': 'label'},
            {'name': 'Arvo', 'id': 'value'},
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
                "Tapahtumat (%d)" % len(ivs), className="float-left mt-2",
                id="interventions-collapse-button",
            )),
        ]),
        dbc.Collapse([
            dbc.CardBody([
                iv_table,
                html.Div(dbc.Button(
                    'Palauta oletustapahtumat', id='interventions-reset-defaults', color='secondary',
                    size='sm', className='mt-3'
                ), className='text-right'),
            ], className="px-5"),
            dbc.CardFooter([
                html.H6('Lisää uusi tapahtuma'),
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
        brand="Koronaepidemiasimulaatio",
        brand_href="#",
        color="primary",
        dark=True,
    )
    rows = []
    rows.append(dbc.Row([
        dbc.Col([
            html.H3('COVID-19-epidemian kehittyminen: %s' % get_variable('area_name')),
            html.P('Tutkitaan kuinka erilaiset interventiot vaikuttavat koronavirusepidemian etenemiseen.', className="lead"),
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
                options=[dict(label='%d päivää' % x, value=x) for x in (45, 90, 180, 360)],
                value=get_variable('simulation_days'),
                searchable=False, clearable=False,
            ),
        ], width=dict(size=2, offset=0)),
        dbc.Col([
            dbc.Button('Suorita simulaatio', id='run-simulation', color='primary'),
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
    Output("disease-collapse", "is_open"),
    [Input("disease-collapse-button", "n_clicks")],
    [State("disease-collapse", "is_open")],
)
def toggle_disease_collapse(n, is_open):
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
    Output('disease-params-table', 'data'),
    [
        Input('disease-params-table', 'data_timestamp'),
        Input('disease-reset-defaults', 'n_clicks'),
    ], [
        State('disease-params-table', 'data'),
    ]
)
def disease_params_data_callback(ts, rows):
    for row in rows:
        if row['value'] < 0:
            row['value'] = 0
        elif row['value'] > 100:
            row['value'] = 100
    return rows


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


def render_result_graphs(df):
    traces = generate_population_traces(df)
    card = GraphCard('population', graph=dict(config=dict(responsive=False)))
    layout = make_layout(
        title='Väestö', height=250, showlegend=True,
        margin=dict(r=250)
    )
    fig = dict(data=traces, layout=layout)
    card.set_figure(fig)
    c1 = card.render()

    hc_cols = (
        ('hospital_beds', 'Vuodepaikat'),
        ('icu_units', 'Tehohoitopaikat')
    )
    traces = []
    for col, name in hc_cols:
        t = dict(type='scatter', name=name, x=df.index, y=df[col], mode='lines')
        traces.append(t)

    card = GraphCard('healthcare', graph=dict(config=dict(responsive=False)))
    layout = make_layout(
        title='Sairaanhoitojärjestelmän vapaa kapasiteetti', height=250, showlegend=True,
        margin=dict(r=250)
    )
    fig = dict(data=traces, layout=layout)
    card.set_figure(fig)
    c2 = card.render()

    df['ifr'] = df.dead.divide((df.infected + df.recovered).replace(0, np.inf)) * 100
    df['cfr'] = df.dead.divide(df.all_detected.replace(0, np.inf)) * 100

    param_cols = (
        ('r', 'R-luku'),
        ('ifr', 'Infektiokuolleisuus (IFR, %)'),
        ('cfr', 'Tapauskuolleisuus (CFR, %)'),
    )
    card = GraphCard('params', graph=dict(config=dict(responsive=False)))
    traces = []
    for col, name in param_cols:
        t = dict(type='scatter', name=name, x=df.index, y=df[col], mode='lines')
        traces.append(t)
    layout = make_layout(
        title='Epidemian parametrit', height=250, showlegend=True,
        margin=dict(r=250)
    )
    fig = dict(data=traces, layout=layout)
    card.set_figure(fig)
    c3 = card.render()

    return dbc.Row([dbc.Col(c1, md=12), dbc.Col(c2, md=12), dbc.Col(c3, md=12)])


def render_result_table(df):
    df = df.rename(columns=dict(tests_run_per_day='positive_tests_per_day'))
    df = df.drop(columns='sim_time_ms')
    df.index = df.index.date

    cols = [{'name': 'date', 'id': 'date', 'type': 'datetime'}]
    for col_name in df.columns:
        d = dict(name=col_name, id=col_name)
        if col_name in ('cfr', 'ifr', 'r'):
            d['type'] = 'numeric'
            d['format'] = Format(precision=2, scheme=Scheme.fixed)
        cols.append(d)

    rows = df.to_dict('records')
    for idx, row in zip(df.index, rows):
        row['date'] = idx

    dp_table = dash_table.DataTable(
        id='simulation-results-table',
        data=rows,
        columns=cols,
        style_table={'overflowX': 'scroll'},
        export_format='xlsx',
    )
    return dbc.Row([dbc.Col(dp_table)])


def generate_population_traces(df):
    det = get_detected_cases()
    pop_cols = (
        ('susceptible', 'yellow', 'Alttiit'),
        ('infected', 'orange', 'Aktiiviset tartunnat'),
        ('all_detected', 'teal', 'Havaitut tapaukset (sim.)'),
        ('hospitalized', 'red', 'Sairaalassa'),
        ('dead', 'indigo', 'Kuolleet'),
        ('recovered', 'green', 'Toipuneet'),
    )

    traces = []
    for col, color, name in pop_cols:
        # if col in ('susceptible', 'recovered'):
        #    continue
        t = dict(
            type='scatter', line=dict(color=THEME_COLORS[color]),
            name=name, x=df.index, y=df[col], mode='lines',
            hoverformat='%d',
        )
        if col in ('susceptible', 'recovered'):
            t['visible'] = 'legendonly'
        traces.append(t)

    traces.append(dict(
        type='scatter', marker=dict(color='gray'),
        name='Havaitut tapaukset (tod.)', x=det.index, y=det['confirmed'], mode='markers'
    ))

    return traces


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
    out = render_result_graphs(df)
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
    from utils.perf import PerfCounter

    print('run simulation (days %d)' % simulation_days)
    set_variable('simulation_days', simulation_days)

    df = simulate_individuals(only_if_in_cache=True)
    if df is not None:
        return [render_result_graphs(df), render_result_table(df)]

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
