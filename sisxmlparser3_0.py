#! /usr/bin/python

'''
sisxmlparser3_0.py
2020-05-28

This module contains classes to parse an XML document in the extended
FDSNStationXML format as defined in sis_extension.xsd (v3.0)
http://anss-sis.scsn.org/xml/ext-stationxml/3.0/sis_extension.xsd and convert
it into python objects. This can be output as an XML file or as a python
dictionary.

Author: Prabha Acharya, ANSS SIS Development Team, SCSN
Email: sis-help@gps.caltech.edu

'''

import argparse
import sys
import re as re_
import base64
import datetime as datetime_
from lxml import etree as etree_
import html
import os


def parsexml_(*args, **kwargs):
    kwargs['parser'] = etree_.ETCompatXMLParser()
    doc = etree_.parse(*args, **kwargs)
    return doc

class SISError(Exception):
    def __init__(self, value):
        Exception.__init__(self, value)

# Globals
#

Namespace_extract_pat_ = re_.compile(r'{(.*)}(.*)')

# nskey: (namespaceuri, prefix in output, schemalocation, schemaversion)
nsd = {'xsi' : ('http://www.w3.org/2001/XMLSchema-instance', 'xsi', '', ''),
       'fsx' : ('http://www.fdsn.org/xml/station/1','', 'http://www.fdsn.org/xml/station/fdsn-station-1.1.xsd', '1.1'),
       'iris' : ('http://www.fdsn.org/xml/station/1/iris','', '', ''),
       'sis' : ('http://anss-sis.scsn.org/xml/ext-stationxml/3.0', 'sis', 'https://anss-sis.scsn.org/xml/ext-stationxml/3.0/sis_extension.xsd', '3.0')
      }

insd = dict((v[0], k) for k, v in nsd.items())

# map of xml datatypes (string) to python datatypes
datatype_map = dict(text=str,
    integer=int,
    date = datetime_.datetime,
    double=float,
    boolean=bool,
    )

docnsprefixmap = {}     #value is set when parsing the document.

INDENT = '  '


def get_ns_nodename(node):
    [nsuri, nodename] = Namespace_extract_pat_.match(node.tag).groups()
    ns = None
    if nsuri in insd:
        ns = insd[nsuri]

    return ns, nodename

def get_ns_name_type(node):
    ns, name = get_ns_nodename(node)
    typensname = get_ns_type(node.attrib)
    return ns, name, typensname

def get_ns_type(attrib):
    typekey = '{http://www.w3.org/2001/XMLSchema-instance}type'
    if typekey in attrib:
        nstype = attrib[typekey]
        return get_remapped_type(nstype)
    else:
        return None

def get_remapped_type(nstype):
    ''' Accept a string of the form nsprefix:xmltype like ns2:RootType and remap to sis:RootType '''
    try:
        ns, type = nstype.split(':')
    except ValueError as e:
        #No prefix, that means use a default prefix None
        ns = None

    remappedprefix = None
    if ns in docnsprefixmap:
        remappedprefix = nsd[docnsprefixmap[ns]][1]
    if remappedprefix:
        return f'{remappedprefix}:{type}'
    else:
        return type


def parse_datetime(input_data):
    '''Parse an xml date string with timezone information.
       Return a datetime object with time in UTC'''

    fmt_tz = ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S.%f%z') # date string with time offset specified as +-HH:SS
    fmt_z = ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S.%fZ') # date string ending with Z indicating UTC
    fmt_no_tz = ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f') # no timezone given in string, assume UTC
    dt = None
    for fmt in fmt_tz:
        try:
            dt = datetime_.datetime.strptime(input_data, fmt)
            dt = dt.astimezone(datetime_.timezone.utc)
            break
        except ValueError:
            pass

    else:   # didnt find a dt in the earlier loop try formats where it is UTC or assumed to be UTC
        for fmt in fmt_z + fmt_no_tz:
            try:
                dt = datetime_.datetime.strptime(input_data, fmt).replace(tzinfo=datetime_.timezone.utc)
                break
            except ValueError:
                pass

    if not dt:
        raise ValueError()
    return dt


def cast_to_datatype(datatype, v, node=None):
    # if it is a text type, then return as is. Ensure "" is returned as "" and not changed into None.
    if datatype == 'text':
        return v

    if v is None or v =='':
        return None

    if datatype_map[datatype] == type(v):
        return v

    val = None
    try:
        if datatype == 'double':
            val = float(v)
        elif datatype == 'integer':
            val = int(v)
        elif datatype == 'boolean':
            if v.lower() in ('true', '1'):
                val=True
            elif v.lower() in ('false', '0'):
                val=False
            else:
                raise ValueError()
        elif datatype == 'date':
            val = parse_datetime(v)
        else:
            raise SISError(f'Invalid datatype: {datatype} for {node}')
    except(TypeError, ValueError) as e:
        raise SISError(f'Expected datatype: {datatype}. Received invalid value {v} in {node}')
    return val

# Special string Formats for formatting decimals for output
FMT_DEC_1 = '{0:.1f}'
FMT_DEC_6 = '{0:.6f}'
FMT_EXP_6 = '{0:.6e}'

