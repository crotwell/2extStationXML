#! /usr/bin/python
'''
clean unit names in fdsn stationxml file
see https://github.com/iris-edu/StationXML-Validator/wiki/Unit-name-overview-for-IRIS-StationXML-validator
'''
import checkNRL as checkNRL
import sisxmlparser2_0 as sisxmlparser

import argparse
import datetime
import os
import re
import sys

VERBOSE=False

KNOWN_UNITS = [ "meter", "m", "m/s", "m/s**2",
"centimeter", "cm", "cm/s", "cm/s**2",
"millimeter", "mm", "mm/s", "mm/s**2", "mm/hour",
"micrometer", "um", "um/s", "um/s**2",
"nanometer", "nm", "nm/s", "nm/s**2",
"second", "s", "millisecond", "ms", "microsecond", "us", "nanosecond", "ns",
"minute", "min",
"hour",
"radian", "rad", "microradian", "urad", "nanoradian", "nrad",
"rad/s", "rad/s**2",
"degree", "deg",
"kelvin", "K",
"celsius", "degC",
"candela", "cd",
"pascal", "Pa", "kilopascal", "kPa", "hectopascal", "hPa",
"bar", "millibar", "mbar",
"ampere", "A", "milliamp", "mA",
"volt", "V", "millivolt", "mV", "microvolt", "uV",
"ohm",
"hertz", "Hz",
"newton", "N",
"joule", "J",
"tesla", "T", "nanotesla", "nT",
"strain", "m/m", "m**3/m**3", "cm/cm", "mm/mm", "um/um", "nm/nm", "microstrain",
"watt", "W", "milliwatt", "mW",
"V/m",
"W/m**2",
"gap",
"reboot",
"byte","bit",
"bit/s",
"percent","%",
"count","counts",
"number",
"unitless" ]


#UNITS_WITH_CAPS = set([ "K","Pa","kPa","hPa","A","mA","V","mV","uV","Hz","N","J","T","nT","W","mW","V/m","W/m**2", "degC"])
def hasCap(s): return s != s.lower()

UNITS_WITH_CAPS = set(filter(hasCap, KNOWN_UNITS))

KNOWN_UNIT_SET = set(KNOWN_UNITS)


def setVerbose(b):
    VERBOSE = b

def initArgParser():
  parser = argparse.ArgumentParser(description='Clean Unit Names in StationXML or ExtendedStationXML.')
  parser.add_argument('-s', '--stationxml', required=True, help="input FDSN StationXML file, often retrieved from http://service.iris.edu/fdsnws/station/1/")
  parser.add_argument('-o', '--outfile', nargs='?', type=argparse.FileType('w'), default=sys.stdout)
  parser.add_argument('-v', '--verbose', action='store_true', help="verbose output")
  return parser.parse_args()

def cleanUnitName(inUnitName, changes):
    if inUnitName in UNITS_WITH_CAPS:
        unit = inUnitName
    else:
        unit = inUnitName.lower()
    outUnitName = unit
# not sure if I really want to fix these...
#    if (unit == 'degC'): outUnitName = 'celsius'
#    if (unit == 'count' or unit == 'counts'): outUnitName = 'count'
    if inUnitName != outUnitName: 
      changes['numChanges']+=1
      changes[inUnitName] = outUnitName
      if VERBOSE: print "change %s to %s"%(inUnitName, outUnitName)
    if (not unit in KNOWN_UNIT_SET):
      print "WARNING: unknown unit: %s"%(inUnitName,)
    return outUnitName

def cleanUnit(inUnit, changes):
    inUnit.Name = cleanUnitName(inUnit.Name, changes)
    

def cleanBaseFilter(filter, changes):
    cleanUnit(filter.InputUnits, changes)
    cleanUnit(filter.OutputUnits, changes)
    return True, "ok"

def cleanPolesZeros(pz, changes):
    cleanBaseFilter(pz, changes)
    return True, "ok"

def cleanCoefficients(coef, changes):
    cleanBaseFilter(coef, changes)
    return True, "ok"
 
    
