# -*- coding: utf-8 -*-
"""
Created on 1-10-2020

@authors:
Frederique de Groen (frederique.degroen@deltares.nl)
"""

# external modules
import os, sys
folder = os.path.dirname(os.path.realpath(__file__))
sys.path.append(folder)
import copy
import pandas as pd
import time
import logging
import networkx as nx
import osmnx
import numpy as np
from numpy import nanmean
import warnings
import geopandas as gpd
import rtree
import pickle
import rasterio
from shapely.geometry import Point, LineString, MultiLineString
from statistics import mean
from numpy import object as np_object
from geopy import distance
from pathlib import Path

# local modules
# todo change os to pathlib


def single_link_alternative_routes(G, InputDict, crs=4326):
    """
    This is the function to analyse roads with a single link disruption and
    an alternative route.

    Arguments:
        InputDict [dictionary] = dictionary of input data used for calculating
            the costs for taking alternative routes
        ParameterNamesDict [dictionary] = names of the parameters used for calculating
            the costs for taking alternative routes
    """
    logging.info("----------------------------- {} -----------------------------".format(InputDict['analysis_name']))
    startstart = time.time()

    print(
        "\nYou have chosen the Single Link Alternative Route Finder. You might need to give a bit more input later. Starting to calculate now...\n")

    # TODO adjust to the right names of the RA2CE tool
    # if 'road_usage_data_path' in InputDict:
    #     road_usage_data = pd.read_excel(InputDict['road_usage_data_path'])
    #     road_usage_data.dropna(axis=0, how='all', subset=['vehicle_type'], inplace=True)
    #     aadt_names = [aadt_name for aadt_name in road_usage_data['attribute_name'] if aadt_name == aadt_name]
    # else:
    #     aadt_names = None
    #     road_usage_data = pd.DataFrame()
    road_usage_data = None  # can be removed if the above is fixed
    aadt_names = None  # can be removed if the above is fixed

    # CALCULATE CRITICALITY
    #TODO return back to criticality_single_link. Now temporarily changed for RWS project

    # gdf = criticality_single_link_osm(G, InputDict['shp_unique_ID'], roadUsageData=road_usage_data, aadtNames=aadt_names)
    gdf = criticality_single_link_osm(G)
    logging.info("Function [criticality_single_link]: executing")

    # Extra calculation possible (like multiplying the disruption time with the cost for disruption)
    # todo: input here this option

    # save to shapefile
    gdf.crs = {'init': 'epsg:{}'.format(crs)}
    save_name = os.path.join(InputDict['output'], '{}_criticality.shp'.format(InputDict['analysis_name']))
    gdf_to_shp(gdf, save_name)

    print("\nThe shapefile with calculated criticality can be found here:\n{}".format(save_name))

    end = time.time()
    logging.info("Full analysis [single_link_alternative_routes]: {}".format(timer(startstart, end)))


def multi_link_alternative_routes(G, InputDict, crs=4326):
    """Calculates if road segments that are disrupted have an alternative route from node to node
    Args:

    Returns:+

    """

    logging.info("----------------------------- {} -----------------------------".format(InputDict['analysis_name']))
    startstart = time.time()

    print(
        "\nYou have chosen the Multi-link Disruption (1): Calculate the disruption for all damaged roads. Starting to calculate now...\n")

    # load the input files if they are there
    if 'shp_unique_ID' in InputDict:
        id_name = InputDict['shp_unique_ID']
    else:
        id_name = 'G_fid_simple'

    # initiate variables
    id_name_hazard = None

    # if the hazard data is joined with the network by ID (otherwise spatially)
    if 'hazard_unique_ID' in InputDict:
        id_name_hazard = InputDict['hazard_unique_ID']
        # TODO: join hazard data with network by ID (now it uses a gdf, should be graph)
        G = hazard_join_id_shp(G, InputDict)
    else:
        G = hazard_intersect_graph(G, InputDict['hazard_data'], InputDict['hazard_attribute_name'], InputDict['analysis_name'],
                                   agg=InputDict['hazard_aggregation'])

    # CALCULATE CRITICALITY
    gdf = criticality_multi_link_hazard(G, InputDict['hazard_attribute_name'], InputDict['hazard_threshold'],
                                        id_name)
    logging.info("Function [criticality_single_link]: executing")

    # Extra calculation possible (like multiplying the disruption time with the cost for disruption)
    # todo: input here this option

    # save to shapefile
    gdf.crs = {'init': 'epsg:{}'.format(crs)}
    save_name = os.path.join(InputDict['output'], '{}_criticality.shp'.format(InputDict['analysis_name']))
    gdf_to_shp(gdf, save_name)

    print("\nThe shapefile with calculated criticality can be found here:\n{}".format(save_name))

    end = time.time()
    logging.info("Full analysis [multi_link_alternative_routes]: {}".format(timer(startstart, end)))


def multi_link_alternative_routes_rws(G, InputDict, save_file=False, crs=4326):
    """Calculates if road segments that are disrupted have an alternative route from node to node
    copy of multi_link_alternative_routes, adjusted for RWS, because the hazard intersect is not done within the script.
    Args:

    Returns:

    """

    logging.info("----------------------------- {} -----------------------------".format(InputDict['analysis_name']))
    startstart = time.time()

    print(
        "\nYou have chosen the Multi-link Disruption (1) _RWS: Calculate the disruption for all damaged roads. Starting to calculate now...\n")

    # load the input files if they are there
    if 'shp_unique_ID' in InputDict:
        id_name = InputDict['shp_unique_ID']
    else:
        id_name = 'G_fid_simple'
    #TODO implement this in input table.
    weighing = 'time'
    if weighing == 'time':
        # not yet possible for input with shapefiles, except when a max speed attribute is attached to the shapefile
        # calculate the time it takes per road segment

        #define path where to save csv with average speeds or to load when it already exists
        avg_speed_path = InputDict['output'] / 'avg_speeds.csv'
        avg_speeds = calc_avg_speed(G, 'highway', existing_path=avg_speed_path)

        # moved from criticality_multi_link_hazard_OD to allow batch runs with the same speeds
        path = InputDict['output'] / 'G_simple_avg_speed.gpickle'
        if path.exists():
            print('simple pickle with average speeds was already created, we load the existing one')
            G = nx.read_gpickle(path)
        else:
            if len(avg_speeds.loc[avg_speeds['avg_speed'] == 0]) > 0:
                logging.info("An average speed of 50 is used in locations where the maximum speed limit is 0 in OSM data.")
                avg_speeds.loc[avg_speeds['avg_speed'] == 0, 'avg_speed'] = 50  # this is assumed
            G = assign_avg_speed(G, avg_speeds, 'highway', save_path=InputDict['output'], save_pickle=True)

            # make a time value of seconds, length of road streches is in meters
            for u, v, k, edata in G.edges.data(keys=True):
                hours = (edata['length'] / 1000) / edata['avgspeed']
                G[u][v][k][weighing] = hours * 3600
            nx.write_gpickle(G, path, protocol=4)
            print("Saving graph with avgspeed to .gpickle")

    #add part where the simple_IDs are matched with the flood data from the exposure part.
    gdf_pickle = InputDict['hazard_pickle']
    with open(gdf_pickle, 'rb') as f:
        gdf = pickle.load(f)
    print('flood data ', InputDict['hazard_pickle'],' loaded')
    #in e pickle is de simple_id als float
    gdf[id_name] = gdf[id_name].astype('int64')
    #add values of hazard to the simple IDs and identify which edges are excluded when performing the multi-link disruption
    if InputDict['hazard_attribute_name'][0] == 'Embankment_avg_depth':
        G, count = match_simple_ids2(G, gdf, InputDict['hazard_attribute_name'][0],InputDict['hazard_threshold'])
    else:
        G, count = match_simple_ids(G, gdf, InputDict['hazard_attribute_name'][0],InputDict['hazard_threshold'])

    #check if the main network is failing. If count >0 do the whole analysis. otherwise return np.nan output.
    if count > 0:
        # Create Origins and Destinations
        #TODO: add edges for directed graphs
        gdf, df_origin = multi_link_od_matrix_rws(G, InputDict,save_file=True, crs=4326)
        output = assign_traffic_data(gdf, df_origin, InputDict)
        logging.info("Function [criticality_single_link]: executing")
    if count == 0:
        print('main network is not disrupted')
        output = pd.Series({'extra_time': np.nan, 'detour_Euro_ET_Hr': np.nan, 'detour_Euro_AS_Hr': np.nan, 'TNO_ET_Euro_Hr': np.nan,
             'TNO_AS_Euro_Hr': np.nan}, name=str(input_dict[analysis]['analysis_name']))
    return output


def assign_traffic_data(gdf, df, InputDict):
    # TODO: assign the values to the affected road segments based on the preferred routes
    # summarize the average extra time (excluding negative values and same) based on origin.
    # crate gdf with columns: ['origin', 'avg_extra_time', 'G_fid_simple_in', 'LinkNr', 'ET_VTG', 'VOT_Etm', 'Euro_Etm_Hr'. 'Euro_AS_Hr']
    #load traffic data
    AllInput = Path(__file__).parents[1] / 'test/input/origin_destination'
    traffic_data = pd.read_csv(AllInput / 'G_fid_simple_LinkNr_dissolved.csv')
    traffic_data.G_fid_simp=traffic_data.G_fid_simp.astype('int')
    extra_time=gdf.groupby('origin'). agg({'extra_time': [nanmean]})['extra_time']['nanmean']

    #add column to origin_list_id
    df['extra_time'] = ''
    df['Euro_AS_Hr'] = ''
    df['Euro_ET_Hr'] = ''
    # TODO: consider adding the extra traveltimes based on TNO single link redundancy
    df['extra_time_AS_TNO'] = ''
    df['extra_time_ET_TNO'] = ''
    x = [x for x in df.index]
    for xx in x:
        df['extra_time'][xx]=extra_time[str(xx)]/3600 #convert to hours, since the traffic data is also in hours
        ids = df['G_fid_simple'][xx]
        sel = traffic_data.loc[traffic_data['G_fid_simp'].isin(ids)]
        df['Euro_AS_Hr'][xx] = np.nansum(sel['Euro_AS_Hr'])
        df['Euro_ET_Hr'][xx] = np.nansum(sel['Euro_ET_Hr'])
        df['extra_time_AS_TNO'][xx] = np.nanmean(sel['VA_AV_HWN']) / 60 #average extra traveltime based on TNO data in minutes -> hours
        df['extra_time_ET_TNO'][xx] = np.nanmean(sel['VA_Etm_HWN']) / 60 #average extra traveltime based on TNO data in minutes -> hours

    #multiply the costs for the traffic per hour with the extra average travel time
    df['detour_Euro_AS_Hr'] = np.where(df['extra_time'].isna(), df['extra_time'], df['extra_time'] * df['Euro_AS_Hr'])
    df['detour_Euro_ET_Hr'] = np.where(df['extra_time'].isna(), df['extra_time'], df['extra_time'] * df['Euro_ET_Hr'])
    df['TNO_AS_Euro_Hr'] = np.where(df['extra_time_AS_TNO'].isna(), df['extra_time_AS_TNO'], df['extra_time_AS_TNO'] * df['Euro_AS_Hr'])
    df['TNO_ET_Euro_Hr'] = np.where(df['extra_time_ET_TNO'].isna(), df['extra_time_ET_TNO'], df['extra_time_ET_TNO'] * df['Euro_ET_Hr'])

    df.to_pickle(InputDict['output']/'traffic'/(str(InputDict['analysis_name'])+'_traffic.p'))
    sums = df.sum()
    output = pd.Series({'extra_time': sums['extra_time'], 'detour_Euro_ET_Hr': sums['detour_Euro_ET_Hr'], 'detour_Euro_AS_Hr': sums['detour_Euro_AS_Hr'],'TNO_ET_Euro_Hr': sums['TNO_ET_Euro_Hr'], 'TNO_AS_Euro_Hr': sums['TNO_AS_Euro_Hr']}, name=str(InputDict['analysis_name']))
    print(output)
    return output

def match_simple_ids(G,gdf, value_col1, threshold):
    """Matches hazard intensity of an existing gdf with the simple_id's of the graph.
    Args:
        G [networkx graph]: networkx graph with at least simple_id
        gdf with simple_ids, complex ids and hazard attribute
        value_col [string] the attribute of the hazard within the gdf

    Returns:
        Graph with an additional columns indicating which simple_ids are disrupted by the hazard

    Created by Margreet van Marle and based on network_functions.match_ids (@Frederique de Groen) and create_network_from_osm_dump.add_simple_ID_to_G_complex (@Kees van Ginkel)
    """
    print('matching by simple_IDs')
    #todo check if nan values are used or not
    df1 = gdf.groupby('G_fid_simple')[value_col1].mean()
    dict_df1=dict(df1)
    df2 = gdf.groupby('G_fid_simple')['Underlying_avg_depth'].mean()
    dict_df2=dict(df2)
    obtained_simple_ids = nx.get_edge_attributes(G, 'G_fid_simple') # {(u,v,k) : 'G_fid_complex'}
    values_col1 = obtained_simple_ids.copy() #start with a copy
    values_col2 = obtained_simple_ids.copy() #start with a copy
    values_col3 = obtained_simple_ids.copy()
    count=0
    for key, value in obtained_simple_ids.items(): # {(u,v,k) : 'G_fid_complex'}
        values_col3[key] = 0
        try:
            new_value = dict_df1[value] #find simple id belonging to the complex id
            if np.isnan(new_value)==True:
                values_col1[key]=0
            else:
                values_col1[key] = new_value
                if values_col1[key] > threshold:
                    values_col3[key] = 1
                    count = count + 1.

        except KeyError as e:
            # print('Could not find the simple ID belonging to complex ID {}; value set to None'.format(key))
            values_col1[key] = 0

    for key, value in obtained_simple_ids.items(): # {(u,v,k) : 'G_fid_complex'}
        try:
            new_value2 = dict_df2[value]
            if np.isnan(new_value2)==True:
                values_col2[key] = 0
            else:
                values_col2[key] = new_value2
                if values_col2[key] > threshold:
                    values_col3[key] = 1
        except KeyError as e:
            # print('Could not find the simple ID belonging to complex ID {}; value set to None'.format(key))
            values_col2[key] = 0


    #Now the format of simple_ids_per_complex_id is: {(u,v,k) : 'G_fid_simple}
    nx.set_edge_attributes(G,values_col1,value_col1)
    nx.set_edge_attributes(G,values_col2,'Underlying_avg_depth')
    nx.set_edge_attributes(G,values_col3,'analysis')
    return G, count

