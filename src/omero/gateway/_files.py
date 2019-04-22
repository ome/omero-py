import os

import omero
from ._core import BlitzObjectWrapper
from ._core import OmeroRestrictionWrapper


class _OriginalFileAsFileObj(object):
    """
    Based on
    https://docs.python.org/2/library/stdtypes.html#file-objects
    """
    def __init__(self, originalfile, buf=2621440):
        self.originalfile = originalfile
        self.bufsize = buf
        # Can't use BlitzGateway.createRawFileStore as it always returns the
        # same store https://trello.com/c/lC8hFFix/522
        self.rfs = originalfile._conn.c.sf.createRawFileStore()
        self.rfs.setFileId(originalfile.id, originalfile._conn.SERVICE_OPTS)
        self.pos = 0

    def seek(self, n, mode=0):
        if mode == os.SEEK_SET:
            self.pos = n
        elif mode == os.SEEK_CUR:
            self.pos += n
        elif mode == os.SEEK_END:
            self.pos = self.rfs.size() + n
        else:
            raise ValueError('Invalid mode: %s' % mode)

    def tell(self):
        return self.pos

    def read(self, n=-1):
        buf = ''
        if n < 0:
            endpos = self.rfs.size()
        else:
            endpos = min(self.pos + n, self.rfs.size())
        while self.pos < endpos:
            nread = min(self.bufsize, endpos - self.pos)
            buf += self.rfs.read(self.pos, nread)
            self.pos += nread
        return buf

    def close(self):
        self.rfs.close()

    def __iter__(self):
        while self.pos < self.rfs.size():
            yield self.read(self.bufsize)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()


class _OriginalFileWrapper (BlitzObjectWrapper, OmeroRestrictionWrapper):
    """
    omero_model_OriginalFileI class wrapper extends BlitzObjectWrapper.
    """

    OMERO_CLASS = 'OriginalFile'

    def getFileInChunks(self, buf=2621440):
        """
        Returns a generator yielding chunks of the file data.

        :return:    Data from file in chunks
        :rtype:     Generator
        """
        with self.asFileObj(buf) as f:
            for chunk in f:
                yield chunk

    def asFileObj(self, buf=2621440):
        """
        Return a read-only file-like object.
        Caller must call close() on the file object after use.
        This can be done automatically by using the object as a
        ContextManager.
        For example:

            with f.asFileObj() as fo:
                content = fo.read()

        :return:    File-like object wrapping the OriginalFile
        :rtype:     File-like object
        """
        return _OriginalFileAsFileObj(self, buf)


OriginalFileWrapper = _OriginalFileWrapper


class _FilesetWrapper (BlitzObjectWrapper):
    """
    omero_model_FilesetI class wrapper extends BlitzObjectWrapper
    """

    OMERO_CLASS = 'Fileset'

    @classmethod
    def _getQueryString(cls, opts=None):
        """
        Used for building queries in generic methods such as
        getObjects("Fileset").
        Returns a tuple of (query, clauses, params).

        :param opts:        Dictionary of optional parameters.
                            NB: No options supported for this class.
        :return:            Tuple of string, list, ParametersI
        """
        query = "select obj from Fileset obj "\
            "left outer join fetch obj.images as image "\
            "left outer join fetch obj.usedFiles as usedFile " \
            "join fetch usedFile.originalFile"
        return query, [], omero.sys.ParametersI()

    def copyImages(self):
        """ Returns a list of :class:`ImageWrapper` linked to this Fileset """
        from ._images import ImageWrapper  # TODO: recursive import!!!
        return [ImageWrapper(self._conn, i) for i in self._obj.copyImages()]

    def listFiles(self):
        """
        Returns a list of :class:`OriginalFileWrapper` linked to this Fileset
        via Fileset Entries
        """
        return [OriginalFileWrapper(self._conn, f.originalFile)
                for f in self._obj.copyUsedFiles()]

FilesetWrapper = _FilesetWrapper
