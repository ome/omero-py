OMERO.py
========

.. image:: https://github.com/ome/omero-py/workflows/Build/badge.svg
   :target: https://github.com/ome/omero-py/actions

.. image:: https://badge.fury.io/py/omero-py.svg
    :target: https://badge.fury.io/py/omero-py

Introduction
------------

OMERO.py provides Python bindings to the OMERO.blitz server
as well as a pluggable command-line interface.

Dependencies
------------

Direct dependencies of OMERO.py are:

- `ZeroC IcePy 3.6`_
- numpy
- Pillow >= 10.0.0

Installation
------------

We recommend installing omero-py in a Python virtual environment.
You can create one using for example ``venv``, ``conda`` or ``mamba``.

Before installing ``omero-py``, we recommend to install the `ZeroC IcePy 3.6`_ Python bindings.
Our commercial partner `Glencoe Software <https://www.glencoesoftware.com/blog/2023/12/08/ice-binaries-for-omero.html>`_ has produced several Python wheels to install the Ice-Python bindings depending on the desired Python version and the operating system. Please visit `OMERO.py`_ for a list of supported platforms and Python versions.


When the wheel is installed, activate the virtual environment and install ``omero-py`` from `PyPI <https://pypi.org/>`_::

  $ pip install -U omero-py

Setting of the environment variable ``OMERODIR`` is required
for some functionality.
``$OMERODIR/var/log/`` directory will contain log files.
``$OMERODIR/etc/grid/config.xml`` is used to store config.

If ``OMERODIR`` is set to an OMERO.server directory,
the ``import`` and ``admin`` commands will be enabled::

    # If you need import or admin commands:
    export OMERODIR=/path/to/OMERO.server/

    # otherwise, can choose any location.
    export OMERODIR=$(pwd)

Since version 5.13.0, the use of ``omero certificates`` is required to ensure that an OMERO server installation has, at minimum, a self-signed certificate.

See: `OMERO`_ documentation for more details and 
`OMERO server certificate management plugin <https://pypi.org/project/omero-certificates/>`_

Usage
-----

- For Command Line usage, see `OMERO.CLI`_.
- For API documentation, see https://omero-py.readthedocs.io/

Contributing
------------

See: `OMERO`_ documentation

Developer installation
----------------------

OMERO.py currently depends on an externally built artifact which is automatically bundled in the PyPI package.

For a development installation, we recommend to create a virtual environment with the Ice-Python binding matching your Python version and your operating system, see `OMERO.py`_.

Activate the virtual environment and clone this repository::

    $ git clone https://github.com/ome/omero-py
    $ cd omero-py
    $ python setup.py devtarget
    $ pip install -e .


This will install ``omero-py`` into your virtualenv as an editable package, so any edits to ``src`` files should be reflected in your installation.
Note that if you add or remove files you must rerun the last two steps.

Running tests
-------------

Unit tests are located under the `test` directory and can be run with pytest.

Integration tests
^^^^^^^^^^^^^^^^^

Integration tests are stored in the main repository (ome/openmicroscopy) and depend on the
OMERO integration testing framework. Reading about `Running and writing tests`_ in the `OMERO`_ documentation

Release process
---------------

This repository uses `bump2version <https://pypi.org/project/bump2version/>`_ to manage version numbers.
To tag a release run::

    $ bumpversion release

This will remove the ``.dev0`` suffix from the current version, commit, and tag the release.

To switch back to a development version run::

    $ bumpversion --no-tag [major|minor|patch]

specifying ``major``, ``minor`` or ``patch`` depending on whether the development branch will be a `major, minor or patch release <https://semver.org/>`_. This will also add the ``.dev0`` suffix.

Remember to ``git push`` all commits and tags.s essential.

The CI pipeline will automatically deploy the tag onto PyPI. Once released,
a Pull Request will be automatically  opened against
`conda-omero-py <https://github.com/ome/conda-omero-py>`_ to update the 
official `OMERO.py Conda package <https://anaconda.org/ome/omero-py>`_.

Documentation
-------------

The API documentation is generated using Sphinx.
To generate it:

- Install `Sphinx <https://www.sphinx-doc.org/en/master/>`_.
- Set the environment variable ``NO_TEMP_MANAGER`` to ``true``.
- In the ``docs`` directory, run ``make clean html``.

License
-------

OMERO.py is released under the GPL v2.

Copyright
---------

2009-2024, The Open Microscopy Environment, Glencoe Software, Inc.

.. _ZeroC IcePy 3.6: https://zeroc.com/downloads/ice/3.6
.. _OMERO.py: https://omero.readthedocs.io/en/stable/developers/Python.html
.. _OMERO.CLI: https://omero.readthedocs.io/en/stable/users/cli/index.html
.. _OMERO: https://omero.readthedocs.io/en/stable/index.html
.. _Running and writing tests: https://omero.readthedocs.io/en/stable/developers/testing.html
