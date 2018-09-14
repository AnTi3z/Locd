import sys
import os
import time
import argparse
import logging
import mmap
import threading

import daemon
from daemon import pidfile
from lockfile import AlreadyLocked

import location

logger = logging.getLogger('loc_daemon')
logger.setLevel(logging.DEBUG)

curf = '/usr/local/www/res/cur.txt'
CUR_LOC_FILE = '/usr/local/www/res/cur.txt'
#PID_FILE = '/var/run/locd/locd.pid'
#LOG_FILE = '/var/log/locd/locd.log'
PID_FILE = 'pid'
LOG_FILE = 'log'
SOCK_FILE = '/var/run/locd/locd.sock'
MMAP_FILE = '/var/run/locd/locd.mmap'
REFRESH_CUR_TIME = 0.2


class FileDumper(threading.Thread):
    def __init__(self, fo, tracker):
        threading.Thread.__init__(self)
        self.daemon = True
        self.tracker = tracker
        self.curf = fo

    def run(self):
        while self.tracker.get_track():
            self.save_once()
            time.sleep(REFRESH_CUR_TIME)

    def save_once(self):
        lat, lon = self.tracker.accurate_loc().pos
        with open(self.curf, 'w') as f:
            f.write(f'{lat},{lon}')


class Locd():
    def __init__(self, args):
        self.curf = args['cur_file']
        self.pidf = pidfile.TimeoutPIDLockFile(args['pid_file'])
        with open(curf, 'r') as f:
            # TODO: add try/except
            lat, lon = [float(coord) for coord in f.readline().split(',')]
            # logger.info(f'Read from {curf}: Lat: {lat}, Lon: {lon}')
        self.tracker = location.Tracker(lat, lon)
        self.curf_thr = FileDumper(curf, self.tracker)
        self.context = None

    def run(self):
        with self.context:
            pass

    def is_running(self):
        try:
            self.pidf.acquire()
            # daemon stopped
            return False
        except AlreadyLocked:
            try:
                os.kill(self.pidf.read_pid(), 0)
                # daemon running
                return True
            except OSError:  # No process with locked PID
                # daemon been killed (stopped)
                self.pidf.break_lock()
                return False

    def stop(self):
        if self.is_running():
            # TODO: save state
            self.tracker.set_speed(0)
            self.curf_thr.cancel()
            self.curf_thr.save_once()
            os.kill(self.pidf.read_pid(), 15)

    def parse_args(self, args):
        pass

    def _req_handler(self):
        pass


def daemon_start(args):
    logf = args.log_file
    ### This does the "work" of the daemon

    fh = logging.FileHandler(logf)
    fh.setLevel(logging.DEBUG)

    formatstr = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(formatstr)

    fh.setFormatter(formatter)

    logger.addHandler(fh)
    logger.info('STARTED')

    with open(curf,'r') as f:
        # TODO: add try/except
        lat, lon = [float(coord) for coord in f.readline().split(',')]
        logger.info(f'Read from {curf}: Lat: {lat}, Lon: {lon}')

    # TODO: Create Unix socket for IPC

    trck = location.Tracker(lat, lon)
    if args['cmd'] == 'move':
        trck.move_to(float(args['lat']), float(args['lat']))

    curf_thread = FileDumper(curf, trck)

    if args['force-file']:
        curf_thread.run()

    while args['i'] or args['cmd']=='start':
        time.sleep(1)
        # TODO: sock server listen



def stopped_daemon(args, pidf):
    if args['cmd'] == 'status':
        print("{'running': false}")
    elif args['cmd'] == 'cur':
        with open(args['cur_file'],'r') as f:
            print(f.readline())
            #lat, lon = [float(coord) for coord in f.readline().split(',')]
    elif args['cmd'] == 'track':
        print('[]')
    elif args['cmd'] in ['move','start']:
        context = daemon.DaemonContext(
            working_directory='./',
            umask=0o002,
            pidfile=pidf)
        with context:
            daemon_start(args)


def running_daemon(args, pidf):
    #TODO: IPC connect here
    if args['cmd'] == 'status':
        print('running')
    elif args['cmd'] == 'move':
        os.kill(pidf.read_pid(), 15)  # SIGTERM
        # stop daemon and restart
        stopped_daemon(args, pidf)
    else:
        print('not impleneted yet')


def main(args):
    pidlockf = pidfile.TimeoutPIDLockFile(args['pid_file'])

    try:
        pidlockf.acquire()
        # daemon stopped
        stopped_daemon(args, pidf=pidlockf)
    except AlreadyLocked:
        try:
            os.kill(pidlockf.read_pid(), 0)
            # daemon running
            running_daemon(args, pidf=pidlockf)
        except OSError:  # No process with locked PID
            # daemon been killed (stopped)
            pidlockf.break_lock()
            stopped_daemon(args, pidf=pidlockf)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Location daemon starter/wrapper")
    parser.add_argument('-p', '--pid-file', default=PID_FILE, help='(Default: %(default)s)')
    parser.add_argument('-l', '--log-file', default=LOG_FILE, help='(Default: %(default)s)')
    parser.add_argument('-s', '--sock-file', default=SOCK_FILE, help='(Default: %(default)s)')
    # parser.add_argument('-m', '--mmap-file', default=MMAP_FILE, help='(Default: %(default)s)')
    parser.add_argument('-c', '--cur-file', default=CUR_LOC_FILE, help='(Default: %(default)s)')

    subparsers = parser.add_subparsers(dest='cmd', help='sub-command help')

    parser_status = subparsers.add_parser('status', help='Get daemon status')
    # parser_status.add_argument('-j', '--json', help='')

    parser_cur = subparsers.add_parser('cur', help='Get current location')
    # parser_cur.add_argument('--force-file', help='')

    parser_start = subparsers.add_parser('start', help='Start daemon and stay it alive')
    # parser_start.add_argument('--force-file', help='')

    parser_move = subparsers.add_parser('move', help='Move to point with given latitude and longitude'
                                                     '(daemon will automaticaly start if it not)')
    parser_move.add_argument('lat', type=float, help='Latitude of point')
    parser_move.add_argument('lon', type=float, help='Longitude of point')
    # parser_move.add_argument('-a', help='Keep daemon alive')
    # parser_move.add_argument('--force-file', help='')

    subparsers.add_parser('stop', help='Stop movement and daemon(if it was started with "move" cmd and'
                                       ' -a key is ommited)')

    parser_track = subparsers.add_parser('track', help='Get current waypoint track')
    #parser_track.add_argument('-j', '--json', help='')

    parser_speed = subparsers.add_parser('speed', help='Setup current movement speed')
    parser_speed.add_argument('spd', type=float, help='Speed in km/h')

    args = parser.parse_args()
    #main(vars(args))
    main(args)
