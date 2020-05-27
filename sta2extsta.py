#! /usr/bin/python
'''
use the classes in sisxmlparser2_2 to generate an ExtStationXML file from regular stationxml.
'''
import checkNRL as checkNRL
import sisxmlparser3_0 as sisxmlparser
import uniqResponses as uniqResponses
import cleanUnitNames as cleanUnitNames
from xerces_validate import xerces_validate, SCHEMA_FILE

import argparse
import datetime
import dateutil.parser
import os
import re
import subprocess
import sys

VERBOSE = False
#VERBOSE = True

USAGE_TEXT = """
Usage: python <Parser>.py <in_xml_file>
"""

NRL_PREFIX = "http://ds.iris.edu/NRL"


def usage():
    initArgParser()

    sys.exit(1)

def getStartDate(channel):
  return channel.startDate

def initArgParser():
  parser = argparse.ArgumentParser(description='Convert StationXML to ExtendedStationXML.')
  parser.add_argument('-s', '--stationxml', required=True, help="input FDSN StationXML file, often retrieved from http://service.iris.edu/fdsnws/station/1/")
  parser.add_argument('--nrl', default='nrl', help="replace matching responses with links to NRL")
  parser.add_argument('--namespace', default='Testing', help="SIS namespace to use for named responses, see http://anss-sis.scsn.org/sis/master/namespace/")
  parser.add_argument('--operator', default='Testing', help="SIS operator to use for stations, see http://anss-sis.scsn.org/sis/master/org/")
  parser.add_argument('--delcurrent', action="store_true", help="remove channels that are currently operating. Only do this if you want to go back and manually via the web interface add hardware for current epochs.")
  parser.add_argument('--onlychan', default=False, help="only channels with codes matching regular expression, ie BH. for all broadband. Can also match locid like '00\.HH.' Empty loc ids for filtering as '--'")
  parser.add_argument('-o', '--outfile', nargs='?', type=argparse.FileType('w'), default=sys.stdout)
  parser.add_argument('-v', '--verbose', action='store_true', help="verbose output")
  parser.add_argument('--ignorewarning', action='store_true', default=False)
  return parser.parse_args()

def convertToResponseDict(fdsnResponse):
    respDict = sisxmlparser.ResponseDict()
    respDict.FilterSequence = sisxmlparser.FilterSequenceType()

def isSimpleSOHSingleStage(namedResponse):
    if len(namedResponse.Stage) > 1:
        return False
    stage = namedResponse.Stage[0]
    if hasattr(stage, 'Coefficients') and hasattr(stage, 'Decimation'):
       if hasattr(stage.Coefficients, 'InputUnits') and \
           hasattr(stage.Coefficients, 'OutputUnits') and \
           (stage.Coefficients.OutputUnits.Name == 'count' or stage.Coefficients.OutputUnits.Name == 'counts'):
           return True
    #print "Coeff: %s  Dec:%s  In:%s  Out: %s"%(hasattr(stage, 'Coefficients'), hasattr(stage, 'Decimation'), stage.Coefficients.InputUnits.Name, stage.Coefficients.OutputUnits.Name)
    return False

def isAtoDStage(namedResponse, sNum):
    for stage in namedResponse.Stage:
       if stage.number == sNum:
           break
    reason = ""
    if not hasattr(stage, 'Coefficients'):
        reason = "Stage {}={} does not have Coefficients".format(sNum, stage.number)
    elif hasattr(stage.Coefficients, 'Denominator'):
        reason = "Stage {}={} has Coefficients with Denominator".format(sNum, stage.number)
    elif hasattr(stage.Coefficients, 'Numerator'):
        reason = "Stage {}={} has Coefficients with Numerator".format(sNum, stage.number)
    elif not hasattr(stage, 'Decimation'):
        reason = "Stage {}={} does not have Decimation".format(sNum, stage.number)
    elif not hasattr(stage.Coefficients, 'InputUnits'):
        reason = "Stage {}={} does not have InputUnits".format(sNum, stage.number)
    elif not hasattr(stage.Coefficients, 'OutputUnits'):
        reason = "Stage {}={} does not have OutputUnits".format(sNum, stage.number)
    elif not (stage.Coefficients.InputUnits.Name == 'V' or stage.Coefficients.InputUnits.Name == 'volt'):
        reason = "Stage {}={} InputUnits {} are not V or volt".format(sNum, stage.number, stage.Coefficients.InputUnits.Name)
    elif not (stage.Coefficients.OutputUnits.Name == 'count' or stage.Coefficients.OutputUnits.Name == 'counts'):
        reason = "Stage {}={} InputUnits {} are not V or volt".format(sNum, stage.number, stage.Coefficients.OutputUnits.Name)
    else:
        reason = ""
    return reason == "", reason

