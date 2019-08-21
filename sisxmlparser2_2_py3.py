#! /usr/bin/python

'''
sisxmlparser2_2.py
version 2.2
2017-08-31

This module contains classes to parse an XML document in the extended
FDSNStationXML format as defined in sis_extension.xsd which currently is at
http://anss-sis.scsn.org/xml/ext-stationxml/2.2/sis_extension.xsd and convert
it into python objects. This can be output as an XML file or as a python
dictionary.

Author: Prabha Acharya, ANSS SIS Development Team, SCSN
Email: sis-help@gps.caltech.edu

Changelog 2014-12-15
Added classes:
    SISPolesZerosType
    SISCoefficientsType
    SISFIRType
    SISPolynomialType
    PlaceType
    LogType (was EquipmentLogType)
    GeoSiteType
    FilterIDType
    FilterStageType (was FilterType)
    ProjectType
    EquipIDType
    SiteIDType
    ComponentDetailType
    LoggerPackageContentType
    LoggerPackageType
    HardwareInstallationType
    HardwareInstallationGroupType

Modified classes:
    CalResponseDetailType
    SubResponseDetailType
    ResponseDictType
    ResponseDictLinkType
    SISStationType
    FilterSequenceType
    ResponseDictGroupType
    EquipmentEpochType
    EquipBaseType
    ComponentType
    HardwareType
    HardwareResponseType

Removed classes:
    FilterType (renamed to FilterStageType)
    EquipmentLogType (renamed to LogType)
    LoggerType

2015-02-23: Ignore elements in namespaces that are unknown to this
    parser (like 'iris:alternateNetworkCodes') instead or raising an error.

2015-06-10: Added code to handle utf-8 strings and write them out as html/xml encoded strings.

2016-06-16
  Added class LoggerType
  Removed elements: PreampGain in SubResponse, IsPhysicalSOH and IsVirtual in ComponentType
Thanks to Dave Kuhlmann for writing generateDS.py. Some of the generated
code is included in this file. http://www.rexx.com/~dkuhlman/generateDS.html

2016-11-10
  Changed ExtStationXML schemalocation from http to https.

2017-08-31
  SensorSiteDescription: Made following elements optional - StationHousing, GeologicSiteClass, PhysicalCondition, SensorOffset

'''

import sys
import getopt
import re as re_
import base64
import datetime as datetime_
from lxml import etree as etree_


def parsexml_(*args, **kwargs):
    kwargs['parser'] = etree_.ETCompatXMLParser()
    doc = etree_.parse(*args, **kwargs)
    return doc

class SISError(Exception):
    def __init__(self, value):
        Exception.__init__(self, value)

def raise_parse_error(msg, node=None):
    if node:
        if XMLParser_import_library == XMLParser_import_lxml:
            msg = '%s (element %s/line %d)' % (
                msg, node.tag, node.sourceline, )
        else:
            msg = '%s (element %s)' % (msg, node.tag, )
    raise SISError(msg)

#
# Globals
#

ExternalEncoding = 'ascii'

Tag_pattern_ = re_.compile(r'({.*})?(.*)')
String_cleanup_pat_ = re_.compile(r"[\n\r\s]+")
Namespace_extract_pat_ = re_.compile(r'{(.*)}(.*)')

nsd = {'xsi' : 'http://www.w3.org/2001/XMLSchema-instance',
       'fsx' : 'http://www.fdsn.org/xml/station/1',
       'sis' : 'http://anss-sis.scsn.org/xml/ext-stationxml/2.2',}

insd = dict((v, k) for k, v in list(nsd.items()))

# The schemaLocation for FDSNstationXML is defined in sis_extension.xsd
nslocd = {'sis' : 'https://anss-sis.scsn.org/xml/ext-stationxml/2.2/sis_extension.xsd',}

#set these when parsing the document.
docnsmap = {}
docnsprefixmap = {}

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
        remappedprefix = docnsprefixmap[ns]

    return '%s:%s' % (remappedprefix, type)


def quote_xml(inStr):
    if not inStr:
        return ''
    s1 = (isinstance(inStr, str) and inStr or
          '%s' % inStr)
    s1 = s1.replace('&', '&amp;')
    s1 = s1.replace('<', '&lt;')
    s1 = s1.replace('>', '&gt;')
    return s1


