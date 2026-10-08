"""Flag at-risk projects, waiting registrations and unacknowledged notices, and notify people.

    python manage.py run_automation                 # run the checks once and exit
    python manage.py run_automation --loop          # keep running, every 60 seconds
    python manage.py run_automation --loop --interval 300

Nothing runs by itself: either a scheduler (Windows Task Scheduler, cron) starts the one-off form,
or a --loop process must be kept running. See docs/explain/automation.md.
Safe to run as often as you like: the same alert goes to the same person at most once per 24 hours.
"""

import logging
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from apps.supervision.automation import run_once

logger = logging.getLogger("projecthub.automation")


class Command(BaseCommand):
    help = "Flag at-risk projects, registrations pending over 48 hours and unacknowledged notices; send notifications."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep running instead of exiting after one run.")
        parser.add_argument("--interval", type=int, default=60, help="Seconds between runs with --loop (default 60).")

    def handle(self, *args, **options):
        interval = options["interval"]
        if interval < 1:
            raise CommandError("--interval must be at least 1 second.")
        if not options["loop"]:
            run_once()
            return
        logger.info("run_automation: looping every %s seconds; stop with Ctrl+C", interval)
        try:
            while True:
                try:
                    run_once()
                except Exception:  # one failed run must not stop the loop
                    logger.exception("run_automation: run failed; trying again in %s seconds", interval)
                close_old_connections()  # drop database connections that went stale while sleeping
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("run_automation: stopped")
