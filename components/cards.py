from __future__ import annotations

from dataclasses import dataclass
from dash.development.base_component import Component
from dash_archer import DashArcherContainer, DashArcherElement
import dash_bootstrap_components as dbc
import dash_html_components as html
import dash_core_components as dcc

from utils.colors import ARCHER_STROKE
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


class ConnectedCardGridRow:
    width = 12

    def __init__(self):
        self.cards = []

    def add_card(self, card: GraphCard):
        self.cards.append(card)

    def set_width(self, width: int):
        self.width = width


class ConnectedCardGrid:
    def __init__(self):
        self.rows = []

    def make_new_row(self) -> ConnectedCardGridRow:
        row = ConnectedCardGridRow()
        self.rows.append(row)
        return row

    def add_card(self, card: ConnectedCardBase):
        """Helper method to add a card to the last row"""
        self.rows[-1].add_card(card)

    def render(self) -> Component:
        grid_has_archer = False
        # First check if this is an archered grid
        for row in self.rows:
            for card in row.cards:
                if card.downstream_card or card.upstream_card:
                    grid_has_archer = True
                    break
            if grid_has_archer:
                break

        rows = []
        for row_idx, row in enumerate(self.rows):
            grid_cols_per_card = 12 // len(row.cards)
            cols = []
            for card in row.cards:
                is_top_row = row_idx == 0
                card_el = card.render(is_top_row)
                if card.downstream_card or card.upstream_card:
                    relations = []
                    if card.downstream_card:
                        relations.append(dict(
                            targetId='%s-elem' % card.downstream_card.id,
                            targetAnchor='top',
                            sourceAnchor='bottom'
                        ))
                    card_el = DashArcherElement(
                        card_el,
                        id='%s-elem' % card.id,
                        relations=relations
                    )

                cols.append(dbc.Col(md=grid_cols_per_card, children=card_el))

            rows.append(dbc.Row(cols))

        if grid_has_archer:
            children = DashArcherContainer(
                rows,
                strokeColor=ARCHER_STROKE['default']['color'],
                strokeWidth=ARCHER_STROKE['default']['width'],
                arrowLength=0.001,
                arrowThickness=0.001,
            )
        else:
            children = rows

        return dbc.Row(dbc.Col(md=10, children=children))
