set -e
set -u
set -x
IMAGE=${IMAGE:-${USER}-py-test}
PIP_CACHE_DIR=${PIP_CACHE_DIR:-/tmp/pip-cache}
mkdir -m 777 -p ${PIP_CACHE_DIR}
chmod a+t ${PIP_CACHE_DIR}
docker build -t ${IMAGE} .
docker run -ti --rm -v ${PIP_CACHE_DIR}:/tmp/pip-cache ${IMAGE} "$@"
