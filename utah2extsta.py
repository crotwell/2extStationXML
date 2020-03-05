#! /usr/bin/python
'''
use the classes in sisxmlparser2_2 to generate an ExtStationXML file from
Utah's response data files.
'''
import sta2extsta as sta2extsta
import checkNRL as checkNRL
import sisxmlparser2_2_py3 as sisxmlparser
import uniqResponses as uniqResponses
import cleanUnitNames as cleanUnitNames
from xerces_validate import xerces_validate, SCHEMA_FILE

import argparse
import copy
import datetime
import dateutil.parser
import os
import re
import subprocess
import sys

VERBOSE = False
#VERBOSE = True

USAGE_TEXT = """
Usage: python <Parser>.py <in_resp_dir>
"""

NRL_PREFIX = "http://ds.iris.edu/NRL"

def usage():
    print(USAGE_TEXT)
    sys.exit(1)


def initArgParser():
    parser = argparse.ArgumentParser(description='Convert Utah Resp dir to ExtendedStationXML.')
    parser.add_argument('-s', '--stationxml', required=True, help="input FDSN StationXML file, often retrieved from http://service.iris.edu/fdsnws/station/1/")
    parser.add_argument('-d', '--dir', required=True, help="input directory with Utah resp files")
    parser.add_argument('--nrl', default='nrl', help="replace matching responses with links to NRL")
    parser.add_argument('--namespace', default='Testing', help="SIS namespace to use for named responses, see http://anss-sis.scsn.org/sis/master/namespace/")
    parser.add_argument('--operator', default='Testing', help="SIS operator to use for stations, see http://anss-sis.scsn.org/sis/master/org/")
    parser.add_argument('--delcurrent', action="store_true", help="remove channels that are currently operating. Only do this if you want to go back and manually via the web interface add hardware for current epochs.")
    parser.add_argument('--onlychan', default=False, help="only channels with codes matching regular expression, ie BH. for all broadband. Can also match locid like '00\.HH.' Empty loc ids for filtering as '--'")
    parser.add_argument('-o', '--outfile', nargs='?', type=argparse.FileType('w'), default=sys.stdout)
    parser.add_argument('-v', '--verbose', action='store_true', help="verbose output")
    return parser.parse_args()

def loadUtahResp(dir, station, channel):
    out = []
    for dirpath, dnames, fnames in os.walk(dir):
        for f in fnames:
            if f.startswith("{}.{}".format(station.code.lower(), channel.code.lower())) \
            and channel.startDate.strftime(".s%Y%m%d") in f:
                respDict = {}
                respDict['filename'] = f
                out.append(respDict)
                with open(os.path.join(dirpath, f)) as infile:
                    readingZeros = False
                    readingPoles = False
                    for line in infile:
                        split = line.split()
                        if line.startswith('*'):
                            respDict[split[1]] = split[2:]
                        else:
                            if line.startswith('ZEROS'):
                                readingZeros = True
                                respDict['ZEROS'] = []
                                numZeros = int(split[1])
                            elif line.startswith('POLES'):
                                readingZeros = False
                                extraZeros = numZeros-len(respDict['ZEROS'])
                                for i in range(extraZeros):
                                    respDict['ZEROS'].append(['0.0','0.0'])
                                readingPoles = True
                                respDict['POLES'] = []
                                numPoles = int(split[1])
                            elif line.startswith('CONSTANT'):
                                readingZeros = False
                                readingPoles = False
                                respDict['CONSTANT'] = float(split[1])
                            elif readingZeros:
                                respDict['ZEROS'].append(split)
                            elif readingPoles:
                                respDict['POLES'].append(split)
                #print(respDict)
    return out

def subtractZero(utahResp):
    try:
        if len(utahResp['ZEROS']) == 0:
            print(utahResp)
            raise Exception("len zeros is 0")
        if float(utahResp['ZEROS'][0][0]) != 0.0 or float(utahResp['ZEROS'][0][1]) != 0.0 :
            raise Exception("first zero is not 0 0")
        out = copy.deepcopy(utahResp)
        out['ZEROS'] = out['ZEROS'][1:]
    except Exception as e:
        print("{}  {}".format(e, utahResp))
        raise e
    return out