def match_simple_ids2(G,gdf, value_col1, threshold):
    """Matches hazard intensity of an existing gdf with the simple_id's of the graph.
    Args:
        G [networkx graph]: networkx graph with at least simple_id
        gdf with simple_ids, complex ids and hazard attribute
        value_col [string] the attribute of the hazard within the gdf

    Returns:
        Graph with an additional columns indicating which simple_ids are disrupted by the hazard

    Created by Margreet van Marle and based on network_functions.match_ids (@Frederique de Groen) and create_network_from_osm_dump.add_simple_ID_to_G_complex (@Kees van Ginkel)
    """
    print('matching by simple_IDs')
    #when there is an embankment failure included. both the pavement as well as the embankment fail.

    temp1 = gdf.groupby('G_fid_simple')[value_col1,'Pavement_avg_depth' ].mean()
    df1 = temp1.max(axis=1)
    dict_df1 = dict(df1)

    df2 = gdf.groupby('G_fid_simple')['Underlying_avg_depth'].mean()
    dict_df2=dict(df2)

    obtained_simple_ids = nx.get_edge_attributes(G, 'G_fid_simple') # {(u,v,k) : 'G_fid_complex'}
    values_col1 = obtained_simple_ids.copy() #start with a copy -> these values determine the average waterdepth
    values_col2 = obtained_simple_ids.copy() #start with a copy -> these values determine the waterdepth on the underlying network
    values_col3 = obtained_simple_ids.copy() #start with a copy -> this one gives y/n for failing network (including underlying).

    count=0
    for key, value in obtained_simple_ids.items(): # {(u,v,k) : 'G_fid_complex'}
        values_col3[key] = 0
        try:
            new_value = dict_df1[value] #find simple id belonging to the complex id
            if np.isnan(new_value)==True:
                values_col1[key]=0
            else:
                values_col1[key] = new_value
                if values_col1[key] > threshold:
                    values_col3[key] = 1
                    count = count + 1

        except KeyError as e:
            # print('Could not find the simple ID belonging to complex ID {}; value set to None'.format(key))
            values_col1[key] = 0

    for key, value in obtained_simple_ids.items(): # {(u,v,k) : 'G_fid_complex'}
        try:
            new_value2 = dict_df2[value]
            if np.isnan(new_value2)==True:
                values_col2[key] = 0
            else:
                values_col2[key] = new_value2
                if values_col2[key] > threshold:
                    values_col3[key] = 1
        except KeyError as e:
            # print('Could not find the simple ID belonging to complex ID {}; value set to None'.format(key))
            values_col2[key] = 0

    #check for failing road segments. count number of times

    #Now the format of simple_ids_per_complex_id is: {(u,v,k) : 'G_fid_simple}
    nx.set_edge_attributes(G,values_col1,value_col1)
    nx.set_edge_attributes(G,values_col2,'Underlying_avg_depth')
    nx.set_edge_attributes(G,values_col3,'analysis')

    #check
    return G, count


def multi_link_od_matrix(G, InputDict, crs=4326):
    """
    Removes all links that are disrupted by a hazard. It takes
    an Origin/Destination matrix as input and calculates the alternative routes for
    each O/D pair, if links are removed between the fastest route from O to D.

    Arguments:
        graph [networkx graph] = the graph with at least the columns that you use in group en sort
        InputDict [dictionary] = dictionary of input data used for calculating
            the costs for taking alternative routes
    """

    logging.info("----------------------------- {} -----------------------------".format(InputDict['analysis_name']))
    startstart = time.time()

    print(
        "\nYou have chosen the Multi-link Disruption Analysis - to calculate the disruption for an Origin/Destination. You might need to give a bit more input later. Starting to calculate now...\n")

    # initiate variables
    id_name_hazard = None
    weighing = 'time'  # TODO: make this variable

    # load the input files if they are there
    if 'id_name' in InputDict:
        id_name = InputDict['id_name']
    else:
        id_name = 'G_fid_simple'

    if InputDict:
        # there is hazard data available
        if 'ID' in InputDict:
            id_name_hazard = InputDict['ID']

    # not all edges contain the attribute 'geometry' - because of geometry simplification these are streets that are straight and can be computed
    # TODO: check that the right file is selected. Currently the filename is hardcoded. In future situations you would like to have this flexible
    G_hazard_path = Path(InputDict['output'] / (str(InputDict['analysis_name']) + '_G_hazard.gpickle'))
    # G_hazard_path = Path(InputDict['output'] / ('DH_drive_G_hazard.gpickle'))
    # check for G_hazard first (similar to ra2ce.py main script) Hazard intersect can take long.
    if not (G_hazard_path.exists()):
        print('G_hazard does not exist. Hazard intersect starts now')
        # TODO check if this is necessary
        G = add_missing_geoms_graph(G)

        if (id_name_hazard is None) & (len(InputDict) != 0):
            G = hazard_intersect_graph(G, InputDict['hazard_data'], InputDict['hazard_attribute_name'], InputDict['analysis_name'],
                                       agg=InputDict['hazard_aggregation'])
        path = Path(InputDict['output'] / (str(InputDict['analysis_name']) + '_G_hazard.gpickle'))
        nx.write_gpickle(G, path, protocol=4)
        print(path, 'saved')
    else:
        print('G_hazard already exists, uses the existing one!: {}'.format(G_hazard_path))
        G = nx.read_gpickle(G_hazard_path)

    # Add the origin/destination nodes to the network
    ods = read_OD_files(InputDict['origin_shp'], InputDict['o_names'],
                        InputDict['destination_shp'], InputDict['d_names'],
                        InputDict['id_name_origin_destination'], crs)

    od_pairs_path = Path(InputDict['output'] / (str(InputDict['analysis_name']) + '_G_hazard_od_pairs.shp'))

    # check for G_hazard first (similar to ra2ce.py main script) Hazard intersect can take long.
    if not (od_pairs_path.exists()):
        # todo: after check put save_shp back to False
        ods = create_OD_pairs(ods, G, id_name, InputDict=InputDict, save_shp=True, save_pickle=True)
    else:
        print('OD_pairs already exists, uses the existing one!: {}'.format(od_pairs_path))
        # ods = nx.read_gpickle(od_pairs_path)
        ods = gpd.read_file(od_pairs_path)
        ods.rename(columns={'geometry':'OD'},inplace=True)

    od_graph_path = Path(InputDict['output'] / (str(InputDict['analysis_name']) + '_G_hazard_OD.gpickle'))
    if not (od_graph_path.exists()):
        # todo: after check put save_shp back to False
        G = add_od_nodes(G, ods, id_name, name=InputDict['analysis_name'], InputDict=InputDict, save_shp=True, save_pickle=True)
    else:
        print('G_hazard_OD_pairs already exists, uses the existing one!: {}'.format(od_graph_path))
        G = nx.read_gpickle(od_graph_path)



    if weighing == 'time':
        # not yet possible for input with shapefiles, except when a max speed attribute is attached to the shapefile
        # calculate the time it takes per road segment
        avg_speeds = calc_avg_speed(G, 'highway', save_csv=True, save_path=os.path.join(InputDict['output'], 'avg_speeds_{}.csv'.format(InputDict['analysis_name'])))
        avg_speeds = pd.read_csv(os.path.join(InputDict['output'], 'avg_speeds_{}.csv'.format(InputDict['analysis_name'])))
        if len(avg_speeds.loc[avg_speeds['avg_speed'] == 0]) > 0:
            logging.info("An average speed of 50 is used in locations where the maximum speed limit is 0 in OSM data.")
            avg_speeds.loc[avg_speeds['avg_speed'] == 0, 'avg_speed'] = 50  # this is assumed
        G = assign_avg_speed(G, avg_speeds, 'highway')

        # make a time value of seconds, length of road streches is in meters
        for u, v, k, edata in G.edges.data(keys=True):
            hours = (edata['length'] / 1000) / edata['avgspeed']
            G[u][v][k][weighing] = hours * 3600

    # Calculate the preferred routes
    pref_routes = preferred_routes_od(G, weighing, id_name, ods, crs, InputDict, shortest_route=False,
                                      save_shp=True, save_pickle=True,
                                      file_output=InputDict['output'], name=InputDict['analysis_name'])

    # origin_closest_dest, other = find_closest_node_attr(G, InputDict['id_name_origin_destination'], weighing, o_name, d_name)
    # pref_routes, base_graph = calc_pref_routes_closest_dest(G, base_graph, weighing, crs, InputDict['id_name_origin_destination'], idName,
    #                                                         origin_closest_dest, neighborhoods, nr_people_name,
    #                                                         factor_hospital)
    #
    # # Find the distance of the routes to the hospitals, see if those hospitals are flooded or not
    # base_graph, hospitals, list_hospital_flooded, pp_no_delay, pp_delayed, extra_dist_meters, extra_miles = \
    #     calc_routes_closest_dest(G, base_graph, origin_closest_dest, pref_routes, weighing, InputDict['origin_shp'],
    #                              InputDict['destination_shp'], InputDict['id_name_origin_destination'], wd,
    #                              InputDict['hazard_threshold'])

# , factor_hospital, nr_people_name

    # Calculate the criticality
    gdf = criticality_multi_link_hazard_OD(G, pref_routes, weighing, InputDict['hazard_attribute_name'][0],
                                           InputDict['hazard_threshold'], crs)

    # save graph
    save_name = os.path.join(InputDict['output'], '{}_criticality.shp'.format(InputDict['analysis_name']))
    gdf_to_shp(gdf, save_name)

    print("\nThe shapefile with calculated criticality can be found here:\n{}".format(save_name))

    end = time.time()
    logging.info("Full analysis [multi_link_od_matrix]: {}".format(timer(startstart, end)))

def multi_link_od_matrix_rws(G, InputDict, save_file=True, crs=4326):
    """
    Removes all links that are disrupted by a hazard. It takes
    an Origin/Destination matrix as input and calculates the alternative routes for
    each O/D pair, if links are removed between the fastest route from O to D.

    Arguments:
        graph [networkx graph] = the graph with at least the columns that you use in group en sort
        InputDict [dictionary] = dictionary of input data used for calculating
            the costs for taking alternative routes

    Created by Margreet van Marle and Frederique de Groen
    """

    logging.info("----------------------------- {} -----------------------------".format(InputDict['analysis_name']))
    startstart = time.time()

    print(
        "\nYou have chosen the Multi-link Disruption Analysis - to calculate the disruption for an Origin/Destination. You might need to give a bit more input later. Starting to calculate now...\n")

    # initiate variables
    id_name_hazard = None
    weighing = 'time'  # TODO: make this variable

    # load the input files if they are there
    if 'id_name' in InputDict:
        id_name = InputDict['id_name']
    else:
        id_name = 'osmid'

    if InputDict:
        # there is hazard data available
        if 'ID' in InputDict:
            id_name_hazard = InputDict['ID']

    # not all edges contain the attribute 'geometry' - because of geometry simplification these are streets that are straight and can be computed
    # TODO check if this is necessary
    G = add_missing_geoms_graph(G)


    # Add the origin/destination nodes to the network
    G2=copy.deepcopy(G)
    print('G2 copy created')
    edges_remove = [e for e in G2.edges.data(keys=True) if InputDict['hazard_attribute_name'][0] in e[-1]]
    #remove all edges that are still functioning. bridges are removed in criticality_multi_link_hazard_OD
    edges_remove = [e for e in edges_remove if (e[-1][InputDict['hazard_attribute_name'][0]] <= InputDict['hazard_threshold'])]
    G2.remove_edges_from(edges_remove)


    #save G2 to check out nodes and edges that were removed
    if save_file:
        graph_to_shp(G2, Path(InputDict['output']/(str(InputDict['analysis_name'])+'_G2_edges.shp')),
                     Path(InputDict['output']/(str(InputDict['analysis_name'])+'_G2_nodes.shp')))
        print(Path(InputDict['output']/(str(InputDict['analysis_name'])+'_G2_edges.shp')))

    e_id = [edata['G_fid_simple'] for u,v,edata in G2.edges(data=True)]
    ods=[]
    os=[]
    ds=[]
    for subg in list(nx.weakly_connected_component_subgraphs(G2)):
            if subg.number_of_edges() == 0:
                continue  # not a cycle
            else:
        #todo add the island every origin and destinat ion is connected voor edges remove
                #find outer nodes that define origins and destinations
                o = [x for x in subg.nodes() if subg.in_degree(x)==0 and subg.out_degree(x)>=1]
                d = [x for x in subg.nodes() if subg.out_degree(x)==0 and subg.in_degree(x)>=1]
                od=[(x,y) for x in o for y in d]
                if len(od)>=1:
                    ods.extend(od)
                    os.extend(o)
                    ds.extend(d)
    print('these nodes are the origins: ', os)
    print('these nodes are the destinations: ', ds)

    #create empty dataframe with origins and list with corresponding edges, used for the coupling of traffic data later on.
    list_id = pd.DataFrame(index=list(os), columns=['G_fid_simple'])
    for oo in os:
        G.nodes[oo]['od_id'] = str(oo)
        list_id['G_fid_simple'][oo] = [data['G_fid_simple'] for u, v, data in G.in_edges(oo, data=True)]
    for dd in ds:
        G.nodes[dd]['od_id'] = str(dd)

    # Calculate the preferred routes.
    pref_routes = preferred_routes_rws(G, weighing, id_name, ods, crs, InputDict, shortest_route=False,
                                      save_shp=True, save_pickle=True,
                                      file_output=InputDict['output'], name=InputDict['analysis_name'])

    # origin_closest_dest, other = find_closest_node_attr(G, 'od_id', weighing, o_name, d_name)
    # pref_routes, base_graph = calc_pref_routes_closest_dest(G, base_graph, weighing, crs, od_id, idName,
    #                                                         origin_closest_dest, neighborhoods, nr_people_name,
    #                                                         factor_hospital)

    # TODO: add nodes so this to_undirected action is not necessary!
    G=G.to_undirected()

    # Calculate the criticality
    gdf = criticality_multi_link_hazard_OD_RWS(G, pref_routes, weighing, 'analysis',
                                           InputDict['hazard_threshold'],InputDict, crs)

    #save pickle
    gdf.to_pickle(InputDict['output']/'criticality'/(str(InputDict['analysis_name']) + '_criticality.p'))

    # save graph
    save_name = InputDict['output']/'criticality'/(str(InputDict['analysis_name'])+'_criticality_emb.shp')
    gdf_to_shp(gdf, save_name)

    print("\nThe shapefile with calculated criticality can be found here:\n{}".format(save_name))

    end = time.time()
    logging.info("Full analysis [multi_link_od_matrix]: {}".format(timer(startstart, end)))
    print('Done')
    return gdf, list_id

