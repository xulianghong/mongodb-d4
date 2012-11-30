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
import os
import signal
import threading
import subprocess
import logging

LOG = logging.getLogger(__name__)

class MongoStatCollector(threading.Thread):
    
    def __init__(self, host, outputFile, outputInterval=10, showAll=True):
        threading.Thread.__init__(self)
        self.host = host
        self.outputFile = outputFile
        self.outputInterval = outputInterval
        self.showAll = outputFile
        self.daemon = True
        self.process = None
        self.record = False
    ## DEF
    
    def startRecording(self):
        LOG.info("Starting stat data collection [%s]", self.outputFile)
        self.record = True
        
    def stopRecording(self):
        LOG.info("Stopping stat data collection [%s]", self.outputFile)
        self.record = False
    
    def run(self):
        command = "mongostat --host %s" % self.host
        if self.showAll: command += " --all"
        command += " %d" % self.outputInterval
        
        LOG.debug("Forking command: %s" % command)
        self.process = subprocess.Popen(command, \
                             stdout=subprocess.PIPE, \
                             shell=True,
                             preexec_fn=os.setsid)
        LOG.info("Writing MongoStat output to '%s'" % self.outputFile)
        with open(self.outputFile, "w") as fd:
            for line in self.process.stdout:
                if self.record: fd.write(line)
        LOG.debug("MongoStatCollection thread is stopping")
    ## DEF
    
    def stop(self):
        if not self.process is None:
            LOG.warn("Killing MongoStatCollection process %d [%s]", self.process.pid, self.outputFile)
            os.killpg(self.process.pid, signal.SIGTERM)
    ## DEF

## CLASS