class SISBase(object):
    '''Base class for the extended FDSN StationXML.'''
    ELEMS = () #for each element create a tuple with name, datatype, isrequired, ismultivalue
    ATTRIBS = (('xsi:type', 'text', False, False), )
    NS = '' #Set the XML namespace for each class. Set 'fsx' for types in FDSNStationXML and 'sis' for the types in the SIS extension.
    EXTNS = ''  # Set a value only when the extension is in a different namespace from the super class
    EXTTYPE = '' # Set a value only for the sis types that extend from types defined in FDSNStationXML. Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = '' #Set a value only when the extension is in a different namespace from the super class

    def __init__(self, **kw):
        ''' Called when python object is built by script, not called when parsing XML file'''
        self.elemdict = dict([(e[0], e[1:]) for e in self.ELEMS])
        self.attribdict = dict([(e[0], e[1:]) for e in self.ATTRIBS])
        self.allowed_attr_types = [(t[0], t[1]) for t in self.ATTRIBS + self.ELEMS]
        self.allowed_attrs = [t[0] for t in self.ATTRIBS + self.ELEMS]
        self.reqdattrs = [t[0] for t in self.ATTRIBS + self.ELEMS if t[2]]
        self.extnstype = f'{self.EXTNS}:{self.EXTTYPE}' if self.EXTNS and self.EXTTYPE else ''
        if self.extnstype:
            self.settype(self.extnstype)
        for e, t, isreqd, ismulti in self.ATTRIBS + self.ELEMS:
            if e in kw:
                v = kw.pop(e)
                if type(t) == str:
                    # basic datatypes, cast it to the expected type
                    if ismulti:
                        val = [cast_to_datatype(t, li, e) for li in v]
                    else:
                        val = cast_to_datatype(t, v, e)
                    setattr(self, e, val)
                else:
                    # complex type.
                    if ismulti:
                        childobjs = []
                        for val in v:
                            if type(val) == dict:
                                child = t(**val)
                            else:
                                child = val
                            childobjs.append(child)
                        setattr(self, e, childobjs)
                    else:
                        if type(v) == dict:
                            child = t(**v)
                        else:
                            child = v
                        setattr(self, e, child)
        if kw:
            raise SISError(f'Unexpected keys {kw}')

    def settype(self, type):
        setattr(self, 'xsi:type', type)

    def build(self, node):
        '''Read and set the attributes for this node and call function to read child nodes '''
        self.ns, self.nodename = get_ns_nodename(node)
        for k, v in node.attrib.items():
            #remove the namespaceuris and replace with the namespaceprefix
            for uri,prefix in insd.items():
                k = k.replace('{'+uri+'}', prefix + ':')

            if k in self.attribdict:
                if k == 'xsi:type':
                    #store the remapped prefix:type
                    val = get_remapped_type(v)
                else:
                    datatype, isreqd, ismulti = self.attribdict[k]
                    val = cast_to_datatype(datatype, v, k)

                setattr(self, k, val)

        for child in node:
            self.buildchildren(child, node)
        
        

    def buildchildren(self, child, node):
        '''Parse the child node and save all elements to the instance of this class and call function to read its child nodes'''
        cns, cname, ctype = get_ns_name_type(child)
        # If unknown namespace ignore the element/node
        if cns is None:
            return
        if cname in self.elemdict:
            datatype, isreqd, ismulti = self.elemdict[cname]
            if isinstance(datatype, str):
                v = child.text.strip() if child.text else ''
                val = cast_to_datatype(datatype, v, cname)

            #handle the objects
            else:
                val = datatype()
                #Verify that the type defined in xml uses the correponding class in python

                if ctype and ctype != val.extnstype:
                    print (f'Warning: Type defined in xml {ctype}, expected {val.extnstype}')
                val.build(child)

            # Note that val might contain a simple value or an object. If this element can have multiple values make a list.
            if ismulti:
                if not hasattr(self, cname):
                    setattr(self, cname, [])
                self.__dict__[cname].append(val)
            else:
                setattr(self, cname, val)
        else:
            #unknown or unexpected element. raise error.
            raise SISError (f'Unknown element {cname} under node {self.nodename}')

    def validate(self):
        # This function is to be extended in the classes where applicable.

        for k in self.reqdattrs:
            v = getattr(self, k, None)
            if v is None or v=='':
                elem = '' if k == 'ValueOf' else f' > {k}'
                raise SISError(f'Missing required element or attribute or value: "{self.__class__.__name__}{elem}"')

    # defined as functions so individual classes can override if an element or type needs a special format
    def format_string(self, input_data):
        return html.escape(input_data.strip())
    def format_integer(self, input_data):
        return '{0:d}'.format(input_data)
    def format_decimal(self, input_data):
        return '{0}'.format(input_data)

    def format_boolean(self, input_data):
        if input_data:
            return 'true'
        else:
            return 'false'

    def format_datetime(self, input_data):
        val = input_data
        if val.tzinfo is None:
            #assume UTC
            val = val.replace(tzinfo=datetime_.timezone.utc)
        return val.isoformat()

    def formatval(self, datatype, v):
        ''' Call the appropriate format function based on this element's datatype '''
        if datatype == 'text':
            val = self.format_string(v)
        elif datatype == 'double':
            val = self.format_decimal(v)
        elif datatype == 'integer':
            val = self.format_integer(v)
        elif datatype == 'date':
            val = self.format_datetime(v)
        elif datatype == 'boolean':
            val = self.format_boolean(v)
        return val

    def enclosetag(self, datatype, level, nsk, v, attr=''):
        val = self.formatval(datatype, v)
        return ('{0}<{1}{2}>{3}</{1}>{4}'.format(INDENT*level, nsk, attr, val, os.linesep))

    def exportdict(self, ignorewarning=False):
        '''Return a python dictionary of this object's elements '''

        exp ={}
        #validate the content of this object
        try:
            self.validate()
        except SISError as e:
            if not ignorewarning:
                raise
            else:
                print ("Warning:", e)
        for contentdict in [self.elemdict, self.attribdict]:
            for k, v in contentdict.items():
                datatype, isreqd, ismulti = v
                val = getattr(self, k, None)
                if val is not None:
                    if isinstance(datatype, str):
                        # The builtin datatypes of str/float/integer/date are listed as string literals. Single or multivalues both are handled simply.
                        exp[k] = val
                    else:
                        # Datatype is a type matching the xml complex type.
                        # Export the contents as a dictionary
                        if ismulti:
                            # Multivalue possible, stored as a list. Export a list of dictionaries
                            exp[k] = []
                            for o in val:
                                exp[k].append(o.exportdict(ignorewarning))
                        else:
                            exp[k] = val.exportdict(ignorewarning)

        return exp
    def getattrxml (self):
        '''
        Return a string containing all the attribute key value pairs with a leading space
        or an empty string if there are no attributes.
        '''
        alist = []
        for k, datatype, isreqd, ismulti in self.ATTRIBS:
            v = getattr(self, k, None)
            if v is not None:
                val = self.formatval(datatype, v)
                alist.append(f'{k}="{val}"')
        axml = ' ' + ' '.join(alist) if alist else ''
        return axml

    def exportxml(self, outfile, nstag='FDSNStationXML', level=0, ignorewarning=False):
        '''Write the xml for this object and its subelements. '''
        #validate the content of this object
        try:
            self.validate()
        except SISError as e:
            if not ignorewarning:
                raise
            else:
                print ("Warning:", e)
                
        # Get an xml string with attributes formatted as key='val'
        axml = self.getattrxml()
        if level == 0:
            #write the xxml doctype
            outfile.write('<?xml version="1.0" encoding="UTF-8"?>' + os.linesep)

        outfile.write('{0}<{1}{2}>{3}'.format(INDENT*level, nstag, axml, os.linesep))
        sublevel = level + 1

        #use the tuple self.ELEMS because the order is important
        for k, datatype, isreqd, ismulti in self.ELEMS:
            # in case the extended type is in a different namespace then self.EXTNS has been set
            ns = self.NS
            if self.EXTNS:
                sup = self.SUPERCLASS
                #if element is not in the superclass then use self.EXTNS as the namespace prefix
                if k not in [e[0] for e in sup.ELEMS]:
                    ns = self.EXTNS

            if ns is None or ns == 'fsx':
                nsk = k
            else:
                nsk = f'{ns}:{k}'

            if getattr(self, k, None) is not None:
                #Python has only one builtin type named float that is equivalent to a c style double.
                if not ismulti:
                    v = getattr(self, k)
                    if isinstance(datatype, str):
                        outfile.write(self.enclosetag(datatype, sublevel, nsk, v))
                    else:
                        v.exportxml(outfile, nsk, sublevel, ignorewarning)
                else:
                    vlist = getattr(self, k)
                    for v in vlist:
                        if v is None:
                             print("Warning: found None in list for {0}, skipping".format(k))
                        elif isinstance(datatype, str):
                            outfile.write(self.enclosetag(datatype, sublevel, nsk, v))
                        else:
                            v.exportxml(outfile, nsk, sublevel, ignorewarning)
        outfile.write('{0}</{1}>{2}'.format(INDENT*level, nstag, os.linesep))

    def exportobj(self, outfile, level=0, ignorewarning=False):
        '''Write out a python object representation. '''
        try:
            self.validate()
        except SISError as e:
            if not ignorewarning:
                raise
            else:
                print ("Warning:", e)
 
        if level == 0:
            #For the outer most class add its name
            outfile.write('{0}={1}({2}'.format('rootobj', self.__class__.__name__, os.linesep))
            level = level +1

        for (k, datatype, isreqd, ismulti) in self.ATTRIBS + self.ELEMS:
            if k in self.__dict__:
                v = getattr(self, k)
                if isinstance(datatype, str):
                    if datatype == 'text' and not ismulti:
                        v=f"'{v}'"  # add quotes for string values
                    outfile.write('{0}{1}={2},{3}'.format(INDENT*level, k, v, os.linesep))
                else:
                    if ismulti:
                        outfile.write('{0}{1}=[{2}'.format(INDENT*level, k, os.linesep))
                        level = level+1
                        for elem in v:
                            outfile.write('{0}{1}({2}'.format(INDENT*level, elem.__class__.__name__, os.linesep))
                            elem.exportobj(outfile, level+1, ignorewarning)
                            outfile.write ('{0}),{1}'.format(INDENT*level, os.linesep))
                        outfile.write('{0}],{1}'.format(INDENT*level, os.linesep))
                        level = level - 1
                    else:
                        outfile.write('{0}{1}={2}({3}'.format(INDENT*level, k, v.__class__.__name__, os.linesep))
                        v.exportobj(outfile, level+1, ignorewarning)
                        outfile.write ('{0}),{1}'.format(INDENT*level, os.linesep))

        if level == 1:
            #close the outer most class
            outfile.write('){0}'.format(os.linesep))

