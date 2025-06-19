#!/usr/bin/env python3

import shutil
import sys
import time

from slurm_interface import *

# Default constants (can be overridden by environment variables)
SLURM_JOB_START_TIMEOUT_SECONDS = 1200  # 20 minutes
SLURM_JOB_STOP_TIMEOUT_SECONDS_BEFORE_CANCEL = 30


def wait_until(condition, timeout_seconds: int = 10) -> bool:
    while timeout_seconds != 0:
        if condition():
            return True
        time.sleep(1)
        timeout_seconds -= 1
    return False


def update_file_timestamp(path: str) -> None:
    if not os.path.exists(path):
        return
    if not os.path.isfile(path):
        return
    subprocess.Popen(f"touch -c -m {path} >/dev/null", shell=True)


def flush_system_io(path: str) -> None:
    subprocess.Popen(f"ls -la {os.path.dirname(path)} >/dev/null",
                     shell=True)


def exit_system_failure(message=None) -> int:
    if message is not None:
        logging.critical(f"SYSTEM FAILURE: {message}")
    return int(os.getenv("SYSTEM_FAILURE_EXIT_CODE", "2"))


def exit_build_failure(message=None) -> int:
    if message is not None:
        logging.critical(f"BUILD FAILURE: {message}")
    return int(os.getenv("BUILD_FAILURE_EXIT_CODE", "1"))


class GitLabJobInterface:
    @staticmethod
    def get_env(key: str, default=None) -> str:
        gitlab_ci_env_token = "CUSTOM_ENV_"
        # Return value of the local key (if any job has overridden the global one)
        # Otherwise, return the global value (if any)
        # Otherwise, return the default value is not any
        local_key = f"{gitlab_ci_env_token}LOCAL_{key}"
        global_key = f"{gitlab_ci_env_token}{key}"
        return os.environ.get(local_key, os.environ.get(global_key, default))

    @staticmethod
    def get_bool_env(key: str) -> bool:
        value = GitLabJobInterface.get_env(key)
        if value is None:
            return False
        return value.lower().strip() in ["true", "1", "yes", "y"]

    @staticmethod
    def is_defined_env(key: str) -> bool:
        return GitLabJobInterface.get_env(key) is not None

    @staticmethod
    def get_job_uid() -> str:
        job_name = GitLabJobInterface.get_env("CI_PROJECT_ID")
        job_name += "__"
        job_name += GitLabJobInterface.get_env("CI_PIPELINE_ID")
        job_name += "_"
        job_name += GitLabJobInterface.get_env("CI_JOB_ID")
        return job_name

    @staticmethod
    def get_build_dir_path() -> str:
        return GitLabJobInterface.get_env("CI_BUILDS_DIR")


