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
- future
- numpy
- Pillow

Installation
------------

We recommend installing omero-py in a Python virtual environment.
You can create one using either ``venv`` or ``conda`` (preferred).
If you opt for `Conda`_, you will need
to install it first, see `miniconda`_ for more details.

To install ``omero-py`` using conda (preferred)::

    conda create -n myenv -c ome python=3.6 zeroc-ice36-python omero-py
    conda activate myenv

Alternatively install ``omero-py`` using venv::

    python3.6 -m venv myenv
    . myenv/bin/activate
    pip install omero-py

You may need to replace ``python3.6`` with ``python`` or ``python3`` depending on your Python distribution.

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

See: `OMERO`_ documentation for more details.

Usage
-----

- For OMERO python language bindings, see `OMERO.py`_.
- For Command Line usage, see `OMERO.CLI`_.

Contributing
------------

See: `OMERO`_ documentation

Developer installation
----------------------

OMERO.py currently depends on an externally built artifact which is automatically bundled in the PyPI package.

For a development installation we recommend creating a virtualenv with the following setup (example assumes ``python3.6`` but you can create and activate the virtualenv using any compatible Python):

To install using venv::

    python3.6 -mvenv myenv
    . myenv/bin/activate
    git clone https://github.com/ome/omero-py
    cd omero-py
    python setup.py devtarget
    pip install -e .

To install ``omero-py`` using conda (preferred)::

    conda create -n myenv -c ome python=3.6 zeroc-ice36-python
    conda activate myenv
    git clone https://github.com/ome/omero-py
    cd omero-py
    python setup.py devtarget
    pip install -e .


This will install omero-py into your virtualenv as an editable package, so any edits to ``src`` files should be reflected in your installation.
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
a Pull Request needs to be opened against
`conda-omero-py <https://github.com/ome/conda-omero-py>`_ to update the 
official `OMERO.py Conda package <https://anaconda.org/ome/omero-py>`_.

License
-------

OMERO.py is released under the GPL v2.

Copyright
---------

2009-2021, The Open Microscopy Environment, Glencoe Software, Inc.

.. _ZeroC IcePy 3.6: https://zeroc.com/downloads/ice/3.6
.. _OMERO.py: https://docs.openmicroscopy.org/omero/5.6/developers/Python.html
.. _OMERO.CLI: https://docs.openmicroscopy.org/omero/5.6/users/cli/index.html
.. _OMERO: https://docs.openmicroscopy.org/omero/5.6/index.html
.. _Running and writing tests: https://docs.openmicroscopy.org/latest/omero/developers/testing.html
.. _Conda: https://docs.conda.io/en/latest/
.. _miniconda: https://docs.conda.io/en/latest/miniconda.html