def findAtoDStage(namedResponse):
    for stage in namedResponse.Stage:
        isAtoD, isAtoDReason = isAtoDStage(namedResponse, stage.number)
        if isAtoD:
            return stage.number
    return -1

def isPreampStage(namedResponse, sNum):
    for stage in namedResponse.Stage:
       if stage.number == sNum:
           break
    reason = ""
    if isOnlyGainStage(namedResponse, sNum):
        return True, ""
    elif not hasattr(stage, 'PolesZeros'):
        reason = "Stage {}={} not gain only and does not have PolesZeros".format(sNum, stage.number)
    elif hasattr(stage, 'Decimation'):
        reason = "Stage {}={} has Decimation".format(sNum, stage.number)
    elif not hasattr(stage.PolesZeros, 'InputUnits'):
        reason = "Stage {}={} does not have InputUnits".format(sNum, stage.number)
    elif not hasattr(stage.PolesZeros, 'OutputUnits'):
        reason = "Stage {}={} does not have OutputUnits".format(sNum, stage.number)
    elif not (stage.PolesZeros.InputUnits.Name == 'V' or stage.PolesZeros.InputUnits.Name == 'volt'):
        reason = "Stage {}={} InputUnits {} are not V or volt".format(sNum, stage.number, stage.PolesZeros.InputUnits.Name)
    elif not (stage.PolesZeros.OutputUnits.Name == 'V' or stage.PolesZeros.OutputUnits.Name == 'volt'):
        reason = "Stage {}={} OutputUnits {} are not V or volt".format(sNum, stage.number, stage.PolesZeros.OutputUnits.Name)
    else:
        reason = ""
        return True, reason
    return False, reason


def findPreampStage(namedResponse):
    for stage in namedResponse.Stage:
        isPreamp, isPreampReason = isPreampStage(namedResponse, stage.number)
        if isPreamp:
            return stage.number
    return -1

def isOnlyGainStage(namedResponse, sNum):
    for stage in namedResponse.Stage:
       if stage.number == sNum:
           break
    if hasattr(stage, 'PolesZeros') or \
       hasattr(stage, 'Coefficients') or \
       hasattr(stage, 'ResponseList') or \
       hasattr(stage, 'FIR') or \
       hasattr(stage, 'Polynomial'):
        return False
    else:
        return True

