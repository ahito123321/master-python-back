from django.shortcuts import render
from django.http import HttpRequest
from rest_framework.response import Response
from rest_framework.views import APIView
import json
import requests
import numpy as np

GOOGLE_API_KEY = 'AIzaSyB8pHk0GskSMHDLLYPEC1-wdHXoUDhlDwc'
GOOGLE_LANGUAGE = 'ru'
GOOGLE_DISTANCE_MATRIX_END_POINT = 'https://maps.googleapis.com/maps/api/distancematrix/json'

BORDER_BOUND = 'https://mbab.herokuapp.com/api/bab/basic'

RANDOM_CONSISTENCY_SIZE = [0, 0, 0.58, 0.9, 1.12]


class Point:
    def __init__(self, lat, lng, id):
        self.lat = lat
        self.lng = lng
        self.id = id


class Route:

    def __init__(self, origin_point, destination_point, mode='DRIVING'):
        self.distance = 0
        self.duration = 0
        self.price = 0
        self.origin_point = origin_point
        self.destination_point = destination_point
        self.mode = mode
        self.isStartRoute = False

    def init_distances(self):
        response = requests.get(
            GOOGLE_DISTANCE_MATRIX_END_POINT,
            params={
                'units': 'metric',
                'key': GOOGLE_API_KEY,
                'language': GOOGLE_LANGUAGE,
                'mode': self.mode,
                'origins': '{0}, {1}'.format(self.origin_point.lat, self.origin_point.lng),
                'destinations': '{0}, {1}'.format(self.destination_point.lat, self.destination_point.lng)
            },
            headers={'Content-type': 'application/json'}
        )
        json_response = response.json()
        self.distance = json_response['rows'][0]['elements'][0]['distance']['value']
        self.duration = json_response['rows'][0]['elements'][0]['duration']['value']

        return json_response

    @staticmethod
    def get_routes(first_point_index, points_ids):
        full_routes = list()
        index = 0

        for id in points_ids:
            if index != first_point_index:
                new_route = list()
                new_route.append(points_ids[first_point_index])
                new_route.append(id)

                existed = list(points_ids)
                existed.remove(points_ids[first_point_index])
                existed.remove(id)

                Route._init_routes(full_routes, new_route, existed)
            index += 1

        return full_routes

    @staticmethod
    def _init_routes(full_routes, selected, existed):

        if existed.__len__() == 0:
            return full_routes.append(selected)

        for id in existed:
            selected_copy = list(selected)
            selected_copy.append(id)

            existed_copy = list(existed)
            existed_copy.remove(id)

            Route._init_routes(full_routes, selected_copy, existed_copy)


class ComboRoute:
    def __init__(self, full_route, json_settings):
        self.full_route = full_route
        self.prepared_route = list()
        self.route_duration = 0
        self.route_distance = 0
        self.routes_price = 0
        self.route_full_duration = 0
        self.json_settings = json_settings

    def init_route(self, points, routes):
        for index in range(points.__len__() - 1):

            origin_id = points[index]
            destination_id = points[index + 1]
            temp = list()
            temp.append(origin_id)
            temp.append(destination_id)
            self.prepared_route.append(temp)

            for route in routes:
                if route.origin_point.id == origin_id and route.destination_point.id == destination_id:
                    self.route_duration += route.duration
                    self.route_distance += route.distance

                    if self.json_settings['takeRoutePrice']:
                        car_consumption = self.json_settings['carConsumption']
                        fuel_cost = self.json_settings['fuelCost']
                        self.routes_price += route.distance * (car_consumption / (100 * 1000)) * fuel_cost
                    break

    def getRouteForResponse(self):
        routes = list()
        route = list()
        for point in self.full_route:
            route.append(point)

            if route.__len__() == 2:
                routes.append(route)
                route = list()
                route.append(point)

        return {
            'route': routes,
            'duration': {
                'label': 'Время',
                'value': self.route_duration
            },
            'distance': {
                'label': 'Расстояние',
                'value': self.route_distance
            },
            'price': {
                'label': 'Цена',
                'value': self.routes_price
            }
        }


class SaatiMatrix:

    def __init__(self, matrix):
        self.matrix = matrix
        self.number_cols = self.matrix[0].__len__()

        total_sum = 0
        temp_vector = []

        for row in self.matrix:
            row_mul = 1

            for col in row:
                row_mul *= col

            val = row_mul ** (1 / self.number_cols)
            temp_vector.append(val)
            total_sum += val

        self.vector = np.array(temp_vector)
        temp_norm_vector = []

        for row in self.vector:
            temp_norm_vector.append(row / total_sum)

        self.norm_vector = np.array(temp_norm_vector)

        temp_col_sum = []
        for index in range(self.number_cols):
            sum = 0
            for el in self.matrix[:, index]:
                sum += el
            temp_col_sum.append(sum)

        temp_l_max = []
        l_sum = 0

        for index in range(self.number_cols):
            val = temp_col_sum[index] * temp_norm_vector[index]
            temp_l_max.append(val)
            l_sum += val

        self.l_max = temp_l_max
        self.consistency_index = (l_sum - self.number_cols) / (self.number_cols - 1)
        self.consistency_relation = self.consistency_index / RANDOM_CONSISTENCY_SIZE[self.number_cols - 1]


