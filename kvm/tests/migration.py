import logging, time
from autotest_lib.client.common_lib import error
import kvm_subprocess, kvm_test_utils, kvm_utils


def run_migration(test, params, env):
    """
    KVM migration test:
    1) Get a live VM and clone it.
    2) Verify that the source VM supports migration.  If it does, proceed with
            the test.
    3) Send a migration command to the source VM and wait until it's finished.
    4) Kill off the source VM.
    3) Log into the destination VM after the migration is finished.
    4) Compare the output of a reference command executed on the source with
            the output of the same command on the destination machine.

    @param test: kvm test object.
    @param params: Dictionary with test parameters.
    @param env: Dictionary with the test environment.
    """
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    timeout = int(params.get("login_timeout", 360))
    session = vm.wait_for_login(timeout=timeout)

    mig_timeout = float(params.get("mig_timeout", "3600"))
    mig_protocol = params.get("migration_protocol", "tcp")
    mig_cancel_delay = int(params.get("mig_cancel") == "yes") * 2
    offline = params.get("offline", "no") == "yes"
    check = params.get("vmstate_check", "no") == "yes"

    # Get the output of migration_test_command
    test_command = params.get("migration_test_command")
    reference_output = session.cmd_output(test_command)

    # Start some process in the background (and leave the session open)
    background_command = params.get("migration_bg_command", "")
    session.sendline(background_command)
    time.sleep(5)

    # Start another session with the guest and make sure the background
    # process is running
    session2 = vm.wait_for_login(timeout=timeout)

    try:
        check_command = params.get("migration_bg_check_command", "")
        session2.cmd(check_command, timeout=30)
        session2.close()

        # Migrate the VM
        vm.migrate(mig_timeout, mig_protocol, mig_cancel_delay, offline, check)

        # Log into the guest again
        logging.info("Logging into guest after migration...")
        session2 = vm.wait_for_login(timeout=30)
        logging.info("Logged in after migration")

        # Make sure the background process is still running
        session2.cmd(check_command, timeout=30)

        # Get the output of migration_test_command
        output = session2.cmd_output(test_command)

        # Compare output to reference output
        if output != reference_output:
            logging.info("Command output before migration differs from "
                         "command output after migration")
            logging.info("Command: %s" % test_command)
            logging.info("Output before:" +
                         kvm_utils.format_str_for_message(reference_output))
            logging.info("Output after:" +
                         kvm_utils.format_str_for_message(output))
            raise error.TestFail("Command '%s' produced different output "
                                 "before and after migration" % test_command)

    finally:
        # Kill the background process
        if session2 and session2.is_alive():
            session2.cmd_output(params.get("migration_bg_kill_command", ""))

    session2.close()
    session.close()
