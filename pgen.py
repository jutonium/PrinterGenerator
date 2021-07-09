#!/usr/bin/env python3

# since this is probably used on a system with munki the munki-included python should be used:
# #!/usr/local/munki/munki-python
# coding: utf8


'''
This module contains the core functionality of the printer generator.
'''
__author__ = 'Johannes Bock (bock@wycomco.de)'
__version__ = '2.0.2_rc'

import os
import copy
import sys
import re

INSTALLCHECK_SCRIPT = '''#!/usr/local/munki/munki-python
import subprocess
import sys
import shlex

printerOptions = { OPTIONS }

cmd = ['/usr/bin/lpoptions', '-p', 'PRINTERNAME', '-l']
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
(lpoptLongOut, lpoptErr) = proc.communicate()

# lpoptions -p printername -l will still exit 0 even if printername does not exist
# but it will print to stderr
if lpoptErr:
    print(lpoptErr)
    sys.exit(0)

cmd = ['/usr/bin/lpoptions', '-p', 'PRINTERNAME']
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
(lpoptOut, lpoptErr) = proc.communicate()

#Note: lpoptions -p printername will never fail. If PRINTERNAME does not exist, it
#will still exit 0, but just produce no output.
#Thanks, cups, I was having a good day until now.

for option in lpoptLongOut.splitlines():
    for myOption in printerOptions.keys():
        optionName = option.split("/", 1)[0]
        optionValues = option.split("/",1)[1].split(":")[1].strip().split(" ")
        for opt in optionValues:
            if "*" in opt:
                actualOptionValue = opt.replace('*', '')
                break
        if optionName == myOption:
            if not printerOptions[myOption].lower() == actualOptionValue.lower():
                print("Found mismatch: %s is '%s', should be '%s'" % (myOption, printerOptions[myOption], actualOptionValue))
                sys.exit(0)

try:
    lpoptOut = lpoptOut.decode("utf-8")
except UnicodeDecodeError:
    sys.exit(0)

optionDict = {}
for builtOption in shlex.split(lpoptOut):
    try:
        optionDict[builtOption.split("=")[0]] = builtOption.split("=")[1]
    except:
        optionDict[builtOption.split("=")[0]] = None

comparisonDict = { "device-uri":"ADDRESS", "printer-info":"DISPLAY_NAME", "printer-location":"LOCATION" }
for keyName in comparisonDict.keys():
    comparisonDict[keyName] = None if comparisonDict[keyName].strip() == "" else comparisonDict[keyName]
    optionDict[keyName] = None if keyName not in optionDict or optionDict[keyName].strip() == "" else optionDict[keyName]
    if not comparisonDict[keyName] == optionDict[keyName]:
        print("Settings mismatch: %s is '%s', should be '%s'" % (keyName, optionDict[keyName], comparisonDict[keyName]))
        sys.exit(0)

sys.exit(1)
'''

PREINSTALL_SCRIPT = '''#!/usr/local/munki/munki-python
import subprocess
import sys
'''

POSTINSTALL_SCRIPT = '''#!/usr/local/munki/munki-python
import subprocess
import sys

# Populate these options if you want to set specific options for the printer. E.g. duplexing installed, etc.
printerOptions = { OPTIONS }

cmd = [ '/usr/sbin/lpadmin', '-x', 'PRINTERNAME' ]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
(lpadminxOut, lpadminxErr) = proc.communicate()

# Install the printer
cmd = [ '/usr/sbin/lpadmin',
        '-p', 'PRINTERNAME',
        '-L', 'LOCATION',
        '-D', 'DISPLAY_NAME',
        '-v', 'ADDRESS',
        '-P', "DRIVER",
        '-E',
        '-o', 'printer-is-shared=false',
        '-o', 'printer-error-policy=abort-job' ]

for option in printerOptions.keys():
    cmd.append("-o")
    cmd.append(str(option) + "=" +  str(printerOptions[option]))

proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
(lpadminOut, lpadminErr) = proc.communicate()

if lpadminErr:
        if "Printer drivers are deprecated" in lpadminErr or "Reine Wartelisten wurden verworfen" in lpadminErr:
                # work around lpadmin deprecation message
                print("Install successful - caught deprecation message; preventing exit 1")
        else:
                print("Error: %s" % lpadminErr)
                sys.exit(1)
print("Results: %s" % lpadminOut)
sys.exit(0)
'''

UNINSTALL_SCRIPT = '''#!/bin/bash
/usr/sbin/lpadmin -x PRINTERNAME
'''

TEMPLATE = \
    {
        'autoremove': False,
        'catalogs': ['testing'],
        'description': 'DESCRIPTION',
        'display_name': 'DISPLAY_NAME',
        'installcheck_script': INSTALLCHECK_SCRIPT,
        'installer_type': 'nopkg',
        'minimum_os_version': '10.7.0',
        'name': 'AddPrinter_DISPLAYNAME',
        'postinstall_script': POSTINSTALL_SCRIPT,
        'unattended_install': True,
        'uninstall_method': 'uninstall_script',
        'uninstall_script': UNINSTALL_SCRIPT,
        'uninstallable': True,
        'version': 'VERSION'
    }

