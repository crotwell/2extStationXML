#! /usr/bin/python
'''
use the classes in sisxmlparser2_0 to generate an ExtStationXML file from regular stationxml.
'''
import checkNRL as checkNRL
import sisxmlparser2_0 as sisxmlparser
import uniqResponses as uniqResponses
import cleanUnitNames as cleanUnitNames

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

SCHEMA_FILE = "sis_extension_2.0.xsd"

def usage():
    print(USAGE_TEXT)
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
  return parser.parse_args()

def convertToResponseDict(fdsnResponse):
    respDict = sisxmlparser.ResponseDict()
    respDict.FilterSequence = sisxmlparser.FilterSequenceType()
    
def isAtoDStage(namedResponse, sNum):
    for stage in namedResponse.Stage:
       if stage.number == sNum:
           break
    if hasattr(stage, 'Coefficients') and hasattr(stage, 'Decimation'):
       if hasattr(stage.Coefficients, 'InputUnits') and stage.Coefficients.InputUnits.Name == 'V' and \
           hasattr(stage.Coefficients, 'OutputUnits') and \
           (stage.Coefficients.OutputUnits.Name == 'count' or stage.Coefficients.OutputUnits.Name == 'counts'):
           return True
    #print "Coeff: %s  Dec:%s  In:%s  Out: %s"%(hasattr(stage, 'Coefficients'), hasattr(stage, 'Decimation'), stage.Coefficients.InputUnits.Name, stage.Coefficients.OutputUnits.Name)
    return False

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

