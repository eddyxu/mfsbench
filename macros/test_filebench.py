#!/usr/bin/env python3
#
# Author: Lei Xu <eddyxu@gmail.com>

"""Use filebench to test manycore VFS performance.
"""

import os
import sys
sys.path.append('..')
import mfsbase
import argparse

FILE_SYSTEMS = 'ext4,btrfs'
WORKLOADS = 'varmail,fileserver,oltp,webserver,webproxy'


def prepare_disks(**kwargs):
    """Prepare disks
    """
    fs = kwargs.get('fs', 'ext4')
    if not os.exists('ramdisks'):
        os.makedirs('ramdisks')


def main():
    """Filebench tests
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--formats', metavar='FS,FS,..',
                        help='sets testing file systems (default: {}).'
                        .format(FILE_SYSTEMS))
    parser.add_argument('-w', '--workloads', metavar='NAME,NAME,..',
                        help='set workloads, separated by comma. (default: {})'
                        .format(WORKLOADS))
    parser.add_argument('-i', '--iteration', metavar='NUM', type=int,
                        default=1, help='set iteration, default: 1')
    parser.add_argument('-s', '--iosize', metavar='NUM', type=int,
                        default=1024, help='set IOSIZE (default: 1024)')
    args = parser.parse_args()
    mfsbase.check_root_or_exit()


if __name__ == '__main__':
    main()