class RouteAlgorithm:

    @staticmethod
    def call_branch_and_bound_method(json_points):
        routes = list()
        id_starting_point = 0
        index_starting_point = 0
        index = 0
        initial_point = list()

        for json_point in json_points:
            origin_point = Point(json_point['position']['lat'], json_point['position']['lng'], json_point['id'])
            initial_point.append(origin_point)

            if json_point['isStartingPoint']:
                id_starting_point = json_point['id']
                index_starting_point = index

            for json_another_point in json_point['anotherPoints']:
                destination_point_id = json_another_point['id']
                route = Route(origin_point, json_another_point['variant'])

                for _json_point in json_points:
                    if _json_point['id'] == destination_point_id:
                        route.destination_point = Point(_json_point['position']['lat'],
                                                        _json_point['position']['lng'],
                                                        _json_point['id'])

                routes.append(route)

            index += 1

        number_of_points = json_points.__len__()
        duration_matrix = [['' for j in range(number_of_points)] for i in range(number_of_points)]
        distance_matrix = [['' for j in range(number_of_points)] for i in range(number_of_points)]
        index = 0
        initial_ids = list()

        for row in range(number_of_points):
            if index == 0:
                initial_ids.append(routes[index].origin_point)
            for col in range(number_of_points):
                if row != col:
                    routes[index].init_distances()
                    duration_matrix[row][col] = routes[index].duration
                    distance_matrix[row][col] = routes[index].distance
                    index += 1
                else:
                    duration_matrix[row][col] = None
                    distance_matrix[row][col] = None

        duration_response = requests.post(
            BORDER_BOUND,
            data=json.dumps({
                'matrix': duration_matrix,
                'start': index_starting_point
            }),
            headers={'Content-type': 'application/json'}
        )
        distance_response = requests.post(
            BORDER_BOUND,
            data=json.dumps({
                'matrix': distance_matrix,
                'start': index_starting_point
            }),
            headers={'Content-type': 'application/json'}
        )

        duration_response_json = duration_response.json()
        distance_response_json = distance_response.json()
        duration_response_json_route = duration_response.json()['route']
        distance_response_json_route = distance_response.json()['route']

        print(duration_response_json)
        print(distance_response_json)

        for ik in range(number_of_points):
            first_point_id_dur = duration_response_json_route[ik][0]
            second_point_id_dur = duration_response_json_route[ik][1]
            first_point_id_dis = distance_response_json_route[ik][0]
            second_point_id_dis = distance_response_json_route[ik][1]

            for jk in range(number_of_points):
                if first_point_id_dur == jk:
                    duration_response_json_route[ik][0] = initial_point[jk].id
                if first_point_id_dur == jk:
                    duration_response_json_route[ik][1] = initial_point[jk].id
                if first_point_id_dis == jk:
                    distance_response_json_route[ik][0] = initial_point[jk].id
                if second_point_id_dis == jk:
                    distance_response_json_route[ik][1] = initial_point[jk].id

        return {
            'success': True,
            'routes': {
                'duration': duration_response.json(),
                'distance': distance_response.json()
            },
            'labels': {
                'duration': 'Время',
                'distance': 'Расстояние'
            }
        }

    @staticmethod
    def call_sati(json_points, json_settings, json_prioritization):
        temp = np.array([
            [1, 1 / json_prioritization['distanceToTime'], 1 / json_prioritization['priceToTime']],
            [json_prioritization['distanceToTime'], 1, 1 / json_prioritization['priceToDistance']],
            [json_prioritization['priceToTime'], json_prioritization['priceToDistance'], 1]
        ])
        prioritization_matrix = SaatiMatrix(temp)

        if prioritization_matrix.consistency_relation > 0.1:
            return {
                'success': False,
                'message': 'Неверные параметры приоритизации! Проверьте введённые данные!'
            }

        routes = list()
        index = 0
        index_starting_point = 0
        points_ids = list()

        for json_point in json_points:
            origin_point = Point(json_point['position']['lat'],
                                 json_point['position']['lng'],
                                 json_point['id'])
            points_ids.append(origin_point.id)

            if json_point['isStartingPoint']:
                id_starting_point = json_point['id']
                index_starting_point = index

            for json_another_point in json_point['anotherPoints']:
                destination_point_id = json_another_point['id']
                route = Route(origin_point, json_another_point['variant'])

                if json_point['isStartingPoint']:
                    route.isStartRoute = True

                for _json_point in json_points:
                    if _json_point['id'] == destination_point_id:
                        route.destination_point = Point(_json_point['position']['lat'],
                                                        _json_point['position']['lng'],
                                                        _json_point['id'])

                routes.append(route)

            index += 1

        full_initial_routes = Route.get_routes(index_starting_point, points_ids)

        for route in routes:
            route.init_distances()

        full_routes = list()
        print('\nroutes')
        for full_initial_route in full_initial_routes:
            comboRoute = ComboRoute(full_initial_route, json_settings)
            comboRoute.init_route(full_initial_route, routes)
            full_routes.append(comboRoute)
            print('route', comboRoute.full_route)
            print('distance', comboRoute.route_distance)
            print('duration', comboRoute.route_duration)
            print('duration', comboRoute.routes_price)

        return {
            'success': True,
            'routes': {
                'main': full_routes[0].getRouteForResponse()
            },
            'labels': {
                'main': 'Основной'
            }
        }


class RouteView(APIView):
    def get(self, request):
        return Response('get')

    def post(self, request):
        # try:
            json_body = json.loads(request.body)
            json_points = json_body['points']
            json_settings = json_body['settings']
            json_prioritization = json_body['prioritization']

            print(json_settings)
            print(json_prioritization)

            if (json_settings['takePrioritization'] == True):
                print('SAATI')
                result = RouteAlgorithm.call_sati(json_points, json_settings, json_prioritization)
            else:
                print('BAB')
                result = RouteAlgorithm.call_branch_and_bound_method(json_points)

            # print(json_points)
            # print(json_settings)
            # print(json_prioritization)
            return Response({
                'success': True,
                'data': result
            })
        # except Exception as err:
        #     print('err')
        #     print(err)
        #     return Response({
        #         'success': False,
        #         'message': 'Ошибка! Проверьте пожалуйста выбранные точки!'
        #     })
