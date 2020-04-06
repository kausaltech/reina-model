from itertools import groupby
from dataclasses import dataclass
import numpy as np
from datetime import timedelta, date
from dash_table.Format import Format, Scheme
import dash_bootstrap_components as dbc
import dash_html_components as html
import dash_table
from dash.dependencies import Input, Output, State
from flask_babel import lazy_gettext as _

from components.cards import GraphCard
from components.graphs import make_layout
from calc.datasets import get_detected_cases
from calc.simulation import INTERVENTIONS
from utils.colors import THEME_COLORS
from variables import get_variable


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
    det = det[det['confirmed'] > 0]

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


IV_BACKGROUND_COLOR = '#eceae6'
IV_Y_HEIGHT = 0.08
IV_Y_MARGIN = IV_Y_HEIGHT * 3
IV_BAR_PIXELS = 30


@dataclass
class InterventionRange:
    start: date
    strength: float


INTERVENTION_TYPES = {
    'testing-mode': dict(label=_('Testing'), color='blue', order=0),
    'limit-mass-gatherings': dict(label=_('Limit mass gatherings'), color='orange', order=1),
    'limit-mobility': dict(label=_('Limit population mobility'), color='red', order=2),
    'import-infections': dict(label=_('Import infections'), color='red', type='event', order=3)
}


def _draw_one_intervention(index, ranges, name, y_start):
    iv_type = INTERVENTION_TYPES[name]

    shapes = []
    shapes.append(dict(
        type='rect', xref='x', yref='paper',
        x0=index[0], y0=y_start - IV_Y_HEIGHT, x1=index[-1], y1=y_start,
        fillcolor=IV_BACKGROUND_COLOR,
        line=dict(
            width=0,
        )
    ))
    for idx, r in enumerate(ranges):
        opacity = r.strength
        if len(ranges) > idx + 1:
            end = ranges[idx + 1].start
        else:
            end = index[-1]

        d = dict(
            type='rect', xref='x', yref='paper',
            x0=r.start, y0=y_start - IV_Y_HEIGHT, x1=end, y1=y_start,
            fillcolor=iv_type['color'],
            opacity=opacity,
            line=dict(
                width=0,
            )
        )
        if iv_type.get('type') == 'event':
            d['type'] = 'circle'
            d['x1'] = d['x0'] + timedelta(days=1)
        shapes.append(d)

    annotations = dict(
        xref='paper', yref='paper', x=1.025, y=y_start - IV_Y_HEIGHT, showarrow=False,
        text=iv_type['label'], xanchor='left', yanchor='bottom', yshift=-4
    )

    return shapes, [annotations]


def make_intervention_shapes(df):
    Y_START = -0.4

    shapes = []
    annotations = []

    cur_y = Y_START

    ivs = get_variable('interventions')
    icu_units = get_variable('icu_units')
    hospital_beds = get_variable('hospital_beds')

    out = []
    for iv in ivs:
        name = iv[0]
        if name == 'test-all-with-symptoms':
            name = 'testing-mode'
            strength = 0.5
        elif name == 'test-only-severe-symptoms':
            name = 'testing-mode'
            strength = 0.2
        elif name == 'test-with-contact-tracing':
            name = 'testing-mode'
            strength = 0.8
        elif name == 'limit-mobility':
            strength = iv[2] / 100
        elif name == 'limit-mass-gatherings':
            if iv[2] >= 500:
                strength = 0.1
            elif iv[2] >= 100:
                strength = 0.3
            elif iv[2] >= 50:
                strength = 0.5
            elif iv[2] >= 10:
                strength = 0.8
            elif iv[2] >= 2:
                strength = 1.0
        elif name == 'import-infections':
            strength = 0.5
        else:
            continue

        out.append((name, iv[1], strength))

    ivs = sorted(out, key=lambda x: (INTERVENTION_TYPES[x[0]]['order'], x[0], x[1]))
    bar_count = 0
    for name, group in groupby(ivs, lambda x: x[0]):
        ranges = [InterventionRange(date.fromisoformat(x[1]), x[2]) for x in group]

        s, a = _draw_one_intervention(df.index, ranges, name, cur_y)
        shapes += s
        annotations += a
        cur_y -= IV_Y_MARGIN
        bar_count += 1

    return shapes, annotations, bar_count


def render_population_card(df):
    traces = generate_population_traces(df)
    card = GraphCard('population', graph=dict(config=dict(responsive=False)))
    shapes, annotations, bar_count = make_intervention_shapes(df)

    layout = make_layout(
        title=_('Population'), height=250 + bar_count * IV_BAR_PIXELS, showlegend=True,
        margin=dict(r=250, b=75 + bar_count * IV_BAR_PIXELS),
        shapes=shapes,
        annotations=annotations
    )
    fig = dict(data=traces, layout=layout)
    card.set_figure(fig)
    return card.render()


def render_result_graphs(df):
    hc_cols = (
        ('available_hospital_beds', _('Hospital beds')),
        ('available_icu_units', _('ICU units')),
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

    df['ifr'] = df.dead.divide(df.all_infected.replace(0, np.inf)) * 100
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
        dbc.Col(render_population_card(df), md=12),
        dbc.Col(c2, md=12),
        dbc.Col(c3, md=12),
        dbc.Col(render_validation_card(df), md=12),
    ])


def render_result_table(df):
    df = df.rename(columns=dict(tests_run_per_day='positive_tests_per_day'))
    df = df.drop(columns='us_per_infected')
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
            dbc.Button(
                _('Simulation result data'), className="float-left",
                id="simulation-results-data-collapse-button",
            ),
        ]),
        dbc.Collapse([
            dbc.CardBody([res_table], className="px-5"),
        ], is_open=False, id='simulation-results-data-collapse'),
    ], className='mb-4')

    return dbc.Row([dbc.Col(card)])


def render_indicators(df):
    rdays = df['mobility_limitation'].dropna().cumsum().iloc[-1]
    icu_cap = ((df['available_icu_units'] / df['total_icu_units']) < 0.1).sum()
    dead = df['dead'].dropna().iloc[-1]

    # Indicator Placemarkers TODO: Map to data
    cols = []
    cols.append(dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.H6(_('Restriction Day Index')),
                html.P('%d' % rdays, className="display-4"),
                html.Small("Total number of days with full mobility interventions."),
            ])
        ), width=dict(size=4))
    )
    cols.append(dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.H6(_('ICU Capacity Exceeded')),
                html.P('%d' % icu_cap, className="display-4"),
                html.Small("Days ICU units had less than 10% of capacity left."),
            ])
        ), width=dict(size=4))
    )
    cols.append(dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.H6(_('Fatalities')),
                html.P('%d' % dead, className="display-4"),
                html.Small("Total number of deaths."),
            ])
        ), width=dict(size=4))
    )
    return dbc.Row(cols)


def render_results(df):
    return html.Div([render_indicators(df), render_result_graphs(df), render_result_table(df)])


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
