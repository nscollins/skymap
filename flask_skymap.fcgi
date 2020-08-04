#!/home8/nathali4/public_html/prototypes/skymap/venv/bin/python

from flup.server.fcgi import WSGIServer
from app import app as application

WSGIServer(application).run()
