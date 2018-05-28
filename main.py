from flask import Flask, render_template, request, jsonify, make_response,Response
from requests.auth import HTTPBasicAuth
import requests
import xml.etree.ElementTree as ET
from flask import g
from functools import wraps

import configparser

import urllib.request
import pdfkit

from collections import OrderedDict

import os
import pandas as pd

import redis

import datetime

from concorde_optimize import conconrdeOptimize, get_time, get_path
from helperFunctions import rearrangeStopOrder, haversine

from sqlalchemy import create_engine

from requests_ntlm import HttpNtlmAuth
from io import StringIO

app = Flask(__name__)

#Read the api value
config = configparser.ConfigParser()
config.read("./.properties")

#api = os.environ.get('api', 'what')
api = config['API']['api']

def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    return username == 'admin' and password == 'secret'

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

#redis database initialize
r = redis.Redis(host='172.17.0.2', port=6379, charset="utf-8", decode_responses=True)
#r = redis.Redis(host='127.0.0.1', port=6379, charset="utf-8", decode_responses=True)

# def get_db():
#     db = getattr(g, '_database', None)
#     if db is None:
#         db = g._database = sqlite3.connect(DATABASE)
#     return db
#
# @app.teardown_appcontext
# def close_connection(exception):
#     db = getattr(g, '_database', None)
#     if db is not None:
#         db.close()

def getData():
    #get cash balance from CALE
    response = requests.get(
        'https://webservice.mdc.dmz.caleaccess.com/cwo2exportservice/LiveDataExport/1/LiveDataExportService.svc/terminalbalances',
        auth=HTTPBasicAuth(config['CALE']['user'], config['CALE']['password']))
    root = ET.fromstring(response.content)
    df_terminalBalance = pd.DataFrame(columns=['TerminalID', 'TerminalLocation', 'CoinBalance'])
    for child in root:
        df_terminalBalance = df_terminalBalance.append(pd.DataFrame(
            [[str(child.attrib['TerminalID']).lower(), child.attrib['TerminalLocation'].replace(",", ""),float(child.attrib['CoinBalance'])]],
            columns=['TerminalID', 'TerminalLocation', 'CoinBalance']))
        # data pulled from CALE api are stored in the redis database for half-an-hour
        if r.exists(str(child.attrib['TerminalID']).lower()):
            #terminal locations as they cause csv reading errors.
            r.hset(str(child.attrib['TerminalID']).lower(), 'TerminalLocation', child.attrib['TerminalLocation'].replace(",", ""))
            r.hset(str(child.attrib['TerminalID']).lower(), 'CoinBalance', float(child.attrib['CoinBalance']))
        else:
            r.hset(str(child.attrib['TerminalID']).lower(), 'TerminalLocation', child.attrib['TerminalLocation'].replace(",", ""))
            r.hset(str(child.attrib['TerminalID']).lower(), 'CoinBalance', float(child.attrib['CoinBalance']))
            r.expire(str(child.attrib['TerminalID']).lower(), 1800)

    response = requests.get(
        'https://webservice.mdc.dmz.caleaccess.com/cwo2exportservice/LiveDataExport/1/LiveDataExportService.svc/uncollectedterminals',
        auth=HTTPBasicAuth(config['CALE']['user'], config['CALE']['password']))
    root = ET.fromstring(response.content)

    df_Days = pd.DataFrame(columns=['TerminalID', 'CollectionDateLocal', 'NumberOfDays', 'Balance'])
    for child in root:
        if child.attrib['TerminalStatus'] == 'Active':
            df_Days = df_Days.append(pd.DataFrame([[child.attrib['TerminalID'], child.attrib['CollectionDateLocal'],
                                          child.attrib['NumberOfDays'], child.attrib['Balance']]],
                                        columns=['TerminalID', 'CollectionDateLocal', 'NumberOfDays', 'Balance']))

    df_Days['CollectionDateLocal'] = pd.to_datetime(df_Days['CollectionDateLocal'], format='%Y-%m-%dT%H:%M:%S.%f')
    df_Days['Balance'] = df_Days['Balance'].apply(lambda x: float(x))
    df_Days['NumberOfDays'] = df_Days['NumberOfDays'].apply(lambda x: float(x))

    df_Days.drop_duplicates(subset=['TerminalID'], keep='last', inplace=True)

    df_terminalBalance = df_terminalBalance.merge(df_Days[['TerminalID', 'NumberOfDays']], on='TerminalID', how='left')

    df_terminalBalance = df_terminalBalance.sort_values('CoinBalance', ascending=False)

    # get terminal locations from db
    # Create a SQL connection to our SQLite database
    #con = get_db()

    # the result of a "cursor.execute" can be iterated over by row
    df_Locations = getEparkLoc()
    #con.close()

    df = df_terminalBalance.merge(df_Locations, on='TerminalID', how='left')

    df.sort_values('CoinBalance', ascending=False, inplace=True)

    df.set_index('TerminalID', inplace=True)

    id_latlon = OrderedDict()

    for index, row in df.iterrows():
        id_latlon[index] = {'CoinBalance': row['CoinBalance'], 'lat_lon': str(row['lat'])+","+str(row['lon']), 'Days Since last Collected':
                            row['NumberOfDays']}

    return id_latlon

