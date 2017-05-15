# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2017, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
"""\
This script is used to listen for notifications coming from PostgreSQL.
This script translates the notifications into events that are handled
by this project's logic.

To handle a notification, register an event subscriber for the specific
channel event.
For further instructions see `cnxpublishing.events.PGNotifyEvent`
and `cnxpublishing.events.create_pg_notify_event` (an event factory).

"""
from __future__ import print_function
import logging
import os
import select
import sys

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from pyramid.paster import bootstrap
from pyramid.threadlocal import get_current_registry

from cnxpublishing.config import CONNECTION_STRING
from cnxpublishing.events import create_pg_notify_event


logger = logging.getLogger('channel_processing')
# TODO make this a configuration option.
CHANNELS = ['post_publication']


def usage(argv):
    cmd = os.path.basename(argv[0])
    print('Usage: {} <config_uri>\n'
          '(example: "{} development.ini")'.format(cmd, cmd),
          file=sys.stderr)
    sys.exit(1)


def processor(config_uri):
    registry = bootstrap(config_uri)['registry']
    settings = registry.settings
    connection_string = settings[CONNECTION_STRING]

    # Code adapted from
    # http://initd.org/psycopg/docs/advanced.html#asynchronous-notifications
    with psycopg2.connect(connection_string) as conn:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        with conn.cursor() as cursor:
            for channel in CHANNELS:
                cursor.execute('LISTEN {}'.format(channel))
                logger.debug('Waiting for notifications on channel "{}"'
                             .format(channel))

        rlist = [conn]  # wait until ready for reading
        wlist = []  # wait until ready for writing
        xlist = []  # wait for an "exceptional condition"
        timeout = 5

        while True:
            if select.select(rlist, wlist, xlist, timeout) != ([], [], []):
                conn.poll()
                while conn.notifies:
                    notif = conn.notifies.pop(0)
                    logger.debug('Got NOTIFY: pid={} channel={} payload={}'
                                 .format(notif.pid, notif.channel,
                                         notif.payload))
                    # TODO Error handling and recovery for...
                    event = create_pg_notify_event(notif)
                    try:
                        registry.notify(event)
                    except Exception as exc:
                        logger.exception('Logging an uncaught exception')


def main(argv=sys.argv):
    if len(argv) < 2:
        usage(argv)

    config_uri = argv[1]
    processor(config_uri)


if __name__ == '__main__':
    main()