class SISSimpleType(SISBase):
    '''
    Use this class for simple types that have no sub-elements, but have attributes.
    Redefine ElEMS if not of type text. Should be a tuple containing info for only
    one element named ValueOf.
    '''
    ELEMS = (('ValueOf', 'text', True, False),)
    NS = 'fsx'
    def build(self, node):
        self.ns, self.nodename = get_ns_nodename(node)
        ndatatype = self.ELEMS[0][1]
        v = node.text.strip() if node.text else ''
        self.ValueOf = cast_to_datatype(ndatatype, v, self.nodename)

        for k, v in node.attrib.items():
            if k in self.attribdict:
                datatype, isreqd, ismulti = self.attribdict[k]
                val = cast_to_datatype(datatype, v, k)
                setattr(self, k, val)
            else:
                raise SISError (f'Unexpected attribute {k}={v} in {self.nodename}')

    def buildchildren(self, child, node):
        pass

    def exportxml(self, outfile, nstag, level, ignorewarning=False):
        '''Export the value in ValueOf as the content of the passed in tag. '''
        try:
            self.validate()
        except SISError as e:
            if not ignorewarning:
                raise
            else:
                print ("Warning:", e)
        axml = self.getattrxml()
        ndatatype = self.ELEMS[0][1]

        outfile.write(self.enclosetag(ndatatype, level, nstag, self.ValueOf, axml))


class UnitsType(SISBase):
    ELEMS = (('Name', 'text', True, False),
             ('Description', 'text', False, False),
            )

    NS = 'fsx'

class FloatNoUnitType(SISSimpleType):
    '''
    This is a SimpleType node.
    This also stands in for fsx:NumeratorType
    '''
    ELEMS = (('ValueOf', 'double', True, False),)
    ATTRIBS = SISSimpleType.ATTRIBS + (('plusError', 'double', False , False),
                ('minusError', 'double', False , False),
                ('measurementMethod', 'text', False , False),
                ('number', 'integer', False, False), # this is from fsx:NumeratorType
              )
    NS = 'fsx'

    def validate(self):
        super(FloatNoUnitType, self).validate()
        plus = getattr(self, 'plusError', None)
        minus = getattr(self, 'minusError', None)
        if plus != minus:
            raise SISError ('The plus error and minus error are different. The loader requires them to be the same. Class {0}, plus error {1}, minus error {2}'.format(self.__class__.__name__, plus, minus))

class FloatType(FloatNoUnitType):
    ''' This also stands in for fsx:NumeratorCoefficientType
    '''
    ATTRIBS = FloatNoUnitType.ATTRIBS + (('unit', 'text', False, False),
            ('i', 'integer', False, False),)    # from fsx:NumeratorCoefficientType
    NS = 'fsx'

class NumeratorCoefficientType(SISSimpleType):
    ELEMS = (('ValueOf', 'double', True, False),)
    ATTRIBS = SISSimpleType.ATTRIBS + (('i', 'integer', False, False),)
    NS = 'fsx'

class NumeratorType(FloatNoUnitType):
    ATTRIBS = FloatNoUnitType.ATTRIBS + (('number', 'integer', False, False),)
    NS = 'fsx'

class FrequencyType(FloatType):
    def validate(self):
        super(FrequencyType, self).validate()
        if hasattr(self, 'unit') and self.unit != 'HERTZ':
            raise SISError (f'Invalid Frequency unit {self.unit}. Expected value: HERTZ')

class IdentifierType(SISSimpleType):
    ELEMS = (('ValueOf', 'text', True, False),)
    ATTRIBS = SISSimpleType.ATTRIBS + (('type', 'text', False , False),
              )
    NS = 'fsx'

class DecimationType(SISBase):
    ELEMS = (('InputSampleRate', FrequencyType, True, False),
             ('Factor', 'integer', True, False),
             ('Offset', 'integer', True, False),
             ('Delay', 'double', True, False),
             ('Correction', 'double', True, False),
             )
    NS = 'fsx'

class GainType(SISBase):
    ELEMS = (('Value', 'double', True, False),
             ('Frequency', 'double', True, False),
             )
    NS = 'fsx'

