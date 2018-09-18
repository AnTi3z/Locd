import time
import random

import pyproj
import openrouteservice
from openrouteservice import convert

from config import API_KEY


class Location:
    def __init__(self, lat=0.0, lon=0.0, proj_name='epsg:3857'):
        #  epsg:3857 Pseudo-mercator
        #  epsg:3395 Mercator projection
        self._lat = None
        self._lon = None
        self._proj = None
        self._geod = pyproj.Geod(ellps='WGS84')
        self.set_lat(lat)
        self.set_lon(lon)
        self.set_proj(proj_name)

    # Сравнение двух объектов экземпляра класса на соответстие координат друг другу
    def __eq__(self, other):
        return self._lat == other.lat and self._lon == other.lon

    # def __add__(self, other):
    #    return Location(self._lat+other._lat, self._lon+other._lon)

    # def __sub__(self, other):
    #    return Location(self._lat-other._lat, self._lon-other._lon)

    # Кооринаты точки на расстоянии dst и по направлению az
    def fwd(self, az, dst):
        lon, lat, _ = self._geod.fwd(self._lon, self._lat, az, dst)
        return Location(lat, lon)

    # Азимут и расстояние до точки с координатами lat, lon
    def inv(self, lat, lon):
        az, _, dst = self._geod.inv(self._lon, self._lat, lon, lat)
        return az, dst

    def set_proj(self, proj_name):
        self._proj = pyproj.Proj(init=proj_name)

    def get_lat(self):
        return self._lat

    def set_lat(self, new_lat):
        self._lat = min(89.5, max(new_lat, -89.5))

    def get_lon(self):
        return self._lon

    def set_lon(self, new_lon):
        self._lon = min(180.0, max(new_lon, -180.0))

    def get_pos(self):
        return self._lat, self._lon

    def set_pos(self, *new_pos):
        self.set_lat(new_pos[0])
        self.set_lon(new_pos[1])

    def get_x(self):
        return self.get_pos_xy()[0]

    def set_x(self, new_x):
        self._lon, _ = self._proj(new_x, self.get_y(), inverse=True)

    def get_y(self):
        return self.get_pos_xy()[1]

    def set_y(self, new_y):
        _, self._lat = self._proj(self.get_x(), new_y, inverse=True)

    def get_pos_xy(self):
        return self._proj(self._lon, self._lat)

    def set_pos_xy(self, *new_pos_xy):
        self._lon, self._lat = self._proj(new_pos_xy[0], new_pos_xy[1], inverse=True)

    # Получение/установка широты(lat) и долготы(lon) точки
    lat = property(get_lat, set_lat)
    lon = property(get_lon, set_lon)
    # Одновременная запись и получение широты и долготы (lat, lon)
    pos = property(get_pos, set_pos)
    # Получение/установка координат точки x и y (в метрах)
    x = property(get_x, set_x)
    y = property(get_y, set_y)
    # Одновременная запись и получение двух координат (x,y) (в метрах)
    pos_xy = property(get_pos_xy, set_pos_xy)