def fixResponseNRL(n, s, c, oldResponse, uniqResponse, namespace):

    chanCodeId = checkNRL.getChanCodeId(n, s, c)

    if VERBOSE:
        print("fixResponseNRL: %s"%(chanCodeId,))
    if oldResponse is None:
        print("Channel has no Response: "+chanCodeId)
        return
    c.Response = sisxmlparser.SISResponseType()
    if hasattr(oldResponse, 'InstrumentSensitivity'):
        c.Response.InstrumentSensitivity = oldResponse.InstrumentSensitivity
    elif hasattr(oldResponse, 'InstrumentPolynomial'):
        c.Response.InstrumentPolynomial = toSISPolynomial(oldResponse.InstrumentPolynomial, namespace)
    else:
        # need to calculate overall sensitivity
        print("WARNING: %s does not have InstrumentSensitivity or InstrumentPolynomial, this is required in SIS."%(chanCodeId,))

    if hasattr(c, 'Sensor'):
        #sometimes equipment comment in Sensor.Type
        if hasattr(c.Sensor, 'Type'):
            if not hasattr(c, 'Comment'):
                c.Comment = []
            comment = sisxmlparser.CommentType()
            comment.Value = "Sensor.Type: "+c.Sensor.Type
            c.Comment.append(comment)
        del c.Sensor
    if not hasattr(oldResponse, 'Stage'):
        print("WARNING: %s's Response does not have any Stage elements."%(chanCodeId,))
        return

    sensorSubResponse = sisxmlparser.SubResponseType()
    sensorSubResponse.sequenceNumber = 1
    preampSubResponse = sisxmlparser.SubResponseType()
    preampSubResponse.sequenceNumber = 2
    atodSubResponse = sisxmlparser.SubResponseType()
    atodSubResponse.sequenceNumber = 3
    loggerSubResponse = sisxmlparser.SubResponseType()
    loggerSubResponse.sequenceNumber = 4
    for prototypeChan, namedResponse, chanCodeList, sss, lll in uniqResponse:
        for xcode in chanCodeList:
            if xcode == chanCodeId:
                # sensor ######
                # but SOH channels sometimes have only 1 stage, so no logger
                if len(sss) == 0:
                    if VERBOSE: print("        sensor not NRL, use named resp: %s"%(xcode,))
                    # not nrl, so use named response

                    if isSimpleSOHSingleStage(namedResponse):
                        # but SOH channels sometimes have only 1 stage, so no sensor, only atod
                        sensorSubResponse = None
                        preampSubResponse.sequenceNumber -= 1
                        atodSubResponse.sequenceNumber -= 1
                        loggerSubResponse.sequenceNumber -= 1
                    else:
                        sensorSubResponse.ResponseDictLink = sisxmlparser.ResponseDictLinkType2()
                        sensorSubResponse.ResponseDictLink.Name = "S_"+prototypeChan
                        sensorSubResponse.ResponseDictLink.SISNamespace = namespace

                        if hasattr(oldResponse.Stage[0], 'Polynomial'):
                            # polynomial doesn't use Gain
                            sensorSubResponse.ResponseDictLink.Type = 'Polynomial'
                        else:
                            if not hasattr(oldResponse.Stage[0], 'StageGain'):
                                raise Exception("         sensor has no StageGain in stage 0: {}".format(xcode))
                            sensorSubResponse.ResponseDictLink.Gain = sisxmlparser.SISGainType()
                            sensorSubResponse.ResponseDictLink.Gain.Value = oldResponse.Stage[0].StageGain.Value
                            sensorSubResponse.ResponseDictLink.Gain.Frequency = oldResponse.Stage[0].StageGain.Frequency
                            if hasattr(oldResponse.Stage[0], 'PolesZeros'):
                                sensorSubResponse.ResponseDictLink.Type = 'PolesZeros'
                                sensorSubResponse.ResponseDictLink.Gain.InputUnits = oldResponse.Stage[0].PolesZeros.InputUnits
                                sensorSubResponse.ResponseDictLink.Gain.OutputUnits = oldResponse.Stage[0].PolesZeros.OutputUnits
                            elif hasattr(oldResponse.Stage[0], 'Coefficients'):
                                if VERBOSE: print("         sensor has no PolesZeros in stage, use Coefficients: {}".format(xcode))
                                sensorSubResponse.ResponseDictLink.Type = 'Coefficients'
                                sensorSubResponse.ResponseDictLink.Gain.InputUnits = oldResponse.Stage[0].Coefficients.InputUnits
                                sensorSubResponse.ResponseDictLink.Gain.OutputUnits = oldResponse.Stage[0].Coefficients.OutputUnits
                            else:
                                if VERBOSE: print("         WARNING: sensor has no PolesZeros, Coefficients or Polynomial in stage: {}".format(xcode))


                else:
                    if len(sss) > 1:
                        print("       WARNING: %s has more than one matching sensor response in NRL, using first"%(chanCodeId,))
                    for temps in sss:
                        print("         %s"%(temps[0],))
                    if VERBOSE: print("        sensor in NRL: %s"%(xcode,))
                    sensorSubResponse.RESPFile = sisxmlparser.RESPFileType()
                    sensorSubResponse.RESPFile.ValueOf = sss[0][0].replace("nrl", NRL_PREFIX)
                    # stage To/From not required for NRL responses, use SIS rules
                    #sensorSubResponse.RESPFile.stageFrom = 1
                    #sensorSubResponse.RESPFile.stageTo = 1
                # datalogger #######
                if len(lll) == 0:
                    if VERBOSE: print("        logger not NRL, use named resp: %s"%(xcode,))
                    atodStageInOrig = 1
                    loggerStageInOrig = 2
                    # not nrl, so use named response
                    if isSimpleSOHSingleStage(namedResponse):
                        # simple 1 stage, coeff count->count stage
                        preampSubResponse = None
                        atodSubResponse.sequenceNumber = 1
                        atodStageInOrig = 1
                        loggerSubResponse = None
                        loggerStageInOrig = 999
                        atodSubResponse.ResponseDetail = sisxmlparser.SubResponseDetailType()
                        atodSubResponse.ResponseDetail.Gain = sisxmlparser.SISGainType()
                        atodOld = namedResponse.Stage[atodStageInOrig-1]
                        atodSubResponse.ResponseDetail.Gain.Value = atodOld.StageGain.Value
                        atodSubResponse.ResponseDetail.Gain.Frequency = atodOld.StageGain.Frequency
                        atodSubResponse.ResponseDetail.Gain.InputUnits = atodOld.Coefficients.InputUnits
                        atodSubResponse.ResponseDetail.Gain.OutputUnits = atodOld.Coefficients.OutputUnits
                    else:
                        preampStage = findPreampStage(namedResponse)
                        atodStageInOrig = findAtoDStage(namedResponse)
                        loggerStageInOrig = atodStageInOrig+1
                        if preampStage > 0:
                            preampSubResponse.ResponseDetail = sisxmlparser.SubResponseDetailType()
                            preampSubResponse.ResponseDetail.Gain = sisxmlparser.SISGainType()
                            preampSubResponse.ResponseDetail.Gain.Value = namedResponse.Stage[preampStage-1].StageGain.Value
                            preampSubResponse.ResponseDetail.Gain.Frequency = namedResponse.Stage[preampStage-1].StageGain.Frequency
                            preampSubResponse.ResponseDetail.Gain.InputUnits = sisxmlparser.UnitsType
                            preampSubResponse.ResponseDetail.Gain.InputUnits.Name = "None Specified"
                            preampSubResponse.ResponseDetail.Gain.OutputUnits = sisxmlparser.UnitsType
                            preampSubResponse.ResponseDetail.Gain.OutputUnits.Name = "None Specified"
                            if hasattr(namedResponse.Stage[preampStage-1], 'PolesZeros'):
                                preampSubResponse.ResponseDetail.PolesZeros = namedResponse.Stage[preampStage-1].PolesZeros
                            else:
                                # try to find input units for StageGain-only stage from prev and next stages
                                # and store in sis style Gain
                                if hasattr(namedResponse.Stage[preampStage-2], 'PolesZeros'):
                                    preampSubResponse.ResponseDetail.Gain.InputUnits = namedResponse.Stage[preampStage-2].PolesZeros.OutputUnits
                                else:
                                    raise Exception("can't get prior units for gain only stage: {}  prev: {}".format(s.exportdict(ignorewarning=True), namedResponse.Stage[preampStage-2].exportdict(ignorewarning=True)))
                                if hasattr(namedResponse.Stage[preampStage], 'Coefficients'):
                                    preampSubResponse.ResponseDetail.Gain.OutputUnits = namedResponse.Stage[preampStage].Coefficients.InputUnits
                                elif hasattr(namedResponse.Stage[preampStage], "FIR"):
                                    preampSubResponse.ResponseDetail.Gain.OutputUnits = namedResponse.Stage[logpreampStagegerStartStage].FIR.InputUnits
                                else:
                                    raise Exception("can't get next units for gain only stage: {}  next: {}".format(s.exportdict(ignorewarning=True), namedResponse.Stage[preampStage].exportdict(ignorewarning=True)))

                        else:
                            preampSubResponse = None
                            atodSubResponse.sequenceNumber -= 1
                            loggerSubResponse.sequenceNumber = atodSubResponse.sequenceNumber +1

                        if atodStageInOrig < 0:
                            raise Exception('Cannot find AtoD stage in {}'.format(namedResponse))

                        isAtoD, isAtoDReason = isAtoDStage(namedResponse, atodStageInOrig)
                        if not isAtoD:
                            raise Exception('Expected AtoD stage as {}, but does not look like V to count Coefficients: {}, {}'.format(atodStageInOrig, chanCodeId, isAtoDReason))
                        atodSubResponse.ResponseDetail = sisxmlparser.SubResponseDetailType()
                        atodSubResponse.ResponseDetail.Gain = sisxmlparser.SISGainType()
                        atodOld = namedResponse.Stage[atodStageInOrig-1]
                        atodSubResponse.ResponseDetail.Gain.Value = atodOld.StageGain.Value
                        atodSubResponse.ResponseDetail.Gain.Frequency = atodOld.StageGain.Frequency
                        atodSubResponse.ResponseDetail.Gain.InputUnits = atodOld.Coefficients.InputUnits
                        atodSubResponse.ResponseDetail.Gain.OutputUnits = atodOld.Coefficients.OutputUnits
                        # check make sure there are more stages
                        if loggerSubResponse is None or len(namedResponse.Stage) < loggerStageInOrig:
                            loggerSubResponse = None
                        else:
                            loggerSubResponse.ResponseDictLink = sisxmlparser.ResponseDictLinkType()
                            loggerSubResponse.ResponseDictLink.Name = "L_"+prototypeChan
                            loggerSubResponse.ResponseDictLink.SISNamespace = namespace
                            loggerSubResponse.ResponseDictLink.Type = 'FilterSequence'
                else:
                    if len(lll) > 1:
                        print("       WARNING: %s has more than one matching logger response in NRL, using first"%(chanCodeId,))
                        for templ in lll:
                            print("         %s"%(templ[0],))
                    if VERBOSE: print("        logger in NRL: %s"%(xcode,))
                    loggerSubResponse.RESPFile = sisxmlparser.RESPFileType()
                    loggerSubResponse.RESPFile.ValueOf = lll[0][0].replace("nrl", NRL_PREFIX)
                    # don't need these if logger came from NRL
                    preampSubResponse = None
                    atodSubResponse = None
                    loggerSubResponse.sequenceNumber -= 2
                    # stage To/From not required for NRL responses, use SIS rules
                    #loggerSubResponse.RESPFile.stageFrom = lll[0][2]
                    #loggerSubResponse.RESPFile.stageTo = lll[0][3]

    c.Response.SubResponse = []
    if sensorSubResponse is not  None:
        c.Response.SubResponse.append( sensorSubResponse)
    if preampSubResponse is not  None:
        c.Response.SubResponse.append(preampSubResponse)
    if atodSubResponse is not  None:
        # might be None in case of NRL logger
        c.Response.SubResponse.append(atodSubResponse)
    if loggerSubResponse is not None:
        c.Response.SubResponse.append( loggerSubResponse )
    return c


