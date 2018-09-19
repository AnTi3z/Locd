import os
import time
import argparse
import logging
import threading
import signal
import json

import daemon
from daemon import pidfile
from lockfile import AlreadyLocked

import location
import ipc

from config import *


logger = logging.getLogger('locd')
logger.setLevel(logging.DEBUG)


class FileSaver(threading.Thread):
    def __init__(self, curf, tracker):  # , lock):
        threading.Thread.__init__(self, daemon=True)
        self.stopped = True
        self.tracker = tracker
        self.curf = curf
        # self.lock = lock

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
        # with self.lock:
        lat, lon = self.tracker.accurate_loc().pos

        with open(self.curf, 'w') as f:
            f.write(f'{lat},{lon}')


class Locd():
    def __init__(self, curf=None, pidf=None, sockf=None, logf=None):
        self.curf = curf
        self.pidlockf = pidfile.TimeoutPIDLockFile(pidf) if pidf else None
        self.sockf = sockf
        self._log_fh = logging.FileHandler(logf) if logf else None

        if self._log_fh:
            Locd._logger_init(self._log_fh)

        self.tracker = None
        self.server = None
        # self.lock = None
        self.curf_thrd = None
        self.context = None

    @staticmethod
    def _logger_init(fh):
        fh.setLevel(logging.DEBUG)

        formatstr = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        formatter = logging.Formatter(formatstr)

        fh.setFormatter(formatter)

        logger.addHandler(fh)

    def start(self):
        # TODO: check curf, pidf, logf, sockf
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
            stdout=self._log_fh.stream,
            stderr=self._log_fh.stream,
            # files_preserve=[self._log_fh.stream]
            )
        with self.context:
            self.run()

    def run(self):
        logger.info(f'Location daemon STARTED!')

        self.server = ipc.Server(self.sockf, self._req_handler)
        # self.lock = threading.RLock()
        self.curf_thrd = FileSaver(self.curf, self.tracker)  # , self.lock)

        with self.server:
            self.server.serve_forever()

    def request(self, args):
        # TODO: check sockf
        logger.debug(f'Request to daemon: {args}')
        if self.is_running():
            with ipc.Client(self.sockf) as client:
                try:
                    response = client.send(args)
                except ipc.ConnectionClosed:
                    if args['cmd'] != 'stop':
                        raise
                    else:
                        logger.info('Daemon successfully stopped')
                        return {}

                logger.debug(f'Response from daemon: {response}')
                return response
        else:
            logger.info(f'Request to not runned daemon: {args}')
            # TODO: raise exception
            return {}

    def is_running(self):
        if not self.pidlockf: return False
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
            os.kill(self.pidlockf.read_pid(), signal.SIGTERM)
            logger.info(f'Location daemon STOPPED!')

    def _req_handler(self, req):
        logger.info(f'Got request by location daemon')
        # with self.lock:
        if req['cmd'] == 'move':
            self.tracker.move_to(req['lat'], req['lon'])
            self.curf_thrd.start()
            return self.tracker.get_status()
        elif req['cmd'] == 'speed':
            self.tracker.speed = req['spd']
            self.tracker.accurate_loc()
            return self.tracker.get_status()
        elif req['cmd'] == 'status':
            self.tracker.accurate_loc()
            return self.tracker.get_status()
        elif req['cmd'] == 'cur':
            return {'cur_loc': self.tracker.accurate_loc().pos}
        elif req['cmd'] == 'track':
            self.tracker.accurate_loc()
            return {'track': self.tracker.get_track()}
        elif req['cmd'] == 'stop':
            self.kill()
        elif req['cmd'] == 'start':
            self.tracker.accurate_loc()
            return self.tracker.get_status()


def main(**kwargs):
    cur_file = kwargs.pop('cur_file') if 'cur_file' in kwargs else CUR_LOC_FILE
    pid_file = kwargs.pop('pid_file') if 'pid_file' in kwargs else PID_FILE
    sock_file = kwargs.pop('sock_file') if 'sock_file' in kwargs else SOCK_FILE
    log_file = kwargs.pop('log_file') if 'log_file' in kwargs else LOG_FILE

    loc_daemon = Locd(curf=cur_file, pidf=pid_file, sockf=sock_file, logf=log_file)

    if kwargs['cmd'] in ['start', 'move'] and not loc_daemon.is_running():
        loc_daemon.start()

    result = {'online': loc_daemon.is_running(),
              'req_cmd': kwargs['cmd']}

    if result['online']:
        response = loc_daemon.request(kwargs)
        result['status'] = response
    else:
        if kwargs['cmd'] == 'cur':
            with open(cur_file, 'r') as f:
                # TODO: add try/except
                lat, lon = [float(coord) for coord in f.readline().split(',')]
                logger.info(f"Read from {cur_file}: Lat: {lat}, Lon: {lon}")
                result['status'] = {'cur_loc': [lat, lon]}
        else:
            result['status'] = {}

    return result


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
    # parser_move.add_argument('-k', help='Kill the deamon if movement had finished')

    subparsers.add_parser('stop', help='Stop movement and daemon')

    subparsers.add_parser('track', help='Get current waypoints track')

    parser_speed = subparsers.add_parser('speed', help='Setup current movement speed')
    parser_speed.add_argument('spd', type=float, help='Speed in km/h')

    kwargs = vars(parser.parse_args())

    result = main(**kwargs)

    print(json.dumps(result))
