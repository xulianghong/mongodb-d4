# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------
# Copyright (C) 2012
# Andy Pavlo - http://www.cs.brown.edu/~pavlo/
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

import sys
import random
import logging
from pprint import pformat

from ophasher import *
from util import constants

LOG = logging.getLogger(__name__)

class StatsProcessor:

    def __init__(self, metadata_db, dataset_db):
        self.metadata_db = metadata_db
        self.dataset_db = dataset_db
        self.hasher = OpHasher()
    ## DEF
    
    def reset(self):
        # FIXME: This should be done with a single update query
        for col in self.metadata_db.Collection.find():
            for k, v in col['fields'].iteritems() :
                v['query_use_count'] = 0
                v['cardinality'] = 0
                v['selectivity'] = 0
                col.save()
    ## DEF
    
    def processWorkload(self):
        """Process Workload Trace"""
        for rec in self.metadata_db[constants.COLLECTION_WORKLOAD].find().limit(1000) :
            for op in rec['operations'] :
                tuples = []
                col_info = self.metadata_db.Collection.one({'name':op['collection']})
                if op['type'] == '$delete' :
                    for content in op['query_content'] :
                        for k,v in content.iteritems() :
                            tuples.append((k, v))
                elif op['type'] == '$insert' :
                    for content in op['query_content'] :
                        for k,v in content.iteritems() :
                            tuples.append((k, v))
                elif op['type'] == '$query' :
                    for content in op['query_content'] :
                        if content['query'] != None :
                            for k, v in content['query'].iteritems() :
                                tuples.append((k, v))
                elif op['type'] == '$update' :
                    for content in op['query_content'] :
                        try :
                            for k,v in content.iteritems() :
                                tuples.append((k, v))
                        except AttributeError :
                            pass
                for t in tuples :
                    ## Update times the column is referenced in a query
                    try :
                        col_info['fields'][t[0]]['query_use_count'] += 1
                    except KeyError :
                        pass
                col_info.save()
    ## DEF
    
    def processQueryIds(self):
        for rec in self.metadata_db[constants.COLLECTION_WORKLOAD].find().limit(1000):
            for op in rec['operations'] :
                op[u"query_id"] = self.hasher.hash(op)
            self.metadata_db[constants.COLLECTION_WORKLOAD].save(rec)
        ## FOR
        print("Query Class Histogram:\n%s" % self.hasher.histogram)
    ## DEF
    
    def processDataset(self, sample_rate):
        """Process Sample Dataset"""
        tuple_sizes = {}
        distinct_values = {}
        first = {}
        
        # Compute per-column statistics
        for col in self.metadata_db.Collection.find():
            if not col['name'] in distinct_values:
                distinct_values[col['name']] = {}
                first[col['name']] = {}
                for k, v in col['fields'].iteritems() :
                    distinct_values[col['name']][k] = {}
                    first[col['name']][k] = True
                ## FOR
            ## IF
            
            col['tuple_count'] = 0
            tuple_sizes[col['name']] = 0
            rows = self.dataset_db[col['name']].find()
            for row in rows :
                col['tuple_count'] += 1
                to_use = random.randrange(1, 100, 1)
                if to_use <= sample_rate : 
                    for k, v in row.iteritems() :
                        if k <> '_id' :
                            if col['fields'][k]['type'] == 'int' :
                                tuple_sizes[col['name']] += 4
                            elif col['fields'][k]['type'] == 'str' :
                                tuple_sizes[col['name']] += len(v)
                            elif col['fields'][k]['type'] == 'datetime' :
                                tuple_sizes[col['name']] += 8
                            elif col['fields'][k]['type'] == 'float' :
                                tuple_sizes[col['name']] += 8
                            distinct_values[col['name']][k][v] = v
                        else :
                            tuple_sizes[col['name']] += 12
            if col['tuple_count'] == 0 :
                col['avg_doc_size'] = 0
            else :
                col['avg_doc_size'] = int(tuple_sizes[col['name']] / col['tuple_count'])
            col.save()
        ## FOR
        
        # Calculate cardinality and selectivity
        for col in self.metadata_db.Collection.find():
            for k,v in col['fields'].iteritems() :
                v['cardinality'] = len(distinct_values[col['name']][k])
                if col['tuple_count'] == 0 :
                    v['selectivity'] = 0
                else :
                    v['selectivity'] = v['cardinality'] / col['tuple_count']
            col.save()
    ## DEF
    