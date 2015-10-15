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


DOCKER_CREATE_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "Request validation to create a new Docker container",
    "type": "object",
    "properties": {
        "vm_id": {
            "description": "Docker VM instance identifier",
            "type": "string",
            "minLength": 36,
            "maxLength": 36,
            "pattern": "^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$"
        },
        "name": {
            "description": "Docker container name",
            "type": "string",
            "minLength": 1,
        },
        "command": {
            "description": "Docker CMD entry",
            "type": "string",
            "minLength": 1,
        },
        "image": {
            "description": "Docker image name",
            "type": "string",
            "minLength": 1,
        },
    },
    "additionalProperties": False,
}

DOCKER_OBJECT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "Docker instance",
    "type": "object",
    "properties": {
        "name": {
            "description": "Docker container name",
            "type": "string",
            "minLength": 1,
        },
        "vm_id": {
            "description": "Docker container instance UUID",
            "type": "string",
            "minLength": 36,
            "maxLength": 36,
            "pattern": "^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$"
        },
        "container_id": {
            "description": "Docker container ID",
            "type": "string",
            "minLength": 12,
            "maxLength": 12,
            "pattern": "^[a-f0-9]{12}$"
        },
        "project_id": {
            "description": "Project UUID",
            "type": "string",
            "minLength": 36,
            "maxLength": 36,
            "pattern": "^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$"
        },
        "image": {
            "description": "Docker image name",
            "type": "string",
            "minLength": 1,
        }
    },
    "additionalProperties": False,
    "required": ["vm_id", "project_id"]
}