def cleanFIR(fir, changes):
    cleanBaseFilter(fir, changes)
    return True, "ok"

def cleanPolynomial(polynomial, changes):
    cleanBaseFilter(polynomial, changes)
    return True, "ok"


def cleanDecimation(decimation, changes):
    return True, "ok"

def cleanGain(gain, changes):
    if hasattr(gain, 'InputUnits'):
      cleanUnit(gain.InputUnits, changes)
    if hasattr(gain, 'OutputUnits'):
      cleanUnit(gain.OutputUnits, changes)

    

def cleanStage(stage, changes):
    if hasattr(stage, 'PolesZeros'):
        cleanPolesZeros(stage.PolesZeros, changes)
    elif hasattr(stage, 'Coefficients'):
        cleanCoefficients(stage.Coefficients, changes)
    elif hasattr(stage, 'FIR'):
        cleanFIR(stage.FIR, changes)
    elif hasattr(stage, 'Polynomial'):
        cleanPolynomial(stage.Polynomial, changes)
    if hasattr(stage, 'Decimation'):
        cleanDecimation(stage.Decimation, changes)
    if hasattr(stage, 'StageGain'):
        cleanGain(stage.StageGain, changes)
    

def cleanResponse(resp, changes):
    if hasattr(resp, 'InstrumentSensitivity'):
      cleanUnit(resp.InstrumentSensitivity.InputUnits, changes)
      cleanUnit(resp.InstrumentSensitivity.OutputUnits, changes)
    if hasattr(resp, 'SubResponse') and hasattr(resp.SubResponse, 'ResponseDetail'):
      cleanStage(resp.SubResponse.ResponseDetail, changes)
    if hasattr(resp, 'Stage'):
        stage = getattr(resp, 'Stage', [])
        for i in range(0, len(stage)):
            cleanStage(resp.Stage[i], changes)
    return True, "ok"

def cleanUnitNames(staxml):
    changes = { 'numChanges': 0 }
    for n in staxml.Network:
      for s in n.Station:
        for c in s.Channel:
          chanCode = checkNRL.getChanCodeId(n, s, c)
          if VERBOSE: print "clean chanCode %s "%(chanCode, )
          if hasattr(c, 'SignalUnits'):
              cleanUnit(c.SignalUnits, changes)
          if hasattr(c, 'CalibrationUnits'):
              cleanUnit(c.CalibrationUnits, changes)
          result = cleanResponse(c.Response, changes)
    if hasattr(staxml, 'HardwareResponse'):
      
      if hasattr(staxml.HardwareResponse, 'ResponseDictGroup'):
        respDict = getattr(staxml.HardwareResponse.ResponseDictGroup, 'ResponseDict', [])
        for i in range(0, len(respDict)):
            cleanStage(respDict[i], changes)
            if hasattr(respDict[i], 'FilterSequence'):
              filterStage = getattr(respDict[i].FilterSequence, 'FilterStage', [])
              for i in range(0, len(filterStage)):
                 cleanStage(filterStage[i], changes)
    return changes

def usage():
    print "python cleanUnitNames <staxml>"


def main():
    VERBOSE=False
    parseArgs = initArgParser()
    if parseArgs.verbose:
        VERBOSE=True
        for k, v in vars(parseArgs).iteritems():
            print "    Args: %s %s"%(k, v)
    if parseArgs.stationxml:
        if not os.path.exists(parseArgs.stationxml):
            print "ERROR: can't fine stationxml file %s"%(parseArgs.stationxml,)
            return
    staxml = sisxmlparser.parse(parseArgs.stationxml)
    print "Clean unit names"
    changes = cleanUnitNames(staxml)
    print "ok (%d changes)"%(changes['numChanges'],)
    if VERBOSE:
        for k, v in changes.iteritems():
            if k != 'numChanges':
                print "    %s => %s"%(k, v)
    staxml.exportxml(parseArgs.outfile, 'FDSNStationXML', 'fsx', 0)

if __name__ == '__main__':
    main()

