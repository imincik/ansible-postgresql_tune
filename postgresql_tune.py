#!/usr/bin/env python

################################################################################
#
# Copyright 2013 Crown copyright (c)
# Land Information New Zealand and the New Zealand Government.
# All rights reserved
#
# This program is released under the terms of the new BSD license. See the
# LICENSE file for more information.
#
# Computing logic is based on http://pgtune.leopard.in.ua, developed by
# Alexey Vasiliev and released under MIT license.
#
################################################################################

# Hacking:
#   ansible/hacking/test-module -m postgresql_tune.py \
#   -a " \
#   db_version=9.3 \
#   db_type=dw \
#   total_memory=1000 \
#   max_connections=50 \
#   postgresql_file=/tmp/postgresql_tune.conf \
#   sysctl_file=/tmp/sysctl_tune.conf \
#"

# TODO: detect configuration files changes. Now changed: True is always returned

import math
from ansible.module_utils.basic import *


DOCUMENTATION = '''
---
module: postgresql_tune
short_description: Generate PostgreSQL configuration
description:
    - Generate PostgreSQL and kernel configuration (if required) according
      server parameters

options:
    db_version:
        description
            - PostgreSQL version.
              Format: float number (ex.: 9.3).
        required: True
        default: null

    db_type:
        description
            - Database usage type.
              Options:
               web: web applications
               oltp: online transactions processing systems
               dw: data warehouses
               desktop: desktop applications
               mixed: mixed type of applications
        required: True
        default: null

    total_memory:
        description
            - Total memory usable for PostgreSQL on server.
              Format: (1-9999)('MB' | GB')
        required: False
        default: Calculated

    total_memory_percentage:
        description
            - Tune based on a percentage of the total_memory.
              Format: 1-100
        required: False
        default: 100

    max_connections:
        description
            - Maximum number of PostgreSQL client's connections.
              Format: integer number (ex.: 100)
        required: True
        default: null

    disable_max_connections:
        description
            - Stop max_connections being passed down to the generated Postgresql config.
              Useful to tune to a certain number of connections but allow a higher max.
              Format: false|true
        required: false
        default: false

'''


CONST_SIZE = {
    'KB': 1024,
    'MB': 1048576,
    'GB': 1073741824,
    'TB': 1099511627776,
    'KB_PER_GB': 1048576,
    'KB_PER_MB': 1024
}

CON_BY_TYPE = {
    'web': 200,
    'oltp': 300,
    'dw': 20,
    'desktop': 5,
    'mixed': 100
}


