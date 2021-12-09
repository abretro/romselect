#!/usr/bin/env python3

"""
romselect.py for retropie            
"""
import os
import re
import shutil
import subprocess
import sys
import time

from datetime import datetime
from pathlib import Path

# where compression/decompression files are staged:
WORK_DIR = '/tmp/work'

# where to copy the roms to (romselect knows over 15 rom types at the moment)
ROMS_DIR = '/home/pi/RetroPie/roms'

# what flags represent the "good" roms (set in the filename of the rom):
ROM_GOOD = '[!]'

# what country code is default? (set in the filename of the rom):
ROM_COUNTRY = 'U'



"""
# not all of these platforms are currently coded to work with romselect.
# (PR's will be looked at)
~/RetroPie/roms $ ls
amstradcpc  atarijaguar  gamegear   mame-advmame   nds     pcengine  snes
arcade      atarilynx    gb         mame-libretro  neogeo  ports     ti99
atari2600   atarist      gba        mame-mame4all  nes     psx       ti99sim
atari5200   dreamcast    gbc        mastersystem   ngp     sega32x   vectrex
atari7800   fba          genesis    megadrive      ngpc    segacd    x68000
atari800    fds          macintosh  n64            pc      sg-1000   zxspectrum


Specific platform notes:


neogeo and the cdrom platforms:
    All of these use .bin, so there is no default platform for .bin

"""

EXTENSIONS = { 
    # regular set
    'a26': 'atari2600',
    'a78': 'atari7800',
    'lnx': 'atarilynx',
    'gen': 'megadrive',
    'gg': 'gamegear',
    'pce': 'pcengine',
    'sfc': 'snes',
    'smc': 'snes',
    'sms': 'mastersystem',

    # same named, all nintendo, interesting:
    'nes': 'nes',
    'snes': 'snes',
    'n64': 'n64',
    'gb': 'gb',
    'gbc': 'gbc',
    'gba': 'gba',
    'fds': 'fds',
}


def file_exists(filename):
    """
    Returns True or False if the file (directory, block, device, whatever)
    exists
    """
    return os.path.exists(filename)


def runsh(sh):
    p = subprocess.Popen(args=sh, shell=True,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         stdin=subprocess.PIPE)
    so, se = p.communicate()
    rc = p.returncode
    return (so, se, rc)


def ls_7z(filename, binary):
    """
    use the technical list mode to get the data
    we need
    """
    sh = '%s l -slt "%s"' % (binary, filename)
    so, se, rc = runsh(sh)

    file_sizes = {}

    if rc == 0:
        candidate = ''
        for line in so.splitlines():
            if 'Path = '.encode(encoding='UTF-8') in line:
                result = re.search('^Path = (.+)$'.encode(encoding='UTF-8'), line)
                if result:
                    candidate = result.group(1)
            if candidate:
                result = re.search('^Size = (.+)$'.encode(encoding='UTF-8'), line)
                if result:
                    file_sizes[candidate] = result.group(1)
                    candidate = ''
    return file_sizes


def extract_7z(filename, target_dir, binary, target=None, overwrite=True):
    """
    if targets is None, it will extract all files

    target_dir = where to extract the files at

    otherwise, targets is a tuple of filenames to extract from the
    archive specified by filename
    """
    target_name = target_dir + '/' + target
    if file_exists(target_name):
        if overwrite:
            now = datetime.now()
            time_str = now.strftime("_%Y_%m_%d_%H%M%S")

            backup_name = target_name + '.' + time_str
            #
            shutil.move(target_name, backup_name)
            print()
            print("Existing File!")
            print("Existing rom in work directory: %s" % target_name)
            print("Moved to backup file: %s" % backup_name)
            print("")
        else:
            print("Cannot overwrite file %s" % target_name)
            print("exiting")
            sys.exit(1)

    sh = '%s x "%s" -o"%s" "%s"' % (binary, filename, target_dir, target)
    so, se, rc = runsh(sh)

    return so, se, rc


def compress_7z(filename, source, binary):
    """
    sources = a tuple of files to add to the archive filename

    theres a bug in here when using 7zr
    """
    if file_exists(filename):
        now = datetime.now()
        time_str = now.strftime("_%Y_%m_%d_%H%M%S")

        backup_name = filename + '.' + time_str

        shutil.move(filename, backup_name)
        print()
        print("Existing archive file!")
        print("Existing archive: %s" % filename)
        print("Moved to backup: %s" % backup_name)
        print("")

    sh = '%s a "%s" "%s"' % (binary, filename, source)
    print()
    print('Compression command used:')
    print(sh)
    print()
    so, se, rc = runsh(sh)
    return so, se, rc


def which_bin(program):
    """
    returns the stdout from "which <program>"
    """
    so, se, rc = runsh('which %s' % program)
    if not rc:
        retval = so
    else:
        retval = ''
    return retval