def quote_attrib(inStr):
    s1 = (isinstance(inStr, str) and inStr or
          '%s' % inStr)
    s1 = s1.replace('&', '&amp;')
    s1 = s1.replace('<', '&lt;')
    s1 = s1.replace('>', '&gt;')
    if '"' in s1:
        s1 = s1.replace('"', "&quot;")
    return s1

def cast_to_float(val, node=None):
    if val is None or val == '':
        return None
    try:
        tval = float(val)
        return tval
    except (TypeError, ValueError) as exp:
        raise_parse_error('Value passed in: %s. Requires float or double. %s' % (val, exp), node)

def cast_to_integer(val, node=None):
    if val is None or val == '':
        return None
    try:
        tval = int(val)
        return tval
    except (TypeError, ValueError) as exp:
        raise_parse_error('Value passed in: %s. Requires integer. %s' % (val, exp), node)

def cast_to_bool(val, node=None):
    if val is None or val == '':
        return None
    if val in ('true', '1'):
        ival = True
    elif val in ('false', '0'):
        ival = False
    else:
        raise_parse_error('Value passed in %s. Requires boolean' % (val,), node)
    return ival

def get_text(node):
    if node.text:
        return node.text.strip()
    else:
        return ""

class MyBase(object):
    '''Base class - derived from the base class generated by generateDS.py, hence the gds prefix. '''
    def gds_format_string(self, input_data):
        return input_data.strip()
    def gds_validate_string(self, input_data, node):
        return input_data
    def gds_format_base64(self, input_data):
        return base64.b64encode(input_data)
    def gds_validate_base64(self, input_data, node):
        return input_data
    def gds_format_integer(self, input_data):
        return '%d' % input_data
    def gds_validate_integer(self, input_data, node):
        return input_data
    def gds_format_float(self, input_data):
        # #362 - Shorten the display for the zeros.
        if input_data == 0.0:
            return '%.1f' % input_data
        return '%.12E' % input_data
    def gds_validate_float(self, input_data, node):
        return input_data
    def gds_format_double(self, input_data):
        # #362 - Shorten the display for the zeros.
        if input_data == 0.0:
            return '%.1f' % input_data
        return '%.12E' % input_data
    def gds_validate_double(self, input_data, node):
        return input_data
    def gds_format_decimal(self, input_data):
        return '%s' % input_data
    def gds_validate_decimal(self, input_data, node):
        return input_data
    def gds_format_boolean(self, input_data):
        return ('%s' % input_data).lower()
    def gds_validate_boolean(self, input_data, node):
        return input_data
    def gds_validate_datetime(self, input_data, node):
        return input_data
    def gds_format_datetime(self, input_data):
        if input_data.microsecond == 0:
            _svalue = '%04d-%02d-%02dT%02d:%02d:%02d' % (
                input_data.year,
                input_data.month,
                input_data.day,
                input_data.hour,
                input_data.minute,
                input_data.second,
            )
        else:
            _svalue = '%04d-%02d-%02dT%02d:%02d:%02d.%s' % (
                input_data.year,
                input_data.month,
                input_data.day,
                input_data.hour,
                input_data.minute,
                input_data.second,
                ('%f' % (float(input_data.microsecond) / 1000000))[2:],
            )
        if input_data.tzinfo is not None:
            tzoff = input_data.tzinfo.utcoffset(input_data)
            if tzoff is not None:
                total_seconds = tzoff.seconds + (86400 * tzoff.days)
                if total_seconds == 0:
                    _svalue += 'Z'
                else:
                    if total_seconds < 0:
                        _svalue += '-'
                        total_seconds *= -1
                    else:
                        _svalue += '+'
                    hours = total_seconds // 3600
                    minutes = (total_seconds - (hours * 3600)) // 60
                    _svalue += '{0:02d}:{1:02d}'.format(hours, minutes)
        else:
            # assume it is in UTC if no timezone info is specified.
            _svalue += 'Z'
        return _svalue
    def gds_parse_datetime(cls, input_data):
        '''Parse an xml date string with timezone information.
           Return a datetime object with time in UTC'''
        tzoff_pattern = re_.compile(r'(\+|-)((0\d|1[0-3]):[0-5]\d|14:00)$')
        tzoff = 0
        if input_data[-1] == 'Z':
            # it is in UTC
            input_data = input_data[:-1]
        else:
            # not in UTC. Get the offset in minutes
            results = tzoff_pattern.search(input_data)
            if results is not None:
                tzoff_parts = results.group(2).split(':')
                tzoff = int(tzoff_parts[0]) * 60 + int(tzoff_parts[1])
                if results.group(1) == '-':
                    tzoff *= -1
                input_data = input_data[:-6]

        if len(input_data.split('.')) > 1:
            dt = datetime_.datetime.strptime(
                input_data, '%Y-%m-%dT%H:%M:%S.%f')
        else:
            dt = datetime_.datetime.strptime(
                input_data, '%Y-%m-%dT%H:%M:%S')
        dt = dt - datetime_.timedelta(minutes=tzoff)
        return dt