def postgres_settings(
        db_version,
        os_type,
        db_type,
        total_memory,
        max_connections=None):
    """Generate PostgreSQL configuration"""

    config = {}

    # validate max_connections
    if not max_connections or max_connections < 1 or max_connections > 9999:
        config['max_connections'] = CON_BY_TYPE[db_type]
    else:
        config['max_connections'] = max_connections

    memory_in_KB = total_memory / CONST_SIZE['KB']

    # this tool not being optimal for low memory systems
    if total_memory >= (256 * CONST_SIZE['MB']):
        # shared_buffers
        config['shared_buffers'] = {
            'web': math.floor(memory_in_KB / 4),
            'oltp': math.floor(memory_in_KB / 4),
            'dw': math.floor(memory_in_KB / 4),
            'desktop': math.floor(memory_in_KB / 16),
            'mixed': math.floor(memory_in_KB / 4)
        }[db_type]

        # limit shared_buffers to 512MB on Windows
        if os_type == 'windows' \
                and config['shared_buffers'] > (512 * CONST_SIZE['MB'] / CONST_SIZE['KB']):
            config['shared_buffers'] = 512 * CONST_SIZE['MB'] / CONST_SIZE['KB']

        # and not more, whan 8GB for linux
        # not true right now for new versions
        #elif os_type != 'windows' \
        #        and config['shared_buffers'] > (8 * CONST_SIZE['GB'] / CONST_SIZE['KB']):
        #    config['shared_buffers'] = (8 * CONST_SIZE['GB'] / CONST_SIZE['KB'])

        # effective_cache_size
        config['effective_cache_size'] = {
            'web': math.floor(memory_in_KB * 3 / 4),
            'oltp': math.floor(memory_in_KB * 3 / 4),
            'dw': math.floor(memory_in_KB * 3 / 4),
            'desktop': math.floor(memory_in_KB / 4),
            'mixed': math.floor(memory_in_KB * 3 / 4)
        }[db_type]

        # work_mem is assigned any time a query calls for a sort, or a hash,
        # or any other structure that needs a space allocation, which can happen
        # multiple times per query. So you're better off assuming
        # max_connections * 2 or max_connections * 3 is the amount of RAM that
        # will actually use in reality. At the very least, you need to
        # subtract shared_buffers from the amount you're distributing to
        # connections in work_mem.
        # The other thing to consider is that there's no reason to run on the
        # edge of available memory. If you do that, there's a very high risk
        # the out-of-memory killer will come along and start killing PostgreSQL
        # backends. Always leave a buffer of some kind in case of spikes
        # in memory usage. So your maximum amount of memory available in
        # work_mem should be ((RAM - shared_buffers) / 2 / (max_connections * 3)).
        work_mem = (memory_in_KB - config['shared_buffers']) / (config['max_connections'] * 3)
        config['work_mem'] = {
            'web': math.floor(work_mem),
            'oltp': math.floor(work_mem),
            'dw': math.floor(work_mem / 2),
            'desktop': math.floor(work_mem / 6),
            'mixed': math.floor(work_mem / 2)
        }[db_type]

        # maintenance_work_mem
        config['maintenance_work_mem'] = {
            'web': math.floor(memory_in_KB / 16),
            'oltp': math.floor(memory_in_KB / 16),
            'dw': math.floor(memory_in_KB / 8),
            'desktop': math.floor(memory_in_KB / 16),
            'mixed': math.floor(memory_in_KB / 16)
        }[db_type]

        # Cap maintenance RAM at 2GB on servers with lots of memory
        if config['maintenance_work_mem'] > (2 * CONST_SIZE['GB'] / CONST_SIZE['KB']):
            config['maintenance_work_mem'] = math.floor(2 * CONST_SIZE['GB'] / CONST_SIZE['KB'])

        # such setting can be even bad for very high memory systems, need show
        # warnings
        if total_memory >= (100 * CONST_SIZE['GB']):
            print ("# WARNING: not optimal for very high memory systems")
    else:
        print ("# WARNING: not optimal for very high memory systems")

    if db_version < 9.5:
        # checkpoint_segments
        config['checkpoint_segments'] = {
            'web': 32,
            'oltp': 64,
            'dw': 128,
            'desktop': 3,
            'mixed': 32
        }[db_type]
    else:
        config['min_wal_size'] = {
            'web': (1024 * CONST_SIZE['MB'] / CONST_SIZE['KB']),
            'oltp': (2048 * CONST_SIZE['MB'] / CONST_SIZE['KB']),
            'dw': (4096 * CONST_SIZE['MB'] / CONST_SIZE['KB']),
            'desktop': (100 * CONST_SIZE['MB'] / CONST_SIZE['KB']),
            'mixed': (1024 * CONST_SIZE['MB'] / CONST_SIZE['KB'])
        }[db_type]
        config['max_wal_size'] = {
            'web': (2048 * CONST_SIZE['MB'] / CONST_SIZE['KB']),
            'oltp': (4096 * CONST_SIZE['MB'] / CONST_SIZE['KB']),
            'dw': (8192 * CONST_SIZE['MB'] / CONST_SIZE['KB']),
            'desktop': (100 * CONST_SIZE['MB'] / CONST_SIZE['KB']),
            'mixed': (2048 * CONST_SIZE['MB'] / CONST_SIZE['KB'])
        }[db_type]

    # checkpoint_completion_target
    config['checkpoint_completion_target'] = {
        'web': 0.7,
        'oltp': 0.9,
        'dw': 0.9,
        'desktop': 0.5,
        'mixed': 0.9
    }[db_type]

    # wal_buffers
    # Follow auto-tuning guideline for wal_buffers added in 9.1, where it's
    # set to 3% of shared_buffers up to a maximum of 16MB.
    if 'shared_buffers' in config:
        config['wal_buffers'] = math.floor(3 * config['shared_buffers'] / 100)
        if config['wal_buffers'] > (16 * CONST_SIZE['MB'] / CONST_SIZE['KB']):
            config['wal_buffers'] = math.floor(16 * CONST_SIZE['MB'] / CONST_SIZE['KB'])

        # It's nice of wal_buffers is an even 16MB if it's near that number.
        # Since that is a common case on Windows, where shared_buffers is
        # clipped to 512MB, round upwards in that situation
        if (14 * CONST_SIZE['MB'] / CONST_SIZE['KB']) < config['wal_buffers'] \
                and config['wal_buffers'] < (16 * CONST_SIZE['MB'] / CONST_SIZE['KB']):
            config['wal_buffers'] = math.floor(16 * CONST_SIZE['MB'] / CONST_SIZE['KB'])

    # default_statistics_target
    config['default_statistics_target'] = {
        'web': 100,
        'oltp': 100,
        'dw': 500,
        'desktop': 100,
        'mixed': 100
    }[db_type]


    # format size values
    NOT_SIZE_VALUES = [
        'max_connections', 'checkpoint_segments',
        'checkpoint_completion_target', 'default_statistics_target',
        'random_page_cost', 'seq_page_cost'
    ]
    def format_value(key, value):
        if key in NOT_SIZE_VALUES:
            return "{0}".format(value)

        # This uses larger units only if there's no loss of resolution in
        # displaying with that value.  Therefore, if using this to output newly
        # assigned values, that value needs to be rounded appropriately if you
        # want it to show up as an even number of MB or GB
        if value % CONST_SIZE['KB_PER_GB'] == 0:
          value = math.floor(value / CONST_SIZE['KB_PER_GB'])
          unit = "GB"
        elif value % CONST_SIZE['KB_PER_MB'] == 0:
          value = math.floor(value / CONST_SIZE['KB_PER_MB'])
          unit = "MB"
        else:
          unit = "kB"
        return "{0}{1}".format(int(value), unit)

    return { k: format_value(k, v) for k, v in config.iteritems() }


