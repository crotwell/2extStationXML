#! /usr/bin/python
'''
Interact with the NRL and parse RESP files.
'''


import sisxmlparser2_0 as sisxmlparser

import argparse
import datetime 
import os
import re
import sys

#VERBOSE = True
VERBOSE = False

USAGE_TEXT = """
Usage: python <Parser>.py <in_xml_file>
"""

TYPE = "type"

def setVerbose(b):
    VERBOSE = b

def usage():
    print USAGE_TEXT
    sys.exit(1)

def _addBlocketteField(blockette, field, value):
#    print "%s %s %s"%(blockette, field, value)
    if field in blockette:
        if isinstance(blockette[field], (tuple, basestring)):
            tmp = blockette[field]
            blockette[field] = [ tmp, value]
        elif isinstance(blockette[field], (list,)):
            blockette[field].append(value)
        else:
            raise UnknownTypeInBlockette(blockette[field])
    else:
        blockette[field] = value
    return blockette

def _appendBlocketteField(blockette, field, value):
#    print "%s %s %s"%(blockette, field, value)
    if field in blockette:
        if isinstance(blockette[field], (tuple, basestring)):
            raise Exception("can only append to lists fields "+blockette[field])
        elif isinstance(blockette[field], (list,)):
            blockette[field].append(value)
        else:
            raise Exception("can only append to lists fields "+blockette[field])
    else:
        blockette[field] = [value,]
    return blockette



def loadResp(filename):
    resp = []
    blocketteFieldPattern = re.compile(r'^B(\d\d\d)F(\d\d)\s+(\S.+):\s+(\S.*)$')
    emptyLocationPattern = re.compile(r'^B(\d\d\d)F(\d\d)\s+(Location):\s+()$')
    poleZeroFieldPattern = re.compile(r'^B(\d\d\d)F(\d\d\-\d\d)\s+(\d+\s+\S.*)$')
    prevB = None
    blockette = None
    with open(filename, 'r') as f:
        for line in f:
           if line[0] == '#':
               if "-----" in line:
                   # new blockette
                   prevB = None
               continue
           elif line[0] == 'B':
               mb = blocketteFieldPattern.match(line)
               if mb is None:
                 mb = emptyLocationPattern.match(line)
               if mb is not None:
                 b = mb.group(1)
                 f = mb.group(2)
                 label = mb.group(3)
                 v = mb.group(4)
               else:
                 mpz = poleZeroFieldPattern.match(line)
                 if mpz is not None:
                   b = mpz.group(1)
                   f = mpz.group(2)
                   vtmp = mpz.group(3).split()
                   v = []
                   v.append( int(vtmp[0]))
                   for i in range(1, len(vtmp)):
                      v.append(float(vtmp[i]))
                 else:
                   raise Exception( "no pattern match: %s in %s"%(line,filename))
               if b != prevB:
                   if blockette is not None:
                       resp.append(cleanBlockette(blockette))
                   blockette = {}
                   blockette[TYPE] = b
                   prevB = b
               if mb is not None:
                   blockette = _addBlocketteField(blockette, f, v) 
               else:
                   blockette = _appendBlocketteField(blockette, f, v) 
    resp.append(cleanBlockette(blockette))
    return resp

def cleanBlockette(b):
    #print "clean %s  %s"%(b[TYPE], stageForBlockette(b)) 
    if b[TYPE] == '053' or b[TYPE] == '054':
      b['04'] = int(b['04'])
    if b[TYPE] == '058' or b[TYPE] == '057':
      b['03'] = int(b['03'])
    return b

def stageForBlockette(b):
    if b[TYPE] == '050':
       return None
    if b[TYPE] == '052':
       return None
    if b[TYPE] == '053':
       return b['04']
    if b[TYPE] == '058':
       return b['03']
    if b[TYPE] == '054':
       return b['04']
    if b[TYPE] == '057':
       return b['03']
    raise Exception("unknown blockette type: %s"%(b[TYPE],))
    
def findRespBlockette(blockette, stage, blocketteType):
    for b in blockette:
        if b[TYPE] == blocketteType and stage == stageForBlockette(b):
           return b
    if VERBOSE: print "can't find b%s for stage %s"%(blocketteType, stage)
    return None

