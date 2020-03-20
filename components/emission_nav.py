import pandas as pd
import dash_html_components as html
import dash_bootstrap_components as dbc

from pages.routing import get_page_for_emission_sector
from calc.emissions import predict_emissions, SECTORS

from variables import get_variable


def _make_nav_item(sector_name, emissions, indent, page, bold=False, active=False):
    attrs = {}
    if page is None:
        attrs['disabled'] = True
    else:
        attrs['disabled'] = False
        attrs['href'] = page.path
    style = {}
    if indent:
        style = {'marginLeft': '%drem' % 2 * indent}
    if bold:
        style = {'fontWeight': 'bold'}

    if active:
        attrs['active'] = True

    item = dbc.ListGroupItem(
        [
            html.Span(sector_name, style=style),
            dbc.Badge("%.0f kt" % emissions, color="light", className="ml-1 float-right")
        ],
        action=True,
        **attrs
    )
    return item


def make_emission_nav(current_page):
    df = predict_emissions()
    target_year = get_variable('target_year')

    ts = df.sort_index().drop(columns='Forecast', level=0).loc[target_year]

    items = []

    current_sector = current_page.emission_sector if current_page and current_page.emission_sector else None
    # Sort sectors based on the target year emissions
    sector_emissions = ts.sum(level=0).sort_values(ascending=False)

    def render_sector(s, sector_path, level):
        sector_emissions = s.sum(level=0).sort_values(ascending=False)
        for subsector_name, emissions in sector_emissions.iteritems():
            if not subsector_name:
                continue
            subsector_path = tuple([*sector_path, subsector_name])

            next_metadata = SECTORS
            for sp in subsector_path:
                metadata = next_metadata[sp]
                next_metadata = metadata.get('subsectors', {})

            if current_sector == subsector_path:
                active = True
            else:
                active = False

            page = get_page_for_emission_sector(*subsector_path)
            item = _make_nav_item(
                metadata['name'], emissions, level, page, active=active
            )
            items.append(item)

            ss = s[subsector_name]
            if isinstance(ss, pd.Series):
                render_sector(ss, subsector_path, level + 1)

    render_sector(ts, tuple(), 0)

    items.append(_make_nav_item('Yhteensä', sector_emissions.sum(), 0, None, bold=True))

    return html.Div([
        html.H6('Päästöt vuonna %s' % target_year),
        dbc.ListGroup(children=items)
    ])


if __name__ == '__main__':
    pd.set_option('display.max_rows', None)
    make_emission_nav(None)
