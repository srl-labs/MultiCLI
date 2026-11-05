#!/bin/bash

_term() {
    echo "Caught signal SIGTERM !!"
    kill -TERM "$child" 2>/dev/null
}

trap _term SIGTERM

virtual_env="/opt/srlinux/python/virtual-env/bin/activate"
main_module="/etc/opt/srlinux/appmgr/multicli/multicli.py"

if [ -f "${virtual_env}" ]; then
    # shellcheck disable=SC1090
    source "${virtual_env}"
fi

PYBASE="/opt/srlinux/python/virtual-env/lib"
if [ -d "${PYBASE}/python3.13" ]; then
    PYVER="python3.13"
elif [ -d "${PYBASE}/python3.11" ]; then
    PYVER="python3.11"
else
    PYVER=$(ls -d "${PYBASE}"/python3.* 2>/dev/null | head -n 1 | xargs basename 2>/dev/null || echo "python3.11")
fi

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${PYTHONPATH:-}:/etc/opt/srlinux/helper:/etc/opt/srlinux/appmgr/multicli:/opt/srlinux/bin:/usr/lib/${PYVER}/dist-packages/sdk_protos:/usr/lib/${PYVER}/dist-packages"

PYTHON_BIN="/opt/srlinux/python/virtual-env/bin/python3"
if [ ! -x "${PYTHON_BIN}" ]; then
    PYTHON_BIN="python3"
fi

"${PYTHON_BIN}" "${main_module}" &
child=$!
wait "$child"