def findSensors(nrlDir, utahResp):
    out = []
    sensorLine = utahResp['Seismometer']
    manuf = sensorLine[0]
    if manuf == 'Trillium':
        manuf = 'nanometrics'
    # nrl sorts poles/zeros by positive imag first, then neg imaginary
    for idx in range(len(utahResp['ZEROS'])-1):
        if utahResp['ZEROS'][idx][0] == utahResp['ZEROS'][idx+1][0] \
        and utahResp['ZEROS'][idx][1] == "-{}".format(utahResp['ZEROS'][idx+1][1]):
            tmp = utahResp['ZEROS'][idx]
            utahResp['ZEROS'][idx] = utahResp['ZEROS'][idx+1]
            utahResp['ZEROS'][idx+1] = tmp

    for idx in range(len(utahResp['POLES'])-1):
        if utahResp['POLES'][idx][0] == utahResp['POLES'][idx+1][0] \
        and utahResp['POLES'][idx][1] == "-{}".format(utahResp['POLES'][idx+1][1]):
            tmp = utahResp['POLES'][idx]
            utahResp['POLES'][idx] = utahResp['POLES'][idx+1]
            utahResp['POLES'][idx+1] = tmp

    velUtahResp = subtractZero(utahResp)
    accUtahResp = subtractZero(velUtahResp)
    if VERBOSE: print("walk {} for sensor {} {}".format(nrlDir,sensorLine[0], sensorLine[1]))
    for root, dirs, files in os.walk("{}/sensors/{}/".format(nrlDir,manuf.lower())):
      if '.svn' in dirs:
        dirs.remove('.svn')
      for respfile in files:
        if respfile.startswith("RESP"):
            if VERBOSE: print("try {}".format(respfile))
            nrlResp = checkNRL.loadResp(os.path.join(root, respfile))
            b53 = checkNRL.findRespBlockette(nrlResp, 1, '053')
            if b53 is not None:
                accResult = checkNRL.checkMultiple( [
                  ("num zeros", len(accUtahResp['ZEROS']), int(b53['09'])),
                  ("num poles", len(accUtahResp['POLES']), int(b53['14']))
                  #("A0 norm factor", utahResp['CONSTANT'], float(b53['07']), 0.001)
                ])
                if accResult[0]:
                    checklist = []
                    zeros = accUtahResp['ZEROS']
                    poles = accUtahResp['POLES']
                    for zi in range(len(zeros)):
                        checklist.append(("%d zero real"%(zi,), float(zeros[zi][0]), float(b53['10-13'][zi][1]), 0.001))
                        checklist.append(("%d zero imag"%(zi,), float(zeros[zi][1]), float(b53['10-13'][zi][2]), 0.001))
                    for pi in range(len(poles)):
                        checklist.append(("%d pole real"%(pi,), float(poles[pi][0]), float(b53['15-18'][pi][1]), 0.001))
                        checklist.append(("%d pole imag"%(pi,), float(poles[pi][1]), float(b53['15-18'][pi][2]), 0.001))
                    accResult = checkNRL.checkMultiple(checklist)

                if accResult[0]:
                    out.append({'type': 'acc', 'filename': respfile, 'nrlResp': nrlResp})
                else:
                    #print(result)
                    try:
                        #print("Try sub zero {} {}: {}".format(len(utahResp['ZEROS']), len(velUtahResp['ZEROS']), velUtahResp))
                        velResult = checkNRL.checkMultiple( [
                          ("num zeros", len(velUtahResp['ZEROS']), int(b53['09'])),
                          ("num poles", len(velUtahResp['POLES']), int(b53['14']))
                          #("A0 norm factor", velUtahResp['CONSTANT'], float(b53['07']), 0.001)
                        ])
                        if int(b53['09']) != 0 and int(b53['09']) != len(b53['10-13']):
                            raise Exception('b53 has wrong number zeros: {} {}'.format(int(b53['09']), len(b53['10-13'])))
                        if velResult[0]:
                            checklist = []
                            zeros = velUtahResp['ZEROS']
                            poles = velUtahResp['POLES']
                            for zi in range(len(zeros)):
                                checklist.append(("%d zero real"%(zi,), float(zeros[zi][0]), float(b53['10-13'][zi][1]), 0.001))
                                checklist.append(("%d zero imag"%(zi,), float(zeros[zi][1]), float(b53['10-13'][zi][2]), 0.001))
                            for pi in range(len(poles)):
                                checklist.append(("%d pole real"%(pi,), float(poles[pi][0]), float(b53['15-18'][pi][1]), 0.001))
                                checklist.append(("%d pole imag"%(pi,), float(poles[pi][1]), float(b53['15-18'][pi][2]), 0.001))
                            velResult = checkNRL.checkMultiple(checklist)

                        if velResult[0]:
                            out.append({'type':'vel', 'filename': respfile, 'nrlResp': nrlResp})
                        else:
                            #print(velResult)
                            pass
                    except Exception as e:
                        print("Skip subtractZero for {}, {}".format(utahResp['filename'], e))
                        raise e

    return out