def toSISNetwork(n):
    elemDict = n.exportdict(ignorewarning=False)
    sisNet = sisxmlparser.SISNetworkType(**elemDict)
    sisNet.Station = []
    return sisNet


def toSISStation(s):
    elemDict = s.exportdict(ignorewarning=False)
    sisSta = sisxmlparser.SISStationType(**elemDict)
    sisSta.Channel = []
    return sisSta

def toSISChannel(ch):
    '''
    copies all attrs from the input fdsn channel object to a sis channel, except
    the Response as that needs to be a SISResponseType
    '''
    savedResponse = ch.Response
    ch.Response = None
    elemDict = ch.exportdict(ignorewarning=False)
    sisCh = sisxmlparser.SISChannelType(**elemDict)
    ch.Response = savedResponse
    return sisCh

def toSISPolesZeros(pz, sisNamespace):
    elemDict = pz.exportdict(ignorewarning=False)
    sisPZ = sisxmlparser.SISPolesZerosType(**elemDict)
    sisPZ.SISNamespace = sisNamespace
    return sisPZ

def toSISCoefficients(coef, sisNamespace):
    elemDict = coef.exportdict(ignorewarning=False)
    sisCoef = sisxmlparser.SISCoefficientsType(**elemDict)
    sisCoef.SISNamespace = sisNamespace
    return sisCoef

