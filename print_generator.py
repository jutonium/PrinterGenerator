#!/usr/bin/env python3

# since this is probably used on a system with munki the munki-included python should be used:
# #!/usr/local/munki/munki-python
# coding: utf8

'''
This module uses the printer p_gen.py module to generate a munki-nopkg-printer setup from variables
and writes it to disk.
'''
__author__ = 'jutonium (github)'
__version__ = '2.0 RC'


import argparse
import csv
import os
import sys
import errno
from xml.parsers.expat import ExpatError

from plistlib import load as load_plist
from plistlib import dump as dump_plist

import pgen

# Preference handling copied from Munki:
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
                pwd = os.path.dirname(os.path.realpath(__file__))
                file_handle = open(os.path.join(pwd, PREFSPATH), 'rb')
                pref.cache = load_plist(file_handle)
                file_handle.close()
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
    parser = argparse.ArgumentParser(description='Generate a Munki nopkg-style pkginfo for ' \
                                     'printer installation.')
    parser.add_argument('--printername', help='Name of printer queue. May not contain spaces, ' \
                        'tabs, # or /. Required.')
    parser.add_argument('--driver', help='Name of driver file in ' \
                        '/Library/Printers/PPDs/Contents/Resources/. Can be relative or full ' \
                        'path. Required.')
    parser.add_argument('--address', help='IP or DNS address of printer. If no protocol is ' \
                        'specified, defaults to lpd://. Required.')
    parser.add_argument('--location', help='Location name for printer. Optional. Defaults to ' \
                        'printername.')
    parser.add_argument('--displayname', help='Display name for printer (and Munki pkginfo). ' \
                        'Optional. Defaults to printername.')
    parser.add_argument('--desc', help='Description for Munki pkginfo only. Optional.')
    parser.add_argument('--requires', help='Required packages in form of space-delimited ' \
                        '\'CanonDriver1 CanonDriver2\'. Optional.')
    parser.add_argument('--options', nargs='*', dest='options', help='Printer options in form of ' \
                        'space-delimited \'Option1=Key Option2=Key Option3=Key\', etc. Optional.')
    parser.add_argument('--version', help='Version number of Munki pkginfo. Optional. Defaults ' \
                        'to 1.0.', default='1.0')
    parser.add_argument('--icon', help='Specifies an existing icon in the Munki repo to display ' \
                        'for the printer in Managed Software Center. Optional.')

    parser.add_argument('--catalogs', help='Specifies the catalog which shall be used. Defaults ' \
                        'to default_catalog if present or testing otherweise. Optional.')
    parser.add_argument('--munkiname', help='Name of Munki item. Defaults to printername. ' \
                        'Optional.')
    parser.add_argument('--repo', help='Path to Munki repo. If specified, we will try to write ' \
                        'directly to its containing pkgsinfo directory. If not defined, we will ' \
                        'write to current working directory. Optional.')
    parser.add_argument('--subdirectory', help='Subdirectory of Munki\'s pkgsinfo directory. ' \
                        'Optional.')
    parser.add_argument('--pkginfoext', help='File extension for the nopkg. Defaults to pkginfo. ' \
                        'Optional.', default='pkginfo')

    parser.add_argument('--csv', help='Path to CSV file containing printer info. If CSV is ' \
                        'provided, all other options are ignored.')
    args = parser.parse_args()

    if args.csv:
        return args
    # check for missing parameters and quit if not present
    if not args.printername:
        print(os.path.basename(sys.argv[0]) + ': error: argument --printername is required',
              file=sys.stderr)
        parser.print_usage()
        sys.exit(1)
    if not args.driver:
        print(os.path.basename(sys.argv[0]) + ': error: argument --driver is required',
              file=sys.stderr)
        parser.print_usage()
        sys.exit(1)
    if not args.address:
        print(os.path.basename(sys.argv[0]) + ': error: argument --address is required',
              file=sys.stderr)
        parser.print_usage()
        sys.exit(1)
    return args

def path_create_exists(mydir):
    '''Create all directories leading to the file stated.'''
    try:
        os.makedirs(mydir)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            print('Directory ' + mydir + ' could not be created!', file=sys.stderr)
            return False
    return True

def write_pkginfo(full_file_name, new_printer):
    '''
    Writes the given printer dictionary as a valid pkginfo to disk.
    '''
    target_dir = os.path.split(full_file_name)[0]
    target_exists = False
    target_exists = path_create_exists(target_dir)
    if target_exists:
        with open(full_file_name, 'wb') as file_handle:
            dump_plist(new_printer, file_handle)


