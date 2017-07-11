# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from __future__ import absolute_import

from re import compile, match

import psycopg2
from celery.result import AsyncResult
from pyramid import httpexceptions
from pyramid.view import view_config

from cnxarchive.utils.ident_hash import IdentHashError
from .. import config
from .moderation import get_moderation
from .api_keys import get_api_keys

STATE_ICONS = {
    "SUCCESS": {'class': 'fa fa-check-square',
                'style': 'font-size:20px;color:limeGreen'},
    "STARTED": {'class': 'fa fa-exclamation-triangle',
                'style': 'font-size:20px;color:gold'},
    "PENDING": {'class': 'fa fa-exclamation-triangle',
                'style': 'font-size:20px;color:gold'},
    "RETRY": {'class': 'a fa-close',
              'style': 'font-size:20px;color:red'},
    "FAILURE": {'class': 'fa fa-close',
                'style': 'font-size:20px;color:red'}}
SORTS_DICT = {
    "bpsa.created": 'created',
    "m.name": 'name',
    "STATE": 'state'}
ARROW_MATCH = {
    "ASC": 'fa fa-angle-up',
    "DESC": 'fa fa-angle-down'}


@view_config(route_name='admin-index', request_method='GET',
             renderer="cnxpublishing.views:templates/index.html",
             permission='preview')
def admin_index(request):  # pragma: no cover
    return {
        'navigation': [
            {'name': 'Moderation List',
             'uri': request.route_url('admin-moderation'),
             },
            {'name': 'API Keys',
             'uri': request.route_url('admin-api-keys'),
             },
            {'name': 'Post Publication Logs',
             'uri': request.route_url('admin-post-publications'),
             },
            {'name': 'Content Status',
             'uri': request.route_url('admin-content-status'),
             },
            ],
        }


@view_config(route_name='admin-moderation', request_method='GET',
             renderer="cnxpublishing.views:templates/moderations.html",
             permission='moderate')
@view_config(route_name='moderation-rss', request_method='GET',
             renderer="cnxpublishing.views:templates/moderations.rss",
             permission='view')
def admin_moderations(request):  # pragma: no cover
    return {'moderations': get_moderation(request)}


@view_config(route_name='admin-api-keys', request_method='GET',
             renderer="cnxpublishing.views:templates/api-keys.html",
             permission='administer')
def admin_api_keys(request):  # pragma: no cover
    # Easter Egg that will invalidate the cache, just hit this page.
    # FIXME Move this logic into the C[R]UD views...
    from ..authnz import lookup_api_key_info
    from ..cache import cache_manager
    cache_manager.invalidate(lookup_api_key_info)

    return {'api_keys': get_api_keys(request)}


@view_config(route_name='admin-post-publications', request_method='GET',
             renderer='cnxpublishing.views:templates/post-publications.html',
             permission='administer')
def admin_post_publications(request):
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    states = []
    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT ident_hash(m.uuid, m.major_version, m.minor_version),
       m.name, bpsa.created, bpsa.result_id::text
FROM document_baking_result_associations AS bpsa
     INNER JOIN modules AS m USING (module_ident)
