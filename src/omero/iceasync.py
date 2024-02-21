import asyncio
from functools import partial, update_wrapper
import logging


logger = logging.getLogger(__name__)


def _firstline_truncate(s):
    lines = "{}\n".format(s).splitlines()
    if len(lines[0]) > 80 or len(lines) > 1:
        s = lines[0][:79] + "…"
    return s


async def ice_async(loop, func, *args, **kwargs):
    """
    Wrap an asynchronous Ice service method so it can be used with asyncio

    loop: The event loop
    func: The Ice service method
    *args: Positional arguments for the Ice service method
    *kwargs: Keyword arguments for the Ice service method
    """
    # https://docs.python.org/3.6/library/asyncio-task.html#example-future-with-run-until-complete

    # Ice runs in a different thread from asyncio so must use
    # call_soon_threadsafe
    # https://docs.python.org/3.6/library/asyncio-dev.html#concurrency-and-multithreading

    future = loop.create_future()

    def exception_cb(ex):
        logger.warning("exception_cb: %s", _firstline_truncate(ex))
        loop.call_soon_threadsafe(future.set_exception, ex)

    def response_cb(result=None, *outparams):
        logger.debug("response_cb: %s", _firstline_truncate(result))
        loop.call_soon_threadsafe(future.set_result, result)

    a = func(*args, **kwargs, _response=response_cb, _ex=exception_cb)
    logger.debug(
        "_exec_ice_async(%s) sent:%s completed:%s",
        func.__name__,
        a.isSent(),
        a.isCompleted(),
    )

    result = await future
    return result


class AsyncService:
    def __init__(self, svc, loop=None):
        """
        Convert an OMERO Ice service to an async service

        svc: The OMERO Ice service
        loop: The async event loop (optional)
        """

        # This would be easier in Python 3.7 since Future.get_loop() returns
        # the loop the Future is bound to so there's no need to pass it
        # https://docs.python.org/3/library/asyncio-future.html#asyncio.Future.get_loop
        if not loop:
            loop = asyncio.get_event_loop()
        methods = {
            m for m in dir(svc)
            if callable(getattr(svc, m)) and not m.startswith("_")
        }

        # Ice methods come in sync (`f`) and async (`begin_f`…`end_f`) versions
        # https://doc.zeroc.com/ice/3.6/language-mappings/python-mapping/client-side-slice-to-python-mapping/asynchronous-method-invocation-ami-in-python
        # Replace each set of functions with a single async function `f`.
        # Uses `update_wrapper` to copy the original signature for `f` to the
        # wrapped function.
        async_methods = {m for m in methods if m.startswith("begin_")}
        for async_m in async_methods:
            sync_m = async_m[6:]
            methods.remove(sync_m)
            methods.remove("begin_" + sync_m)
            methods.remove("end_" + sync_m)
            setattr(
                self,
                sync_m,
                update_wrapper(
                    partial(ice_async, loop, getattr(svc, async_m)),
                    getattr(svc, sync_m),
                ),
            )
        for sync_m in methods:
            setattr(
                self,
                sync_m,
                update_wrapper(partial(
                    getattr(svc, sync_m)), getattr(svc, sync_m)),
            )


async def _getServiceWrapper(getsvc_m, loop):
    svc = await getsvc_m()
    return AsyncService(svc, loop)


class AsyncSession(AsyncService):
    def __init__(self, session, loop=None):
        """
        Wrap a session from client.getSession() so all services are async

        session: The OMERO session
        loop: The async event loop (optional)
        """

        # This will wrap methods including getXxxService(), but we need to also
        # wrap the results of those services
        super().__init__(session, loop)
        getsvc_methods = {
            m
            for m in dir(self)
            if callable(getattr(self, m))
            and m.startswith("get")
            and m.endswith("Service")
        }

        for getsvc_m in getsvc_methods:
            setattr(
                self,
                getsvc_m,
                update_wrapper(
                    partial(_getServiceWrapper, getattr(self, getsvc_m), loop),
                    getattr(session, getsvc_m),
                ),
            )
