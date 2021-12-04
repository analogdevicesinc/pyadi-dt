import pytest
import os

import adidt

loc = os.path.dirname(__file__)


def test_dt_local_file_import():
    dtb = os.path.join(loc, "devicetree.dtb")
    d = adidt.dt(dt_source="local_file", local_dt_filepath=dtb, arch="arm")


def test_dt_remote_sysfs(ip):
    d = adidt.dt(dt_source="remote_sysfs", ip=ip)


def test_dt_remote_sd(ip):
    d = adidt.dt(dt_source="remote_sd", ip=ip)
