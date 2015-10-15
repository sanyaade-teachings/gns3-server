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

import pytest
import os
import stat
import sys
import uuid
import aiohttp

from tests.utils import asyncio_patch
from unittest.mock import patch, MagicMock, PropertyMock


@pytest.fixture
def base_params():
    """Return standard parameters"""
    return {"name": "PC TEST 1", "image": "nginx", "command": "nginx-daemon"}


@pytest.fixture
def vm(server, project, base_params):
    with asyncio_patch("gns3server.modules.docker.Docker.execute", return_value={"Id": "8bd8153ea8f5"}) as mock:
        response = server.post("/projects/{project_id}/docker/vms".format(project_id=project.id), base_params)
    print(response.body)
    assert response.status == 201
    return response.json


def test_docker_create(server, project, base_params):
    with asyncio_patch("gns3server.modules.docker.Docker.execute", return_value={"Id": "8bd8153ea8f5"}) as mock:
        response = server.post("/projects/{project_id}/docker/vms".format(project_id=project.id), base_params)
    assert response.status == 201
    assert response.route == "/projects/{project_id}/docker/vms"
    assert response.json["name"] == "PC TEST 1"
    assert response.json["project_id"] == project.id
    assert response.json["container_id"] == "8bd8153ea8f5"
    assert response.json["image"] == "nginx"


def test_docker_start(server, vm):
    with asyncio_patch("gns3server.modules.docker.docker_vm.Container.start", return_value=True) as mock:
        response = server.post("/projects/{project_id}/docker/vms/{vm_id}/start".format(project_id=vm["project_id"], vm_id=vm["vm_id"]))
        assert mock.called
        assert response.status == 204


def test_docker_stop(server, vm):
    with asyncio_patch("gns3server.modules.docker.docker_vm.Container.stop", return_value=True) as mock:
        response = server.post("/projects/{project_id}/docker/vms/{vm_id}/stop".format(project_id=vm["project_id"], vm_id=vm["vm_id"]))
        assert mock.called
        assert response.status == 204


def test_docker_reload(server, vm):
    with asyncio_patch("gns3server.modules.docker.docker_vm.Container.restart", return_value=True) as mock:
        response = server.post("/projects/{project_id}/docker/vms/{vm_id}/reload".format(project_id=vm["project_id"], vm_id=vm["vm_id"]))
        assert mock.called
        assert response.status == 204


def test_docker_delete(server, vm):
    with asyncio_patch("gns3server.modules.docker.docker_vm.Container.remove", return_value=True) as mock:
        response = server.delete("/projects/{project_id}/docker/vms/{vm_id}".format(project_id=vm["project_id"], vm_id=vm["vm_id"]))
        assert mock.called
        assert response.status == 204


def test_docker_reload(server, vm):
    with asyncio_patch("gns3server.modules.docker.docker_vm.Container.pause", return_value=True) as mock:
        response = server.post("/projects/{project_id}/docker/vms/{vm_id}/suspend".format(project_id=vm["project_id"], vm_id=vm["vm_id"]))
        assert mock.called
        assert response.status == 204


def test_docker_nio_create_udp(server, vm):
    response = server.post("/projects/{project_id}/docker/vms/{vm_id}/adapters/0/ports/0/nio".format(project_id=vm["project_id"], vm_id=vm["vm_id"]), {"type": "nio_udp",
                                                                                                                                                       "lport": 4242,
                                                                                                                                                       "rport": 4343,
                                                                                                                                                       "rhost": "127.0.0.1"},
                           example=True)
    assert response.status == 201
    assert response.route == "/projects/{project_id}/docker/vms/{vm_id}/adapters/{adapter_number:\d+}/ports/{port_number:\d+}/nio"
    assert response.json["type"] == "nio_udp"


def test_docker_delete_nio(server, vm):
    server.post("/projects/{project_id}/docker/vms/{vm_id}/adapters/0/ports/0/nio".format(project_id=vm["project_id"], vm_id=vm["vm_id"]), {"type": "nio_udp",
                                                                                                                                            "lport": 4242,
                                                                                                                                            "rport": 4343,
                                                                                                                                            "rhost": "127.0.0.1"})
    response = server.delete("/projects/{project_id}/docker/vms/{vm_id}/adapters/0/ports/0/nio".format(project_id=vm["project_id"], vm_id=vm["vm_id"]), example=True)
    assert response.status == 204
    assert response.route == "/projects/{project_id}/docker/vms/{vm_id}/adapters/{adapter_number:\d+}/ports/{port_number:\d+}/nio"
