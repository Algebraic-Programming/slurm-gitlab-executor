# GitLab custom executor for Slurm

<img alt="GitHub License" src="https://img.shields.io/github/license/Algebraic-Programming/slurm-gitlab-executor?label=License&color=%23FDEE21&style=for-the-badge"> <img alt="GitHub Actions Workflow Status" src="https://img.shields.io/github/actions/workflow/status/Algebraic-Programming/slurm-gitlab-executor/pylint.yml?logo=python&logoColor=white&label=Pylint&style=for-the-badge">

> ⭐ This project is actively maintained and contributions are welcomed !

This repository provides a GitLab custom executor for Slurm, allowing you to run your GitLab CI/CD jobs
directly on your own Slurm cluster.

**Requirement:** This executor does not allow SSH access, the GitLab executor needs to be running on the same machine as the Slurm frontend.

**Dependencies:**
* Python 3.6+ (no external module)
* GitLab Runner 12.1.0+
* UNIX environment

## Runner setup

1. Clone this repository:
    ```bash
    git clone https://github.com/Algebraic-Programming/slurm-gitlab-executor.git slurm-gitlab-executor
    cd slurm-gitlab-executor
    ```

2. Create a configuration with GitLab Runner by following
   the [registration instructions](https://docs.gitlab.com/runner/commands/#interactive-registration). This will
   generate a **config.toml** from which you can generate the final configuration.
    ```bash
    gitlab-runner register --name slurm-gitlab-executor --url https://mydomain.gitlab.com --token glrt-t0k3n 
    ```

3. Use the `generate-config.sh` script to generate another **config.toml**:
    ```bash
    ./generate-config.sh /path/to/generated/config/dir/config.toml > /path/to/slurm-gitlab-executor/config.toml
    ```

   You should end up with a configuration similar to this one:
    ```toml
    check_interval = 0
    shutdown_timeout = 0

    # Amount of concurrent Slurm jobs that can be running at the same time
    concurrent = 10

    [[runners]]
        executor = "custom"

        # Values generated by "gitlab-runner register"
        name = "my-slurm-gitlab-executor" # This is the name of your runner
        url = "https://gitlab.my-domain.com/" # This is the URL of your GitLab instance
        id = "11" # This is the runner id
        token = "glrt-g1b3rr1sh" # This is the runner token
        token_obtained_at = "2023-01-01T00:00:00Z"
        token_expires_at = "2024-01-01T00:00:00Z"

        # Paths to the builds and cache directories
        # - must be absolute
        # - must be owned by the user running gitlab-runner
        # - must have enough space to store potential large artifacts
        builds_dir = "/path/to/slurm-gitlab-executor/wd/builds"
        cache_dir = "/path/to/slurm-gitlab-executor/wd/cache"

        # Un-comment me out during debugging
        # log_level = "debug"

        # Paths to the driver/main.py executable controlling the Slurm jobs
        [runners.custom]
            config_exec = "/path/to/slurm-gitlab-executor/driver/main.py"
            config_args = ["config", "/path/to/slurm-gitlab-executor/wd/builds", "/path/to/slurm-gitlab-executor/wd/cache"]
            prepare_exec = "/path/to/slurm-gitlab-executor/driver/main.py"
            prepare_args = ["prepare"]
            run_exec = "/path/to/slurm-gitlab-executor/driver/main.py"
            run_args = ["run"]
            cleanup_exec = "/path/to/slurm-gitlab-executor/driver/main.py"
            cleanup_args = ["cleanup"]
    ```

4. The runner can be executed in many ways:
    * In a shell: \
      ```./gitlab-runner run --config /path/to/slurm-gitlab-executor/config.toml```
    * In a _screen_ session : \
      ```screen -S slurm-gitlab-executor -dmS ./gitlab-runner run --config /path/to/slurm-gitlab-executor/config.toml```
    * As a service (recommended): \
      ```bash
      sudo cp /path/to/slurm-gitlab-executor/gitlab-runner.service /etc/systemd/system/
      sudo systemctl daemon-reload
      sudo systemctl enable gitlab-runner
      sudo systemctl start gitlab-runner
      ```

## Job setup

* Example job configuration (more detailed version [here](./.gitlab-ci.yml)):
    ```yaml
    default:
      tags:
        - slurm
    
    variables:
        CI_SLURM_PARTITION:
          value: "x86"
          description: "Slurm partition to use"
          options: ["x86", "arm"]
        CI_SLURM_NNODES: 
          value: "1"
          description: "Number of nodes"
        CI_SLURM_NTASKS: 
          value: "1"
          description: "Number of tasks"
        CI_SLURM_CPUS_PER_TASK: 
          value: "8"
          description: "Number of CPUs per task"
        CI_SLURM_MEM_PER_NODE: 
          value: "32G"
          description: "Memory available per node"
        CI_SLURM_TIMELIMIT:
          value: "00-01:00:00" # 0 days, 1 hour, 0 minutes, 0 seconds
          description: "Time limit (format: days-hours:minutes:seconds)"
    
    # Simple job executed in a Slurm job with 8 cpus
    my_parallel_slurm_job:
        script:
            - echo "Hello from the Slurm cluster, in job ${SLURM_JOB_NAME}!"
            - touch output_from_parallel_job.txt
        artifacts:
            paths:
              - output_from_parallel_job.txt

    # Simple job executed in a Slurm job with only 1 cpu
    my_sequential_slurm_job:
        variables:
          # Any Slurm variable can be overridden using the "LOCAL_" prefix
          LOCAL_CI_SLURM_CPUS_PER_TASK: "1"
        script:
            - echo "Hello from the Slurm cluster, in job ${SLURM_JOB_NAME}!"
            - touch output_from_sequential_job.txt
        artifacts:
            paths:
              - output_from_sequential_job.txt
    
    # Simple job executed in a Docker, gathering the exported artifacts 
    # from the two Slurm jobs above
    my_docker_job:
      needs: [my_parallel_slurm_job, my_sequential_slurm_job]
      tags:
        - docker
      image: ubuntu:latest
      script:
        - ls -l
        - echo "Successful execution"
    ```

### Supported Slurm options:

Based on the [Slurm documentation](https://slurm.schedmd.com/sbatch.html#SECTION_INPUT-ENVIRONMENT-VARIABLES),
with every _SBATCH_VAR_ replaced by _SLURM_VAR_.

| GitLab CI variable             | CLI equivalent                                                                  | Supported  | Options / Format             | Default                                |
|--------------------------------|---------------------------------------------------------------------------------|:----------:|------------------------------|----------------------------------------|
| CI_**SLURM_PARTITION**         | [-p / --partition](https://slurm.schedmd.com/sbatch.html#OPT_partition)         |     ✅     |                              |                                        |
| CI_**SLURM_NNODES**            | [-N / --nodes](https://slurm.schedmd.com/sbatch.html#OPT_nodes)                 |     ✅     |                              |                                        |
| CI_**SLURM_MEM_PER_NODE**      | [--mem](https://slurm.schedmd.com/sbatch.html#OPT_mem)                          |     ✅     |                              |                                        |
| CI_**SLURM_MEM_BIND**          | [--mem-bind](https://slurm.schedmd.com/sbatch.html#OPT_mem-bind)                |     ✅     |                              |                                        |
| CI_**SLURM_MEM_PER_CPU**       | [--mem-per-cpu](https://slurm.schedmd.com/sbatch.html#OPT_mem-per-cpu)          |     ✅     |                              |                                        |
| CI_**SLURM_CPUS_PER_TASK**     | [-c / --cpus-per-task](https://slurm.schedmd.com/sbatch.html#OPT_cpus-per-task) |     ✅     |                              |                                        |
| CI_**SLURM_NTASKS**            | [--ntasks](https://slurm.schedmd.com/sbatch.html#OPT_ntasks)                    |     ✅     |                              |                                        |
| CI_**SLURM_TIMELIMIT**         | [-t / --time](https://slurm.schedmd.com/sbatch.html#OPT_time)                   |     ✅     | *days-hours:minutes:seconds* | `00-02:00:00`                          |
| CI_**SLURM_TIME_MIN**          | [--time-min](https://slurm.schedmd.com/sbatch.html#OPT_time-min)                |     ✅     |                              |                                        |
| CI_**SLURM_EXCLUSIVE**         | [--exclusive](https://slurm.schedmd.com/sbatch.html#OPT_exclusive)              |     ✅     | `yes`, `no`                  | `no`                                   |
| CI_**SLURM_NETWORK**           | [--network](https://slurm.schedmd.com/sbatch.html#OPT_network_1)                |     ✅     |                              |                                        |
| CI_**SLURM_CONTIGUOUS**        | [--network](https://slurm.schedmd.com/sbatch.html#OPT_contiguous)               |     ✅     | `yes`, `no`                  | `no`                                   |
| CI_**SLURM_POWER**             | [--power](https://slurm.schedmd.com/sbatch.html#OPT_power)                      |     ✅     |                              |                                        |
| CI_**SLURM_CI_SLURM_PRIORITY** | [--priority](https://slurm.schedmd.com/sbatch.html#OPT_priority)                |     ✅     |                              |                                        |
| CI_**SLURM_CI_SLURM_NICE**     | [--nice](https://slurm.schedmd.com/sbatch.html#OPT_nice)                        |     ✅     |                              |                                        |
| CI_**SLURM_MEM_PER_CPU**       | [--mem-per-cpu](https://slurm.schedmd.com/sbatch.html#OPT_mem-per-cpu)          |     ✅     |                              |                                        |
| CI_**SLURM_COMMENT**           | [--comment](https://slurm.schedmd.com/sbatch.html#OPT_comment)                  |     ✅     |                              | `Automatic job created from GitLab CI` |
| CI_**SLURM_GPUS**              | [-G / --gpus](https://slurm.schedmd.com/sbatch.html#OPT_gpus)                   |     ⌛     |                              |                                        |
| CI_**SLURM_GPUS_PER_NODE**     | [--gpus-per-node](https://slurm.schedmd.com/sbatch.html#OPT_gpus-per-node)      |     ⌛     |                              |                                        |
| CI_**SLURM_GPUS_PER_TASK**     | [--gpus-per-task](https://slurm.schedmd.com/sbatch.html#OPT_gpus-per-task)      |     ⌛     |                              |                                        |
| CI_**SLURM_CPUS_PER_GPU**      | [--cpus-per-gpu](https://slurm.schedmd.com/sbatch.html#OPT_mem-per-gpu)         |     ⌛     |                              |                                        |
| Others...                      |                                                                                 |     ❌     |                              |                                        |

### Supported runner options:

| GitLab CI variable                               | Description                                                                                                    | Supported  | Options                 | Default |
|--------------------------------------------------|----------------------------------------------------------------------------------------------------------------|:----------:|-------------------------|---------|
| **CI_KEEP_BUILD_DIR**                            | If true, the build folder in the Slurm cluster will not get removed after a successful execution of the job    |     ✅     | `yes`, `no`             | `no`    |
| **CI_LOG_LEVEL_SLURM_EXECUTOR**                  | Log level of the executor                                                                                      |     ✅     | `debug`, `info`, `none` | `info`  |
| **SLURM_JOB_START_TIMEOUT_SECONDS**              | Time limit to wait for a Slurm job to pass from *PENDING* to *RUNNING* before considering failure (in seconds) |     ✅     |                         | `1200`  |
| **SLURM_JOB_STOP_TIMEOUT_SECONDS_BEFORE_CANCEL** | Time limit to wait before cancelling a Slurm job that received a stop request (in seconds)                     |     ✅     |                         | `30`    |

## Troubleshooting

> **Q:** My CI job was killed for timeout because the Slurm job stayed _PENDING_ for too long, what should I do ?
>
> **A:** Increase this GitLab variable: **Settings > CI/CD > Runners > edit-icon > Maximum job timeout**. This value is
> the maximum time you expect your CI job to run + the time to schedule it on the cluster.

> **Q:** My job is killed for timeout because the jobs stays _RUNNING_ for too long, what should I do ?
>
> **A:** Increase this Slurm variable: **CI_SLURM_TIMELIMIT** (format is days-hours:minutes:seconds).

> **Q:** Sometimes I can not see the logs of my failed jobs, what should I do ?
>
> **A:** If for any reason the job fails before the logs are sent back to GitLab, you can still access them on the
> cluster. At the beginning of the job, the executor will print the path to the logs on the cluster. You can then
> connect to the cluster and check the logs manually.

> **Q:** I noticed that some jobs stayed active after the job was finished, what should I do ?
>
> **A:** The maximum time a job can stay active without receiving any update is 10 minutes. Past this time, the job is
> supposed to stop by itself.
> If it's not the case, please create an issue on GitHub and provide as much information as you can.

## Copyright and Licensing

<pre>
  Copyright 2024 Huawei Technologies Co., Ltd.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
</pre>
