#! /usr/bin/python
'''
use the classes in sisxmlparser2_0 to generate an ExtStationXML file from regular stationxml.
'''
import checkNRL as checkNRL
import sisxmlparser2_0 as sisxmlparser
import uniqResponses as uniqResponses

import argparse
import datetime 
import dateutil.parser
import sys

USAGE_TEXT = """
Usage: python <Parser>.py <in_xml_file>
"""

NRL_PREFIX = "http://ds.iris.edu/NRL"

def usage():
    print USAGE_TEXT
    sys.exit(1)

def getStartDate(channel):
  return channel.startDate

def initArgParser():
  parser = argparse.ArgumentParser(description='Convert StationXML to ExtendedStationXML.')
  parser.add_argument('-s', '--stationxml', required=True, help="input FDSN StationXML file, often retrieved from http://service.iris.edu/fdsnws/station/1/")
  parser.add_argument('--nrl', help="replace matching responses with links to NRL")
  parser.add_argument('--namespace', default='Testing', help="SIS namespace to use for named responses, see http://anss-sis.scsn.org/sis/master/namespace/")
  parser.add_argument('--operator', default='Testing', help="SIS operator to use for stations, see http://anss-sis.scsn.org/sis/master/org/")
  parser.add_argument('--delcurrent', action="store_true", help="remove channels that are currently operating. Only do this if you want to go back and manually via the web interface add hardware for current epochs.")
  parser.add_argument('-o', '--outfile', nargs='?', type=argparse.FileType('w'), default=sys.stdout)
  return parser.parse_args()

def convertToResponseDict(fdsnResponse):
    respDict = sisxmlparser.ResponseDict()
    respDict.FilterSequence = sisxmlparser.FilterSequenceType()
    

def fixResponseNRL(n, s, c, uniqResponse, namespace):
  if c.Response != None:
     chanCodeId = checkNRL.getChanCodeId(n, s, c)
     sensorSubResponse = sisxmlparser.SubResponseType()
     sensorSubResponse.sequenceNumber = 1
     loggerSubResponse = sisxmlparser.SubResponseType()
     loggerSubResponse.sequenceNumber = 2

     oldResponse = c.Response
     c.Response = sisxmlparser.SISResponseType()
     for prototypeChan, nanmedRespone, chanCodeList, sss, lll in uniqResponse:
         for xcode in chanCodeList:
             if xcode == chanCodeId:
                 # found it
                 # sensor ######
                 if len(sss) == 0 :
                     # not nrl, so use named response
                     sensorSubResponse.ResponseDictLink = sisxmlparser.ResponseDictLinkType2()
                     sensorSubResponse.ResponseDictLink.Name = "S_"+prototypeChan
                     sensorSubResponse.ResponseDictLink.SISNamespace = namespace
                     sensorSubResponse.ResponseDictLink.Type = 'PolesZeros'
                     sensorSubResponse.ResponseDictLink.Gain = sisxmlparser.SISGainType()
                     sensorSubResponse.ResponseDictLink.Gain.Value = oldResponse.Stage[0].StageGain.Value
                     sensorSubResponse.ResponseDictLink.Gain.Frequency = oldResponse.Stage[0].StageGain.Frequency

                 else:
                     if len(sss) > 1:
                       print "WARNING: %s has more than one matching sensor, using first"%(chanCodeId,)
                     sensorSubResponse.RESPFile = sisxmlparser.RESPFileType()
                     sensorSubResponse.RESPFile.stageFrom = 1
                     sensorSubResponse.RESPFile.stageTo = 1
                     sensorSubResponse.RESPFile.ValueOf = sss[0][0].replace("nrl", NRL_PREFIX)
                 # datalogger #######
                 if len(lll) == 0:
                     # not nrl, so use named response
                     loggerSubResponse.ResponseDictLink = sisxmlparser.ResponseDictLinkType()
                     loggerSubResponse.ResponseDictLink.Name = "L_"+prototypeChan
                     loggerSubResponse.ResponseDictLink.SISNamespace = namespace
                     loggerSubResponse.ResponseDictLink.Type = 'FilterSequence'
                 else:
                     if len(lll) > 1:
                       print "WARNING: %s has more than one matching logger, using first"%(chanCodeId,)
                     loggerSubResponse.RESPFile = sisxmlparser.RESPFileType()
                     loggerSubResponse.RESPFile.stageFrom = lll[0][2]
                     loggerSubResponse.RESPFile.stageTo = lll[0][3]
                     loggerSubResponse.RESPFile.ValueOf = lll[0][0].replace("nrl", NRL_PREFIX)
               
     c.Response.SubResponse = [ sensorSubResponse, loggerSubResponse ]
     if hasattr(c, 'Sensor'):
         #sometimes equipment comment in Sensor.Type
         if hasattr(c.Sensor, 'Type'):
             if not hasattr(c, 'Comment'):
                 c.Comment = []
             comment = sisxmlparser.CommentType()
             comment.Value = "Sensor.Type: "+c.Sensor.Type
             c.Comment.append(comment)
         del c.Sensor

