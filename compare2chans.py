#! /usr/bin/python
'''
find unique responses in fdsn stationxml file
'''
import checkNRL as checkNRL
import sisxmlparser2_0 as sisxmlparser
import uniqResponses as uniqResponses

import datetime
import os
import re
import sys


def usage():
    print "python compare2chans <file.staxml> <chanAId> <chanBId>"
    print "python compare2chans <file.staxml> --list"


def main():
    checkNRL.setVerbose(True)
    args = sys.argv[1:]
    if len(args) == 0:
        usage()
        return
    if not os.path.isfile(args[0]):
        print "Can't find file %s"%(args[0],)
        return
    staxml = sisxmlparser.parse(args[0])
    if args[1] == '--list':
      print "--all channels--"
      for n in staxml.Network:
        for s in n.Station:
          for c in s.Channel:
            cCode = checkNRL.getChanCodeId(n,s,c)
            print cCode
    return

    chanA = None
    chanB = None
    for n in staxml.Network:
      for s in n.Station:
        for c in s.Channel:
          cCode = checkNRL.getChanCodeId(n,s,c)
          if cCode == args[1]:
              chanA = c
          if cCode == args[2]:
              chanB = c
    if chanA is None or chanB is None:
        print "did not find channels: %s %s %s %s"%(chanA, chanB, args[1], args[2])
        return

    result = uniqResponses.areSameResponse(chanA.Response, chanB.Response)
    print result
 


if __name__ == '__main__':
    main()