def draw_menu(archive_menu, regular_menu, rom_good, rom_country):

    print()
    print("Archive's roms:")
    good_roms = {}
    for k, v in archive_menu.items():
        print('%6d: %s' % (k, v.decode('utf-8')))
        if rom_good.encode(encoding='UTF-8') in v:
            good_roms[k] = v

    # needs better first_match logic - Donkey Kong Country.7z shows this,
    # where it has multiple versions but it selects the middle version instead
    # of the later one.  I would like to default to the later one to pickup any
    # lockup bug fixes the developers saw fit, which is commonly why those
    # are released.  This might suck for games like punch out on the nes.
    first_match = ''
    if good_roms:
        print()
        print('"Good" choices, %s:' % rom_good)
        for k,v in good_roms.items():
            if rom_country.encode(encoding='UTF-8') in v:
                if not first_match:
                    first_match = (k,v.decode('utf-8'))
            print('%6d: %s' % (k, v.decode('utf-8')))

    if first_match:
         print('')
         print('Good choice (%s) + country code (%s):' % (rom_good, rom_country))
         print('     A: %s' % first_match[1])

    print()
    print('Controls:')
    for k, v in regular_menu.items():
        print('%6s: %s' % (k, v))

    return first_match


def main():
    """
    open a specified archive, displaying a menu of its contents.
    offer to write out the contents discretely as new archives and do so.
    """
    binary = '7z'
    if not which_bin(binary):
        binary = '7zr'
        if not which_bin(binary):
            print('cannot find a 7zip handler in path, exiting')
            sys.exit(1)

    if len(sys.argv) < 2:
        raise RuntimeError('Need to specify a rom archive(tarball) to process')

    archive_file = sys.argv[1]
    if not file_exists(archive_file):
        raise RuntimeError('Archive file doesnt exist: %s' % archive_file)

    rom_good = ROM_GOOD
    rom_country = ROM_COUNTRY
    archive_list = ls_7z(archive_file, binary)

    selection_menu = True
    if len(archive_list) <= 1:
        print('Single file in archive, not displaying menu.')
        print(archive_list)
        selection_menu = False
        user_choice = 1
        archive_menu = {}
        for key in archive_list:
            archive_menu[1] = key

    if selection_menu:
        counter = 1
        archive_menu = {}
        for entry in archive_list:
            archive_menu[counter]=entry
            counter += 1

        regular_menu = {}
        regular_menu['R'] = 'Redraw the roms menu'
        regular_menu['Q'] = 'Quit the program, back to shell'

        first_match = draw_menu(archive_menu, regular_menu, rom_good, rom_country)

        user_choice = False
        while not user_choice:
            # user input - which roms to handle?
            print('')
            user_input = input('Menu choice: ')
            # scrub user input better
            if re.search('^\d+$', user_input):
                if int(user_input) >= 1 and int(user_input) <= len(archive_menu):
                    user_choice = user_input

            if user_input.upper() == 'Q':
                sys.exit(0)

            if user_input.upper() == 'R':
                first_match = draw_menu(archive_menu, regular_menu, rom_good, rom_country)
                print()

            if first_match:
                if user_input.upper() == 'A':
                    user_choice = first_match[0]

            if not user_choice:
                print('Please select an item before pressing enter')


    picked_file = archive_menu[int(user_choice)].decode('utf-8')

    so, se, rc = extract_7z(archive_file, WORK_DIR, binary, picked_file)

    if rc:
        print("ERROR! Could not extract file in work directory %s" % WORK_DIR)
        print(so)
        print(se)
        sys.exit(1)
    else:
        print("Extracted rom: %s" % picked_file)
        print("Work Directory: %s" % WORK_DIR)


    rom_extension = picked_file.split('.')[-1]
    rom_filename = '.'.join(picked_file.split('.')[:-1])

    new_filename = '%s/%s.7z' % (WORK_DIR, rom_filename)
    source_filename = '%s/%s' % (WORK_DIR, picked_file)
    so, se, rc = compress_7z(new_filename, source_filename, binary)

    if rc:
        print("ERROR! Could not save file in work directory")
        print(so)
        print(se)
        sys.exit(1)

    if rom_extension in EXTENSIONS:
        sys_dir = '%s/%s' % (ROMS_DIR, EXTENSIONS[rom_extension])
    else:
        print('Unknown rom type, not copying rom to target directory')
        sys.exit(1)

    if not file_exists(sys_dir):
        print("Unable to copy file, directory does not exist: %s" % sys_dir)
        sys.exit(1)


    print("Files/Directories:")
    print(" - Uncompressed rom: %s/%s" % (WORK_DIR, picked_file))
    print(" - Archive file: %s/%s.7z" % (sys_dir, rom_filename))

    rom_target = '%s/%s.7z' % (sys_dir, rom_filename)
    if not file_exists(rom_target):
        try:
            shutil.copy(new_filename, rom_target)
            print(" - Copied new archive to %s" % rom_target)
        except IOError as io_error:
            print("!!!!!!! Unable to copy new archive. Error: %s" % io_error)
            sys.exit(1)


if __name__ == '__main__':
    main()


#######
# specs
#
# FIRST TASKS:
# - opens 7z, zip, etc. with a list in a menu? check boxes?
#
# - pick from list which roms need new discrete archive
#
# - ability to assign new name to archive and rom in archive
#
# - extracts each file from source_dir 7z and puts
#   in a new 7z in the WORK_DIR
#
# - option to make other than 7z
# (code 7z as one of the options, make it default)
#
# LATER TASKS:
# - if the creation in the WORK_DIR is ok,
# (7z list it? other checks?), then mv it over to
# the ROMS_DIR
#


"""
TODO:
- make file tree menu at start instead of whine about missing file

- loop in the menu so multiple roms can be picked

- multiple roms at once (1,2,3)

- drive new system aliasing, like pcengine = turbografx16, etc.
  (rom aliasing is implemented, but probably not completely defined)

- ansi/curses menus

- fix pathing so that it can handle various references (./rom.zip, etc.)
  (workaround is to use full paths)


"""