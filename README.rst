OMERO.py
========

.. image:: https://travis-ci.org/ome/omero-py.png
   :target: http://travis-ci.org/ome/omero-py

.. image:: https://badge.fury.io/py/omero-py.svg
    :target: https://badge.fury.io/py/omero-py

Introduction
------------

OMERO.py provides Python bindings to the OMERO.blitz server
as well as a pluggable command-line interface.

Dependencies
------------

Direct dependencies of OMERO.py are:

- `ZeroC IcePy`_

Installation
------------

See: `OMERO`_ documentation

Usage
-----

See: `OMERO`_ documentation

Contributing
------------

See: `OMERO`_ documentation

Developer installation
----------------------

OMERO.py currently depends on an externally built artifact which is automatically bundled in the PyPi package.

For a development installation we recommend creating a virtualenv with the following setup (example assumes ``python3.6`` but you can create and activate the virtualenv using any compatible Python):

::

    python3.6 -mvenv venv
    . venv/bin/activate
    pip install zeroc-ice==3.6.5
    git clone https://github.com/ome/omero-py
    cd omero-py
    python setup.py devtarget
    pip install -e .

This will install OMERO.py into your virtualenv as an editable package, so any edits to ``src`` files should be reflected in your installation.
Note that if you add or remove files you must rerun the last two steps.

Running tests
-------------

Unit tests are located under the `test` directory and can be run with pytest.

Integration tests
^^^^^^^^^^^^^^^^^

Integration tests are stored in the main repository (ome/openmicroscopy) and depend on the
OMERO integration testing framework. Reading about `Running and writing tests`_ in the `OMERO`_ documentation
is essential.

License
-------

OMERO.py is released under the GPL v2.

Copyright
---------

2009-2019, The Open Microscopy Environment, Glencoe Software, Inc.

.. _ZeroC IcePy: https://zeroc.com/
.. _OMERO: https://www.openmicroscopy.org/omero
.. _Running and writing tests: https://docs.openmicroscopy.org/latest/omero/developers/testing.html