ORDER BY bpsa.created DESC LIMIT 100""")
            for row in cursor.fetchall():
                message = ''
                result_id = row[-1]
                result = AsyncResult(id=result_id)
                if result.failed():  # pragma: no cover
                    message = result.traceback
                states.append({
                    'ident_hash': row[0],
                    'title': row[1],
                    'created': row[2],
                    'state': result.state,
                    'state_message': message,
                })

    return {'states': states}


def get_baking_statuses_sql(request):
    args = {}
    sort = request.GET.get('sort', 'bpsa.created DESC')
    if (len(sort.split(" ")) != 2 or
            sort.split(" ")[0] not in SORTS_DICT.keys() or
            sort.split(" ")[1] not in ARROW_MATCH.keys()):
        raise httpexceptions.HTTPBadRequest(
            'invalid sort: {}'.format(sort))
    if sort == "STATE ASC" or sort == "STATE DESC":
        sort = 'bpsa.created DESC'
    uuid_filter = request.GET.get('uuid', '')
    author_filter = request.GET.get('author', '')

    sql_filters = "WHERE"
    if uuid_filter != '':
        args['uuid'] = uuid_filter
        sql_filters += " m.uuid=%(uuid)s AND "
    if author_filter != '':
        author_filter = author_filter.decode('utf-8')
        sql_filters += "%(author)s=ANY(m.authors) "
        args["author"] = author_filter

    if sql_filters.endswith("AND "):
        sql_filters = sql_filters[:-4]
    if sql_filters == "WHERE":
        sql_filters = ""

    statement = """SELECT ident_hash(m.uuid, m.major_version, m.minor_version),
                       m.name, m.authors, m.uuid, m.print_style,
                       ps.fileid as latest_recepie,  m.recipe,
                       lm.version as latest_version, m.version,
                       bpsa.created, bpsa.result_id::text
                FROM document_baking_result_associations AS bpsa
                INNER JOIN modules AS m USING (module_ident)
                LEFT JOIN print_style_recipes as ps
                    ON ps.print_style=m.print_style
                LEFT JOIN latest_modules as lm
                    ON lm.uuid=m.uuid
                {}
                ORDER BY {};
                """.format(sql_filters, sort)
    args.update({'sort': sort})
    return statement, args


def format_autors(authors):
    if len(authors) == 0:
        return ""
    return_str = ""
    for author in authors:
        return_str += author.decode('utf-8') + ", "
    return return_str[:-2]


@view_config(route_name='admin-content-status', request_method='GET',
             renderer='cnxpublishing.views:templates/content-status.html',
             permission='administer')
def admin_content_status(request):
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]
    statement, args = get_baking_statuses_sql(request)
    states = []
    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute(statement, vars=args)
            for row in cursor.fetchall():
                message = ''
                result_id = row[-1]
                result = AsyncResult(id=result_id)
                if result.failed():  # pragma: no cover
                    message = result.traceback.split("\n")[-2]
                latest_recepie = row[5]
                current_recepie = row[6]
                latest_version = row[7]
                current_version = row[8]
                state = str(result.state)
                if current_version != latest_version:
                    state += ' stale_content'
                if current_recepie != latest_recepie:
                    state += ' stale_recipie'
                state_icon = result.state
                if state[:7] == "SUCCESS" and len(state) > 7:
                    state_icon = 'PENDING'
                states.append({
                    'ident_hash': row[0],
                    'title': row[1].decode('utf-8'),
                    'authors': format_autors(row[2]),
                    'uuid': row[3],
                    'print_style': row[4],
                    'recipe': row[5],
                    'created': row[-2],
                    'state': state,
                    'state_message': message,
                    'state_icon': STATE_ICONS[state_icon]['class'],
                    'state_icon_style': STATE_ICONS[state_icon]['style'],
                    'link': request.route_url('get-content',
                                              ident_hash=row[3])
                })
    status_filters = request.GET.getall('status_filter')
    if status_filters == []:
        status_filters = ["PENDING", "STARTED", "RETRY", "FAILURE", "SUCCESS"]
    for f in (status_filters):
        args[f] = "checked"
    final_states = []
    for state in states:
        if state['state'].split(' ')[0] in status_filters:
            final_states.append(state)

    sort = request.GET.get('sort', 'bpsa.created DESC')
    sort_match = SORTS_DICT[sort.split(' ')[0]]
    args['sort_' + sort_match] = ARROW_MATCH[sort.split(' ')[1]]
    args['sort'] = sort
    if sort == "STATE ASC":
        final_states = sorted(final_states, key=lambda x: x['state'])
    if sort == "STATE DESC":
        final_states = sorted(final_states,
                              key=lambda x: x['state'], reverse=True)

    num_entries = request.GET.get('number', 100)
    page = request.GET.get('page', 1)
    try:
        page = int(page)
        num_entries = int(num_entries)
        start_entry = (page - 1) * num_entries
    except ValueError:
        raise httpexceptions.HTTPBadRequest(
            'invalid page({}) or entries per page({})'.
            format(page, num_entries))
    final_states = final_states[start_entry: start_entry + num_entries]
    args.update({'start_entry': start_entry,
                 'num_entries': num_entries,
                 'page': page,
                 'total_entries': len(final_states)})

    args.update({'states': final_states})
    return args


@view_config(route_name='admin-content-status-single', request_method='GET',
             renderer='templates/content-status-single.html',
             permission='administer')
def admin_content_status_single(request):
    uuid = request.matchdict['uuid']
    pat = ("[0-9a-z]{8}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12}$")
    if not compile(pat).match(uuid):
        raise httpexceptions.HTTPBadRequest(
            '{} is not a valid uuid'.format(uuid))

    settings = request.registry.settings
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
                SELECT ident_hash(m.uuid, m.major_version, m.minor_version),
                       m.name, m.authors, m.uuid, m.print_style,
                       ps.fileid as latest_recepie,  m.recipe,
                       lm.version as latest_version, m.version,
                       bpsa.created, bpsa.result_id::text
                FROM document_baking_result_associations AS bpsa
                INNER JOIN modules AS m USING (module_ident)
                LEFT JOIN print_style_recipes as ps
                    ON ps.print_style=m.print_style
                LEFT JOIN latest_modules as lm
                ON lm.uuid=m.uuid
                WHERE uuid=%s ORDER BY bpsa.created DESC;
                """, vars=(uuid,))
            modules = cursor.fetchall()
            if len(modules) == 0:
                raise httpexceptions.HTTPBadRequest(
                    '{} is not a book'.format(uuid))

            states = []
            row = modules[0]
            args = {'uuid': str(row[3]),
                    'title': row[1].decode('utf-8'),
                    'authors': format_autors(row[2]),
                    'print_style': row[4],
                    'current_recipie': row[5]}

            for row in modules:
                message = ''
                result_id = row[-1]
                result = AsyncResult(id=result_id)
                if result.failed():  # pragma: no cover
                    message = result.traceback
                latest_recepie = row[5]
                current_recepie = row[6]
                latest_version = row[7]
                current_version = row[8]
                state = result.state
                if current_recepie != latest_recepie:
                    state += ' stale_recipie'
                if current_version != latest_version:
                    state += ' stale_content'
                states.append({
                    'ident_hash': row[0],
                    'recipe': row[5],
                    'created': str(row[6]),
                    'state': state,
                    'state_message': message,
                })
            args['states'] = states
            return args
