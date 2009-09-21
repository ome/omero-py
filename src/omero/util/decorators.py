#!/usr/bin/env python
#
# OMERO Decorators
# Copyright 2009 Glencoe Software, Inc.  All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
#

import logging
import threading
import traceback
import exceptions

import omero

from omero_ext.functional import wraps


def remoted(func):
    """ Decorator for catching any uncaught exception and converting it to an InternalException """
    log = logging.getLogger("omero.remote")
    def exc_handler(*args, **kwargs):
        try:
            rv = func(*args, **kwargs)
            #log.info("%s(%s,%s)=>%s" % (func, args, kwargs, rv))
            return rv
        except exceptions.Exception, e:
            log.info("%s=>%s(%s)" % (func, type(e), e))
            if isinstance(e, omero.ServerError):
                raise e
            else:
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


