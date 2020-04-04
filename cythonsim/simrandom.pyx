# cython: language_level=3

from numpy.random import PCG64
import numpy as np

from cpython.pycapsule cimport PyCapsule_IsValid, PyCapsule_GetPointer
from numpy.random cimport bitgen_t
from numpy.random.c_distributions cimport random_lognormal, random_gamma


cdef class RandomPool:
    def __init__(self, seed):
        np.random.seed(seed)
        self.gen = np.random.PCG64(seed)
        capsule = self.gen.capsule
        # Optional check that the capsule if from a BitGenerator
        if not PyCapsule_IsValid(capsule, 'BitGenerator'):
            raise ValueError("Invalid pointer to anon_func_state")
        # Cast the pointer
        self.rng = <bitgen_t *> PyCapsule_GetPointer(capsule, 'BitGenerator')

    cdef double get(self) nogil:
        cdef bitgen_t *rng = self.rng
        return rng.next_double(rng.state)

    cdef unsigned int getint(self) nogil:
        cdef bitgen_t *rng = self.rng
        return rng.next_uint32(rng.state)

    cdef bint chance(self, double p) nogil:
        if p == 1.0:
            return True
        elif p == 0:
            return False

        cdef double val = self.get()
        return val < p

    cdef double lognormal(self, double mean, double sigma) nogil:
        cdef bitgen_t *rng = self.rng
        cdef double ret = random_lognormal(rng, mean, sigma)
        return ret

    cdef double gamma(self, double mean, double sigma) nogil:
        cdef bitgen_t *rng = self.rng
        cdef double ret = random_gamma(rng, mean, sigma)
        return ret