class SISBase(MyBase):
    '''Base class for the extended FDSN StationXML.'''

    EOL = '\n'
    INDENT = '  '

    ELEMS = () #for each element create a tuple with name, datatype, isrequired, ismultivalue
    ATTRIBS = (('xsi:type', 'text', False, False), )
    NS = '' #Set the XML namespace for each class. Set 'fsx' for types in FDSNStationXML and 'sis' for the types in the SIS extension.
    EXTNS = ''  # Set a value only when the extension is in a different namespace from the super class
    EXTTYPE = '' # Set a value only for the sis types that extend from types defined in FDSNStationXML. Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = '' #Set a value only when the extension is in a different namespace from the super class


    def __init__(self, **kw):
        self.elemdict = dict([(e[0], e[1:]) for e in self.ELEMS])
        self.attribdict = dict([(e[0], e[1:]) for e in self.ATTRIBS])
        for e in list(self.elemdict.keys()) + list(self.attribdict.keys()):
            if e in kw:
                setattr(self, e, kw.pop(e))
        if kw:
            raise SISError('Unexpected keys %s' % kw)

    def settype(self, type):
        setattr(self, 'xsi:type', type)

    def build(self, node):
        '''Read and set the attributes for this node and call function to read child nodes '''
        self.ns, self.nodename = get_ns_nodename(node)
        for k, v in list(node.attrib.items()):
            #remove the namespaceuris and replace with the namespaceprefix
            for uri,prefix in list(insd.items()):
                k = k.replace('{'+uri+'}', prefix + ':')
            if k in self.attribdict:
                if k == 'xsi:type':
                    #store the remapped prefix:type
                    val = get_remapped_type(v)
                else:
                    datatype, isreqd, ismulti = self.attribdict[k]
                    if datatype == 'text':
                        val = v
                    elif datatype == 'float' or datatype == 'decimal':
                        val = cast_to_float(v, None)
                    elif datatype == 'integer':
                        val = cast_to_integer(v, None)
                    elif datatype == 'boolean':
                        val = cast_to_bool(v, None)
                    elif datatype == 'date':
                        val = self.gds_parse_datetime(v)
                    else:
                        raise SISError ('Unknown datatype %s for attribute %s' %(datatype, k))
                self.__dict__[k] = val

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
            if datatype == 'text':
                val = get_text(child)
            elif datatype == 'float' or datatype == 'decimal':
                val = cast_to_float(get_text(child), child)
            elif datatype == 'integer':
                val = cast_to_integer(get_text(child), child)
            elif datatype == 'boolean':
                val = cast_to_bool(get_text(child), child)
            elif datatype == 'date':
                val = self.gds_parse_datetime(get_text(child))

            #handle the objects
            else:
                val = datatype()
                #Get the type defined in xml in the attribute xsi:type. Note this type value has been remapped.
                nstype = None
                if val.EXTNS and val.EXTTYPE:
                    nstype = '%s:%s' % (val.EXTNS, val.EXTTYPE)
                #Verify that the type defined in xml uses the correponding class in python
                if ctype  and ctype != nstype:
                    print(('Type defined in xml %s, using class %s' % (ctype, datatype)))
                val.build(child)

            # Note that val might contain a simple value or an object. If this element can have multiple values make a list.
            if ismulti:
                if not hasattr(self, cname):
                    self.__dict__[cname] = []
                self.__dict__[cname].append(val)
            else:
                self.__dict__[cname] = val
        else:
            #unknown or unexpected element. raise error.
            raise SISError ('Unknown element %s:%s under node %s'% (cns, cname, self.nodename))
    def validate(self):
        # this function is to be extended in the classes where applicable.
        pass

    def exportdict(self):
        '''Return a python dictionary of this object's elements '''

        exp ={}
        #validate the content of this object
        self.validate()
        all = dict(list(self.elemdict.items()) + list(self.attribdict.items()))
        for k, v in list(all.items()):
            datatype, isreqd, ismulti = v
            if hasattr(self, k):
                if getattr(self, k) is None and isreqd:
                    raise SISError('Expected non-null value for required element or attribute %s'%k)
                if isinstance(datatype, str):
                    # The builtin datatypes of str/float/integer/date are listed as string literals. Single or multivalues both are handled simply.
                    exp[k] = getattr(self, k)
                else:
                    # Datatype is a type matching the xml complex type.
                    # Export the contents as a dictionary
                    if ismulti:
                        # Multivalue possible, stored as a list. Export a list of dictionaries
                        exp[k] = []
                        objs = getattr(self, k)
                        for o in objs:
                            exp[k].append(o.exportdict())
                    else:
                        obj = getattr(self, k)
                        exp[k] = obj.exportdict()
            else:
                if isreqd:
                    raise SISError('Missing required element or attribute %s'% (k))

        return exp
    def getattrxml (self):
        '''
        Return a string containing all the attribute key value pairs with a leading space
        or an empty string if there are no attributes.
        '''

        alist = []
        for k, datatype, isreqd, ismulti in self.ATTRIBS:
            if hasattr(self, k):
                v = getattr(self, k)
                if datatype == 'text':
                    val = self.gds_format_string(quote_attrib(v))
                elif datatype == 'float':
                    val = self.gds_format_float(v)
                elif datatype == 'decimal':
                    val = self.gds_format_decimal(v)
                elif datatype == 'integer':
                    val = self.gds_format_integer(v)
                elif datatype == 'date':
                    val = self.gds_format_datetime(v)
                elif datatype == 'boolean':
                    val = self.gds_format_boolean(v)

                alist.append('%s="%s"' % (k,val))
        axml = ''
        if alist:
            axml = ' ' + ' '.join(alist)
        return axml

    def exportxml(self, outfile, tag, tagns, level):
        '''Write the xml for this object and its subelements. '''

        # Get an xml string with attributes formatted as key='val'
        axml = self.getattrxml()
        if level == 0:
            #write the xxml doctype
            outfile.write('<?xml version="1.0" ?>\n')
            #write out the namespaces and prefixes in the attribute list
            for prefix, uri in list(nsd.items()):
                axml = axml + ' xmlns:%s="%s"' % (prefix, uri)

        #validate the content of this object
        self.validate()
        outfile.write('%s<%s:%s%s>%s' % (self.INDENT*level, tagns, tag, axml, self.EOL))
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


            if hasattr(self, k):
                if getattr(self,k) is None:
                    if isreqd:
                        raise SISError('Expected non-null value for required element or attribute %s in %s'% (k, tag))
                else:
                    #TODO check encoding and formatting. Does double and float need to be handled differently?
                    if not ismulti:
                        v = getattr(self, k)
                        if isinstance(datatype, str):
                            if datatype == 'text':
                                #TODO check encoding for string
                                val = self.gds_format_string(quote_xml(v))
                            elif datatype == 'float':
                                val = self.gds_format_float(v)
                            elif datatype == 'decimal':
                                val = self.gds_format_decimal(v)
                            elif datatype == 'integer':
                                val = self.gds_format_integer(v)
                            elif datatype == 'date':
                                val = self.gds_format_datetime(v)
                            elif datatype == 'boolean':
                                val = self.gds_format_boolean(v)

                            outfile.write('%s<%s:%s>%s</%s:%s>%s' % (self.INDENT*sublevel, ns, k, val, ns, k, self.EOL))
                        else:
                            v.exportxml(outfile, k, ns, level+1)
                    else:
                        vlist = getattr(self, k)
                        for v in vlist:
                            if isinstance(datatype, str):
                                if datatype == 'text':
                                    #TODO check encoding for string
                                    val = self.gds_format_string(quote_xml(v))
                                elif datatype == 'float':
                                    val = self.gds_format_float(v)
                                elif datatype == 'decimal':
                                    val = self.gds_format_decimal(v)
                                elif datatype == 'integer':
                                    val = self.gds_format_integer(v)
                                elif datatype == 'date':
                                    val = self.gds_format_datetime(v)
                                elif datatype == 'boolean':
                                    val = self.gds_format_boolean(v)

                                outfile.write('%s<%s:%s>%s</%s:%s>%s' % (self.INDENT*sublevel, ns, k, val, ns, k, self.EOL))
                            else:
                                v.exportxml(outfile, k, ns, sublevel)
            else:
                if isreqd:
                    raise SISError('Missing required element or attribute %s in %s'% (k, tag))
        outfile.write('%s</%s:%s>%s' % (self.INDENT*level, tagns, tag, self.EOL))

    def exportobj(self, outfile, level):
        '''Write out a python object representation. '''
        self.validate()

        if level == 0:
            #For the outer most class add its name
            outfile.write('%s=%s(%s' % ('rootobj', self.__class__.__name__, self.EOL))
            level = level +1

        for (k, datatype, isreqd, ismulti) in self.ATTRIBS + self.ELEMS:
            if k in self.__dict__:
                v = getattr(self, k)
                if isinstance(datatype, str):
                    if datatype == 'text' and not ismulti:
                        outfile.write("%s%s='%s',%s" % (self.INDENT*level, k, v, self.EOL))
                    else:
                        outfile.write('%s%s=%s,%s' % (self.INDENT*level, k, v, self.EOL))
                else:
                    if ismulti:
                        outfile.write('%s%s=[%s' % (self.INDENT*level, k, self.EOL))
                        level = level+1
                        for elem in v:
                            outfile.write('%s%s(%s' %(self.INDENT*level, elem.__class__.__name__, self.EOL))
                            elem.exportobj(outfile, level+1)
                            outfile.write ('%s),%s' %(self.INDENT*level, self.EOL))
                        outfile.write('%s],%s' %(self.INDENT*level, self.EOL))
                        level = level - 1
                    else:
                        outfile.write('%s%s=%s(%s' %(self.INDENT*level, k, v.__class__.__name__, self.EOL))
                        v.exportobj(outfile, level+1)
                        outfile.write ('%s),%s' %(self.INDENT*level, self.EOL))

        if level == 1:
            #close the outer most class
            outfile.write(')%s'%(self.EOL,))

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
        v = node.text.strip()
        if ndatatype == 'text':
            val = v
        elif ndatatype == 'float' or ndatatype == 'decimal':
            val = cast_to_float(v, None)
        elif ndatatype == 'integer':
            val = cast_to_integer(v, None)
        elif ndatatype == 'boolean':
            val = cast_to_bool(v, None)
        elif ndatatype == 'date':
            val = self.gds_parse_datetime(v)
        else:
            raise SISError ('Unknown datatype %s' %datatype)
        self.ValueOf = val

        for k, v in list(node.attrib.items()):
            if k in self.attribdict:
                datatype, isreqd, ismulti = self.attribdict[k]
                if datatype == 'text':
                    val = v
                elif datatype == 'float' or datatype =='decimal':
                    val = cast_to_float(v, None)
                elif datatype == 'integer':
                    val = cast_to_integer(v, None)
                elif datatype == 'boolean':
                    val = cast_to_bool(v, None)
                elif datatype == 'date':
                    val = self.gds_parse_datetime(v)
                else:
                    raise SISError ('Unknown datatype %s' %datatype)
                self.__dict__[k] = val
            else:
                raise SISError ('Unexpected attribute %s=%s in node %s in class%s' %(k, v, self.nodename, self.__class__.__name__))

    def buildchildren(self, child, node):
        pass

    def exportxml(self, outfile, tag, tagns, level):
        '''Export the value in ValueOf as the content of the passed in tag. '''
        axml = self.getattrxml()

        #validate the content of this object
        self.validate()

        (ndatatype, isreqd) = self.ELEMS[0][1:3]
        if isreqd and self.ValueOf is None:
            raise SISError('Expected non-null value for required element %s'% (tag))

        if ndatatype == 'text':
            val = self.gds_format_string(quote_xml(self.ValueOf))
        elif ndatatype == 'float':
            val = self.gds_format_float(self.ValueOf)
        elif ndatatype == 'decimal':
            val = self.gds_format_decimal(self.ValueOf)
        elif ndatatype == 'integer':
            val = self.gds_format_integer(self.ValueOf)
        elif ndatatype == 'date':
            val = self.gds_format_datetime(self.ValueOf)
        elif ndatatype == 'boolean':
            val = self.gds_format_boolean(self.ValueOf)

        outfile.write('%s<%s:%s%s>%s</%s:%s>%s' % (self.INDENT*level, tagns, tag, axml, val, tagns, tag, self.EOL))