def kernel_settings(db_version, os_type, db_type, total_memory):
    """Generate Linux kernel configuration"""

    if os_type == 'windows' or db_version > 9.3:
        return {}
    else:
        shmall = math.floor(total_memory / 8192)
        return {
            'kernel.shmmax': int(shmall * 4096),
            'kernel.shmall': int(shmall)
        }


def format_config(config):
    return "\n".join(["{0} = {1}".format(k, v) for k, v in config.iteritems()])


def create_dirs(file_path):
    if not os.path.exists(os.path.dirname(file_path)):
        try:
            os.makedirs(os.path.dirname(file_path))
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise


def file_exists(file_path):
    if not file_path:
        return False
    elif not os.path.isfile(file_path):
        return False
    else:
        return True


def md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def tune(data):
    """Write PostgreSQL and Linux kernel configuration files"""
    config = {}

    db_version = float(data["db_version"])
    db_type = data["db_type"]
    max_connections = int(data["max_connections"])

    # convert total_memory from xxxMB or xxxGB into a bytes value
    memory_arg = data["total_memory"]
    mem_in_size = int(memory_arg[:-2])
    const_for_size = CONST_SIZE[memory_arg[-2:]]
    total_memory = mem_in_size * const_for_size
    total_memory_original = total_memory

    total_memory_percentage = int(data["total_memory_percentage"])

    if total_memory_percentage != 100:
        total_memory = ( total_memory * total_memory_percentage / 100 )

    ### POSTGRESQL CONFIGURATION
    config["postgresql"] = postgres_settings(
        db_version,
        "linux",
        db_type,
        total_memory,
        max_connections
    )

    disable_max_connections = data["disable_max_connections"]

    if disable_max_connections:
        config["postgresql"].pop("max_connections", None)
    

    # write configuration file
    old_postgresql_file_hash = md5(data["postgresql_file"]) if file_exists(data["postgresql_file"]) else None

    create_dirs(data["postgresql_file"])
    with open(data["postgresql_file"], 'w') as confile:
        # document some key parameters in the on server config file
        confile.write("# pgtune db_version = " + str(db_version) + "\n")
        confile.write("# pgtune db_type = " + str(db_type) + "\n")
        confile.write("# pgtune total_memory = " + str(total_memory_original / float(CONST_SIZE['GB'])) + 'GB' + "\n")
        confile.write("# pgtune total_memory_percentage = " + data['total_memory_percentage'] + '%'+ "\n")
        confile.write("# pgtune total_memory allocated = " + str(total_memory / float(CONST_SIZE['GB'])) + 'GB' + "\n")
        for k,v in config["postgresql"].items():
            confile.writelines("{} = {}\n".format(k,v))

    new_postgresql_file_hash = md5(data["postgresql_file"])


    ### KERNEL CONFIGURATION
    config["kernel"] = kernel_settings(
        db_version,
        "linux",
        db_type,
        total_memory,
    )

    # write configuration file
    old_sysctl_file_hash = None
    new_sysctl_file_hash = None
    if bool(data["sysctl_file"]):
        old_sysctl_file_hash = md5(data["sysctl_file"]) if file_exists(data["sysctl_file"]) else None

        create_dirs(data["sysctl_file"])
        with open(data["sysctl_file"], 'w') as confile:
            for k,v in config["kernel"].items():
                confile.writelines("{} = {}\n".format(k,v))

        new_sysctl_file_hash = md5(data["postgresql_file"])

    return (old_postgresql_file_hash != new_postgresql_file_hash, config) or (old_sysctl_file_hash != new_sysctl_file_hash)


def main():
    """Main entry point function"""

    import os
    # tested on Linux and Mac el Capitan
    calculated_mem_bytes = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    default_memory = str(int(calculated_mem_bytes/(1024.**2))) + 'MB'

    fields = {
        "db_version": {
            "required": True,
            "type": "str"
        },
        "db_type": {
            "required": True,
            "type": "str"
        },
        "total_memory": {
            "required": False,
            "type": "str",
            "default": default_memory
        },
        "total_memory_percentage": {
            "required": False,
            "type": "str",
            "default": 100
        },
        "max_connections": {
            "required": True,
            "type": "str"
        },
        "postgresql_file": {
            "required": True,
            "type": "str"
        },
        "disable_max_connections": {
            "required": False,
            "type": "bool"
        },
        "sysctl_file": {
            "required": False,
            "type": "str"
        },
    }

    module = AnsibleModule(argument_spec=fields)
    has_changed, config = tune(module.params)
    module.exit_json(changed=has_changed, config=config)


if __name__ == '__main__':
    main()


# vim: set ts=4 sts=4 sw=4 et:
