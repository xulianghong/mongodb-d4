# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------
# Copyright (C) 2012 by Brown University
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
import os
import string
import re
import logging
import traceback
import pymongo
from datetime import datetime
from pprint import pprint, pformat

import constants
from util import *
from api.abstractworker import AbstractWorker
from api.message import *

LOG = logging.getLogger(__name__)

# BLOGWORKER
# Andy Pavlo - http://www.cs.brown.edu/~pavlo/
# 
# This is the worker for the 'blog' microbenchmark in the paper
# There are three types of experiments that we want to perform on the 
# data generated by this code. These experiments are designed to higlight
# different aspects of database design in MongoDB by demonstrated the
# performance trade-offs of getting it wrong.
# For each experiment type, there are two variations of the workload. The first 
# of which is the "correct" design choice and the second is the "bad" design
# choice. Yes, this is somewhat a simplistic view, but it's mostly 
# meant to be an demonstration rather than a deep analysis of the issues:
#
# Experiment #1: SHARDING KEYS
# For this experiment, we will shard articles by their autoinc id and then 
# by their id+timestamp. This will show that sharding on just the id won't
# work because of skew, but by adding the timestamp the documents are spread out
# more evenly.
# 
# Experiment #2: DENORMALIZATION
# In our microbenchmark we should have a collection of articles and collection of 
# article comments. The target workload will be to grab an article and grab the 
# top 10 comments for that article sorted by a user rating. In the first experiment,
# we will store the articles and comments in separate collections.
# In the second experiment, we'll embedded the comments inside of the articles.
# 
# Experiment #3: INDEXES
# In our final benchmark, we compared the performance difference between a query on 
# a collection with (1) no index for the query's predicate, (2) an index with only one 
# key from the query's predicate, and (3) a covering index that has all of the keys 
# referenced by that query.
# 
class BlogWorker(AbstractWorker):
    
    def initImpl(self, config):
        
        # A list of booleans that we will randomly select
        # from to tell us whether our txn should be a read or write
        self.workloadWrite = [ ]
        for i in xrange(0, constants.WORKLOAD_READ_PERCENT):
            self.workloadWrite.append(False)
        for i in xrange(0, constants.WORKLOAD_WRITE_PERCENT):
            self.workloadWrite.append(True)
        
        # Total number of articles in database
        self.num_articles = int(self.getScaleFactor() * constants.NUM_ARTICLES)
        
        articleOffset = (1 / float(self.getWorkerCount())) * self.num_articles
        self.firstArticle = int(self.getWorkerId() * articleOffset)
        self.lastArticle = int(self.firstArticle + articleOffset)
        self.lastCommentId = None
        self.articleZipf = ZipfGenerator(self.num_articles, 1.0)
        LOG.info("Worker #%d Articles: [%d, %d]" % (self.getWorkerId(), self.firstArticle, self.lastArticle))
        
        numComments = int(config[self.name]["commentsperarticle"])
        # Zipfian distribution on the number of comments & their ratings
        self.commentsZipf = ZipfGenerator(numComments, 1.0)
        self.ratingZipf = ZipfGenerator(constants.MAX_COMMENT_RATING, 1.0)
        # breaking the date range in x segments to do the range queries against later
        self.dateZipf = ZipfGenerator(constants.NUMBER_OF_DATE_SUBRANGES,1.0)
        self.db = self.conn[config['default']["dbname"]]
        
        
        #HACK recomputing the authors list for simplicity TODO to pass it in the initImpl
        elf.authors = [ ]
        for i in xrange(0, constants.NUM_AUTHORS):
            #authorSize = constants.AUTHOR_NAME_SIZE
            self.authors.append("authorname".join(str(i))
        self.authorZipf = ZipfGenerator(constants.NUM_AUTHORS,1.0)
        
        if self.getWorkerId() == 0:
            if config['default']["reset"]:
                LOG.info("Resetting database '%s'" % config['default']["dbname"])
                self.conn.drop_database(config['default']["dbname"])
            
            ## SHARDING
            if config[self.name]["experiment"] == constants.EXP_SHARDING:
                self.initSharding(config)
        ## IF
        
        self.initNextCommentId(config[self.name]["maxCommentId"])
    ## DEF
    
    def initSharding(self, config):
        assert self.db != None
        
        # Enable sharding on the entire database
        try:
            result = self.db.command({"enablesharding": self.db.name})
            assert result["ok"] == 1, "DB Result: %s" % pformat(result)
        except:
            LOG.error("Failed to enable sharding on database '%s'" % self.db.name)
            raise
        
        # Generate sharding key patterns
        # CollectionName -> Pattern
        # http://www.mongodb.org/display/DOCS/Configuring+Sharding#ConfiguringSharding-ShardingaCollection
        shardingPatterns = { }
        
        if config[self.name]["sharding"] == constants.SHARDEXP_SINGLE:
            pass
        
        elif config[self.name]["sharding"] == constants.SHARDEXP_COMPOUND:
            pass
        
        else:
            raise Exception("Unexpected sharding configuration type '%d'" % config["sharding"])
        
        # Then enable sharding on each of these collections
        for col,pattern in shardingPatterns.iteritems():
            LOG.debug("Sharding Collection %s.%s: %s" % (self.db.name, col, pattern))
            try:
                result = self.db.command({"shardcollection": col, "key": pattern})
                assert result["ok"] == 1, "DB Result: %s" % pformat(result)
            except:
                LOG.error("Failed to enable sharding on collection '%s.%s'" % (self.db.name, col))
                raise
        ## FOR
        
        LOG.debug("Successfully enabled sharding on %d collections in database %s" % \
                  (len(shardingPatterns, self.db.name)))
    ## DEF
    
    def initIndexes(self, optType, denormalize=False):
        assert self.db != None
	
        # Nothing
        if optType == constants.INDEXEXP_NONE:
            pass
        # Regular Index
        elif optType == constants.INDEXEXP_PREDICATE:
	    LOG.info("Creating primary key indexes for %s" % self.db[constants.ARTICLE_COLL].full_name) 
            self.db[constants.ARTICLE_COLL].ensure_index([("id", pymongo.ASCENDING)])
        # Cover Index
        elif optType == constants.INDEXEXP_COVERING:
            self.db[constants.ARTICLE_COLL].ensure_index([("id", pymongo.ASCENDING), \
                                                          ("date", pymongo.ASCENDING), \
                                                          ("author", pymongo.ASCENDING)])
        # Busted!
        else:
            raise Exception("Unexpected indexing configuration type '%d'" % optType)
        if not denormalize:
	   #drop useless comment._id index - if removed the drop_indexes doesn't do actually anything...
           LOG.info("Creating indexes (articleId,rating) %s" % self.db[constants.COMMENT_COLL].full_name)
           self.db[constants.COMMENT_COLL].ensure_index([("article", pymongo.ASCENDING), \
                                                         ("rating", pymongo.DESCENDING)])
        ## IF
        
    ## DEF
    
    def initNextCommentId(self, maxCommentId):
        idRange = int(250000 * self.getScaleFactor())
        self.lastCommentId = maxCommentId + (idRange * self.getWorkerId())
        LOG.info("Initialized NextCommentId for Worker %d: %d" % (self.getWorkerId(), self.lastCommentId))
    ## DEF
    
    def getNextCommentId(self):
        """Return the next commentId to use at this worker. This is guaranteed to be globally unique across all workers in this benchmark invocation"""
        assert self.lastCommentId <> None
        self.lastCommentId += 1
        return self.lastCommentId
    ## DEF
 
    ## ---------------------------------------------------------------------------
    ## STATUS
    ## ---------------------------------------------------------------------------
    
    def statusImpl(self, config, channel, msg):
        result = { }
        for col in self.db.collection_names():
            stats = self.db.validate_collection(col)
            result[self.db.name + "." + col] = (stats.datasize, stats.nrecords)
        ## FOR
        return (result)
    ## DEF
 
    ## ---------------------------------------------------------------------------
    ## LOAD
    ## ---------------------------------------------------------------------------
    
    def loadImpl(self, config, channel, msg):
        assert self.conn != None
        
        # The message we're given is a tuple that contains
        # the list of author names that we'll generate articles from
        #authors = msg.data[0]
        #LOG.info("Generating %s data [denormalize=%s]" % (self.getBenchmarkName(), config[self.name]["denormalize"]))
        
        # HACK: Setup the indexes if we're the first client
        if self.getWorkerId() == 0:
            self.db[constants.ARTICLE_COLL].drop_indexes()
            self.db[constants.COMMENT_COLL].drop_indexes()
            
            # SHARDING KEY + DENORMALIZATION
            if config[self.name]["experiment"] in [constants.EXP_SHARDING, constants.EXP_DENORMALIZATION]:
                self.initIndexes(constants.INDEXEXP_PREDICATE, config[self.name]["denormalize"])
            # INDEXING
            elif config[self.name]["experiment"] == constants.EXP_INDEXING:
                self.initIndexes(config[self.name]["indexes"])
            # BUSTED!
            else:
                raise Exception("Unexpected experiment type %s" % config[self.name]["experiment"])
        ## IF
        
        ## ----------------------------------------------
        ## LOAD ARTICLES
        ## ----------------------------------------------
        articlesBatch = [ ]
        articleCtr = 0
        articleTotal = self.lastArticle - self.firstArticle
        commentsBatch = [ ]
        commentCtr = 0
        commentTotal= 0
        numComments = int(config[self.name]["commentsperarticle"])
        for articleId in xrange(self.firstArticle, self.lastArticle+1):
            titleSize = constants.ARTICLE_TITLE_SIZE
            title = randomString(titleSize)
            contentSize = constants.ARTICLE_CONTENT_SIZE
            content = randmString(contentSize)
            slug = list(title.replace(" ", ""))
            if len(slug) > 64: slug = slug[:64]
            for idx in xrange(0, len(slug)):
                if random.randint(0, 10) == 0:
                    slug[idx] = "-"
            ## FOR
            slug = "".join(slug)
            articleDate = randomDate(constants.START_DATE, constants.STOP_DATE)
            
            article = {
                "id": articleId,
                "title": title,
                "date": articleDate,
                "author": random.choice(authors),
                "slug": slug,
                "content": content,
                "numComments": numComments,
            }
            articleCtr+=1;
            #if denormalize directly insert article else store it in batch
            if config[self.name]["denormalize"]:
                article["comments"] = [ ]
                self.db[constants.ARTICLE_COLL].insert(article)
            else:
	        articlesBatch.append(article)
            
            
            ## ----------------------------------------------
            ## LOAD COMMENTS
            ## ----------------------------------------------
            
            LOG.debug("Comments for article %d: %d" % (articleId, numComments))
            for ii in xrange(0, numComments):
                lastDate = randomDate(lastDate, constants.STOP_DATE)
                commentAuthor = randomString(constants.AUTHOR_NAME_SIZE)
                commentContent = randomString(constants.COMMENT_CONTENT_SIZE)
                
                comment = {
                    "id": articleId+"|"+ii,
                    "article": articleId,
                    "date": randomDate(articleDate, constants.STOP_DATE), 
                    "author": commentAuthor,
                    "comment": commentContent,
                    "rating": int(self.ratingZipf.next())
                }
                commentCtr += 1
                
		commentsBatch.append(comment) 
		
	    ## FOR (comments)
	    
	    #if denormalize insert in article else insert in separate collection of comments
	    if config[self.name]["denormalize"]:
	        self.db[constants.ARTICLE_COLL].update({"id": articleId},{"$pushAll":{"comments":commentsBatch}})
	
            if articleCtr % 100 == 0 or articleCtr % 100 == 1 :
                self.loadStatusUpdate(articleCtr / articleTotal)
                LOG.info("ARTICLE: %6d / %d" % (articleCtr, articleTotal))
                if len(commentsBatch) > 0:
                    LOG.debug("COMMENTS: %6d" % (commentCtr))
            #self.db[constants.ARTICLE_COLL].insert(articlesBatch)
            
            if not config[self.name]["denormalize"]:
	        if len(articlesBatch) > 0:
		    self.db[constants.ARTICLE_COLL].insert(articlesBatch)
                if len(commentsBatch) > 0:
                    self.db[constants.COMMENT_COLL].insert(commentsBatch)
           
            
            
             
             
            articlesBatch = [ ]
            commentsBatch = [ ]
            ## IF
	## FOR (articles)    
        LOG.info("FINAL-ARTICLES: %6d / %d" % (articleCtr-1, articleTotal))
        LOG.info("FINAL-COMMENTS: %6d / %d" % (commentCtr,commentCtr))        
                #if config[self.name]["denormalize"]:
                #    if self.debug: 
                #        LOG.debug("Storing new comment for article %d directly in document" % articleId)
                #    article["comments"].append(comment)
                #else:
                #    if self.debug:
                #        LOG.debug("Storing new comment for article %d in separate batch" % articleId)
                #    commentsBatch.append(comment)
            ## FOR (comments)
            #if self.debug: LOG.debug("Comment Batch: %d" % len(commentsBatch))

            # Always insert the article
            #articlesBatch.append(article)
            #articleCtr += 1
            #if articleCtr % 100 == 0 :
            #    if articleCtr % 1000 == 0 :
            #        self.loadStatusUpdate(articleCtr / articleTotal)
            #        LOG.info("ARTICLE: %6d / %d" % (articleCtr, articleTotal))
            #        if len(commentsBatch) > 0:
            #            LOG.debug("COMMENTS: %6d" % (commentCtr))
            #    self.db[constants.ARTICLE_COLL].insert(articlesBatch)
            #    articlesBatch = [ ]
            #    
            #    if len(commentsBatch) > 0:
            #        self.db[constants.COMMENT_COLL].insert(commentsBatch)
            #        commentsBatch = [ ]
            ## IF
                
        ## FOR (articles)
        #if len(articlesBatch) > 0 and not config[self.name]["denormalize"]:
        #    LOG.info("ARTICLE: %6d / %d" % (articleCtr, articleTotal))
        #    self.db[constants.ARTICLE_COLL].insert(articlesBatch)
        #    #if len(commentsBatch) > 0:
        #        #self.db[constants.COMMENT_COLL].insert(commentsBatch)
        
        
    ## DEF
    
    ## ---------------------------------------------------------------------------
    ## EXECUTION INITIALIZATION
    ## ---------------------------------------------------------------------------
    
    def executeInitImpl(self, config):
        pass
    ## DEF
    
    ## ---------------------------------------------------------------------------
    ## WORKLOAD EXECUTION
    ## ---------------------------------------------------------------------------
    
    def next(self, config):
        assert "experiment" in config[self.name]
        
        ## Generate skewed target articleId if we're doing the
        ## sharding experiments
        #if config[self.name]["experiment"] == constants.EXP_SHARDING:
        #    assert self.articleZipf
        #    articleId = int(self.articleZipf.next())
        ## Otherwise pick one at random uniformly
        #else:
        #    articleId = int(self.articleZipf.next())
        #    # HACK articleId = random.randint(0, self.num_articles)
        
        
    
        ## Check wether we're doing a read or a write txn
        #if random.choice(self.workloadWrite):
        #    txnName = "writeComment"
        #else:
        #    txnName = "readArticle"
        
        if config[self.name]["experiment"] == constants.EXP_DENORMALIZATION:
           articleId = random.randint(0, self.num_articles)
           txnName = "readArticleTopTenComments"
           return (txnName, (articleId))
        elif config[self.name]["experiment"] == constants.EXP_INDEXING:
	   #The skew percentage determines which operations we will grab 
	   #an articleId/articleDate using a Zipfian random number generator versus 
	   #a uniform distribution random number generator.
	   skewfactor = float(config[self.name]["skew"]
	   trial = int(config[self.name]["sharding"])
	   #The first trial (0) will consist of 90% reads and 10% writes. 
	   #The second trial (1) will be 80% reads and 20% writes.
	   readwriterandom = random.random()
	   read = False
	   if trial == 0: 
	       #read
	       if readwriterandom < 0.8:
	           read = True
	   elif trial == 1:
	       #read
	       if readwriterandom < 0.9:
	           read = True	 
	   
	   #if read
	   if read == True:
	       #random 1..3 to see which read we will make
	       randreadop = random.randint(1,3)
	       skewrandom = random.random()
	       if randreadop == 1:
	           if skewrandom < skewfactor
	               articleId = random.randint(0, self.num_articles)
	           else:
		       articleId = self.articleZipf.next()
		   txnName = "readArticleById"
		   return (txnName, (articleId))
	       elif randreadop == 2:
	           if skewrandom < skewfactor
	               author = authors[int(random.randint(0,constants.NUM_AUTHORS-1))] #TODO to fix
	           else:
		       author = authors[self.authorZipf.next()] #TODO to fix how to get the right position
		   txnName = "readArticleByAuthor"
		   return (txnName, (author)) 
	       elif randreadop == 3:
	       	   if skewrandom < skewfactor
	               date = random.randint(0,constants.NUMBER_OF_DATE_SUBRANGES-1) 
	               author = authors[int(random.randint(0,constants.NUM_AUTHORS-1))] #TODO to fix
	           else:
		       date = self.dateZipf.next() #TODO use the DateZipf and make range date queries 
		       author = authors[self.authorZipf.next()] #TODO to fix how to get the right position
		   txnName = "readArticleByAuthorAndDate"
		   return (txnName, (author,date)) 
	   #if write
	   elif read == False: 
	       if skewrandom < skewfactor
	               articleId = random.randint(0, self.num_articles)
	           else:
		       articleId = self.articleZipf.next()
	       txnName="incViewsArticle"
	       return (txnName, (articleId)) 
	   #do the increase of views
	  
	  return
	  
	  
	  
	  
	  
	  
        
   
   ## DEF
        
    def executeImpl(self, config, txn, params):
        assert self.conn != None
        assert "experiment" in config[self.name]
        
        if self.debug:
            LOG.debug("Executing %s / %s" % (txn, str(params)))
        
        m = getattr(self, txn)
        assert m != None, "Invalid transaction name '%s'" % txn
        try:
            result = m(config[self.name]["denormalize"], params)
        except:
            LOG.warn("Unexpected error when executing %s" % txn)
            raise
        
        return
    ## DEF
    
    def readArticleById(self, denormalize, articleId):
        article = self.db[constants.ARTICLE_COLL].find_one({"id": articleId})
        if not article:
            LOG.warn("Failed to find %s with id #%d" % (constants.ARTICLE_COLL, articleId))
            return
        assert article["id"] == articleId, \
            "Unexpected invalid %s record for id #%d" % (constants.ARTICLE_COLL, articleId)
          None  
        # If we didn't denormalize, then we have to execute a second
        # query to get all of the comments for this article
        if not denormalize:
            comments = self.db[constants.COMMENT_COLL].find({"article": articleId})
        else:
            assert "comments" in article, pformat(article)
            comments = article["comments"]
    ## DEF
	
	def readArticleByAuthor(self,denormalize,author):
	    article = self.db[constants.ARTICLE_COLL].find_one({"author": author})
            articleId = article["id"]
	if not article:
            LOG.warn("Failed to find %s with id #%d" % (constants.ARTICLE_COLL, articleId))
            return
        assert article["author"] == author, \
            "Unexpected invalid %s record for id #%d" % (constants.ARTICLE_COLL, articleId)
            
        # If we didn't denormalize, then we have to execute a second
        # query to get all of the comments for this article
        if not denormalize:
            comments = self.db[constants.COMMENT_COLL].find({"article": articleId})
        else:
            assert "comments" in article, pformat(article)
            comments = article["comments"]
    ## DEF
	
	#def readArticleByDate(self,denormalize,date):
	#    article = self.db[constants.ARTICLE_COLL].find_one({"date": date})
        #    articleId = article["id"]
	#if not article:
        #    LOG.warn("Failed to find %s with id #%d" % (constants.ARTICLE_COLL, articleId))
        #    return
        #assert article["author"] == author, \
        #    "Unexpected invalid %s record for id #%d" % (constants.ARTICLE_COLL, articleId)
        #    
        ## If we didn't denormalize, then we have to execute a second
        ## query to get all of the comments for this article
        #if not denormalize:
        #    comments = self.db[constants.COMMENT_COLL].find({"article": articleId})
        #else:
        #    assert "comments" in article, pformat(article)
        #    comments = article["comments"]
    ## DEF
	
	
    def readArticleByAuthorAndDate(self,denormalize,author,date):
        article = self.db[constants.ARTICLE_COLL].find_one({"author":author,"date": date})
        articleId = article["id"]
	if not article:
            LOG.warn("Failed to find %s with id #%d" % (constants.ARTICLE_COLL, articleId))
            return
        assert article["author"] == author, \
            "Unexpected invalid %s record for id #%d" % (constants.ARTICLE_COLL, articleId)
        assert article["date"] == date, \
            "Unexpected invalid %s record for id #%d" % (constants.ARTICLE_COLL, articleId)   
        # If we didn't denormalize, then we have to execute a second
        # query to get all of the comments for this article
        if not denormalize:
            comments = self.db[constants.COMMENT_COLL].find({"article": articleId})
        else:
            assert "comments" in article, pformat(article)
            comments = article["comments"]
    ## DEF
	
    def readArticleTopTenComments(self,denormalize,articleId):
        
        # We are searching for the comments that had been written for the article with articleId 
        # and we sort them in descending order of user rating
        if not denormalize: 
            article = self.db[constants.ARTICLE_COLL].find_one({"id": articleId})
            comments = self.db[constants.COMMENT_COLL].find({"article": articleId}).sort("rating",-1)
            #for comment in comments:
            #    pprint(comment)
            #    print("\n");
            #print("~~~~~~~~~~~~~~");
        else:
            article = self.db[constants.ARTICLE_COLL].find_one({"id": articleId})
            #print(pformat(article))
            if not article is None:
                assert 'comments' in article, pformat(article)
                comments = article[u'comments']
                #sort by rating ascending and take top 10..
                comments = sorted(comments, key=lambda k: -k[u'rating'])
                comments = comments[0:10]
                #    pprint(comments)
                #    print("\n");
        if article is None:
            LOG.warn("Failed to find %s with id #%d" % (constants.ARTICLE_COLL, articleId))
            return
        assert article["id"] == articleId, \
            "Unexpected invalid %s record for id #%d" % (constants.ARTICLE_COLL, articleId) 
        
        
    ## DEF
	
    def incViewsArticle(self,denormalize,articleId):
        # Increase the views of an article by one
        result=self.db[constants.ARTICLE_COLL].update({'id':articleId},{"$inc" : "views"},True)
        if not result:
            LOG.warn("Failed to increase views on %s with id #%d" % (constants.ARTICLE_COLL, articleId))
            return
	
    #def writeComment(self, denormalize, articleId):
    #    # Generate a random comment document
    #    # The commentIds are generated 
    #    commentAuthor = randomString(constants.AUTHOR_NAME_SIZE)
    #    commentContent = randomString(constants.COMMENT_CONTENT_SIZE)
    #    comment = {
    #        "id":       self.getNextCommentId(),
    #        "article":  articleId,
    #        "date":     randomDate(, 
    #        "author":   commentAuthor,
    #        "comment":  commentContent,
    #        "rating":   int(self.ratingZipf.next())
    #    }
    #    
    #    # If we're denormalized, then we need to append our comment
    #    # to the article's list of comments
    #    if denormalize:
    #        #self.db[constants.ARTICLE_COLL].update({"id": articleId}, {"$push": {"comments": comment})
    #        pass
    #    
    #    # Otherwise, we can just insert it into the COMMENTS collection
    #    else:
    #        self.db[constants.COMMENT_COLL].insert(comment)
    # 
    #    return
    ## DEF

    def expIndexes(self, articleId):
        """
        In our final benchmark, we compared the performance difference between a query on 
        a collection with (1) no index for the query's predicate, (2) an index with only one 
        key from the query's predicate, and (3) a covering index that has all of the keys 
        referenced by that query.
        What do we want to vary here on the x-axis? The number of documents in the collection?
        """
        
        article = self.db[constants.ARTICLE_COLL].find({"id": articleId}, {"id", "date", "author"})
        if not article:
            LOG.warn("Failed to find %s with id #%d" % (constants.ARTICLE_COLL, articleId))
            return
        
        return
## CLASS