def preferred_routes_rws(graph, weighing_name, idName, od, crs, hazard_data, shortest_route, save_shp, save_pickle,
                        file_output, name):
    """Computes the quikest/shortest routes between Origin/Destination nodes
    Args:
        graph [networkX graph]: graph for which the preferred routes should be computed
        weighing_name [string]: name of the attribute to weigh with (e.g. length, time, etc.)
        name [string]: name of the analysis
        file_output [string]: path to folder where the geodataframe and/or pickle should be stored
        save_shp [bool]: True/False to save the OD pairs to a shapefile in the folder 'file_output'
        crs [int]: CRS EPSG, like 4326
    Returns:
        pref_routes [geodataframe]: dataframe with all O/D pairs, their preferred route and the weighing of that route
    """
    # dataframe to save the preferred routes
    pref_routes = gpd.GeoDataFrame(columns=['o_node', 'd_node', 'origin', 'destination',
                                            'pref_path', weighing_name, 'match_ids', 'geometry'],
                                   geometry='geometry', crs={'init': 'epsg:{}'.format(crs)})



    # create the routes between all OD pairs
    for o, d in od:
        if nx.has_path(graph, o, d):
            # calculate the length of the preferred route
            pref_route = nx.dijkstra_path_length(graph, o, d, weight=weighing_name)

            # save preferred route nodes
            pref_nodes = nx.dijkstra_path(graph, o, d, weight=weighing_name)

            # found out which edges belong to the preferred path
            edgesinpath = list(zip(pref_nodes[0:], pref_nodes[1:]))

            pref_edges = []
            match_list = []
            for u, v in edgesinpath:
                # get edge with the lowest weighing if there are multiple edges that connect u and v
                edge_key = sorted(graph[u][v], key=lambda x: graph[u][v][x][weighing_name])[0]
                if 'geometry' in graph[u][v][edge_key]:
                    pref_edges.append(graph[u][v][edge_key]['geometry'])
                else:
                    pref_edges.append(LineString([graph.nodes[u]['geometry'], graph.nodes[v]['geometry']]))
                if idName in graph[u][v][edge_key]:
                    match_list.append(graph[u][v][edge_key][idName])

            # compile the road segments into one geometry
            pref_edges = MultiLineString(pref_edges)
            pref_routes = pref_routes.append({'o_node': o, 'd_node': d, 'origin': str(o),
                                              'destination': str(d), 'pref_path': pref_nodes,
                                              weighing_name: pref_route, 'match_ids': match_list,
                                              'geometry': pref_edges}, ignore_index=True)
    #to select top 3 nearest
    if shortest_route:
        pref_routes = pref_routes.loc[pref_routes.sort_values(weighing_name).groupby('o_node').head(3).index]

    # # intersect the origin and destination nodes with the hazard map (now only geotiff possible)
    # pref_routes['d_disrupt'] = None
    # pref_routes['o_disrupt'] = None
    # pref_routes['d_{}'.format(hazard_data['attribute_name'][0])] = None
    # pref_routes['o_{}'.format(hazard_data['attribute_name'][0])] = None
    # src = rasterio.open(hazard_data['path'][0])
    # for i in range(len(pref_routes.index)):
    #     dest = graph.nodes[int(pref_routes.d_node.iloc[i])]['geometry']
    #     if (src.bounds.left < dest.coords[0][0] < src.bounds.right) and (
    #         src.bounds.bottom < dest.coords[0][1] < src.bounds.top):
    #         hzrd = [x.item(0) for x in src.sample(dest.coords)][0]
    #         pref_routes['d_{}'.format(hazard_data['attribute_name'][0])].iloc[i] = hzrd
    #         if hzrd > hazard_data['threshold']:
    #             pref_routes['d_disrupt'].iloc[i] = 'disrupted'
    #         else:
    #             pref_routes['d_disrupt'].iloc[i] = 'not disrupted'
    #     else:
    #         pref_routes['d_{}'.format(hazard_data['attribute_name'][0])].iloc[i] = 0
    #         pref_routes['d_disrupt'].iloc[i] = 'unknown'
    #     orig = graph.nodes[int(pref_routes.o_node.iloc[i])]['geometry']
    #     if (src.bounds.left < orig.coords[0][0] < src.bounds.right) and (
    #         src.bounds.bottom < orig.coords[0][1] < src.bounds.top):
    #         hzrd = [x.item(0) for x in src.sample(orig.coords)][0]
    #         pref_routes['o_{}'.format(hazard_data['attribute_name'][0])].iloc[i] = hzrd
    #         if hzrd > hazard_data['threshold']:
    #             pref_routes['o_disrupt'].iloc[i] = 'disrupted'
    #         else:
    #             pref_routes['o_disrupt'].iloc[i] = 'not disrupted'
    #     else:
    #         pref_routes['o_{}'.format(hazard_data['attribute_name'][0])].iloc[i] = 0
    #         pref_routes['o_disrupt'].iloc[i] = 'unknown'

    if save_shp:
        gdf_to_shp(pref_routes, os.path.join(file_output, '{}_pref_routes.shp'.format(name)))
        print("Preferred routes saved to {}".format(os.path.join(file_output, '{}_pref_routes.shp'.format(name))))

    if save_pickle:
        pref_routes.to_pickle(file_output / 'pref_routes' / (str(name) + '_pref_routes.p'))
        print('Preferred routes saved to: ', str(file_output / 'pref_routes' / (str(name) + '_pref_routes.p')))

    return pref_routes



# HELPER FUNCTIONS
def timer(start, end):
    hours, rem = divmod(end - start, 3600)
    minutes, seconds = divmod(rem, 60)
    return "{:0>2}:{:0>2}:{:05.2f}".format(int(hours), int(minutes), seconds)


def graph_to_shp(G, edge_shp, node_shp):
    """Takes in a networkx graph object and outputs shapefiles at the paths indicated by edge_shp and node_shp

    Arguments:

        G []: networkx graph object to be converted

        edge_shp [str]: output path including extension for edges shapefile

        node_shp [str]: output path including extension for nodes shapefile

    Returns:

        None

    """
    # now only multidigraphs and graphs are used
    if type(G) == nx.classes.graph.Graph:
        G = nx.MultiGraph(G)

    nodes, edges = osmnx.graph_to_gdfs(G)

    dfs = [edges, nodes]
    for df in dfs:
        for col in df.columns:
            if df[col].dtype == np_object and col != df.geometry.name:
                df[col] = df[col].astype(str)

    print('\nSaving nodes as shapefile: {}'.format(node_shp))
    print('\nSaving edges as shapefile: {}'.format(edge_shp))

    nodes.to_file(node_shp, driver='ESRI Shapefile', encoding='utf-8')
    edges.to_file(edge_shp, driver='ESRI Shapefile', encoding='utf-8')


def df_to_shp(df, crs, file_path):
    """
    Saves a dataframe with a geometry column to a shapefile. Here use for saving
    the results of an analysis to a shapefile.

    Arguments:
        df [DataFrame]: dataframe with a geometry column
        crs [string]: the CRS EPSG (e.g. 4326)
        file_path [string]: the full path to where the shapefile must be saved.
            Ends with '.shp'
    """

    # clean up file before writing
    df = df[~df['geometry'].isnull()]

    for col in df.columns:
        if df[col].dtype == np_object and col != df.geometry.name:
            df[col] = df[col].astype(str)

    gdf = gpd.GeoDataFrame(df, geometry=df.geometry, crs=crs)
    gdf.to_file(file_path)


# get the length of the lines in meters
def line_length(line):
    """Calculate length of a line in kilometers, given in geographic coordinates.
    Args:
        line: a shapely LineString object with WGS 84 coordinates
    Returns:
        Length of line in m
    """
    # check if the projection is EPSG:4326
    distance.VincentyDistance.ELLIPSOID = 'WGS-84'
    try:
        # Swap shapely (lonlat) to geopy (latlon) points
        latlon = lambda lonlat: (lonlat[1], lonlat[0])
        if isinstance(line, LineString):
            total_length = sum(distance.distance(latlon(a), latlon(b)).meters for (a, b) in pairs(line.coords))
        elif isinstance(line, MultiLineString):
            total_length = sum(
                [sum(distance.distance(latlon(a), latlon(b)).meters for (a, b) in pairs(l.coords)) for l in line])
        else:
            warnings.warn("Something went wrong while calculating the length of the road stretches.")
    except:
        warnings.warn(
            "The CRS is not EPSG:4326. Quit the analysis, reproject the layer to EPSG:4326 and try again to run the tool.")
    return round(total_length, 0)


# Iterate over a list in overlapping pairs without wrap-around.
def pairs(lst):
    """
    Args:
        lst: an iterable/list

    Returns:
        Yields a pair of consecutive elements (lst[k], lst[k+1]) of lst. Last
        call yields the last two elements.

    Example:
        lst = [4, 7, 11, 2]
        pairs(lst) yields (4, 7), (7, 11), (11, 2)

    Source:
        https://stackoverflow.com/questions/1257413/1257446#1257446
    """
    i = iter(lst)
    prev = next(i)
    for item in i:
        yield prev, item
        prev = item


# Delete duplicate points
def delete_duplicates(all_points):
    points = [point for point in all_points]
    uniquepoints = []
    for point in points:
        if not any(p.almost_equals(point) for p in uniquepoints):
            uniquepoints.append(point)
    return uniquepoints


def cut_lines(lines_gdf, nodes, idName, tolerance):
    """Cuts lines at the nodes, with a certain tolerance
    """
    max_id = max(lines_gdf[idName])
    list_columns = list(lines_gdf.columns.values)
    for rem in ['geometry', 'length', idName]:
        list_columns.remove(rem)

    to_add = gpd.GeoDataFrame(columns=list(lines_gdf.columns.values))
    to_remove = []
    to_iterate = zip(list(lines_gdf.index.values), list(lines_gdf[idName]), list(lines_gdf['geometry']))

    for idx, i, line in to_iterate:
        if isinstance(line, LineString):
            points_to_cut = [pnt for pnt in list(nodes['geometry']) if
                             (line.distance(pnt) < tolerance) & (line.boundary.distance(pnt) > tolerance)]
        elif isinstance(line, MultiLineString):
            points_to_cut = []
            for ln in line:
                points_to_cut.extend([pnt for pnt in list(nodes['geometry']) if
                                      (ln.distance(pnt) < tolerance) & (ln.boundary.distance(pnt) > tolerance)])

        if points_to_cut:
            # cut lines
            newlines = split_line_with_points(line=line, points=points_to_cut)
            for j, newline in enumerate(newlines):
                if j == 0:
                    # copy and remove the row of the original linestring
                    properties_dict = lines_gdf.loc[lines_gdf[idName] == i][list_columns].to_dict(orient='records')[0]

                    # add the data with one part of the cut linestring
                    properties_dict.update({idName: i, 'geometry': newline, 'length': line_length(newline)})
                    to_add = to_add.append(properties_dict, ignore_index=True)
                    logging.info("added line segment to {} {}".format(idName, i))
                else:
                    properties_dict = lines_gdf.loc[lines_gdf[idName] == i][list_columns].to_dict(orient='records')[0]
                    properties_dict.update({idName: max_id + 1, 'geometry': newline, 'length': line_length(newline)})
                    to_add = to_add.append(properties_dict, ignore_index=True)
                    logging.info("added line segment to {} {}".format(idName, i))
                    max_id += 1

            # remove the original linestring that has been cut
            to_remove.append(idx)

    lines_gdf.drop(to_remove, inplace=True)
    lines_gdf = lines_gdf.append(to_add, ignore_index=True)
    return lines_gdf


def split_line_with_points(line, points):
    """Splits a line string in several segments considering a list of points.
    """
    segments = []
    current_line = line

    # make a list of points and its distance to the start to sort them from small to large distance
    list_dist = [current_line.project(pnt) for pnt in points]
    list_dist.sort()

    for d in list_dist:
        # cut the line at a distance d
        seg, current_line = cut(current_line, d)
        if seg:
            segments.append(seg)
    segments.append(current_line)
    return segments


def cut(line, distance):
    # Cuts a line in two at a distance from its starting point
    # This is taken from shapely manual
    if (distance <= 0.0) | (distance >= line.length):
        return [None, LineString(line)]

    if isinstance(line, LineString):
        coords = list(line.coords)
        for i, p in enumerate(coords):
            pd = line.project(Point(p))
            if pd == distance:
                return [
                    LineString(coords[:i + 1]),
                    LineString(coords[i:])]
            if pd > distance:
                cp = line.interpolate(distance)
                # check if the LineString contains an Z-value, if so, remove
                # only use XY because otherwise the snapping functionality doesn't work
                return [LineString([xy[0:2] for xy in coords[:i]] + [(cp.x, cp.y)]),
                        LineString([(cp.x, cp.y)] + [xy[0:2] for xy in coords[i:]])]
    elif isinstance(line, MultiLineString):
        for ln in line:
            coords = list(ln.coords)
            for i, p in enumerate(coords):
                pd = ln.project(Point(p))
                if pd == distance:
                    return [
                        LineString(coords[:i + 1]),
                        LineString(coords[i:])]
                if pd > distance:
                    cp = ln.interpolate(distance)
                    # check if the LineString contains an Z-value, if so, remove
                    # only use XY because otherwise the snapping functionality doesn't work
                    return [LineString([xy[0:2] for xy in coords[:i]] + [(cp.x, cp.y)]),
                            LineString([(cp.x, cp.y)] + [xy[0:2] for xy in coords[i:]])]


# def prune_lines(lines, prune_threshold):
#
#    # create nodes on intersections and on lines that should be snapped
#    inters = []
#    for line1,line2 in itertools.combinations(lines, 2):
#        # Make points at intersections of lines
#        if line1.intersects(line2):
#            inter = line1.intersection(line2)
#            if "Point" == inter.type:
#                segments1 = split_line_with_points(line1, [inter])
#                segments2 = split_line_with_points(line2, [inter])
#
#
#            elif "MultiPoint" == inter.type:
#                inters.extend([pt for pt in inter])
#            elif "MultiLineString" == inter.type:
#                multiLine = [line for line in inter]
#                first_coords = multiLine[0].coords[0]
#                last_coords = multiLine[len(multiLine)-1].coords[1]
#                inters.append(Point(first_coords[0], first_coords[1]))
#                inters.append(Point(last_coords[0], last_coords[1]))
#            elif "GeometryCollection" == inter.type:
#                for geom in inter:
#                    if "Point" == geom.type:
#                        inters.append(geom)
#                    elif "MultiPoint" == geom.type:
#                        inters.extend([pt for pt in geom])
#                    elif "MultiLineString" == geom.type:
#                        multiLine = [line for line in geom]
#                        first_coords = multiLine[0].coords[0]
#                        last_coords = multiLine[len(multiLine)-1].coords[1]
#                        inters.append(Point(first_coords[0], first_coords[1]))
#                        inters.append(Point(last_coords[0], last_coords[1]))
#    # prune lines
#    if pruning:
#        # from m to km
#        prune_threshold = prune_threshold / 1000
#
#        # remove the segments shorter than prune_threshold meter
#        new_lines = [line for line in new_lines if line.length > prune_threshold]


