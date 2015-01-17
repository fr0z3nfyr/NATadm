#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2014 Mariusz Pluciński
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import collections
import imp
import logging
import os.path
import ssl
import sys
import time


current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)
sys.path.insert(0, os.path.dirname(current_dir))

import tornado.gen
import tornado.ioloop
import tornado.options
import tornado.tcpclient

import common.protocol
import common.proxy

CONFIG_FILE = 'NATadm.conf'

tornado.options.define('name', type=str)
tornado.options.define('remote', type=tuple)
tornado.options.define('cafile', type=str)
tornado.options.define('interval', type=int, default=60)
tornado.options.define('infinite', type=bool, default=False)

tornado.options.parse_config_file(CONFIG_FILE, False)
tornado.options.parse_command_line()

def unexpected_package(package):
	raise Exception('Unexpected package: '+package)

@tornado.gen.coroutine
def tunnel(client, stream, port):
	logging.debug('Requested to create tunnel with local port {}'.format(port))

	package = yield common.protocol.package.read(stream)
	if not isinstance(package, common.protocol.connect):
		unexpected_package(package)

	logging.info('Connecting with local port {}...'.format(port))
	local_client = tornado.tcpclient.TCPClient()
	local_stream = yield client.connect(
		'localhost', port
	)

	logging.info('Connection established with local port {}'.format(port))
	proxy = common.proxy.Proxy(stream, local_stream)
	yield proxy.run()

	logging.debug('Closing tunnel...')
	yield common.protocol.disconnect().write(stream)

@tornado.gen.coroutine
def main():
	while True:
		try:
			remote = tornado.options.options.remote
			logging.info('Trying to connect {}:{} (client name "{}")...'.format(remote[0], remote[1], tornado.options.options.name))
			client = tornado.tcpclient.TCPClient()
			stream = yield client.connect(
				remote[0], remote[1], ssl_options=dict(
					ca_certs = tornado.options.options.cafile,
					cert_reqs = ssl.CERT_REQUIRED
				)
			)
			logging.debug('Connection established')
			yield common.protocol.hello(tornado.options.options.name).write(stream)

			package = yield common.protocol.package.read(stream)
			if isinstance(package, common.protocol.create_tunnel):
				tornado.ioloop.IOLoop.instance().add_callback(tunnel, client, stream, package.port)
			elif isinstance(package, common.protocol.not_interested):
				logging.info('Nobody interested in tunnel, disconnecting')
				stream.close()
			else:
				unexpected_package(package)

		except Exception as e:
			logging.exception(e)

		if not tornado.options.options.infinite:
			tornado.ioloop.IOLoop.instance().stop()
			break

		logging.warning('Waiting until next trial')
		yield tornado.gen.Task(
			tornado.ioloop.IOLoop.instance().add_timeout,
			time.time()+tornado.options.options.interval
		)


io_loop = tornado.ioloop.IOLoop.instance()
io_loop.add_callback(main)
io_loop.start()