def fixResponseNRL(n, s, c, uniqResponse, namespace):

  chanCodeId = checkNRL.getChanCodeId(n, s, c)

  if VERBOSE:
      print "fixResponseNRL: %s"%(chanCodeId,)
  if c.Response is None:
     print "Channel has no Response: "+chanCodeId
     return

  oldResponse = c.Response
  c.Response = sisxmlparser.SISResponseType()
  if oldResponse.InstrumentSensitivity != None:
      c.Response.InstrumentSensitivity = oldResponse.InstrumentSensitivity
  else:
      # need to calculate overall sensitivity
      print "WARNING: %s does not have InstrumentSensitivity, this is required in SIS."%(chanCodeId,)

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
      print "WARNING: %s's Response does not have any Stage elements."%(chanCodeId,)
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
              if len(sss) == 0 :
                  if VERBOSE: print " sensor not NRL, use named resp: %s"%(xcode,)
                  # not nrl, so use named response
                  sensorSubResponse.ResponseDictLink = sisxmlparser.ResponseDictLinkType2()
                  sensorSubResponse.ResponseDictLink.Name = "S_"+prototypeChan
                  sensorSubResponse.ResponseDictLink.SISNamespace = namespace
                  sensorSubResponse.ResponseDictLink.Type = 'PolesZeros'
                  sensorSubResponse.ResponseDictLink.Gain = sisxmlparser.SISGainType()
                  sensorSubResponse.ResponseDictLink.Gain.Value = oldResponse.Stage[0].StageGain.Value
                  sensorSubResponse.ResponseDictLink.Gain.Frequency = oldResponse.Stage[0].StageGain.Frequency
                  sensorSubResponse.ResponseDictLink.Gain.InputUnits = oldResponse.Stage[0].PolesZeros.InputUnits
                  sensorSubResponse.ResponseDictLink.Gain.OutputUnits = oldResponse.Stage[0].PolesZeros.OutputUnits

              else:
                  if len(sss) > 1:
                    print "WARNING: %s has more than one matching sensor response in NRL, using first"%(chanCodeId,)
                    for temps in sss:
                      print "  %s"%(temps[0],)
                  if VERBOSE: print " sensor in NRL: %s"%(xcode,)
                  sensorSubResponse.RESPFile = sisxmlparser.RESPFileType()
                  sensorSubResponse.RESPFile.ValueOf = sss[0][0].replace("nrl", NRL_PREFIX)
                  # stage To/From not required for NRL responses, use SIS rules
                  #sensorSubResponse.RESPFile.stageFrom = 1
                  #sensorSubResponse.RESPFile.stageTo = 1
              # datalogger #######
              if len(lll) == 0:
                  if VERBOSE: print " logger not NRL, use named resp: %s"%(xcode,)
                  # not nrl, so use named response
                  if isOnlyGainStage(namedResponse, 2):
                      preampSubResponse.PreampGain = namedResponse.Stage[1].StageGain.Value
                  else:
                      preampSubResponse = None
                      atodSubResponse.sequenceNumber = 2
                      loggerSubResponse.sequenceNumber = 3
                  if not isAtoDStage(namedResponse, atodSubResponse.sequenceNumber):
                      raise Exception('Expected AtoD stage as %d, but does not look like V to count Cefficients: %s'%(loggerSubResponse.sequenceNumber, chanCodeId))
                  atodSubResponse.ResponseDetail = sisxmlparser.SubResponseDetailType()
                  atodSubResponse.ResponseDetail.Gain = sisxmlparser.SISGainType()
                  atodOld = namedResponse.Stage[atodSubResponse.sequenceNumber-1]
                  atodSubResponse.ResponseDetail.Gain.Value = atodOld.StageGain.Value
                  atodSubResponse.ResponseDetail.Gain.Frequency = atodOld.StageGain.Frequency
                  atodSubResponse.ResponseDetail.Gain.InputUnits = atodOld.Coefficients.InputUnits
                  atodSubResponse.ResponseDetail.Gain.OutputUnits = atodOld.Coefficients.OutputUnits
                  # check make sure there are more stages
                  if len(namedResponse.Stage) < loggerSubResponse.sequenceNumber:
                      loggerSubResponse = None
                  else:
                      loggerSubResponse.ResponseDictLink = sisxmlparser.ResponseDictLinkType()
                      loggerSubResponse.ResponseDictLink.Name = "L_"+prototypeChan
                      loggerSubResponse.ResponseDictLink.SISNamespace = namespace
                      loggerSubResponse.ResponseDictLink.Type = 'FilterSequence'
              else:
                  if len(lll) > 1:
                    print "WARNING: %s has more than one matching logger response in NRL, using first"%(chanCodeId,)
                    for templ in lll:
                      print "  %s"%(templ[0],)
                  if VERBOSE: print " logger in NRL: %s"%(xcode,)
                  loggerSubResponse.RESPFile = sisxmlparser.RESPFileType()
                  loggerSubResponse.RESPFile.ValueOf = lll[0][0].replace("nrl", NRL_PREFIX)
                  # stage To/From not required for NRL responses, use SIS rules
                  #loggerSubResponse.RESPFile.stageFrom = lll[0][2]
                  #loggerSubResponse.RESPFile.stageTo = lll[0][3]
               
  c.Response.SubResponse = []
  c.Response.SubResponse.append( sensorSubResponse)
  if preampSubResponse != None:
      c.Response.SubResponse.append(preampSubResponse)
  if atodSubResponse != None:
      # might be None in case of NRL logger
      c.Response.SubResponse.append(atodSubResponse)
  if loggerSubResponse is not None:
      c.Response.SubResponse.append( loggerSubResponse )

def toSISPolesZeros(pz):
    sisPZ = sisxmlparser.SISPolesZerosType()
    if hasattr(pz, 'Description'):
        sisPZ.Description = pz.Description
    sisPZ.InputUnits = pz.InputUnits
    sisPZ.OutputUnits = pz.OutputUnits
    sisPZ.PzTransferFunctionType = pz.PzTransferFunctionType
    sisPZ.NormalizationFactor = pz.NormalizationFactor
    sisPZ.NormalizationFrequency = pz.NormalizationFrequency
    if hasattr(pz, 'Zero'):
        sisPZ.Zero = pz.Zero
    if hasattr(pz, 'Pole'):
        sisPZ.Pole = pz.Pole
    return sisPZ


