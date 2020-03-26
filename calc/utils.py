import importlib
import hashlib
import os
import json
from functools import wraps

from variables import get_variable
from utils.quilt import load_datasets
from utils.perf import PerfCounter

from common import cache


_dataset_cache = {}


def ensure_imported(func):
    if isinstance(func, str):
        paths = func.split('.')
        func_name = paths.pop()
        paths.insert(0, 'calc')
        mod = importlib.import_module('.'.join(paths))
        return getattr(mod, func_name)
    return func


def _get_func_hash_data(func, seen_funcs):
    if seen_funcs is None:
        seen_funcs = set([func])

    variables = func.variables or {}
    all_variables = set(variables.values())

    children = func.calcfuncs or []
    children = [ensure_imported(x) for x in children]
    all_funcs = set(children)

    for child in children:
        if child in seen_funcs:
            continue
        seen_funcs.add(child)
        hash_data = _get_func_hash_data(child, seen_funcs)
        all_variables.update(hash_data['variables'])
        all_funcs.update(hash_data['funcs'])

    all_funcs.add(func)

    return dict(variables=all_variables, funcs=all_funcs)


def _hash_funcs(funcs):
    m = hashlib.md5()
    for f in funcs:
        m.update(f.__code__.co_code)
    return m.hexdigest()


def _calculate_cache_key(func, hash_data):
    funcs = hash_data['funcs']
    variables = hash_data['variables']
    var_data = json.dumps({x: get_variable(x) for x in variables}, sort_keys=True)

    func_hash = _hash_funcs(funcs)
    func_name = '.'.join((func.__module__, func.__name__))
    return '%s:%s:%s' % (func_name, hashlib.md5(var_data.encode()).hexdigest(), func_hash)


def calcfunc(variables=None, datasets=None, funcs=None):
    if datasets is not None:
        assert isinstance(datasets, (list, tuple, dict))
        if not isinstance(datasets, dict):
            datasets = {x: x for x in datasets}

    if variables is not None:
        assert isinstance(variables, (list, tuple, dict))
        if not isinstance(variables, dict):
            variables = {x: x for x in variables}

        for var_name in variables.values():
            # Test that the variables indeed exist.
            get_variable(var_name)

    if funcs is not None:
        assert isinstance(funcs, (list, tuple))
        for func in funcs:
            assert callable(func) or isinstance(func, str)

    def wrapper_factory(func):
        func.variables = variables
        func.datasets = datasets
        func.calcfuncs = funcs

        @wraps(func)
        def wrap_calc_func(*args, **kwargs):
            should_profile = os.environ.get('PROFILE_CALC', '').lower() in ('1', 'true', 'yes')

            only_if_in_cache = kwargs.pop('only_if_in_cache', False)

            if should_profile:
                pc = PerfCounter('%s.%s' % (func.__module__, func.__name__))
                pc.display('enter')

            hash_data = _get_func_hash_data(func, None)
            cache_key = _calculate_cache_key(func, hash_data)

            assert 'variables' not in kwargs
            assert 'datasets' not in kwargs

            unknown_kwargs = set(kwargs.keys()) - set(['step_callback'])
            if not args and not unknown_kwargs:
                should_cache_func = True
            else:
                should_cache_func = False

            if should_cache_func:
                ret = cache.get(cache_key)
                if ret is not None:  # calcfuncs must not return None
                    if should_profile:
                        pc.display('cache hit')
                    return ret
                if only_if_in_cache:
                    return None

            if variables is not None:
                kwargs['variables'] = {x: get_variable(y) for x, y in variables.items()}

            if datasets is not None:
                datasets_to_load = set(list(datasets.values())) - set(_dataset_cache.keys())
                if datasets_to_load:
                    loaded_datasets = []
                    for dataset_name in datasets_to_load:
                        if should_profile:
                            ds_pc = PerfCounter('dataset %s' % dataset_name)
                        df = load_datasets(dataset_name)
                        if should_profile:
                            ds_pc.display('loaded')
                            del ds_pc
                        loaded_datasets.append(df)

                    for dataset_name, dataset in zip(datasets_to_load, loaded_datasets):
                        _dataset_cache[dataset_name] = dataset

                kwargs['datasets'] = {ds_name: _dataset_cache[ds_url] for ds_name, ds_url in datasets.items()}

            ret = func(*args, **kwargs)

            if should_profile:
                pc.display('func ret')
            if should_cache_func:
                assert ret is not None
                cache.set(cache_key, ret, timeout=3600)

            return ret

        return wrap_calc_func

    return wrapper_factory
