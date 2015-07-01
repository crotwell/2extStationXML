#! /usr/bin/python
'''
find unique responses in fdsn stationxml file
'''
import checkNRL as checkNRL
import sisxmlparser2_0 as sisxmlparser

import datetime
import os
import re
import sys

VERBOSE=False

def setVerbose(b):
    VERBOSE = b

def areSameStageType(stageA, stageB):
    for t in ['PolesZeros', 'Coefficients', 'FIR', 'Polynomial']:
        booleanA = hasattr(stageA, t)
        booleanB = hasattr(stageB, t)
        if booleanA != booleanB:
            return (False, "Not same stage type: %s, %s %s"%(t, booleanA, booleanB))
    return True, "ok"

def samePolesZeros(pzA, pzB):
    zerosA = getattr(pzA, 'Zero', [])
    polesA = getattr(pzA, 'Pole', [])
    zerosB = getattr(pzB, 'Zero', [])
    polesB = getattr(pzB, 'Pole', [])
    result = checkNRL.checkMultiple( [
        ("PzTransferFunctionType", pzA.PzTransferFunctionType, pzB.PzTransferFunctionType),
        ("NormalizationFactor", pzA.NormalizationFactor, pzB.NormalizationFactor, 0.001),
        ("NormalizationFrequency", pzA.NormalizationFrequency, pzB.NormalizationFrequency, 0.001),
        ("zero len", len(zerosA), len(zerosB)),
        ("pole len", len(polesA), len(polesB))
    ])
    if not result[0]:
         return result
    checklist = []
    for zi in range(len(zerosA)):
         checklist.append(("%d zero real"%(zi,), float(pzA.Zero[zi].Real.ValueOf), float(pzB.Zero[zi].Real.ValueOf), 0.001))
         checklist.append(("%d zero imag"%(zi,), float(pzA.Zero[zi].Imaginary.ValueOf), float(pzB.Zero[zi].Imaginary.ValueOf), 0.001))
    for pi in range(len(polesA)):
         checklist.append(("%d pole real"%(pi,), float(pzA.Pole[pi].Real.ValueOf), float(pzB.Pole[pi].Real.ValueOf), 0.001))
         checklist.append(("%d pole imag"%(pi,), float(pzA.Pole[pi].Imaginary.ValueOf), float(pzB.Pole[pi].Imaginary.ValueOf), 0.001))
    result = checkNRL.checkMultiple(checklist)
    return result

def sameCoefficients(coefA, coefB):
    numerA = getattr(coefA, 'Numerator', [])
    denomA = getattr(coefA, 'Denominator', [])
    numerB = getattr(coefB, 'Numerator', [])
    denomB = getattr(coefB, 'Denominator', [])
    result = checkNRL.checkMultiple( [
        ("CfTransferFunctionType", coefA.CfTransferFunctionType, coefB.CfTransferFunctionType),
        ("numerator len", len(numerA), len(numerB)),
        ("denominator len", len(denomA), len(denomB))
    ])
    if not result[0]:
         return result
    checklist = []
    for zi in range(len(numerA)):
         checklist.append(("%d numerator"%(zi,), float(coefA.Numerator[zi].ValueOf), float(coefB.Numerator[zi].ValueOf), 0.001))
    for pi in range(len(denomA)):
         checklist.append(("%d denominator"%(pi,), float(coefA.Denominator[pi].ValueOf), float(coefB.Denominator[pi].ValueOf), 0.001))
    result = checkNRL.checkMultiple(checklist)
    return result
 
    
def sameFIR(firA, firB):
    result = checkNRL.checkMultiple( [
        ('Symmetry', firA.Symmetry, firB.Symmetry),
        ('len NumeratorCoefficient', len(firA.NumeratorCoefficient), len(firB.NumeratorCoefficient))
    ] )
    if not result[0]:
         return result
    checklist = []
    for i in range(len(firA.NumeratorCoefficient)):
         checklist.append(("%d NumeratorCoefficient"%(i,), float(firA.NumeratorCoefficient[i].ValueOf), float(firB.NumeratorCoefficient[i].ValueOf), 0.001))
    result = checkNRL.checkMultiple(checklist)
    return result

def sameDecimation(stageA, stageB):
    booleanA = hasattr(stageA, 'Decimation')
    booleanB = hasattr(stageB, 'Decimation')
    if booleanA != booleanB:
        return (False, "Not same stage %s: %s %s"%('Decimation', booleanA, booleanB))
    if booleanA:
        result = checkNRL.checkMultiple( [
            ('InputSampleRate', stageA.Decimation.InputSampleRate.ValueOf, stageB.Decimation.InputSampleRate.ValueOf, 0.001),
            ('Factor', stageA.Decimation.Factor, stageB.Decimation.Factor)
            ] )
        return result
    else:
        return True, "ok"

