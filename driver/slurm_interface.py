#!/usr/bin/env python3

import enum
import logging
import os
import signal
import subprocess
from enum import Enum
from typing import Tuple, Optional, List, Dict


def _system(
        command: str,
        timeout_seconds: int = 30,
        as_shell: bool = False
) -> Tuple[int, str, str]:
    with subprocess.Popen(
            command if as_shell else command.split(),
            shell=as_shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy()
    ) as execution:
        execution.wait(timeout=timeout_seconds)
        stdout, stderr = [x.decode("utf-8").strip() for x in execution.communicate()]
        retcode = execution.returncode
        logging.debug(f"Command: {command}")
        logging.debug(f" - Return code: {retcode}")
        logging.debug(f" - Stdout: {stdout}")
        if len(stderr) > 0:
            logging.debug(f" - Stderr: {stderr}")
    return retcode, stdout, stderr


class SLURMJobState(Enum):
    """
    Enum for SLURM job states based
    on https://slurm.schedmd.com/sacct.html#SECTION_JOB-STATE-CODES
    """

    BOOT_FAIL = enum.auto()
    CANCELLED = enum.auto()
    COMPLETED = enum.auto()
    DEADLINE = enum.auto()
    FAILED = enum.auto()
    NODE_FAIL = enum.auto()
    OUT_OF_MEMORY = enum.auto()
    PENDING = enum.auto()
    PREEMPTED = enum.auto()
    RUNNING = enum.auto()
    REQUEUED = enum.auto()
    RESIZING = enum.auto()
    REVOKED = enum.auto()
    SUSPENDED = enum.auto()
    TIMEOUT = enum.auto()

    @staticmethod
    def _get_equivalent_states() -> Dict[str, "SLURMJobState"]:
        return dict({
            "BOOT_FAIL": SLURMJobState.BOOT_FAIL,
            "BF": SLURMJobState.BOOT_FAIL,
            "CANCELLED": SLURMJobState.CANCELLED,
            "CA": SLURMJobState.CANCELLED,
            "COMPLETED": SLURMJobState.COMPLETED,
            "CD": SLURMJobState.COMPLETED,
            "DEADLINE": SLURMJobState.DEADLINE,
            "DL": SLURMJobState.DEADLINE,
            "FAILED": SLURMJobState.FAILED,
            "F": SLURMJobState.FAILED,
            "NODE_FAIL": SLURMJobState.NODE_FAIL,
            "NF": SLURMJobState.NODE_FAIL,
            "OUT_OF_MEMORY": SLURMJobState.OUT_OF_MEMORY,
            "OOM": SLURMJobState.OUT_OF_MEMORY,
            "PENDING": SLURMJobState.PENDING,
            "PD": SLURMJobState.PENDING,
            "PREEMPTED": SLURMJobState.PREEMPTED,
            "PR": SLURMJobState.PREEMPTED,
            "RUNNING": SLURMJobState.RUNNING,
            "R": SLURMJobState.RUNNING,
            "REQUEUED": SLURMJobState.REQUEUED,
            "RQ": SLURMJobState.REQUEUED,
            "RESIZING": SLURMJobState.RESIZING,
            "RS": SLURMJobState.RESIZING,
            "REVOKED": SLURMJobState.REVOKED,
            "RV": SLURMJobState.REVOKED,
            "SUSPENDED": SLURMJobState.SUSPENDED,
            "S": SLURMJobState.SUSPENDED,
            "TIMEOUT": SLURMJobState.TIMEOUT,
            "TO": SLURMJobState.TIMEOUT
        })

    @staticmethod
    def from_string(state: str) -> Optional["SLURMJobState"]:
        return SLURMJobState._get_equivalent_states().get(state, None)

    def to_string(self) -> str:
        for k, v in SLURMJobState._get_equivalent_states().items():
            if v == self:
                return k
        raise ValueError(f"Invalid SLURM job state: {self}")


class SLURMRegisteredJobData:
    @staticmethod
    def variables() -> List[str]:
        return ["JobID", "JobName", "State", "ExitCode", "Elapsed", "NTasks", "Submit", "Start", "End", "Account",
                "User", "Timelimit"]

    def __init__(self, raw_data: dict):
        self.id = raw_data["JobID"].split(".")[0]
        self.name = raw_data["JobName"]
        self.state = SLURMJobState.from_string(raw_data["State"])
        self.exit_code = raw_data["ExitCode"]
        self.elapsed = raw_data["Elapsed"]
        self.n_tasks = raw_data["NTasks"]
        self.submit = raw_data["Submit"]
        self.start = raw_data["Start"]
        self.end = raw_data["End"]
        self.account = raw_data["Account"]
        self.user = raw_data["User"]
        self.time_limit = raw_data["Timelimit"]


