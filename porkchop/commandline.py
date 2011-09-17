import logging
from optparse import OptionParser
from server import GetHandler
import sys

from porkchop.plugin import PorkchopPluginHandler
from porkchop.server import GetHandler, ThreadedHTTPServer

def coerce_number(s):
  try:
    return int(s)
  except:
    return float(s)

def get_logger(level = logging.INFO):
  logger = logging.getLogger('porkchop')
  logger.setLevel(logging.DEBUG)
  ch = logging.StreamHandler()
  ch.setLevel(level)
  formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
  ch.setFormatter(formatter)
  logger.addHandler(ch)

  return logger

def main():
  plugin_dir = '/usr/share/porkchop/plugins'
  listen_address = ''
  listen_port = 5000

  parser = OptionParser()
  parser.add_option('-d', dest='plugindir',
                    default=plugin_dir,
                    help='Load plugins from DIR (default: %s)' % plugin_dir,
                    metavar='DIR')
  parser.add_option('-s', dest='listen_address',
                    default=listen_address,
                    help='Bind to ADDRESS', metavar='ADDRESS')
  parser.add_option('-p', type="int", dest='listen_port',
                    default=listen_port,
                    help='Bind to PORT (default: %d)' % listen_port,
                    metavar='PORT')
  parser.add_option('-v', dest='verbose',
                    default=False,
                    help='Verbose logging',
                    action='store_true')

  (options, args) = parser.parse_args()

  if options.verbose:
    logger = get_logger(logging.DEBUG)
  else:
    logger = get_logger()

  PorkchopPluginHandler(options.plugindir)
  server = ThreadedHTTPServer((options.listen_address, options.listen_port),
                              GetHandler)
  server.serve_forever()

def collector():
  import requests
  import socket
  import sys
  import time

  carbon_host = 'localhost'
  carbon_port = 2003
  porkchop_url = 'http://localhost:5000/'

  interval = 10
  prefix = 'porkchop.%s' % socket.gethostname().split('.')[0].replace('.','_')

  parser = OptionParser()
  parser.add_option('--carbon-host', dest='carbon_host',
                    default=carbon_host,
                    help='Connect to carbon on HOST (default: %s)' % carbon_host,
                    metavar='HOST')
  parser.add_option('--carbon-port', type='int', dest='carbon_port',
                    default=carbon_port,
                    help='Connect to carbon on PORT (default: %d)' % carbon_port,
                    metavar='PORT')
  parser.add_option('--porkchop-url', dest='porkchop_url',
                    default=porkchop_url,
                    help='Connect to porkchop on URL (default: %s)' % porkchop_url,
                    metavar='URL')
  parser.add_option('-i', type='int', dest='interval',
                    default=interval,
                    help='Fetch data at INTERVAL (default: %d)' % interval,
                    metavar='INTERVAL')
  parser.add_option('-n', dest='noop',
                    default=False,
                    help='Don\'t actually send to graphite',
                    action='store_true')
  parser.add_option('-P', dest='prefix',
                    default=prefix,
                    help='Graphite prefix (default: %s)' % prefix)
  parser.add_option('-v', dest='verbose',
                    default=False,
                    help='Verbose logging',
                    action='store_true')


  (options, args) = parser.parse_args()

  if options.verbose:
    logger = get_logger(logging.DEBUG)
  else:
    logger = get_logger()

  if not options.noop:
    carbon = Carbon(options.carbon_host, options.carbon_port, logger)

  while True:
    try:
      logger.debug('Fetching porkchop data from %s', options.porkchop_url)
      r = requests.get(options.porkchop_url)
      r.raise_for_status()
      lines = []
      now = int(time.time())
      for line in r.content.strip('\n').splitlines():
        (key, val) = line.lstrip('/').split(' ', 1)
        key = '.'.join([options.prefix, key.replace('/', '.')])
        try:
          if not options.noop:
            carbon.data.append((key, coerce_number(val), now))
        except:
          pass

      if not options.noop:
        carbon.send()
    except:
      logger.error('Got bad response code from porkchop: %s', sys.exc_info()[1])

    logger.debug('Sleeping for %d', options.interval)
    time.sleep(options.interval)

class Carbon(object):
  def __init__(self, host, port, logger):
    self.data = []
    self.host = host
    self.port = port
    self.logger = logger
    try:
      self.sock = self._connect()
    except socket.error:
      self.logger.fatal('Unable to connect to carbon.')

  def _connect(self):
    import socket
    self.logger.info('Connecting to carbon on %s:%d', self.host, self.port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((self.host, self.port))

    return sock

  def send(self):
    self.logger.info('Sending to carbon.')
    try:
      for met in self.data:
        self.logger.debug(met)
      self.sock.sendall('\n'.join(['%s %s %s' % met for met in self.data]))
    except socket.socket.error:
      self.logger.error('Error send to carbon, trying to reconnect.')
      self.sock = self._connect()
