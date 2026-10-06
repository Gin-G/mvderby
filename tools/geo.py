"""Lat/lon <-> PDF point transform for the NOAA Custom Chart (GeoPDF viewport, Web Mercator)."""
import math

X0, X1 = 50.96465, 2397.03535
Y0, Y1 = 202.16569, 1511.43431
LAT0, LAT1 = 41.1388, 41.65449
LON0, LON1 = -71.22814, -70.00095
PAGE_H = 1584.0


def merc(lat):
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


M0, M1 = merc(LAT0), merc(LAT1)


def ll2pdf(lat, lon):
    xf = (lon - LON0) / (LON1 - LON0)
    yf = (merc(lat) - M0) / (M1 - M0)
    return X0 + xf * (X1 - X0), Y0 + yf * (Y1 - Y0)


def pdf2ll(x, y):
    xf = (x - X0) / (X1 - X0)
    yf = (y - Y0) / (Y1 - Y0)
    lon = LON0 + xf * (LON1 - LON0)
    m = M0 + yf * (M1 - M0)
    return math.degrees(2 * math.atan(math.exp(m)) - math.pi / 2), lon
