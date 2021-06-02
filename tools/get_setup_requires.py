#! /usr/bin/env python

import argparse
from pathlib import Path
from setuptools.config import read_configuration


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        '-c', '--conf-file', dest='conf_file', default='setup.cfg',
        help='Path to the setup.cfg file to read. Default is "%(default)s"',
    )
    p.add_argument(
        '-e', '--extras', dest='extras',
        help='Only show "extra" dependencies with the given name',
    )
    p.add_argument(
        '-d', '--delimiter', dest='delimiter', default=' ',
        help='Character(s) to separate the results. Default is "%(default)s"',
    )
    args = p.parse_args()
    args.conf_file = Path(args.conf_file)
    return args

def main():
    args = parse_args()
    conf = read_configuration(args.conf_file)
    if args.extras:
        try:
            deps = conf['options']['extras_require'][args.extras]
        except KeyError:
            return
    else:
        deps = conf['options']['install_requires']
    print(args.delimiter.join(deps))

if __name__ == '__main__':
    main()
