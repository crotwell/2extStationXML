#! /usr/bin/python
'''
check if single channel sensor response in NRL
'''
import checkNRL as checkNRL
import sisxmlparser3_0 as sisxmlparser
import uniqResponses as uniqResponses
from xerces_validate import xerces_validate, SCHEMA_FILE

import argparse
import datetime
import os
import re
import subprocess
import sys

global VERBOSE
VERBOSE=False
#VERBOSE=True

def usage():
    print("python isnrl <file.staxml> <chanAId>")
    print("python isnrl <file.staxml> --list")

def initArgParser():
  parser = argparse.ArgumentParser(description='Check one channel in StationXML to see if same as NRL.')
  parser.add_argument('-s', '--stationxml', required=True, help="input FDSN StationXML file, often retrieved from http://service.iris.edu/fdsnws/station/1/")
  parser.add_argument('-c', '--channel', required=True, help="channel code to compare")
  parser.add_argument('--nrl', help="replace matching responses with links to NRL")
  parser.add_argument('--sensordir', help="Sensor manufacturor subdir of NRL, to limit number of files parsed.")
  parser.add_argument('--loggerdir', help="Logger manufacturor subdir of NRL, to limit number of files parsed.")
  parser.add_argument('-o', '--outfile', nargs='?', type=argparse.FileType('w'), default=sys.stdout)
  parser.add_argument('-v', '--verbose', action='store_true', help="verbose output")
  return parser.parse_args()

def main():
    global VERBOSE
    parseArgs = initArgParser()

    if parseArgs.verbose:
        VERBOSE=True

    if not parseArgs.stationxml:
        return

    if not os.path.exists(parseArgs.stationxml):
        print("ERROR: can't fine stationxml file %s"%(parseArgs.stationxml,))
        return

    # validate with SIS validator
    # http://maui.gps.caltech.edu/SIStrac/wiki/SIS/Code
    if not xerces_validate(parseArgs.stationxml):
        return

    # Parse an xml file
    staxml = sisxmlparser.parse(parseArgs.stationxml)


    '''
    if parseArgs.list:
      print "--all channels--"
      for n in staxml.Network:
        for s in n.Station:
          for c in s.Channel:
            cCode = checkNRL.getChanCodeId(n,s,c)
            print cCode
      return
    '''

    chanCode = None
    for n in staxml.Network:
      for s in n.Station:
        for c in s.Channel:
          cCode = checkNRL.getChanCodeId(n,s,c)
          if cCode == parseArgs.channel:
              chanA = c

    if parseArgs.sensordir:
        nrlSubdir = "%s/sensors/%s"%(parseArgs.nrl, parseArgs.sensordir)
        if VERBOSE: print("walk %s"%(nrlSubdir,))
        for root, dirs, files in os.walk(nrlSubdir):
          if '.svn' in dirs:
            dirs.remove('.svn')
          for respfile in files:
            if respfile.startswith("RESP"):
                if VERBOSE: print("try %s"%(respfile,))
                r = checkNRL.loadResp(os.path.join(root, respfile))
                result = checkNRL.areSimilarSensor(c.Response, r)
                if result[0]:
                    print("MATCH %s match %s"%(chanCode, respfile,))
                else:
                    print("FAIL %s match %s: %s"%(chanCode, respfile, result[1]))


    if parseArgs.loggerdir:
        nrlSubdir = "%s/dataloggers/%s"%(parseArgs.nrl, parseArgs.loggerdir)
        if VERBOSE: print("walk %s"%(nrlSubdir,))
        for root, dirs, files in os.walk(nrlSubdir):
          if '.svn' in dirs:
            dirs.remove('.svn')
          for respfile in files:
            if respfile.startswith("RESP"):
                if VERBOSE: print("try %s"%(respfile,))
                r = checkNRL.loadResp(os.path.join(root, respfile))
                result = checkNRL.areSimilarLogger(c.Response, r)
                if result[0]:
                    print("MATCH %s match %s"%(chanCode, respfile,))
                else:
                    print("FAIL %s match %s: %s"%(chanCode, respfile, result[1]))

if __name__ == "__main__":
    sys.exit(main())