def createResponseDict(prototypeChan, s, sisNamespace):
    '''create sis ResponseDict from a Stage'''
    rd = sisxmlparser.ResponseDictType()
    if hasattr(s, "PolesZeros"):
        rd.PolesZeros = toSISPolesZeros(s.PolesZeros)
        rd.PolesZeros.name = "FS_%d_%s"%(s.number, prototypeChan)
        rd.PolesZeros.SISNamespace = sisNamespace
    elif hasattr(s, "FIR"):
        rd.FIR = sisxmlparser.SISFIRType()
        if hasattr(s.FIR, 'Description'):
            rd.FIR.Description = s.FIR.Description
        rd.FIR.InputUnits = s.FIR.InputUnits
        rd.FIR.OutputUnits = s.FIR.OutputUnits
        rd.FIR.Symmetry = s.FIR.Symmetry
        rd.FIR.NumeratorCoefficient = s.FIR.NumeratorCoefficient
        rd.FIR.name = "FS_%d_%s"%(s.number, prototypeChan)
        rd.FIR.SISNamespace = sisNamespace
    elif hasattr(s, "Coefficients"):
        rd.Coefficients = sisxmlparser.SISCoefficientsType()
        if hasattr(s.Coefficients, 'Description'):
            rd.Coefficients.Description = s.Coefficients.Description
        rd.Coefficients.InputUnits = s.Coefficients.InputUnits
        rd.Coefficients.OutputUnits = s.Coefficients.OutputUnits
        rd.Coefficients.CfTransferFunctionType = s.Coefficients.CfTransferFunctionType
        if hasattr(s.Coefficients, "Numerator"):
            rd.Coefficients.Numerator = s.Coefficients.Numerator
        if hasattr(s.Coefficients, "Denominator"):
            rd.Coefficients.Denominator = s.Coefficients.Denominator
        rd.Coefficients.name = "FS_%d_%s"%(s.number, prototypeChan)
        rd.Coefficients.SISNamespace = sisNamespace
    else:
        print "ERROR: stage does not have PZ, FIR or Coef: %s stage %s   \n%s"%(prototypeChan, s.number, dir(s))
        rd = None
    return rd


def main():
    VERBOSE = False
    sisNamespace = "TESTING"
    parseArgs = initArgParser()
    print "in main"
    if parseArgs.verbose:
        VERBOSE=True
        for k, v in vars(parseArgs).iteritems():
            print "    Args: %s %s"%(k, v)
    sisNamespace = parseArgs.namespace
    if parseArgs.stationxml:

        if not os.path.exists(parseArgs.stationxml):
            print "ERROR: can't fine stationxml file %s"%(parseArgs.stationxml,)
            return

        # validate with SIS validator
        # http://wiki.anss-sis.scsn.org/SIStrac/wiki/SIS/Code

        if not os.path.exists(SCHEMA_FILE):
            print """
Can't find schema file sis_extension_2.0.xsd

    wget -O sis_extension_2.0.xsd https://anss-sis.scsn.org/xml/ext-stationxml/2.0/sis_extension.xsd
"""
            return;

       
        if os.path.exists('xerces-2_11_0-xml-schema-1.1-beta') and os.path.exists('xmlvalidator/ValidateStationXml.class'):
            print "Validating xml..."
            try:
                validateOut = subprocess.check_output(['java', '-cp', 'xmlvalidator:xerces-2_11_0-xml-schema-1.1-beta/xercesImpl.jar:xerces-2_11_0-xml-schema-1.1-beta/xml-apis.jar:xerces-2_11_0-xml-schema-1.1-beta/serializer.jar:xerces-2_11_0-xml-schema-1.1-beta/org.eclipse.wst.xml.xpath2.processor_1.1.0.jar:.', 'ValidateStationXml', '-s', SCHEMA_FILE, '-i', parseArgs.stationxml])
            except subprocess.CalledProcessError as e:
                validateOut = "error calling process: " + e.output
            validateOut = validateOut.strip()
            if not validateOut == '0':
                print "ERROR: invalid stationxml document, errors: '%s'"%(validateOut,)
                return
            else:
                print "OK"
        else:
            print """
ERROR: Can't find validator: %s %s
            
            wget http://mirror.cc.columbia.edu/pub/software/apache//xerces/j/binaries/Xerces-J-bin.2.11.0-xml-schema-1.1-beta.tar.gz
            tar zxf Xerces-J-bin.2.11.0-xml-schema-1.1-beta.tar.gz
            wget http://maui.gps.caltech.edu/SIStrac/raw-attachment/wiki/SIS/Code/validator.tar.gz
            tar ztf validator.tar.gz

We assume the directories validator and xerces-2_11_0-xml-schema-1.1-beta
are in current directory for validation.
            """%(os.path.exists('xerces-2_11_0-xml-schema-1.1-beta') , os.path.exists('validator/ValidateStationXml.class'))
          
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
                                print "Skip %s as doesn't match --onlychan"%(checkNRL.getChanCodeId(n, s, c),)
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
                             print "INFO: adding unity V to V polezero to stage 1 for %s.%s.%s.%s"%(n.code, s.code, c.locationCode, c.code)
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
                             print "WARNING: can't fix stage 1, no poleszeros for %s.%s.%s.%s"%(n.code, s.code, c.locationCode, c.code)
 
                                 

