#!/usr/bin/env python
# encoding: utf-8
"""
::

   Copyright 2010 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

"""
Module which parses an icegrid XML file for configuration settings.

see ticket:800
see ticket:2213 - Replacing Java Preferences API
"""

import os
import path
import time
import logging
import exceptions
import portalocker

import xml.dom.minidom

try:
    from xml.etree.ElementTree import XML, Element, SubElement, Comment, ElementTree, tostring
except ImportError:
    from elementtree.ElementTree import XML, Element, SubElement, Comment, ElementTree, tostring


class ConfigXml(object):
    """

    """
    KEY = "omero.config.version"
    VERSION = "4.2.0"
    INTERNAL = "__ACTIVE__"
    DEFAULT = "omero.config.profile"
    IGNORE = (KEY, DEFAULT)

    def __init__(self, filename, env_config = None, exclusive = True):
        self.logger = logging.getLogger(self.__class__.__name__)    #: Logs to the class name
        self.XML = None                                             #: Parsed XML Element
        self.env_config = env_config                                #: Environment override
        self.filename = filename                                    #: Path to the file to be read and written
        self.source = open(filename, "a+")                          #: Open file handle
        self.exclusive = exclusive                                  #: Whether or not an exclusive lock should be acquired
        if exclusive:
            try:
                portalocker.lock(self.source, portalocker.LOCK_NB|portalocker.LOCK_EX)
            except portalocker.LockException, le:
                self.close()
                raise

        self.source.seek(0)
        text = self.source.read()

        if text:
            self.XML = XML(text)
            try:
                self.version_check()
            except:
                self.close()
                raise

        # Nothing defined, so create a new tree
        if not self.XML:
            default = self.default()
            self.XML = Element("icegrid")
            properties = SubElement(self.XML, "properties", id=self.INTERNAL)
            _ = SubElement(properties, "property", name=self.DEFAULT, value=default)
            _ = SubElement(properties, "property", name=self.KEY, value=self.VERSION)
            properties = SubElement(self.XML, "properties", id=default)
            _ = SubElement(properties, "property", name=self.KEY, value=self.VERSION)

    def version(self, id = None):
        if id is None:
            id = self.default()
        properties = self.properties(id)
        for x in properties.getchildren():
            if x.get("name") == self.KEY:
                return x.get("value")

    def version_check(self):
        for k, v in self.properties(None, True):
            version = self.version(k)
            if version != self.VERSION:
                self.version_fix(v, version)

    def version_fix(self, props, version):
        """
        Currently we are assuming that all blocks without a 4.2.0 version
        are bogus. The configuration script when it generates an initial
        config.xml will use prefs.class to parse the existing values and
        immediately do the upgrade.
        """
        raise exceptions.Exception("Version mismatch: %s has %s" % (props.get("id"), version))

    def internal(self):
        return self.properties(self.INTERNAL)

    def properties(self, id = None, filter_internal = False):

        if not self.XML:
            return None

        props = self.XML.findall("./properties")
        if id is None:
            rv = list()
            for x in props:
                id = x.attrib["id"]
                if filter_internal:
                    if id == self.INTERNAL:
                        continue
                rv.append((id, x))
            return rv
        for p in props:
            if "id" in p.attrib and p.attrib["id"] == id:
                return p
    def remove(self, id = None):
        if id is None:
            id = self.default()
        properties = self.properties(id)
        self.XML.remove(properties)

    def default(self, value = None):
        if value:
            self.env_config = value
        if self.env_config:
            return self.env_config
        elif "OMERO_CONFIG" in os.environ:
            return os.environ["OMERO_CONFIG"]
        else:
            props = self.props_to_dict(self.internal())
            return props.get(self.DEFAULT, "default")

    def dump(self):
        prop_list = self.properties()
        for id, p in prop_list:
            props = self.props_to_dict(p)
            print "# ===> %s <===" % id
            print self.dict_to_text(props)

    def close(self):
        try:
            # If we didn't get an XML instance,
            # then something has gone wrong and
            # we should exit.
            if self.XML:
                # Create a new icegrid block
                #
                #
                icegrid = Element("icegrid")
                comment = Comment("\n".join(["\n",
                "\tThis file was generated at %s by the OmeroConfig system.",
                "\tDo not edit directly but see bin/omero config for details.",
                "\tThis file may be included into your IceGrid application.",
                "\n"]) % time.ctime())
                icegrid.append(comment)
                # First step is to add a new self.INTERNAL block to it
                # which has self.DEFAULT set to the current default,
                # and then copies all the values from that profile.
                default = self.default()
                internal = SubElement(icegrid, "properties", id=self.INTERNAL)
                SubElement(internal, "property", name=self.DEFAULT, value=default)
                SubElement(internal, "property", name=self.KEY, value=self.VERSION)
                to_copy = self.properties(default)
                if to_copy is not None:
                    for x in to_copy.getchildren():
                        if x.get("name") != self.DEFAULT and x.get("name") != self.KEY:
                            SubElement(internal, "property", x.attrib)
                else:
                    # Doesn't exist, create it
                    properties = SubElement(icegrid, "properties", id=default)
                    SubElement(properties, "property", name=self.KEY, value=self.VERSION)
                # Now we simply reproduce all the other blocks
                prop_list = self.properties(None, True)
                for k, p in prop_list:
                    self.clear_text(p)
                    icegrid.append(p)
                self.source.seek(0)
                self.source.truncate()
                self.source.write(self.element_to_xml(icegrid))
        finally:
            self.source.close()

    def props_to_dict(self, c):

        if c is None:
            return {}

        rv = dict()
        props = c.findall("./property")
        for p in props:
            if "name" in p.attrib:
                rv[p.attrib["name"]] = p.attrib.get("value", "")
        return rv

    def dict_to_text(self, parsed = None):

        if parsed is None:
            return

        rv = ""
        for k, v in parsed.items():
            rv += "%s=%s" % (k, v)
        return rv

    def element_to_xml(self, elem):
        string = tostring(elem, 'utf-8')
        return xml.dom.minidom.parseString(string).toprettyxml("  ", "\n", None)

    def clear_text(self, p):
        """
        To prevent the accumulation of text outside of elements (including whitespace)
        we walk the given element and remove tail from it and it's children.
        """
        p.tail = ""
        p.text = ""
        for p2 in p.getchildren():
            self.clear_text(p2)

    #
    # Map interface on the default properties element
    #
    def as_map(self):
        return self.props_to_dict(self.properties(self.default()))

    def keys(self):
        return self.as_map().keys()

    def __getitem__(self, key):
        return self.props_to_dict(self.properties(self.default()))[key]

    def __setitem__(self, key, value):
        default = self.default()
        props = self.properties(default)

        if props == None:
            props = SubElement(self.XML, "properties", {"id":default})

        for x in props.findall("./property"):
            if x.attrib["name"] == key:
                x.attrib["value"] = value
                return
        SubElement(props, "property", {"name":key, "value":value})

    def __delitem__(self, key):
        default = self.default()
        props = self.properties(default)
        to_remove = []
        for p in props.getchildren():
            if p.get("name") == key:
                to_remove.append(p)
        for x in to_remove:
            props.remove(x)