def checkStringEqual(reason, valA, valB):
    if valA == valB:
       return True, "ok"
    else:
       return False, "%s : '%s' != '%s'"%(reason, valA, valB)

def checkIntEqual(reason, valA, valB):
    if valA == valB:
       return True, "ok"
    else:
       return False, "%s: %d!=%d"%(reason, valA, valB)

def checkFloatEqual(reason, valA, valB, tolPercent):
    #print "check float %s, %f, %f, < %f"%(reason, valA, valB, tolPercent)
    if valA == 0.0:
       if valB == 0.0:
          return True, "ok"
       else:
          return False, "%s %f != %f (tol %% %f)"%(reason, valA, valB, tolPercent)
    elif abs((valA - valB)/valA) < tolPercent:
       return True, "ok"
    else:
       return False, "%s %f != %f (tol %% %f)"%(reason, valA, valB, tolPercent)


def checkItem(item):
    if VERBOSE: print "check %s"%(item,)
    result = (False, "do not know how to check %s"%(item,))
    if len(item) == 4 and isinstance(item[1], (int,float)) and isinstance(item[2], (int,float)):
        result = checkFloatEqual(item[0], item[1], item[2], item[3])
    elif len(item) == 3 and isinstance(item[1], int) and isinstance(item[2], int):
        result = checkIntEqual(item[0], item[1], item[2])
    elif len(item) == 3 and isinstance(item[1], basestring) and isinstance(item[2], basestring):
        result = checkStringEqual(item[0], item[1], item[2])
    else:
        raise Exception("unknown check tuple %s"%(item,))
    if VERBOSE and not result[0]: print "Fail item %s -> %s"%(item, result)
    return result
      
def checkMultiple(list):
    for item in list:
      result = checkItem(item)
      if not result[0]:
        return result
    return (True, "ok")

def areSimilarStageB53(staxml, resp):
    result = (False, "can't file blockette to match %s"%(resp[TYPE],))
    if hasattr(staxml,'PolesZeros') and resp[TYPE] == '053':
       zeros = getattr(staxml.PolesZeros, 'Zero', [])
       poles = getattr(staxml.PolesZeros, 'Pole', [])
       result = checkMultiple( [
        ("A0 norm factor", float(staxml.PolesZeros.NormalizationFactor), float(resp['07']), 0.001),
        ("num zeros", len(zeros), int(resp['09'])),
        ("num poles", len(poles), int(resp['14']))
       ])
       if not result[0]:
         return result
       checklist = []
       for zi in range(len(zeros)):
             checklist.append(("%d zero real"%(zi,), float(zeros[zi].Real.ValueOf), float(resp['10-13'][zi][1]), 0.001))
             checklist.append(("%d zero imag"%(zi,), float(zeros[zi].Imaginary.ValueOf), float(resp['10-13'][zi][2]), 0.001))
       for pi in range(len(poles)):
             checklist.append(("%d pole real"%(pi,), float(poles[pi].Real.ValueOf), float(resp['15-18'][pi][1]), 0.001))
             checklist.append(("%d pole imag"%(pi,), float(poles[pi].Imaginary.ValueOf), float(resp['15-18'][pi][2]), 0.001))
       result = checkMultiple(checklist)
    return result

def areSimilarStageB54(staxml, resp):
    result = (False, "can't file blockette to match %s"%(resp[TYPE],))
    if resp[TYPE] == '054' and hasattr(staxml,'Coefficients'):
       checklist = []
       numerators = getattr(staxml.Coefficients, 'Numerator', [])
       denominators = getattr(staxml.Coefficients, 'Denominator', [])
       result = checkMultiple( [
         ("stage num", int(staxml.number), resp['04']),
         ("Num numerators", len(numerators), int(resp['07'])),
         ("Num denominators", len(denominators), int(resp['10'])) ])
       if not result[0]:
           return result
       for ni  in range(len(numerators)):
             checklist.append(("%d numerator "%(ni,), float(numerators[ni].ValueOf), float(resp['08-09'][ni][1]), 0.001))
       for di in range(len(denominators)):
             checklist.append(("%d denominator "%(di,), float(denominators[di].ValueOf), float(resp['11-12'][di][1]), 0.001))
       result = checkMultiple(checklist)
    return result

