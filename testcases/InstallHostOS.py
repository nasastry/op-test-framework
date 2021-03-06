#!/usr/bin/env python2
# OpenPOWER Automated Test Project
#
# Contributors Listed Below - COPYRIGHT 2018
# [+] International Business Machines Corp.
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.
#

'''
Install HostOS
--------------

Installs HostOS on the host.
'''


import unittest
import os

import OpTestConfiguration
from common.OpTestSystem import OpSystemState
from common import OpTestInstallUtil


class InstallHostOS(unittest.TestCase):
    def setUp(self):
        self.conf = OpTestConfiguration.conf
        self.cv_HOST = self.conf.host()
        self.cv_IPMI = self.conf.ipmi()
        self.cv_SYSTEM = self.conf.system()
        self.cv_BMC = self.conf.bmc()
        self.bmc_type = self.conf.args.bmc_type
        if not (self.conf.args.os_repo or self.conf.args.os_cdrom):
            self.fail("Provide installation media for installation, --os-repo is missing")
        if not (self.conf.args.host_ip and self.conf.args.host_gateway and self.conf.args.host_dns
                and self.conf.args.host_submask and self.conf.args.host_mac):
            self.fail("Provide host network details refer, --host-{ip,gateway,dns,submask,mac}")
        if not (self.conf.args.host_user and self.conf.args.host_password):
            self.fail("Provide host user details refer, --host-{user,password}")
        if not self.conf.args.host_scratch_disk:
            self.fail("Provide proper host disk to install refer, --host-scratch-disk")
        if not self.conf.args.host_name:
            self.fail("Provide hostname to be set during installation")

    def runTest(self):
        self.cv_SYSTEM.goto_state(OpSystemState.PETITBOOT_SHELL)

        # Local path to keep install files
        base_path = os.path.join(self.conf.basedir, "osimages", "hostos")
        # relative path from repo where vmlinux and initrd is present
        boot_path = "ppc/ppc64"
        vmlinux = "vmlinuz"
        initrd = "initrd.img"
        ks = "hostos.ks"
        OpIU = OpTestInstallUtil.InstallUtil(base_path=base_path,
                                             vmlinux=vmlinux,
                                             initrd=initrd,
                                             ks=ks,
                                             boot_path=boot_path)
        my_ip = OpIU.get_server_ip()
        if not my_ip:
            self.fail("Unable to get the ip from host")

        if self.conf.args.os_cdrom and not self.conf.args.os_repo:
            repo = OpIU.setup_repo(self.conf.args.os_cdrom)
        if self.conf.args.os_repo:
            repo = self.conf.args.os_repo
        if not repo:
            self.fail("No valid repo to start installation")
        if not OpIU.extract_install_files(repo):
            self.fail("Unable to download install files")

        OpIU.extract_install_files(repo)

        # start our web server
        port = OpIU.start_server(my_ip)

        if "qemu" not in self.bmc_type:
            ks_url = 'http://%s:%s/%s' % (my_ip, port, ks)
            kernel_args = "ifname=net0:%s ip=%s::%s:%s:%s:net0:none nameserver=%s inst.ks=%s" % (self.conf.args.host_mac,
                                                                                                 self.cv_HOST.ip,
                                                                                                 self.conf.args.host_gateway,
                                                                                                 self.conf.args.host_submask,
                                                                                                 self.conf.args.host_name,
                                                                                                 self.conf.args.host_dns,
                                                                                                 ks_url)
            self.c = self.cv_SYSTEM.console
            cmd = "[ -f %s ]&& rm -f %s;[ -f %s ] && rm -f %s;true" % (vmlinux,
                                                                       vmlinux,
                                                                       initrd,
                                                                       initrd)
            self.c.run_command(cmd)
            self.c.run_command("wget http://%s:%s/%s" % (my_ip, port, vmlinux))
            self.c.run_command("wget http://%s:%s/%s" % (my_ip, port, initrd))
            self.c.run_command("kexec -i %s -c \"%s\" %s -l" % (initrd,
                                                                kernel_args,
                                                                vmlinux))
            raw_pty = self.c.get_console()
            raw_pty.sendline("kexec -e")
        else:
            pass
        # Do things
        raw_pty = self.c.get_console()
        raw_pty.expect('opal: OPAL detected', timeout=60)
        r = None
        while r != 0:
            r = raw_pty.expect(['Running post-installation scripts',
                             'Starting installer',
                             'Setting up the installation environment',
                             'Starting package installation process',
                             'Performing post-installation setup tasks',
                             'Configuring installed system'], timeout=1500)
        raw_pty.expect('reboot: Restarting system', timeout=300)
        self.cv_SYSTEM.set_state(OpSystemState.IPLing)
        self.cv_SYSTEM.goto_state(OpSystemState.PETITBOOT_SHELL)
        OpIU.stop_server()
        OpIU.set_bootable_disk(self.cv_HOST.get_scratch_disk())
        self.cv_SYSTEM.goto_state(OpSystemState.OFF)
        self.cv_SYSTEM.goto_state(OpSystemState.OS)
        con = self.cv_SYSTEM.console
        con.run_command("uname -a")
        con.run_command("cat /etc/os-release")
        self.cv_HOST.host_gather_opal_msg_log()
        self.cv_HOST.host_gather_kernel_log()
