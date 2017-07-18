# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from __future__ import absolute_import

import psycopg2
from celery.result import AsyncResult
from pyramid import httpexceptions
from pyramid.view import view_config

from .. import config


@view_config(route_name='print-style-history', request_method='GET',
             renderer='templates/print-style-history.html')
def print_style_history(request):
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    styles = []
    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
            SELECT print_style, baked, recipe, name, sha1
            FROM latest_modules
            JOIN files ON latest_modules.recipe=files.fileid
            WHERE portal_type='Collection' AND baked is not null
            ORDER BY baked DESC limit 100;
            """)
            response = cursor.fetchall()
            for row in response:
                styles.append({
                    'print_style': row[0],
                    'baked': row[1],
                    'recipe': row[2],
                    'name': row[3].decode('utf-8'),
                    'version': row[4]
                })

    return {'styles': styles}

@view_config(route_name='print-style-history-name', request_method='GET',
             renderer='templates/print-style-history.html')
def print_style_history_name(request):
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    print("HELLO MADE IT TO THIS FUNCTION")
    name = request.matchdict['name']
    styles = []
    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
            SELECT print_style, baked, recipe, name, sha1
            FROM latest_modules
            JOIN files ON latest_modules.recipe=files.fileid
            WHERE portal_type='Collection' AND baked is not null
                AND print_style=(%s)
            ORDER BY baked DESC limit 100;
            """, vars=(name, ))
            response = cursor.fetchall()
            for row in response:
                styles.append({
                    'print_style': row[0],
                    'baked': row[1],
                    'recipe': row[2],
                    'name': row[3].decode('utf-8'),
                    'version': row[4]
                })

    return {'print_style': name,
            'styles': styles}


@view_config(route_name='print-style-history-version', request_method='GET',
             renderer='templates/print-style-history.html')
def print_style_history_version(request):
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    name = request.matchdict['name']
    version = request.matchdict['version']

    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
            SELECT sha1
            FROM files
            WHERE fileid=(SELECT fileid
                          FROM print_style_recipes
                          WHERE print_style=(%s) AND tag=(%s));
            """, vars=(name, version))
            recipe = cursor.fetchall()

            print(len(recipe))
            if len(recipe) != 1:
                raise httpexceptions.HTTPBadRequest(
                    'style {} with version {} not found'.format(name, version))

            sha1 = recipe[0][0]
            print(request.route_path('resource', hash=sha1, ignore=""))
            raise httpexceptions.HTTPFound(
                location=request.route_path('resource',
                                            hash=sha1, ignore=""))

    return {'file': file_data}
