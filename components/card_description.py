from babel.numbers import format_decimal
import dash_html_components as html

from variables import get_variable


class Value:
    def __init__(self, val):
        self.val = val

    def __format__(self, fmt):
        val = self.val
        if fmt == 'noround':
            dec_fmt = None
        else:
            # Use three meaningful digits by default
            dec_fmt = '@@@'
        out = format_decimal(val, format=dec_fmt, locale='fi_FI')
        return '|%s|' % out


class CardDescription:
    def __init__(self):
        self.context = self._get_default_context()

    def _get_default_context(self):
        return dict(
            org_genitive=get_variable('org_genitive'),
            org_nominative=get_variable('org_nominative'),
            municipality_genitive=get_variable('municipality_genitive'),
            municipality_locative=get_variable('municipality_locative'),
            target_year=get_variable('target_year'),
        )

    def set_variables(self, **kwargs):
        self.context.update(kwargs)

    def set_values(self, **kwargs):
        ctx = {key: Value(value) for key, value in kwargs.items()}
        self.context.update(ctx)

    def render(self, s):
        out = s.format(**self.context)
        tokens = out.split('|')
        paragraphs = []
        els = []
        for idx, token in enumerate(tokens):
            if not token.strip():
                continue
            if idx == 0:
                token = token.lstrip()
            if idx % 2 == 0:
                el = token
            else:
                if token == 'p':
                    paragraphs.append(html.P(els))
                    els = []
                    continue
                else:
                    el = html.Span(token, className='summary-card__value')
            els.append(el)

        if els:
            paragraphs.append(html.P(els))
        return paragraphs
