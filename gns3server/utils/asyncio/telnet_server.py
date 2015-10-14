# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 GNS3 Technologies Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import asyncio.subprocess

import logging
log = logging.getLogger(__name__)


class AsyncioTelnetServer:
    def __init__(self, reader=None, writer=None):
        self._reader = reader
        self._writer = writer

    @asyncio.coroutine
    def run(self, network_reader, network_writer):
        network_read = asyncio.async(network_reader.readline())
        reader_read = asyncio.async(self._reader.readline())

        while True:
            done, pending = yield from asyncio.wait(
                [
                    network_read,
                    reader_read
                ],
                return_when=asyncio.FIRST_COMPLETED)
            for coro in done:
                data = coro.result()
                if coro == network_read:
                    network_read = asyncio.async(network_reader.readline())
                    self._writer.write(data)
                    yield from self._writer.drain()
                elif coro == reader_read:
                    reader_read = asyncio.async(self._reader.readline())
                    network_writer.write(data)
                    yield from network_writer.drain()
                #TODO: manage EOF

if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    process = loop.run_until_complete(asyncio.async(asyncio.subprocess.create_subprocess_exec("bash",
                                                                                              stdout=asyncio.subprocess.PIPE,
                                                                                              stderr=asyncio.subprocess.STDOUT,
                                                                                              stdin=asyncio.subprocess.PIPE)))
    server = AsyncioTelnetServer(reader=process.stdout, writer=process.stdin)

    coro = asyncio.start_server(server.run, '127.0.0.1', 2222, loop=loop)
    s = loop.run_until_complete(coro)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    # Close the server
    s.close()
    loop.run_until_complete(s.wait_closed())
    loop.close()
