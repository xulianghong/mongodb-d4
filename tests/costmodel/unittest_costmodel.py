#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os, sys
import random
import time
import unittest

basedir = os.path.realpath(os.path.dirname(__file__))
sys.path.append(os.path.join(basedir, "../../"))

# mongodb-d4
try:
    from mongodbtestcase import MongoDBTestCase
except ImportError:
    from tests import MongoDBTestCase
import catalog
import costmodel
from search import Design
from workload import Session
from util import constants
from inputs.mongodb import MongoSniffConverter

COLLECTION_NAMES = ["squirrels", "girls"]
NUM_DOCUMENTS = 10000
NUM_SESSIONS = 50
NUM_FIELDS = 6
NUM_NODES = 8
NUM_INTERVALS = 10

class TestCostModel(MongoDBTestCase):

    def setUp(self):
        MongoDBTestCase.setUp(self)

        # WORKLOAD
        self.workload = [ ]
        timestamp = time.time()
        for i in xrange(0, NUM_SESSIONS):
            sess = self.metadata_db.Session()
            sess['session_id'] = i
            sess['ip_client'] = "client:%d" % (1234+i)
            sess['ip_server'] = "server:5678"
            sess['start_time'] = timestamp

            for j in xrange(0, len(COLLECTION_NAMES)):
                _id = str(random.random())
                queryId = long((i<<16) + j)
                queryContent = { }
                queryPredicates = { }

                responseContent = {"_id": _id}
                responseId = (queryId<<8)
                for f in xrange(0, NUM_FIELDS):
                    f_name = "field%02d" % f
                    if f % 2 == 0:
                        responseContent[f_name] = random.randint(0, 100)
                        queryContent[f_name] = responseContent[f_name]
                        queryPredicates[f_name] = constants.PRED_TYPE_EQUALITY
                    else:
                        responseContent[f_name] = str(random.randint(1000, 100000))
                    ## FOR

                queryContent = { constants.REPLACE_KEY_DOLLAR_PREFIX + "query": queryContent }
                op = Session.operationFactory()
                op['collection']    = COLLECTION_NAMES[j]
                op['type']          = constants.OP_TYPE_QUERY
                op['query_id']      = queryId
                op['query_content'] = [ queryContent ]
                op['resp_content']  = [ responseContent ]
                op['resp_id']       = responseId
                op['predicates']    = queryPredicates

                op['query_time']    = timestamp
                timestamp += 1
                op['resp_time']    = timestamp

                sess['operations'].append(op)
            ## FOR (ops)
            sess['end_time'] = timestamp
            timestamp += 2
            sess.save()
            self.workload.append(sess)
        ## FOR (sess)

        # Use the MongoSniffConverter to populate our metadata
        converter = MongoSniffConverter(self.metadata_db, self.dataset_db)
        converter.no_mongo_parse = True
        converter.no_mongo_sessionizer = True
        converter.process()
        self.assertEqual(NUM_SESSIONS, self.metadata_db.Session.find().count())

        self.collections = dict([ (c['name'], c) for c in self.metadata_db.Collection.fetch()])
        self.assertEqual(len(COLLECTION_NAMES), len(self.collections))

        self.costModelConfig = {
           'max_memory':     6144, # MB
           'skew_intervals': NUM_INTERVALS,
           'address_size':   64,
           'nodes':          NUM_NODES,
        }
        self.cm = costmodel.CostModel(self.collections, self.workload, self.costModelConfig)
    ## DEF

