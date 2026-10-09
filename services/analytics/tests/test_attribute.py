"""Plate-to-vehicle binding and the colour heuristic.

The feedsim hexes are regression anchors (they pin the thresholds), not evidence of
accuracy on real footage; the HSV anchors cover real paint the simulator never renders.
"""
import cv2
import numpy as np
import pytest

from sentinel_analytics.attribute import (bind_parent, body_pixels, classify_colour, containment,
                                          frame_has_colour, vehicle_colour)
from sentinel_analytics.objects import Obj

PLATE = (140, 160, 80, 20)          # x, y, w, h
CAR = Obj("car", (60, 60, 240, 150), 0.8)


def test_containment():
    assert containment(PLATE, CAR.box) == 1.0
    assert containment(PLATE, (0, 0, 10, 10)) == 0.0
    assert containment((0, 0, 10, 10), (5, 0, 10, 10)) == 0.5


def test_binds_to_the_vehicle_that_contains_the_plate():
    assert bind_parent(PLATE, [CAR]) == CAR


def test_smallest_container_wins():
    bus = Obj("bus", (0, 0, 600, 400), 0.9)          # a bus box that happens to enclose the car
    assert bind_parent(PLATE, [bus, CAR]) == CAR


def test_ambiguous_parents_abstain():
    truck = Obj("truck", (58, 58, 250, 156), 0.7)      # same vehicle, second class, similar size
    assert bind_parent(PLATE, [CAR, truck]) is None


def test_side_by_side_overlap_abstains():
    big_car = Obj("car", (20, 40, 320, 190), 0.8)
    scooter = Obj("motorcycle", (120, 110, 120, 220), 0.8)  # covers the plate, half outside the car
    assert bind_parent(PLATE, [big_car, scooter]) is None


def test_vehicle_in_front_of_a_larger_one_wins():
    scooter = Obj("motorcycle", (120, 60, 120, 140), 0.8)   # wholly inside the car's box: in front
    assert bind_parent(PLATE, [CAR, scooter]) == scooter


def test_off_centre_plate_is_not_this_vehicles():
    beside = Obj("car", (130, 60, 300, 150), 0.8)           # plate near its left edge
    assert bind_parent(PLATE, [beside]) is None


@pytest.mark.parametrize("objs", [
    [],
    None,
    [Obj("person", (60, 60, 240, 150), 0.9)],          # a plate never belongs to a person
    [Obj("bicycle", (60, 60, 240, 150), 0.9)],         # bicycles carry no registration plate
    [Obj("car", (400, 60, 240, 150), 0.9)],            # plate outside the box
    [Obj("car", (130, 150, 100, 40), 0.9)],            # plate is 80% of the "vehicle": not a parent
    [Obj("car", (60, 150, 240, 150), 0.9)],            # plate in the top quarter of the box
])
def test_no_parent_is_null_not_a_guess(objs):
    assert bind_parent(PLATE, objs) is None


def _patch(bgr, noise=6, shape=(60, 120), seed=0):
    rng = np.random.default_rng(seed)
    p = np.full((*shape, 3), bgr, np.int16) + rng.normal(0, noise, (*shape, 3)).astype(np.int16)
    return np.clip(p, 0, 255).astype(np.uint8)


@pytest.mark.parametrize("hexs,want", [
    ("2d4a8a", "blue"), ("8a2d2d", "red"), ("3a3a3a", "black"), ("d8d8d8", "white/silver"),
    ("6b8e23", "green"), ("8b5a2b", "brown"), ("b0b0b0", "white/silver"),
])
def test_feedsim_body_colours(hexs, want):
    r, g, b = (int(hexs[i:i + 2], 16) for i in (0, 2, 4))
    name, conf = classify_colour(_patch((b, g, r)).reshape(-1, 3))
    assert name == want and conf > 0.3        # near a lightness cut the score is low, by design


@pytest.mark.parametrize("hsv,want", [
    ((24, 228, 240), "yellow"),     # taxi yellow in sun: V near 255 must stay chromatic
    ((20, 100, 214), "beige"),
    ((20, 64, 214), "white/silver"),    # a washed-out cream is not called a colour
    ((105, 70, 200), "white/silver"),   # silver paint with a sky-blue cast is not "blue"
    ((14, 255, 240), "orange"),
    ((0, 8, 184), "white/silver"),
    ((0, 4, 240), "white/silver"),
    ((0, 10, 45), "black"),
    ((175, 180, 96), "maroon"),
    ((109, 200, 150), "blue"),
])
def test_real_paint_anchors(hsv, want):
    bgr = cv2.cvtColor(np.full((60, 120, 3), hsv, np.uint8), cv2.COLOR_HSV2BGR)
    name, _ = classify_colour(_patch(bgr[0, 0].tolist(), noise=4).reshape(-1, 3))
    assert name == want


def test_abstains_when_blown_out_or_starved():
    assert classify_colour(np.full((500, 3), 252, np.uint8)) == (None, 0.0)
    assert classify_colour(np.full((100, 3), 128, np.uint8)) == (None, 0.0)


def test_monochrome_frames_get_no_colour():
    red = np.full((200, 300, 3), (40, 40, 200), np.uint8)
    ir = cv2.cvtColor(cv2.cvtColor(red, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    assert frame_has_colour(red) and not frame_has_colour(ir)


def _car_frame(body_bgr):
    img = np.full((360, 640, 3), (60, 60, 60), np.uint8)                 # road
    cv2.rectangle(img, (60, 60), (300, 210), body_bgr, -1)                 # body
    cv2.rectangle(img, (100, 66), (260, 100), (40, 30, 25), -1)            # rear glass (top band)
    cv2.rectangle(img, PLATE[:2], (PLATE[0] + PLATE[2], PLATE[1] + PLATE[3]), (255, 255, 255), -1)
    cv2.putText(img, "GJ01AB1234", (PLATE[0] + 2, PLATE[1] + 15), 0, 0.35, (0, 0, 0), 1)
    return img


def test_plate_and_glass_do_not_colour_the_car():
    img = _car_frame((0x8a, 0x4a, 0x2d))                                   # BGR for a blue body
    assert vehicle_colour(img, CAR, PLATE)[0] == "blue"


def test_two_wheelers_and_tiny_boxes_get_no_colour():
    img = _car_frame((0x8a, 0x4a, 0x2d))
    assert vehicle_colour(img, Obj("motorcycle", CAR.box, 0.9), PLATE) is None
    assert body_pixels(img, (60, 60, 40, 30), PLATE) is None
