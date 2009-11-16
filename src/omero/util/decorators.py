#!/usr/bin/env python
#
# OMERO Decorators
# Copyright 2009 Glencoe Software, Inc.  All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
#

import time
import logging
import threading
import traceback
import exceptions

import omero

from omero_ext.functional import wraps

perf_log = logging.getLogger("omero.perf")

def perf(func):
    """ Decorator for (optionally) printing performance statistics """
    def handler(*args, **kwargs):

        # Early Exit. Can't do this in up a level
        # because logging hasn't been configured yet.
        lvl = perf_log.getEffectiveLevel()
        if lvl > logging.DEBUG:
            return func(*args, **kwargs)

        try:
            self = args[0]
            mod = self.__class__.__module__
            cls = self.__class__.__name__
            tag = "%s.%s.%s" % (mod, cls, func.func_name)
        except:
            tag = func.func_name
        start = time.time()
        try:
            rv = func(*args, **kwargs)
            return rv
        finally:
            stop = time.time()
            diff = stop - start
            startMillis = int(start * 1000)
            timeMillis = int(diff * 1000)
            perf_log.debug("start[%d] time[%d] tag[%s]", startMillis, timeMillis, tag)
    handler = wraps(func)(handler)
    return handler


def remoted(func):
    """ Decorator for catching any uncaught exception and converting it to an InternalException """
    log = logging.getLogger("omero.remote")
    def exc_handler(*args, **kwargs):
        try:
            self = args[0]
            log.info(" Meth: %s.%s", self.__class__.__name__, func.func_name)
            start = time.time()
            rv = func(*args, **kwargs)
            stop = time.time()
            log.info(" Rslt: %20.20s in %ss", rv, (stop-start))
            return rv
        except exceptions.Exception, e:
            stop = time.time()
            log.info(" Excp: %20.20s in %ss.", e, (stop-start))
            if isinstance(e, omero.ServerError):
                raise
            else:
                log.warn("%s raised a non-ServerError (%s): %s", func, type(e), e)
                msg = traceback.format_exc()
                raise omero.InternalException(msg, None, "Internal exception")
    exc_handler = wraps(func)(exc_handler)
    return exc_handler

def locked(func):
    """ Decorator for using the self._lock argument of the calling instance """
    def with_lock(*args, **kwargs):
        self = args[0]
        self._lock.acquire()
        try:
            return func(*args, **kwargs)
        finally:
            self._lock.release()
    with_lock = wraps(func)(with_lock)
    return with_lock


