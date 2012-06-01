#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------
# Copyright (C) 2011 by Brown University
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
# -----------------------------------------------------------------------
from __future__ import with_statement

import os
import sys
import fileinput
import time
import argparse
import logging
from pprint import pformat
from pymongo import Connection

# Third-Party Dependencies
basedir = os.path.realpath(os.path.dirname(__file__))
sys.path.append(os.path.join(basedir, "../../libs"))
import mongokit

# MongoDB-Designer
sys.path.append(os.path.join(basedir, "../workload"))
sys.path.append(os.path.join(basedir, "../sanitizer"))
import workload_info
import parser
from traces import *

logging.basicConfig(level = logging.INFO,
                    format="%(asctime)s [%(funcName)s:%(lineno)03d] %(levelname)-5s: %(message)s",
                    datefmt="%m-%d-%Y %H:%M:%S",
                    stream = sys.stdout)
LOG = logging.getLogger(__name__)

## ==============================================
## DEFAULT VALUES
## you can specify these with args
## ==============================================
INPUT_FILE = "sample.txt"
WORKLOAD_DB = "metadata"
WORKLOAD_COLLECTION = "workload01"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = "27017"

## ==============================================
## main
## ==============================================
if __name__ == '__main__':
    aparser = argparse.ArgumentParser(description='MongoDesigner Trace Parser')
    aparser.add_argument('--host', default=DEFAULT_HOST,
                         help='hostname of machine running mongo server')
    aparser.add_argument('--port', type=int, default=DEFAULT_PORT,
                         help='port to connect to')
    aparser.add_argument('--file', default=INPUT_FILE,
                         help='file to read from')
    aparser.add_argument('--workload_db', default=WORKLOAD_DB,
                         help='the database where you want to store the traces')
    aparser.add_argument('--workload_col', default=WORKLOAD_COLLECTION,
                         help='The collection where you want to store the traces', )
    aparser.add_argument('--clean', action='store_true',
                         help='Remove all documents in the workload collection before processing is started')
    aparser.add_argument('--debug', action='store_true',
                         help='Enable debug log messages')
    args = vars(aparser.parse_args())
    if args['debug']: LOG.setLevel(logging.DEBUG)

    LOG.info("..:: MongoDesigner Trace Parser ::..")
    LOG.debug("Server: %(host)s:%(port)d / InputFile: %(file)s / Storage: %(workload_db)s.%(workload_col)s" % args)

    # initialize connection to MongoDB
    # Initialize connection to db that stores raw transactions
    LOG.debug("Connecting to MongoDB at %s:%d" % (args['host'], args['port']))
    connection = Connection(args['host'], args['port'])
    workload_col = connection[args['workload_db']][args['workload_col']]
    assert workload_col, "Invalid target collection %s.%s" % (args['workload_db'], args['workload_col'])

    # Create the Parser object that will go to town on the input file that we
    # were given
    with open(args['file'], 'r') as fd:
        p = parser.Parser(workload_col, fd)
        
        # wipe the collection
        if args['clean']:
            LOG.warn("Cleaning '%s' collection...", workload_col)
            p.cleanWorkload()
        
        LOG.info("Processing file %s", args['file'])
        p.parse()
        LOG.info("Done. Added [%d sessions] to '%s'" % (p.getSessionCount(), workload_col))
    ## WITH
    
    # Print out some information when parsing finishes
    if args['debug']:
        workload_info.print_stats(args['host'], args['port'], args['workload_db'], args['workload_col'])
    
## MAIN


    