def join_nodes_edges(gdf_nodes, gdf_edges, idName):
    """Creates tuples from the adjecent nodes and add as column in geodataframe.
    Args:
        gdf_nodes [geodataframe]: geodataframe of the nodes of a graph
        gdf_edges [geodataframe]: geodataframe of the nodes of a graph
    Returns:
        result [geodataframe]: geodataframe of adjecent nodes from edges
    """
    # list of the edges that are not topographically correct
    incorrect_edges = []

    # add node attributes to edges
    gdf = gpd.sjoin(gdf_edges, gdf_nodes, how="left", op='intersects')

    tuples_df = pd.DataFrame({'node_A': [], 'node_B': []})

    for edge in gdf[idName].unique():
        node_tuple = gdf.loc[gdf[idName] == edge, 'node_fid']
        if len(node_tuple) > 2:
            # if there are more than 2 nodes intersecting the linestring, choose the ones at the endpoints
            # todo: check this section!!
            incorrect_edges.append(edge)
            line_nodes = gdf.loc[gdf[idName] == edge, 'geometry'].iloc[0]
            if isinstance(line_nodes, LineString):
                point_coords = [Point(line_nodes.coords[0]), Point(
                    line_nodes.coords[-1])]  # these are the two endpoints of the linestring - we take these as nodes
                n = gdf_nodes[gdf_nodes['node_fid'].isin(node_tuple)]  # get the geometries of the nodes
                special_tuple = ()
                for point in list(n.geometry):
                    if any(p.equals(point) for p in point_coords):
                        special_tuple = special_tuple + (n.loc[n.geometry == point, 'node_fid'].iloc[
                                                             0],)  # find the node id of the two endpoints of the linestring
                warnings.warn(
                    "More than two nodes are intersecting with edge {}: {}. The nodes that are intersecting are: {}".format(
                        idName, edge, list(n['node_fid'])))
                try:
                    tuples_df = tuples_df.append({'node_A': special_tuple[0], 'node_B': special_tuple[1]},
                                                 ignore_index=True)
                except IndexError as e:
                    warnings.warn("Only one node can be found for edge with {} {}: {}".format(idName, edge, e))
            elif isinstance(line_nodes, MultiLineString):
                special_tuple = ()
                for ln in line_nodes:
                    point_coords = [Point(ln.coords[0]), Point(
                        ln.coords[-1])]  # these are the two endpoints of the linestring - we take these as nodes
                    n = gdf_nodes[gdf_nodes['node_fid'].isin(node_tuple)]  # get the geometries of the nodes
                    for point in list(n.geometry):
                        if any(p.equals(point) for p in point_coords):
                            special_tuple = special_tuple + (n.loc[n.geometry == point, 'node_fid'].iloc[
                                                                 0],)  # find the node id of the two endpoints of the linestring
                    warnings.warn(
                        "More than two nodes are intersecting with edge {}: {}. The nodes that are intersecting are: {}".format(
                            idName, edge, list(n['node_fid'])))
                try:
                    tuples_df = tuples_df.append({'node_A': special_tuple[0], 'node_B': special_tuple[1]},
                                                 ignore_index=True)
                except IndexError as e:
                    warnings.warn("Only one node can be found for edge with {} {}: {}".format(idName, edge, e))
        elif len(node_tuple) < 2:
            # somehow the geopandas sjoin did not find any nodes on this edge, but there are so look for them
            node_a = [i for i, xy in zip(gdf_nodes.node_fid, gdf_nodes.geometry) if xy.almost_equals(
                Point(list(gdf_edges.loc[gdf_edges[idName] == edge].iloc[0].geometry.coords)[0]))]
            node_b = [i for i, xy in zip(gdf_nodes.node_fid, gdf_nodes.geometry) if xy.almost_equals(
                Point(list(gdf_edges.loc[gdf_edges[idName] == edge].iloc[0].geometry.coords)[-1]))]
            tuples_df = tuples_df.append(
                {'node_A': gdf_nodes.loc[gdf_nodes['node_fid'] == node_a[0], 'node_fid'].iloc[0],
                 'node_B': gdf_nodes.loc[gdf_nodes['node_fid'] == node_b[0], 'node_fid'].iloc[0]}, ignore_index=True)
        elif len(node_tuple) == 2:
            # this is what you want for a good network
            tuples_df = tuples_df.append({'node_A': node_tuple.iloc[0], 'node_B': node_tuple.iloc[1]},
                                         ignore_index=True)
        else:
            warnings.warn("Something went wrong..")

    if incorrect_edges:
        warnings.warn('More than 2 nodes intersecting edges {}'.format(incorrect_edges))

    result = gpd.GeoDataFrame(pd.concat([gdf_edges, tuples_df], axis=1))

    # drop all columns without values
    if result.columns[result.isnull().all()].any():
        to_drop = result.columns[result.isnull().all()]
        result.drop(to_drop, axis=1, inplace=True)

    return result


def graph_from_gdf(gdf, gdf_nodes, name='network'):
    # create a Graph object
    G = nx.MultiGraph(crs=gdf.crs)

    # create nodes on the Graph
    for index, row in gdf_nodes.iterrows():
        c = {'ID': row.node_fid, 'geometry': row.geometry}
        G.add_node(row.node_fid, **c)

    # create edges on top of the nodes
    for index, row in gdf.iterrows():
        dict_row = row.to_dict()
        G.add_edge(u_for_edge=dict_row['node_A'], v_for_edge=dict_row['node_B'], **dict_row)

    # make a name
    G.graph['name'] = name

    return G


def vertices_from_lines(lines, listIds):
    """Return dict of with values: unique vertices from list of LineStrings.
    keys: index of LineString in original list
    From shapely_tools:
        @author: Dirk Eilander (dirk.eilander@deltares.nl)
        Adjusted 15-10-2019: Frederique de Groen (frederique.degroen@deltares.nl)
        Build on library from https://github.com/ojdo/python-tools/blob/master/shapelytools.py
    """
    vertices_dict = {}
    for i, line in zip(listIds, lines):
        if isinstance(line, LineString):
            vertices_dict[i] = [Point(p) for p in set(list(line.coords))]
        if isinstance(line, MultiLineString):
            all_vertices = []
            for each_line in line:
                all_vertices.extend([Point(p) for p in set(list(each_line.coords))])
            vertices_dict[i] = all_vertices
    return vertices_dict


def find_isolated_endpoints(linesIds, lines):
    """Find endpoints of lines that don't touch another line.

    Args:
        lines: a list of LineStrings or a MultiLineString

    Returns:
        A list of line end Points that don't touch any other line of lines

    From shapely_tools:
        @author: Dirk Eilander (dirk.eilander@deltares.nl)
        Adjusted 15-10-2019: Frederique de Groen (frederique.degroen@deltares.nl)
        Build on library from https://github.com/ojdo/python-tools/blob/master/shapelytools.py
    """
    isolated_endpoints = []
    for i, id_line in enumerate(zip(linesIds, lines)):
        ids, line = id_line
        other_lines = lines[:i] + lines[i + 1:]
        for q in [0, -1]:
            if isinstance(line, LineString):
                endpoint = Point(line.coords[q])
                if any(endpoint.touches(another_line)
                       for another_line in other_lines):
                    continue
                else:
                    isolated_endpoints.append((ids, endpoint))
            elif isinstance(line, MultiLineString):
                endpoints = [Point(l.coords[q]) for l in line]
                for endpnt in endpoints:
                    if any(endpnt.touches(another_line)
                           for another_line in other_lines):
                        continue
                    else:
                        isolated_endpoints.append((ids, endpoint))
    return isolated_endpoints


def getKeysByValue(dictOfElements, value):
    """
    https://thispointer.com/python-how-to-find-keys-by-value-in-dictionary/
    """
    theKey = 0
    listOfItems = dictOfElements.items()
    for item in listOfItems:
        if value in item[1]:
            theKey = item[0]
    return theKey


def nearest_neighbor_within(search_points, spatial_index, point, max_distance):
    """Find nearest point among others up to a maximum distance.

    Args:
        others: a dict with keys: index of line, values: list of Points or a MultiPoint
        point: a Point
        max_distance: maximum distance to search for the nearest neighbor

    Returns:
        A shapely Point if one is within max_distance, None otherwise

    From shapely_tools:
        @author: Dirk Eilander (dirk.eilander@deltares.nl)
        Adjusted 15-10-2019: Frederique de Groen (frederique.degroen@deltares.nl)
        Build on library from https://github.com/ojdo/python-tools/blob/master/shapelytools.py
    """

    # the point from where you are searching
    if isinstance(max_distance, pd.Series):
        max_distance = max_distance[0]
    geometry_buffered = point.buffer(max_distance)

    # expand bounds by max_distance in all directions
    bounds = [a + b * max_distance for a, b in zip(geometry_buffered.bounds, [-1, -1, 1, 1])]

    # get list of fids where bounding boxes intersect
    interesting_points = [int(i) for i in spatial_index.intersection(geometry_buffered.bounds)]

    if not interesting_points:
        closest_point = None
    elif len(interesting_points) == 1:
        closest_point = search_points[interesting_points[0]]
    else:
        points_list = [search_points[ip] for ip in interesting_points]
        distance_list = [(p, point.distance(p)) for p in points_list if point.distance(p) > 0]
        closest_point, closest_distance = min(distance_list, key=lambda t: t[1])

    return closest_point


def snap_endpoints_lines(lines_gdf, max_dist, idName, tolerance=1e-7):
    """Snap endpoints of lines with endpoints or vertices of other lines
    if they are at most max_dist apart. Choose the closest endpoint or vertice.

    Args:
        lines: a list of LineStrings or a MultiLineString
        max_dist: maximum distance two endpoints may be joined together

    From shapely_tools:
        @author: Dirk Eilander (dirk.eilander@deltares.nl)
        Adjusted 15-10-2019: Frederique de Groen (frederique.degroen@deltares.nl)
        Build on library from https://github.com/ojdo/python-tools/blob/master/shapelytools.py
    """
    max_id = max(lines_gdf[idName])

    # initialize snapped lines with list of original lines
    # snapping points is a MultiPoint object of all vertices
    snapped_lines = [line for line in list(lines_gdf['geometry'])]
    snapping_dict = vertices_from_lines(snapped_lines, list(lines_gdf[idName]))

    # isolated endpoints are being snapped to the closest vertex
    isolated_endpoints = find_isolated_endpoints(list(lines_gdf[idName]), snapped_lines)

    print("Number of isolated endpoints (points that probably need to be snapped): {} ".format(len(isolated_endpoints)))
    print("Snapping lines.. Follow the progress:")
    # only snap isolated endpoints within max_dist of another vertice / endpoint
    for i, isolated_endpoint in enumerate(isolated_endpoints):
        ids, endpoint = isolated_endpoint

        # create a list of the vertices that are not the line's own vertices
        points_without_linepoints = [value for key, value in snapping_dict.items() if key != ids]

        # create list of all points to search in
        all_vertices = [p for sublist in points_without_linepoints for p in sublist]

        # create an empty spatial index object to search in
        idx = rtree.index.Index()

        # populate the spatial index
        for j, pnt in enumerate(all_vertices):
            idx.insert(j, pnt.bounds)

        # find all vertices within a radius of max_distance as possible
        # choose closest vertice and line the vertice lays on
        target = nearest_neighbor_within(all_vertices, idx, endpoint, max_dist)

        # draw a progress bar
        drawProgressBar(i / len(isolated_endpoints))

        # do nothing if the target point is further away from the endpoint than max_dist
        # or if they are at the same location
        if not target:
            continue

        # check if the line does not yet exist
        new_line = LineString([(target.x, target.y), (endpoint.x, endpoint.y)])
        if not any(new_line.equals(another_line) for another_line in snapped_lines):
            if new_line.length > 0:
                lines_gdf = lines_gdf.append({idName: max_id + 1, 'geometry': new_line, 'length': line_length(new_line),
                                              'to_analyse': 0}, ignore_index=True)
                max_id += 1

    # TODO: remove any lines that are overlapping?

    return lines_gdf


def drawProgressBar(percent, barLen=20):
    """
    https://stackoverflow.com/questions/3002085/python-to-print-out-status-bar-and-percentage
    """
    # percent float from 0 to 1.
    sys.stdout.write("\r")
    sys.stdout.write("[{:<{}}] {:.0f}%".format("=" * int(barLen * percent), barLen, percent * 100))
    sys.stdout.flush()


def read_OD_files(origin_paths, origin_names, destination_paths, destination_names, od_id, crs_):
    origin = gpd.GeoDataFrame(columns=[od_id, 'o_id', 'geometry'], crs=crs_)
    destination = gpd.GeoDataFrame(columns=[od_id, 'd_id', 'geometry'], crs=crs_)

    if isinstance(origin_paths, str):
        origin_paths = [origin_paths]
    if isinstance(destination_paths, str):
        destination_paths = [destination_paths]
    if isinstance(origin_names, str):
        origin_names = [origin_names]
    if isinstance(destination_names, str):
        destination_names = [destination_names]

    for op, on in zip(origin_paths, origin_names):
        origin_new = gpd.read_file(op, crs=crs_)
        origin_new = origin_new[[od_id, 'geometry']]
        origin_new['o_id'] = on + "_" + origin_new[od_id].astype(str)
        origin = origin.append(origin_new, ignore_index=True, sort=False)

    for dp, dn in zip(destination_paths, destination_names):
        destination_new = gpd.read_file(dp, crs=crs_)
        destination_new = destination_new[[od_id, 'geometry']]
        destination_new['d_id'] = dn + "_" + destination_new[od_id].astype(str)
        destination = destination.append(destination_new, ignore_index=True, sort=False)

    od = pd.concat([origin, destination], sort=False)
    od[od_id] = list(range(len(od.index)))

    return od


def create_OD_pairs(od, graph, id_name, name=None, InputDict=None, save_shp=False, save_pickle=False):
    """Get centroids of the selected NUTS-3 regions and gets closest vertice on the road of a graph.
    Args:
        origins [string]: file path of shapefile of the NUTS-3 regions in Europe
        country_codes [list of string(s)]: list of NUTS country codes
        graph [networkX graph]: graph of the roads of a or multiple European countries
        name [string]: name of the analysis
        file_output [string]: path to folder where the geodataframe and/or pickle should be stored
        save_shp [bool]: True/False to save the OD pairs to a shapefile in the folder 'file_output'
        save_pickle [bool]: True/False to save the OD pairs to a pickle in the folder 'file_output'
    Returns:
        centroids: dataframe of vertices closest to the centroids of the selected NUTS-3 regions
    """

    # find closest vertice of road network to centroid
    # create dictionary of the roads geometries
    edge_list = [e for e in graph.edges.data() if 'geometry' in e[-1]]
    vertices_dict = {}
    for line in edge_list:
        vertices_dict[(line[0], line[1])] = [Point(p) for p in set(list(line[-1]['geometry'].coords))]

    # create list of all points to search in
    all_vertices = [p for sublist in list(vertices_dict.values()) for p in sublist]

    # create an empty spatial index object to search in
    idx = rtree.index.Index()

    # populate the spatial index
    for i, pnt in enumerate(all_vertices):
        idx.insert(i, pnt.bounds)

    od = find_closest_vertice(od, idx, all_vertices, vertices_dict, edge_list, id_name)

    # save OD points
    # if save_shp:
    #     gdf_to_shp(od, os.path.join(file_output, name + "_od_pairs.shp"))
    #     print("Saved OD pairs to shapefiles: {} and {}".format(os.path.join(file_output, name + "_od_pairs.shp")))
    # if save_pickle:
    #     pickle.dump(od, open(os.path.join(file_output, name + "_od_pairs.p"), 'wb'))
    #     print("Saved OD pairs to pickles: {} and {}".format(os.path.join(file_output, name + "_od_pairs.p")))
    if save_shp:
        path = Path(InputDict['output'] / (str(InputDict['analysis_name']) + '_G_hazard_OD_pairs.shp'))
        gdf_to_shp(od, path)
        print("\nThe shapefile with OD pairs can be found here:\n{}".format(path))
    if save_pickle:
        path = Path(InputDict['output'] / (str(InputDict['analysis_name']) + '_G_hazard_od_pairs.gpickle'))
        nx.write_gpickle(od, path, protocol=4)
        print("\nThe pickle with OD pairs can be found here:\n{}".format(path))
    return od