def toSISPolesZeros(pz):
    sisPZ = sisxmlparser.SISPolesZerosType()
    if hasattr(pz, 'Description'):
        sisPZ.Description = pz.Description
    sisPZ.InputUnits = pz.InputUnits
    sisPZ.OutputUnits = pz.OutputUnits
    sisPZ.PzTransferFunctionType = pz.PzTransferFunctionType
    sisPZ.NormalizationFactor = pz.NormalizationFactor
    sisPZ.NormalizationFrequency = pz.NormalizationFrequency
    sisPZ.Zero = pz.Zero
    sisPZ.Pole = pz.Pole
    return sisPZ

def main():
    sisNamespace = "TESTING"
    parseArgs = initArgParser()
    sisNamespace = parseArgs.namespace
    if parseArgs.stationxml:

        # Parse an xml file
        rootobj = sisxmlparser.parse(parseArgs.stationxml)
        origModuleURI = rootobj.ModuleURI

        rootobj.schemaVersion='1.0',
        rootobj.Source=parseArgs.namespace
        rootobj.Sender=parseArgs.namespace
        rootobj.Module='sta2extsta.py',
        rootobj.ModuleURI='https://github.com/crotwell/2extStationXML',
        rootobj.Created=datetime.datetime.now()

        if not hasattr(rootobj, 'comments'):
            rootobj.comments = []
        rootobj.comments.append("From: "+origModuleURI)

# Cannot use 'xsi:type' as an identifier which is how it is 
# stored in the object. So a set function has been defined for this 
# one case. Use it only when the type has been extended - RootType, 
# StationType, ChannelType, GainType, and ResponseType
        rootobj.settype('sis:RootType')

        loggerRateIndex = checkNRL.loadRespfileSampleRate('logger_samp_rate.sort')
        uniqResponse = uniqResponses.uniqueResponses(rootobj)
        uniqWithNRL = checkNRL.checkRespListInNRL(parseArgs.nrl, uniqResponse, loggerRateIndex=loggerRateIndex)
        

        for n in rootobj.Network:
#          print "%s %s"%(n.code, n.getattr('xsi:type'))
          print "%s %s"%(n.code, n.getattrxml())
          for s in n.Station:
            print "  %s   %s"%(s.code, s.getattrxml())
            if not hasattr(s, 'Operator'):
                s.Operator = []
                sOp = sisxmlparser.OperatorType()
                sOp.Agency = []
                sOp.Agency.append(parseArgs.operator)
                s.Operator.append(sOp)
            allChanCodes = {}
            for c in s.Channel:
              print "    %s.%s "%(c.locationCode, c.code,)
              if c.endDate > datetime.datetime.now() and parseArgs.delcurrent:
                 print "channel ends after now %s "%(checkNRL.getChanCodeId(n,s,c),)
                 s.Channel.remove(c)
              else:
#                print "    %s.%s "%(c.getattr('locationCode'), c.code,)
                key = "%s.%s"%(c.locationCode, c.code)
                if not key in allChanCodes:
                  allChanCodes[key] = []
                allChanCodes[key].append(c)
                fixResponseNRL(n, s, c, uniqWithNRL, sisNamespace)

            print "all chan codes: %d"%(len(allChanCodes))
            for key, epochList in allChanCodes.iteritems():
              epochList.sort(key=getStartDate)
              print "%s %d %s %s"%(key, len(epochList), epochList[-1].startDate, epochList[-1].endDate)
            

