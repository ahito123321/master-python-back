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

BORDER_BOUND = 'http://127.0.0.1:5001/api/bab/basic'

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

        print('\nget_instance')
        print('rows {0}'.format(json_response['rows'].__len__()))
        print('elements {0}'.format(json_response['rows'][0]['elements'].__len__()))
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
                print(new_route)
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

        for json_point in json_points:
            origin_point = Point(json_point['position']['lat'], json_point['position']['lng'], json_point['id'])

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

        for row in range(number_of_points):
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

        return {
            'duration': duration_response.json(),
            'distance': distance_response.json()
        }

    @staticmethod
    def call_sati(json_points, json_settings, json_prioritization):
        if json_prioritization['priceToTime']:
            temp = np.array([
                [1, 1 / json_prioritization['distanceToTime'], 1 / json_prioritization['priceToTime']],
                [json_prioritization['distanceToTime'], 1, 1 / json_prioritization['priceToDistance']],
                [json_prioritization['priceToTime'], json_prioritization['priceToDistance'], 1]
            ])
            prioritization_matrix = SaatiMatrix(temp)
            print(prioritization_matrix.norm_vector)
            print(prioritization_matrix.l_max)
            print(prioritization_matrix.consistency_relation)

            if prioritization_matrix.consistency_relation > 0.1:
                return {
                    'message': 'Неверные параметры приоритизации! Проверьте введённые данные!'
                }

            routes = list()
            index = 0
            id_starting_point = 0
            index_starting_point = 0
            points_ids = list()

            for json_point in json_points:
                origin_point = Point(json_point['position']['lat'], json_point['position']['lng'], json_point['id'])
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

            print(points_ids)
            print(index_starting_point)

            full_routes = Route.get_routes(index_starting_point, points_ids)

        return {
            'test': 'test'
        }


class RouteView(APIView):
    def get(self, request):
        return Response('get')

    def post(self, request):
        try:
            json_body = json.loads(request.body)
            json_points = json_body['points']
            json_settings = json_body['settings']
            json_prioritization = json_body['prioritization']

            print(json_settings)
            print(json_prioritization)

            if (json_settings['takeRating'] or
                    json_settings['takeWorkingHours'] or
                    json_settings['takeRoutePrice'] or
                    json_settings['takePrioritization']):
                result = RouteAlgorithm.call_sati(json_points, json_settings, json_prioritization)
            else:
                result = RouteAlgorithm.call_branch_and_bound_method(json_points)

            # print(json_points)
            # print(json_settings)
            # print(json_prioritization)
            return Response({
                'success': True,
                'data': result
            })
        except Exception as err:
            print(err)
            return Response({
                'success': False,
                'message': 'Ошибка! Проверьте пожалуйста выбранные точки!'
            })
