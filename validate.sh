#!/bin/bash

if [[ ! -r 'validator/ValidateStationXml.class' ]]
then
    echo
    echo "validator not in current directory, please get with:"
    echo
    echo "wget http://maui.gps.caltech.edu/SIStrac/raw-attachment/wiki/SIS/Code/validator.tar.gz"
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
else
    if [[ ! -n $1 ]]
    then
        echo "Warn: no stationxml file on command line"
    elif [[ ! -r $1 ]]
    then
        echo "Warn: cannot read stationxml file"
    else
        ERRFILE=`java -cp xerces-2_11_0-xml-schema-1.1-beta/xercesImpl.jar:xerces-2_11_0-xml-schema-1.1-beta/xml-apis.jar:xerces-2_11_0-xml-schema-1.1-beta/serializer.jar:xerces-2_11_0-xml-schema-1.1-beta/org.eclipse.wst.xml.xpath2.processor_1.1.0.jar:validator ValidateStationXml -i $*`

        if [ $ERRFILE = "0" ]
        then
           echo "Valid"
        else
           less $ERRFILE
           echo $ERRFILE
        fi
    fi
fi