class SensitivityType(GainType):
    ELEMS = GainType.ELEMS + (('InputUnits', UnitsType, True, False),
            ('OutputUnits', UnitsType, True, False),
            ('FrequencyStart', 'double', False, False),
            ('FrequencyEnd', 'double', False, False),
            ('FrequencyDBVariation', 'double', False, False),
            )
    NS = 'fsx'

class SISGainType (GainType):
    ELEMS = GainType.ELEMS + (('InputUnits', UnitsType, False, False),
            ('OutputUnits', UnitsType, False, False),
            )
    EXTNS = 'sis'
    EXTTYPE = 'GainType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = GainType


class PoleZeroType(SISBase):
    ELEMS = (('Real', FloatNoUnitType, True, False),
             ('Imaginary', FloatNoUnitType, True, False),
             )
    ATTRIBS = SISBase.ATTRIBS + (('number', 'integer', False, False),)
    NS = 'fsx'

class BaseFilterType(SISBase):
    #Units are required in XSD, but not required for the loader.
    ELEMS = (('Description', 'text', False, False),
             ('InputUnits', UnitsType, False, False),
             ('OutputUnits', UnitsType, False, False),
            )
    ATTRIBS = SISBase.ATTRIBS + (('resourceid', 'text', False, False),
               ('name', 'text', False, False),
               )
    NS = 'fsx'

class PolesZerosType(BaseFilterType):
    ELEMS =  BaseFilterType.ELEMS + (('PzTransferFunctionType', 'text', True, False),
             ('NormalizationFactor', 'double', True, False),
             ('NormalizationFrequency', 'double', True, False),
             ('Zero', PoleZeroType, False, True),
             ('Pole', PoleZeroType, False, True),
            )
    NS = 'fsx'

class SISPolesZerosType(PolesZerosType):
    ATTRIBS = PolesZerosType.ATTRIBS + (('SISNamespace', 'text', True, False),)
    EXTNS = 'sis'
    EXTTYPE = 'PolesZerosType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = PolesZerosType

class CoefficientsType (BaseFilterType):
    ELEMS = BaseFilterType.ELEMS + (('CfTransferFunctionType', 'text', True, False),
            ('Numerator', FloatType, False, True),
            ('Denominator', FloatType, False, True),
            )
    NS = 'fsx'

class SISCoefficientsType(CoefficientsType):
    ATTRIBS = CoefficientsType.ATTRIBS + (('SISNamespace', 'text', True, False),)
    EXTNS = 'sis'
    EXTTYPE = 'CoefficientsType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = CoefficientsType

class FIRType(BaseFilterType):
    ELEMS = BaseFilterType.ELEMS + (('Symmetry', 'text', True, False),
            ('NumeratorCoefficient', FloatType, False, True),
            )
    NS = 'fsx'

class SISFIRType(FIRType):
    ATTRIBS = FIRType.ATTRIBS + (('SISNamespace', 'text', True, False),)
    EXTNS = 'sis'
    EXTTYPE = 'FIRType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = FIRType

class PolynomialType(BaseFilterType):
    ELEMS = BaseFilterType.ELEMS + (('ApproximationType', 'text', True, False),
            ('FrequencyLowerBound', FrequencyType, True, False),
            ('FrequencyUpperBound', FrequencyType, True, False),
            ('ApproximationLowerBound', 'double', True, False),
            ('ApproximationUpperBound', 'double', True, False),
            ('MaximumError', 'double', True, False),
            ('Coefficient', FloatNoUnitType, True, True),
            )
    NS = 'fsx'

class SISPolynomialType(PolynomialType):
    ATTRIBS = PolynomialType.ATTRIBS + (('SISNamespace', 'text', True, False),)
    EXTNS = 'sis'
    EXTTYPE = 'PolynomialType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = PolynomialType

class PersonType(SISBase):
    ELEMS = (('Name', 'text', False, True),
            ('Agency', 'text', False, True),
            ('Email', 'text', False, True),
            ('Phone', 'text', False, True),
            )
    NS = 'fsx'

class CommentType(SISBase):
    ELEMS = (('Value', 'text', True, False),
            ('BeginEffectiveTime', 'date', False, False),
            ('EndEffectiveTime', 'date', False, False),
            ('Author', PersonType, False, True),
            )
    ATTRIBS = SISBase.ATTRIBS + (('id', 'integer', False, False),
                ('subject', 'text', False, False),)
    NS = 'fsx'

class BaseNodeType (SISBase):
    ELEMS = (('Description', 'text', False, False),
            ('Identifier', IdentifierType, False, True),
            ('Comment', CommentType, False, True),
            )
    ATTRIBS = SISBase.ATTRIBS + (('code', 'text', True, False),
               ('startDate', 'date', False, False),
               ('endDate', 'date', False, False),
               ('sourceID', 'text', False, False),
               ('restrictedStatus', 'text', False, False),
               ('alternateCode', 'text', False, False),
               ('historicalCode', 'text', False, False),)
    NS = 'fsx'

class DegreeMixin(object):
    def validate(self):
        super(DegreeMixin, self).validate()
        if hasattr(self, 'unit') and self.unit != 'DEGREES':
            raise SISError ('{0} unit should be DEGREES. Invalid value {1}'.format(self.__class__.__name__, self.unit))

class LatitudeType(DegreeMixin, FloatType):
    ATTRIBS = FloatType.ATTRIBS + (('datum', 'text', False, False),)
    NS = 'fsx'

    def validate(self):
        super(LatitudeType, self).validate()
        if self.ValueOf <-90 or self.ValueOf > 90:
            raise SISError(f'Invalid Latitude: {self.ValueOf}')

    #Override default exponential out format and precision defined for FloatType. 
    # Not needed in sisxmlparser3_0 since there is format is defined that needs overriding. 
    # And let the dataless converter handle the reduced precision defined in the SEED format. 
    # Leaving it in as a comment to keep an example and if it needs to be revived
    
    #def format_decimal(self, input_data):
    #    return FMT_DEC_6.format(input_data)

class LongitudeType(DegreeMixin, FloatType):
    ATTRIBS = FloatType.ATTRIBS + (('datum', 'text', False, False),)
    NS = 'fsx'

    def validate(self):
        super(LongitudeType, self).validate()
        if self.ValueOf <-180 or self.ValueOf > 180:
            raise SISError(f'Invalid Longitude: {self.ValueOf}')

class AzimuthType(DegreeMixin, FloatType):
    NS = 'fsx'

    def validate(self):
        super(AzimuthType, self).validate()
        if self.ValueOf <0 or self.ValueOf > 360:
            raise SISError(f'Invalid Azimuth: {self.ValueOf}')

    #Override default exponential out format and precision defined for FloatType
    #def format_decimal(self, input_data):
    #    return FMT_DEC_1.format(input_data)