@app.route("/")
@app.route("/optimap/")
@requires_auth
def optimap():
    id_latlon = getData()
    return render_template('directions.html', id_latlon=id_latlon)

@app.route("/show_tables/")
def show_tables():
    d = datetime.datetime.today().strftime('%Y-%m-%d')

    optimized_route = r.lrange('optimized_route', 0, -1)
    #optimal_route = [['TerminalID', 'LatLon', 'BoxIn', 'BoxOut', 'Time', 'Notes']]

    if optimized_route is not None:
        optimal_route_with_info = []
        for s in optimized_route:
            if r.hget(s, 'CoinBalance') is not None and r.hget(s, 'TerminalLocation') is not None:
                optimal_route_with_info.append(s + "<br>" + str(r.hget(s, 'TerminalLocation')))
                #optimal_route.append([s + ": " + str(r.hget(s, 'TerminalLocation')), , ])
            else:
                #This takes care if the page was loaded too long ago and has not been refreshed.
                return "Your session has expired. Refresh the previous page and rerun."
    else:
        optimal_route_with_info = [''] * 25

    #return render_template('StopOrederTable.html', optimal_route=optimal_route_with_info, date=d)

    rendered = render_template('StopOrederTable.html', optimal_route=optimal_route_with_info, date=d)
    pdf = pdfkit.from_string(rendered, False)

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=output.pdf'

    return response

def savePath(url_path, stops):
    DB_CONN = 'postgresql+psycopg2://coeadmin@coeacepostgres:5kApENkVumi6tGiQ@coeacepostgres.postgres.database.azure.com/tracking'
    engine = create_engine(DB_CONN)
    con = engine.connect()

    url_path += '&key={0}'.format(api)

    # get the path from google
    try:
        f = urllib.request.urlopen(url_path)
        text = f.read().decode('utf8')
        path = get_path(text)
    except:
        path = "An error occurred"

    # Insert the path into the database
    # get the date and time
    d = datetime.datetime.today()
    sql = """SELECT COUNT(*) FROM optiroute.suggested_path WHERE date(date) = '{0}'""".format(d.strftime('%Y-%m-%d'))
    rows = con.execute(sql).fetchall()[0][0]
    con.execute("""INSERT INTO optiroute.suggested_path (date, date_feature, path,
    stops) VALUES (to_timestamp('{0}', 'YYYY-MM-DD HH24:MI:SS'), {1}, '{2}', '{3}')"""
        .format(
        d.strftime('%Y-%m-%d %H:%M:%S'), rows, path, ",".join(stops)
    ))
    # close the connection
    con.close()

def getEparkLoc():
    headers = {'accept': 'application/json;odata=verbose'}
    response = requests.get(
        'https://sharepoint.edmonton.ca/transportation/to/pm/psm/_vti_bin/owssvr.dll?XMLDATA=1&List={E8B690DA-1C9F-4B56-BBBC-74381A48E22E}&View={AB8D9EDE-876E-45A1-B3CE-6F386FB5D924}&RowLimit=0&RootFolder=%2ftransportation%2fto%2fpm%2fpsm%2fLists%2fPay%20Machine%20Inventory',
        auth=HttpNtlmAuth(config['SharePoint']['user'], str(config['SharePoint']['password'])), headers=headers)
    root = ET.fromstring(response.content)
    csv = ['TerminalID,lat,lon']
    for c in root.iter('{#RowsetSchema}row'):
        if 'ows_xcoordinate' not in c.attrib.keys() or 'ows_Ycoordinate' not in c.attrib.keys():
            pass  # csv.append(c.attrib['ows_LinkTitle']+ "," + + "," + c.attrib['ows_Ycoordinate'])
        else:
            csv.append(
                str(c.attrib['ows_LinkTitle']).lower() + "," + c.attrib['ows_xcoordinate'] + "," + c.attrib['ows_Ycoordinate'])

    DATA = StringIO("\n".join(csv))
    df = pd.read_csv(DATA, sep=",")
    return df