class SLURMIdleJob:
    id: str
    work_dir: str
    current_execution: str = None

    def __init__(self, job_id: str, work_dir: str = None):
        self.id = job_id
        self.work_dir = work_dir

    @staticmethod
    def create(
            configuration: SLURMJobRequestData,
            work_dir: str,
            batch_filename: str = "config.sbatch"
    ) -> Optional["SLURMIdleJob"]:
        # Find the path of the idle_script.sh file (next to this file location)
        idle_bash_script_filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), "idle_script.sh")
        if not os.path.isfile(idle_bash_script_filepath):
            logging.critical(f"File {idle_bash_script_filepath} does not exist")
            return None
        if not os.access(idle_bash_script_filepath, os.X_OK):
            logging.critical(f"File {idle_bash_script_filepath} is not executable")
            return None
        if not os.access(idle_bash_script_filepath, os.R_OK):
            logging.critical(f"File {idle_bash_script_filepath} is not readable")
            return None

        batch_filepath = os.path.join(work_dir, batch_filename)
        with open(batch_filepath, "w", encoding="utf-8") as f:
            f.write(
                configuration.to_sbatch_file_string([f". {idle_bash_script_filepath}"])
            )
        # Make the file executable, readable and writable
        os.chmod(batch_filepath, 0o777)
        logging.info(f"Created the sbatch configuration file in {os.path.abspath(batch_filepath)}")
        # Log the content of the batch file (debug mode only)
        if logging.getLogger().level == logging.DEBUG:
            with open(batch_filepath, "r", encoding="utf-8") as f:
                logging.debug(f"Content of {batch_filepath}:\n{f.read()}")
        # Execute the batch file
        job_id = SLURMInterface.sbatch(batch_filepath)
        logging.debug(f"Submitted SLURM job with ID {job_id}")
        # Wait for the job to be created
        wait_until(lambda: SLURMInterface.exists(job_id), timeout_seconds=120)
        return SLURMIdleJob(job_id, work_dir) if SLURMInterface.exists(job_id) else None

    @staticmethod
    def attach(job_name: str, work_dir: str) -> Optional["SLURMIdleJob"]:
        job_id = SLURMInterface.get_id_from_name(job_name)
        if job_id is None:
            return None
        return SLURMIdleJob(job_id, work_dir) if job_id is not None else None
        # Try to attach to the job

    def get_state(self) -> SLURMJobState:
        return SLURMInterface.sacct(self.id).state

    def is_running(self) -> bool:
        return self.get_state() == SLURMJobState.RUNNING

    def is_pending(self) -> bool:
        return self.get_state() == SLURMJobState.PENDING

    def get_execution_script_path(self) -> str:
        return os.path.join(self.work_dir, self.current_execution) + ".gitlab_ci_step_script"

    def get_execution_executed_path(self) -> str:
        return self.get_execution_script_path() + ".executed"

    def get_execution_logfile_path(self) -> str:
        return self.get_execution_script_path() + ".log"

    def execute_script(
            self,
            script_name: str,
            source_script_path: str = None
    ) -> Tuple[str, str]:
        self.current_execution = script_name
        script_filepath = self.get_execution_script_path()
        script_log_filepath = self.get_execution_logfile_path()
        script_executed_filepath = self.get_execution_executed_path()

        script_content = ""
        try:
            if source_script_path is not None:
                with open(source_script_path, "r", encoding="utf-8") as f:
                    script_content = f.read()
        finally:
            tmp_script_filepath = script_filepath + ".tmp"
            with open(tmp_script_filepath, "w", encoding="utf-8") as f:
                f.write(script_content)
            os.rename(tmp_script_filepath, script_filepath)
            logging.debug(f"Created the script file: {os.path.abspath(script_filepath)}")
            logging.info(
                f"Logs of current phase <{script_name}> will be available "
                f"in {os.path.abspath(script_log_filepath)}")

        return script_executed_filepath, script_log_filepath

    def mark_stop(self) -> None:
        exit_script_path = os.path.join(self.work_dir, "batch.gitlab_ci_exit")
        with open(exit_script_path, "w", encoding="utf-8") as f:
            f.write("This file  is used to instruct the SLURM job to stop")
        logging.debug(f"Created the exit file: {os.path.abspath(exit_script_path)}")

    def try_stop(self) -> None:
        try:
            self.mark_stop()
            timeout_before_cancel = int(GitLabJobInterface.get_env(
                "SLURM_JOB_STOP_TIMEOUT_SECONDS_BEFORE_CANCEL", SLURM_JOB_STOP_TIMEOUT_SECONDS_BEFORE_CANCEL))
            wait_until(lambda: not self.is_running(), timeout_seconds=timeout_before_cancel)
        finally:
            if self.is_running():
                SLURMInterface.scancel(self.id)

    def clean_chdir(self) -> None:
        if GitLabJobInterface.get_env("CI_KEEP_BUILD_DIR"):
            return
        # Remove the build directory
        if os.path.exists(self.work_dir) and os.path.isdir(self.work_dir):
            shutil.rmtree(self.work_dir)


