import traceback
from flask import Flask
from flask_babel import Babel
from flask_cors import CORS
from flask_session import Session
from graphql_schema import schema
from graphql_server.flask import GraphQLView


class ExceptionMiddleware:
    def resolve(self, next, root, info, **args):
        try:
            promise = next(root, info, **args)
        except Exception:
            traceback.print_exc()
            raise
        return promise


class ReinaGraphQLView(GraphQLView):
    def format_error(self, error):
        ret = super().format_error(error)
        return ret


app = Flask(__name__)

CORS(app, supports_credentials=True, origins=['*'])  # Enable Cross-Origin headers

app.add_url_rule('/graphql', view_func=ReinaGraphQLView.as_view(
    'graphql',
    schema=schema.graphql_schema,
    middleware=[ExceptionMiddleware()],
    graphiql=True,
))

app.config.from_object('common.settings')
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'locale'

babel = Babel(default_locale='fi')
babel.init_app(app)

sess = Session()
sess.init_app(app)


if __name__ == '__main__':
    app.run()
