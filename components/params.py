from flask_babel import lazy_gettext as _
import dash
import dash_html_components as html
import dash_table
import dash_core_components as dcc
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc

from calc.simulation import sample_model_parameters
from components.graphs import make_layout
from components.cards import GraphCard
from variables import set_variable, get_variable, reset_variable


def render_model_param_graphs(age):
    sample = sample_model_parameters('incubation_period', age)
    card = GraphCard('incubation-period', graph=dict(config=dict(responsive=False)))
    layout = make_layout(
        title=_('Incubation period'), height=250, showlegend=False,
        yaxis=dict(
            title='%'
        ),
        xaxis=dict(
            title=_('days')
        ),
    )
    sample = sample * 100 / sum(sample)
    trace = dict(
        type='bar', x=sample.index, y=sample.values,
        hovertemplate='%{y} %', name='',
    )
    fig = dict(layout=layout, data=[trace])
    card.set_figure(fig)
    c1 = card.render()

    sample = sample_model_parameters('symptom_severity', age)
    sample.index = sample.index.map({
        'ASYMPTOMATIC': _('Asymptomatic'),
        'MILD': _('Mild'),
        'SEVERE': _('Severe'),
        'CRITICAL': _('Critical'),
    })
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
            range=[0, 15]
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

    return html.Div([
        dbc.Row([dbc.Col(html.H5(_('Distributions for a %(age)d-year-old person', age=age)))]),
        dbc.Row([dbc.Col(c1, md=6), dbc.Col(c2, md=6), dbc.Col(c3, md=6)], className='mt-4')
    ])


DISEASE_PARAMS = (
    ('p_asymptomatic', _('Ratio of all infected people who remain asymptomatic'), '%',),
    ('p_infection', _('Probability of becoming infected after being exposed'), '%',),
    # ('p_critical', _('Probability of requiring ICU care after having severe symptoms'), '%',),
    ('p_icu_death', _('Probability of dying during ICU care'), '%'),
    ('p_hospital_death', _('Probability of dying after regular hospital treatment'), '%'),
    ('p_hospital_death_no_beds', _('Probability of dying if no hospital beds are available'), '%'),
    ('p_icu_death_no_beds', _('Probability of dying if no ICU units are available'), '%')
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
            html.H2(dbc.Button(
                _('Disease parameters'), className="float-left mt-2",
                id="disease-collapse-button",
            )),
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
                dbc.Row([dbc.Col([
                    dcc.Slider(
                        id='disease-params-age-slider', min=0, max=80, step=1, value=60,
                        marks={x: str(x) for x in range(0, 80 + 1, 10)}
                    ),
                    html.P(_('Age of person')),
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
        ]
    )
    def person_age_callback(value):
        return render_model_param_graphs(value)
