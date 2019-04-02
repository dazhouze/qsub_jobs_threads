# qsub_jobs_threads
- Read Makefile and submit parallel multi-threads jobs to Sun Grid Engine (SGE).
- If user qdel a job in 'qw' state, a period of time(TIMEOUT) later the program will stop.
- Jobs will be submitted in -pe smp(PE), and log directory will be 'log_SGE'(LOG_DIR).
- Logs will be append to file log_SGE.out.
- Specifal comment in the 'target: dependence' line, #-@ INT, will be the threads (INT). 
- No comment (#...) is allowed in command line.

## Mechanism:
- Using qstat (1st(id) and 5th(state) column) to get jobs ongoing/waiting information. 
- Using qacct (exit_status row) to get jobs stopped(success/fail) information.

## Install:
```
# download.
git clone git@github.com:dazhouze/qsub_jobs_threads.git
# add the directory to environment variable.
export PATH=dir/of/qsub_jobs_threads:$PATH
```

## Run:
```
# More options will be shown in terminal.
qsub_jobs_threads -j #jobs -t #threads -f makefile -q queue
# or
qsub_jobs_threads <#jobs> <#threads> <makefile> [queue]
```