class Tracker:
    ors_client = openrouteservice.Client(key=API_KEY)

    def __init__(self, lat=0.0, lon=0.0):
        self._rnd_noise = 1  # +/-1m
        self._cur_loc = Location(lat, lon)
        self._sync_time = time.time()
        self._speed = 0
        self._target_loc = self._cur_loc
        self._track = None  # [[lat1, lon1], [lat2, lon2], ... etc
        self._odo = 0

    def get_status(self):
        self._calc_loc()
        if self._track:
            az, _ = self._cur_loc.inv(*self._track[0])
        else:
            az = None
        return {'cur_loc': self._cur_loc.pos,
                'target_loc': self._target_loc.pos,
                'track': self._track,
                'speed': self._speed,
                'azimuth': az,
                'odo': self._odo}

    def get_track(self):
        return self._track

    def get_speed(self):
        return self._speed

    # Установить скорость движения до заданной точки
    def set_speed(self, speed):
        if speed >= 0:
            # Фиксируем нашу текущую позицию
            self._calc_loc()
            if self._cur_loc != self._target_loc:
                self._speed = speed

    def set_pos(self, new_lat, new_lon):
        self._speed = 0
        self._cur_loc = Location(new_lat, new_lon)
        self._sync_time = time.time()

    # Получить точные координаты текущей точки (Location)
    def accurate_loc(self):
        self._calc_loc()
        return self._cur_loc

    # Получить координаты текущей точки со случайным небольшим смещением (Location)
    def noised_loc(self):
        self._calc_loc()
        fake_loc = Location(*self._cur_loc.pos)
        fake_loc.x = random.gauss(fake_loc.x, self._rnd_noise / 2)
        fake_loc.y = random.gauss(fake_loc.y, self._rnd_noise / 2)
        return fake_loc

    # Координаты последней полученной точки (Location)
    def last_loc(self):
        return self._cur_loc

    # Время (в сек) с момента последнего расчета координат
    def elapsed_time(self):
        return time.time() - self._sync_time

    # Построить трек от cur_pos до target_pos
    def _build_route(self, prof='foot-walking'):
        self._odo = 0
        self._track = []
        # TODO: Add transport type selecting "driving-car" "cycling-regular" "foot-walking"
        if self._target_loc != self._cur_loc:
            try:
                geom = Tracker.ors_client.directions(coordinates=((self._cur_loc.lon, self._cur_loc.lat),
                                                     (self._target_loc.lon, self._target_loc.lat)),
                                                     profile=prof)['routes'][0]['geometry']
                track = convert.decode_polyline(geom)['coordinates']
                # Меняем (lon, lat) координаты на (lat, lon)
                self._track = [(pnt[1], pnt[0]) for pnt in track]
                # Последняя точка в маршруте должна быть наша цель
                self._track.append(self._target_loc.pos)
            except Exception as e:
                print(e)
                # Маршрут не построен, никуда не двигаемся
                # self._target_loc = Location(*self._cur_loc.pos)

    # Задаем двигаться в направлении direction(азимут) на расстояние dist(метры) со скоростью speed(км/ч)
    def move_dir(self, direction, dist, speed=3):
        # Фиксируем нашу текущую позицию
        self._calc_loc()
        self._target_loc = self._cur_loc.fwd(direction, dist)
        # Строим трек до заданной точки
        self._build_route()
        self._speed = speed

    # Задаем двигаться до точки с координатами lat, lon (широта, долгота) со скоростью speed(км/ч)
    def move_to(self, lat=None, lon=None, speed=3, location=None):
        # Фиксируем нашу текущую позицию
        self._calc_loc()

        if location:
            self._target_loc = location
        elif lat and lon:
            self._target_loc = Location(lat, lon)
        # Строим трек до заданной точки
        self._build_route()
        self._speed = speed

    # Вычисление текущего положения, с учетом прошедшего времени, заданной скорости и целевой точки
    def _calc_loc(self):
        # Если мы в целевой точке, то прекратить движение
        if self._cur_loc == self._target_loc:
            self._speed = 0
        # Если маршрут не построен, пробуем построить, иначе никуда не двигаемся
        if self._speed > 0 and not self._track:
            self._build_route()
            if not self._track:
                self._speed = 0
        # Текущее время
        ts = time.time()
        if self._speed > 0:
            # Прошедшее время (сек)
            delta_t = ts - self._sync_time  # delta t in seconds
            # Считаем путь, который мы должны пройти за прошедшее время (метры)
            delta_s = (self._speed / 3.6) * delta_t  # meters
            self._odo += delta_s
            # Перебираем точки в треке, пока "пройденный" нами путь больше расстояния до следующей точки
            while self._track:
                # Координаты следующей точки в треке
                next_pnt = Location(*self._track[0])
                # Азимут и расстояние до следующей точки
                azimuth, dist = self._cur_loc.inv(*next_pnt.pos)
                # Если до следющей точки дальше чем пройденный нами путь, то считаем где мы остановились
                if delta_s <= dist:
                    # Двигаемся на расстояние delta_s в направлении следующей точки
                    self._cur_loc = self._cur_loc.fwd(azimuth, delta_s)
                    break
                # Проверить, не "проскочили" ли мы финишную точку
                elif next_pnt == self._target_loc:
                    self._cur_loc = self._target_loc
                    self._speed = 0
                    self._track = None
                    break
                # Проскочили точку, едем дальше
                delta_s -= dist
                del self._track[0]

        # Запоминаем время произведенных вычислений
        self._sync_time = ts

    speed = property(get_speed, set_speed)
