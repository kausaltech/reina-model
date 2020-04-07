from flask_babel import lazy_gettext as _
import dash
import dash_html_components as html
import dash_table
import dash_core_components as dcc
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from calc.simulation import sample_model_parameters
from components.graphs import make_layout
from components.cards import GraphCard
from variables import set_variable, get_variable, reset_variable


SYMPTOM_MAP = {
    'ASYMPTOMATIC': _('Asymptomatic'),
    'MILD': _('Mild'),
    'SEVERE': _('Severe'),
    'CRITICAL': _('Critical'),
    'FATAL': _('Fatal'),
}

SYMPTOM_COLOR_MAP = {
    'MILD': 'yellow',
    'SEVERE': 'orange',
    'CRITICAL': 'red',
    'FATAL': 'black',
}


def render_model_param_graphs(age):
    PERIOD_PARAMS = (
        ('incubation_period', _('Incubation period')),
        ('hospitalization_period', _('Duration of hospital treatment')),
        ('icu_period', _('Duration of ICU treatment')),
    )

    period_cards = []
    for param, label in PERIOD_PARAMS:
        card = GraphCard(param, graph=dict(config=dict(responsive=False)))
        layout = make_layout(
            title=label, height=250,
            yaxis=dict(
                title='%'
            ),
            xaxis=dict(
                title=_('days')
            ),
        )
        traces = []
        if param == 'incubation_period':
            sample = sample_model_parameters(param, age)
            sample = sample * 100 / sample.sum()
            trace = dict(
                type='bar', x=sample.index, y=sample.values,
                hovertemplate='%{y} %', name='',
            )
            traces.append(trace)
        else:
            for severity in ('SEVERE', 'CRITICAL', 'FATAL'):
                if severity == 'SEVERE' and param == 'icu_period':
                    continue
                sample = sample_model_parameters(param, age, severity)
                sample = sample * 100 / sample.sum()
                trace = go.Bar(
                    type='bar', x=sample.index, y=sample.values,
                    hovertemplate='%{y} %', name=str(SYMPTOM_MAP[severity]),
                    marker_color=SYMPTOM_COLOR_MAP[severity]
                )
                traces.append(trace)
            layout['barmode'] = 'group'
            layout['showlegend'] = True

        fig = dict(layout=layout, data=traces)
        card.set_figure(fig)
        period_cards.append(card.render())

    sample = sample_model_parameters('symptom_severity', age)
    sample.index = sample.index.map(SYMPTOM_MAP)
    card = GraphCard('symptom-severity', graph=dict(config=dict(responsive=False)))
    layout = make_layout(
        title=_('Symptom severity'), height=250, showlegend=False,
        yaxis=dict(
            title='%'
        ),
    )
    sample = sample * 100 / sum(sample)
    trace = dict(type='bar', x=sample.index, y=sample.values)
    fig = dict(layout=layout, data=[trace])
    card.set_figure(fig)
    c2 = card.render()

    sample = sample_model_parameters('contacts_per_day', age)
    card = GraphCard('contacts_per_day', graph=dict(config=dict(responsive=False)))
    layout = make_layout(
        title=_('Contacts per day'), height=250, showlegend=False,
        yaxis=dict(
            title='%',
        ),
        xaxis=dict(
            title=_('number of contacts')
        ),
    )
    sample = sample.reindex(range(0, 100), fill_value=0)
    sample = sample * 100 / sum(sample)
    trace = dict(type='bar', x=sample.index, y=sample.values)
    fig = dict(layout=layout, data=[trace])
    card.set_figure(fig)
    c3 = card.render()

    sample = sample_model_parameters('infectiousness', age)
    sample *= 100
    card = GraphCard('infectiousness', graph=dict(config=dict(responsive=False)))
    layout = make_layout(
        title=_('Infectiousness over time'), height=250, showlegend=False,
        yaxis=dict(
            title='%',
        ),
        xaxis=dict(
            title=_('Day of illness'),
            range=[-2, 14],
        ),
    )
    trace = dict(
        type='lines', x=sample.index, y=sample.values,
        line=dict(shape='spline', smoothing=0.3),
    )
    fig = dict(layout=layout, data=[trace])
    card.set_figure(fig)
    c4 = card.render()

    return html.Div([
        dbc.Row([
            dbc.Col(c2, md=6), dbc.Col(c3, md=6), dbc.Col(c4, md=6),
            *[dbc.Col(c, md=6) for c in period_cards]
        ], className='mt-4')
    ])


