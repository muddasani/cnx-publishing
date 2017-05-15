# -*- coding: utf-8 -*-
import unittest

from pyramid import testing

from . import use_cases
from .testing import db_connect
from .test_db import BaseDatabaseIntegrationTestCase


class PostPublicationProcessingTestCase(BaseDatabaseIntegrationTestCase):

    @property
    def target(self):
        from cnxpublishing.subscribers import post_publication_processing
        return post_publication_processing

    def _make_event(self, payload):
        from psycopg2.extensions import Notify
        notif = Notify(pid=555, channel='post_publication', payload=payload)
        from cnxpublishing.events import PostPublicationEvent
        event = PostPublicationEvent(notif)
        return event

    @db_connect
    def setUp(self, cursor):
        super(PostPublicationProcessingTestCase, self).setUp()
        use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        self.ident_hash = '{}@{}'.format(
            'c3bb4bfb-3b53-41a9-bb03-583cf9ce3408',
            '1.1')
        cursor.execute(
            "SELECT module_ident FROM modules "
            "WHERE ident_hash(uuid, major_version, minor_version) = %s",
            (self.ident_hash,))
        self.module_ident = cursor.fetchone()[0]
    # We don't test for not found, because a notify only takes place when
    #   a module exists.

    @db_connect
    def test(self, cursor):
        payload = '{{"module_ident": {}, "ident_hash": "{}", ' \
                  '"timestamp": "<date>"}}'.format(self.module_ident,
                                                   self.ident_hash)
        event = self._make_event(payload)

        self.target(event)
        cursor.execute("SELECT count(*) FROM trees WHERE is_collated = 't';")
        collation_count = cursor.fetchone()[0]
        assert collation_count > 0, "baking didn't happen"