def find_closest_vertice(origins_destinations, spatial_idx, search_vertices, vertices_dict, edge_list, id_name):
    ODs = []
    match_ids = []
    for i, c in enumerate(origins_destinations['geometry']):
        # find the closest vertice and line the vertice lays on
        target = list(spatial_idx.nearest(c.bounds))

        # draw a progress bar
        drawProgressBar(i / len(origins_destinations))

        # do nothing if the target point is further away from the endpoint than max_dist
        # or if they are at the same location
        if not target:
            continue

        points_list = [search_vertices[ip] for ip in target]

        # check on which road this point lays
        road_i = getKeysByValue(vertices_dict, points_list[0])
        match_ids.append([i[-1][id_name] for i in edge_list if (road_i[0] == i[0]) and (road_i[1] == i[1])][0])

        # save in list
        ODs.append(points_list[0])

    # save in dataframe
    origins_destinations['OD'] = ODs
    origins_destinations['match_ids'] = match_ids

    # save the road vertices closest to the centroids as geometry, delete the centroid geometry
    origins_destinations = gpd.GeoDataFrame(origins_destinations, geometry='OD')
    origins_destinations = origins_destinations.drop(columns=['geometry'])

    return origins_destinations

def find_new_nearest_vertice(edge_list,graph, od, id_name, match_OD,i):
    vertices_dict = {}
    for line in edge_list:
        vertices_dict[(line[0], line[1])] = [Point(p) for p in set(list(line[-1]['geometry'].coords))]
    all_vertices = [p for sublist in list(vertices_dict.values()) for p in sublist]
    # create an empty spatial index object to search in
    idx = rtree.index.Index()
    # populate the spatial index
    for j, pnt in enumerate(all_vertices):
        idx.insert(j, pnt.bounds)
    # find the closest vertice and line the vertice lays on
    target = list(idx.nearest(match_OD.coords[0]))
    match_OD = [all_vertices[ip] for ip in target]
    match_OD = match_OD[0]
    all_matches = [am for am in edge_list if match_OD.coords[0] in [p for p in set(list(am[-1]['geometry'].coords))]]
    return all_matches,match_OD

def add_od_nodes(graph, od, id_name, name=None, InputDict=None, save_shp=False, save_pickle=False):
    """From a geodataframe of vertices on a graph, adds nodes on that graph.
    Args:
        graph [networkX graph]: graph of the roads of a or multiple European countries
        centroids [geodataframe]: geodataframe from the function 'create_OD_pairs'
        name [string]: name of the analysis
        file_output [string]: path to folder where the geodataframe and/or pickle should be stored
        save_shp [bool]: True/False to save the OD pairs to a shapefile in the folder 'file_output'
        save_pickle [bool]: True/False to save the OD pairs to a pickle in the folder 'file_output'
    Returns:
        graph: networkX graph with the nodes closes to the centroids of the NUTS-3 regions added.
        The ID's of the added nodes are adding in number from the highest ID of the nodes in the original graph.
    """
    # To make it easier to match the match_ids potential lists are turned into strings (or strings to strings)
    od['match_ids'] = od['match_ids'].astype(str)

    # Check the highest node id, to add on that
    max_node_id = max([n for n in graph.nodes()])
    print('adding OD nodes to graph...')

    for i in range(len(od.index)):
        drawProgressBar(i / len(od.index))
        # the vertice on the edge that is closest to the origin/destination point
        match_OD = od.iloc[i]['OD']
        # Check which roads belong to the centroids closest vertices
        all_matches = [e for e in graph.edges(data=True, keys=True) if str(e[-1][id_name]) == od.iloc[i]['match_ids']]
        if len(all_matches) > 1:
            # all_matches = [am for am in all_matches if match_OD in [(Point(p) for p in set(list(am[-1]['geometry'].coords)))]]
            all_matches = [am for am in all_matches if match_OD.coords[0] in [p for p in set(list(am[-1]['geometry'].coords))]]
            if len(all_matches) == 0: #created to find nearest vertice when a new edge has already been created
                #todo build this in in the other def find nearest vertice
                edge_list = [e for e in graph.edges(data=True, keys=True) if
                             str(e[-1][id_name]) == od.iloc[i]['match_ids']]
                all_matches,match_OD = find_new_nearest_vertice(edge_list,graph, od, id_name, match_OD, i)
        if len(all_matches) == 1:
            if [am for am in all_matches if match_OD.coords[0] in [p for p in set(list(am[-1]['geometry'].coords))]] == []:
                edge_list = [e for e in graph.edges(data=True, keys=True) if
                             str(e[-1][id_name]) == od.iloc[i]['match_ids']]
                all_matches,match_OD = find_new_nearest_vertice(edge_list,graph, od, id_name, match_OD, i)
        if len(all_matches) == 0: #when the edge does not exist anymore in the adjusted graph. look over the full graph and find the nearest vertice
            edge_list = [e for e in graph.edges.data() if 'geometry' in e[-1]]
            all_matches, match_OD = find_new_nearest_vertice(edge_list, graph, od, id_name, match_OD, i)
        m = all_matches[0]

        if 'geometry' in m[-1]:
            match_geom = m[-1]['geometry']
            if len(m)==3:
                match_edge = m[0],m[1],0
            else:
                match_edge = m[:3]
            match_name = od.iloc[i]['o_id']
            if match_name == 'nan':
                match_name = np.nan #convert string nans to np.nans to be able to differentiate between origins and destinations in the next step.
            if not match_name == match_name:
                # match_name is nan, the point is not an origin but a destination
                match_name = od.iloc[i]['d_id']
            new_lines = split_line_with_points(match_geom, [match_OD])
            if len(new_lines) == 2:
                line1, line2 = new_lines
            else:
                # if the vertice is at the end of the road; you don't have to add a new node
                # but do add a new attribute to the node

                if (graph.nodes[match_edge[0]]['geometry'].coords[0][1] == match_OD.coords[0][1]) & (
                    graph.nodes[match_edge[0]]['geometry'].coords[0][0] == match_OD.coords[0][0]):
                    if 'od_id' in graph.nodes[match_edge[0]]:
                        # the node already has a origin/destination attribute
                        graph.nodes[match_edge[0]]['od_id'] = graph.nodes[match_edge[0]]['od_id'] + ',' + match_name
                    else:
                        graph.nodes[match_edge[0]]['od_id'] = match_name
                elif (graph.nodes[match_edge[1]]['geometry'].coords[0][1] == match_OD.coords[0][1]) & (
                    graph.nodes[match_edge[1]]['geometry'].coords[0][0] == match_OD.coords[0][0]):
                    if 'od_id' in graph.nodes[match_edge[1]]:
                        graph.nodes[match_edge[1]]['od_id'] = graph.nodes[match_edge[1]]['od_id'] + ',' + match_name
                    else:
                        graph.nodes[match_edge[1]]['od_id'] = match_name
                elif ((graph.nodes[match_edge[0]]['geometry'].coords[0][1] == match_OD.coords[0][1]) & (
                    graph.nodes[match_edge[0]]['geometry'].coords[0][0] == match_OD.coords[0][0]))==False & ((graph.nodes[match_edge[1]]['geometry'].coords[0][1] == match_OD.coords[0][1]) & (
                    graph.nodes[match_edge[1]]['geometry'].coords[0][0] == match_OD.coords[0][0]))==False:
                    print(i)
                    print('continue')
                    continue
                continue
            new_node_id = max_node_id + 1
            max_node_id = new_node_id

            graph.add_node(new_node_id, y=match_OD.coords[0][1], x=match_OD.coords[0][0], geometry=match_OD,
                           od_id=match_name)

            edge_data = graph.edges[match_edge]

            # Check which line is connected to which node. There can be 8 different combinations
            #if 'line2' in locals():
            if (graph.nodes[match_edge[0]]['geometry'].coords[0][1] == line2.coords[-1][1]) & (
                graph.nodes[match_edge[0]]['geometry'].coords[0][0] == line2.coords[-1][0]):
                edge_data.update(length=line_length(line2), geometry=line2)
                graph.add_edge(match_edge[0], new_node_id, match_edge[-1], **edge_data)

            if (graph.nodes[match_edge[1]]['geometry'].coords[0][1] == line2.coords[0][1]) & (
                graph.nodes[match_edge[1]]['geometry'].coords[0][0] == line2.coords[0][0]):
                edge_data.update(length=line_length(line2), geometry=line2)
                graph.add_edge(match_edge[1], new_node_id, match_edge[-1], **edge_data)

            if (graph.nodes[match_edge[0]]['geometry'].coords[0][1] == line2.coords[0][1]) & (
                graph.nodes[match_edge[0]]['geometry'].coords[0][0] == line2.coords[0][0]):
                edge_data.update(length=line_length(line2), geometry=line2)
                graph.add_edge(match_edge[0], new_node_id, match_edge[-1], **edge_data)

            if (graph.nodes[match_edge[1]]['geometry'].coords[0][1] == line2.coords[-1][1]) & (
                graph.nodes[match_edge[1]]['geometry'].coords[0][0] == line2.coords[-1][0]):
                edge_data.update(length=line_length(line2), geometry=line2)
                graph.add_edge(match_edge[1], new_node_id, match_edge[-1], **edge_data)

            #if 'line1' in locals():

            if (graph.nodes[match_edge[1]]['geometry'].coords[0][1] == line1.coords[0][1]) & (
                graph.nodes[match_edge[1]]['geometry'].coords[0][0] == line1.coords[0][0]):
                edge_data.update(length=line_length(line1), geometry=line1)
                graph.add_edge(match_edge[1], new_node_id, match_edge[-1], **edge_data)

            if (graph.nodes[match_edge[0]]['geometry'].coords[0][1] == line1.coords[-1][1]) & (
                graph.nodes[match_edge[0]]['geometry'].coords[0][0] == line1.coords[-1][0]):
                edge_data.update(length=line_length(line1), geometry=line1)
                graph.add_edge(match_edge[0], new_node_id, match_edge[-1], **edge_data)

            if (graph.nodes[match_edge[1]]['geometry'].coords[0][1] == line1.coords[-1][1]) & (
                graph.nodes[match_edge[1]]['geometry'].coords[0][0] == line1.coords[-1][0]):
                edge_data.update(length=line_length(line1), geometry=line1)
                graph.add_edge(match_edge[1], new_node_id, match_edge[-1], **edge_data)

            if (graph.nodes[match_edge[0]]['geometry'].coords[0][1] == line1.coords[0][1]) & (
                graph.nodes[match_edge[0]]['geometry'].coords[0][0] == line1.coords[0][0]):
                edge_data.update(length=line_length(line1), geometry=line1)
                graph.add_edge(match_edge[0], new_node_id, match_edge[-1], **edge_data)

            # remove the edge that is split in two
            u, v, k = match_edge
            graph.remove_edge(u, v, k)

    if save_shp:
        path_edges = Path(InputDict['output'] / (str(InputDict['analysis_name']) + '_G_hazard_OD_edges.shp'))
        path_nodes = Path(InputDict['output'] / (str(InputDict['analysis_name']) + '_G_hazard_OD_nodes.shp'))
        graph_to_shp(graph, path_edges,path_nodes)
        print("Saved graph to shapefile in {}".format(path_edges))
    if save_pickle:
        path = Path(InputDict['output'] / (str(InputDict['analysis_name']) + '_G_hazard_OD.gpickle'))
        nx.write_gpickle(graph, path, protocol=4)
        print("Saved graph to pickle in {}".format(path))

    return graph


def preferred_routes_od(graph, weighing_name, idName, od, crs, hazard_data, shortest_route, save_shp, save_pickle,
                        file_output, name):
    """Computes the quikest/shortest routes between Origin/Destination nodes
    Args:
        graph [networkX graph]: graph for which the preferred routes should be computed
        weighing_name [string]: name of the attribute to weigh with (e.g. length, time, etc.)
        name [string]: name of the analysis
        file_output [string]: path to folder where the geodataframe and/or pickle should be stored
        save_shp [bool]: True/False to save the OD pairs to a shapefile in the folder 'file_output'
        crs [int]: CRS EPSG, like 4326
    Returns:
        pref_routes [geodataframe]: dataframe with all O/D pairs, their preferred route and the weighing of that route
    """
    # dataframe to save the preferred routes
    pref_routes = gpd.GeoDataFrame(columns=['o_node', 'd_node', 'origin', 'destination',
                                            'pref_path', weighing_name, 'match_ids', 'geometry'],
                                   geometry='geometry', crs={'init': 'epsg:{}'.format(crs)})
    graph=graph.to_undirected()
    # create list of origin-destination pairs
    od=od.replace('nan', np.nan)
    od_pairs = [(a, b) for a in od.loc[od['o_id'].notnull(), 'o_id'] for b in od.loc[od['d_id'].notnull(), 'd_id']]
    all_nodes = [(n, v['od_id']) for n, v in graph.nodes(data=True) if 'od_id' in v]
    od_nodes = []
    for aa, bb in od_pairs:
        # it is possible that there are multiple origins/destinations at the same 'entry-point' in the road
        od_nodes.append(([(n, n_name) for n, n_name in all_nodes if (n_name == aa) | (aa in n_name)][0],
                         [(n, n_name) for n, n_name in all_nodes if (n_name == bb) | (bb in n_name)][0]))

    # create the routes between all OD pairs
    i=0
    for o, d in od_nodes:
        drawProgressBar(i / len(od_nodes))
        if nx.has_path(graph, o[0], d[0]):
            # calculate the length of the preferred route
            pref_route = nx.dijkstra_path_length(graph, o[0], d[0], weight=weighing_name)

            # save preferred route nodes
            pref_nodes = nx.dijkstra_path(graph, o[0], d[0], weight=weighing_name)

            # found out which edges belong to the preferred path
            edgesinpath = list(zip(pref_nodes[0:], pref_nodes[1:]))

            pref_edges = []
            match_list = []
            for u, v in edgesinpath:
                # get edge with the lowest weighing if there are multiple edges that connect u and v
                edge_key = sorted(graph[u][v], key=lambda x: graph[u][v][x][weighing_name])[0]
                if 'geometry' in graph[u][v][edge_key]:
                    pref_edges.append(graph[u][v][edge_key]['geometry'])
                else:
                    pref_edges.append(LineString([graph.nodes[u]['geometry'], graph.nodes[v]['geometry']]))
                if idName in graph[u][v][edge_key]:
                    match_list.append(graph[u][v][edge_key][idName])

            # compile the road segments into one geometry
            pref_edges = MultiLineString(pref_edges)
            pref_routes = pref_routes.append({'o_node': o[0], 'd_node': d[0], 'origin': o[1],
                                              'destination': d[1], 'pref_path': pref_nodes,
                                              weighing_name: pref_route, 'match_ids': match_list,
                                              'geometry': pref_edges}, ignore_index=True)
            i=i+1

    if shortest_route:
        pref_routes = pref_routes.loc[pref_routes.sort_values(weighing_name).groupby('o_node').head(5).index]

    # intersect the origin and destination nodes with the hazard map (now only geotiff possible)
    pref_routes['d_disrupt'] = None
    pref_routes['o_disrupt'] = None
    pref_routes['d_{}'.format(hazard_data['hazard_attribute_name'][0])] = None
    pref_routes['o_{}'.format(hazard_data['hazard_attribute_name'][0])] = None
    src = rasterio.open(hazard_data['hazard_data'][0])
    for i in range(len(pref_routes.index)):
        dest = graph.nodes[int(pref_routes.d_node.iloc[i])]['geometry']
        if (src.bounds.left < dest.coords[0][0] < src.bounds.right) and (
            src.bounds.bottom < dest.coords[0][1] < src.bounds.top):
            hzrd = [x.item(0) for x in src.sample(dest.coords)][0]
            pref_routes['d_{}'.format(hazard_data['hazard_attribute_name'][0])].iloc[i] = hzrd
            if hzrd > hazard_data['hazard_threshold']:
                pref_routes['d_disrupt'].iloc[i] = 'disrupted'
            else:
                pref_routes['d_disrupt'].iloc[i] = 'not disrupted'
        else:
            pref_routes['d_{}'.format(hazard_data['hazard_attribute_name'][0])].iloc[i] = 0
            pref_routes['d_disrupt'].iloc[i] = 'unknown'
        orig = graph.nodes[int(pref_routes.o_node.iloc[i])]['geometry']
        if (src.bounds.left < orig.coords[0][0] < src.bounds.right) and (
            src.bounds.bottom < orig.coords[0][1] < src.bounds.top):
            hzrd = [x.item(0) for x in src.sample(orig.coords)][0]
            pref_routes['o_{}'.format(hazard_data['hazard_attribute_name'][0])].iloc[i] = hzrd
            if hzrd > hazard_data['hazard_threshold']:
                pref_routes['o_disrupt'].iloc[i] = 'disrupted'
            else:
                pref_routes['o_disrupt'].iloc[i] = 'not disrupted'
        else:
            pref_routes['o_{}'.format(hazard_data['hazard_attribute_name'][0])].iloc[i] = 0
            pref_routes['o_disrupt'].iloc[i] = 'unknown'

    if save_shp:
        gdf_to_shp(pref_routes, os.path.join(file_output, '{}_pref_routes.shp'.format(name)))
        print("Preferred routes saved to {}".format(os.path.join(file_output, '{}_pref_routes.shp'.format(name))))

    if save_pickle:
        pref_routes[['origin', 'destination', 'AoIs', 'pref_path', weighing_name,
                     'match_ids']].to_pickle(os.path.join(file_output, '{}_pref_routes.pkl'.format(name)))
        print("Preferred routes saved to {}".format(os.path.join(file_output, '{}_pref_routes.pkl'.format(name))))

    return pref_routes


