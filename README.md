ansible-postgresql_tune
=======================

Ansible module for automatic PostgreSQL tuning.

The module creates tuned settings for Postgres based on various use cases and system sizing parameters.

Tuned settings are written out to a dedicated config file, not to the main postgresql.conf.

Installation
------------

Place postgresql_tune.py in your Ansible library directory

Requirements
------------

Postgresql installation.

To include a separate config file with your postgresql.conf a common stanza is:-

    include_dir = 'conf.d'

Duplicated parameters override parameters that occur earlier in the core postgresql.conf file.

Dependencies
------------

None

Example Playbook
----------------

# Postgresql 9.6

```
  vars:
    postgresql_version: 9.6
    postgresql_conf_directory: /etc/postgresql/9.6
    postgresql_tune_db_type: web
    postgresql_tune_total_memory: "{{ ansible_memtotal_mb }}MB"

  tasks:
  - name: Tune Postgresql
    postgresql_tune:
      db_version: "{{ postgresql_version }}"
      db_type: "{{ postgresql_tune_db_type }}"
      total_memory: "{{ postgresql_tune_total_memory }}"
      postgresql_file: "{{ postgresql_conf_directory }}/conf.d/99-postgresql-tune.conf"

```

# Postgres 9.1 changing the kernels SHM settings and setting a custom max_connections setting

```
  vars:
    postgresql_version: 9.6
    postgresql_conf_directory: /etc/postgresql/9.6
    postgresql_tune_db_type: web
    postgresql_tune_total_memory: "{{ ansible_memtotal_mb }}MB"
    postgresql_tune_sysctl_file: /etc/sysctl.d/99-postgresql-tune.conf
    postgresql_tune_connections: 50

  tasks:
  - name: Tune Postgresql
    postgresql_tune:
      db_version: "{{ postgresql_version }}"
      db_type: "{{ postgresql_tune_db_type }}"
      total_memory: "{{ postgresql_tune_total_memory }}"
      max_connections: "{{ postgresql_tune_connections }}"
      postgresql_file: "{{ postgresql_conf_directory }}/conf.d/99-postgresql-tune.conf"
      sysctl_file: "{{ postgresql_postgresql_tune_sysctl_file }}"

```

License
-------

BSD

Author Information
------------------

Copyright 2013 Crown copyright (c)
Land Information New Zealand and the New Zealand Government.
All rights reserved

This program is released under the terms of the new BSD license. See the
LICENSE file for more information.

Computing logic is based on http://pgtune.leopard.in.ua, developed by
Alexey Vasiliev and released under MIT license.

