import copy
import os


def deepupdate(target, src):
    for k, v in src.items():
        if type(v) == list:
            if k not in target:
                target[k] = copy.deepcopy(v)
            else:
                target[k].extend(v)
        elif type(v) == dict:
            if k not in target:
                target[k] = copy.deepcopy(v)
            else:
                deepupdate(target[k], v)
        elif type(v) == set:
            if k not in target:
                target[k] = v.copy()
            else:
                target[k].update(v.copy())
        else:
            target[k] = copy.copy(v)


def get_root_path():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def add_root_path(filename: str) -> str:
    """
    Add the root path of the program to the filename given as parameter
    """
    filename = filename.lstrip("/")
    return os.path.join(get_root_path(), filename)
