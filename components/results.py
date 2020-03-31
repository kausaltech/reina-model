import numpy as np
from dash_table.Format import Format, Scheme
import dash_bootstrap_components as dbc
import dash_html_components as html
import dash_table
from dash.dependencies import Input, Output, State
from flask_babel import lazy_gettext as _

from components.cards import GraphCard
from components.graphs import make_layout
from calc.datasets import get_detected_cases
from utils.colors import THEME_COLORS


COLUMN_COLORS = {
    'all_detected': THEME_COLORS['teal'],
    'hospitalized': THEME_COLORS['orange'],
    'in_icu': THEME_COLORS['cyan'],
    'dead': THEME_COLORS['indigo'],
}


POP_COLS = (
    ('susceptible', 'yellow', _('Susceptible')),
    ('infected', 'purple', _('Active infections')),
    ('all_detected', 'teal', _('Detected cases')),
    ('hospitalized', 'orange', _('Hospitalized')),
    ('in_icu', 'red', _('In ICU')),
    ('dead', 'indigo', _('Dead')),
    ('recovered', 'green', _('Recovered')),
)


def generate_population_traces(df):
    traces = []
    for col, color, name in POP_COLS:
        # if col in ('susceptible', 'recovered'):
        #    continue
        t = dict(
            type='scatter', line=dict(color=THEME_COLORS[color]),
            name=name, x=df.index, y=df[col], mode='lines',
            hoverformat='%d', hoverlabel=dict(namelength=-1),
        )
        if col in ('susceptible', 'recovered'):
            t['visible'] = 'legendonly'
        traces.append(t)

    return traces


def render_validation_card(df):
    det = get_detected_cases()
    max_date = det.index.max()
    df = df[df.index <= max_date]

    traces = []
    for col_name in ('all_detected', 'hospitalized', 'in_icu', 'dead'):
        col = [x for x in POP_COLS if x[0] == col_name][0]
        traces.append(dict(
            type='scatter', mode='lines', line=dict(color=COLUMN_COLORS[col_name]),
            name=col[2] + ' ' + _('(simulated)'),
            x=df.index, y=df[col_name],
            hoverlabel=dict(namelength=-1),
        ))
        col_name_map = {
            'all_detected': 'confirmed',
            'dead': 'deaths',
        }
        det_col_name = col_name_map.get(col_name, col_name)
        traces.append(dict(
            type='scatter', mode='markers', line=dict(color=COLUMN_COLORS[col_name]),
            name=col[2] + ' ' + _('(real)'),
            x=det.index, y=det[det_col_name],
            hoverlabel=dict(namelength=-1),
        ))

    card = GraphCard('validation', graph=dict(config=dict(responsive=False)))
    layout = make_layout(
        title=_('Validation'), height=250, showlegend=True,
        margin=dict(r=250)
    )
    fig = dict(data=traces, layout=layout)
    card.set_figure(fig)
    return card.render()


def render_result_graphs(df):
    traces = generate_population_traces(df)
    card = GraphCard('population', graph=dict(config=dict(responsive=False)))
    layout = make_layout(
        title=_('Population'), height=250, showlegend=True,
        margin=dict(r=250)
    )
    fig = dict(data=traces, layout=layout)
    card.set_figure(fig)
    c1 = card.render()

    hc_cols = (
        ('hospital_beds', _('Hospital beds')),
        ('icu_units', _('ICU units')),
    )
    traces = []
    for col, name in hc_cols:
        t = dict(
            type='scatter', name=name, x=df.index, y=df[col], mode='lines',
            hoverlabel=dict(namelength=-1),
        )
        traces.append(t)

    card = GraphCard('healthcare', graph=dict(config=dict(responsive=False)))
    layout = make_layout(
        title=_('Free capacity in the healthcare system'), height=250, showlegend=True,
        margin=dict(r=250)
    )
    fig = dict(data=traces, layout=layout)
    card.set_figure(fig)
    c2 = card.render()

    df['ifr'] = df.dead.divide((df.infected + df.recovered).replace(0, np.inf)) * 100
    df['cfr'] = df.dead.divide(df.all_detected.replace(0, np.inf)) * 100
    df['r'] = df['r'].rolling(window=7).mean()

    param_cols = (
        ('r', _('Reproductive number (Rₜ)')),
        ('ifr', _('Infection fatality ratio (IFR, %')),
        ('cfr', _('Case fatality ratio (CFR, %')),
    )
    card = GraphCard('params', graph=dict(config=dict(responsive=False)))
    traces = []
    for col, name in param_cols:
        t = dict(
            type='scatter', name=name, x=df.index, y=df[col], mode='lines',
            hoverlabel=dict(namelength=-1),
        )
        traces.append(t)
    layout = make_layout(
        title=_('Epidemic parameters'), height=250, showlegend=True,
        margin=dict(r=250)
    )
    fig = dict(data=traces, layout=layout)
    card.set_figure(fig)
    c3 = card.render()

    return dbc.Row([
        dbc.Col(c1, md=12),
        dbc.Col(c2, md=12),
        dbc.Col(c3, md=12),
        dbc.Col(render_validation_card(df), md=12),
    ])


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

    res_table = dash_table.DataTable(
        id='simulation-results-table',
        data=rows,
        columns=cols,
        style_table={'overflowX': 'scroll'},
        export_format='xlsx',
    )

    card = dbc.Card([
        dbc.CardHeader([
            html.H2(dbc.Button(
                _('Simulation result data'), className="float-left mt-2",
                id="simulation-results-data-collapse-button",
            )),
        ]),
        dbc.Collapse([
            dbc.CardBody([res_table], className="px-5"),
        ], is_open=False, id='simulation-results-data-collapse'),
    ], className='mb-4')

    return dbc.Row([dbc.Col(card)])


def render_results(df):
    return html.Div([render_result_graphs(df), render_result_table(df)])


def register_results_callbacks(app):
    @app.callback(
        Output("simulation-results-data-collapse", "is_open"),
        [Input("simulation-results-data-collapse-button", "n_clicks")],
        [State("simulation-results-data-collapse", "is_open")],
    )
    def toggle_iv_collapse(n, is_open):
        if n:
            return not is_open
        return is_open
