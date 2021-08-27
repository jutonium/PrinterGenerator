#!/usr/bin/env python3

# since this is probably used on a system with munki the munki-included python should be used:
# #!/usr/local/munki/munki-python
# coding: utf8


'''
This module contains the core functionality of the printer generator.
'''
__author__ = 'jutonium (github)'
__version__ = '2.0 RC'

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

def _get_options_str(options):
    # options should be a list formatted as a string with spaces as seperators
    # options -> set -> list and propper iteration
    options_str = ''
    if options:
        if isinstance(options, str):
            # string -> list
            options = options.split(' ')
        elif len(options) == 1 and isinstance(options[0], str):
            # list of single string -> list
            options = options[0].split(' ')
        options_lst = list(set(options))
        for option in options_lst:
            options_str += '\"%s\":\"%s\"' % (str(option.split('=')[0]),
                                              str(option.split('=')[1])) + ', '
        options_str = options_str[:-2]
    return options_str

def get_printer_parameters():
    '''
    Create and return a template dict with all parameters.
    '''
    return {
        'printername':  '',
        'location':     '',
        'display_name': '',
        'address':      '',
        'driver':       '',
        'description':  '',
        'options':      [],
        'version':      '',
        'requires':     '',
        'icon_name':    '',
        'catalogs':      [],
        'subdirectory': '',
        'munkiname':    ''
    }

def get_printer_defaults():
    '''
    Create and return a template dict with default for some parameters.
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
        'catalogs':      ['testing'],
        'subdirectory': '',
        'munkiname':    ''
    }

def check_printer_vars(parameters):
    '''
    Checks all printervariables and replaces some with defaults if not present.
    '''
    defaults = get_printer_defaults()

    # enforce existence of important parameters
    if (not parameters['printername'] or
            re.search(r"[\s#/]", parameters['printername'])):
        # printernames can't contain spaces, tabs, # or /.  See lpadmin manpage for details.
        print("ERROR: Printername must be specified and must not contain spaces, tabs, # or /.",
              file=sys.stderr)
        print("Skipping printer " + parameters['printername'] + ".", file=sys.stderr)
        return None
    if not parameters['driver']:
        print("ERROR: Driver must be specified.", file=sys.stderr)
        print("Skipping printer " + parameters['printername'] + ".", file=sys.stderr)
        return None
    if not parameters['address']:
        print("ERROR: Address must be specified.", file=sys.stderr)
        print("Skipping printer " + parameters['printername'] + ".", file=sys.stderr)
        return None

    parameters['description'] = parameters['description'] if parameters['description'] \
        else defaults['description']

    parameters['display_name'] = parameters['display_name'] if parameters['display_name'] \
        else parameters['printername']

    parameters['munkiname'] = parameters['munkiname'] if parameters['munkiname'] \
        else parameters['printername']

    parameters['version'] = parameters['version'] if parameters['version'] \
        else defaults['version']

    parameters['icon_name'] = parameters['icon_name'] if parameters['icon_name'] \
        else defaults['icon_name']

    if isinstance(parameters['catalogs'], str):
        parameters['catalogs'] = [parameters['catalogs']]

    parameters['catalogs'] = parameters['catalogs'] if parameters['catalogs'] \
        else defaults['catalogs']

    parameters['location'] = parameters['location'] if parameters['location'] \
        else parameters['printername']

    # convenience functions
    if '://' not in parameters['address']:
        # Assume the user did not pass in a full address and protocol and
        # wants to use the default, lpd://
        parameters['address'] = 'lpd://' + parameters['address']

    if not parameters['driver'].startswith('/Library'):
        # Assume the user passed in only a relative filename
        parameters['driver'] = os.path.join('/Library/Printers/PPDs/Contents/Resources',
                                            parameters['driver'])


    return parameters

def generate_pkginfo(parameters):
    '''
    Create a dictionary representing a munki-nopkg-style printer setup.
    Returns the newly created dict.
    '''
    parameters = check_printer_vars(parameters)

    pkginfo = copy.deepcopy(TEMPLATE)
    # Options in the form of "Option=Value Option2=Value Option3=Value"
    # Requires in the form of "package1 package2" Note: the space seperator
    options_str = _get_options_str(parameters['options'])

   # root pkginfo variable replacement
    pkginfo['description'] = parameters['description']
    pkginfo['display_name'] = parameters['display_name']
    pkginfo['name'] = parameters['munkiname']
    pkginfo['version'] = parameters['version']
    pkginfo['icon_name'] = parameters['icon_name']
    pkginfo['catalogs'] = parameters['catalogs']

    # installcheck_script variable replacement
    pkginfo['installcheck_script'] = pkginfo['installcheck_script'].\
        replace("PRINTERNAME", parameters['printername'])
    pkginfo['installcheck_script'] = pkginfo['installcheck_script'].\
        replace("ADDRESS", parameters['address'])
    pkginfo['installcheck_script'] = pkginfo['installcheck_script'].\
        replace("DISPLAY_NAME", parameters['display_name'])
    pkginfo['installcheck_script'] = pkginfo['installcheck_script'].\
        replace("LOCATION", parameters['location'].replace('"', ''))
    pkginfo['installcheck_script'] = pkginfo['installcheck_script'].\
        replace("OPTIONS", options_str)
    # postinstall_script variable replacement
    pkginfo['postinstall_script'] = pkginfo['postinstall_script'].\
        replace("PRINTERNAME", parameters['printername'])
    pkginfo['postinstall_script'] = pkginfo['postinstall_script'].\
        replace("ADDRESS", parameters['address'])
    pkginfo['postinstall_script'] = pkginfo['postinstall_script'].\
        replace("DISPLAY_NAME", parameters['display_name'])
    pkginfo['postinstall_script'] = pkginfo['postinstall_script'].\
        replace("LOCATION", parameters['location'].replace('"', ''))
    pkginfo['postinstall_script'] = pkginfo['postinstall_script'].\
        replace("DRIVER", parameters['driver'].replace('"', ''))
    pkginfo['postinstall_script'] = pkginfo['postinstall_script'].\
        replace("OPTIONS", options_str)
    # uninstall_script variable replacement
    pkginfo['uninstall_script'] = pkginfo['uninstall_script'].\
        replace("PRINTERNAME", parameters['printername'])
    # required packages
    if parameters['requires']:
        pkginfo['requires'] = \
            [r.replace('\\', '') for r in re.split(r"(?<!\\)\s", parameters['requires'])]

    return pkginfo

if __name__ == '__main__':
    print('Please import this module with import pgen_mod.')