def toSISPolynomial(poly, sisNamespace):
    elemDict = poly.exportdict(ignorewarning=False)
    sisPoly = sisxmlparser.SISPolynomialType(**elemDict)
    sisPoly.SISNamespace = sisNamespace
    return sisPoly

def createResponseDict(prototypeChan, s, sisNamespace):
    '''create sis ResponseDict from a Stage'''
    rd = sisxmlparser.ResponseDictType()
    if hasattr(s, "PolesZeros"):
        rd.PolesZeros = toSISPolesZeros(s.PolesZeros, sisNamespace)
        rd.PolesZeros.name = "FS_%d_%s"%(s.number, prototypeChan)
    elif hasattr(s, "FIR"):
        elemDict = s.FIR.exportdict()
        rd.FIR = sisxmlparser.SISFIRType(**elemDict)
        rd.FIR.name = "FS_%d_%s"%(s.number, prototypeChan)
        rd.FIR.SISNamespace = sisNamespace
    elif hasattr(s, "Coefficients"):
        rd.Coefficients = toSISCoefficients(s.Coefficients, sisNamespace)
        rd.Coefficients.name = "FS_%d_%s"%(s.number, prototypeChan)
    elif hasattr(s, "StageGain") and hasattr(s.StageGain, 'InputUnits') and hasattr(s.StageGain, 'OutputUnits'):
        # preamp gain only stage, but we already fixed the units
        rd = None
    else:
        raise Exception("ERROR: createResponseDict stage does not have PZ, FIR or Coef: %s stage %s   \n%s"%(prototypeChan, s.number, s.exportdict(ignorewarning=True)))
    return rd


