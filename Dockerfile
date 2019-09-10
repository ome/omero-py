FROM centos:centos7
RUN localedef -i en_US -f UTF-8 en_US.UTF-8
ENV LANG='en_US.UTF-8' LANGUAGE='en_US:en' LC_ALL='en_US.UTF-8'
RUN yum install -y python-setuptools python-virtualenv git python-yaml
RUN virtualenv /v && /v/bin/pip install twine tox pytest pytest-xdist restructuredtext-lint
RUN /v/bin/pip install --upgrade pip setuptools future
RUN /v/bin/pip install https://github.com/ome/zeroc-ice-py-centos7/releases/download/0.1.0/zeroc_ice-3.6.4-cp27-cp27mu-linux_x86_64.whl

# Optimize for fixing tests
COPY *.py /src/
COPY README.rst /src
COPY src /src/src
WORKDIR /src

RUN /v/bin/rst-lint README.rst
RUN /v/bin/python setup.py sdist
RUN /v/bin/pip install dist/omero-py*gz
RUN /v/bin/python -c "import omero_version; print omero_version.omero_version"

# Copy test-related files and run
COPY ice.config /src/
COPY *.ini /src/
COPY test /src/test
RUN /v/bin/tox