class SLURMJobRequestData:

    def __init__(
            self,
            job_name: str,
            nodes: str = None,
            mem: str = None,
            mem_bind: str = None,
            mem_per_cpu: str = None,
            cpus_per_task: str = None,
            n_tasks: str = None,
            time_limit: str = None,
            time_min: str = None,
            exclusive: bool = False,
            network: str = None,
            contiguous: bool = False,
            partition: str = None,
            power: str = None,
            priority: str = None,
            nice: str = None,
            comment: str = None,
            chdir: str = None,
            export: str = None,
            stdout_file: str = None,
            stderr_file: str = None,
    ):
        self.job_name = job_name
        self.nodes = nodes
        self.mem = mem
        self.mem_bind = mem_bind
        self.mem_per_cpu = mem_per_cpu
        self.cpus_per_task = cpus_per_task
        self.n_tasks = n_tasks
        self.time_limit = time_limit
        self.time_min = time_min
        self.exclusive = exclusive
        self.network = network
        self.contiguous = contiguous
        self.partition = partition
        self.power = power
        self.priority = priority
        self.nice = nice
        self.comment = comment
        self.chdir = chdir
        self.export = export
        self.stdout_file = stdout_file
        self.stderr_file = stderr_file

    def get_cli_parameters(self) -> List[str]:
        parameters = [
            f"--job-name={self.job_name}",
            f"--nodes={self.nodes}" if self.nodes is not None else None,
            f"--mem={self.mem}" if self.mem is not None else None,
            f"--mem-bind={self.mem_bind}" if self.mem_bind is not None else None,
            f"--mem-per-cpu={self.mem_per_cpu}" if self.mem_per_cpu is not None else None,
            f"--cpus-per-task={self.cpus_per_task}" if self.cpus_per_task is not None else None,
            f"--ntasks={self.n_tasks}" if self.n_tasks is not None else None,
            f"--time={self.time_limit}" if self.time_limit is not None else None,
            f"--time-min={self.time_min}" if self.time_min is not None else None,
            f"--exclusive" if self.exclusive else None,
            f"--network={self.network}" if self.network is not None else None,
            f"--contiguous" if self.contiguous else None,
            f"--partition={self.partition}" if self.partition is not None else None,
            f"--power={self.power}" if self.power is not None else None,
            f"--priority={self.priority}" if self.priority is not None else None,
            f"--nice={self.nice}" if self.nice is not None else None,
            f"--comment=\"{self.comment}\"" if self.comment is not None else None,
            f"--chdir={self.chdir}" if self.chdir is not None else None,
            f"--export={self.export}" if self.export is not None else None,
            f"--output={self.stdout_file}" if self.stdout_file is not None else None,
            f"--error={self.stderr_file}" if self.stderr_file is not None else None,
        ]
        return [x for x in parameters if x is not None]

    def to_sbatch_file_string(self, script_lines: List[str]) -> str:
        assert len(script_lines) > 0
        lines = ["#!/bin/bash", ""]
        lines.extend([f"#SBATCH {x}" for x in self.get_cli_parameters()])
        lines.append("")
        lines.extend(script_lines)
        return "\n".join(lines)

    def to_srun_interactive_command_string(
            self, add_pty: bool = True, shell: str = "bash"
    ) -> str:
        command = ["srun"]
        command.extend(self.get_cli_parameters())
        if add_pty:
            command.append("--pty")
        command.append(shell)
        return " ".join(command)


class SLURMInterface:

    @staticmethod
    def get_id_from_name(job_name: str) -> Optional[str]:
        """
        Returns the last submitted job id from a given job name
        :param job_name:  The job name
        :return:          The job id or None if no job with the given name exists
        """
        retcode, stdout, _ = _system(
            f"sacct --name \"{job_name}\" --noheader -P --format=JobID,JobName,Submit")
        if retcode != 0:
            return None
        stdout_lines = stdout.split("\n")
        if len(stdout_lines) == 0:
            return None
        # Filter lines that do not match the job name
        stdout_lines = [x for x in stdout_lines if job_name in x.strip().split("|")[1]]
        if len(stdout_lines) == 0:
            return None
        # Find the newest job, format of the date is YYYY-MM-DDTHH:MM:SS
        newest_job = max(stdout_lines, key=lambda x: x.strip().split("|")[2])
        return newest_job.strip().split("|", 1)[0]

    @staticmethod
    def sacct(job_id: str) -> Optional[SLURMRegisteredJobData]:
        variables = SLURMRegisteredJobData.variables()
        retcode, stdout, _ = _system(
            f"sacct --jobs {job_id} --noheader -P --format={','.join(variables)}")
        if retcode != 0 or len(stdout) == 0:
            return None
        stdout_lines = stdout.split("\n", 1)
        if len(stdout_lines) == 0:
            return None
        job_variables = stdout_lines[0].strip().split("|")
        return SLURMRegisteredJobData(dict(zip(variables, job_variables)))

    @staticmethod
    def exists(job_id: str) -> bool:
        return SLURMInterface.sacct(job_id) is not None

    @staticmethod
    def scancel(job_id: str) -> bool:
        retcode, stdout, stderr = _system(f"scancel {job_id}")
        return retcode == 0

    @staticmethod
    def skill(job_id: str, signal_no=signal.SIGKILL) -> bool:
        retcode, _, _ = _system(f"skill {job_id} -s {signal_no.value}")
        return retcode == 0

    @staticmethod
    def sbatch(sbatch_filepath: str) -> Optional[str]:
        """
        Submits a job request to SLURM
        :param sbatch_filepath:  The path to the sbatch file to submit
        :return:                 The job id or None if the job could not be submitted
        """
        retcode, stdout, stderr = _system(f"sbatch --parsable {sbatch_filepath}")
        if retcode != 0:
            return None
        job_id = stdout.strip().split("\n", 1)[0].split(";", 1)[0]
        return job_id