def main():
    global VERBOSE
    sisNamespace = "TESTING"
    parseArgs = initArgParser()
    if parseArgs.verbose:
        VERBOSE=True
        for k, v in vars(parseArgs).items():
            print("    Args: %s %s"%(k, v))
    sisNamespace = parseArgs.namespace
    if parseArgs.stationxml:
        if not xerces_validate(parseArgs.stationxml):
            return

        # Parse an xml file
        isExtStaXml = False
        rootobj = sisxmlparser.parse(parseArgs.stationxml, isExtStaXml)
        if hasattr(rootobj, 'comments'):
            origModuleURI = rootobj.ModuleURI
        else:
            origModuleURI = ""
        sisRoot = sisxmlparser.SISRootType()
        sisRoot.schemaVersion='3.0'
        sisRoot.Source=parseArgs.namespace
        sisRoot.Sender=parseArgs.namespace
        sisRoot.Module='sta2extsta.py'
        sisRoot.ModuleURI='https://github.com/crotwell/2extStationXML'
        sisRoot.Created=datetime.datetime.now()

        if not hasattr(rootobj, 'comments'):
            sisRoot.comments = []
        else:
            sisRoot.comments = rootobj.comments
        sisRoot.comments.append("From: "+origModuleURI)

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

        for n in rootobj.Network:
            for s in n.Station:
                tempChan = []
                for c in s.Channel:
                    if hasattr(c, 'Response') and hasattr(c.Response, 'Stage') and isOnlyGainStage(c.Response, 1):
                         # for weird case of gain channels for gain-ranged channels
                         # input and output units should be volts and we will
                         # insert a fake unity sensor for this.
                         if c.Response.InstrumentSensitivity.InputUnits.Name == 'V' and c.Response.Stage[1].Coefficients.InputUnits.Name == 'V':
                             print("INFO: adding unity V to V polezero to stage 1 for %s.%s.%s.%s"%(n.code, s.code, c.locationCode, c.code))
                             pzTemp = sisxmlparser.PolesZerosType()
                             pzTemp.InputUnits = c.Response.InstrumentSensitivity.InputUnits
                             pzTemp.OutputUnits = c.Response.Stage[1].Coefficients.InputUnits
                             pzTemp.PzTransferFunctionType = "LAPLACE (RADIANS/SECOND)"
                             pzTemp.NormalizationFactor = 1
                             pzTemp.NormalizationFrequency = 1
                             pzTemp.Zero = []
                             pzTemp.Pole = []
                             c.Response.Stage[0].PolesZeros = pzTemp
                         else:
                             print("WARNING: can't fix stage 1, no poleszeros for %s.%s.%s.%s"%(n.code, s.code, c.locationCode, c.code))


        if not os.path.exists(parseArgs.nrl):
            print("ERROR: can't find nrl dir at '%s', get with 'svn checkout http://seiscode.iris.washington.edu/svn/nrl/trunk nrl"%(parseArgs.nrl,))
            return
        spsIndex = os.path.join(parseArgs.nrl, "logger_sample_rate.sort")
        if not os.path.exists(spsIndex):
            print("ERROR: can't fine sps index file for NRL. Should be logger_sample_rate.sort inside NRL directory")
            print("python checkNRL.py --samplerate --nrl <path_to_nrl>")
            return

