# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 GNS3 Technologies Inc.
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

"""
Docker container instance.
"""

import sys
import shlex
import re
import os
import tempfile
import json
import socket
import asyncio
import docker
import netifaces
import subprocess
import configparser
import signal

from docker.utils import create_host_config

from gns3server.utils.asyncio import wait_for_process_termination
from gns3server.utils.asyncio import monitor_process
from pkg_resources import parse_version
from .docker_error import DockerError
from ..base_vm import BaseVM
from ..adapters.ethernet_adapter import EthernetAdapter
from ..nios.nio_udp import NIOUDP

import logging
log = logging.getLogger(__name__)


class Container(BaseVM):
    """Docker container implementation.

    :param name: Docker container name
    :param project: Project instance
    :param manager: Manager instance
    :param image: Docker image
    """
    def __init__(self, name, vm_id, project, manager, image):
        self._name = name
        self._id = vm_id
        self._project = project
        self._manager = manager
        self._image = image
        self._temporary_directory = None
        self._ethernet_adapters = []
        self._ubridge_process = None
        self._ubridge_stdout_file = ""

        log.debug(
            "{module}: {name} [{image}] initialized.".format(
                module=self.manager.module_name,
                name=self.name,
                image=self._image))

    def __json__(self):
        return {
            "name": self._name,
            "vm_id": self._id,
            "cid": self._cid,
            "project_id": self._project.id,
            "image": self._image,
        }

    @asyncio.coroutine
    def _get_container_state(self):
        """Returns the container state (e.g. running, paused etc.)

        :returns: state
        :rtype: str
        """
        try:
            result = yield from self.manager.execute(
                "inspect_container", {"container": self._cid})
            result_dict = {state.lower(): value for state, value in result["State"].items()}
            for state, value in result_dict.items():
                if value is True:
                    # a container can be both paused and running
                    if state == "paused":
                        return "paused"
                    if state == "running":
                        if "paused" in result_dict and result_dict["paused"] is True:
                            return "paused"
                    return state.lower()
            return 'exited'
        except Exception as err:
            raise DockerError("Could not get container state for {0}: ".format(
                self._name), str(err))

    @asyncio.coroutine
    def create(self):
        """Creates the Docker container."""
        result = yield from self.manager.execute(
            "create_container", {
                "name": self._name,
                "image": self._image,
                "network_disabled": True,
                "host_config": create_host_config(
                    privileged=True, cap_add=['ALL'])
            }
        )
        self._cid = result['Id']
        log.info("Docker container '{name}' [{id}] created".format(
            name=self._name, id=self._id))
        return True

    def _update_ubridge_config(self):
        """Updates the ubrige.ini file."""

        ubridge_ini = os.path.join(self.working_dir, "ubridge.ini")
        config = configparser.ConfigParser()
        for adapter_number in range(0, self.adapters):
            adapter = self._ethernet_adapters[adapter_number]
            nio = adapter.get_nio(0)
            if nio:
                bridge_name = "bridge{}".format(adapter_number)

                if sys.platform.startswith("linux"):
                    config[bridge_name] = {"source_linux_raw": adapter.host_ifc}

                if isinstance(nio, NIOUDP):
                    udp_tunnel_info = {
                        "destination_udp": "{lport}:{rhost}:{rport}".format(
                            lport=nio.lport,
                            rhost=nio.rhost,
                            rport=nio.rport)}
                    config[bridge_name].update(udp_tunnel_info)

                if nio.capturing:
                    capture_info = {"pcap_file": "{pcap_file}".format(
                        pcap_file=nio.pcap_output_file)}
                    config[bridge_name].update(capture_info)
        try:
            with open(ubridge_ini, "w", encoding="utf-8") as config_file:
                config.write(config_file)
            log.info(
                'Docker VM "{name}" [id={id}]: ubridge.ini updated'.format(
                    name=self._name, id=self._id))
        except OSError as e:
            raise DockerError("Could not create {}: {}".format(ubridge_ini, e))

    @property
    def ubridge_path(self):
        """Returns the uBridge executable path.

        :returns: path to uBridge
        """
        path = self._manager.config.get_section_config("Server").get(
            "ubridge_path", "ubridge")
        if path == "ubridge":
            path = shutil.which("ubridge")
        return path

    @asyncio.coroutine
    def _start_ubridge(self):
        """Starts uBridge (handles connections to and from this Docker VM)."""

        try:
            command = [self.ubridge_path]
            log.info("starting ubridge: {}".format(command))
            self._ubridge_stdout_file = os.path.join(
                self.working_dir, "ubridge.log")
            log.info("logging to {}".format(self._ubridge_stdout_file))
            os.system("touch %s/ubridge.ini" % self.working_dir)
            with open(self._ubridge_stdout_file, "w", encoding="utf-8") as fd:
                self._ubridge_process = yield from asyncio.create_subprocess_exec(
                    *command,
                    stdout=fd,
                    stderr=subprocess.STDOUT,
                    cwd=self.working_dir)

                monitor_process(
                    self._ubridge_process, self._termination_callback)
            log.info("ubridge started PID={}".format(
                self._ubridge_process.pid))
        except (OSError, subprocess.SubprocessError) as e:
            ubridge_stdout = self.read_ubridge_stdout()
            log.error("Could not start ubridge: {}\n{}".format(
                e, ubridge_stdout))
            raise DockerError("Could not start ubridge: {}\n{}".format(
                e, ubridge_stdout))

    def _termination_callback(self, returncode):
        """Called when the process has stopped.

        :param returncode: Process returncode
        """
        log.info("uBridge process has stopped, return code: %d", returncode)

    def is_ubridge_running(self):
        """Checks if the ubridge process is running

        :returns: True or False
        :rtype: bool
        """
        if self._ubridge_process and self._ubridge_process.returncode is None:
            return True
        return False

    def read_ubridge_stdout(self):
        """
        Reads the standard output of the uBridge process.
        Only use when the process has been stopped or has crashed.
        """

        output = ""
        if self._ubridge_stdout_file:
            try:
                with open(self._ubridge_stdout_file, "rb") as file:
                    output = file.read().decode("utf-8", errors="replace")
            except OSError as e:
                log.warn("could not read {}: {}".format(
                    self._ubridge_stdout_file, e))
        return output

    def _terminate_process_ubridge(self):
        """Terminate the ubridge process if running."""

        if self._ubridge_process:
            log.info(
                'Stopping uBridge process for Docker container "{}" PID={}'.format(
                    self.name, self._ubridge_process.pid))
            try:
                self._ubridge_process.terminate()
            # Sometime the process can already be dead when we garbage collect
            except ProcessLookupError:
                pass

    @asyncio.coroutine
    def start(self):
        """Starts this Docker container."""

        ubridge_path = self.ubridge_path
        if not ubridge_path or not os.path.isfile(ubridge_path):
            raise DockerError("ubridge is necessary to start a Docker VM")
        yield from self._start_ubridge()

        state = yield from self._get_container_state()
        if state == "paused":
            yield from self.unpause()
        else:
            result = yield from self.manager.execute(
                "start", {"container": self._cid})
        log.info("Docker container '{name}' [{image}] started".format(
            name=self._name, image=self._image))

    def is_running(self):
        """Checks if the container is running.

        :returns: True or False
        :rtype: bool
        """
        state = yield from self._get_container_state()
        if state == "running":
            return True
        return False

    @asyncio.coroutine
    def restart(self):
        """Restarts this Docker container."""
        result = yield from self.manager.execute(
            "restart", {"container": self._cid})
        log.info("Docker container '{name}' [{image}] restarted".format(
            name=self._name, image=self._image))

    @asyncio.coroutine
    def stop(self):
        """Stops this Docker container."""

        if self.is_ubridge_running():
            self._terminate_process_ubridge()
            try:
                yield from wait_for_process_termination(
                    self._ubridge_process, timeout=3)
            except asyncio.TimeoutError:
                if self._ubridge_process.returncode is None:
                    log.warn(
                        "uBridge process {} is still running... killing it".format(
                            self._ubridge_process.pid))
                    self._ubridge_process.kill()
            self._ubridge_process = None

        state = yield from self._get_container_state()
        if state == "paused":
            yield from self.unpause()
        result = yield from self.manager.execute(
            "kill", {"container": self._cid})
        log.info("Docker container '{name}' [{image}] stopped".format(
            name=self._name, image=self._image))

    @asyncio.coroutine
    def pause(self):
        """Pauses this Docker container."""
        result = yield from self.manager.execute(
            "pause", {"container": self._cid})
        log.info("Docker container '{name}' [{image}] paused".format(
            name=self._name, image=self._image))

    @asyncio.coroutine
    def unpause(self):
        """Unpauses this Docker container."""
        result = yield from self.manager.execute(
            "unpause", {"container": self._cid})
        state = yield from self._get_container_state()
        log.info("Docker container '{name}' [{image}] unpaused".format(
            name=self._name, image=self._image))

    @asyncio.coroutine
    def remove(self):
        """Removes this Docker container."""
        state = yield from self._get_container_state()
        if state == "paused":
            yield from self.unpause()
        if state == "running":
            yield from self.stop()
        result = yield from self.manager.execute(
            "remove_container", {"container": self._cid, "force": True})
        log.info("Docker container '{name}' [{image}] removed".format(
            name=self._name, image=self._image))

    @asyncio.coroutine
    def close(self):
        """Closes this Docker container."""
        log.debug("Docker container '{name}' [{id}] is closing".format(
            name=self.name, id=self._cid))
        for adapter in self._ethernet_adapters.values():
            if adapter is not None:
                for nio in adapter.ports.values():
                    if nio and isinstance(nio, NIOUDP):
                        self.manager.port_manager.release_udp_port(
                            nio.lport, self._project)

        yield from self.remove()

        log.info("Docker container '{name}' [{id}] closed".format(
            name=self.name, id=self._cid))
        self._closed = True

    def _reload_ubridge(self):
        """Reloads ubridge."""
        if self.is_ubridge_running():
            self._update_ubridge_config()
            os.kill(self._ubridge_process.pid, signal.SIGHUP)

    def adapter_add_nio_binding(self, adapter_number, nio):
        """Adds an adapter NIO binding.

        :param adapter_number: adapter number
        :param nio: NIO instance to add to the slot/port
        """
        try:
            adapter = self._ethernet_adapters[adapter_number]
        except IndexError:
            raise DockerError(
                "Adapter {adapter_number} doesn't exist on Docker container '{name}'".format(
                    name=self.name, adapter_number=adapter_number))

        if nio and isinstance(nio, NIOUDP):
            ifcs = netifaces.interfaces()
            for index in range(128):
                ifcs = netifaces.interfaces()
                if "gns3-veth{}ext".format(index) not in ifcs:
                    adapter.ifc = "eth{}".format(str(index))
                    adapter.host_ifc = "gns3-veth{}ext".format(str(index))
                    adapter.guest_ifc = "gns3-veth{}int".format(str(index))
                    break
            if not hasattr(adapter, "ifc"):
                raise DockerError(
                    "Adapter {adapter_number} couldn't allocate interface on Docker container '{name}'".format(
                        name=self.name, adapter_number=adapter_number))
            os.system("sudo ip link add {} type veth peer name {}".format(
                adapter.host_ifc, adapter.guest_ifc))
        adapter.add_nio(0, nio)
        self._reload_ubridge()
        log.info(
            "Docker container '{name}' [{id}]: {nio} added to adapter {adapter_number}".format(
                name=self.name,
                id=self._id,
                nio=nio,
                adapter_number=adapter_number))
        return nio

    def adapter_remove_nio_binding(self, adapter_number):
        """Removes an adapter NIO binding.

        :param adapter_number: adapter number

        :returns: NIO instance
        """

        try:
            adapter = self._ethernet_adapters[adapter_number]
        except IndexError:
            raise DockerError(
                "Adapter {adapter_number} doesn't exist on Docker container '{name}'".format(
                    name=self.name, adapter_number=adapter_number))
        try:
            os.system("sudo ip link del {}".format(adapter.host_ifc))
        except:
            pass
        nio = adapter.get_nio(0)
        adapter.remove_nio(0)
        self._reload_ubridge()

        log.info("Docker container '{name}' [{id}]: {nio} removed from adapter {adapter_number}".format(
            name=self.name, id=self.id, nio=nio,
            adapter_number=adapter_number))

    @property
    def adapters(self):
        """Returns the number of Ethernet adapters for this QEMU VM.

        :returns: number of adapters
        :rtype: int
        """
        return len(self._ethernet_adapters)

    @adapters.setter
    def adapters(self, adapters):
        """Sets the number of Ethernet adapters for this Docker container.

        :param adapters: number of adapters
        """

        self._ethernet_adapters.clear()
        for adapter_number in range(0, adapters):
            self._ethernet_adapters.append(EthernetAdapter())

        log.info(
            'Docker container "{name}" [{id}]: number of Ethernet adapters changed to {adapters}'.format(
                name=self._name,
                id=self._id,
                adapters=adapters))

    def get_namespace(self):
        result = yield from self.manager.execute(
            "inspect_container", {"container": self._cid})
        return int(result['State']['Pid'])

    def change_netnamespace(self, adapter):
        ns = self.get_namespace()
        os.system("sudo rm -f /var/run/netns/%s" % ns)
        os.system("sudo ln -s /proc/{0}/ns/net /var/run/netns/{0}".format(ns))
        os.system("sudo ip link set {guest_ifc} netns {netns}".format(
            netns=ns, guest_ifc=adapter.guest_ifc))
        os.system("sudo ip netns exec {netns} ip link set {guest_ifc} name {ifc}".format(
            netns=ns, guest_ifc=adapter.guest_ifc, ifc=adapter.ifc))