class DipType(DegreeMixin, FloatType):
    NS = 'fsx'

    def validate(self):
        super(DipType, self).validate()
        if self.ValueOf < -90 or self.ValueOf > 90:
            raise SISError(f'Invalid Dip: {self.ValueOf}')

class DistanceType(FloatType):
    NS = 'fsx'

    def validate(self):
        super(DistanceType, self).validate()
        if hasattr(self, 'unit') and self.unit != 'METERS':
            raise SISError (f'Distance should be in METERS. It is specified as {self.unit}')

class ExternalReferenceType(SISBase):
    ELEMS = (('URI', 'text', True, False),
            ('Description', 'text', True, False),
            )
    NS = 'fsx'

class SampleRateRatioType(SISBase):
    ELEMS = (('NumberSamples', 'integer', True, False),
            ('NumberSeconds', 'integer', True, False),
            )
    NS = 'fsx'

class EquipmentType(SISBase):
    ELEMS = (('Type', 'text', False, False),
            ('Description', 'text', False, False),
            ('Manufacturer', 'text', False, False),
            ('Vendor', 'text', False, False),
            ('Model', 'text', False, False),
            ('SerialNumber', 'text', False, False),
            ('InstallationDate', 'date', False, False),
            ('RemovalDate', 'date', False, False),
            ('CalibrationDate', 'date', False, True),
            )
    ATTRIBS = SISBase.ATTRIBS + (('resourceId', 'text', False, False),)
    NS = 'fsx'

class ResponseStageType(SISBase):

    ELEMS = (('PolesZeros', PolesZerosType, False, False),
            ('Coefficients', CoefficientsType, False, False),
            ('FIR', FIRType, False, False),
            ('Decimation', DecimationType, False, False),
            ('StageGain', GainType, False, False),
            ('Polynomial', PolynomialType, False, False),
            )
    ATTRIBS = SISBase.ATTRIBS + (('resourceId', 'text', False, False),
              ('number', 'integer', False, False),
              )
    NS = 'fsx'

    def validate(self):
        super(ResponseStageType, self).validate()
        # Ensure that either gain is present or polynomial is present. Both should not be present. They are mutually exclusive.
        hasgain = hasattr(self, 'StageGain')
        haspoly = hasattr(self, 'Polynomial')
        #
        if hasgain == haspoly:
            raise SISError ('Specify either StageGain or Polynomial in ResponseStage')

class ResponseType(SISBase):
    ELEMS = (('InstrumentSensitivity', SensitivityType, False, False),
                ('InstrumentPolynomial', PolynomialType, False, False),
                ('Stage', ResponseStageType, False, True),
                )
    ATTRIBS = SISBase.ATTRIBS + (('resourceId', 'text', False, False),)
    NS = 'fsx'

class EquipmentLinkType(SISBase):
    ELEMS = (('SerialNumber', 'text', True, False),
            ('ModelName', 'text', True, False),
            ('Category', 'text', True, False),
            ('ComponentName', 'text', True, False),
            ('CalibrationDate', 'date', False, False),
            ('AtoDDelay', DecimationType, False, False),
            )
    NS = 'sis'

class CalResponseDetailType(SISBase):

    ELEMS = (('PolesZeros', SISPolesZerosType, False, False),
            ('Polynomial', SISPolynomialType, False, False),
            )
    NS = 'sis'

class SubResponseDetailType(SISBase):

    ELEMS = (('PolesZeros', SISPolesZerosType, False, False),
            ('Coefficients', SISCoefficientsType, False, False),
            ('FIR', SISFIRType, False, False),
            ('Decimation', DecimationType, False, False),
            ('Gain', SISGainType, True, False),
            ('Polynomial', SISPolynomialType, False, False),
            )
    NS = 'sis'

    def validate(self):
        super(SubResponseDetailType, self).validate()
        # Ensure that either gain is present or polynomial is present. Both should not be present. They are mutually exclusive.
        hasgain = hasattr(self, 'Gain')
        haspoly = hasattr(self, 'Polynomial')
        #
        if hasgain == haspoly:
            raise SISError ('Specify either Gain or Polynomial in ResponseStage')


class RESPFileType(SISSimpleType):
    '''
    This is a SimpleType node
    '''
    ELEMS = (('ValueOf', 'text', True, False),
            )
    ATTRIBS = SISBase.ATTRIBS + (('stageFrom', 'integer', False, False),
              ('stageTo', 'integer', False, False),
              )
    NS = 'sis'

class ResponseDictLinkType(SISBase):
    ELEMS = (('Name', 'text', True, False),
            ('SISNamespace', 'text', True, False),
            ('Type', 'text', True, False),
           )
    NS = 'sis'

class ResponseDictLinkType2(ResponseDictLinkType):
    ELEMS = ResponseDictLinkType.ELEMS + (('Gain', SISGainType, False, False),)
    NS = 'sis'

class SubResponseType(SISBase):
    ELEMS = (('EquipmentLink', EquipmentLinkType, False, False),
            ('ResponseDetail', SubResponseDetailType, False, False),
            ('RESPFile', RESPFileType, False, False),
            ('ResponseDictLink', ResponseDictLinkType2, False, False),
            )
    ATTRIBS = SISBase.ATTRIBS + (('sequenceNumber', 'integer', False, False),
              ('type', 'text', False, False),
              )
    NS = 'sis'

class SISResponseType(ResponseType):
    ELEMS = (('InstrumentSensitivity', SensitivityType, False, False),
                ('InstrumentPolynomial', SISPolynomialType, False, False),
                ('Stage', ResponseStageType, False, True),
                ('SubResponse', SubResponseType,False, True),
            )
    EXTNS = 'sis'
    EXTTYPE = 'ResponseType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = ResponseType

class SensorOffsetType(SISBase):
    ELEMS = (('NorthOffset', 'double', False, False),
            ('EastOffset', 'double', False, False),
            ('VerticalOffset', 'double', False, False),
            )
    NS = 'sis'

class SensorSiteDescriptionType(SISBase):
    ELEMS = (('StationHousing', 'integer', False, False),
            ('GeologicSiteClass', 'text', False, False),
            ('PhysicalCondition', 'text', False, False),
            ('Vs30', 'double', False, False),
            ('SensorOffset', SensorOffsetType, False, False),
            )
    NS = 'sis'

