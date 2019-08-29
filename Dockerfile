FROM centos:centos7
RUN yum install -y python-setuptools python-virtualenv git python-yaml
RUN echo git clean -dfx
RUN virtualenv /v && /v/bin/pip install twine
RUN /v/bin/pip install --upgrade pip setuptools
RUN /v/bin/pip install https://github.com/ome/zeroc-ice-py-centos7/releases/download/0.1.0/zeroc_ice-3.6.4-cp27-cp27mu-linux_x86_64.whl
COPY . /src
WORKDIR /src
RUN python setup.py sdist
RUN /v/bin/pip install dist/omero-py*gz
RUN /v/bin/python -c "import omero_version; print omero_version.omero_version"
# More to be added here
RUN python setup.py test -t test/unit/clitest/
RUN python setup.py test -t test/unit/fstest/
RUN python setup.py test -t test/unit/gatewaytest/
RUN python setup.py test -t test/unit/scriptstest/