@staticmethod
def _get_options_str(options):
    # options should be a list formatted as a string with spaces as seperators
    options_lst = options.split(" ")
    options_str = ''
    for option in options_lst:
        if option == options_lst[-1]: #FIXME if an option is defined twice the iteration will stop too soon
            # better: options -> set -> list and propper iteration
            options_str += "\"%s\":\"%s\"" % (str(option.split('=')[0]), str(option.split('=')[1]))
        else:
            options_str += "\"%s\":\"%s\"" % (str(option.split('=')[0]),
                                              str(option.split('=')[1])) + ', '
    return options_str

def get_printer_variables():
    '''
    Create and return a template dict with all printer_variables.
    '''
    return {
        'printername':  '',
        'location':     '',
        'display_name': '',
        'address':      '',
        'driver':       '',
        'description':  '',
        'options':      '',
        'version':      '1.0',
        'requires':     '',
        'icon_name':    '',
        'catalogs':      '',
        'subdirectory': '',
        'munkiname':    ''
    }

def generate_printer(printer_variables):
    '''
    Create a dictionary representing a munki-nopkg-style printer setup.
    Returns the newly created dict.
    '''
    print(printer_variables)
    if not printer_variables['printername'] or re.search(r"[\s#/]", printer_variables['printername']):
        # printernames can't contain spaces, tabs, # or /.  See lpadmin manpage for details.
        print("ERROR: Printername must be specified and must not contain spaces, tabs, # or /.", file=sys.stderr)
        print("Skipping printer " + printer_variables['printername'] + ".", file=sys.stderr)
        return None
    if not printer_variables['driver']:
        print("ERROR: Driver must be specified.", file=sys.stderr)
        print("Skipping printer " + printer_variables['printername'] + ".", file=sys.stderr)
        return None
    if not printer_variables['address']:
        print("ERROR: Address must be specified.", file=sys.stderr)
        print("Skipping printer " + printer_variables['printername'] + ".", file=sys.stderr)
        return None

    printer_plist = copy.deepcopy(TEMPLATE)
    # Options in the form of "Option=Value Option2=Value Option3=Value"
    # Requires in the form of "package1 package2" Note: the space seperator
    options_str = ''
    if options_str:
        options_str = _get_options_str(options_str)

   # root pkginfo variable replacement
    if printer_variables['description']:
        printer_plist['description'] = printer_variables['description']
    else:
        printer_plist['description'] = ''
    
    if printer_variables['display_name']:
        printer_plist['display_name'] = printer_variables['display_name']
    else:
        printer_plist['display_name'] = printer_variables['printername']

    if printer_variables['munkiname']:
        printer_plist['name'] = printer_variables['munkiname']
    else:
        printer_plist['name'] = printer_variables['display_name']

    if printer_variables['version']:
        printer_plist['version'] = printer_variables['version']
    else:
        printer_plist['version'] = '1.0'

    if printer_variables['icon_name']:
        printer_plist['icon_name'] = printer_variables['icon_name']
    else:
        printer_plist['icon_name'] = ''

    if '://' not in printer_variables['address']:
        # Assume the user did not pass in a full address and protocol and wants to use the default, lpd://
        printer_variables['address'] = 'lpd://' + printer_variables['address']
    
    if not printer_variables['driver'].startswith('/Library'):
        # Assume the user passed in only a relative filename
        printer_variables['driver'] = os.path.join('/Library/Printers/PPDs/Contents/Resources', printer_variables['driver'])

    # installcheck_script variable replacement
    printer_plist['installcheck_script'] = printer_plist['installcheck_script'].replace("PRINTERNAME", printer_variables['printername'])
    printer_plist['installcheck_script'] = printer_plist['installcheck_script'].replace("ADDRESS", printer_variables['address'])
    printer_plist['installcheck_script'] = printer_plist['installcheck_script'].replace("DISPLAY_NAME", printer_variables['display_name'])
    printer_plist['installcheck_script'] = printer_plist['installcheck_script'].replace("LOCATION", printer_variables['location'].replace('"', ''))
    printer_plist['installcheck_script'] = printer_plist['installcheck_script'].replace("OPTIONS", options_str)
    # postinstall_script variable replacement
    printer_plist['postinstall_script'] = printer_plist['postinstall_script'].replace("PRINTERNAME", printer_variables['printername'])
    printer_plist['postinstall_script'] = printer_plist['postinstall_script'].replace("ADDRESS", printer_variables['address'])
    printer_plist['postinstall_script'] = printer_plist['postinstall_script'].replace("DISPLAY_NAME", printer_variables['display_name'])
    printer_plist['postinstall_script'] = printer_plist['postinstall_script'].replace("LOCATION", printer_variables['location'].replace('"', ''))
    printer_plist['postinstall_script'] = printer_plist['postinstall_script'].replace("DRIVER", printer_variables['driver'].replace('"', ''))
    printer_plist['postinstall_script'] = printer_plist['postinstall_script'].replace("OPTIONS", options_str)
    # uninstall_script variable replacement
    printer_plist['uninstall_script'] = printer_plist['uninstall_script'].replace("PRINTERNAME", printer_variables['printername'])
    # required packages
    if printer_variables['requires']:
        printer_plist['requires'] = [r.replace('\\', '') for r in re.split(r"(?<!\\)\s", printer_variables['requires'])]

    return printer_plist

if __name__ == '__main__':
    print('Please import this module with import pgen_mod.')
