# This function rearranges the stop order so that the underground stops are alphabetical
def rearrangeStopOrder(stops):
    # find the index of the stops that start with 7010
    st = []
    for s in stops:
        if s.startswith('7010'):
            st.append(stops.index(s))

    if len(st)>1:
        stops = stops[:min(st)] + sorted(stops[min(st):max(st) + 1]) + stops[max(st) + 1:]

    # find the index of the stops that start with 7020
    st = []
    for s in stops:
        if s.startswith('7020'):
            st.append(stops.index(s))

    if len(st) > 1:
        stops = stops[:min(st)] + sorted(stops[min(st):max(st) + 1]) + stops[max(st) + 1:]

    # find the index of the stops that start with 7000
    st = []
    for s in stops:
        if s.startswith('7000'):
            st.append(stops.index(s))

    if len(st)>1:
        stops = stops[:min(st)] + sorted(stops[min(st):max(st) + 1]) + stops[max(st) + 1:]

    return stops

from math import radians, cos, sin, asin, sqrt
def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    # Radius of earth in kilometers is 6371
    km = 6371* c
    return km*1000
