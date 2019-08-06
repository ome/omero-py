FROM centos:centos7
RUN yum install -y python-setuptools python-virtualenv git
RUN echo git clean -dfx
RUN virtualenv v && v/bin/pip install twine
COPY . /src
WORKDIR /src
RUN python setup.py sdist
