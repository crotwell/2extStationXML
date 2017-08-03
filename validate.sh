#!/bin/bash

SCHEMAURL='https://anss-sis.scsn.org/xml/ext-stationxml/2.0/sis_extension.xsd'
SCHEMA='sis_extension_2.0.xsd'

if [[ ! -r 'xmlvalidator/ValidateStationXml.class' ]]
then
    echo
    echo "xmlvalidator not in current directory, please get with:"
    echo
    echo "wget http://wiki.anss-sis.scsn.org/SIStrac/raw-attachment/wiki/SIS/Code/validator.tar.gz"
    echo "tar ztf validator.tar.gz"
    echo
elif [[ ! -r 'xerces-2_11_0-xml-schema-1.1-beta/xercesImpl.jar' ]]
then
    echo
    echo "Xerces not in current directory, please get with:"
    echo
    echo "wget http://mirror.cc.columbia.edu/pub/software/apache/xerces/j/binaries/Xerces-J-bin.2.11.0-xml-schema-1.1-beta.tar.gz"
    echo "tar zxf Xerces-J-bin.2.11.0-xml-schema-1.1-beta.tar.gz"
    echo
    echo "Note it must be the xml-schema-1.1 version."
    echo
elif [[ ! -r $SCHEMA ]]
then
    echo
    echo "$SCHEMA not in current directory, please get with:"
    echo
    echo "wget -O $SCHEMA $SCHEMAURL"
    echo
    echo "Note you may choose the a different version, like 2.1 instead, but will need to change this script."
    echo
else
    if [[ ! -n $1 ]]
    then
        echo "Warn: no stationxml file on command line"
    elif [[ ! -r $1 ]]
    then
        echo "Warn: cannot read stationxml file"
    else
        ERRFILE=`java -cp xerces-2_11_0-xml-schema-1.1-beta/xercesImpl.jar:xerces-2_11_0-xml-schema-1.1-beta/xml-apis.jar:xerces-2_11_0-xml-schema-1.1-beta/serializer.jar:xerces-2_11_0-xml-schema-1.1-beta/org.eclipse.wst.xml.xpath2.processor_1.1.0.jar:xmlvalidator ValidateStationXml -s $SCHEMA -i $*`

        if [ $ERRFILE = "0" ]
        then
           echo "Valid"
        else
           less $ERRFILE
           echo $ERRFILE
        fi
    fi
fi
