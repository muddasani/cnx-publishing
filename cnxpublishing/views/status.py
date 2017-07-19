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
             renderer='json')
def print_style_history(request):
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    styles = []
    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
            SELECT lm.print_style, baked, recipe, name, psr.tag
            FROM latest_modules as lm
            JOIN print_style_recipes as psr
                ON lm.print_style=psr.print_style
            WHERE portal_type='Collection' AND baked is not null
            ORDER BY baked;
            """)
            response = cursor.fetchall()
            for row in response:
                styles.append({
                    'print_style': row[0],
                    'baked': str(row[1]),
                    'recipe': row[2],
                    'name': row[3].decode('utf-8'),
                    'version': row[4],
                    'print_style_url': request.route_url(
                        'print-style-history-name',
                        name=row[0]),
                    'recipe_url': request.route_url('print-style-history-version',
                        name=row[0], version=row[4])
                })
    return styles


@view_config(route_name='print-style-history_POST', request_method='POST',
             renderer='json')
def print_style_history_POST(request):
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    files = request.POST.get('files')
    data = request.POST.get('data')
    name = data['name']
    version = data['version']

    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            # add the file
            cursor.execute("""
            INSERT INTO files (file, media_type)
            VALUES (%s, 'text/css');""")

            cursor.execute("""
                SELECT fileid FROM files ORDER BY fileid DESC LIMIT 1;""")
            fileid = cursor.fetchall()[0][0]

            # add the file to print style table
            cursor.execute("""
            INSERT INTO print_style_recipes
            (print_style, tag, fileid)
            VALUES (%s, %s, %s);
            """, vars=(name, version, fileid, ))
    return {}


@view_config(route_name='print-style-history-name', request_method='GET',
             renderer='json')
def print_style_history_name(request):
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    name = request.matchdict['name']
    styles = []
    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
            SELECT lm.print_style, baked, recipe, name, psr.tag
            FROM latest_modules as lm
            JOIN print_style_recipes as psr
                ON lm.print_style=psr.print_style
            WHERE portal_type='Collection' AND baked is not null
                AND lm.print_style=(%s)
            ORDER BY baked;
            """, vars=(name, ))
            response = cursor.fetchall()
            for row in response:
                styles.append({
                    'print_style': row[0],
                    'baked': row[1].strftime('%Y-%m-%d %H:%M:%S'),
                    'recipe': row[2],
                    'name': row[3].decode('utf-8'),
                    'version': row[4],
                    'recipe_url': request.route_url('print-style-history-version',
                        name=row[0], version=row[4])
                })
    return styles


@view_config(route_name='print-style-history-version', request_method='GET')
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
            files = cursor.fetchall()
            print(files)

            if len(files) != 1:
                raise httpexceptions.HTTPBadRequest(
                    'style {} with version {} not found'.format(name, version))
            sha1 = files[0][0]
            raise httpexceptions.HTTPFound(
                location=request.route_path('resource',
                                            hash=sha1, ignore=""))
