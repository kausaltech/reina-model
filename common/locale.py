from plotly import utils as plotly_utils
from flask_babel.speaklater import LazyString
from flask import request, session
import flask


class JSONEncoder(plotly_utils.PlotlyJSONEncoder):
    def default(self, o):
        if isinstance(o, LazyString):
            return str(o)

        return super().default(o)


def get_active_locale():
    if not flask.has_request_context():
        return 'fi'

    language = session.get('language')
    if language:
        return language
    return request.accept_languages.best_match(['fi', 'en'])


def init_locale(babel):
    # Monkeypatch Plotly to accept lazystrings
    plotly_utils.PlotlyJSONEncoder = JSONEncoder
    babel.localeselector(get_active_locale)