def sameGain(stageA, stageB):
    booleanA = hasattr(stageA, 'StageGain')
    booleanB = hasattr(stageB, 'StageGain')
    if booleanA != booleanB:
        return (False, "Not same stage %s: %s %s"%('StageGain', booleanA, booleanB))
    if booleanA:
        result = checkNRL.checkMultiple( [
            ('Value', stageA.StageGain.Value, stageB.StageGain.Value, 0.001),
            ('Frequency', stageA.StageGain.Frequency, stageB.StageGain.Frequency, 0.001)
            ] )
        return result
    else:
        return True, "ok"

    

def areSameStage(stageA, stageB):
    result = areSameStageType(stageA, stageB)
    if not result[0]:
        return result
    if hasattr(stageA, 'PolesZeros'):
        result = samePolesZeros(stageA.PolesZeros, stageB.PolesZeros)
    elif hasattr(stageA, 'Coefficients'):
        result = sameCoefficients(stageA.Coefficients, stageB.Coefficients)
    elif hasattr(stageA, 'FIR'):
        result = sameFIR(stageA.FIR, stageB.FIR)
    elif hasattr(stageA, 'Polynomial'):
        result = False, "don't know how to do polynomial yet"
    if not result[0]:
        return result
    result = sameDecimation(stageA, stageB)
    if not result[0]:
        return result
    return sameGain(stageA, stageB)
    


def areSameResponse(respA, respB):
    stageA = getattr(respA, 'Stage', [])
    stageB = getattr(respB, 'Stage', [])
    if VERBOSE: print "areSameResponse: "
    result = checkNRL.checkIntEqual("num stages", len(stageA), len(stageB))
    if not result[0]:
        if VERBOSE: print "not same num stages %s %s %d %d"%(result[0], result[1], len(stageA), len(stageB))
        return result
    for i in range(0, len(stageA)):
        result = areSameStage(respA.Stage[i], respB.Stage[i])
        if not result[0]:
            result = False, "Stage %d %s"%(i+1,result[1])
            if VERBOSE: print result[0]
            return result
    return True, "ok"

def uniqueResponses(staxml):
    uniqResponse = []
    for n in staxml.Network:
      for s in n.Station:
        for c in s.Channel:
          chanCode = checkNRL.getChanCodeId(n, s, c)
          foundMatch = None
          if VERBOSE: print "chanCode %s "%(chanCode, )
#          print "chanCode %s numStage = %d"%(chanCode, len(c.Response.Stage),)
          for uResp in uniqResponse:
#              try:
              result = areSameResponse(c.Response, uResp[1])
#              except:
#                e =  sys.exc_info()[0]
#                print "Error comparing %s, %s"%(uResp[0], e)
#                result = False, " %s"%(e,)
#                return
              if VERBOSE: print "areSame %s: %s"%(result[0], result[1],)
              if result[0]:
                  foundMatch = uResp
                  break
          if foundMatch is None:
              uniqResponse.append( ( chanCode, c.Response, [ chanCode] ) ) 
              if VERBOSE: print "no match %d"%(len(uniqResponse),)
          else:
              foundMatch[2].append(chanCode)
              if VERBOSE: print "found match %s  %s"%(chanCode, foundMatch[0])
    return uniqResponse

def usage():
    print "python uniqueResponses <staxml>"


def main():
    args = sys.argv[1:]
    if len(args) == 0:
        usage()
        return
    if not os.path.isfile(args[0]):
        print "Can't find file %s"%(args[0],)
        return
    staxml = sisxmlparser.parse(args[0])
    print "Find unique responses"
    uniq = uniqueResponses(staxml)
    print "NRL check unique responses"
    nrledUniq = checkNRL.checkRespListInNRL('nrl', uniq, 'logger_samp_rate.sort')
    numChans = 0
    print "found %d uniq responses "%(len(uniq), )
    for x in nrledUniq:
      for xc in x[2]:
        sys.stdout.write("%s "%(xc,))
      sys.stdout.write("  NRL: ")
      sys.stdout.write("  Sensor: ")
      for s in x[3]:
        sys.stdout.write("%s "%(s,))
      sys.stdout.write("  Logger: ")
      for l in x[4]:
        sys.stdout.write("%s "%(l,))
     
      print ""

if __name__ == '__main__':
    main()