# Cannot use 'xsi:type' as an identifier which is how it is 
# stored in the object. So a set function has been defined for this 
# one case. Use it only when the type has been extended - RootType, 
# StationType, ChannelType, GainType, and ResponseType
        rootobj.settype('sis:RootType')

        if not os.path.exists(parseArgs.nrl):
            print "ERROR: can't find nrl dir at '%s', get with 'svn checkout http://seiscode.iris.washington.edu/svn/nrl/trunk nrl"%(parseArgs.nrl,)
            return
        spsIndex = os.path.join(parseArgs.nrl, "logger_sample_rate.sort")
        if not os.path.exists(spsIndex):
            print "ERROR: can't fine sps index file for NRL. Should be logger_sample_rate.sort inside NRL directory"
            print "python checkNRL.py --samplerate --nrl <path_to_nrl>"
            return

# load logger response by sample rate index file, speeds search
        if VERBOSE: print "load NRL sample rate index"
        loggerRateIndex = checkNRL.loadRespfileSampleRate(spsIndex)
# clean unit names (ie count instead of COUNTS)
        cleanChanges = cleanUnitNames.cleanUnitNames(rootobj)
        if VERBOSE:
          for k, v in cleanChanges.iteritems():
            if k != 'numChanges':
                print "Rename unit: %s => %s"%(k, v)
# find all unique responses so only check identical channels once
        if VERBOSE: print "find unique responses in xml"
        uniqResponse = uniqResponses.uniqueResponses(rootobj)
