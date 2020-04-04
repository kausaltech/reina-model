# cython: language_level=3
from numpy.random cimport bitgen_t


cdef class RandomPool:
    cdef object gen
    cdef bitgen_t *rng
    cdef double get(self) nogil
    cdef bint chance(self, double p) nogil
    cdef double lognormal(self, double mean, double sigma) nogil
    cdef double gamma(self, double mean, double sigma) nogil

    cdef unsigned int getint(self) nogil
