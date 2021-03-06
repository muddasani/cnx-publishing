# -*- coding: utf-8 -*-
import logging

from cnxarchive.scripts import export_epub
from pyramid.events import subscriber
from pyramid.threadlocal import get_current_registry


from . import events
from .bake import remove_baked, bake
from .db import (
    update_module_state,
    with_db_cursor,
)
from .tasks import task


logger = logging.getLogger('cnxpublishing')


@with_db_cursor
def track_baking_proc_state(result, module_ident, cursor):
    cursor.execute('INSERT INTO document_baking_result_associations '
                   '(module_ident, result_id) VALUES (%s, %s)',
                   (module_ident, result.id))


@subscriber(events.PostPublicationEvent)
@with_db_cursor
def post_publication_processing(event, cursor):
    """Process post-publication events coming out of the database."""
    module_ident, ident_hash = event.module_ident, event.ident_hash
    logger.debug('Processing module_ident={} ident_hash={}'.format(
        module_ident, ident_hash))
    update_module_state(cursor, module_ident, 'processing', None)
    # Commit the state change before preceding.
    cursor.connection.commit()

    # Start of task
    # FIXME Looking up the task isn't the most clear usage here.
    task_name = 'cnxpublishing.subscribers.baking_processor'
    baking_processor = get_current_registry().celery_app.tasks[task_name]
    result = baking_processor.delay(module_ident, ident_hash)

    # Save the mapping between a celery task and this event.
    track_baking_proc_state(result, module_ident, cursor)


def _get_recipe_ids(module_ident, cursor):
    """Returns a tuple of length 2 of primary and fallback recipe ids.

    The primary will be based on the print_style of the book. The fallback
    is the recipe used for last successful bake of this book, if different
    than the primary. Either value or both values may be None"""
    cursor.execute("""select coalesce(psf.fileid, mf.fileid, mf2.fileid),
                         CASE
                           WHEN lm.recipe != coalesce(psf.fileid,
                                                      mf.fileid,
                                                      mf2.fileid,0)
                             THEN lm.recipe
                             ELSE NULL
                         END
                      FROM modules m LEFT JOIN print_style_recipes psf
                                         ON m.print_style = psf.print_style
                                     LEFT JOIN module_files mf
                                         ON m.module_ident = mf.module_ident
                                         AND m.print_style = mf.filename
                                     LEFT JOIN module_files mf2
                                         ON m.module_ident = mf2.module_ident
                                         AND mf2.filename = 'ruleset.css'
                                     LEFT JOIN latest_modules lm
                                         ON m.uuid = lm.uuid
                      WHERE m.module_ident = %s""", (module_ident,))
    return cursor.fetchone()


@task()
@with_db_cursor
def baking_processor(module_ident, ident_hash, cursor=None):

    try:
        binder = export_epub.factory(ident_hash)
    except:
        logger.exception('Logging an uncaught exception during baking'
                         'ident_hash={} module_ident={}'
                         .format(ident_hash, module_ident))
        # FIXME If the top module doesn't exist, this is going to fail.
        update_module_state(cursor, module_ident, 'errored', None)
        raise
    finally:
        logger.debug('Finished exporting module_ident={} ident_hash={}'
                     .format(module_ident, ident_hash))

    cursor.execute("""\
SELECT submitter, submitlog FROM modules
WHERE ident_hash(uuid, major_version, minor_version) = %s""",
                   (ident_hash,))
    publisher, message = cursor.fetchone()
    remove_baked(ident_hash, cursor=cursor)

    recipe_ids = _get_recipe_ids(module_ident, cursor)

    state = 'current'
    for recipe_id in recipe_ids:
        try:
            bake(binder, recipe_id, publisher, message, cursor=cursor)
        except Exception as exc:
            if state == 'current' and recipe_ids[1] is not None:
                state = 'fallback'
                continue
            else:
                state = 'errored'
                # TODO rollback to pre-removal of the baked content??
                cursor.connection.rollback()
                logger.exception('Uncaught exception during baking')
                update_module_state(cursor, module_ident, state, recipe_id)
                raise
        finally:
            logger.debug('Finished module_ident={} ident_hash={} '
                         'with a final state of \'{}\'.'
                         .format(module_ident, ident_hash, state))
            update_module_state(cursor, module_ident, state, recipe_id)
            break


@subscriber(events.ChannelProcessingStartUpEvent)
@with_db_cursor
def post_publication_start_up(event, cursor):
    # If you make changes to the payload, be sure to update the trigger
    # code as well.
    cursor.execute("""\
SELECT pg_notify('post_publication',
                 '{"module_ident": '||
                 module_ident||
                 ', "ident_hash": "'||
                 ident_hash(uuid, major_version, minor_version)||
                 '", "timestamp": "'||
                 CURRENT_TIMESTAMP||
                 '"}')
FROM modules
WHERE stateid = (
    SELECT stateid
    FROM modulestates
    WHERE statename = 'post-publication');""")


__all__ = (
    'post_publication_processing',
    'post_publication_start_up',
)