# add named non-NRL responses to hardwareResponse
        if not hasattr(rootobj, "HardwareResponse"):
            rootobj.HardwareResponse = sisxmlparser.HardwareResponseType()
        if not hasattr(rootobj.HardwareResponse, "ResponseDictGroup"):
            rootobj.HardwareResponse.ResponseDictGroup = sisxmlparser.ResponseDictGroupType()
        
        respGroup = rootobj.HardwareResponse.ResponseDictGroup
        if not hasattr(rootobj.HardwareResponse.ResponseDictGroup, "ResponseDict"):
            rootobj.HardwareResponse.ResponseDictGroup.ResponseDict = []
        for prototypeChan, namedResponse, chanCodeList, sss, lll in uniqWithNRL:
            if len(sss) == 0:
                # add stage 1 as sensor
                sensor = sisxmlparser.ResponseDictType()
                if hasattr(namedResponse.Stage[0], "PolesZeros"):
                    sensor.PolesZeros = toSISPolesZeros(namedResponse.Stage[0].PolesZeros)
                    sensor.PolesZeros.name = "S_"+prototypeChan
                    sensor.PolesZeros.SISNamespace = sisNamespace 
                else:
                    print "WARNING: sensor response for %s doesnot have PolesZeros"%(prototypeChan,)
                respGroup.ResponseDict.append(sensor)
            if len(lll) == 0:
                # add later stages as logger
                logger = sisxmlparser.ResponseDictType()
                logger.FilterSequence = sisxmlparser.FilterSequenceType()
                logger.FilterSequence.name = "L_"+prototypeChan
                logger.FilterSequence.SISNamespace = sisNamespace 
                logger.FilterSequence.FilterStage = []
                for s in namedResponse.Stage[1:]:
                   filterStage = sisxmlparser.FilterStageType()
                   filterStage.SequenceNumber = s.number
                   filterStage.Decimation = s.Decimation
                   filterStage.Gain = s.StageGain
                   filterStage.Filter = sisxmlparser.FilterIDType()
                   filterStage.Filter.Name = "FS_%d_%s"%(s.number, prototypeChan)
                   filterStage.Filter.SISNamespace = sisNamespace
                   logger.FilterSequence.FilterStage.append(filterStage)
                   rd = sisxmlparser.ResponseDictType()
                   if hasattr(s, "PolesZeros"):
                       filterStage.Filter.Type = "PolesZeros"
                       rd.PolesZeros = toSISPolesZeros(s.PolesZeros)
                       rd.PolesZeros.name = "FS_%d_%s"%(s.number, prototypeChan)
                       rd.Poles.Zeros.SISNamespace = sisNamespace
                   if hasattr(s, "FIR"):
                       filterStage.Filter.Type = "FIR"
                       rd.FIR = sisxmlparser.SISFIRType()
                       if hasattr(s.FIR, 'Description'):
                           rd.FIR.Description = s.FIR.Description
                       rd.FIR.InputUnits = s.FIR.InputUnits
                       rd.FIR.OutputUnits = s.FIR.OutputUnits
                       rd.FIR.Symmetry = s.FIR.Symmetry
                       rd.FIR.NumeratorCoefficient = s.FIR.NumeratorCoefficient
                       rd.FIR.name = "FS_%d_%s"%(s.number, prototypeChan)
                       rd.FIR.SISNamespace = sisNamespace
                   if hasattr(s, "Coefficients"):
                       filterStage.Filter.Type = "Coefficients"
                       rd.Coefficients = sisxmlparser.SISCoefficientsType()
                       if hasattr(s.Coefficients, 'Description'):
                           rd.Coefficients.Description = s.Coefficients.Description
                       rd.Coefficients.InputUnits = s.Coefficients.InputUnits
                       rd.Coefficients.OutputUnits = s.Coefficients.OutputUnits
                       rd.Coefficients.CfTransferFunctionType = s.Coefficients.CfTransferFunctionType
                       rd.Coefficients.Numerator = s.Coefficients.Numerator
                       if hasattr(s.Coefficients, "Denominator"):
                           rd.Coefficients.Denominator = s.Coefficients.Denominator
                       rd.Coefficients.name = "FS_%d_%s"%(s.number, prototypeChan)
                       rd.Coefficients.SISNamespace = sisNamespace
                   respGroup.ResponseDict.append(rd)
                respGroup.ResponseDict.append(logger)
                  

# Finally after the instance is built export it. 
        rootobj.exportxml(parseArgs.outfile, 'FDSNStationXML', 'fsx', 0)
#        rootobj.exportxml(sys.stdout, 'FDSNStationXML', 'fsx', 0)



if __name__ == "__main__":
    sys.exit(main())
