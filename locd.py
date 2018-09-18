import sys
import os
import time
import argparse
import logging
import threading
import signal

import daemon
from daemon import pidfile
from lockfile import AlreadyLocked

import location
import ipc


CUR_LOC_FILE = '/usr/local/www/res/cur.txt'
#PID_FILE = '/var/run/locd/locd.pid'
#LOG_FILE = '/var/log/locd/locd.log'
PID_FILE = 'pid'
LOG_FILE = 'log'
#SOCK_FILE = '/var/run/locd/locd.sock'
SOCK_FILE = './locd.sock'
REFRESH_CUR_TIME = 0.5


logger = logging.getLogger('locd')
logger.setLevel(logging.DEBUG)


class FileSaver(threading.Thread):
    def __init__(self, curf, tracker):
        threading.Thread.__init__(self, daemon=True)
        self.stopped = True
        self.tracker = tracker
        self.curf = curf

    def run(self):
        logger.info('Starting cur file save...')
        self.stopped = False
        while self.tracker.get_track() and not self.stopped:
            self.save_once()
            time.sleep(REFRESH_CUR_TIME)
        self.stopped = True
        logger.info('Stopped cur file save')

    def stop(self):
        self.save_once()
        self.stopped = True

    def save_once(self):
        # TODO: WITH THREAD LOCK
        lat, lon = self.tracker.accurate_loc().pos

        with open(self.curf, 'w') as f:
            f.write(f'{lat},{lon}')


class Locd():
    def __init__(self, curf=CUR_LOC_FILE, pidf=PID_FILE, sockf=SOCK_FILE, logf=LOG_FILE):
        self.curf = curf
        self.pidlockf = pidfile.TimeoutPIDLockFile(pidf)
        self.sockf = sockf
        self.logf = logf
        self.log_fh = logging.FileHandler(logf)
        Locd._logger_init(self.log_fh)

        self.tracker = None
        self.server = None
        self.curf_thrd = None
        self.context = None

    @staticmethod
    def _logger_init(fh):
        # fh = logging.FileHandler(logf)
        fh.setLevel(logging.DEBUG)

        formatstr = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        formatter = logging.Formatter(formatstr)

        fh.setFormatter(formatter)

        logger.addHandler(fh)

    def start(self):
        logger.info(f'Location daemon starting...')

        with open(self.curf, 'r') as f:
            # TODO: add try/except
            lat, lon = [float(coord) for coord in f.readline().split(',')]
            logger.info(f'Read from {self.curf}: Lat: {lat}, Lon: {lon}')
        self.tracker = location.Tracker(lat, lon)

        self.context = daemon.DaemonContext(
            working_directory='./',
            umask=0o002,
            pidfile=self.pidlockf,
            stdout=sys.stdout,
            stderr=sys.stderr,
            #files_preserve=[self.log_fh]
            )
        with self.context:
            self.run()

    def run(self):
        self.server = ipc.Server(self.sockf, self._req_handler)
        self.curf_thrd = FileSaver(self.curf, self.tracker)
        # TODO: Own logger for daemon
        #print(vars(logger))
        fh = logging.FileHandler(self.logf)
        #fh.setLevel(logging.DEBUG)
        logger.info(f'Location daemon STARTED!')

        with self.server:
            self.server.serve_forever()

    def request(self, args):
        logger.debug(f'Request to daemon: {args}')
        if self.is_running():
            with ipc.Client(self.sockf) as client:
                # response = client.send(args)
                try:
                    response = client.send(args)
                except ipc.ConnectionClosed:
                    if args['cmd'] != 'stop':
                        raise
                    else:
                        logger.info('Daemon succefuly stopped')
                        return "STOPPED"

                logger.debug(f'Response from daemon: {response}')
                return response
        else:
            logger.info(f'Request to not runned daemon: {args}')
            return "STOPPED"

    def is_running(self):
        try:
            self.pidlockf.acquire()
            # daemon stopped
            self.pidlockf.release()
            return False
        except AlreadyLocked:
            try:
                os.kill(self.pidlockf.read_pid(), 0)
                # daemon running
                return True
            except OSError:  # No process with locked PID
                # daemon been killed (stopped)
                self.pidlockf.break_lock()
                return False

    def kill(self):
        if self.is_running():
            self.curf_thrd.stop()
            # self.server.shutdown()
            os.kill(self.pidlockf.read_pid(), signal.SIGTERM)
            # self.context.close()
            logger.info(f'Location daemon STOPPED!')

    def _req_handler(self, req):
        logger.info(f'Got request by location daemon')
        # TODO: WITH THREAD LOCK
        if req['cmd'] == 'move':
            self.tracker.move_to(req['lat'], req['lon'])
            # self.curf_thrd.start()
            return self.tracker.get_status()
        elif req['cmd'] == 'speed':
            self.tracker.speed = req['spd']
            return self.tracker.get_status()
        elif req['cmd'] == 'status':
            self.tracker.accurate_loc()
            return self.tracker.get_status()
        elif req['cmd'] == 'cur':
            return self.tracker.accurate_loc().pos
        elif req['cmd'] == 'track':
            self.tracker.accurate_loc()
            return self.tracker.get_track()
        elif req['cmd'] == 'stop':
            self.tracker.accurate_loc()
            self.kill()
        elif req['cmd'] == 'start':
            self.tracker.accurate_loc()
            return self.tracker.get_status()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Location daemon starter/wrapper")
    parser.add_argument('-p', '--pid-file', default=PID_FILE, help='(Default: %(default)s)')
    parser.add_argument('-l', '--log-file', default=LOG_FILE, help='(Default: %(default)s)')
    parser.add_argument('-s', '--sock-file', default=SOCK_FILE, help='(Default: %(default)s)')
    parser.add_argument('-c', '--cur-file', default=CUR_LOC_FILE, help='(Default: %(default)s)')

    subparsers = parser.add_subparsers(dest='cmd', help='sub-command help')

    subparsers.add_parser('status', help='Get daemon status')

    subparsers.add_parser('cur', help='Get current location')

    subparsers.add_parser('start', help='Start daemon and stay it alive')

    parser_move = subparsers.add_parser('move', help='Move to point with given latitude and longitude'
                                                     '(Daemon will automaticaly start)')
    parser_move.add_argument('lat', type=float, help='Latitude of point')
    parser_move.add_argument('lon', type=float, help='Longitude of point')

    subparsers.add_parser('stop', help='Stop movement and daemon')

    subparsers.add_parser('track', help='Get current waypoints track')

    parser_speed = subparsers.add_parser('speed', help='Setup current movement speed')
    parser_speed.add_argument('spd', type=float, help='Speed in km/h')

    args = vars(parser.parse_args())

    cur_file = args.pop('cur_file')
    pid_file = args.pop('pid_file')
    sock_file = args.pop('sock_file')
    log_file = args.pop('log_file')

    loc_daemon = Locd(curf=cur_file, pidf=pid_file, sockf=sock_file, logf=log_file)

    if args['cmd'] in ['start', 'move'] and not loc_daemon.is_running():
        loc_daemon.start()

    if loc_daemon.is_running():
        result = loc_daemon.request(args)
        print(f'ONLINE: {result}')
    else:
        if args['cmd'] == 'cur':
            with open(cur_file, 'r') as f:
                # TODO: add try/except
                lat, lon = [float(coord) for coord in f.readline().split(',')]
                logger.info(f"Read from {cur_file}: Lat: {lat}, Lon: {lon}")
                print(f'OFFLINE: [{lat}, {lon}]')
        else:
            print(f'OFFLINE: []')

