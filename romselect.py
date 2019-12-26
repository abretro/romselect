#!/usr/bin/env python



"""
TODO:

- loop in the menu so multiple roms can be picked

- multiple roms at once (1,2,3)

- drive new system aliasing, like pcengine = turbografx16, etc.
  (rom aliasing is implemented, but probably not completely defined)

- ansi menus

- only run if there is more than N roms in archive mode (for processing existing
directories)

- fix pathing so that it can handle various references (./rom.zip, etc.)
  (workaround is to use full paths)


"""

"""
# Why I didnt use python-libarchive:
#
# it depends on libarchive:
# apt-get install build-essential libtool python-dev automake
# cd ~/Downloads
# wget https://libarchive.org/downloads/libarchive-3.3.3.tar.gz
# cd /usr/src
# tar xzvpf ~/Downloads/libarchive-3.3.3.tar.gz
# cd libarchive-3.3.3
# build/autogen.sh
# ./configure --prefix=/usr/local
# make
# make install
#
# echo /usr/local/lib > /etc/ld.so.conf.d/libarchive3.conf
# ldconfig -v
#
# And then actually getting python-libarchive...
#
# cd ~/Downloads
# wget https://storage.googleapis.com/google-code-archive-downloads/\
# v2/code.google.com/python-libarchive/python-libarchive-3.1.2-1.tar.gz
#
# cd /usr/src
# tar xzpvf ~/Downloads/python-libarchive-3.1.2-1.tar.gz
# cd python-libarchive-3.1.2-1
# python setup.py
#
# where the versions in raspbian stock are so old
# that the documentation doesnt reflect them in
# any usable manner.
#
#
# oh queso, maybe not libarchive.
#
"""
import os
import re
import shutil
import subprocess
import sys
import time

from datetime import datetime

WORK_DIR = '/home/pi/work'

ROMS_DIR = '/home/pi/RetroPie/roms'

#'file extension': 'RetroPie/roms/directory'

"""
~/RetroPie/roms:
amstradcpc  atarilynx  gbc            n64       ports    ti99
arcade      fba        genesis        neogeo    psx      vectrex
atari2600   fds        mame-libretro  nes       sega32x  zxspectrum
atari5200   gamegear   mame-mame4all  ngp       segacd
atari7800   gb         mastersystem   ngpc      sg-1000
atari800    gba        megadrive      pcengine  snes
"""

EXTENSIONS = { 

# needs to handle the 5 supergrafx roms special since they're .pce too
# neogeo are .bin, ugh.

# regular set
'a26': 'atari2600',
'a78': 'atari7800',
'lnx': 'atarilynx',
'gen': 'genesis',
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

# not verified (directory):
'jag': 'atarijaguar'

}


def file_exists(filename):
    """
    Returns True or False if the file (directory, block, device, whatever)
    exists
    """
    return os.path.exists(filename)


def runsh(sh, bufsize=0, shell=True, stdout=None, stderr=None, stdin=None,
          raise_err=False, duration=None):
    """
    This is minirunsh, it runs a shell with the commands given

    sh: a string to execute with a shell
        example: 'ls -al /tmp'

    bufsize: buffer the output
             0 = unbuffered (default)
             -N = system buffering  (-1, etc.)
             N = lines to buffer (4096, etc.)

    shell: use a login shell to run the commands
           True = heavier, can use builtins (ls, etc.),
                  potentially insecure if you use this with a function
                  that takes in user input!!!!

           False = lighter weight, no builtins, you will probably rarely use
                   this mode even though its "more secure"

    stdout = where to send stdout, in our case we're going to set it to the
             pipe from subprocess (as opposed to say, another file handle)

    stderr = where to send stderr - see stdout

    raise_err = raise an error if the returncode is greater than 0 and
                raise_err is True

    returns a tuple of the subprocesses returncode, stdout and stderr
    """

    stdout = stdout or subprocess.PIPE
    stderr = stderr or subprocess.PIPE
    stdin = stdin or subprocess.PIPE
    p = subprocess.Popen(args=sh, bufsize=bufsize, shell=shell,
                         stdout=stdout, stderr=stderr, stdin=stdin)

    if duration:
        elapsed_time = -1
        start_time = time.time()
        while (time.time() - start_time) < duration:
            rc = p.poll()
            if rc is not None:
                elapsed_time = time.time() - start_time
                break
            time.sleep(.1)

        if elapsed_time == -1:
            elapsed_time = duration
            p.kill()
    else:
        start_time = time.time()

    # collect the return values so is "stdout", se is "stderr",
    # but use non-clobbering variable names (threading future, etc.):
    so, se = p.communicate()

    if not duration:
        elapsed_time = time.time() - start_time

    # rc is "returncode"
    rc = p.returncode

    # raise an error:
    if rc and raise_err:

        raise ValueError('Returncode[%s] from command: %s' % (rc, sh))

    return (so, se, rc, elapsed_time)


def ls_7z(filename):
    """
    use the technical list mode to get the data
    we need
    """
    if not file_exists(filename):
        print 'File does not exist: %s' % filename
        return

    sh = '7z l -slt "%s"' % filename
    so, se, rc, timed = runsh(sh)

    if rc == 127:
        print 'Cant find 7z command in path, is it installed?'
        sys.exit(1)

    file_sizes = {}

    if rc == 0:
        candidate = ''
        for line in so.splitlines():
            if 'Path = ' in line:
                result = re.search('^Path = (.+)$', line)
                if result:
                    candidate = result.group(1)
            if candidate:
                result = re.search('^Size = (.+)$', line)
                if result:
                    file_sizes[candidate] = result.group(1)
                    candidate = ''
    return file_sizes


