# Copyright 2020-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import multiprocessing
import sys

import portage
from portage import os
from portage.tests import TestCase
from portage.util._async.AsyncFunction import AsyncFunction
from portage.util.futures import asyncio
from portage.util.futures._asyncio.streams import _writer
from portage.util.futures.unix_events import _set_nonblocking


class AsyncFunctionTestCase(TestCase):
    @staticmethod
    def _read_from_stdin(pr, pw):
        if pw is not None:
            os.close(pw)
        os.dup2(pr.fileno(), sys.stdin.fileno())
        return "".join(sys.stdin)

    async def _testAsyncFunctionStdin(self, loop):
        test_string = "1\n2\n3\n"
        pr, pw = multiprocessing.Pipe(duplex=False)
        reader = AsyncFunction(
            scheduler=loop,
            target=self._read_from_stdin,
            args=(
                pr,
                pw.fileno() if multiprocessing.get_start_method() == "fork" else None,
            ),
        )
        reader.start()
        pr.close()
        _set_nonblocking(pw.fileno())
        with open(pw.fileno(), mode="wb", buffering=0, closefd=False) as pipe_write:
            await _writer(pipe_write, test_string.encode("utf_8"))
        pw.close()
        self.assertEqual((await reader.async_wait()), os.EX_OK)
        self.assertEqual(reader.result, test_string)

    def testAsyncFunctionStdin(self):
        loop = asyncio._wrap_loop()
        loop.run_until_complete(self._testAsyncFunctionStdin(loop=loop))

    @staticmethod
    def _test_getpid_fork():
        """
        Verify that portage.getpid() cache is updated in a forked child process.
        """
        loop = asyncio._wrap_loop()
        proc = AsyncFunction(scheduler=loop, target=portage.getpid)
        proc.start()
        proc.wait()
        return proc.pid == proc.result

    def test_getpid_fork(self):
        self.assertTrue(self._test_getpid_fork())

    def test_getpid_double_fork(self):
        """
        Verify that portage.getpid() cache is updated correctly after
        two forks.
        """
        loop = asyncio._wrap_loop()
        proc = AsyncFunction(scheduler=loop, target=self._test_getpid_fork)
        proc.start()
        self.assertEqual(proc.wait(), 0)
        self.assertTrue(proc.result)
