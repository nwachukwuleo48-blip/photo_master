"""
WSGI entrypoint for production servers (Waitress, etc.).

Example:
  waitress-serve --listen=0.0.0.0:$PORT wsgi:application
"""

from app import app as application

