import sys
from omero.gateway import BlitzGateway
HOST = 'ws://idr.openmicroscopy.org/omero-ws'
conn = BlitzGateway('public', 'public',
                    host=HOST, secure=True)
if conn.connect() is True:
    print("connected")
    conn.close()
else:
    print("Connection failed")
sys.exit()