class ChannelType(BaseNodeType):
    BASE_ELEMS = (('ExternalReference', ExternalReferenceType, False, True),
                ('Latitude', LatitudeType, True, False),
                ('Longitude', LongitudeType, True, False),
                ('Elevation', DistanceType, True, False),
                ('Depth', DistanceType, True, False),
                ('Azimuth', AzimuthType, False, False),
                ('Dip', DipType, False, False),
                ('WaterLevel', FloatType, False, False),
                ('Type', 'text', False, True),
                ('SampleRate', FloatType, False, False),
                ('SampleRateRatio', SampleRateRatioType, False, False),
                ('ClockDrift', FloatType, False, False),
                ('CalibrationUnits', UnitsType, False, False),
                ('Sensor', EquipmentType, False, False),
                ('PreAmplifier', EquipmentType, False, False),
                ('DataLogger', EquipmentType, False, False),
                ('Equipment', EquipmentType, False, True))
    ELEMS = BaseNodeType.ELEMS + BASE_ELEMS + (
                ('Response', ResponseType, False, False),
                )
    ATTRIBS = BaseNodeType.ATTRIBS + (('locationCode', 'text', True, False),)
    NS = 'fsx'

    def __init__(self, **kw):
        super(ChannelType, self).__init__(**kw)
        # The validate function checks that values for reqdattrs are not empty.
        # In case of locationCode "" is a valid value, and not the same as  empty, so remove it from the reqdattrs list
        self.reqdattrs.remove('locationCode')

class SISChannelType(ChannelType):
    ELEMS = BaseNodeType.ELEMS + ChannelType.BASE_ELEMS + (
                ('Response', SISResponseType, False, False),
                ('StationChannelNumber', 'integer', False, False),
                ('MeasurementType', 'text', False, False),
                ('SignalUnits', UnitsType, False, False),
                ('Clip', 'double', False, False),
                ('Cutoff', 'double', False, False),
                ('PinNumber', 'integer', False, False),
                ('ChannelSource', 'text', False, False),
                ('NeedsReview', 'boolean', False, False),
                ('SensorSiteDescription', SensorSiteDescriptionType, False, False),
                )
    EXTNS = 'sis'
    EXTTYPE = 'ChannelType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = ChannelType

class SiteType(SISBase):
    ELEMS = (('Name', 'text', True, False),
                ('Description', 'text', False, False),
                ('Town', 'text', False, False),
                ('County', 'text', False, False),
                ('Region', 'text', False, False),
                ('Country', 'text', False, False),
                )
    NS = 'fsx'

class OperatorType(SISBase):
    ELEMS = (('Agency', 'text', True, False),
            ('Contact', PersonType, False, True),
            ('WebSite', 'text', False, False),
            )
    NS = 'fsx'

class PlaceType(SISBase):
    ELEMS = (('Name', 'text', True, False),
            ('Latitude', LatitudeType, True, False),
            ('Longitude', LongitudeType, True, False),
            )
    NS = 'sis'

class LogType (SISBase):
    ELEMS = (('LogDate', 'date', True, False),
                ('Subject', 'text', True, False),
                ('LogText', 'text', True, False),
                ('OffDate', 'date', False, False),
                ('Author', 'text', False, False),
               )
    NS = 'sis'

class GeoSiteType(SISBase):
    ELEMS = (('Place', PlaceType, True, False),
            ('SiteNetCode', 'text', False, False),
            ('SiteLookupCode', 'text', False, False),
            ('SiteTypeTag', 'text', False, True),
            ('SiteLog', LogType, False, True),
            )
    NS = 'sis'

class StationType(BaseNodeType):
    BASE_ELEMS = (('Latitude', LatitudeType, True, False),
            ('Longitude', LongitudeType, True, False),
            ('Elevation', DistanceType, True, False),
            ('Site', SiteType, True, False),
            ('WaterLevel', FloatType, False, False),
            ('Vault', 'text', False, False),
            ('Geology', 'text', False, False),
            ('Equipment', EquipmentType, False, True),
            ('Operator', OperatorType, False, True),
            ('CreationDate', 'date', False, False),
            ('TerminationDate', 'date', False, False),
            ('TotalNumberChannels', 'integer', False, False),
            ('SelectedNumberChannels', 'integer', False, False),
            ('ExternalReference', ExternalReferenceType, False, True),
            )
    ELEMS = BaseNodeType.ELEMS + BASE_ELEMS + (
            ('Channel', ChannelType, False, True),
            )
    NS = 'fsx'

class SISStationType(StationType):
    ELEMS = BaseNodeType.ELEMS + StationType.BASE_ELEMS + (
            ('Channel', SISChannelType, False, True),
            ('DatumVertical', 'text', False, False),
            ('SecondaryStationNumber', 'text', False, False),
            ('ReferenceAzimuth', AzimuthType, False, False),
            ('GeoSite', GeoSiteType, False, False),
            )
    ATTRIBS = StationType.ATTRIBS + (('codeType', 'text', False, False), )
    EXTNS = 'sis'
    EXTTYPE = 'StationType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = StationType

class NetworkType (BaseNodeType):
    BASE_ELEMS = (('Operator', OperatorType, False, True),
            ('TotalNumberStations', 'integer', False, False),
            ('SelectedNumberStations', 'integer', False, False),
            )
    ELEMS = BaseNodeType.ELEMS + BASE_ELEMS + (
            ('Station', StationType, False, True),)
    NS = 'fsx'

class SISNetworkType (BaseNodeType):
    ELEMS = BaseNodeType.ELEMS + NetworkType.BASE_ELEMS + (
            ('Station', SISStationType, False, True),)
    NS = 'fsx'

class RootType (SISBase):
    BASE_ELEMS = (('Source', 'text', True, False),
            ('Sender', 'text', False, False),
            ('Module', 'text', False, False),
            ('ModuleURI', 'text', False, False),
            ('Created', 'date', True, False),
            )
    ELEMS = BASE_ELEMS +(('Network', NetworkType, True, True),)
    ATTRIBS = SISBase.ATTRIBS + (
        ('xmlns', 'text', False, False),
        ('xmlns:xsi', 'text', False, False),
        ('schemaVersion', 'text', False, False),
        ('xsi:schemaLocation', 'text', False, False),
        )
    NS = 'fsx'
    IS_EXTSTA = False

    def __init__(self, **kw):
        super(RootType, self).__init__(**kw)
        self.nskey = self.EXTNS if self.IS_EXTSTA else self.NS
        # set defaults for the attributes that are expected to be written out if they are not provided
        
        if getattr(self, 'schemaVersion', None) is None:
            self.schemaVersion = nsd[self.nskey][3]
        if getattr(self, 'xmlns', None) is None:
            self.xmlns = nsd['fsx'][0]
        if getattr(self, 'xmlns:xsi', None) is None:
            setattr(self, 'xmlns:xsi', nsd['xsi'][0])
        if getattr(self, 'xsi:schemaLocation', None) is None:
            setattr(self, 'xsi:schemaLocation', '{0} {2}'.format(*nsd[self.nskey]))

    def validate(self):
        super(RootType, self).validate()
        if getattr(self, 'schemaVersion') and self.schemaVersion != nsd[self.nskey][3]:
            raise SISError('Invalid schemaversion {0}. Parser expects {1}'.format(self.schemaVersion, nsd[self.nskey][3]))

        schemaLoc = getattr(self, 'xsi:schemaLocation')
        expectedLoc = '{0} {2}'.format(*nsd[self.nskey])
        if schemaLoc != expectedLoc:
            print ('Warning: Invalid xsi:schemaLocation {0}. Parser expects {1}'.format(schemaLoc, expectedLoc))
        

