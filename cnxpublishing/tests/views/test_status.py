# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import unittest
from datetime import datetime

from cnxdb.init import init_db
from pyramid import testing
from pyramid import httpexceptions

from .. import use_cases
from ..testing import (
    integration_test_settings,
    db_connection_factory,
    )


def add_data(self):
    with self.db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            # Insert one book into archive.
            book = use_cases.setup_BOOK_in_archive(self, cursor)
            db_conn.commit()

            # Insert some data into the association table.
            cursor.execute("""
            UPDATE latest_modules
            SET baked=%s, recipe=1, portal_type='Collection'
            WHERE true;
            """, vars=(datetime.today(), ))
            db_conn.commit()

            cursor.execute("""\
            INSERT INTO print_style_recipes
            (print_style, fileid, tag)
            VALUES
            ('*print style*', 1, '1.0')""")
    return book


# FIXME There is an issue with setting up the celery app more than once.
#       Apparently, creating the app a second time doesn't really create
#       it again. There is some global state hanging around that we can't
#       easily get at. This causes the task results tables used in these
#       views to not exist, because the code believes it's already been
#       initialized.
# @unittest.skip("celery is too global")
class PostPublicationsViewsTestCase(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.settings = integration_test_settings()
        from cnxpublishing.config import CONNECTION_STRING
        cls.db_conn_str = cls.settings[CONNECTION_STRING]
        cls.db_connect = staticmethod(db_connection_factory())

    def setUp(self):
        self.config = testing.setUp(settings=self.settings)
        self.config.include('cnxpublishing.tasks')
        self.config.add_route('resource', '/resources/{hash}{ignore:(/.*)?}')  # noqa cnxarchive.views:get_resource
        init_db(self.db_conn_str, True)

    def tearDown(self):
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    @unittest.skip("celery is too global, run one at a time")
    def test_print_style_history(self):
        request = testing.DummyRequest()

        book = add_data(self)

        from ...views.status import print_style_history
        content = print_style_history(request)
        self.assertEqual({
            'styles': [{
                'name': 'Document One of Infinity',
                'version': '1.0',
                'recipe': 1,
                'print_style': '*print style*',
                'baked': content['styles'][0]['baked']
            }]},
            content)

    @unittest.skip("celery is too global, run one at a time")
    def test_print_style_history_single_style(self):
        request = testing.DummyRequest()

        name = '*print style*'
        request.matchdict['name'] = name

        book = add_data(self)

        from ...views.status import print_style_history_name
        content = print_style_history_name(request)
        self.assertEqual({
            'print_style': name,
            'styles': [{
                'name': 'Document One of Infinity',
                'version': '1.0',
                'recipe': 1,
                'print_style': '*print style*',
                'baked': content['styles'][0]['baked']
            }]},
            content)

    # @unittest.skip("celery is too global, run one at a time")
    def test_print_style_history_single_version(self):
        request = testing.DummyRequest()

        name = '*print style*'
        request.matchdict['name'] = name
        request.matchdict['version'] = '1.0'

        book = add_data(self)

        from ...views.status import print_style_history_version
        with self.assertRaises(httpexceptions.HTTPFound) as cm:
            print_style_history_version(request)

        self.assertEqual(cm.exception.headers['Location'],
                         '/resources/8d539366a39af1715bdf4154d0907d4a5360ba29')
        self.assertEqual(cm.exception.headers['Content-Type'],
                         'text/html; charset=UTF-8')