def areSimilarStageB57(staxml, resp):
    result = (False, "can't file blockette to match %s"%(resp[TYPE],))
    if resp[TYPE] == '057' and hasattr(staxml,'Decimation'):
       result = checkMultiple(  [
        ("Input Samp Rate", float(staxml.Decimation.InputSampleRate.ValueOf), float(resp['04']), 0.001),
        ("Factor", int(staxml.Decimation.Factor), int(resp['05'])),
       ])
    return result

def areSimilarStageB58(staxml, resp):
    result = (False, "can't file blockette to match %s"%(resp[TYPE],))
    if resp[TYPE] == '058' and hasattr(staxml,'StageGain'):
       result = checkMultiple( [
        ("Gain Value", float(staxml.StageGain.Value), float(resp['04']), 0.001),
        ("Gain Frequency", float(staxml.StageGain.Frequency), float(resp['05'].split()[0]), 0.001)
       ])
    return result

def areSimilarSensor(staxmlResp, nrlResp):
    if not hasattr(staxmlResp, 'Stage'):
        return False, "no Stage in staxml"
    stageNum = 1
    b53 = findRespBlockette(nrlResp, stageNum, '053')
    if b53 is not None:
       result = areSimilarStageB53(staxmlResp.Stage[0], b53)
    else:
       result = False,"blockette53 not found"
    if not result[0]:
       return result
    b58 = findRespBlockette(nrlResp, stageNum, '058')
    if b58 is not None:
       result = areSimilarStageB58(staxmlResp.Stage[0], b58)
    else:
       result = False,"blockette58 not found"
    return (result[0], result[1], 1, 1)

def areSimilarLogger(staxmlResp, nrlResp):
    '''
    returns (False, reason)
    returns (True, reason, staxml stage begin, nrl stage begin, nrl stage end)
    '''
    atodStageStaxml = 0
    atodStageNRL = 3 # I think Mary always uses 3 as A to D stage
    if not hasattr(staxmlResp, 'Stage'):
        return False, "no Stage in staxml"
    for staxmlStage in staxmlResp.Stage:
        if hasattr(staxmlStage, 'Coefficients'):
            if (staxmlStage.Coefficients.InputUnits.Name == 'V' or staxmlStage.Coefficients.InputUnits.Name.lower() == 'volts'  or staxmlStage.Coefficients.InputUnits.Name.lower() == 'volt') and (staxmlStage.Coefficients.OutputUnits.Name.lower() == 'count' or staxmlStage.Coefficients.OutputUnits.Name.lower() == 'counts'):
                atodStageStaxml = staxmlStage.number
                break
    
    result = checkItem(("num logger stages", len(staxmlResp.Stage)-atodStageStaxml, stageForBlockette(nrlResp[-2])-atodStageNRL))
    if not result[0]:
        return result
    preampStageNRL = atodStageNRL - 1
    preampStageStaxml = atodStageStaxml - 1
    if VERBOSE: print "preamp logger stage is %d"%(preampStageNRL,)
    b58 = findRespBlockette(nrlResp, preampStageNRL, '058')
    if b58 is not None:
        result = areSimilarStageB58(staxmlResp.Stage[preampStageStaxml-1], b58)
        if not result[0]:
            return False,"preamp stage %s: %s"%(preampStageNRL, result[1])
    else:
        return False,"Can't find b58 for preamp stage %d"%(preampStageNRL,)
    loggerStageNRL = atodStageNRL
    loggerStageStaxml = atodStageStaxml
    b58 = findRespBlockette(nrlResp, loggerStageNRL, '058')
    if b58 is None:
        result = False,"stage %s blockette58 not found"%(loggerStageNRL,)
    else:
        if VERBOSE: print "logger stage is %d"%(loggerStageNRL,)
        while b58 is not None:
            if b58 is not None:
              result = areSimilarStageB58(staxmlResp.Stage[loggerStageStaxml-1], b58)
              if not result[0]:
                  return False,"stage %s: %s"%(loggerStageStaxml, result[1])
            else:
              return False,"Can't find b58 for stage %d"%(loggerStageNRL,)
            b57 = findRespBlockette(nrlResp, loggerStageNRL, '057')
            if b57 is not None:
              result = areSimilarStageB57(staxmlResp.Stage[loggerStageStaxml-1], b57)
              if not result[0]:
                  return False,"stage %s: %s"%(loggerStageNRL, result[1])
            else:
              return False,"Can't find b57 for stage %d"%(loggerStageNRL,)
            b54 = findRespBlockette(nrlResp, loggerStageNRL, '054')
            if b54 is not None:
              result = areSimilarStageB54(staxmlResp.Stage[loggerStageStaxml-1], b54)
              if not result[0]:
                  return False,"stage %s: %s"%(loggerStageNRL, result[1])
            loggerStageNRL+=1
            loggerStageStaxml+=1
            b58 = findRespBlockette(nrlResp, loggerStageNRL, '058')
        if b54 is None and len(staxmlResp.Stage) > loggerStageStaxml:
            return False,"more stages in staxml than in resp %d > %d"%(len(staxmlResp.Stage), loggerStageStaxml)
    return (result[0], result[1],  preampStageStaxml,  preampStageNRL, loggerStageNRL-1 )

def printBlockettes(r):
    for b in r:
      print "Blockette %s ##########"%(b['type'],)
      for key in sorted(b.iterkeys()):
        print "  %s  %s"%(key, b[key])

def getChanCodeId(n, s, c):
        return "%s.%s.%s.%s_%s"%(n.code, s.code, c.locationCode, c.code, c.startDate.isoformat())

def saveFinalSampRate(nrlDir):
    outfile = open(os.path.join(nrlDir, 'logger_sample_rate.sort'), 'w')
    dataloggerDir = os.path.join(nrlDir, 'dataloggers')
    for root, dirs, files in os.walk(dataloggerDir):
      for respfile in files:
        if respfile.startswith("RESP"):
            if VERBOSE: print "try %s"%(respfile,)
            r = loadResp(os.path.join(root, respfile))
            finalSampRate = 0
            for b in r:
                if b['type'] == '057':
                    sampRate = b['04']
                    decFactor = b['05']
                    finalSampRate = float(sampRate)/int(decFactor)
            outfile.write("%s %s\n"%(finalSampRate, os.path.join(root, respfile)))

def possibleSampRateMatch(respfile, staxml, loggerRateIndex):
    for n in staxml.Network:
        for s in n.Station:
            for c in s.Channel:
                if respfile in loggerRateIndex and c.SampleRate.ValueOf == loggerRateIndex[respfile]:
                    return True
    return False

def checkRespInNRL(nrlDir, staxml, areSimilarFunc, loggerRateIndex = None):
    matchDict = dict()
    if VERBOSE: print "walk %s"%(nrlDir,)
    for root, dirs, files in os.walk(nrlDir):
      for respfile in files:
        if respfile.startswith("RESP") and (loggerRateIndex is None or possibleSampRateMatch(os.path.join(root, respfile), staxml, loggerRateIndex)):
            if VERBOSE: print "try %s"%(respfile,)
            r = loadResp(os.path.join(root, respfile))
            for n in staxml.Network:
              for s in n.Station:
                for c in s.Channel:
                  chanCode = getChanCodeId(n, s, c)
                  if hasattr(c, 'Response'):
                    result = areSimilarFunc(c.Response, r)
                    if result[0]:
                      if VERBOSE: print "%s found match %s"%(chanCode, respfile,)
                      if not chanCode in matchDict:
                          matchDict[chanCode] = []
                      matchDict[chanCode].append( ( os.path.join(root, respfile), result[2], result[3] ) )
                    else:
                      if VERBOSE: print "FAIL %s match %s: %s"%(chanCode, respfile, result[1])
    return matchDict

