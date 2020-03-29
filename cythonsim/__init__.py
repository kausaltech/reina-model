import os
import pyximport
import numpy as np

"""
inc_path = np.get_include()
# not so nice. We need the random/lib library from numpy
lib_path = os.path.join(np.get_include(), '..', '..', 'random', 'lib')

pyximport.install(setup_args={
    'include_dirs': [inc_path],
    'library_dirs': [lib_path],
    #'libraries': [('npyrandom', dict(library_dirs=[lib_path]))]
})
"""

pyximport.install()

from . import simrandom
from . import main as model
