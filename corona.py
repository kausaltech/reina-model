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

from calc.sir import simulate_progress
from components.cards import GraphCard
from components.graphs import make_layout
from variables import set_variable


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
            html.H2('Koronaepidemian kehittyminen'),
        ], className='mb-4'),
    ], className='mt-4'),
    dbc.Row([
        dbc.Col([
            html.H5('R0-luku')
        ], md=12),
        dbc.Col([
            dcc.Slider(
                id="r0-slider", min=0, max=50, step=1, value=20,
                marks={x: '%.1f' % (x / 10) for x in range(0, 51, 5)}
            ),
        ], md=6),
    ], className='mt-4'),
    dbc.Row([
        dbc.Col([
            html.Div(id="sir-graph-container")
        ]),
    ]),
])])])


@app.callback(
    Output('sir-graph-container', 'children'),
    [
        Input('r0-slider', 'value'),
    ]
)
def building_selector_callback(r0_value):
    set_variable('r0', r0_value / 10)
    df = simulate_progress()
    card = GraphCard('sir', graph=dict(config=dict(responsive=False)))

    t0 = pd.date_range(date.today(), periods=df.index.max())
    traces = [dict(type='scatter', name=col, x=t0, y=df[col], mode='lines') for col in df.columns]
    layout = make_layout(title='Infected')
    fig = dict(data=traces, layout=layout)
    card.set_figure(fig)
    return card.render()


if __name__ == '__main__':
    # Write the process pid to a file for easier profiling with py-spy
    with open('.corona.pid', 'w') as pid_file:
        pid_file.write(str(os.getpid()))
    app.run_server(debug=True, port=8123)