def calc_avg_speed(graph, road_type_col_name, save_csv=False, save_path=None, existing_path=None):
    """Calculates the average speed from OSM roads, per road type
    Args:
        graph: NetworkX graph with road types
        road_type_col_name: name of the column which holds the road types ('highway' in OSM)
        save_csv [boolean]: to save a csv or not
        save_path [string]: path to save the csv to
    Returns:
        dataframe with the average road speeds per road type
    """
    if existing_path == None:
        # Create a dataframe of all road types
        exceptions = list(set([str(edata[road_type_col_name]) for u, v, edata in graph.edges.data() if
                               isinstance(edata[road_type_col_name], list)]))
        types = list(set([str(edata[road_type_col_name]) for u, v, edata in graph.edges.data() if
                          isinstance(edata[road_type_col_name], str)]))
        all_road_types = exceptions + types
        df = pd.DataFrame({'road_types': all_road_types, 'avg_speed': 0})

        # calculate average speed
        for i in range(len(df)):
            print(i)
            roadtype = df.road_types[i]
            all_edges = [(u, v, edata['maxspeed'], edata['length']) for u, v, edata in graph.edges.data() if
                         (str(edata[road_type_col_name]) == roadtype) & ('maxspeed' in edata)]
            all_avg = []
            all_l = []
            for u, v, s, l in all_edges:
                if isinstance(s, list):
                    ns = []
                    for ss in s:
                        if not any(c.isalpha() for c in ss) and not (';' in ss) and not ('|' in ss) and not (',' in ss):
                            ns.append(int(ss))
                        elif not any(c.isalpha() for c in ss) and ';' in ss:
                            ns.extend([int(x) for x in ss.split(';') if x.isnumeric()])
                        elif not any(c.isalpha() for c in ss) and '|' in ss:
                            ns.extend([int(x) for x in ss.split('|') if x.isnumeric()])
                        elif not any(c.isalpha() for c in s) and ',' in s:
                            ns.extend([int(x) for x in s.split(',') if x.isnumeric()])
                        elif ' mph' in ss:
                            ns.append(int(ss.split(' mph')[0]) * 1.609344)
                    if len(ns) > 0:
                        ss = sum(ns) / len(ns)
                    else:
                        continue
                elif isinstance(s, str):
                    if not any(c.isalpha() for c in s) and not (';' in s) and not ('|' in s) and not (',' in s):
                        ss = int(s)
                    elif not any(c.isalpha() for c in s) and ';' in s:
                        ss = mean([int(x) for x in s.split(';') if x.isnumeric()])
                    elif not any(c.isalpha() for c in s) and '|' in s:
                        ss = mean([int(x) for x in s.split('|') if x.isnumeric()])
                    elif not any(c.isalpha() for c in s) and ',' in s:
                        ss = mean([int(float(x)) for x in s.split(',')])
                    elif ' mph' in s:
                        ss = int(s.split(' mph')[0]) * 1.609344
                    else:
                        continue
                all_avg.append(ss * l)
                all_l.append(l)
                df.iloc[i, 1] = sum(all_avg) / sum(all_l)

        if save_csv:
            if not save_path.endswith('.csv'):
                save_path = save_path + '.csv'
            df.to_csv(save_path)
            print("Saved the average speeds per road type to: {}".format(save_path))
        return df

    if existing_path:
        if not existing_path.exists():
            print('Average speed file does not exist!: {}'.format(existing_path))

        else:
            print('average speed file already exists, uses the existing one!: {}'.format(existing_path))
            # CONVERT GRAPHS TO GEODATAFRAMES
            df = pd.read_csv(existing_path)
            return df




def assign_avg_speed(graph, avg_road_speed, road_type_col_name, save_path=None, save_shp=False, save_pickle=False):
    """Assigns the average speed to roads in an existing (OSM) graph
    """
    # make a list of strings instead of just a string of the road types column
    avg_road_speed["road_types"] = avg_road_speed["road_types"].astype(str)


    # calculate the average maximum speed per edge and assign the ones that don't have a value
    for u, v, k, edata in graph.edges.data(keys=True):
        road_type = str(edata[road_type_col_name])
        if 'maxspeed' in edata:
            max_speed = edata['maxspeed']
            if isinstance(max_speed, list):
                ns = []
                for ms in max_speed:
                    if not any(c.isalpha() for c in ms) and not (';' in ms) and not ('|' in ms) and not (',' in ms):
                        ns.append(int(ms))
                    elif not any(c.isalpha() for c in ms) and ';' in ms:
                        ns.extend([int(x) for x in ms.split(';') if x.isnumeric()])
                    elif not any(c.isalpha() for c in ms) and '|' in ms:
                        ns.extend([int(x) for x in ms.split('|') if x.isnumeric()])
                    elif not any(c.isalpha() for c in ms) and ',' in ms:
                        ns.extend([int(x) for x in ms.split(',') if x.isnumeric()])
                    elif ' mph' in ms:
                        ns.append(int(ms.split(' mph')[0]) * 1.609344)
                if len(ns) > 0:
                    graph[u][v][k]['avgspeed'] = sum(ns) / len(ns)
                else:
                    graph[u][v][k]['avgspeed'] = \
                    avg_road_speed.loc[avg_road_speed['road_types'] == road_type, 'avg_speed'].iloc[0]
            elif isinstance(max_speed, str):
                if not any(c.isalpha() for c in max_speed) and not (';' in max_speed) and not ('|' in max_speed) and not (',' in max_speed):
                    graph[u][v][k]['avgspeed'] = int(max_speed)
                elif not any(c.isalpha() for c in max_speed) and ';' in max_speed:
                    graph[u][v][k]['avgspeed'] = mean([int(x) for x in max_speed.split(';') if x.isnumeric()])
                elif not any(c.isalpha() for c in max_speed) and '|' in max_speed:
                    graph[u][v][k]['avgspeed'] = mean([int(x) for x in max_speed.split('|') if x.isnumeric()])
                elif not any(c.isalpha() for c in max_speed) and ',' in max_speed:
                    graph[u][v][k]['avgspeed'] = mean([int(float(x)) for x in max_speed.split(',')])
                elif ' mph' in max_speed:
                    graph[u][v][k]['avgspeed'] = int(max_speed.split(' mph')[0]) * 1.609344
                else:
                    graph[u][v][k]['avgspeed'] = \
                    avg_road_speed.loc[avg_road_speed['road_types'] == road_type, 'avg_speed'].iloc[0]
        else:
            if ']' in road_type:
                avg_speed = int([s for r, s in zip(avg_road_speed['road_types'], avg_road_speed['avg_speed']) if
                                 set(road_type[2:-2].split("', '")) == set(r[2:-2].split("', '"))][0])
                graph[u][v][k]['avgspeed'] = avg_speed
            else:
                graph[u][v][k]['avgspeed'] = \
                avg_road_speed.loc[avg_road_speed['road_types'] == road_type, 'avg_speed'].iloc[0]

    if save_shp:
        graph_to_shp(graph, os.path.join(save_path, '_edges.shp'), os.path.join(save_path, '_nodes.shp'))
        print("Saving graph to shapefile in: {}".format(save_path))
    if save_pickle:
        nx.write_gpickle(graph, os.path.join(save_path, 'graph.gpickle'))
        print("Saving graph to pickle: {}".format(os.path.join(save_path, 'graph.gpickle')))

    return graph




def hazard_intersect_graph(graph, hazard, hazard_name, name, agg='max', save_path=r'C:\Users\loure_le\ra2ce\ra2ce\test\output', save_shp=True,
                           save_pickle=False):
    """adds hazard values (flood/earthquake/etc) to the roads in a graph
    Args:
        graph [networkX graph]
        hazard [string]: full path to hazard data
        agg [string]: choose from max, min or mean; when multiple sections of a road
            are overlapping, aggregate the data in this way
    Returns:
        Graph with the added hazard data, when there is no hazard, the values is 0
    """
    # import and append the hazard data
    #TODO: check size of .tif file or whether it runs over all edges.

    for h, hn in zip(hazard, hazard_name):
        if h.endswith('.tif'):
            # GeoTIFF
            src = rasterio.open(h)

            # check which road is overlapping with the flood and append the flood depth to the graph
            for u, v, k, edata in graph.edges.data(keys=True):
                if 'geometry' in edata:
                    # check how long the road stretch is and make a point every other meter
                    nr_points = round(edata['length'])
                    if nr_points == 1:
                        coords_to_check = list(edata['geometry'].boundary)
                    else:
                        coords_to_check = [edata['geometry'].interpolate(i / float(nr_points - 1), normalized=True) for
                                           i in range(nr_points)]
                    crds = []
                    for c in coords_to_check:
                        # check if part of the linestring is inside the flood extent
                        if (src.bounds.left < c.coords[0][0] < src.bounds.right) and (
                            src.bounds.bottom < c.coords[0][1] < src.bounds.top):
                            crds.append(c.coords[0])
                    if crds:
                        # the road lays inside the flood extent
                        if agg == 'max':
                            if (max([x.item(0) for x in src.sample(crds)]) > 999999) | (
                                max([x.item(0) for x in src.sample(crds)]) < -999999):
                                # the road is most probably in the 'no data' area of the raster (usually a very large or small number is used as 'no data' value)
                                graph[u][v][k][hn] = 0
                            else:
                                graph[u][v][k][hn] = max([x.item(0) for x in src.sample(crds)])
                        elif agg == 'min':
                            if (min([x.item(0) for x in src.sample(crds)]) > 999999) | (
                                min([x.item(0) for x in src.sample(crds)]) < -999999):
                                # the road is most probably in the 'no data' area of the raster (usually a very large or small number is used as 'no data' value)
                                graph[u][v][k][hn] = 0
                            else:
                                graph[u][v][k][hn] = min([x.item(0) for x in src.sample(crds)])
                        elif agg == 'mean':
                            if (mean([x.item(0) for x in src.sample(crds)]) > 999999) | (
                                mean([x.item(0) for x in src.sample(crds)]) < -999999):
                                # the road is most probably in the 'no data' area of the raster (usually a very large or small number is used as 'no data' value)
                                graph[u][v][k][hn] = 0
                            else:
                                graph[u][v][k][hn] = mean([x.item(0) for x in src.sample(crds)])
                        else:
                            warnings.warn("No aggregation method is chosen ('max', 'min' or 'mean).")
                    else:
                        graph[u][v][k][hn] = 0
                else:
                    graph[u][v][k][hn] = 0

        elif h.endswith('.shp'):
            # Shapefile
            gdf = gpd.read_file(h)
            spatial_index = gdf.sindex

            for u, v, k, edata in graph.edges.data(keys=True):
                if 'geometry' in edata:
                    possible_matches_index = list(spatial_index.intersection(edata['geometry'].bounds))
                    possible_matches = gdf.iloc[possible_matches_index]
                    precise_matches = possible_matches[possible_matches.intersects(edata['geometry'])]

                    if not precise_matches.empty:
                        if agg == 'max':
                            graph[u][v][k][hn] = precise_matches[hn].max()
                        if agg == 'min':
                            graph[u][v][k][hn] = precise_matches[hn].min()
                        if agg == 'mean':
                            graph[u][v][k][hn] = precise_matches[hn].mean()
                    else:
                        graph[u][v][k][hn] = 0
                else:
                    graph[u][v][k][hn] = 0

        else:
            print(
                "The hazard data is not a GEOTIFF or Shapefile. Please input only these filetypes. Restart the analysis.")

    if save_shp:
        graph_to_shp(graph, os.path.join(save_path, name + '_edges.shp'), os.path.join(save_path, name + '_nodes.shp'))
    if save_pickle:
        nx.write_gpickle(graph, os.path.join(save_path, name + '_graph.gpickle'))

    return graph


def hazard_join_id_shp(roads, HazardDataDict):
    # read and join hazard data
    col_id, col_val = HazardDataDict['hazard_unique_ID'], HazardDataDict['hazard_attribute_name']

    # Fiona is not always loading the geodataframe with all data, so try a few times to get it correct
    attempts = 0
    while attempts < 3:
        try:
            hazard = gpd.read_file(os.path.join(load_config()["paths"]["test_hazard"], HazardDataDict['hazard_data']))
            hazard = hazard[[col_id, col_val]]
            break
        except KeyError:
            attempts += 1
            print("Attempt {} to load hazard data: {}".format(attempts, HazardDataDict['hazard_data']))
    #
    # for i in range(1, len([HazardDataDict['hazard_data']])):  # TODO: make possible to insert multiple hazardmaps
    #     attempts = 0
    #     while attempts < 3:
    #         try:
    #             hazard2 = gpd.read_file(os.path.join(load_config()["paths"]["test_hazard"], HazardDataDict['hazard_data']), encoding="utf-8")
    #             hazard = pd.concat([hazard, hazard2[[col_id, col_val]]], ignore_index=True)
    #             break
    #         except KeyError:
    #             attempts += 1
    #             print("Attempt {} to load hazard data: {}".format(attempts, HazardDataDict['hazard_data']))

    if (col_val in roads) and (col_id in roads):
        hazard = pd.concat([hazard, roads[[col_id, col_val]]], ignore_index=True)

    # Not necessary now
    # hazard.drop_duplicates(inplace=True)

    for ii in hazard[col_id].unique():
        roads.loc[roads[col_id] == ii, "_{}".format(col_val)] = max(hazard.loc[(hazard[col_id] == ii), col_val])

    return roads