class UnitsType(SISBase):
    ELEMS = (('Name', 'text', True, False),
             ('Description', 'text', False, False),
            )

    NS = 'fsx'

class FloatNoUnitType(SISSimpleType):
    '''
    This is a SimpleType node
    '''
    ELEMS = (('ValueOf', 'float', True, False),)
    ATTRIBS = SISSimpleType.ATTRIBS + (('plusError', 'float', False , False),
                ('minusError', 'float', False , False),
                ('number', 'integer', False , False),
              )
    NS = 'fsx'

    def validate(self):
        plus = getattr(self, 'plusError', None)
        minus = getattr(self, 'minusError', None)
        if plus != minus:
            raise SISError ('The plus error and minus error are different. The loader requires them to be the same. Class %s, plus error %s, minus error %s'%(self.__class__.__name__, plus, minus))
        super(FloatNoUnitType, self).validate()

class FloatType(FloatNoUnitType):
    ATTRIBS = FloatNoUnitType.ATTRIBS + (('unit', 'text', False, False),
                ('i', 'integer', False, False),)
    NS = 'fsx'

class FrequencyType(FloatType):
    def validate(self):
        if hasattr(self, 'unit') and self.unit != 'HERTZ':
            raise SISError ('Frequency unit should be HERTZ. It is specified as %s' % self.unit)
        super(FrequencyType, self).validate()

