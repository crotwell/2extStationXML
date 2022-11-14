import os
import subprocess

SCHEMA_FILE = "sis_extension_3.0.xsd"

def xerces_validate(stationxml):
    if not os.path.exists(stationxml):
        print("ERROR: can't fine stationxml file %s"%(stationxml,))
        return False

    # validate with SIS validator
    # http://wiki.anss-sis.scsn.org/SIStrac/wiki/SIS/Code

    if not os.path.exists(SCHEMA_FILE):
        print("""
Can't find schema file sis_extension_3.0.xsd

wget -O sis_extension_3.0.xsd https://anss-sis.scsn.org/xml/ext-stationxml/3.0/sis_extension.xsd
""")
        return False


    if os.path.exists('xerces-2_12_1-xml-schema-1.1') and os.path.exists('xmlvalidator/ValidateStationXml.class'):
        print("Validating xml...")
        try:
            classpath = '.:xmlvalidator'
            xercesDir = 'xerces-2_12_1-xml-schema-1.1'
            jarList = ['xercesImpl.jar',
                       'xml-apis.jar',
                       'serializer.jar',
                       'org.eclipse.wst.xml.xpath2.processor_1.2.0.jar']
            for j in jarList:
                classpath = classpath+':'+xercesDir+"/"+j

            # 'xmlvalidator:xerces-2_12_0-xml-schema-1.1/xercesImpl.jar:xerces-2_11_0-xml-schema-1.1-beta/xml-apis.jar:xerces-2_11_0-xml-schema-1.1-beta/serializer.jar:xerces-2_11_0-xml-schema-1.1-beta/org.eclipse.wst.xml.xpath2.processor_1.1.0.jar:.'
            validateOut = subprocess.check_output(['java', '-cp', classpath, 'ValidateStationXml', '-s', SCHEMA_FILE, '-i', stationxml])
        except subprocess.CalledProcessError as e:
            validateOut = "error calling process: " + str(e.output)
        validateOut = validateOut.strip()
        if not validateOut == b'0':
            print("  ERROR: invalid stationxml document, errors: '%s'"%(validateOut,))
            return False
        else:
            print("  OK")
            return True
    else:
        print("""
ERROR: Can't find validator: %s %s

        wget http://mirror.cc.columbia.edu/pub/software/apache//xerces/j/binaries/Xerces-J-bin.2.12.1-xml-schema-1.1.tar.gz
        tar zxf Xerces-J-bin.2.12.1-xml-schema-1.1.tar.gz
        wget http://maui.gps.caltech.edu/SIStrac/raw-attachment/wiki/SIS/Code/validator.tar.gz
        tar ztf validator.tar.gz

We assume the directories validator and xerces-2_12_1-xml-schema-1.1
are in current directory for validation.
        """%(os.path.exists('xerces-2_12_1-xml-schema-1.1') , os.path.exists('validator/ValidateStationXml.class')))

        return False
