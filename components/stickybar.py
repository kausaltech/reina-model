from dataclasses import dataclass
import dash_html_components as html
import dash_bootstrap_components as dbc
import dash_core_components as dcc
import plotly.graph_objs as go
import numpy as np
import pandas as pd

from variables import get_variable
from calc.emissions import predict_emissions, predict_emission_reductions, get_sector_by_path
from utils.colors import generate_color_scale


@dataclass
class StickyBar:
    label: str = None
    value: float = None
    unit: str = None
    goal: float = None
    current_page: object = None
    below_goal_good: bool = True

    def _calc_emissions(self):
        df = predict_emissions()
        forecast = df.pop('Forecast')
        self.emissions_df = df

        df = df.sum(axis=1)
        self.last_historical_year = df.loc[~forecast].index.max()
        self.target_year = get_variable('target_year')
        ref_year = get_variable('ghg_reductions_reference_year')
        perc = get_variable('ghg_reductions_percentage_in_target_year')
        ref_emissions = df.loc[ref_year]
        last_emissions = df.loc[self.last_historical_year]
        target_emissions = ref_emissions * (1 - perc / 100)
        self.target_emissions = target_emissions
        self.needed_reductions = last_emissions - target_emissions
        self.scenario_emissions = df.loc[self.target_year]
        self.scenario_reductions = last_emissions - self.scenario_emissions

    def _render_subsectors(self, df, sector_name, cur_x):
        page = self.current_page
        if page is not None and page.emission_sector is not None and \
                page.emission_sector[0] == sector_name:
            active_sector = True
            sector_path = page.emission_sector
        else:
            sector_path = (sector_name,)
            active_sector = False

        path = list(sector_path)
        primary_sector = path.pop(0)
        primary_sector_metadata = get_sector_by_path(primary_sector)
        df = df[primary_sector]

        last_year = df.iloc[-1]
        if not isinstance(last_year, pd.Series):
            last_year = pd.Series([last_year], index=(sector_name,))
        last_year = last_year.dropna(axis=0)
        emissions_left = last_year.dropna(axis=0).sum()

        sector_metadata = primary_sector_metadata
        for p in path:
            try:
                next_sector = last_year[p]
                if not isinstance(next_sector, pd.Series):
                    break
                last_year = next_sector
                sector_metadata = primary_sector_metadata['subsectors'][p]
            except KeyError:
                # The sector might be missing because it has emissions
                # increases instead of decreases.
                last_year = pd.Series()

        if not active_sector:
            last_year = pd.Series()
        else:
            if isinstance(last_year.index, pd.MultiIndex) and len(last_year.index.levels) > 1:
                last_year = last_year.sum(axis=0, level=0)

        colors = generate_color_scale(primary_sector_metadata['color'], len(last_year.index) + 1)
        colors.remove(primary_sector_metadata['color'])
        colors.reverse()

        traces = []
        active_emissions = 0
        for sector_name, emissions in last_year.items():
            if isinstance(sector_name, tuple):
                sector_name = sector_name[0]
            if not emissions or np.isnan(emissions):
                continue
            if not sector_name and len(last_year) == 1:
                break
            if sector_name:
                ss_metadata = sector_metadata['subsectors'][sector_name]
            else:
                ss_metadata = sector_metadata

            color = colors.pop(0)
            name = ss_metadata.get('improvement_name') or ss_metadata['name']
            bar = dict(
                type='bar',
                x=[emissions],
                name=name,
                orientation='h',
                hoverinfo='text',
                hovertext='%.0f kt: %s' % (emissions, name),
                marker=dict(
                    color=color
                )
            )
            traces.append(bar)
            emissions_left -= emissions
            active_emissions += emissions

        md = primary_sector_metadata
        name = md.get('improvement_name') or md['name']
        if traces:
            name = '%s (muu)' % name
        else:
            active_emissions = emissions_left

        traces.append(dict(
            type='bar',
            x=[emissions_left],
            name=name,
            orientation='h',
            hoverinfo='text',
            hovertext='%.0f kt: %s' % (emissions_left, name),
            marker=dict(
                color=primary_sector_metadata['color'],
                line_width=0,
            )
        ))

        shapes = []
        if active_sector:
            shapes.append(dict(
                type='rect',
                x0=cur_x,
                x1=cur_x + active_emissions,
                y0=0,
                y1=1,
                yref='paper',
                line=dict(
                    color='#888',
                    width=4,
                )
            ))

        return traces, shapes

    def _render_emissions_bar(self):
        df = predict_emission_reductions()
        last_year = df.iloc[-1]
        # For now, drop sectors that have emission increases...
        df = df.drop(columns=last_year[last_year < 0].index)
        main_sectors = df.iloc[-1].sum(level=0).sort_values(ascending=False)

        traces = []
        shapes = []
        cur_x = 0
        for sector_name, emissions in main_sectors.items():
            new_traces, new_shapes = self._render_subsectors(df, sector_name, cur_x)
            traces += new_traces
            shapes += new_shapes
            for trace in new_traces:
                cur_x += trace['x'][0]

        if self.scenario_reductions >= self.needed_reductions:
            range_max = self.scenario_reductions
        else:
            bar = dict(
                type='bar',
                x=[self.needed_reductions - self.scenario_reductions],
                name='Tavoitteesta puuttuu',
                orientation='h',
                hovertemplate='%{x: .0f} kt',
                marker=dict(
                    color='#888'
                ),
                opacity=0.5,
            )
            traces.append(bar)
            range_max = self.needed_reductions

        fig = go.Figure(
            data=traces,
            layout=go.Layout(
                shapes=shapes,
                xaxis=dict(
                    showgrid=False,
                    showline=False,
                    showticklabels=False,
                    zeroline=False,
                    # domain=[0.15, 1],
                    autorange=False,
                    range=[0, range_max],
                ),
                yaxis=dict(
                    showgrid=False,
                    showline=False,
                    showticklabels=False,
                    zeroline=False,
                ),
                margin=dict(
                    l=0,  # noqa
                    r=2,
                    b=2,
                    t=2,
                    pad=0,
                ),
                barmode='stack',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
                width=None,
                autosize=True,
                clickmode='none',
                dragmode=False,
                #   transition={'duration': 500},
            ),
        )

        graph = dcc.Graph(
            config={
                'displayModeBar': False,
                'responsive': True,
            },
            style={'height': 60, 'width': '100%'},
            figure=fig,
        )
        return graph

    def _render_value_summary(self, value, goal, label, unit, below_goal_good):
        classes = []
        if goal is not None:
            if (value <= goal and below_goal_good) or \
                    (value >= goal and not below_goal_good):
                classes.append('page-summary__total--good')
            else:
                classes.append('page-summary__total--bad')

            target_el = html.Div([
                "tavoite %.0f" % goal,
                html.Span(" %s" % unit, className="unit")
            ], className="page-summary__target")
        else:
            target_el = None

        classes.append('page-summary__total')

        summary = [
            html.H6(f'{label} ({self.target_year})'),
            html.Div([
                html.Div([
                    "%.0f" % value,
                    html.Span(" %s" % unit, className="unit")
                ], className=' '.join(classes)),
                target_el,
            ], className="page-summary__totals"),
        ]
        return summary

    def render(self):
        self._calc_emissions()
        pötkylä = dbc.Col([
            html.H6('Skenaarion mukaiset päästövähennykset %s–%s' % (self.last_historical_year, self.target_year)),
            self._render_emissions_bar()
        ], md=6)

        emissions_summary = self._render_value_summary(
            self.scenario_emissions, self.target_emissions, 'Kaikki päästöt yhteensä',
            'kt/vuosi', True
        )
        emissions_summary = dbc.Col(emissions_summary, md=3)

        if self.value is not None:
            summary = self._render_value_summary(
                self.value, self.goal, self.label, self.unit, self.below_goal_good
            )
            summary = dbc.Col(summary, md=3)
        else:
            summary = dbc.Col(md=3)

        return dbc.Alert([
            dbc.Row([pötkylä, summary, emissions_summary])
        ], className="page-summary fixed-bottom")


if __name__ == '__main__':
    # from calc.geothermal import get_historical_production
    # get_historical_production()
    from pages.routing import get_page_for_emission_sector
    page = get_page_for_emission_sector('BuildingHeating', 'DistrictHeat')
    assert page is not None
    StickyBar(current_page=page).render()
