#
# Kickstart module for subscription handling.
#
# Copyright (C) 2020 Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#

from dasbus.typing import get_variant, Str

from pyanaconda.core import util
from pyanaconda.core.constants import RHSM_SERVICE_TIMEOUT

from pyanaconda.threading import threadMgr

from pyanaconda.modules.common.task import Task
from pyanaconda.modules.common.errors.task import NoResultError
from pyanaconda.modules.common.constants.services import RHSM
from pyanaconda.modules.common.constants.objects import RHSM_CONFIG

from pyanaconda.anaconda_loggers import get_module_logger
log = get_module_logger(__name__)


class StartRHSMTask(Task):
    """Task for starting the RHSM DBus service."""

    RHSM_SYSTEMD_UNIT_NAME = "rhsm.service"

    @property
    def name(self):
        return "Start RHSM DBus service"

    def run(self):
        """Start the RHSM DBus service.

        And also some related tasks, such as setting RHSM log levels.
        """
        # start the rhsm.service
        # - this is blocking, but as we are effectively running in a thread
        # it should not be an issue
        # - if the return code is non-zero, return False immediately
        rc = util.start_service(self.RHSM_SYSTEMD_UNIT_NAME)
        if rc:
            log.warning(
                "subscription: RHSM systemd service failed to start with error code: %s",
                rc
            )
            return False
        # create a temporary proxy to set the log levels
        rhsm_config_proxy = RHSM.get_proxy(RHSM_CONFIG)

        # set RHSM log levels to debug
        # - otherwise the RHSM log output is not usable for debugging subscription issues
        log.debug("subscription: setting RHSM log level to DEBUG")
        rhsm_config_proxy.Set("logging.default_log_level", get_variant(Str, "DEBUG"), "")
        # all seems fine
        log.debug("subscription: RHSM service start successfully.")
        return True

    def is_service_available(self, timeout=RHSM_SERVICE_TIMEOUT):
        """Return if RHSM service is available or wait if startup is ongoing."""
        if self.is_running:
            # Wait up to defined timeout for the service to startup
            # by joining the thread running the task. We specify a timeout when
            # joining to prevent a deadlocked task blocking this method forever.
            thread = threadMgr.get(self._thread_name)
            if thread:
                log.debug("subscription: waiting for RHSM service to start for up to %f seconds.",
                          timeout)
                thread.join(timeout)
            else:
                log.error("subscription: RHSM startup task is running but no thread found.")
                return False

        # now check again if the task is still running
        if self.is_running:
            # looks like we timed out
            log.debug("subscription: RHSM service not available after waiting for %f seconds.",
                      timeout)
            return False
        else:
            # If we got this far, the task has finished running. If the result is True
            # it was able to successfully start the systemd unit and connect to the DBus API.
            # If the result is False, then the service failed to start.
            try:
                result = self.get_result()
            except NoResultError:
                # if the task fails in weird ways, there could apparently be no result
                log.error("subscription: got no result from StartRHSMTask")
                result = False
            return result