#!/bin/bash

env > env.log

rm ./stdout.log 2>/dev/null
rm ./stderr.log 2>/dev/null
exec 1<&-
exec 2<&-
exec 1<>./stdout.log
exec 2<>./stderr.log

n_executions=0
n_sleeps=0

echo "[$(date)]  -  Starting SLURM waiting loop ..."
while true; do

    exit_script_exists=$(find . -maxdepth 1 -type f -name '*.gitlab_ci_exit' | wc -l) || true
    if [ "$exit_script_exists" -ge 1 ]; then
        echo "[$(date)]  -  Exiting SLURM waiting loop ..."
        exit 0
    fi

    # Search for any file with .gitlab_ci_step_script extension (might be zero)
    script_exists=$(find . -maxdepth 1 -type f -name '*.gitlab_ci_step_script' | wc -l) || true
    if [ "$script_exists" -ge 1 ]; then
        n_executions=$((n_executions+1))
        # If there is a script, execute it
        script_path=$(find . -maxdepth 1 -type f -name '*.gitlab_ci_step_script' | head -n 1)

        sleep 1;
        echo "[$(date)]  -  Starting execution of $script_path ...";

        log_script_path="$script_path.log";
        bash "$script_path" > "$log_script_path" 2>&1;
        # If return code is not 0, exit with error
        if [ "$?" -ne 0 ]; then
            echo "[$(date)]  -  Error executing $script_path";
            exit 1;
        fi

        executed_script_path="$script_path.executed";
        # Create the script with .gitlab_ci_step_script.executed extension, copy the content, then delete the original one
        touch "$executed_script_path"
        cat "$script_path" > "$executed_script_path"
        rm "$script_path"
        # Flush the files+directory to avoid NFS caching issues
        sync -f "$executed_script_path"
        sync -f
        sync
        touch -c -a "$(pwd)"
        touch -c -m "$(pwd)"

        echo "[$(date)]  -  Finished execution of $script_path";
    fi

    sleep 1
    n_sleeps=$((n_sleeps+1))

    # If n_executions is null and n_sleeps is greater than 600, exit with error
    # Prevents the case where a SLURM job is scheduled but the CI got cancelled
    # before the appearance of the SLURM job in the sacct output
    if [ "$n_executions" -eq 0 ] && [ "$n_sleeps" -gt 600 ]; then
        echo "[$(date)]  -  No executions in the last 10 minutes, exiting with error";
        exit 1;
    fi
done