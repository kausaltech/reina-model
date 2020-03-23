import dash
from datetime import date, timedelta
from flask_session import Session
from common import cache
import os
import pandas as pd
import dash_table
import dash_core_components as dcc
import dash_html_components as html
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from dash.dependencies import Input, Output, State

from calc.simulation import simulate_individuals
from components.cards import GraphCard
from components.graphs import make_layout
from variables import set_variable, get_variable


os.environ['DASH_PRUNE_ERRORS'] = 'False'
os.environ['DASH_SILENCE_ROUTES_LOGGING'] = 'False'


app = dash.Dash(__name__)  # suppress_callback_exceptions=True
app.css.config.serve_locally = True
app.scripts.config.serve_locally = True
server = app.server
with server.app_context():
    server.config.from_object('common.settings')

    cache.init_app(server)
    sess = Session()
    sess.init_app(server)


app.layout = dbc.Container([dbc.Row([dbc.Col([
    dbc.Row([
        dbc.Col([
            html.H2('COVID-19-epidemian kehittyminen: %s' % get_variable('area_name')),
        ], className='mb-4'),
    ], className='mt-4'),
    dbc.Row([
        dbc.Col([
            dbc.Button('Laske', id='run-simulation')
        ])
    ]),
    #         html.H5('R0-luku')
    #     ], md=12),
    #     dbc.Col([
    #         dcc.Slider(
    #             id="r0-slider", min=0, max=50, step=1, value=20,
    #             marks={x: '%.1f' % (x / 10) for x in range(0, 51, 5)}
    #         ),
    #     ], md=6),
    # ], className='mt-4'),
    dbc.Row([
        dbc.Col([
            dcc.Loading(html.Div(id="sir-graph-container"))
        ]),
    ]),
])])])


@app.callback(
    Output('sir-graph-container', 'children'),
    [Input('run-simulation', 'n_clicks')],
)
def building_selector_callback(n_clicks):
    df = simulate_individuals()
    df = df[['susceptible', 'infected', 'cum_detected', 'hospitalized', 'dead', 'recovered']]
    # df = df.drop(columns='susceptible')
    card = GraphCard('sir', graph=dict(config=dict(responsive=False)))

    traces = [dict(type='scatter', name=col, x=df.index, y=df[col], mode='lines') for col in df.columns]
    layout = make_layout(title='Epidemia', showlegend=True)
    fig = dict(data=traces, layout=layout)
    card.set_figure(fig)
    return card.render()


if __name__ == '__main__':
    # Write the process pid to a file for easier profiling with py-spy
    with open('.corona.pid', 'w') as pid_file:
        pid_file.write(str(os.getpid()))
    app.run_server(debug=True, port=8123)
