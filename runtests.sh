#!/bin/sh
set -e

if [ "$1" = "--no-cov" ]; then
    COVARG=""
else
    COVARG="--cov=vidhubcontrol"
fi

py.test --cov-config .coveragerc $COVARG
if [ "$COVARG" != "" ]; then
    mv .coverage .coverage-orig
fi

for f in tests/kv/test*.py
do
    echo "Running $f"
    py.test --fulltrace --cov-append --cov-config .coveragerc "$f" $COVARG
    if [ "$COVARG" != "" ]; then
        coverage combine -a .coverage-orig
        mv .coverage .coverage-orig
    fi
done

if [ "$COVARG" != "" ]; then
    coverage combine -a .coverage-orig
    coverage report
fi