# load logger response by sample rate index file, speeds search
        if VERBOSE: print("load NRL sample rate index")
        loggerRateIndex = checkNRL.loadRespfileSampleRate(spsIndex)
# clean unit names (ie count instead of COUNTS)
        cleanChanges = cleanUnitNames.cleanUnitNames(rootobj)
        if VERBOSE:
          print("check units: %d changes"%(cleanChanges['numChanges'],))
          for k, v in cleanChanges.items():
            if k != 'numChanges':
                print("Rename unit: %s => %s"%(k, v))
# find all unique responses so only check identical channels once
        if VERBOSE: print("find unique responses in xml")
        uniqResponse = uniqResponses.uniqueResponses(rootobj)
# for each unique response, see if it is in the NRL so we use NRL instead of
# a in file named response
        if VERBOSE: print("look for responses in NRL...this could take a while")
        uniqWithNRL = checkNRL.checkRespListInNRL(parseArgs.nrl, uniqResponse, loggerRateIndex=loggerRateIndex)


        for n in rootobj.Network:
          print("%s "%(n.code,))
          sisNet = None
          for s in n.Station:
            print("    %s   "%(s.code, ))
            if not hasattr(s, 'Operator'):
                s.Operator = []
                sOp = sisxmlparser.OperatorType()
                sOp.Agency = parseArgs.operator
                s.Operator.append(sOp)
            allChanCodes = {}
            tempChan = []
            for c in s.Channel:
              if parseArgs.delcurrent and (not hasattr(c, 'endDate') or
              c.endDate > datetime.datetime.now(datetime.timezone.utc) ):
                 print("        %s.%s --delcurrent: delete channel ends after now %s "%(c.locationCode, c.code, checkNRL.getChanCodeId(n,s,c),))
              else:
                 tempChan.append(c)

            tempChan = []
            for c in s.Channel:
                print("        %s.%s "%(c.locationCode, c.code,))
                sisChan = toSISChannel(c)
                key = "%s.%s"%(c.locationCode, c.code)
                if not key in allChanCodes:
                    allChanCodes[key] = []
                allChanCodes[key].append(sisChan)
                fixResponseNRL(n, s, sisChan, c.Response, uniqWithNRL, sisNamespace)
                tempChan.append(sisChan)
            if len(tempChan) > 0:
                if sisNet is None:
                    sisNet = toSISNetwork(n)
                    sisNet.Station = [] # to be added later
                    if not hasattr(sisRoot, 'Network'):
                        sisRoot.Network = []
                    sisRoot.Network.append(sisNet)
                sisSta = toSISStation(s)
                sisNet.Station.append(sisSta)
                sisSta.Channel = tempChan

            for key, epochList in allChanCodes.items():
              epochList.sort(key=getStartDate)



        # save old stage as named and added so only add each unique stage once
        # this is only for logger stages as sensor is taken care of in fixResponseNRL
        prevAddedFilterStage = {}

        respGroup = sisxmlparser.ResponseDictGroupType()
        respGroup.ResponseDict = []
        for prototypeChan, namedResponse, chanCodeList, sss, lll in uniqWithNRL:
            if not hasattr(namedResponse, 'Stage'):
                # no stages, so do not need to add
                continue
            if VERBOSE: print("add to hardware, prototype: "+prototypeChan)
            if len(sss) == 0:
                # add stage 1 as sensor
                sensor = sisxmlparser.ResponseDictType()
                if hasattr(namedResponse.Stage[0], "PolesZeros"):
                    sensor.PolesZeros = toSISPolesZeros(namedResponse.Stage[0].PolesZeros, sisNamespace)
                    sensor.PolesZeros.name = "S_"+prototypeChan
                elif hasattr(namedResponse.Stage[0], "Coefficients"):
                    sensor.Coefficients = toSISCoefficients(namedResponse.Stage[0].Coefficients, sisNamespace)
                    sensor.Coefficients.name = "S_"+prototypeChan
                elif isSimpleSOHSingleStage(namedResponse):
                    sensor = None
                elif hasattr(namedResponse.Stage[0], "Polynomial"):
                    sensor.Polynomial = toSISPolynomial(namedResponse.Stage[0].Polynomial, sisNamespace)
                    sensor.Polynomial.name = "S_"+prototypeChan
                else:
                    print("WARNING: sensor response for %s doesnot have PolesZeros"%(prototypeChan,))
                    return
                if sensor is not None:
                    respGroup.ResponseDict.append(sensor)

            if len(lll) == 0:
                # add later stages as logger
                logger = sisxmlparser.ResponseDictType()
                logger.FilterSequence = sisxmlparser.FilterSequenceType()
                logger.FilterSequence.name = "L_"+prototypeChan
                logger.FilterSequence.SISNamespace = sisNamespace
                logger.FilterSequence.FilterStage = []
                loggerStartStage = 2
                # array index is 0-base, stage number is 1-base, so -1
                # first logger stage should be AtoD stage and SIS wants
                # that separate from the filter chain
                if not (isPreampStage(namedResponse, loggerStartStage) and isAtoDStage(namedResponse, loggerStartStage+1) or isAtoDStage(namedResponse, loggerStartStage)):
                   raise Exception("ERROR: expecting preamp then AtoD or AtoD stage, which should have Coefficients, but not found. %d %s"%(loggerStartStage, prototypeChan))

                # now deal with actual filter chain

                respDictSeqNum = 1
                for s in namedResponse.Stage[loggerStartStage -1 : ]:
                    # do not output preamp or atod as part of filter seq.
                    if s.number == loggerStartStage and isPreampStage(namedResponse, loggerStartStage):
                        continue
                    if s.number == loggerStartStage and isAtoDStage(namedResponse, loggerStartStage):
                        continue
                    if s.number == loggerStartStage+1 and isAtoDStage(namedResponse, loggerStartStage+1):
                        continue

                    filterStage = sisxmlparser.FilterStageType()
                    filterStage.SequenceNumber = respDictSeqNum
                    respDictSeqNum += 1

                    if hasattr(s, "Decimation"):
                       filterStage.Decimation = s.Decimation
                    else:
                       print("No decimation in %s stage %d but it is required"%(prototypeChan, s.number))
                    if hasattr(s, "StageGain"):
                       filterStage.Gain = s.StageGain
                    filterStage.Filter = sisxmlparser.FilterIDType()

                    # search to see if we have already added this filter stage
                    found = False
                    for oldName, oldStage in prevAddedFilterStage.items():
                       if uniqResponses.areSameStage(s, oldStage)[0]:
                           found=True
                           break

                    if not found:
                       filterStage.Filter.Name = "FS_%d_%s"%(s.number, prototypeChan)
                       rd = createResponseDict(prototypeChan, s, sisNamespace)
                       if rd is not None:
                           respGroup.ResponseDict.append(rd)
                           prevAddedFilterStage[filterStage.Filter.Name] = s
                    else:
                       filterStage.Filter.Name = oldName
                    filterStage.Filter.SISNamespace = sisNamespace
                    # set type
                    if hasattr(s, "PolesZeros"):
                       filterStage.Filter.Type = "PolesZeros"
                    elif hasattr(s, "FIR"):
                       filterStage.Filter.Type = "FIR"
                    elif hasattr(s, "Coefficients"):
                       filterStage.Filter.Type = "Coefficients"
                    else:
                       raise SISError("stage does not have PZ, FIR or Coef: %s stage %s   \n%s"%(prototypeChan, s.number, s.exportdict(ignorewarning=True)))

                    logger.FilterSequence.FilterStage.append(filterStage)
                if len(logger.FilterSequence.FilterStage) > 0:
                   # only add if not empty
                   respGroup.ResponseDict.append(logger)


# add named non-NRL responses to HardwareResponse but not if respGroup is empty
        if len(respGroup.ResponseDict) > 0:
            if not hasattr(sisRoot, "HardwareResponse"):
                sisRoot.HardwareResponse = sisxmlparser.HardwareResponseType()
            if not hasattr(sisRoot.HardwareResponse, "ResponseDictGroup"):
                sisRoot.HardwareResponse.ResponseDictGroup = respGroup
            else:
                raise SISError ("sisRoot already has HardwareResponse.ResponseDictGroup!")
# Finally after the instance is built export it.
        sisRoot.exportxml(parseArgs.outfile, ignorewarning=parseArgs.ignorewarning)


if __name__ == "__main__":
    sys.exit(main())
