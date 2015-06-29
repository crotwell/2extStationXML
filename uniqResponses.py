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


def areSameStageType(stageA, stageB):
    for t in ['PolesZeros', 'Coefficients', 'FIR', 'Polynomial']:
        booleanA = hasattr(stageA, t)
        booleanB = hasattr(stageB, t)
        if booleanA != booleanB:
            return (False, "Not same stage type: %s, %b %b"%(t, booleanA, booleanB))
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
         checklist.append(("%d zero real"%(zi,), float(coefA.Numerator[zi].ValueOf), float(coefB.Numerator[zi].ValueOf), 0.001))
    for pi in range(len(denomA)):
         checklist.append(("%d pole real"%(pi,), float(coefA.Denominator[pi].ValueOf), float(coefB.Denominator[pi].ValueOf), 0.001))
    result = checkNRL.checkMultiple(checklist)
    return result
 
    
def sameFIR(firA, firB):
    result = checkNRL.checkMultiple( [
        ('Symmetry', firA.Symmetry, firB.Symmetry)
        ('len NumeratorCoefficient', len(firA.NumeratorCoefficient), len(firB.NumeratorCoefficient))
    ] )
    if not result[0]:
         return result
    checklist = []
    for i in range(len(firA.NumeratorCoefficient)):
         checklist.append(("%d NumeratorCoefficient"%(i,), float(firA.NumeratorCoefficient[i].ValueOf), float(firB.NumeratorCoefficient[i].ValueOf), 0.001))
    result = checkNRL.checkMultiple(checklist)
    return result

    

def areSameStage(stageA, stageB):
    result = areSameStageType(stageA, stageB)
    if not result[0]:
        return result
    if hasattr(stageA, 'PolesZeros'):
        return samePolesZeros(stageA.PolesZeros, stageB.PolesZeros)
    if hasattr(stageA, 'Coefficients'):
        return sameCoefficients(stageA.Coefficients, stageB.Coefficients)
    if hasattr(stageA, 'FIR'):
        return sameFIR(stageA.FIR, stageB.FIR)
    if hasattr(stageA, 'Polynomial'):
        return False, "don't know how to do polynomial yet"

    return False, "unknown stage type: %s"%(stageA,)

def areSameResponse(respA, respB):
    print "areSameResponse: "
    result = checkNRL.checkIntEqual("num stages", len(respA.Stage), len(respB.Stage))
    if not result[0]:
        print "not same num stages %s %s %d %d"%(result[0], result[1], len(respA.Stage), len(respB.Stage))
        return result
    for i in range(0, len(respA.Stage)):
        print i
        result = areSameStage(respA.Stage[i], respB.Stage[i])
        if not result[0]:
            return False, "Stage %d %s"%(i+1,result[1])
    return True, "ok"

def uniqueResponses(staxml):
    uniqResponse = []
    for n in staxml.Network:
      for s in n.Station:
        for c in s.Channel:
          chanCode = checkNRL.getChanCodeId(n, s, c)
          foundMatch = None
          print
          print "chanCode %s numStage = %d"%(chanCode, len(c.Response.Stage),)
          for uResp in uniqResponse:
              result = areSameResponse(c.Response, uResp[1])
              print "areSame %s: %s"%(result[0], result[1],)
              if result[0]:
                  foundMatch = uResp
                  break
          if foundMatch is None:
              uniqResponse.append( ( chanCode, c.Response, [ chanCode] ) ) 
              print "no match %d"%(len(uniqResponse),)
          else:
              foundMatch[2].append(chanCode)
              print "found match %s  %s"%(chanCode, foundMatch[0])
    return uniqResponse

def usage():
    print "python uniqueResponses <staxml>"


def main():
    checkNRL.setVerbose(True)
    args = sys.argv[1:]
    if len(args) == 0:
        usage()
        return
    if not os.path.isfile(args[0]):
        print "Can't find file %s"%(args[0],)
        return
    staxml = sisxmlparser.parse(args[0])
    uniq = uniqueResponses(staxml)
    numChans = 0
    print "found %d uniq responses for %d channels"%(len(uniq), numChans)
    for x in uniq:
        print "%s  %s"%(x[0], x[2])

if __name__ == '__main__':
    main()