def translate_row(printer_row):
    '''
    Adds case insensitive handling to the parsing of csv files and provides translation to the
    expected dictionary entries.
    '''
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
        'catalogs':     'catalogs',
        'subdirectory': 'subdirectory',
        'munkiname':    'munki name',
    }
    new_row = dict()
    for key, value in printer_row.items():
        new_row[key.lower()] = value

    printer_variables = pgen.get_printer_parameters()
    for key in translation:
        printer_variables[key] = new_row.get(translation[key], printer_variables[key])
    return printer_variables

def csv_run(args, target_dir, file_ext):
    '''
    Use a csv file as data provider for printer packages.
    '''
    # read utf-8 files with or without BOM.
    with open(args.csv, mode='r', encoding='utf-8-sig' ) as infile:
        file_sample = infile.read(128)
        file_sample = file_sample.split('\n')[0]
        print(file_sample)
        infile.seek(0) # back to the beginning
        num_comma = file_sample.count(',')
        num_semicolon = file_sample.count(';')
        if num_comma < 9 and num_semicolon < 9:
            print(os.path.basename(sys.argv[0]) + ': error: invalid csv file', file=sys.stderr)
            sys.exit(1)

        if num_comma > num_semicolon:
            reader = csv.DictReader(infile, delimiter=',')
        else:
            reader = csv.DictReader(infile, delimiter=';')

        for row in reader:
            # In earlier versions, each row contains up to 10 elements:
            # Printer name, Location, Display name, Address, Driver, Description, Options, Version,
            # Requires, Icon.
            # To preserve backward compatibility, define all possible elements with default values
            # and check for required values

            printer_variables = translate_row(row)
            if 'Catalogs' not in row.keys():
                printer_variables['catalogs'] = [pref('default_catalog', default='testing')]

            new_printer = pgen.generate_pkginfo(printer_variables)

            subdir = printer_variables.get('subdirectory', '')
            file_path = os.path.join(target_dir, subdir)
            file_name = new_printer['name'] + '-' + new_printer['version'] + '.' + file_ext
            file_path = os.path.join(file_path, file_name)
            write_pkginfo(file_path, new_printer)

def single_run(args, target_dir, file_ext):
    '''
    Use the given parameters to creare a single printer packages.
    '''
    printer_variables = pgen.get_printer_parameters()
    printer_variables['printername'] = args.printername if args.printername else \
        printer_variables['printername']
    printer_variables['description'] = args.desc if args.desc else printer_variables['description']
    printer_variables['display_name'] = args.displayname if args.displayname else \
        printer_variables['display_name']
    printer_variables['location'] = args.location if args.location else \
        printer_variables['location']
    printer_variables['version'] = str(args.version) if args.version else \
        printer_variables['version']
    printer_variables['requires'] = args.requires if args.requires else \
        printer_variables['requires']
    printer_variables['icon_name'] = args.icon if args.icon else printer_variables['icon_name']
    printer_variables['options'] = args.options if args.options else printer_variables['options']
    printer_variables['driver'] = args.driver if args.driver else printer_variables['driver']
    printer_variables['address'] = args.address if args.address else printer_variables['address']
    printer_variables['munkiname'] = args.munkiname if args.munkiname else \
        printer_variables['munkiname']
    printer_variables['catalogs'] = [args.catalogs] if args.catalogs else \
        pref('default_catalog', default='testing')

    new_printer = pgen.generate_pkginfo(printer_variables)

    subdir = printer_variables.get('subdirectory', '')
    file_path = os.path.join(target_dir, subdir)
    file_name = new_printer['name'] + '-' + new_printer['version'] + '.' + file_ext
    file_path = os.path.join(file_path, file_name)
    write_pkginfo(file_path, new_printer)

def main():
    '''
    Create (a) printer package(s) either from command line parameters or a given csv. If the csv
    option is used all other inputs except for the file extension are ignored.
    '''
    args = parse_arguments()

    target_dir = os.getcwd() # get working directory
    if args.repo:
        tmp_dir = os.path.join(args.repo, 'pkgsinfo')
        if os.path.isdir(tmp_dir):
            target_dir = args.repo

    file_ext = args.pkginfoext if args.pkginfoext else 'pkginfo'

    if args.csv:
        csv_run(args, target_dir, file_ext)
    else:
        single_run(args, target_dir, file_ext)

if __name__ == '__main__':
    main()
    sys.exit(0)
