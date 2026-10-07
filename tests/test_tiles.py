import math

from app import tiles


def test_wasque_is_in_region_and_far_away_is_not():
    x, y = tiles.lonlat_to_tile(-70.45, 41.35, 13)
    assert tiles.in_region(13, x, y)
    x, y = tiles.lonlat_to_tile(-74.0, 40.7, 13)  # NYC
    assert not tiles.in_region(13, x, y)
    assert not tiles.in_region(16, *tiles.lonlat_to_tile(-70.45, 41.35, 16))  # past MAX_Z


def test_tile_bbox_contains_its_point():
    lon, lat, z = -70.40, 41.325, 14
    x, y = tiles.lonlat_to_tile(lon, lat, z)
    minx, miny, maxx, maxy = tiles.tile_bbox(z, x, y)
    mx = math.radians(lon) * 6378137
    my = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137
    assert minx <= mx < maxx and miny < my <= maxy


def test_offline_set_is_phone_sized():
    n = sum(len(xs) * len(ys) for xs, ys in (tiles.tile_range(z, tiles.SAVE_BOUNDS) for z in range(9, 15)))
    assert 500 < n < 1200