class FilterIDType (SISBase):
    ELEMS = (('Name', 'text', True, False),
                ('SISNamespace', 'text', True, False),
                ('Type', 'text', True, False),
            )
    NS = 'sis'

class FilterStageType (SISBase):
    ELEMS = (('SequenceNumber', 'integer', True, False),
            ('Filter', FilterIDType, True, False),
            ('Decimation', DecimationType, True, False),
            ('Gain', SISGainType, True, False),
            )
    NS = 'sis'

class FilterSequenceType(SISBase):
    ELEMS = (('FilterStage', FilterStageType, True, True),
            )
    ATTRIBS = SISBase.ATTRIBS + (('name', 'text', True, False),
                ('SISNamespace', 'text', True, False),
              )
    NS = 'sis'

class ResponseDictType(SISBase):
    ELEMS = (('PolesZeros', SISPolesZerosType, False, False),
                ('Coefficients', SISCoefficientsType, False, False),
                ('FIR', SISFIRType, False, False),
                ('Polynomial', SISPolynomialType, False, False),
                ('FilterSequence', FilterSequenceType, False, False),
                )
    NS = 'sis'

class ResponseDictGroupType(SISBase):
    ELEMS = (('ResponseDict', ResponseDictType, True, True),
            )
    NS = 'sis'

class ProjectType(SISBase):
    ELEMS = (('Name', 'text', True, False),
                ('GrantNumber', 'text', False, False),
                ('Description', 'text', False, False),
                ('StartDate', 'date', False, False),
                ('EndDate', 'date', False, False),
                ('FundingDate', 'date', False, False),
            )
    ATTRIBS = SISBase.ATTRIBS + (('SISNamespace', 'text', True, False),)
    NS = 'sis'

class EquipmentEpochType(SISBase):
    ELEMS = (('OnDate', 'date', True, False),
            ('OffDate', 'date', False, False),
            ('InventoryStatus', 'text', True, False),
            ('Operator', 'text', True, False),
            ('Owner', 'text', False, False),
            ('PropertyTag', 'text', False, False),
            ('CoOwner', 'text', False, False),
            ('CoPropertyTag', 'text', False, False),
            ('Project', ProjectType, False, False),
            ('Description', 'text', False, False),
           )
    NS = 'sis'

class OnDateType (SISSimpleType):
    '''
    This is a SimpleType node
    '''
    ELEMS = (('ValueOf', 'date', True, False),)
    ATTRIBS = (('onDateType', 'text', False, False),
              )
    NS = 'sis'

class OffDateType (SISSimpleType):
    '''
    This is a SimpleType node
    '''
    ELEMS = (('ValueOf', 'date', True, False),)
    ATTRIBS = (('offDateType', 'text', False, False),
              )
    NS = 'sis'

class ProblemReportType (SISBase):
    ELEMS = (('OnDate', OnDateType, False, False),
            ('OffDate', OffDateType, False, False),
            ('Subject', 'text', True, False),
            ('LogText', 'text', True, False),
            ('CreatedBy', 'text', False, False),
           )
    NS = 'sis'

class SettingType(SISBase):
    ELEMS = (('Key', 'text', True, False),
            ('Value', 'text', True, False),
            ('OnDate', 'date', False, False),
            ('OffDate', 'date', False, False),
           )
    NS = 'sis'

class IPv4AddressType(SISSimpleType):
    '''
    This is a SimpleType node
    '''
    ELEMS = (('ValueOf', 'string', True, False),)
    ATTRIBS = SISSimpleType.ATTRIBS + (('networkMask', 'string', False , False),
                ('gatewayAddress', 'string', False , False),
              )
    NS = 'sis'

class IPv6AddressType(SISSimpleType):
    '''
    This is a SimpleType node
    '''
    ELEMS = (('ValueOf', 'string', True, False),)
    ATTRIBS = SISSimpleType.ATTRIBS + (('prefixLength', 'integer', False , False),
                ('gatewayAddress', 'string', False , False),
              )
    NS = 'sis'

class IPAddressType(SISBase):
    ELEMS = (('IPv4Address', IPv4AddressType, False, False),
             ('IPv6Address', IPv4AddressType, False, False),
             ('PhysicalPort', 'text', False, False),
             ('Notes', 'text', False, False),
           )
    NS = 'sis'


class EquipBaseType(SISBase):
    ELEMS = (('SerialNumber', 'text', True, False),
            ('ModelName', 'text', True, False),
            ('Category', 'text', True, False),
            ('IsActualSerialNumber', 'boolean', True, False),
            ('COSMOSModelNumber', 'integer', False, False),
            ('EquipmentEpoch', EquipmentEpochType, True, True),
            ('Description', 'text', False, False),
            ('Vendor', 'text', False, False),
            ('EquipmentLog', LogType, False, True),
            ('ProblemReport', ProblemReportType, False, True),
            ('EquipSetting', SettingType, False, True),
            ('IPAddress', IPAddressType, False, True),
           )
    NS = 'sis'

class CalResponseType(SISBase):
    ELEMS = (('RESPFile', RESPFileType, False, False),
            ('ResponseDetails', CalResponseDetailType, False, False),
            ('ResponseDictLink', ResponseDictLinkType, False, False),
            ('Gain', SISGainType, False, False),
            )
    NS = 'sis'

class CalibrationType(SISBase):
    ELEMS = (('CalibrationDate', 'date', False, False),
            ('CalibrationDateUnknown', 'boolean', False, False),
            ('Response', CalResponseType, True, False),
            ('InputRange', 'double', False, False),
            ('InputRangeUnit', UnitsType, False, False),
            ('OutputRange', 'double', False, False),
            ('OutputRangeUnit', UnitsType, False, False),
            ('Comments', 'text', False, False),
            ('NeedsReview', 'boolean', False, False),
            ('NaturalFrequency', 'double', False, False),
            ('DampingConstant', 'double', False, False),
            ('Attenuation', 'double', False, False),
            ('StandardGain', 'double', False, False),
            ('TuningHertz', 'double', False, False),
            ('TuningVolt', 'double', False, False),
           )
    NS = 'sis'

    def validate(self):
        super(CalibrationType, self).validate()
        if not hasattr(self, 'CalibrationDate') and not hasattr(self, 'CalibrationDateUnknown'):
            raise SISError('If calibration date is not known, then provide element CalibrationDateUnknown with value true')


