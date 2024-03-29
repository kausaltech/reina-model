import logging
import multiprocessing
import time
import uuid

from calc import ExecutionInterrupted
from calc.simulation import simulate_individuals
from calc.utils import generate_cache_key
from common import cache

logger = logging.getLogger(__name__)


class SimulationProcess(multiprocessing.Process):
    def __init__(self, variables):
        self.variables = variables
        super().__init__(daemon=True)
        self.uuid = str(uuid.uuid4())
        self.cache_key = generate_cache_key(simulate_individuals, var_store=self.variables)
        self.cache_expiration = 30

    def start(self):
        logger.info('%s: start process' % self.uuid)
        finished = cache.get('%s-finished' % self.cache_key)
        if finished is not None:
            logger.info('%s: already running in another process (%s)' % (self.uuid, self.cache_key))
            return
        # Race condition here, but it is of little consequence
        # FIXME: Probably should use SETNX instead
        cache.set('%s-error' % self.cache_key, None, self.cache_expiration)
        cache.set('%s-finished' % self.cache_key, False, timeout=self.cache_expiration)
        super().start()

    def run(self):
        self.last_results = None
        logger.info('%s: run process (cache key %s)' % (self.uuid, self.cache_key))

        def step_callback(total, age_groups=None, by_variant=None, force=False):
            now = time.time()
            res = dict(total=total, age_groups=age_groups, by_variant=by_variant)
            if force or self.last_results is None or now - self.last_results > 0.5:
                logger.debug('%s: set results to %s' % (self.uuid, self.cache_key))
                cache.set('%s-results' % self.cache_key, res, timeout=self.cache_expiration)
                self.last_results = now

            return True

        try:
            df, adf = simulate_individuals(step_callback=step_callback, variable_store=self.variables)
        except ExecutionInterrupted:
            logger.error('%s: process cancelled' % self.uuid)
        except Exception as e:
            cache.set('%s-finished' % self.cache_key, True, self.cache_expiration)
            cache.set('%s-error' % self.cache_key, str(e), self.cache_expiration)
            raise
        else:
            logger.info('%s: computation finished' % self.uuid)
            step_callback(df, age_groups=adf, force=True)

        cache.set('%s-finished' % self.cache_key, True, self.cache_expiration)
        logger.info('%s: process finished' % self.uuid)
