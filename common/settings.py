import os
from urllib.parse import urlparse
from dotenv import load_dotenv
from common.exceptions import ImproperlyConfigured


load_dotenv()

# Points to repo root
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

CACHE_KEY_PREFIX = 'ghgdash-cache'
CACHE_TYPE = 'simple'
CACHE_REDIS_URL = None

SESSION_TYPE = 'filesystem'
SESSION_FILE_DIR = os.path.join(BASE_DIR, 'flask_session')
SESSION_KEY_PREFIX = 'ghgdash-session'

REDIS_URL = os.getenv('REDIS_URL', None)

URL_PREFIX = os.getenv('URL_PREFIX', None)
BASE_URL = os.getenv('BASE_URL', None)

TRAFFIC_WARNING = os.getenv('TRAFFIC_WARNING', False)
RESTRICT_TO_PRESET_SCENARIOS = os.getenv('RESTRICT_TO_PRESET_SCENARIOS', False)


def get_cache_config():
    global CACHE_TYPE, CACHE_REDIS_URL

    url = os.getenv('CACHE_REDIS_URL', None)
    if not url and REDIS_URL:
        url = REDIS_URL

    if url:
        CACHE_REDIS_URL = url
        CACHE_TYPE = 'redis'


get_cache_config()


def get_session_config():
    global SESSION_TYPE, SESSION_REDIS

    url = os.getenv('SESSION_REDIS_URL', None)
    if not url and REDIS_URL:
        url = REDIS_URL

    if not url:
        return

    from redis import Redis

    client = Redis.from_url(url)
    SESSION_REDIS = client
    SESSION_TYPE = 'redis'


get_session_config()