# CRITICALITY FUNCTION
def criticality_single_link(graph, IdName, roadUsageData=None, aadtNames=None):
    """Calculates the alternative detour distance for each road segment if that road segement is blocked.
    Args:
        graph [networkX graph]
    Returns:
        dataframe with road criticality measured with alternative distance if you take away one edge at a time
    """

    # now only multigraphs and graphs are used
    if type(graph) == nx.classes.graph.Graph:
        graph = nx.MultiGraph(graph)

    gdf = osmnx.graph_to_gdfs(graph, nodes=False)

    # all edges in the graph will be removed one by one
    list_remove = list(graph.edges.data(keys=True))

    for e_remove in list_remove:
        # edge to remove
        u, v, k, data = e_remove

        the_id = data[IdName]

        # if data['highway'] in attr_list:
        # make a copy of the graph
        H = graph.copy()

        # remove edge
        H.remove_edge(u, v, k)

        # check if the nodes are normally connected
        if nx.has_path(H, u, v):
            # calculate the alternative distance if that edge is unavailable
            alt_dist = nx.dijkstra_path_length(H, u, v, weight='length')

            # append alternative route nodes
            alt_nodes = nx.dijkstra_path(H, u, v)
            alt_nodes = ', '.join(map(str, alt_nodes))  # make it a string to save in shp

            # calculate the difference in distance
            dif_dist = alt_dist - data['length']
        else:
            alt_dist = np.NaN
            alt_nodes = np.NaN
            dif_dist = np.NaN

        # add the values to the geodataframe
        gdf.loc[gdf[IdName] == the_id, 'alt_dist_m'] = alt_dist
        gdf.loc[gdf[IdName] == the_id, 'alt_nodes'] = alt_nodes
        gdf.loc[gdf[IdName] == the_id, 'dif_dist_m'] = dif_dist

    if roadUsageData:
        if 'operating_cost' in roadUsageData.columns:
            # for now: all missing values for the AADT counts are replaced by 0. TODO: change?
            for aadt in aadtNames:
                gdf[aadt].fillna(0, inplace=True)

            # calculate the costs for the routes with and without detour with the AADT
            # detour possible
            operating_costs = np.multiply(
                np.sum(np.multiply(np.array(roadUsageData['operating_cost'].T), np.array(gdf[aadtNames])), axis=1),
                (np.array(gdf['dif_dist_m']) / 1000))
            operating_costs = [round(num, 2) for num in list(operating_costs)]
            gdf['cost_det'] = operating_costs

        if ('daily_loss_disruption' in roadUsageData.columns) & ('passengers_w_driver' in roadUsageData.columns):
            # no detour possible
            daily_loss = np.multiply(np.sum(np.multiply(np.array(roadUsageData['passengers_w_driver'].T),
                                                        np.array(gdf.loc[gdf['dif_dist_m'].isnull()][aadtNames])),
                                            axis=1), roadUsageData['daily_loss_disruption'].iloc[0])
            daily_loss = [round(num, 2) for num in list(daily_loss)]
            gdf.loc[gdf['dif_dist_m'].isnull(), 'cost_no_d'] = daily_loss

    return gdf


def criticality_single_link_osm(graph):
    """
    :param graph: graph on which to run analysis (MultiDiGraph)
    :return: df with dijkstra detour distance and path results
    """
    # TODO look at differences between this function and the criticality_single_link above and merge/remove one
    # create a geodataframe from the graph
    gdf = osmnx.graph_to_gdfs(graph, nodes=False)

    # list for the length of the alternative routes
    alt_dist_list = []
    alt_nodes_list = []
    dif_dist_list = []
    for e_remove in list(graph.edges.data(keys=True)):
        u, v, k, data = e_remove

        # if data['highway'] in attr_list:
        # remove the edge
        graph.remove_edge(u, v, k)

        if nx.has_path(graph, u, v):
            # calculate the alternative distance if that edge is unavailable
            alt_dist = nx.dijkstra_path_length(graph, u, v, weight='length')
            alt_dist_list.append(alt_dist)

            # append alternative route nodes
            alt_nodes = nx.dijkstra_path(graph, u, v)
            alt_nodes_list.append(alt_nodes)

            # calculate the difference in distance
            dif_dist_list.append(alt_dist - data['length'])
        else:
            alt_dist_list.append(np.NaN)
            alt_nodes_list.append(np.NaN)
            dif_dist_list.append(np.NaN)

        # add edge again to the graph
        graph.add_edge(u, v, k, **data)

    # Add the new columns to the geodataframe
    gdf['alt_dist'] = alt_dist_list
    gdf['alt_nodes'] = alt_nodes_list
    gdf['diff_dist'] = dif_dist_list

    return gdf


def common_member(a, b):
    #Determine if two sequences have at least one common member
    #from https://www.geeksforgeeks.org/python-check-two-lists-least-one-element-common/
    a_set = set(a)
    b_set = set(b)
    if (a_set & b_set):
        return True
    else:
        return False

def criticality_single_link_osm_rws(graph,gdf=None):
    """
    :param graph: graph on which to run analysis (MultiDiGraph)
    :return: df with dijkstra detour distance and path results
    """
    # TODO look at differences between this function and the criticality_single_link above and merge/remove one
    # TODO added because of RWS project to test only the main highway network for redundancy

    #### new stuff by kees ####
    import tqdm
    to_filter_out = ['motorway', 'motorway_link']
    graph = graph.to_undirected()
    # create a geodataframe from the graph
    if gdf is None:
        gdf = osmnx.graph_to_gdfs(graph, nodes=False)

    # list for the length of the alternative routes
    alt_dist_list = []
    alt_nodes_list = []
    dif_dist_list = []
    print('Start removing edges')
    for e_remove in tqdm.tqdm(list(graph.edges.data(keys=True))):
        u, v, k, data = e_remove

        data_highway = data['highway'] #can be string or list of strings
        if isinstance(data_highway,str):
            data_highway = [data_highway]

        if common_member(data_highway,to_filter_out):
            #Use common_mber, because in the simplified graph, the highway tag can be a list instead of a string
            #Remove the edge
            graph.remove_edge(u, v, k)

            if nx.has_path(graph, u, v):
                # calculate the alternative distance if that edge is unavailable
                alt_dist = nx.dijkstra_path_length(graph, u, v, weight='length')
                alt_dist_list.append(alt_dist)

                # append alternative route nodes
                alt_nodes = nx.dijkstra_path(graph, u, v)
                alt_nodes_list.append(alt_nodes)

                # #to Use Dijkstra's algoritme for bidirectional networks.
                # alt_dist, alt_nodes =  nx.bidirectional_dijkstra(graph, u, v, weight='length')
                # alt_dist_list.append(alt_dist)
                # alt_nodes_list.append(alt_nodes)
                # calculate the difference in distance
                dif_dist_list.append(alt_dist - data['length'])
            else:
                alt_dist_list.append(np.NaN)
                alt_nodes_list.append(np.NaN)
                dif_dist_list.append(np.NaN)

            # add edge again to the graph
            graph.add_edge(u, v, k, **data)

        else:
            alt_dist_list.append(None)
            alt_nodes_list.append(None)
            dif_dist_list.append(None)

    # Add the new columns to the geodataframe
    gdf['alt_dist'] = alt_dist_list
    gdf['alt_nodes'] = alt_nodes_list
    gdf['diff_dist'] = dif_dist_list

    return gdf


# def criticality_multi_link_hazard_OD(graph, prefRoutes, weighingName, hazardName, threshold, crs_):
#     """Calculates the criticality of origins and destinations"""
#     # Check if the o/d pairs are still connected while some links are disrupted by the hazard(s)
#     gdf = gpd.GeoDataFrame(
#         columns=['disrupted', 'extra_{}'.format(weighingName), 'no detour', 'origin', 'destination', 'odpair',
#                  'd_disrupt', 'o_disrupt', 'd_{}'.format(hazardName), 'o_{}'.format(hazardName), 'geometry'],
#         geometry='geometry', crs={'init': 'epsg:{}'.format(crs_)})
#
#     to_remove = [(e[0], e[1], e[2]) for e in graph.edges.data(keys=True) if (e[-1][hazardName] > threshold) & (
#         'bridge' not in e[-1])]
#     graph.remove_edges_from(to_remove)
#
#     for ii in range(len(prefRoutes.index)):
#         o, d = prefRoutes.iloc[ii][['o_node', 'd_node']]
#         o = int(o)
#         d = int(d)
#
#         extra_time = np.NaN
#
#         # check if the nodes are still connected
#         if nx.has_path(graph, o, d):
#             # calculate the alternative distance if that edge is unavailable
#             alt_route = nx.dijkstra_path_length(graph, o, d, weight=weighingName)
#
#             # save preferred route nodes
#             pref_nodes = nx.dijkstra_path(graph, o, d, weight=weighingName)
#
#             # subtract the length/time of the optimal route from the alternative route
#             extra_time = alt_route - prefRoutes.iloc[ii][weighingName]
#
#             if prefRoutes.iloc[ii][weighingName] != alt_route:
#                 # the alternative route is different from the optimal route
#                 disrupted = 1
#                 detour = "alt_route"
#                 # found out which edges belong to the preferred path
#                 edgesinpath = list(zip(pref_nodes[0:], pref_nodes[1:]))
#
#                 pref_edges = []
#                 for u, v in edgesinpath:
#                     # get edge with the lowest weighing if there are multiple edges that connect u and v
#                     edge_key = sorted(graph[u][v], key=lambda x: graph[u][v][x][weighingName])[0]
#                     if 'geometry' in graph[u][v][edge_key]:
#                         pref_edges.append(graph[u][v][edge_key]['geometry'])
#                     else:
#                         pref_edges.append(LineString([graph.nodes[u]['geometry'], graph.nodes[v]['geometry']]))
#
#                 # compile the road segments into one geometry
#                 pref_edges = MultiLineString(pref_edges)
#             else:
#                 # the alternative route is the same as the optimal route
#                 disrupted = 0
#                 detour = "same"
#                 pref_edges = prefRoutes.iloc[ii]['geometry']
#         else:
#             # append to calculation dataframe
#             disrupted = 1
#             detour = "no_detour"
#             pref_edges = prefRoutes.iloc[ii]['geometry']
#
#         gdf = gdf.append({'disrupted': disrupted, 'extra_{}'.format(weighingName): extra_time, 'no detour': detour,
#                           'origin': str(prefRoutes.iloc[ii]['origin']),
#                           'destination': str(prefRoutes.iloc[ii]['destination']),
#                           'odpair': str(prefRoutes.iloc[ii]['origin']) + ' to ' + str(
#                               prefRoutes.iloc[ii]['destination']),
#                           #TODO: change for RWS
#                           # 'd_disrupt': prefRoutes.iloc[ii]['d_disrupt'],
#                           # 'o_disrupt': prefRoutes.iloc[ii]['o_disrupt'],
#                           # 'd_{}'.format(hazardName): prefRoutes.iloc[ii]['d_{}'.format(hazardName)],
#                           # 'o_{}'.format(hazardName): prefRoutes.iloc[ii]['o_{}'.format(hazardName)],
#                           'geometry': pref_edges}, ignore_index=True)
#
#     return gdf


def criticality_multi_link_hazard_OD(graph, prefRoutes, weighingName, hazardName, threshold, crs_):
    """Calculates the criticality of origins and destinations"""
    # Check if the o/d pairs are still connected while some links are disrupted by the hazard(s)
    gdf = gpd.GeoDataFrame(
        columns=['disrupted', 'extra_{}'.format(weighingName), 'no detour', 'origin', 'destination', 'odpair',
                 'd_disrupt', 'o_disrupt', 'd_{}'.format(hazardName), 'o_{}'.format(hazardName), 'geometry'],
        geometry='geometry', crs={'init': 'epsg:{}'.format(crs_)})

    to_remove = [(e[0], e[1], e[2]) for e in graph.edges.data(keys=True) if (e[-1][hazardName] > threshold) & ('bridge' not in e[-1])]
    # to_remove = [(e[0], e[1], e[2]) for e in graph.edges.data(keys=True) if (e[-1][hazardName] > threshold)]
    graph.remove_edges_from(to_remove)

    for ii in range(len(prefRoutes.index)):
        o, d = prefRoutes.iloc[ii][['o_node', 'd_node']]
        o = int(o)
        d = int(d)

        extra_time = np.NaN

        # check if the nodes are still connected
        if nx.has_path(graph, o, d):
            # calculate the alternative distance if that edge is unavailable
            alt_route = nx.dijkstra_path_length(graph, o, d, weight=weighingName)

            # save preferred route nodes
            pref_nodes = nx.dijkstra_path(graph, o, d, weight=weighingName)

            # subtract the length/time of the optimal route from the alternative route
            extra_time = alt_route - float(prefRoutes.iloc[ii][weighingName])
            print(extra_time)
            if prefRoutes.iloc[ii][weighingName] != alt_route:
                # the alternative route is different from the optimal route
                print('yes')
                disrupted = 1
                detour = "alt_route"
                # found out which edges belong to the preferred path
                edgesinpath = list(zip(pref_nodes[0:], pref_nodes[1:]))

                pref_edges = []
                for u, v in edgesinpath:
                    # get edge with the lowest weighing if there are multiple edges that connect u and v
                    edge_key = sorted(graph[u][v], key=lambda x: graph[u][v][x][weighingName])[0]
                    if 'geometry' in graph[u][v][edge_key]:
                        pref_edges.append(graph[u][v][edge_key]['geometry'])
                    else:
                        pref_edges.append(LineString([graph.nodes[u]['geometry'], graph.nodes[v]['geometry']]))

                # compile the road segments into one geometry
                pref_edges = MultiLineString(pref_edges)
            else:
                # the alternative route is the same as the optimal route
                disrupted = 0
                detour = "same"
                pref_edges = prefRoutes.iloc[ii]['geometry']
        else:
            # append to calculation dataframe
            disrupted = 1
            detour = "no_detour"
            pref_edges = prefRoutes.iloc[ii]['geometry']

        gdf = gdf.append({'disrupted': disrupted, 'extra_{}'.format(weighingName): extra_time, 'no detour': detour,
                          'origin': str(prefRoutes.iloc[ii]['origin']),
                          'destination': str(prefRoutes.iloc[ii]['destination']),
                          'odpair': str(prefRoutes.iloc[ii]['origin']) + ' to ' + str(
                              prefRoutes.iloc[ii]['destination']),
                          #TODO: change for RWS
                          # 'd_disrupt': prefRoutes.iloc[ii]['d_disrupt'],
                          # 'o_disrupt': prefRoutes.iloc[ii]['o_disrupt'],
                          # 'd_{}'.format(hazardName): prefRoutes.iloc[ii]['d_{}'.format(hazardName)],
                          # 'o_{}'.format(hazardName): prefRoutes.iloc[ii]['o_{}'.format(hazardName)],
                          'geometry': pref_edges}, ignore_index=True)

    return gdf

