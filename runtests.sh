#!/bin/sh
set -e

py.test --cov-config .coveragerc --cov=vidhubcontrol
# mv .coverage .coverage-orig
#
# for f in tests/kv/test*.py
# do
#     echo "Running $f"
#     py.test --fulltrace --cov-append --cov-config .coveragerc --cov=vidhubcontrol "$f"
#     coverage combine -a .coverage-orig
#     mv .coverage .coverage-orig
# done
# coverage combine -a .coverage-orig
# coverage report