def main():
    global VERBOSE
    sisNamespace = "TESTING"
    parseArgs = initArgParser()
    print("in main")
    if parseArgs.verbose:
        VERBOSE=True
        for k, v in vars(parseArgs).items():
            print("    Args: %s %s"%(k, v))


    if parseArgs.stationxml:
        if not xerces_validate(parseArgs.stationxml):
            return

        # Parse an xml file
        rootobj = sisxmlparser.parse(parseArgs.stationxml)
        if hasattr(rootobj, 'comments'):
            origModuleURI = rootobj.ModuleURI
        else:
            origModuleURI = ""

        rootobj.schemaVersion='1.0',
        rootobj.Source=parseArgs.namespace
        rootobj.Sender=parseArgs.namespace
        rootobj.Module='sta2extsta.py',
        rootobj.ModuleURI='https://github.com/crotwell/2extStationXML',
        rootobj.Created=datetime.datetime.now()

        if not hasattr(rootobj, 'comments'):
            rootobj.comments = []
        rootobj.comments.append("From: "+origModuleURI)

        # del non-matching channels
        if parseArgs.onlychan:
            pattern = re.compile(parseArgs.onlychan)
            for n in rootobj.Network:
                for s in n.Station:
                    tempChan = []
                    for c in s.Channel:
                        locid = c.locationCode
                        if locid is None or len(locid) == 0:
                            locid = "--"
                        if pattern.match(c.code):
                            tempChan.append(c)
                        elif pattern.match("%s.%s"%(locid, c.code)):
                            tempChan.append(c)
                        else:
                            if VERBOSE:
                                print("Skip %s as doesn't match --onlychan"%(checkNRL.getChanCodeId(n, s, c),))
                    s.Channel = tempChan

        # sample rate index for loggers
        spsIndex = os.path.join(parseArgs.nrl, "logger_sample_rate.sort")
        if not os.path.exists(spsIndex):
            print("ERROR: can't fine sps index file for NRL. Should be logger_sample_rate.sort inside NRL directory")
            print("python checkNRL.py --samplerate --nrl <path_to_nrl>")
            return
        loggerRateIndex = checkNRL.loadRespfileSampleRate(spsIndex)

        for n in rootobj.Network:
            for s in n.Station:
                tempChan = []
                for c in s.Channel:
                    utah = loadUtahResp(parseArgs.dir, s, c)
                    if len(utah) == 0:
                        print("No Utah resp files found for {}.{} {}".format(s.code, c.code, c.startDate))
                    for u in utah:
                        print("Try: {} {}".format(u['filename'], u['Seismometer']))
                        possibleSensors = findSensors(parseArgs.nrl, u)
                        if len(possibleSensors) == 0:
                            print("No possible NRL sensors found for {} {}".format(checkNRL.getChanCodeId(n, s, c), len(possibleSensors)))
                        for p in possibleSensors:
                            print("Found possible match: {} {} => {}".format(u['filename'], u['Seismometer'], p['filename']))


if __name__ == "__main__":
    sys.exit(main())
