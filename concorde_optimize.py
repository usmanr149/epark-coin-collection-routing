import sqlite3
import pandas as pd

from flask import Response, Flask, send_file

import json
import urllib.request

import os
import subprocess

import itertools
import polyline

app = Flask(__name__)

def shift(l,n):
    return itertools.islice(itertools.cycle(l),n,n+len(l))

def get_distance(direction_data):
    """
    get distance from google directions api response,
    the unit for this field is meter
    """
    return json.loads(direction_data)['routes'][0]['legs'][0]['distance']['value']

def get_path(direction_data):
    """
    get distance from google directions api response,
    the unit for this field is meter
    """
    path = []
    for r in json.loads(direction_data)['routes'][0]['legs']:
        for i in r['steps']:
            path += polyline.decode(i['polyline']['points'])

    return polyline.encode(path)

def get_time(direction_data):
    """
    get time from google directions api response,
    the unit for this field is seconds
    """
    return json.loads(direction_data)['routes'][0]['legs'][0]['duration']['value']


# after running the Concorde executable, parse the output file
def parse_solution(filename):
    solution = []
    f = open(filename, 'r')
    for line in f.readlines():
        tokens = line.split()
        solution += [int(c) for c in tokens]
    f.close()
    solution = solution[1:]  # first number is just the dimension
    return solution

def conconrdeOptimize(matrix, stopovers, coords):

    matrix = [[str(j) for j in i] for i in matrix]

    i = 0
    id_order_match = {}
    for s in stopovers:
        id_order_match[i] = s
        i += 1

    # create input file for Concorde TSP solver
    # we are minimizing total time
    sc_id = 0
    output = ''
    for sc_name in matrix:
        output += '{0}\n'.format(" ".join(sc_name))
        sc_id += 1

    header = """NAME: ParkingMeters
TYPE: TSP
COMMENT: driving time (seconds)
DIMENSION:  %d
EDGE_WEIGHT_TYPE: EXPLICIT
EDGE_WEIGHT_FORMAT: FULL_MATRIX
EDGE_WEIGHT_SECTION
""" % sc_id

    with open('/app/sc.tsp', 'w') as output_file:
        output_file.write(header)
        output_file.write(output)

    tsp_path = '/app/sc.tsp'
    bdir = os.path.dirname(tsp_path)
    os.chdir(bdir)

    CONCORDE = os.environ.get('concorde', '/app/concorde/TSP/concorde')
    try:
        output = subprocess.check_output([CONCORDE, tsp_path], shell=False)
    except OSError as exc:
        if "No such file or directory" in str(exc):
            raise TSPSolverNotFound(
                "{0} is not found on your path or is not executable".format(CONCORDE))

    solf = os.path.join(
        bdir, os.path.splitext(os.path.basename(tsp_path))[0] + ".sol")

    solution = parse_solution(solf)

    coords_path = []
    optimal_path = []
    way_points = []
    for solution_id in solution:
        optimal_path.append(id_order_match[solution_id])
        coords_path.append("(" + str(coords[solution_id][0]) + "," + str(coords[solution_id][1]) + ")")
        way_points.append(str(coords[solution_id][0]) + "," + str(coords[solution_id][1]))

    # check if start or end occurs first in the optimal_path
    start = [index for index in range(len(optimal_path)) if optimal_path[index] == 'start'][0]
    end = [index for index in range(len(optimal_path)) if optimal_path[index] == 'end'][0]
    if start > end:
        optimal_path = list(shift(optimal_path, start))
        coords_path = list(shift(coords_path, start))
        way_points = list(shift(way_points, start))
    else:
        optimal_path = list(shift(optimal_path, start+1))[::-1]
        coords_path = list(shift(coords_path, start+1))[::-1]
        way_points = list(shift(way_points, start+1))[::-1]

    # this is the old url path, doesn't default to your location
    url = 'https://www.google.ca/maps/dir/' + way_points[0] + '/' + "/".join(coords_path[1:])
    # this url defaults to your location
    # url = """https://www.google.com/maps/dir/?api=1&destination={0}&travelmode=driving&waypoints={1}""".format(coords_path[-1],
    #                                                                                                           "%7C".join(coords_path[1:-1]))
    url_path = 'https://maps.googleapis.com/maps/api/directions/json?origin={0}&destination={1}&waypoints=optimize:false|{2}'.format(
        way_points[0], way_points[-1], "|".join(way_points[1:-1])
    )

    return optimal_path, url, url_path