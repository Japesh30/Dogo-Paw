"""Gunicorn settings for the production deployment.

Picked up automatically by `gunicorn app:app` when run from this directory, so
the start command stays short and the reasoning lives here in comments rather
than in an unreadable one-line flag string.

The numbers below are measured, not guessed. One worker of this app — Flask,
SQLAlchemy, numpy, scipy, scikit-learn and the two trained models — occupies
**about 158 MB** resident, and Render's free instance has **512 MB**.
"""

from __future__ import annotations

import os

# Render injects PORT and expects the service to listen on it. Binding to
# 0.0.0.0 rather than localhost is what makes the container reachable at all.
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"

# --------------------------------------------------------------------------- #
# Workers
# --------------------------------------------------------------------------- #
# Gunicorn's default is (2 x CPU) + 1. That default is actively dangerous here:
# a Render free instance reports the *host* CPU count rather than its 0.1 CPU
# share, so the default works out at seventeen or more workers — roughly 2.7 GB
# — and the instance is OOM-killed before it ever serves a request.
#
# Two workers is ~317 MB, which leaves real headroom inside 512 MB. Three would
# be ~475 MB, which is close enough to the ceiling that one request spike ends
# the process.
#
# WEB_CONCURRENCY is the conventional override, so a larger paid instance can be
# given more workers without editing this file.
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))

# Threads, not more processes, are how this app gets concurrency cheaply: almost
# all of a request's wall time is spent waiting on PostgreSQL, and threads share
# the ~120 MB of loaded libraries instead of paying for another copy.
#
# This is only safe because nothing here holds mutable shared state: the models
# are read-only after load, SQLAlchemy sessions are thread-local, and the rate
# limiter guards its counters with a Lock.
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"

# --------------------------------------------------------------------------- #
# Timeouts
# --------------------------------------------------------------------------- #
# Boot is slow on a cold free instance: importing scikit-learn, unpickling both
# models and seeding the database. The 30 s default kills a worker mid-startup
# and gunicorn restarts it into the same wall, so the service never comes up.
timeout = 120

# Slightly above a typical 60 s upstream idle timeout, so the proxy closes
# connections rather than us closing one mid-response.
keepalive = 65
graceful_timeout = 30

# Recycle workers periodically. Cheap insurance against a slow leak on an
# instance nobody is watching; the jitter stops every worker restarting at once.
max_requests = 1000
max_requests_jitter = 100

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
# Render captures stdout/stderr, so log there rather than to files.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# The default access log format records the query string but not headers, so no
# Authorization header and no bearer token can reach the logs.
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(M)sms'

# --------------------------------------------------------------------------- #
# preload_app
# --------------------------------------------------------------------------- #
# Deliberately left off.
#
# Preloading would import the app once and fork, saving roughly 120 MB of
# duplicated libraries. It would also fork *after* SQLAlchemy has opened
# connections, and a TCP socket shared by two processes corrupts both sides of
# the conversation. The correct fix is a post_fork hook disposing the engine
# pool, which is one more moving part to get right and to explain.
#
# Two workers already fit comfortably, so the memory is not needed. If this ever
# moves to a bigger instance with more workers, turn preloading on *and* add:
#
#     def post_fork(server, worker):
#         from models import db
#         db.engine.dispose()
preload_app = False
