#! /usr/bin/python
'''
use the classes in sisxmlparser2_0 to generate an ExtStationXML file from regular stationxml.
'''
import checkNRL as checkNRL
import sisxmlparser2_0 as sisxmlparser
import datetime 
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

def main():
    args = sys.argv[1:]
    if len(args) == 1:

        # Parse an xml file
        rootobj = sisxmlparser.parse(args[0])

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

# find responses that look like they came from the NRL
        matchSensor, matchLogger = checkNRL.checkNRL("nrl", rootobj)


        for n in rootobj.Network:
          n.settype('sis:NetworkType')
#          print "%s %s"%(n.code, n.getattr('xsi:type'))
          print "%s %s"%(n.code, n.getattrxml())
          for s in n.Station:
            print "  %s   %s"%(s.code, s.getattrxml())
            allChanCodes = {}
            for c in s.Channel:
              print "    %s.%s "%(c.locationCode, c.code,)
#              print "    %s.%s "%(c.getattr('locationCode'), c.code,)
              key = "%s.%s"%(c.locationCode, c.code)
              if not key in allChanCodes:
                allChanCodes[key] = []
              allChanCodes[key].append(c)
              if c.Response != None:
                 chanCodeId = checkNRL.getChanCodeId(n, s, c)
                 if chanCodeId in matchSensor:
                    if len(matchSensor[chanCodeId]) > 1:
                       print "WARNING: %s has more than one matching sensor, using first"
                    c.Response = sisxmlparser.SISResponseType()
                    sensorSubResponse = sisxmlparser.SubResponseType()
                    sensorSubResponse.sequenceNumber = 1
                    sensorSubResponse.RESPFile = sisxmlparser.RESPFileType()
                    sensorSubResponse.RESPFile.stageFrom = 1
                    sensorSubResponse.RESPFile.stageTo = 1
                    sensorSubResponse.RESPFile.ValueOf = matchSensor[chanCodeId][0].replace("nrl", NRL_PREFIX)

                    loggerSubResponse = sisxmlparser.SubResponseType()
                    loggerSubResponse.sequenceNumber = 2
                    loggerSubResponse.RESPFile = sisxmlparser.RESPFileType()
                    loggerSubResponse.RESPFile.stageFrom = 2
                    loggerSubResponse.RESPFile.stageTo = -1
                    loggerSubResponse.RESPFile.ValueOf = matchLogger[chanCodeId][0].replace("nrl", NRL_PREFIX)

                    c.Response.SubResponse = [ sensorSubResponse, loggerSubResponse ]



                    
                 if hasattr(c.Response ,'Stage'):
                   print "       %d stages"%(len(c.Response.Stage),)
                   for stage in c.Response.Stage:
                     if hasattr(stage, 'PolesZeros'):
                       print "pz"
                     elif hasattr(stage, 'Coefficients'):
                       print "coef"
                     elif hasattr(stage, 'FIR'):
                       print "fir"
                     elif hasattr(stage, 'Polynomial'):
                       print "poly"
                     elif hasattr(stage, 'Decimation'):
                       print "dec"
                     elif hasattr(stage, 'StageGain'):
                       print "gain"
                     else:
                       print "other resp "

            print "all chan codes: %d"%(len(allChanCodes))
            for key, epochList in allChanCodes.iteritems():
              epochList.sort(key=getStartDate)
              print "%s %d %s %s"%(key, len(epochList), epochList[-1].startDate, epochList[-1].endDate)
            

# Finally after the instance is built export it. 
        out = open("%s.%s"%(args[0], "extstaxml"), 'w')
        rootobj.exportxml(out, 'FDSNStationXML', 'fsx', 0)
#        rootobj.exportxml(sys.stdout, 'FDSNStationXML', 'fsx', 0)



if __name__ == "__main__":
    sys.exit(main())
