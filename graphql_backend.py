from flask import Flask
from flask_babel import Babel
from flask_cors import CORS
from flask_session import Session
from graphql_schema import schema
from graphql_server.flask import GraphQLView

app = Flask(__name__)

CORS(app, supports_credentials=True, origins=['*'])  # Enable Cross-Origin headers

app.add_url_rule('/graphql', view_func=GraphQLView.as_view(
    'graphql',
    schema=schema.graphql_schema,
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
