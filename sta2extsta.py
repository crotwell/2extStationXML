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
  parser.add_argument('-s', '--stationxml')
  parser.add_argument('--nrl', help="replace matching responses with links to NRL")
  parser.add_argument('--namedresp', nargs=1, help="directory of RESP files for reuse")
  parser.add_argument('--delcurrent', action="store_true", help="remove channels that are currently operating")
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


     c.Response = sisxmlparser.SISResponseType()
     for prototypeChan, nanmedRespone, chanCodeList, sss, lll in uniqResponse:
         for xcode in chanCodeList:
             if xcode == chanCodeId:
                 # found it
                 # sensor ######
                 if len(sss) == 0 :
                     # not nrl, so use named response
                     sensorSubResponse.ResponseDictLink = sisxmlparser.ResponseDictLinkType()
                     sensorSubResponse.ResponseDictLink.Name = "S_"+prototypeChan
                     sensorSubResponse.ResponseDictLink.SISNamespace = namespace
                     sensorSubResponse.ResponseDictLink.Type = 'PolesZeros'
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
                     loggerSubResponse.ResponseDictLink.Type = 'PolesZeros'
                 else:
                     if len(lll) > 1:
                       print "WARNING: %s has more than one matching logger, using first"%(chanCodeId,)
                     loggerSubResponse.RESPFile = sisxmlparser.RESPFileType()
                     loggerSubResponse.RESPFile.stageFrom = lll[0][2]
                     loggerSubResponse.RESPFile.stageTo = -1
                     loggerSubResponse.RESPFile.ValueOf = lll[0][0].replace("nrl", NRL_PREFIX)
               
     c.Response.SubResponse = [ sensorSubResponse, loggerSubResponse ]


def main():
#################
#  fix this #####
    sisNamespace = "TESTING"
#################
    parseArgs = initArgParser()
    if parseArgs.stationxml:

        # Parse an xml file
        rootobj = sisxmlparser.parse(parseArgs.stationxml)

        rootobj.schemaVersion='1.0',
        rootobj.Source='SCSN-CA',
        rootobj.Sender='SCSN-CA',
        rootobj.Module='Based on output from IRIS WEB SERVICE: fdsnws-station | version: 1.0.5',
        rootobj.ModuleURI='http://service.iris.edu/fdsnws/station/1/query?net=CI&sta=PASC&loc=00&cha=HHZ&starttime=2007-10-30T01:00:00&endtime=2013-07-19T10:59:27&level=response&format=xml&nodata=404',
        rootobj.Created=datetime.datetime.strptime('2013-07-19 18:09:30', '%Y-%m-%d %H:%M:%S') 

# Cannot use 'xsi:type' as an identifier which is how it is 
# stored in the object. So a set function has been defined for this 
# one case. Use it only when the type has been extended - RootType, 
# StationType, ChannelType, GainType, and ResponseType
        rootobj.settype('sis:RootType')

        loggerRateIndex = checkNRL.loadRespfileSampleRate('logger_samp_rate.sort')
        uniqResponse = uniqResponses.uniqueResponses(rootobj)
        uniqWithNRL = checkNRL.checkRespListInNRL(parseArgs.nrl, uniqResponse, loggerRateIndex=loggerRateIndex)
        

        for n in rootobj.Network:
          n.settype('sis:NetworkType')
#          print "%s %s"%(n.code, n.getattr('xsi:type'))
          print "%s %s"%(n.code, n.getattrxml())
          for s in n.Station:
            print "  %s   %s"%(s.code, s.getattrxml())
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
            rootobj.HardwareResponse.ResponseDictGroup = []
        respGroup = rootobj.HardwareResponse.ResponseDictGroup
        for prototypeChan, namedResponse, chanCodeList, sss, lll in uniqWithNRL:
            if len(sss) == 0:
                # add stage 1 as sensor
                sensor = sisxmlparser.ResponseDictType()
                if hasattr(namedResponse, "PolesZeros"):
                    sensor.PolesZeros = namedResponse.PolesZeros
                    sensor.PolesZeros.name = "S_"+prototypeChan
                    sensor.PolesZeros.SISNamespace = sisNamespace 
                else:
                    print "WARNING: sensor response for %s doesnot have PolesZeros"%(prototypeChan,)
                respGroup.append(sensor)
            if len(lll) == 0:
                # add later stages as logger
                logger = sisxmlparser.ResponseDictType()
                logger.FilterSequence = sisxmlparser.FilterSequenceType()
                logger.FilterSequence.name = "s_"+prototypeChan
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
                   respGroup.append(rd)
                   if hasattr(s, "PolesZeros"):
                       filterStage.Filter.Type = "PolesZeros"
                       rd.PolesZeros = s.PolesZeros
                       rd.PolesZeros.name = "FS_%d_%s"%(s.number, prototypeChan)
                       rd.Poles.Zeros.SISNamespace = sisNamespace
                   if hasattr(s, "FIR"):
                       filterStage.Filter.Type = "FIR"
                       rd.FIR = s.FIR
                       rd.FIR.name = "FS_%d_%s"%(s.number, prototypeChan)
                       rd.FIR.SISNamespace = sisNamespace
                   if hasattr(s, "Coefficients"):
                       filterStage.Filter.Type = "Coefficients"
                       rd.Coefficients = s.Coefficients
                       rd.Coefficients.name = "FS_%d_%s"%(s.number, prototypeChan)
                       rd.Coefficients.SISNamespace = sisNamespace
                respGroup.append(logger)
                  

# Finally after the instance is built export it. 
        rootobj.exportxml(parseArgs.outfile, 'FDSNStationXML', 'fsx', 0)
#        rootobj.exportxml(sys.stdout, 'FDSNStationXML', 'fsx', 0)



if __name__ == "__main__":
    sys.exit(main())
