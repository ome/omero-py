#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# OMERO Text handling utilities
#
# Copyright 2010-2015 Glencoe Software, Inc.  All Rights Reserved.
# Use is subject to license terms supplied in LICENSE.txt
#

#
# The following classes (ALIGN, Column, Table) were originally from
# http://code.activestate.com/recipes/577202-render-tables-for-text-interface/
#
from __future__ import unicode_literals
from __future__ import division
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import zip
from builtins import range
from past.utils import old_div
from builtins import object
import json
import os
import sys


class Style(object):

    NAME = "unknown"

    def headers(self, table):
        return self.SEPARATOR.join(table.get_row(None))

    def width(self, name, decoded_data):
        return max(len(x) for x in decoded_data + [name])

    def __str__(self):
        return self.NAME


class SQLStyle(Style):

    NAME = "sql"
    SEPARATOR = "|"

    def format(self, width, align):
        return ' %%%s%ds ' % (align, width)

    def line(self, table):
        return "+".join(["-" * (x.width + 2) for x in table.columns])

    def status(self, table):
        s = "(%s %s%%s)" % (
            table.length,
            (table.length == 1 and "row" or "rows"))
        if table.page_info is None:
            return s % ""
        return s % (", starting at %s of approx. %s" %
                    (table.page_info[0], table.page_info[2]))

    def get_rows(self, table):
        yield str(self.headers(table))
        yield str(self.line(table))
        for i in range(0, table.length):
            yield self.SEPARATOR.join(table.get_row(i))
        yield str(self.status(table))


class PlainStyle(Style):

    NAME = "plain"
    SEPARATOR = ","

    def format(self, width, align):
        return '%s'

    def _write_row(self, table, i):
        try:
            import csv
            import io
            if sys.version_info >= (3, 0, 0):
                output = io.StringIO()
                def _encode(s):
                    return s
                def _decode(s):
                    return s
            else:
                # Python 2.7 csv module does not support unicode!
                # https://docs.python.org/2.7/library/csv.html#module-csv
                # Need to treat as bytes and encode/decode
                output = io.BytesIO()
                def _encode(s):
                    return s.encode('utf-8')
                def _decode(s):
                    return s.decode('utf-8')
            writer = csv.writer(output, lineterminator='')
            writer.writerow([_encode(s) for s in table.get_row(i)])
            return _decode(output.getvalue())
        except Exception as e:
            return self.SEPARATOR.join(table.get_row(i))

    def get_rows(self, table):
        for i in range(0, table.length):
            yield self._write_row(table, i)


class CSVStyle(PlainStyle):

    NAME = "csv"

    def get_rows(self, table):
        yield self.headers(table)
        for row in PlainStyle.get_rows(self, table):
            yield row


class JSONStyle(Style):

    NAME = "json"

    def format(self, width, align):
        return '%s'

    def get_rows(self, table):
        headers = list(table.get_row(None))

        if table.length == 0:
            yield '[]'

        for i in range(0, table.length):
            prefix = '[' if i == 0 else ''
            suffix = ']' if i == table.length - 1 else ','
            d = dict(list(zip(headers, table.get_row(i))))
            yield prefix + json.dumps(d) + suffix


class StyleRegistry(dict):

    def __init__(self):
        dict.__init__(self)
        self["csv"] = CSVStyle()
        self["sql"] = SQLStyle()
        self["plain"] = PlainStyle()
        self["json"] = JSONStyle()


STYLE_REGISTRY = StyleRegistry()


def find_style(style, error_strategy=None):
    """
    Lookup method for well-known styles by name.
    None may be returned.
    """
    if isinstance(style, Style):
        return style
    else:
        if error_strategy == "pass-through":
            return STYLE_REGISTRY.get(style, style)
        elif error_strategy == "throw":
            return STYLE_REGISTRY[style]
        else:
            return STYLE_REGISTRY.get(style, None)


def list_styles():
    """
    List the styles that are known by find_style
    """
    return list(STYLE_REGISTRY.keys())