# for each unique response, see if it is in the NRL so we use NRL instead of
# a in file named response
        if VERBOSE: print "look for responses in NRL...this could take a while"
        uniqWithNRL = checkNRL.checkRespListInNRL(parseArgs.nrl, uniqResponse, loggerRateIndex=loggerRateIndex)
        

        for n in rootobj.Network:
          print "%s "%(n.code,)
          for s in n.Station:
            print "    %s   "%(s.code, )
            if not hasattr(s, 'Operator'):
                s.Operator = []
                sOp = sisxmlparser.OperatorType()
                sOp.Agency = []
                sOp.Agency.append(parseArgs.operator)
                s.Operator.append(sOp)
            allChanCodes = {}
            tempChan = []
            for c in s.Channel:
              if parseArgs.delcurrent and (not hasattr(c, 'endDate') or c.endDate > datetime.datetime.now() ):
                 print "        %s.%s --delcurrent: delete channel ends after now %s "%(c.locationCode, c.code, checkNRL.getChanCodeId(n,s,c),)
              else:
                 tempChan.append(c)
            s.Channel = tempChan

            for c in s.Channel:
                print "        %s.%s "%(c.locationCode, c.code,)
                key = "%s.%s"%(c.locationCode, c.code)
                if not key in allChanCodes:
                    allChanCodes[key] = []
                allChanCodes[key].append(c)
                fixResponseNRL(n, s, c, uniqWithNRL, sisNamespace)

            for key, epochList in allChanCodes.iteritems():
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
            if VERBOSE: print "add to hardware, prototype: "+prototypeChan
            if len(sss) == 0:
                # add stage 1 as sensor
                sensor = sisxmlparser.ResponseDictType()
                if hasattr(namedResponse.Stage[0], "PolesZeros"):
                    sensor.PolesZeros = toSISPolesZeros(namedResponse.Stage[0].PolesZeros)
                    sensor.PolesZeros.name = "S_"+prototypeChan
                    sensor.PolesZeros.SISNamespace = sisNamespace 
                else:
                    print "WARNING: sensor response for %s doesnot have PolesZeros"%(prototypeChan,)
                    return
                respGroup.ResponseDict.append(sensor)
                    
            if len(lll) == 0:
                # add later stages as logger
                logger = sisxmlparser.ResponseDictType()
                logger.FilterSequence = sisxmlparser.FilterSequenceType()
                logger.FilterSequence.name = "L_"+prototypeChan
                logger.FilterSequence.SISNamespace = sisNamespace 
                logger.FilterSequence.FilterStage = []
                loggerStartStage = 2
                if isOnlyGainStage(namedResponse, 2):
                    #stage 2 is gain only, so assume preamp "
                    loggerStartStage = 3
                # array index is 0-base, stage number is 1-base, so -1
                # first logger stage should be AtoD stage and SIS wants
                # that separate from the filter chain
                if not hasattr(namedResponse.Stage[loggerStartStage-1], "Coefficients"):
                   print "ERROR: expecting AtoD stage, which should have Coefficients, but not found. %d %s"%(loggerStartStage, prototypeChan)
                   return
                if not (namedResponse.Stage[loggerStartStage-1].Coefficients.InputUnits.Name == 'V' and (namedResponse.Stage[loggerStartStage-1].Coefficients.OutputUnits.Name == 'counts' or namedResponse.Stage[loggerStartStage-1].Coefficients.OutputUnits.Name == 'count')):
                   # no AtoD???, quit with error
                   print "ERROR: Was expecting AtoD stage, V to count, but found %s to %s, %s"%(namedResponse.Stage[loggerStartStage-1].Coefficients.InputUnits.Name, namedResponse.Stage[loggerStartStage-1].Coefficients.OutputUnits.Name, prototypeChan)
                   return
                # now deal with actual filter chain
                for s in namedResponse.Stage[loggerStartStage : ]:
                   # first search to see if we have already added this filter stage
                   found = False
                   for oldName, oldStage in prevAddedFilterStage.iteritems():
                       if uniqResponses.areSameStage(s, oldStage)[0]:
                           found=True
                           break
                   filterStage = sisxmlparser.FilterStageType()
                   filterStage.SequenceNumber = s.number
                   if hasattr(s, "Decimation"):
                       filterStage.Decimation = s.Decimation
                   else:
                       print "No decimation in %s stage %d but it is required"%(prototypeChan, s.number)
                   if hasattr(s, "StageGain"):
                       filterStage.Gain = s.StageGain
                   filterStage.Filter = sisxmlparser.FilterIDType()

                   if not found:
                       filterStage.Filter.Name = "FS_%d_%s"%(s.number, prototypeChan)
                       rd = createResponseDict(prototypeChan, s, sisNamespace)
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
                       print "stage does not have PZ, FIR or Coef: %s stage %s   \n%s"%(prototypeChan, s.number, dir(s))

                   logger.FilterSequence.FilterStage.append(filterStage)
                if len(namedResponse.Stage[loggerStartStage : ]) > 0:
                   # only add if not empty
                   respGroup.ResponseDict.append(logger)
                  

# add named non-NRL responses to HardwareResponse but not if respGroup is empty
        if len(respGroup.ResponseDict) > 0:
            if not hasattr(rootobj, "HardwareResponse"):
                rootobj.HardwareResponse = sisxmlparser.HardwareResponseType()
            if not hasattr(rootobj.HardwareResponse, "ResponseDictGroup"):
                rootobj.HardwareResponse.ResponseDictGroup = respGroup
            else:
                raise SISError ("rootobj already has HardwareResponse.ResponseDictGroup!")
# Finally after the instance is built export it. 
        rootobj.exportxml(parseArgs.outfile, 'FDSNStationXML', 'fsx', 0)
#        rootobj.exportxml(sys.stdout, 'FDSNStationXML', 'fsx', 0)



if __name__ == "__main__":
    sys.exit(main())