#This function will construct the distance matrix and pass it back to flask to pass forward to optimize function.
@app.route('/progress')
def progress():
    # Read the MachineID selected on the web page
    stops = request.args.get('stopover').split(",")

    #store the stops in the redis database
    # pass an iterable by using the splat operator to unpack it:
    r.delete('stops')
    r.rpush('stops', *stops)

    #add start and stop to stops
    stops.append('start')
    stops.append('end')

    #read the lat-lon from the db
    #con = sqlite3.connect(DATABASE)
    # con = get_db()

    #df_Locations = pd.read_sql('Select * FROM EParkLocations WHERE TerminalID in {0};'.format(str(stops).
    #                                                                                          replace("[", "(").replace(']',
    #                                                                                                                    ')')), con)
    #con.close()
    df_EPark_Loc_ALL = getEparkLoc()
    df_Locations = df_EPark_Loc_ALL[df_EPark_Loc_ALL.TerminalID.isin(stops)]

    df_Locations.set_index('TerminalID', inplace=True)

    def generate():
        # Check if any stops address is not found in the address table
        missing = set(stops[:-2]) - set(df_Locations.index)
        if len(missing) > 0:
            yield 'data:' + 'Not Found' + '\ndata:' + str(missing) + '\n\n'
        else:
            # get the stopver coords, ignore start and end
            coords = []
            for s in stops[:-2]:
                coords.append([df_Locations.loc[s]['lat'], df_Locations.loc[s]['lon']])

        # add a start and end to coords
        coords.append([53.5892396, -113.42835785])
        coords.append([53.568889, -113.502966])

        times_matrix = [[0 for i in range(len(coords))] for j in range(len(coords))]

        # store the coords into the redis data but first delete coords if they are already in the database
        r.delete('coords')
        r.rpush('coords', *coords)
        #store the results in redis database
        for i in range(len(stops)):
            for j in range(len(stops)):
                if i == j:
                    times_matrix[i][j] = 0
                # if the result is already in the redis database then no need to query google
                elif r.hget(stops[i], stops[j]) is not None:
                    times_matrix[i][j] = int(float(r.hget(stops[i], stops[j])))
                else:
                    # url = """https://maps.googleapis.com/maps/api/directions/json?origin={0},{1}&destination={2},{3}&key={4}""".format(
                    #     coords[i][0], coords[i][1],
                    #     coords[j][0], coords[j][1],
                    #     api)
                    # f = urllib.request.urlopen(url)
                    # text = f.read().decode('utf8')
                    # times_matrix[i][j] = int(get_time(text))
                    # if r.exists(stops[i]):
                    #     r.hset(stops[i], stops[j], times_matrix[i][j])
                    # else:
                    #     r.hset(stops[i], stops[j], times_matrix[i][j])
                    #     r.expire(stops[i], 1800)
                    # haversine distance for testing purposes
                    times_matrix[i][j] = round(haversine(coords[i][1], coords[i][0], coords[j][1], coords[j][0]))
                    if r.exists(stops[i]):
                        r.hset(stops[i], stops[j], times_matrix[i][j])
                    else:
                        r.hset(stops[i], stops[j], times_matrix[i][j])
                        r.expire(stops[i], 1800)
            yield "data:" + str(int(i * 100 / len(coords))) + "\n\n"

        #set the distance and time between start and stop to 0
        times_matrix[len(coords) - 2][len(coords) - 1] = 0
        times_matrix[len(coords) - 1][len(coords) - 2] = 0

        rv, url, url_path = conconrdeOptimize(times_matrix, stops, coords)

        # fix the undergrounds parking lot locations
        rv = rearrangeStopOrder(rv)

        #add the optimized route to redis database (delete if already a solution exists)
        r.delete('optimized_route')
        r.rpush('optimized_route', *rv[1:-1])

        # Save the polyline to the database
        savePath(url_path, rv[1:-1])

        yield 'data:' + "done" + '\ndata:' + str(rv[1:-1]) + '\ndata:' + str(url) + '\n\n'

    return Response(generate(), mimetype='text/event-stream', headers={'X-Accel-Buffering': 'no'})# mimetype='text/json')

if __name__ == "__main__":
    #app.run(port=4000, debug=True)
    app.run(host='0.0.0.0', port = 80)