class TableBuilder(object):

    """
    OMERO-addition to make working with Tables easier
    """

    def __init__(self, *headers):
        self.style = SQLStyle()
        self.headers = list(headers)
        self.results = [[] for x in self.headers]
        self.page_info = None
        self.align = None

    def page(self, offset, limit, total):
        self.page_info = (offset, limit, total)

    def set_style(self, style):
        self.style = find_style(style)

    def set_align(self, align):
        """
        Set column alignments using alignments string, one char for each
        column. 'r' for right-aligned columns, the default, anything else,
        is left-aligned. If the argument list in too short it will be padded
        with the default.
        """
        self.align = list(align)
        if len(self.align) < len(self.headers):
            self.align.extend(['l'] * (len(self.headers) - len(self.align)))

    def col(self, name):
        """
        Add a new column and back fill spaces
        """
        self.headers.append(name)
        self.results.append(["" for x in range(len(self.results[0]))])

    def cols(self, names):
        """
        Similar to col() but only adds unknown columns
        """
        for name in names:
            if name not in self.headers:
                self.col(name)

    def get_col(self, name):
        """
        Return a column by header name.
        """
        if name not in self.headers:
            raise KeyError("%s not in %s" % (name, self.headers))
        idx = self.headers.index(name)
        return self.results[idx]

    def replace_col(self, name, col):
        """
        Replace a column by header name, it must be the same length.
        """
        if name not in self.headers:
            raise KeyError("%s not in %s" % (name, self.headers))
        idx = self.headers.index(name)
        if len(self.results[idx]) != len(col):
            raise ValueError("Size mismatch: %s != %s" %
                             (self.results[idx], len(col)))
        self.results[idx] = col

    def replace_header(self, name, new_name):
        """
        Replace a header name with a new name.
        """
        if name not in self.headers:
            raise KeyError("%s not in %s" % (name, self.headers))
        idx = self.headers.index(name)
        self.headers[idx] = new_name

    def row(self, *items, **by_name):

        if len(items) > len(self.headers):
            raise ValueError("Size mismatch: %s != %s" %
                             (len(items), len(self.headers)))

        # Fill in all values, even if missing
        for idx in range(len(self.results)):
            value = None
            if idx < len(items):
                value = items[idx]
            self.results[idx].append(value)

        for k, v in list(by_name.items()):
            if k not in self.headers:
                raise KeyError("%s not in %s" % (k, self.headers))
            idx = self.headers.index(k)
            self.results[idx][-1] = by_name[self.headers[idx]]
            # Now fill any empty values with "" for consistency with col()
            for idx in range(len(self.headers)):
                if self.results[idx][-1] is None:
                    self.results[idx][-1] = ""

    def sort(self, cols=[0], reverse=False):
        """
        Sort the results on a given column by transposing,
        sorting and then transposing.
        """
        for col in cols:
            if col+1 > len(self.headers):
                raise ValueError("Column mismatch: %s of %s" %
                                 (col, len(self.headers)))

        from operator import itemgetter
        tr = list(zip(*self.results))
        tr.sort(key=itemgetter(*cols), reverse=reverse)
        self.results = list(zip(*tr))

    def build(self):
        columns = []
        for i, x in enumerate(self.headers):
            align = ALIGN.LEFT
            if self.align and self.align[i] == 'r':
                align = ALIGN.RIGHT
            columns.append(
                Column(x, self.results[i], align=align, style=self.style))
        table = Table(*columns)
        if self.page_info:
            table.page(*self.page_info)
        table.set_style(self.style)
        return table

    def __str__(self):
        return str(self.build())


class ALIGN(object):
    LEFT, RIGHT = '-', ''


class Column(list):

    def __init__(self, name, data, align=ALIGN.LEFT, style=SQLStyle()):
        if sys.version_info >= (3, 0, 0):
            def tostring(x):
                if isinstance(x, bytes):
                    return x.decode("utf-8", "surrogateescape")
                else:
                    return str(x)
        else:
            def tostring(x):
                try:
                    return str(x)
                except UnicodeDecodeError:
                    # Unicode characters are present
                    return str(x.decode("utf-8", "ignore"))

        decoded = [tostring(d) for d in data]
        list.__init__(self, decoded)
        self.name = name
        self.width = style.width(name, decoded)
        self.format = style.format(self.width, align)


class Table(object):

    def __init__(self, *columns):
        self.style = SQLStyle()
        self.columns = columns
        self.length = max(len(x) for x in columns)
        self.page_info = None

    def page(self, offset, limit, total):
        self.page_info = (offset, limit, total)

    def set_style(self, style):
        self.style = find_style(style)

    def get_row(self, i=None):
        for x in self.columns:
            if i is None:
                yield x.format % x.name
            else:
                if sys.version_info >= (3, 0, 0):
                    if isinstance(x[i], bytes):
                        yield x.format % bytes.decode(
                            "utf-8", "surrogateescape")
                    else:
                        yield x.format % str(x[i])
                else:
                    try:
                        yield x.format % x[i].decode("ascii")
                    except UnicodeEncodeError:
                        yield x.format % x[i]
                    except UnicodeDecodeError:  # Unicode characters are present
                        yield (x.format % x[i].decode("utf-8")).encode("utf-8")
                    except AttributeError:  # Unicode characters are present
                        yield x.format % x[i]
                    else:
                        yield x.format % x[i]

    def get_rows(self):
        for row in self.style.get_rows(self):
            yield row

    def __str__(self):
        if sys.version_info >= (3, 0, 0):
            return '\n'.join(self.get_rows())
        else:
            return ('\n'.join(self.get_rows())).encode("utf-8")


def filesizeformat(bytes):
    """
    Formats the value like a 'human-readable' file size (i.e. 13 KB, 4.1 MB,
    102 bytes, etc).

    Copied largely from django.template.defaultfilters
    """
    try:
        bytes = float(bytes)
    except (TypeError, ValueError, UnicodeDecodeError):
        return "0 bytes"

    filesize_number_format = lambda value: round(value, 1)

    KB = 1 << 10
    MB = 1 << 20
    GB = 1 << 30
    TB = 1 << 40
    PB = 1 << 50

    if bytes < KB:
        value = "%(size)d B" % {'size': bytes}
    elif bytes < MB:
        value = "%s KB" % filesize_number_format(old_div(bytes, KB))
    elif bytes < GB:
        value = "%s MB" % filesize_number_format(old_div(bytes, MB))
    elif bytes < TB:
        value = "%s GB" % filesize_number_format(old_div(bytes, GB))
    elif bytes < PB:
        value = "%s TB" % filesize_number_format(old_div(bytes, TB))
    else:
        value = "%s PB" % filesize_number_format(old_div(bytes, PB))

    return value