DISEASE_PARAMS = (
    ('p_asymptomatic', _('Ratio of all infected people who remain asymptomatic'), '%',),
    ('p_infection', _('Probability of becoming infected after being exposed'), '%',),
    # ('p_critical', _('Probability of requiring ICU care after having severe symptoms'), '%',),
    # ('p_icu_death', _('Probability of dying during ICU care'), '%'),
    ('p_hospital_death', _('Probability of dying after regular hospital treatment'), '%'),
    ('p_hospital_death_no_beds', _('Probability of dying if no hospital beds are available'), '%'),
    ('p_icu_death_no_beds', _('Probability of dying if no ICU units are available'), '%'),
    ('mean_illness_duration', _('Mean number of days of being ill'), _('days')),
    ('mean_hospitalization_duration', _('Mean number of days of being hospitalized'), _('days')),
    ('mean_icu_duration', _('Mean number of days of being in ICU care'), _('days')),
    ('mean_hospitalization_duration_before_icu', _('Mean number of days in regular hospital care before ICU'), _('days')),
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
            {'name': _('Description'), 'id': 'label', 'editable': False},
            {
                'name': _('Value'),
                'id': 'value',
                'editable': True,
                'format': value_fmt,
                'type': 'numeric',
                'validation': dict(allow_null=False),
            },
            {'name': '', 'id': 'unit', 'editable': False},
        ],
        style_cell={'textAlign': 'left'},
        style_cell_conditional=[
            {
                'if': {'column_id': 'value'},
                'textAlign': 'right'
            }
        ],
        style_as_list_view=True,
        editable=True,
    )

    card = dbc.Card([
        dbc.CardHeader([
            dbc.Button(
                _('Disease parameters'), className="float-left",
                id="disease-collapse-button",
            ),
        ]),
        dbc.Collapse([
            dbc.CardBody([
                dp_table,
                html.Div(dbc.Button(
                    _('Restore defaults'), id='disease-params-reset-defaults', color='secondary',
                    size='sm', className='mt-3'
                ), className='text-right'),
                html.Div(id='disease-param-specifics'),
            ], className="px-5"),
        ], is_open=False, id='disease-collapse'),
    ], className='mb-4')

    return card


def register_params_callbacks(app):
    @app.callback(
        [
            Output("disease-collapse", "is_open"),
            Output("disease-param-specifics", "children")
        ],
        [Input("disease-collapse-button", "n_clicks")],
        [State("disease-collapse", "is_open")],
    )
    def toggle_disease_collapse(n, is_open):
        if n:
            is_open = not is_open

        if is_open:
            out = html.Div([
                dbc.Row([dbc.Col(html.H5(_('Distributions based on model parameters')))]),
                dbc.Row([dbc.Col([
                    html.P(_('Age of person')),
                    dcc.Slider(
                        id='disease-params-age-slider', min=0, max=90, step=1, value=60,
                        marks={x: str(x) for x in range(0, 90 + 1, 10)}
                    ),
                ])]),
                dbc.Row([dbc.Col([
                    html.P(_('Limit population mobility')),
                    dcc.Slider(
                        id='disease-params-limit-mobility-slider', min=0, max=100, step=1, value=0,
                        marks={x: '%s %%' % x for x in range(0, 100 + 1, 10)}
                    ),
                ])]),
                html.Div(id='disease-params-graphs'),
            ])
        else:
            out = None
        return [is_open, out]

    @app.callback(
        Output('disease-params-table', 'data'),
        [
            Input('disease-params-table', 'data_timestamp'),
            Input('disease-params-reset-defaults', 'n_clicks'),
        ], [
            State('disease-params-table', 'data'),
        ]
    )
    def disease_params_data_callback(ts, reset_clicks, rows):
        ctx = dash.callback_context
        if ctx.triggered:
            c_id = ctx.triggered[0]['prop_id'].split('.')[0]
            if reset_clicks is not None and c_id == 'disease-params-reset-defaults':
                for row in rows:
                    reset_variable(row['id'])
                    row['value'] = get_variable(row['id'])

        for row in rows:
            if not isinstance(row['value'], (int, float)):
                row['value'] = get_variable(row['id'])
            if row['value'] < 0:
                row['value'] = 0
            elif row['value'] > 100:
                row['value'] = 100
            set_variable(row['id'], float(row['value']))

        return rows

    @app.callback(
        Output('disease-params-graphs', 'children'),
        [
            Input('disease-params-age-slider', 'value'),
            Input('disease-params-limit-mobility-slider', 'value'),
        ]
    )
    def person_age_callback(age, mobility_limit):
        set_variable('sample_limit_mobility', mobility_limit)
        return render_model_param_graphs(age)
