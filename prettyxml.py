#!/usr/local/bin/python

import os
import sys
import xml.dom.minidom

if (len(sys.argv) == 1):
    print("prettyxml.py <xmlfile>")
    sys.exit(1)

if os.path.exists(sys.argv[1]):
    F = open(sys.argv[1], 'r')
    xml = xml.dom.minidom.parse(F)
    print(xml.toprettyxml(indent="    "))
else:
    print("unable to open file '%s'"%(sys.argv[1],))