class ComponentType(SISBase):
    ELEMS = (('ComponentName', 'text', True, False),
                ('Calibration', CalibrationType, True, True),
                ('NumberOfAtoDBits', 'integer', False, False),
                ('MaxAtoDCount', 'integer', False, False),
               )
    NS = 'sis'

class EquipType(EquipBaseType):
    ELEMS = EquipBaseType.ELEMS + (('Component', ComponentType, True, True),)
    NS = 'sis'

class LoggerType(EquipBaseType):
    ELEMS = EquipBaseType.ELEMS + (('SOHComponent', ComponentType, False, True),)
    NS = 'sis'

class EquipIDType (SISBase):
    ELEMS = (('SerialNumber', 'text', True, False),
             ('ModelName', 'text', True, False),
             ('Category', 'text', True, False),
            )
    NS = 'sis'

class ComponentDetailType(SISBase):
    ELEMS = (('ComponentName', 'text', True, False),
             ('PinNumber', 'integer', True, False),
            )
    NS = 'sis'

class LoggerPackageContentType(SISBase):
    ELEMS = (('LoggerBoard', EquipIDType, True, False),
             ('SlotNumber', 'integer', True, False),
             ('ComponentDetail', ComponentDetailType, True, True),
            )
    NS = 'sis'

class LoggerPackageType(SISBase):
    ELEMS = (('Logger', EquipIDType, True, False),
            ('LoggerContent', LoggerPackageContentType, True, True),
            ('OnDate', 'date', False, False),
            ('OffDate', 'date', False, False),
            )
    NS = 'sis'

class PkgEquipmentType(SISBase):
    ELEMS = (('SerialNumber', 'text', True, False),
            ('ModelName', 'text', True, False),
            ('Category', 'text', True, False),
            )
    NS = 'sis'

class PackageType(SISBase):
    ELEMS = (('Equipment', PkgEquipmentType, True, True),
            ('OnDate', 'date', True, False),
            ('OffDate', 'date', False, False),
            )
    NS = 'sis'

class HardwareType(SISBase):
    ELEMS = (('Sensor', EquipType, False, True),
            ('Logger', LoggerType, False, True),
            ('LoggerBoard', EquipType, False, True),
            ('LoggerPackage', LoggerPackageType, False, True),
            ('Amplifier', EquipType, False, True),
            ('VCO', EquipType, False, True),
            ('Discriminator', EquipType, False, True),
            ('Equipment', EquipBaseType, False, True),
            ('Package', PackageType, False, True),
            )
    NS = 'sis'

class SiteIDType (SISBase):
    ELEMS = (('SiteNetCode', 'text', True, False),
             ('SiteLookupCode', 'text', True, False),
             ('OnDate', 'date', True, False),
             ('OffDate', 'date', False, False),
            )
    NS = 'sis'

class HardwareInstallationType(SISBase):
    ELEMS = (('Equipment', EquipIDType, True, False),
             ('Location', SiteIDType, True, False),
             ('IsMultiSite', 'boolean', True, False),
             ('InstallDate', 'date', True, False),
             ('RemovalDate', 'date', False, False),
             ('Notes', 'text', False, False),
             ('InstallAlias', 'text', False, False),
            )
    NS = 'sis'

class HardwareInstallationGroupType (SISBase):
    ELEMS = (('HardwareInstallation', HardwareInstallationType, True, True),
            )
    NS = 'sis'

class HardwareResponseType(SISBase):
    ELEMS = (('Hardware', HardwareType, False, False),
            ('ResponseDictGroup', ResponseDictGroupType, False, False),
            ('HardwareInstallationGroup', HardwareInstallationGroupType, False, False),
            )
    NS = 'sis'

class SISRootType(RootType):
    ELEMS = RootType.BASE_ELEMS + (
         ('Network', SISNetworkType, True, True),
         ('HardwareResponse', HardwareResponseType, False, False),
        )
    ATTRIBS = RootType.ATTRIBS + (
        ('xmlns:sis', 'text', False, False),
        )
    EXTNS = 'sis'
    EXTTYPE = 'RootType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = RootType
    IS_EXTSTA = True

    def __init__(self, **kw):
        super(SISRootType, self).__init__(**kw)
        # set defaults for the attributes that are expected to be written out if they are not provided
        if getattr(self, 'xmlns:sis', None) is None:
            setattr(self, 'xmlns:sis', nsd['sis'][0])

def parseFdsnStaXml(inFileName):
    return parse(inFileName, isExtStaXml = False)

def parseExtStaXml(inFileName):
    return parse(inFileName, isExtStaXml = True)

def parse(inFileName, isExtStaXml = True):
    ''' Inputs: xmlfile to be parsed and indicate whether it is ExtStaXML or FDSNStatioNXML
    Returns a python object with data from the xmlfile'''
    global docnsprefixmap
    doc = parsexml_(inFileName)
    root = doc.getroot()
    docnsmap = root.nsmap
    for k, uri in docnsmap.items():
        #remap the prefixes used in this document to the default defined in this parser using the uri
        if uri in insd:
            docnsprefixmap[k] = insd[uri]
        else:
            docnsprefixmap[k] = k
            print (f'Warning: Unknown/unexpected namespace: {k}: {uri}. Elements in this namespace will be ignored.')
    if isExtStaXml:
        obj = SISRootType()
    else:
        obj = RootType()

    obj.build(root)
    obj.validate()
    return obj


def main():

    parser = argparse.ArgumentParser(description='Parse / export FDSNStationXML1.1 or ExtStationXML3.0')
    parser.add_argument('xmlfile', type=str,
                        help='Name of file to be parsed')
    parser.add_argument('--xmltype', choices=['sis', 'fdsn'], default='sis',
                        help='Use "sis" for ExtStationXML and "fdsn" for FDSNStationXML')

    parser.add_argument('--ignorewarning', action='store_true', default=False)

    options = parser.parse_args()
    if options.xmltype == 'sis' :
        isExt = True
    else:
        isExt = False
    # Parse an xml file
    obj = parse(options.xmlfile, isExt)

    # Export xml
    obj.exportxml(sys.stdout, ignorewarning=options.ignorewarning)

    ## Export the python object representation
    #obj.exportobj(sys.stdout, ignorewarning=options.ignorewarning)
    #
    ### Convert the python object into a dictionary
    #exp = obj.exportdict(ignorewarning=options.ignorewarning)
    #import pprint
    #pp = pprint.PrettyPrinter(indent=1)
    #pp.pprint(exp)

if __name__ == '__main__':
    main()


