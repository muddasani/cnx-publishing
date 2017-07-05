# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import unittest

from cnxdb.init import init_db
from pyramid import testing

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
            INSERT INTO document_baking_result_associations
            (result_id, module_ident)
            SELECT
            uuid_generate_v4(),
            (SELECT module_ident FROM modules ORDER BY module_ident DESC LIMIT 1);""")
            db_conn.commit()

            cursor.execute("""\
            INSERT INTO document_baking_result_associations
            (result_id, module_ident)
            SELECT
            uuid_generate_v4(),
            (SELECT module_ident FROM modules ORDER BY module_ident DESC LIMIT 1);""")
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
        init_db(self.db_conn_str, True)

    def tearDown(self):
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    @property
    def target(self):
        from ...views.admin import admin_post_publications
        return admin_post_publications

    @unittest.skip("celery is too global, run one at a time")
    def test_no_results(self):
        request = testing.DummyRequest()

        resp_data = self.target(request)

        self.assertEqual({'states': []}, resp_data)

    @unittest.skip("celery is too global, run one at a time")
    def test(self):
        request = testing.DummyRequest()

        book = add_data(self)

        resp_data = self.target(request)
        self.assertEqual({
            'states': [
                {'created': resp_data['states'][0]['created'],
                 'ident_hash': book.ident_hash,
                 'state': u'PENDING',
                 'state_message': '',
                 'title': 'Book of Infinity'},
                {'created': resp_data['states'][1]['created'],
                 'ident_hash': book.ident_hash,
                 'state': u'PENDING',
                 'state_message': '',
                 'title': 'Book of Infinity'},
                ]}, resp_data)


# FIXME There is an issue with setting up the celery app more than once.
#       Apparently, creating the app a second time doesn't really create
#       it again. There is some global state hanging around that we can't
#       easily get at. This causes the task results tables used in these
#       views to not exist, because the code believes it's already been
#       initialized.
# @unittest.skip("celery is too global")
class ContentStatusViewsTestCase(unittest.TestCase):
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
        init_db(self.db_conn_str, True)
        add_data(self)

    def tearDown(self):
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    @unittest.skip("celery is too global, run one at a time")
    def test_admin_content_status_no_filters(self):
        request = testing.DummyRequest()

        from ...views.admin import admin_content_status
        content = admin_content_status(request)
        self.assertEqual({
            'SUCCESS': 'checked',
            'PENDING': 'checked',
            'STARTED': 'checked',
            'RETRY': 'checked',
            'FAILURE': 'checked',
            'start_entry': 0,
            'page': 1,
            'num_entries': 100,
            'sort': 'bpsa.created DESC',
            'states': content['states']
        }, content)
        self.assertEqual(len(content['states']), 2)
        self.assertEqual(
            content['states'],
            sorted(content['states'], key=lambda x: x['created'], reverse=True))

    @unittest.skip("celery is too global, run one at a time")
    def test_admin_content_status_w_filters(self):
        request = testing.DummyRequest()

        request.GET = {'page': 1,
                       'number': 2,
                       'sort': 'STATE ASC',
                       'author': 'charrose',
                       'exculde_statuses': 'SUCCESS,STARTED'}
        from ...views.admin import admin_content_status
        content = admin_content_status(request)
        self.assertEqual({
            'FAILURE': 'checked',
            'RETRY': 'checked',
            'PENDING': 'checked',
            'start_entry': 0,
            'page': 1,
            'num_entries': 2,
            'author': 'charrose',
            'sort': 'STATE ASC',
            'states': content['states']
        }, content)
        self.assertEqual(len(content['states']), 2)
        for state in content['states']:
            self.assertTrue('charrose' in state['authors'])
            self.assertTrue(state['state'] not in ['STARTED', 'SUCCESS'])
        self.assertEqual(
            content['states'],
            sorted(content['states'], key=lambda x: x['state']))

    @unittest.skip("celery is too global, run one at a time")
    def test_admin_content_status_single_page(self):
        request = testing.DummyRequest()

        ident = 'd5dbbd8e-d137-4f89-9d0a-3ac8db53d8ee@1.1'
        request.matchdict['ident_hash'] = ident

        from ...views.admin import admin_content_status_single
        content = admin_content_status_single(request)
        self.assertEqual({
            'ident_hash': ident,
            'title': 'Book of Infinity',
            'authors': 'marknewlyn, charrose',
            'created': content['created'],
            'state': 'PENDING',
            'state_message': '',
        }, content)