class GitLabPhases:
    @staticmethod
    def config() -> None:
        message = """{
    "builds_dir": "{build_path}/",
    "cache_dir": "{cache_path}/",
    "builds_dir_is_shared": false,
    "driver": {
        "name": "SLURM-Executor",
        "version": "0.1.0 (HEAD)"
    }
}
"""
        job_token = GitLabJobInterface.get_job_uid()
        build_dirname = f"{sys.argv[2]}/{job_token}"
        cache_dirname = f"{sys.argv[3]}/{job_token}"
        message = message.replace("{build_path}", build_dirname)
        message = message.replace("{cache_path}", cache_dirname)
        os.makedirs(build_dirname, exist_ok=True)
        os.makedirs(cache_dirname, exist_ok=True)
        print(message, file=sys.stdout)

    @staticmethod
    def prepare():
        logging.debug("PHASE <prepare>")
        sbatch_config = SLURMJobRequestData(
            job_name=GitLabJobInterface.get_job_uid(),
            nodes=GitLabJobInterface.get_env("CI_SLURM_NNODES"),
            mem=GitLabJobInterface.get_env("CI_SLURM_MEM_PER_NODE"),
            mem_bind=GitLabJobInterface.get_env("CI_SLURM_MEM_BIND"),
            mem_per_cpu=GitLabJobInterface.get_env("CI_SLURM_MEM_PER_CPU"),
            cpus_per_task=GitLabJobInterface.get_env("CI_SLURM_CPUS_PER_TASK"),
            n_tasks=GitLabJobInterface.get_env("CI_SLURM_NTASKS"),
            time_limit=GitLabJobInterface.get_env("CI_SLURM_TIMELIMIT", "00-02:00:00"),
            time_min=GitLabJobInterface.get_env("CI_SLURM_TIME_MIN"),
            exclusive=GitLabJobInterface.get_bool_env("CI_SLURM_EXCLUSIVE"),
            network=GitLabJobInterface.get_env("CI_SLURM_NETWORK"),
            contiguous=GitLabJobInterface.get_bool_env("CI_SLURM_CONTIGUOUS"),
            partition=GitLabJobInterface.get_env("CI_SLURM_PARTITION"),
            power=GitLabJobInterface.get_env("CI_SLURM_POWER"),
            priority=GitLabJobInterface.get_env("CI_SLURM_PRIORITY"),
            nice=GitLabJobInterface.get_env("CI_SLURM_NICE"),
            comment=GitLabJobInterface.get_env("CI_SLURM_COMMENT", "Automatic job created from GitLab CI"),
            chdir=GitLabJobInterface.get_build_dir_path(),
            account=GitLabJobInterface.get_env("CI_SLURM_ACCOUNT"),
            qos=GitLabJobInterface.get_env("CI_SLURM_QOS"),
            export="ALL",
            stdout_file="stdout.log",
            stderr_file="stderr.log"
        )
        job = SLURMIdleJob.create(
            sbatch_config,
            GitLabJobInterface.get_build_dir_path()
        )
        if job is None:
            sys.exit(exit_system_failure("Failed to create SLURM job"))
        # Wait for the job to not be pending
        timeout_secs = int(GitLabJobInterface.get_env(
            "SLURM_JOB_START_TIMEOUT_SECONDS", SLURM_JOB_START_TIMEOUT_SECONDS))
        wait_until(lambda: job.is_running(), timeout_secs)
        if not job.is_running():
            job.mark_stop()
            SLURMInterface.scancel(job.id)
            sys.exit(exit_system_failure("Failed to wait for SLURM job to not be pending"))

    @staticmethod
    def run():
        logging.debug("PHASE <run/*>")
        # Try to attach to the job
        job = SLURMIdleJob.attach(GitLabJobInterface.get_job_uid(), GitLabJobInterface.get_build_dir_path())
        if job is None:
            sys.exit(exit_system_failure(
                f"Failed to found to SLURM job with NAME {GitLabJobInterface.get_job_uid()}"))
        if not job.is_running():
            sys.exit(exit_system_failure(f"SLURM job with ID {job.id} is not running, state is {job.get_state()}"))
        # Execute the script created by GitLab
        script_executed_file, script_log_file = job.execute_script(sys.argv[3], sys.argv[2])

        def is_phase_executed() -> bool:
            flush_system_io(script_executed_file)
            return job.is_running() and os.path.isfile(script_executed_file)

        read_bytes = 0
        last_read_timestamp = 0
        # Wait for the script to be executed
        while not wait_until(lambda: is_phase_executed(), timeout_seconds=10):
            if not job.is_running():
                break
            update_file_timestamp(script_executed_file)
            last_edit_timestamp = os.path.getmtime(script_log_file)
            if last_edit_timestamp != last_read_timestamp:
                last_read_timestamp = last_edit_timestamp
                with open(script_log_file, "r", encoding="utf-8") as f:
                    f.seek(read_bytes)
                    print(f.read(), end="", file=sys.stderr)
                    sys.stderr.flush()
                    read_bytes = f.tell()

        # Output the logs of the script
        with open(script_log_file, "r", encoding="utf-8") as f:
            f.seek(read_bytes)
            print(f.read(), end="", file=sys.stderr)
            sys.stderr.flush()

        if not job.is_running():
            sys.exit(exit_system_failure(f"SLURM job with ID {job.id} is not running, state is {job.get_state()}"))

    @staticmethod
    def run_cleanup_file_variables() -> None:
        logging.debug("PHASE <run/cleanup_file_variables>")

        GitLabPhases.run()

        job = SLURMIdleJob.attach(GitLabJobInterface.get_job_uid(), GitLabJobInterface.get_build_dir_path())
        if job is None:
            sys.exit(exit_system_failure(
                f"Failed to found to SLURM job with NAME {GitLabJobInterface.get_job_uid()}"))

        # Stop the job and clean the build folder
        job.try_stop()
        job.clean_chdir()

    @staticmethod
    def cleanup() -> None:
        logging.debug("-- PHASE <cleanup>")

        job = SLURMIdleJob.attach(GitLabJobInterface.get_job_uid(), GitLabJobInterface.get_build_dir_path())
        if job is None:
            return
        # Stop the job and clean the build folder
        job.try_stop()

    @staticmethod
    def execute(phase: str) -> None:
        if phase == "config":
            GitLabPhases.config()
        elif phase == "prepare":
            GitLabPhases.prepare()
        elif phase == "run":
            run_phase = sys.argv[3]
            if run_phase == "cleanup_file_variables":
                GitLabPhases.run_cleanup_file_variables()
            else:
                GitLabPhases.run()
        elif phase == "cleanup":
            GitLabPhases.cleanup()


def main():
    ci_log_level = GitLabJobInterface.get_env("CI_LOG_LEVEL_SLURM_EXECUTOR")
    if ci_log_level is not None:
        ci_log_level = ci_log_level.strip().lower()
    levels = {"debug": logging.DEBUG, "none": logging.CRITICAL}
    logging.basicConfig(
        stream=sys.stderr,
        level=levels.get(ci_log_level, logging.INFO),
        format="[SLURM-EXECUTOR][%(levelname)s] -- %(message)s")
    logging.debug("Starting SLURM executor")

    phase = sys.argv[1]
    GitLabPhases.execute(phase)

    sys.exit(0)


if __name__ == "__main__":
    main()
