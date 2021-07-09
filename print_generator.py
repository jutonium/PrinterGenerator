#!/usr/bin/env python3

# since this is probably used on a system with munki the munki-included python should be used:
# #!/usr/local/munki/munki-python
# coding: utf8

'''
This module uses the printer p_gen.py module to generate a munki-nopkg-printer setup from variables
and writes it to disk.
'''
__author__ = 'Johannes Bock (bock@wycomco.de)'
__version__ = '2.0.2_rc'


import argparse
import csv
import os
import sys
from xml.parsers.expat import ExpatError

from plistlib import load as load_plist
from plistlib import dump as dump_plist

import pgen

# Preference hanlding copied from Munki:
# https://github.com/munki/munki/blob/e8ccc5f53e8f69b59fbc153a783158a34ca6d1ea/code/client/munkilib/cliutils.py#L55

BUNDLE_ID = 'com.googlecode.munki.munkiimport'
PREFSNAME = BUNDLE_ID + '.plist'
PREFSPATH = os.path.expanduser(os.path.join('~/Library/Preferences', PREFSNAME))

FOUNDATION_SUPPORT = True
try:
    # PyLint cannot properly find names inside Cocoa libraries, so issues bogus
    # No name 'Foo' in module 'Bar' warnings. Disable them.
    # pylint: disable=E0611
    from Foundation import CFPreferencesCopyAppValue
    # pylint: enable=E0611
except ImportError:
    # CoreFoundation/Foundation isn't available
    FOUNDATION_SUPPORT = False

if FOUNDATION_SUPPORT:
    def pref(prefname, default=None):
        """Return a preference. Since this uses CFPreferencesCopyAppValue,
        Preferences can be defined several places. Precedence is:
            - MCX/Configuration Profile
            - ~/Library/Preferences/ByHost/
                com.googlecode.munki.munkiimport.XX.plist
            - ~/Library/Preferences/com.googlecode.munki.munkiimport.plist
            - /Library/Preferences/com.googlecode.munki.munkiimport.plist
        """
        value = CFPreferencesCopyAppValue(prefname, BUNDLE_ID)
        if value is None:
            return default
        
        return value

else:
    def pref(prefname, default=None):
        """Returns a preference for prefname. This is a fallback mechanism if
        CoreFoundation functions are not available -- for example to allow the
        possible use of makecatalogs or manifestutil on Linux"""
        if not hasattr(pref, 'cache'):
            pref.cache = None
        if not pref.cache:
            try:
                pwd = os.path.dirname(os.path.realpath(__file__)) #FIXME questionable!
                f = open(os.path.join(pwd, PREFSPATH), 'rb')
                pref.cache = load_plist(f)
                f.close()
            except (IOError, OSError, ExpatError):
                pref.cache = {}
        if prefname in pref.cache:
            return pref.cache[prefname]
        # no pref found
        return default

def parse_arguments():
    '''
    Process arguments.
    '''
    parser = argparse.ArgumentParser(description='Generate a Munki nopkg-style pkginfo for printer installation.')
    parser.add_argument('--printername', help='Name of printer queue. May not contain spaces, tabs, # or /. Required.')
    parser.add_argument('--driver', help='Name of driver file in /Library/Printers/PPDs/Contents/Resources/. Can be relative or full path. Required.')
    parser.add_argument('--address', help='IP or DNS address of printer. If no protocol is specified, defaults to lpd://. Required.')
    parser.add_argument('--location', help='Location name for printer. Optional. Defaults to printername.')
    parser.add_argument('--displayname', help='Display name for printer (and Munki pkginfo). Optional. Defaults to printername.')
    parser.add_argument('--desc', help='Description for Munki pkginfo only. Optional.')
    parser.add_argument('--requires', help='Required packages in form of space-delimited \'CanonDriver1 CanonDriver2\'. Optional.')
    parser.add_argument('--options', nargs='*', dest='options', help='Printer options in form of space-delimited \'Option1=Key Option2=Key Option3=Key\', etc. Optional.')
    parser.add_argument('--version', help='Version number of Munki pkginfo. Optional. Defaults to 1.0.', default='1.0')
    parser.add_argument('--icon', help='Specifies an existing icon in the Munki repo to display for the printer in Managed Software Center. Optional.')

    parser.add_argument('--catalog', help='Specifies the catalog which shall be used. Defaults to default_catalog if present or testing otherweise. Optional.')
    parser.add_argument('--munkiname', help='Name of Munki item. Defaults to printername. Optional.')
    parser.add_argument('--repo', help='Path to Munki repo. If specified, we will try to write directly to its containing pkgsinfo directory. If not defined, we will write to current working directory. Optional.')
    parser.add_argument('--subdirectory', help='Subdirectory of Munki\'s pkgsinfo directory. Optional.')
    parser.add_argument('--pkginfoext', help='File extension for the nopkg. Defaults to pkginfo. Optional.', default='pkginfo')

    parser.add_argument('--csv', help='Path to CSV file containing printer info. If CSV is provided, all other options are ignored.')
    args = parser.parse_args()
    
    if args.csv:
        return args
    # check for missing parameters and quit if not present
    if not args.printername:
        print(os.path.basename(sys.argv[0]) + ': error: argument --printername is required', file=sys.stderr)
        parser.print_usage()
        sys.exit(1)
    if not args.driver:
        print(os.path.basename(sys.argv[0]) + ': error: argument --driver is required', file=sys.stderr)
        parser.print_usage()
        sys.exit(1)
    if not args.address:
        print(os.path.basename(sys.argv[0]) + ': error: argument --address is required', file=sys.stderr)
        parser.print_usage()
        sys.exit(1)
    return args