def checkRespListInNRL(nrlDir, respList, loggerRateIndex = None):
    '''
    respList is list of tuples (name, response, chanCodeList)
    return is list of tuples (name, response, chanCodeList, sensorNrlUrl, loggerNrlUrl)
    where NRLurl is None if not a NRL response.
    Sensor is assumed to be stage 1, Preamp is stage 2 and logger is stage 3 to end.
    '''
    outList = []
    for name, chanResp, chanCodeList in respList:
        outList.append( [ name, chanResp, chanCodeList, [], [] ] )
    if VERBOSE: print "walk %s"%(nrlDir,)
    for root, dirs, files in os.walk("%s/sensors"%(nrlDir,)):
      for respfile in files:
        if respfile.startswith("RESP"): 
            if VERBOSE: print "try %s"%(respfile,)
            r = loadResp(os.path.join(root, respfile))
            for respTuple in outList:
                name, chanResp, chanCodeList, sss, lll = respTuple
                resultSensor = areSimilarSensor(chanResp, r)
                if resultSensor[0]:
                  if VERBOSE: print "%s found Sensor match %s"%(name, respfile,)
                  sss.append( ( os.path.join(root, respfile), resultSensor[2], resultSensor[3] ) )
    for root, dirs, files in os.walk("%s/dataloggers"%(nrlDir,)):
      for respfile in files:
        if respfile.startswith("RESP"): 
            if VERBOSE: print "try %s"%(respfile,)
            r = None # delay loading until a samp rate match
            for respTuple in outList:
                name, chanResp, chanCodeList, sss, lll = respTuple
                if respfile not in loggerRateIndex or c.SampleRate.ValueOf == loggerRateIndex[respfile]:
                    if r is None:
                        r = loadResp(os.path.join(root, respfile))
                    resultLogger = areSimilarLogger(chanResp, r)
                    if resultLogger[0]:
                      if VERBOSE: print "%s found logger match %s"%(name, respfile,)
                      lll.append( ( os.path.join(root, respfile), resultLogger[2], resultLogger[3], resultLogger[4] ) )
                    else:
                      if VERBOSE: print "FAIL %s match %s: %s"%(chanCode, respfile, result[1])
    return outList


def loadRespfileSampleRate(loggerSampFile):
    out = dict()
    for line in open(loggerSampFile, 'r'):
      words = line.split()
      out[words[1]] = float(words[0])
    return out

def checkNRL(nrlDir, staxml):
    '''
    obsolete, faster to check for unique responses first, then walk the nrl
    '''
    loggerRateIndex = loadRespfileSampleRate('logger_samp_rate.sort')
    print "loggerRateIndex has %d entries"%(len(loggerRateIndex,))

    print "Sensor Check"
    matchSensor = checkRespInNRL("%s/sensors"%(nrlDir,), staxml, areSimilarSensor)
    print "Logger Check"
    matchLogger = checkRespInNRL("%s/dataloggers"%(nrlDir,), staxml, areSimilarLogger, loggerRateIndex)
#    loggerRateIndex = loadRespfileSampleRate('rt130_logger_samp_rate.sort')
#    matchLogger = checkNRL("nrl_rt130/dataloggers", staxml, areSimilarLogger, loggerRateIndex)
    return (matchSensor, matchLogger)


def main():
    parser = argparse.ArgumentParser(description='Check NRL, generate sample rate index.')
    parser.add_argument('-s', '--stationxml', help="input FDSN StationXML file, often retrieved from http://service.iris.edu/fdsnws/station/1/")
    parser.add_argument('--nrl', default='nrl', help="path to NRL")
    parser.add_argument('--samplerate', action="store_true", help="Generate the sample rate index file inside the nrl directory.")
    parseArgs = parser.parse_args()
    args = sys.argv[1:]
    if len(args) == 0:
        usage()
        return
    if parseArgs.samplerate:
        saveFinalSampRate(parseArgs.nrl)
        return
    if not os.path.isfile(parseArgs.stationxml):
        print "Can't find file %s"%(parseArgs.stationxml,)
        return
    staxml = sisxmlparser.parse(parseArgs.stationxml)
    (matchSensor, matchLogger) = checkNRL(parseArgs.nrl, staxml)

    for n in staxml.Network:
      for s in n.Station:
        for c in s.Channel:
          chanCode = getChanCodeId(n, s, c)
          print "%s matches:"%(chanCode,)
          if chanCode in matchSensor and len(matchSensor[chanCode])>0:
            if len(matchSensor[chanCode]) > 1 :
              print "  %s MultipleMatch %d  ##############"%(chanCode, len(matchSensor[chanCode]),)
            for rf in matchSensor[chanCode]:
              print "  sensor: %s"%(rf[0],)
          else:
            print "  no sensor match found"
          if chanCode in matchLogger and len(matchLogger[chanCode])>0:
            if len(matchLogger[chanCode]) > 1 :
              print "  %s MultipleMatch %d  ##############"%(chanCode, len(matchLogger[chanCode]),)
            for rf in matchLogger[chanCode]:
              print "  logger: %s"%(rf[0],)
          else:
            print "  no logger match found"
 

if __name__ == "__main__":
    sys.exit(main())

