#! /usr/bin/python
'''
add soh response in fdsn stationxml file
'''
import checkNRL as checkNRL
import sisxmlparser2_2_py3 as sisxmlparser

import argparse
import datetime
import os
import re
import sys

VERBOSE=False

COUNT_UNIT = sisxmlparser.UnitsType()
COUNT_UNIT.Name = 'count'

def calcInputUnits(c):
    """gets input units for a response, checking InstrumentSensitivity,
    InstrumentPolynomial and the first Stage"""
    units = None
    if hasattr(c, 'Response'):
        resp = c.Response
        if hasattr(resp, 'InstrumentPolynomial'):
            units = resp.InstrumentPolynomial.InputUnits
        elif hasattr(resp, 'InstrumentSensitivity'):
            units = resp.InstrumentSensitivity.InputUnits
        elif hasattr(resp, 'Stage') and len(resp.Stage) > 0:
            stage = resp.Stage[0]
            if hasattr(stage, 'PolesZeros'):
                units = stage.PolesZeros.InputUnits
            elif hasattr(stage, 'Coefficients'):
                units = stage.Coefficients.InputUnits
            elif hasattr(stage, 'ResponseList'):
                units = stage.ResponseList.InputUnits
            elif hasattr(stage, 'FIR'):
                units = stage.FIR.InputUnits
            elif hasattr(stage, 'Polynomial'):
                units = stage.Polynomial.InputUnits
    return units

def makeUnityResponse(c, chanCode, changes, inUnitsDict):
    inputunits = calcInputUnits(c)
    if inputunits is None and c.code in list(inUnitsDict):
        inputunits = sisxmlparser.UnitsType()
        inputunits.Name = inUnitsDict[c.code]

    if inputunits is None:
        if VERBOSE: print("skip chanCode %s, no units in response or units file"%(chanCode, ))
        changes[chanCode] = "WARN: No input units"
        return

    if not hasattr(c, 'Response'):
        c.Response = sisxmlparser.ResponseType()
    resp = c.Response
    if hasattr(resp, 'InstrumentPolynomial'):
        if not hasattr(resp, 'Stage'):
            resp.Stage = [ sisxmlparser.ResponseStageType() ]
            resp.Stage[0].number = 1
            resp.Stage[0].Polynomial = resp.InstrumentPolynomial
            changes['numChanges'] += 1
            changes[chanCode] = "copy InstPolynomial to Stage"
    else:
        if not hasattr(resp, 'InstrumentSensitivity') and hasattr(resp, 'Stage'):
            if len(resp.Stage) == 1 and hasattr(resp.Stage[0], 'Polynomial'):
                if len(resp.Stage[0].Polynomial.Coefficient) and resp.Stage[0].Polynomial.Coefficient[0] == 0:
                    # linear polynomial with no DC, can create sensitivity
                    resp.InstrumentSensitivity = sisxmlparser.SensitivityType()
                    resp.InstrumentSensitivity.Value = 1.0/resp.Stage[0].Polynomial.Coefficient[1]
                    resp.InstrumentSensitivity.InputUnits = inputunits
                    resp.InstrumentSensitivity.OutputUnits = resp.Stage[0].Polynomial.OutputUnits
                    changes['numChanges'] += 1
                    changes[chanCode] = "sensitivity from polynomial stage"
                else:
                    # nonlinear, copy to InstPolynomial
                    resp.InstrumentPolynomial = resp.Stage[0].Polynomial
                    changes['numChanges'] += 1
                    changes[chanCode] = "inst polynomial from polynomial stage"
        else:
            if not hasattr(resp, 'InstrumentSensitivity'):
                resp.InstrumentSensitivity = sisxmlparser.SensitivityType()

            if not hasattr(resp.InstrumentSensitivity, 'Value'):
                resp.InstrumentSensitivity.Value = 1.0
            if not hasattr(resp.InstrumentSensitivity, 'Frequency'):
                resp.InstrumentSensitivity.Frequency = 0.0
            if not hasattr(resp.InstrumentSensitivity, 'InputUnits'):
                resp.InstrumentSensitivity.InputUnits = inputunits
            if not hasattr(resp.InstrumentSensitivity, 'OutputUnits'):
                resp.InstrumentSensitivity.OutputUnits = COUNT_UNIT
            if not hasattr(resp, 'Stage'):
                resp.Stage = [ sisxmlparser.ResponseStageType() ]
                resp.Stage[0].number = 1
                resp.Stage[0].Coefficients = sisxmlparser.CoefficientsType()
                resp.Stage[0].Coefficients.InputUnits = inputunits
                resp.Stage[0].Coefficients.OutputUnits = sisxmlparser.UnitsType()
                resp.Stage[0].Coefficients.OutputUnits = COUNT_UNIT
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


def addSohResponse(staxml, inunitsDict):
    changes = { 'numChanges': 0 }
    for n in staxml.Network:
      for s in n.Station:
        for c in s.Channel:
          chanCode = checkNRL.getChanCodeId(n, s, c)
          if VERBOSE: print("soh response chanCode %s "%(chanCode, ))
          makeUnityResponse(c, chanCode, changes, inunitsDict)
    return changes

def parseUnitsFile(unitsFile):
    out = dict()
    for line in unitsFile:
      words = line.split()
      chans = words[0].split(',')
      for c in chans:
          out[c] = words[1]
    return out

def initArgParser():
  parser = argparse.ArgumentParser(description='Add dummy responses for SOH channels in StationXML.')
  parser.add_argument('-s', '--stationxml', required=True, help="input FDSN StationXML file, often retrieved from http://service.iris.edu/fdsnws/station/1/")
  parser.add_argument('-u', '--units', type=argparse.FileType('r'), help="channel input units file, lines like 'VMU,VMV,VMW volt'")
  parser.add_argument('-o', '--outfile', nargs='?', type=argparse.FileType('w'), default=sys.stdout)
  parser.add_argument('-v', '--verbose', action='store_true', help="verbose output")
  return parser.parse_args()

def usage():
    print("python sohResponseAdd <staxml>")


def main():
    VERBOSE=False
    inunits = {}
    parseArgs = initArgParser()
    if parseArgs.verbose:
        VERBOSE=True
        for k, v in vars(parseArgs).items():
            print("    Args: %s %s"%(k, v))
    if parseArgs.stationxml:
        if not os.path.exists(parseArgs.stationxml):
            print("ERROR: can't fine stationxml file %s"%(parseArgs.stationxml,))
            return

    if parseArgs.units:
        inunits = parseUnitsFile(parseArgs.units)

    staxml = sisxmlparser.parse(parseArgs.stationxml)
    changes = addSohResponse(staxml, inunits)
    print("ok (%d changes)"%(changes['numChanges'],))
    if VERBOSE:
        for k, v in changes.items():
            if k != 'numChanges':
                print("    %s => %s"%(k, v))
    staxml.exportxml(parseArgs.outfile, 'FDSNStationXML', 'fsx', 0)

if __name__ == '__main__':
    main()