class DecimationType(SISBase):
    ELEMS = (('InputSampleRate', FrequencyType, True, False),
             ('Factor', 'integer', True, False),
             ('Offset', 'integer', True, False),
             ('Delay', 'float', True, False),
             ('Correction', 'float', True, False),
             )
    NS = 'fsx'

class GainType(SISBase):
    ELEMS = (('Value', 'float', True, False),
             ('Frequency', 'float', True, False),
             )
    NS = 'fsx'

class SensitivityType(GainType):
    ELEMS = GainType.ELEMS + (('InputUnits', UnitsType, True, False),
            ('OutputUnits', UnitsType, True, False),
            ('FrequencyStart', 'float', False, False),
            ('FrequencyEnd', 'float', False, False),
            ('FrequencyDBVariation', 'float', False, False),
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
             ('NormalizationFactor', 'float', True, False),
             ('NormalizationFrequency', 'float', True, False),
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
            ('ApproximationLowerBound', 'decimal', True, False),
            ('ApproximationUpperBound', 'decimal', True, False),
            ('MaximumError', 'decimal', True, False),
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
    NS = 'fsx'

class BaseNodeType (SISBase):
    ELEMS = (('Description', 'text', False, False),
            ('Comment', CommentType, False, True),
            )
    ATTRIBS = SISBase.ATTRIBS + (('code', 'text', True, False),
               ('startDate', 'date', False, False),
               ('endDate', 'date', False, False),
               ('restrictedStatus', 'text', False, False),
               ('alternateCode', 'text', False, False),
               ('historicalCode', 'text', False, False),)
    NS = 'fsx'

class LatitudeType(FloatType):
    ATTRIBS = FloatType.ATTRIBS + (('datum', 'text', False, False),)
    NS = 'fsx'

    def validate(self):
        if hasattr(self, 'unit') and self.unit != 'DEGREES':
            raise SISError ('Latitude should be in DEGREES. It is specified as %s'% self.unit)

        if self.ValueOf <-90 or self.ValueOf > 90:
            raise SISError('Invalid Latitude %s'% self.ValueOf)

        super(LatitudeType, self).validate()

    #Override default exponential out format and precision defined for FloatType
    def gds_format_float(self, input_data):
        return '%.6f' % input_data

class LongitudeType(FloatType):
    ATTRIBS = FloatType.ATTRIBS + (('datum', 'text', False, False),)
    NS = 'fsx'

    def validate(self):
        if hasattr(self, 'unit') and self.unit != 'DEGREES':
            raise SISError ('Longitude should be in DEGREES. It is specified as %s'% self.unit)

        if self.ValueOf <-180 or self.ValueOf > 180:
            raise SISError('Invalid Longitude %s'% self.ValueOf)

        super(LongitudeType, self).validate()

    #Override default exponential out format and precision defined for FloatType
    def gds_format_float(self, input_data):
        return '%.6f' % input_data

class AzimuthType(FloatType):
    NS = 'fsx'

    def validate(self):
        if hasattr(self, 'unit') and self.unit != 'DEGREES':
            raise SISError ('Azimuth should be in DEGREES. It is specified as %s'% self.unit)

        if self.ValueOf <0 or self.ValueOf > 360:
            raise SISError('Invalid Azimuth %s'% self.ValueOf)
        super(AzimuthType, self).validate()

    #Override default exponential out format and precision defined for FloatType
    def gds_format_float(self, input_data):
        return '%.1f' % input_data

class DipType(FloatType):
    NS = 'fsx'

    def validate(self):
        if hasattr(self, 'unit') and self.unit != 'DEGREES':
            raise SISError ('Dip should be in DEGREES. It is specified as %s'% self.unit)

        if self.ValueOf < -90 or self.ValueOf > 90:
            raise SISError('Invalid Dip %s'% self.ValueOf)
        super(DipType, self).validate()

    #Override default exponential out format and precision defined for FloatType
    def gds_format_float(self, input_data):
        return '%.1f' % input_data

class DistanceType(FloatType):
    NS = 'fsx'

    def validate(self):
        if hasattr(self, 'unit') and self.unit != 'METERS':
            raise SISError ('Distance should be in METERS. It is specified as %s'% self.unit)
        super(DistanceType, self).validate()

    #Override default exponential out format and precision defined for FloatType
    def gds_format_float(self, input_data):
        return '%.1f' % input_data

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
            ('Polynomial', PolynomialType, False, False),
            ('Decimation', DecimationType, False, False),
            ('StageGain', GainType, False, False),
            )
    ATTRIBS = SISBase.ATTRIBS + (('resourceId', 'text', False, False),
              ('number', 'integer', False, False),
              )
    NS = 'fsx'

