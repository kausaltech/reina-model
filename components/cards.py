from __future__ import annotations

from dataclasses import dataclass

import dash_bootstrap_components as dbc
import dash_core_components as dcc
import dash_html_components as html
from dash.development.base_component import Component

from .graphs import Graph, PredictionFigure


class ConnectedCardBase:
    def __init__(self, id):
        self.upstream_card = None
        self.downstream_card = None
        self.id = id

    def connect_to(self, card: GraphCard):
        self.downstream_card = card
        card.upstream_card = self

    def render(self, is_top_row: bool = True) -> dbc.Card:
        raise NotImplementedError()

    def get_classes(self, is_top_row: bool):
        classes = ['mb-4']
        if self.downstream_card:
            classes.append('card-border-bottom')

        if self.upstream_card:
            classes.append('card-border-top')
            classes.append('grid-downstream-card')
        elif not is_top_row:
            classes.append('grid-unconnected-downstream-card')

        return classes


class ConnectedCard(ConnectedCardBase):
    def __init__(self, id, component):
        super().__init__(id)
        self.component = component

    def render(self, is_top_row: bool = True) -> dbc.Card:
        classes = self.get_classes(is_top_row)
        return dbc.Card(
            dbc.CardBody(children=self.component, className=' '.join(classes)),
        )


@dataclass
class GraphCard(ConnectedCardBase):
    id: str
    graph: dict = None
    slider: dict = None
    extra_content: Component = None
    link_to_page: Page = None

    def __post_init__(self):
        super().__init__(self.id)
        if self.graph is None:
            self.graph = {}
        self.description = None

    def render(self, is_top_row: bool = True) -> dbc.Card:
        graph = Graph(self.id, self.graph, self.slider)
        classes = self.get_classes(is_top_row)

        graph_el = html.Div(graph.render(), className="slider-card__content")
        if self.link_to_page:
            if isinstance(self.link_to_page, tuple):
                from pages.routing import get_page_for_emission_sector
                page = get_page_for_emission_sector(*self.link_to_page)
            else:
                page = self.link_to_page
            graph_el = dcc.Link(children=graph_el, href=page.path)

        card = dbc.Card(
            dbc.CardBody(children=[
                graph_el,
                dbc.Row(id=self.id + '-description'),
                self.extra_content,
            ]), className=' '.join(classes),
        )
        return card

    def set_figure(self, figure):
        if isinstance(figure, PredictionFigure):
            figure = figure.get_figure()
        self.graph['figure'] = figure

    def get_figure(self):
        return self.graph.get('figure')

    def set_description(self, description):
        self.description = description

    def get_description(self):
        return self.description

    def set_slider_value(self, val):
        self.slider['value'] = val

    def get_slider_value(self):
        return self.slider['value']
