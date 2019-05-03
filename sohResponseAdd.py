#! /usr/bin/python
'''
clean unit names in fdsn stationxml file
see https://github.com/iris-edu/StationXML-Validator/wiki/Unit-name-overview-for-IRIS-StationXML-validator
'''
import checkNRL as checkNRL
import sisxmlparser2_2_py3 as sisxmlparser

import argparse
import datetime
import os
import re
import sys

VERBOSE=False

def makeUnityResponse(c, chanCode, changes, inputunits='count'):
    if not hasattr(c, 'Response'):
        c.Response = sisxmlparser.ResponseType()
    resp = c.Response
    if hasattr(resp, 'InstrumentPolynomial'):
        if not hasattr(resp, 'Stage'):
            changes[chanCode] = "WARN: InstrumentPolynomial but no Stage"
    else:
        if not hasattr(resp, 'InstrumentSensitivity'):
            resp.InstrumentSensitivity = sisxmlparser.SensitivityType()

        if not hasattr(resp.InstrumentSensitivity, 'Value'):
            resp.InstrumentSensitivity.Value = 1.0
        if not hasattr(resp.InstrumentSensitivity, 'Frequency'):
            resp.InstrumentSensitivity.Frequency = 0.0
        if not hasattr(resp.InstrumentSensitivity, 'InputUnits'):
            resp.InstrumentSensitivity.InputUnits = sisxmlparser.UnitsType()
            resp.InstrumentSensitivity.InputUnits.Name = inputunits
        else:
            inputunits = resp.InstrumentSensitivity.InputUnits.Name
        if not hasattr(resp.InstrumentSensitivity, 'OutputUnits'):
            resp.InstrumentSensitivity.OutputUnits = sisxmlparser.UnitsType()
            resp.InstrumentSensitivity.OutputUnits.Name = 'count'
        if not hasattr(resp, 'Stage'):
            resp.Stage = [ sisxmlparser.ResponseStageType() ]
            resp.Stage[0].number = 1
            resp.Stage[0].Coefficients = sisxmlparser.CoefficientsType()
            resp.Stage[0].Coefficients.InputUnits = sisxmlparser.UnitsType()
            resp.Stage[0].Coefficients.InputUnits.Name = inputunits
            resp.Stage[0].Coefficients.OutputUnits = sisxmlparser.UnitsType()
            resp.Stage[0].Coefficients.OutputUnits.Name = 'count'
            resp.Stage[0].Coefficients.CfTransferFunctionType = 'DIGITAL'
            resp.Stage[0].Decimation = sisxmlparser.DecimationType()
            resp.Stage[0].Decimation.InputSampleRate = c.SampleRate
            resp.Stage[0].Decimation.Factor = 1
            resp.Stage[0].Decimation.Offset = 0
            resp.Stage[0].Decimation.Delay = 0.0
            resp.Stage[0].Decimation.Correction = 0.0
            resp.Stage[0].StageGain = sisxmlparser.GainType()
            resp.Stage[0].StageGain.Value = 1.0
            resp.Stage[0].StageGain.Frequency = 0.0
            changes['numChanges'] += 1
            changes[chanCode] = "unity Stage"


def addSohResponse(staxml):
    changes = { 'numChanges': 0 }
    for n in staxml.Network:
      for s in n.Station:
        for c in s.Channel:
          chanCode = checkNRL.getChanCodeId(n, s, c)
          if VERBOSE: print("soh response chanCode %s "%(chanCode, ))
          makeUnityResponse(c, chanCode, changes)
    return changes


def initArgParser():
  parser = argparse.ArgumentParser(description='Add dummy responses for SOH channels in StationXML.')
  parser.add_argument('-s', '--stationxml', required=True, help="input FDSN StationXML file, often retrieved from http://service.iris.edu/fdsnws/station/1/")
  parser.add_argument('-o', '--outfile', nargs='?', type=argparse.FileType('w'), default=sys.stdout)
  parser.add_argument('-v', '--verbose', action='store_true', help="verbose output")
  return parser.parse_args()

def usage():
    print("python sohResponseAdd <staxml>")


def main():
    VERBOSE=False
    parseArgs = initArgParser()
    if parseArgs.verbose:
        VERBOSE=True
        for k, v in vars(parseArgs).items():
            print("    Args: %s %s"%(k, v))
    if parseArgs.stationxml:
        if not os.path.exists(parseArgs.stationxml):
            print("ERROR: can't fine stationxml file %s"%(parseArgs.stationxml,))
            return
    staxml = sisxmlparser.parse(parseArgs.stationxml)
    changes = addSohResponse(staxml)
    print("ok (%d changes)"%(changes['numChanges'],))
    if VERBOSE:
        for k, v in changes.items():
            if k != 'numChanges':
                print("    %s => %s"%(k, v))
    staxml.exportxml(parseArgs.outfile, 'FDSNStationXML', 'fsx', 0)

if __name__ == '__main__':
    main()