def create_path_safe(mydir):
    '''Create all directories leading to the file stated.'''
    # mydir = os.path.split(myfile)[0]
    try:
        os.makedirs(mydir)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            logging.error('Directory %s could not be created!', mydir)
            return False
    return True

def write_pkginfo(full_file_name, new_printer):
    target_dir = os.path.split(full_file_name)[0]
    target_exists = False
    if not os.path.isdir(target_dir):
        target_exists = create_path_safe(target_dir)
    if target_exists:
        #FIXME add error handling
        file_handle = open(full_file_name, 'wb')
        dump_plist(new_printer, file_handle)
        file_handle.close()

def translate_row(printer_row):
    translation = {
        'printername':  'printer name',
        'location':     'location',
        'display_name': 'display name',
        'address':      'address',
        'driver':       'driver',
        'description':  'description',
        'options':      'options',
        'version':      'version',
        'requires':     'requires',
        'icon_name':    'icon',
        'catalogs':      'catalogs',
        'subdirectory': 'subdirectory',
        'munkiname':    'munki name'
    }
    new_row = dict()
    for key, value in printer_row.items():
        new_row[key.lower()] = value

    printer_variables = pgen.get_printer_variables()
    for key in translation:
        print(translation[key])
        print(new_row.get(translation[key]))
        print()
        printer_variables[key] = new_row.get(translation[key], printer_variables[key])

    return printer_variables


def csv_run(args, target_dir, file_ext):
    # A CSV was found, use that for all data.

    with open(args.csv, mode='r') as infile:
        file_sample = infile.read(128)
        infile.seek(0) # back to the beginning
        num_comma = file_sample.count(',')
        num_semicolon = file_sample.count(';')
        if num_comma > num_semicolon:
            reader = csv.DictReader(infile, delimiter=',')
        else:
            reader = csv.DictReader(infile, delimiter=';')

        for row in reader:
            # In earlier versions, each row contains up to 10 elements:
            # Printer name, Location, Display name, Address, Driver, Description, Options, Version,
            # Requires, Icon.
            # To preserve backward compatibility, define all possible elements with default values and check for
            # required values
            
            print(row)
            printer_variables = translate_row(row)
            if 'catalogs' not in row.keys():
                row['Catalogs'] = pref('default_catalog', default='testing')

            new_printer = pgen.generate_printer(printer_variables)

            subdir = printer_variables.get('subdirectory', '')
            file_path = os.path.join(target_dir, subdir)
            file_name = new_printer['name'] + '-' + new_printer['version'] + '.' + file_ext
            file_path = os.path.join(file_path, file_name)
            write_pkginfo(file_path, new_printer)

def single_run(args, target_dir, file_ext):
    #FIXME whole function
    parameters = dict()
    parameters['printername'] = args.printername
    parameters['description'] = args.desc if args.desc else ''
    parameters['displayname'] = args.displayname if args.displayname else args.printername
    parameters['location'] = args.location if args.location else args.printername
    parameters['version'] = str(args.version) if args.version else '1.0'
    parameters['requires'] = args.requires if args.requires else ''
    parameters['icon'] = args.icon if args.icon else ''
    if args.options:
        options_string = args.options
    else:
        parameters['options'] = ''
    parameters['driver'] = args.driver if args.driver.startswith('/Library') else os.path.join('/Library/Printers/PPDs/Contents/Resources', args.driver)
    parameters['address'] = args.address if'://' in args.address else ('lpd://' + args.address)

    new_printer = pgen.generate_printer(parameters)

    subdir = args.get('Subdirectory', '')
    file_path = os.path.join(target_dir, subdir)
    file_name = new_printer['name'] + '-' + new_printer['version'] + file_ext
    file_path = os.path.join(file_path, file_name)
    write_pkginfo(file_path, new_printer)

def main():
    args = parse_arguments()

    target_dir = os.getcwd() # get working directory
    if args.repo:
        tmp_dir = os.path.join(args.repo, 'pkgsinfo')
        if os.path.isdir(tmp_dir):
            target_dir = args.repo        

    if args.pkginfoext:
        file_ext = args.pkginfoext
    else:
        file_ext = 'pkginfo'

    if args.csv:
        csv_run(args, target_dir, file_ext)
    else:
        single_run(args, target_dir, file_ext)

if __name__ == '__main__':
    main()
    exit(0)