class ResponseType(SISBase):
    ELEMS = (('InstrumentSensitivity', SensitivityType, False, False),
                ('InstrumentPolynomial', SISPolynomialType, False, False),
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
            ('Polynomial', SISPolynomialType, False, False),
            ('Decimation', DecimationType, False, False),
            ('Gain', SISGainType, True, False),
            )
    NS = 'sis'


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
    ELEMS = ResponseType.ELEMS + (('SubResponse', SubResponseType,False, True),)
    EXTNS = 'sis'
    EXTTYPE = 'ResponseType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = ResponseType

class SensorOffsetType(SISBase):
    ELEMS = (('NorthOffset', 'float', False, False),
            ('EastOffset', 'float', False, False),
            ('VerticalOffset', 'float', False, False),
            )
    NS = 'sis'

class SensorSiteDescriptionType(SISBase):
    ELEMS = (('StationHousing', 'integer', False, False),
            ('GeologicSiteClass', 'text', False, False),
            ('PhysicalCondition', 'text', False, False),
            ('Vs30', 'float', False, False),
            ('SensorOffset', SensorOffsetType, False, False),
            )
    NS = 'sis'

class ChannelType(BaseNodeType):
    ELEMS = BaseNodeType.ELEMS + (('ExternalReference', ExternalReferenceType, False, True),
                ('Latitude', LatitudeType, True, False),
                ('Longitude', LongitudeType, True, False),
                ('Elevation', DistanceType, True, False),
                ('Depth', DistanceType, True, False),
                ('Azimuth', AzimuthType, False, False),
                ('Dip', DipType, False, False),
                ('Type', 'text', False, True),
                ('SampleRate', FloatType, False, False),
                ('SampleRateRatio', SampleRateRatioType, False, False),
                ('StorageFormat', 'text', False, False),
                ('ClockDrift', FloatType, False, False),
                ('CalibrationUnits', UnitsType, False, False),
                ('Sensor', EquipmentType, False, False),
                ('PreAmplifier', EquipmentType, False, False),
                ('DataLogger', EquipmentType, False, False),
                ('Equipment', EquipmentType, False, False),
                ('Response', SISResponseType, False, False),
                )
    ATTRIBS = BaseNodeType.ATTRIBS + (('locationCode', 'text', False, False),)
    NS = 'fsx'