#    def testGetSplitWorkload(self):
#        """Check that the workload is split into intervals"""
#
#        self.assertEqual(NUM_SESSIONS, sum(map(len, self.cm.workload_segments)))
#        for i in xrange(0, NUM_INTERVALS):
##            print "[%02d]: %d" % (i, len(self.cm.workload_segments[i]))
#            self.assertGreater(len(self.cm.workload_segments[i]), 0)
#        ## FOR
#        self.assertEqual(NUM_INTERVALS, len(self.cm.workload_segments))
#    ## DEF
#
#    def testNetworkCost(self):
#        """Check network cost for equality predicate queries"""
#        col_info = self.collections[COLLECTION_NAMES[0]]
#        self.assertTrue(col_info['interesting'])
#
#        # If we shard the collection on the interesting fields, then
#        # each query should only need to touch one node
#        d = Design()
#        d.addCollection(col_info['name'])
#        d.addShardKey(col_info['name'], col_info['interesting'])
#        cost0 = self.cm.networkCost(d)
##        print "cost0:", cost0
#
#        # If we now shard the collection on just '_id', then every query
#        # should have to touch every node. The cost of this design
#        # should be greater than the first one
#        d = Design()
#        d.addCollection(col_info['name'])
#        d.addShardKey(col_info['name'], ['_id'])
#        cost1 = self.cm.networkCost(d)
##        print "cost1:", cost1
#
#        self.assertLess(cost0, cost1)
#    ## DEF
#
#    def testNetworkCostDenormalization(self):
#        """Check network cost for queries that reference denormalized collections"""
#
#        # Get the "base" design cost when all of the collections
#        # are sharded on their "interesting" fields
#        d = Design()
#        for i in xrange(0, len(COLLECTION_NAMES)):
#            col_info = self.collections[COLLECTION_NAMES[i]]
#            d.addCollection(col_info['name'])
#            if i == 0:
#                d.addShardKey(col_info['name'], col_info['interesting'])
#            else:
#                d.addShardKey(col_info['name'], ["_id"])
#        ## FOR
#        cost0 = self.cm.networkCost(d)
##        print "cost0:", cost0
#
#        # Now get the network cost for when we denormalize the
#        # second collection inside of the first one
#        # We should have a lower cost because there should now be fewer queries
#        d = Design()
#        for i in xrange(0, len(COLLECTION_NAMES)):
#            col_info = self.collections[COLLECTION_NAMES[i]]
#            self.assertTrue(col_info['interesting'])
#            d.addCollection(col_info['name'])
#            if i == 0:
#                d.addShardKey(col_info['name'], col_info['interesting'])
#            else:
#                parent = self.collections[COLLECTION_NAMES[0]]
#                self.assertIsNotNone(parent)
#                d.setDenormalizationParent(col_info['name'], parent['name'])
#                self.assertTrue(d.isDenormalized(col_info['name']), col_info['name'])
#                self.assertIsNotNone(d.getDenormalizationParent(col_info['name']))
#        ## FOR
#        cost1 = self.cm.networkCost(d)
##        print "cost1:", cost1
#
#        # The denormalization cost should also be the same as the cost
#        # when we remove all of the ops one the second collection
#        for sess in self.workload:
#            for op in sess["operations"]:
#                if op["collection"] <> COLLECTION_NAMES[0]:
#                    sess["operations"].remove(op)
#                    ## FOR (op)
#            ## FOR (sess)
#        for i in xrange(1, len(COLLECTION_NAMES)):
#            del self.collections[COLLECTION_NAMES[i]]
#        cost2 = self.cm.networkCost(d)
##        print "cost2:", cost2
#
#        self.assertLess(cost1, cost0)
#        self.assertEqual(cost1, cost2)
#    ## DEF

    def testSkewCost(self):
        col_info = self.collections[COLLECTION_NAMES[0]]
        self.assertTrue(col_info['interesting'])

        # If we shard the collection on the interesting fields, then
        # each query should only need to touch one node
        d = Design()
        d.addCollection(col_info['name'])
        d.addShardKey(col_info['name'], col_info['interesting'])
        cost0 = self.cm.skewCost(d)
        print "skewCost0:", cost0


    ## DEF

#    def testDiskCost(self):
#        cost = self.cm.diskCost(self.d, self.w)
#        self.assertEqual(cost, 1.0)
#
#    def testOverallCost(self):
#        config = {'nodes' : 4}
#        cost = self.cm.overallCost(self.d, self.w, config)
#        self.assertEqual(cost, 0.0)
## CLASS

if __name__ == '__main__':
    unittest.main()
## MAIN