def criticality_multi_link_hazard_OD_RWS(graph, prefRoutes, weighingName, hazardName, threshold, InputDict, crs_):
    """Calculates the criticality of origins and destinations"""
    # Check if the o/d pairs are still connected while some links are disrupted by the hazard(s)
    gdf = gpd.GeoDataFrame(
        columns=['disrupted', 'extra_{}'.format(weighingName), 'no detour', 'origin', 'destination', 'odpair',
                 'd_disrupt', 'o_disrupt', 'd_{}'.format(hazardName), 'o_{}'.format(hazardName), 'geometry'],
        geometry='geometry', crs={'init': 'epsg:{}'.format(crs_)})

    to_remove = [(e[0], e[1], e[2]) for e in graph.edges.data(keys=True) if (e[-1][hazardName] > threshold)]
    graph.remove_edges_from(to_remove)

    to_remove2 = [(e[0], e[1], e[2]) for e in graph.edges.data(keys=True) if (e[-1]['Underlying_avg_depth'] > threshold)]
    graph.remove_edges_from(to_remove2)

    # graph_to_shp(graph, Path(InputDict['output']/(str(InputDict['analysis_name'])+'_G3_edges.shp')),
    #              Path(InputDict['output']/(str(InputDict['analysis_name'])+'_G3_nodes.shp')))

    for ii in range(len(prefRoutes.index)):
        o, d = prefRoutes.iloc[ii][['o_node', 'd_node']]
        o = int(o)
        d = int(d)

        extra_time = np.NaN

        # check if the nodes are still connected
        if nx.has_path(graph, o, d):
            # calculate the alternative distance if that edge is unavailable
            alt_route = nx.dijkstra_path_length(graph, o, d, weight=weighingName)

            # save preferred route nodes
            pref_nodes = nx.dijkstra_path(graph, o, d, weight=weighingName)

            # subtract the length/time of the optimal route from the alternative route
            extra_time = alt_route - prefRoutes.iloc[ii][weighingName]
            #put negative values to
            if extra_time < 0:
                extra_time = np.nan

            if prefRoutes.iloc[ii][weighingName] != alt_route:
                # the alternative route is different from the optimal route
                disrupted = 1
                detour = "alt_route"
                # found out which edges belong to the preferred path
                edgesinpath = list(zip(pref_nodes[0:], pref_nodes[1:]))

                pref_edges = []
                for u, v in edgesinpath:
                    # get edge with the lowest weighing if there are multiple edges that connect u and v
                    edge_key = sorted(graph[u][v], key=lambda x: graph[u][v][x][weighingName])[0]
                    if 'geometry' in graph[u][v][edge_key]:
                        pref_edges.append(graph[u][v][edge_key]['geometry'])
                    else:
                        pref_edges.append(LineString([graph.nodes[u]['geometry'], graph.nodes[v]['geometry']]))

                # compile the road segments into one geometry
                pref_edges = MultiLineString(pref_edges)
            else:
                # the alternative route is the same as the optimal route
                disrupted = 0
                detour = "same"
                pref_edges = prefRoutes.iloc[ii]['geometry']
        else:
            # append to calculation dataframe
            disrupted = 1
            detour = "no_detour"
            pref_edges = prefRoutes.iloc[ii]['geometry']

        gdf = gdf.append({'disrupted': disrupted, 'extra_{}'.format(weighingName): extra_time, 'no detour': detour,
                          'origin': str(prefRoutes.iloc[ii]['origin']),
                          'destination': str(prefRoutes.iloc[ii]['destination']),
                          'odpair': str(prefRoutes.iloc[ii]['origin']) + ' to ' + str(
                              prefRoutes.iloc[ii]['destination']),
                          #TODO: change for RWS
                          # 'd_disrupt': prefRoutes.iloc[ii]['d_disrupt'],
                          # 'o_disrupt': prefRoutes.iloc[ii]['o_disrupt'],
                          # 'd_{}'.format(hazardName): prefRoutes.iloc[ii]['d_{}'.format(hazardName)],
                          # 'o_{}'.format(hazardName): prefRoutes.iloc[ii]['o_{}'.format(hazardName)],
                          'geometry': pref_edges}, ignore_index=True)

    return gdf


def criticality_multi_link_hazard(graph, attribute_name, min_threshold, idName):
    """
    The function removes all links of a variable that have a minimum value
    of min_threshold. For each link it calculates the alternative path, af
    any available. This function only removes one group at the time and saves the data from removing that group.

    Arguments:
        graph [networkx graph] = the graph with at least the columns that you use in group en sort
        attribute_name [string] = name of the attribute that indicates whether a road segment should be removed
        min_threshold [numeric] = the minimum value of the attribute by which the roads should be removed
    Returns:
        gdf [geopandas dataframe]
    """
    # now only multigraphs and graphs are used
    if type(graph) == nx.classes.graph.Graph:
        graph = nx.MultiGraph(graph)

    # Create a geodataframe from the full graph
    gdf = osmnx.graph_to_gdfs(graph, nodes=False)
    gdf[idName] = gdf[idName].astype(str)

    # Check if there is only one or more hazards
    if (isinstance(attribute_name, list)) & (len(attribute_name) == 1):
        attribute_name = attribute_name[0]
    elif (isinstance(attribute_name, list)) & (len(attribute_name) > 1):
        warnings.warn("This feature (multiple hazard criticality calculation) is not yet implemented.")

    # Create the edgelist that consist of edges that should be removed
    edges_remove = [e for e in graph.edges.data(keys=True) if attribute_name in e[-1]]
    edges_remove = [e for e in edges_remove if (e[-1][attribute_name] > min_threshold) & ('bridge' not in e[-1])]

    graph.remove_edges_from(edges_remove)

    # dataframe for saving the calculations of the alternative routes
    df_calculated = pd.DataFrame(columns=['u', 'v', idName, 'alt_dist', 'alt_nodes', 'connected'])

    for i, edges in enumerate(edges_remove):
        u, v, k, edata = edges

        # check if the nodes are still connected
        if nx.has_path(graph, u, v):
            # calculate the alternative distance if that edge is unavailable
            alt_dist = nx.dijkstra_path_length(graph, u, v, weight='length')

            # save alternative route nodes
            alt_nodes = nx.dijkstra_path(graph, u, v)

            # append to calculation dataframe
            df_calculated = df_calculated.append({'u': u, 'v': v, idName: str(edata[idName]), 'alt_dist': alt_dist,
                                                  'alt_nodes': alt_nodes, 'connected': 1}, ignore_index=True)
        else:
            # append to calculation dataframe
            df_calculated = df_calculated.append({'u': u, 'v': v, idName: str(edata[idName]), 'alt_dist': np.NaN,
                                                  'alt_nodes': np.NaN, 'connected': 0}, ignore_index=True)

    # Merge the dataframes
    gdf = gdf.merge(df_calculated, how='left', on=['u', 'v', idName])

    # calculate the difference in distance
    gdf['diff_dist'] = [dist - length if dist == dist else np.NaN for (dist, length) in
                        zip(gdf['alt_dist'], gdf['length'])]

    return gdf


def gdf_to_shp(gdf, result_shp):
    """Takes in a geodataframe object and outputs shapefiles at the paths indicated by edge_shp and node_shp

    Arguments:
        gdf [geodataframe]: geodataframe object to be converted
        edge_shp [str]: output path including extension for edges shapefile
        node_shp [str]: output path including extension for nodes shapefile
    Returns:
        None
    """
    for col in gdf.columns:
        if gdf[col].dtype == np_object and col != gdf.geometry.name:
            gdf[col] = gdf[col].astype(str)

    gdf.to_file(result_shp, driver='ESRI Shapefile', encoding='utf-8')


def add_missing_geoms_graph(graph, geom_name='geometry'):
    # Not all nodes have geometry attributed (some only x and y coordinates) so add a geometry columns
    nodes_without_geom = [n[0] for n in graph.nodes(data=True) if geom_name not in n[-1]]
    for nd in nodes_without_geom:
        graph.nodes[nd][geom_name] = Point(graph.nodes[nd]['x'], graph.nodes[nd]['y'])

    edges_without_geom = [e for e in graph.edges.data(keys=True) if geom_name not in e[-1]]
    for ed in edges_without_geom:
        graph[ed[0]][ed[1]][ed[2]][geom_name] = LineString(
            [graph.nodes[ed[0]][geom_name], graph.nodes[ed[1]][geom_name]])

    return graph

def find_closest_node_attr(H, keyName, weighingName, originLabelContains, destLabelContains):
    """Find the closest destination node with a certain attribute from all origin nodes

    Returns:
        originClosestDest [list of tuples]: list of the origin and destination node id and node name from the routes that are found
        list_no_path [list of tuples]: list of the origin and destination node id and node name from the origins/nodes that do not have a route between them
    """
    H.add_node('special', speciallabel='special')

    special_edges = []
    for n, ndat in H.nodes.data():
        if keyName in ndat:
            if destLabelContains in ndat[keyName]:
                special_edges.append((n, 'special', {weighingName: 0}))

    H.add_edges_from(special_edges)

    list_no_path = []
    for n, ndat in H.nodes.data():
        if keyName in ndat:
            if originLabelContains in ndat[keyName]:
                if nx.has_path(H, n, 'special'):
                    path = nx.shortest_path(H, source=n, target='special', weight=weighingName)
                    ndat['closest'] = path[-2]  # Closest node with destLabelContains in keyName
                else:
                    list_no_path.append((n, ndat[keyName]))

    originClosestDest = [((nn[0], nn[-1][keyName]), (nn[-1]['closest'], H.nodes[nn[-1]['closest']][keyName])) for nn in H.nodes.data() if 'closest' in nn[-1]]
    return originClosestDest, list_no_path


def calc_pref_routes_closest_dest(graph, base_graph, weighing, crs, od_id, idName, origin_closest_dest, origins):
    # dataframe to save the preferred routes
    pref_routes = gpd.GeoDataFrame(columns=['o_node', 'd_node', 'origin', 'destination',
                                            'pref_path', weighing, 'match_ids', 'pop2020', 'patients', 'tot_miles', 'geometry'],
                                   geometry='geometry', crs='epsg:{}'.format(crs))

    # find the optimal route without (hazard) disruption
    for o, d in origin_closest_dest:
        # calculate the length of the preferred route
        pref_route = nx.dijkstra_path_length(graph, o[0], d[0], weight=weighing)

        # save preferred route nodes
        pref_nodes = nx.dijkstra_path(graph, o[0], d[0], weight=weighing)

        # found out which edges belong to the preferred path
        edgesinpath = list(zip(pref_nodes[0:], pref_nodes[1:]))

        # Find the number of people per neighborhood
        # nr_people_per_route_total = origins.loc[origins[od_id] == int(o[1].split('_')[-1]), nr_people_name].iloc[0]
        # nr_patients_per_route = nr_people_per_route_total * factor_hospital

        pref_edges = []
        match_list = []
        length_list = []
        for u, v in edgesinpath:
            # get edge with the lowest weighing if there are multiple edges that connect u and v
            edge_key = sorted(graph[u][v], key=lambda x: graph[u][v][x][weighing])[0]
            if 'geometry' in graph[u][v][edge_key]:
                pref_edges.append(graph[u][v][edge_key]['geometry'])
            else:
                pref_edges.append(LineString([graph.nodes[u]['geometry'], graph.nodes[v]['geometry']]))
            if idName in graph[u][v][edge_key]:
                match_list.append(graph[u][v][edge_key][idName])
            if 'length' in graph[u][v][edge_key]:
                length_list.append(graph[u][v][edge_key]['length'])

            # Add the number of people that need hospital care, to the road segments. For now, each road segment in a route
            # gets attributed all the people that are taking that route.
            # base_graph[u][v][edge_key]['P_pref'] = base_graph[u][v][edge_key]['P_pref'] + nr_patients_per_route

        # compile the road segments into one geometry
        pref_edges = MultiLineString(pref_edges)
        pref_routes = pref_routes.append({'o_node': o[0], 'd_node': d[0], 'origin': o[1],
                                          'destination': d[1], 'pref_path': pref_nodes,
                                          weighing: pref_route, 'match_ids': match_list,
                                          'tot_miles': sum(length_list) / 1609, 'geometry': pref_edges}, ignore_index=True)
        # 'pop2020': nr_people_per_route_total, 'patients': nr_patients_per_route,

    return pref_routes, base_graph


def calc_routes_closest_dest(graph, base_graph, list_closest, pref_routes, weighing, origin, dest, od_id, wd, threshold_hospitals):
    # , factor_hospital, nr_people_name
    pp_no_delay = [0]
    pp_delayed = [0]
    extra_weights = [0]
    extra_miles_total = [0]
    list_hospital_flooded = []

    # find the optimal route with hazard disruption
    for o, d in list_closest:
        # Check if the hospital that is accessed, is flooded
        if dest.loc[dest[od_id] == int(d[1].split('_')[-1]), wd[:-2] + 'WD'].iloc[0] > threshold_hospitals:
            list_hospital_flooded.append((o,d))
            continue

        # calculate the length of the preferred route
        alt_route = nx.dijkstra_path_length(graph, o[0], d[0], weight=weighing)

        # save preferred route nodes
        alt_nodes = nx.dijkstra_path(graph, o[0], d[0], weight=weighing)

        # Find the number of people per neighborhood
        # nr_people_per_route_total = origin.loc[origin[od_id] == int(o[1].split('_')[-1]), nr_people_name].iloc[0]
        # nr_patients_per_route = nr_people_per_route_total * factor_hospital

        # find out which edges belong to the preferred path
        edgesinpath = list(zip(alt_nodes[0:], alt_nodes[1:]))

        # calculate the total length of the alternative route (in miles)
        # Find the road segments that are used for the detour to the same or another hospital
        length_list = []
        for u, v in edgesinpath:
            # get edge with the lowest weighing if there are multiple edges that connect u and v
            edge_key = sorted(graph[u][v], key=lambda x: graph[u][v][x][weighing])[0]

            # Add the number of people that need hospital care, to the road segments. For now, each road segment in a route
            # gets attributed all the people that are taking that route.
            # base_graph[u][v][edge_key][wd[:-2] + '_P'] = base_graph[u][v][edge_key][wd[:-2] + '_P'] + nr_patients_per_route

            if 'length' in graph[u][v][edge_key]:
                length_list.append(graph[u][v][edge_key]['length'])

        alt_miles = sum(length_list) / 1609

        # If the destination is different from the origin, the destination is further than without hazard disruption
        if pref_routes.loc[(pref_routes['origin'] == o[1]) & (pref_routes['destination'] == d[1])].empty:
            # subtract the length/time of the optimal route from the alternative route
            extra_dist = alt_route - pref_routes.loc[pref_routes['origin'] == o[1], weighing].iloc[0]
            extra_miles = alt_miles - pref_routes.loc[pref_routes['origin'] == o[1], 'tot_miles'].iloc[0]
            pp_delayed.append(nr_patients_per_route)
            extra_weights.append(extra_dist)
            extra_miles_total.append(extra_miles)
        else:
            pp_no_delay.append(nr_patients_per_route)

        # compile the road segments into one geometry
        # alt_edges = MultiLineString(alt_edges)

        # Add the number of patients to the total number of patients that go to that hospital
        dest.loc[dest[od_id] == int(d[1].split('_')[-1]), wd[:-2] + '_P'] = dest.loc[dest[od_id] == int(d[1].split('_')[-1]), wd[:-2] + '_P'].iloc[0] + nr_patients_per_route

    return base_graph, dest, list_hospital_flooded, pp_no_delay, pp_delayed, extra_weights, extra_miles_total