class SISChannelType(ChannelType):
    ELEMS = ChannelType.ELEMS + (('StationChannelNumber', 'integer', False, False),
                ('MeasurementType', 'text', False, False),
                ('SignalUnits', UnitsType, False, False),
                ('Clip', 'float', False, False),
                ('Cutoff', 'float', False, False),
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
    ELEMS = (('Agency', 'text', True, True),
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
    ELEMS = BaseNodeType.ELEMS + (('Latitude', LatitudeType, True, False),
            ('Longitude', LongitudeType, True, False),
            ('Elevation', DistanceType, True, False),
            ('Site', SiteType, True, False),
            ('Vault', 'text', False, False),
            ('Geology', 'text', False, False),
            ('Equipment', EquipmentType, False, True),
            ('Operator', OperatorType, False, True),
            ('CreationDate', 'date', True, False),
            ('TerminationDate', 'date', False, False),
            ('TotalNumberChannels', 'integer', False, False),
            ('SelectedNumberChannels', 'integer', False, False),
            ('ExternalReference', ExternalReferenceType, False, True),
            ('Channel', SISChannelType, False, True),
            )
    NS = 'fsx'

class SISStationType(StationType):
    ELEMS = StationType.ELEMS + (('DatumVertical', 'text', False, False),
            ('SecondaryStationNumber', 'text', False, False),
            ('ReferenceAzimuth', AzimuthType, False, False),
            ('GeoSite', GeoSiteType, False, False),
            )
    ATTRIBS = StationType.ATTRIBS + (('codeType', 'text', False, False), )
    EXTNS = 'sis'
    EXTTYPE = 'StationType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = StationType

class NetworkType (BaseNodeType):
    ELEMS = BaseNodeType.ELEMS + (('TotalNumberStations', 'integer', False, False),
            ('SelectedNumberStations', 'integer', False, False),
            ('Station', SISStationType, False, True),
            )
    NS = 'fsx'

class RootType (SISBase):
    ELEMS = (('Source', 'text', True, False),
            ('Sender', 'text', False, False),
            ('Module', 'text', False, False),
            ('ModuleURI', 'text', False, False),
            ('Created', 'date', True, False),
            ('Network', NetworkType, True, True),
            )
    ATTRIBS = SISBase.ATTRIBS + (('schemaVersion', 'text', False, False),)
    NS = 'fsx'

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
            ('InputRange', 'float', False, False),
            ('InputRangeUnit', UnitsType, False, False),
            ('OutputRange', 'float', False, False),
            ('OutputRangeUnit', UnitsType, False, False),
            ('Comments', 'text', False, False),
            ('NeedsReview', 'boolean', False, False),
            ('NaturalFrequency', 'float', False, False),
            ('DampingConstant', 'float', False, False),
            ('Attenuation', 'float', False, False),
            ('StandardGain', 'float', False, False),
            ('TuningHertz', 'float', False, False),
            ('TuningVolt', 'float', False, False),
           )
    NS = 'sis'

    def validate(self):
        if not hasattr(self, 'CalibrationDate') and not hasattr(self, 'CalibrationDateUnknown'):
            raise SISError('If calibration date is not known, then provide element CalibrationDateUnknown with value true')
        super(CalibrationType, self).validate()


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
    ELEMS = RootType.ELEMS + (('HardwareResponse', HardwareResponseType, False, False),
            )
    ATTRIBS = RootType.ATTRIBS + (
        ('sis:schemaLocation', 'text', False, False),
        ('xsi:schemaLocation', 'text', False, False),
        )
    EXTNS = 'sis'
    EXTTYPE = 'RootType' # Use EXTNS:EXTTYPE to set the value for xsi:type
    SUPERCLASS = RootType

    def __init__(self, **kw):
        super(SISRootType, self).__init__(**kw)
        if 'sis:schemaLocation' not in self.__dict__:
            setattr(self, 'sis:schemaLocation', '%s %s' %(nsd['sis'], nslocd['sis']))


def parse(inFileName, rootType = SISRootType):
    global docnsmap, docnsprefixmap
    doc = parsexml_(inFileName)
    root = doc.getroot()
    docnsmap = root.nsmap
    for k, uri in list(docnsmap.items()):
        #remap the prefixes used in this document to the default defined in this parser using the uri
        if uri in insd:
            docnsprefixmap[k] = insd[uri]

    obj = rootType()
    obj.build(root)
    return obj



USAGE_TEXT = """
Usage: python <Parser>.py <in_xml_file>
"""

def usage():
    print(USAGE_TEXT)
    sys.exit(1)


def main():
    args = sys.argv[1:]
    if len(args) == 1:

        # Parse an xml file
        obj = parse(args[0])

        # Export xml
        print('------------ output xml --------------')
        obj.exportxml(sys.stdout, 'FDSNStationXML', 'fsx', 0)

        # Export the python object representation
        print('------------ output object --------------')
        obj.exportobj(sys.stdout, 0)

        # Convert the python object into a dictionary
        print('------------ output dict --------------')
        exp = obj.exportdict()
        import pprint
        pp = pprint.PrettyPrinter(indent=1)
        pp.pprint(exp)

    else:
        usage()

if __name__ == '__main__':
    main()