def extract_7z(filename, target_dir, target=None, overwrite=True):
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
            print "WARNING!"
            print "Moved existing: %s" % target_name
            print "to backup file: %s" % backup_name
            print ""
        else:
            print "Cannot overwrite file %s" % target_name
            print "exiting"
            sys.exit(1)

    sh = '7z x "%s" -o"%s" "%s"' % (filename, target_dir, target)
    so, se, rc, timed = runsh(sh)

    if rc == 127:
        print 'Cant find 7z command in path, is it installed?'
        sys.exit(1)

    return so, se, rc, timed


def compress_7z(filename, source):
    """
    sources = a tuple of files to add to the archive filename

    """
    if file_exists(filename):
        now = datetime.now()
        time_str = now.strftime("_%Y_%m_%d_%H%M%S")

        backup_name = filename + '.' + time_str
        #
        shutil.move(filename, backup_name)
        print "WARNING!"
        print "Moved existing: %s" % filename
        print "to backup file: %s" % backup_name
        print ""

    sh = '7z a "%s" "%s"' % (filename, source)
    so, se, rc, timed = runsh(sh)

    if rc == 127:
        print 'Cant find 7z command in path, is it installed?'
        sys.exit(1)

    return so, se, rc, timed


def which_bin(program):
    """
    returns the stdout from "which <program>"
    """
    so, se, rc, timed = runsh('which %s' % program)
    if not rc:
        retval = so
    else:
        retval = ''
    return retval


def draw_menu(archive_menu, regular_menu, rom_key, rom_country):

    print ""

    good_roms = {}
    for k, v in archive_menu.iteritems():
        print '%6d: %s' % (k, v)
        if rom_key in v:
            good_roms[k] = v
    
    # needs better first_match logic - Donkey Kong Country.7z shows this,
    # where it has multiple versions but it selects the middle version instead
    # of the later one.  I would like to default to the later one to pickup any
    # lockup bug fixes the developers saw fit, which is commonly why those
    # are released.  This might suck for games like punch out on the nes.
    first_match = ''
    if good_roms:
        print '---'
        for k,v in good_roms.iteritems():
            if '(%s)' % rom_country in v:
                if not first_match:
                    first_match = (k,v)
            
            print '%6d: %s' % (k, v)


    for k, v in regular_menu.iteritems():
        print '%6s: %s' % (k, v)
    
    return first_match


def main():
    """
    open a specified archive, displaying a menu of its contents.
    offer to write out the contents discretely as new archives and do so.
    """

    if not which_bin('7z'):
        print 'cannot find 7z in path, exiting'
        sys.exit(1)
    
    


    archive_file = sys.argv[1]
    rom_key = '[!]'
    rom_country = 'U'
    archive_list = ls_7z(archive_file)
    
    selection_menu = True
    if len(archive_list) <= 1:
        print 'Single file in archive, not displaying menu.'
        print archive_list
        # some day this might copy it anyways
        
        # exit 0 for now so && chaining of the command can take place
        #sys.exit(0)
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
        regular_menu['Q'] = 'Quit the program, back to shell'
        
        first_match = draw_menu(archive_menu, regular_menu, rom_key, rom_country)
        

        
        user_choice = False
        while not user_choice:
            # user input - which roms to handle?
            if first_match:
                 print ''
                 print '(D)efault: %s' % first_match[1]
            print ''
            print 'Which Rom to handle?'
            user_input = raw_input('')
            # scrub user input better
            if re.search('^\d+$', user_input):
                if int(user_input) >= 1 and int(user_input) <= len(archive_menu):
                    user_choice = user_input

            if user_input == 'q' or user_input == 'Q':
                sys.exit(0)
            
            if first_match:
                if user_input == 'd' or user_input == 'D':
                    user_choice = first_match[0]
            
            if not user_choice:
                print 'Selection not possible'
                print ''
     

    picked_file = archive_menu[int(user_choice)]
    #print picked_file
    # use filename format?

    so, se, rc, timed = extract_7z(archive_file, WORK_DIR, picked_file)

    if rc:
        print "ERROR! Could not extract file in work directory"
        print so
        print se
        sys.exit(1)
    else:
        print "Extracted rom %s to %s" % (picked_file, WORK_DIR)


    rom_extension = picked_file.split('.')[-1]
    rom_filename = '.'.join(picked_file.split('.')[:-1])

    new_filename = WORK_DIR + '/' + rom_filename + '.7z'
    source_filename = WORK_DIR + '/' + picked_file
    so, se, rc, timed = compress_7z(new_filename, source_filename)

    if rc:
        print "ERROR! Could not save file in work directory"
        print so
        print se
        sys.exit(1)
    else:
        print "Compressed rom %s to %s" % (picked_file, new_filename)

    if rom_extension in EXTENSIONS:
        sys_dir = ROMS_DIR + '/' + EXTENSIONS[rom_extension]
    else:
        print 'Unknown rom type, not copying rom to target directory'
        sys.exit(1)

    print 'Sys_dir %s' % sys_dir
    if not file_exists(sys_dir):
        print "Unable to copy file, directory does not exist: %s" % sys_dir
        sys.exit(1)

    rom_target = sys_dir + '/' + rom_filename + '.7z'
    if not file_exists(rom_target):
        try:
            shutil.copy(source_filename, rom_target)
            print "Copied new archive to %s" % rom_target
        except IOError as io_error:
            print "Unable to copy file. %s" % io_error
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
