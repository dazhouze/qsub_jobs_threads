#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Read Makefile and submit parallel multi-threads jobs to Sun Grid Engine (SGE).

Using 2 objects Parallel_jobs(with nested _Job), and Makefile(with nested _Rule).
Using qstat (1st(id) and 5th(state) column) to get jobs ongoing/waiting information. 
Using qacct (exit_status row) to get jobs stopped(success/fail) information.

If usr qdel a job in qw state, a period of time(TIMEOUT) later the program will stop.
Jobs will be submitted in -pe smp(PE), and log directory will be 'log_SGE'(LOG_DIR).

Specifal comment in the 'target: dependence' line, #-@ INT, will be the threads (INT). 
No comment (#...) is allowed in command line.
'''

__author__ = 'ZHOU Ze <dazhouze@link.cuhk.edu.hk>'
__version__ = '2.0'

import os
import subprocess as sp
import datetime
from time import sleep
import sys
import getopt

TIMEOUT = 2*60  # 2min
PE = 'smp'  # pe in SGE
LOG_DIR = 'log_SGE'  # log directory

class Parallel_jobs(object):
	'''
	A batch of jobs (_Job).
	'''

	##### Nested Job. #####
	class _Job(object):
		'''
		Single job object.
		'''
		def __init__(self):
			self._sge_name = None  # the string behind qsub -N
			self._target = None  # makefile target
			self._record_time = None  # the starting time
			self._id = None  # the sge given id
			self._status = None  # the sge job status

		def __repr__(self):
			return '{} {}'.format(self._sge_name, self._status)
	
		def set_status(self, status, time_now):  # job status
			if status is not None:
				self._status = status
				self._record_time = time_now

		def get_id(self):
			return self._id

		def get_status(self):
			return self._status

		def get_target(self):
			return self._target

		def is_timeout(self, time_now):
			'''
			Return if job timeout.
			'''
			if (time_now - self._record_time).total_seconds() > TIMEOUT:
				print('Job {} or {} \tID: {}\tName: {}\tTime: {}'
					.format('qdel while job qw',  # possible reason 1
						"qacct can't accounting file",  # possible reason 2
						self._id,
						self._sge_name, 
						time_now.strftime('%Y-%m-%d %H:%M:%S')))
				return True
			return False

		def is_finished(self):
			'''
			Return False if job stopped with error.
			Return True if job finished successfully.
			Return None if without information.
			'''
			if isinstance(self._status, int):  # finished
				if self._status > 0:  # stopped error
					self.kill('error ({})'.format(self._status))
					return False
				else:  # finished successfully
					print('Job finished\tID: {}\tName: {}\tTime: {}'
						.format(self._id,
							self._sge_name, 
							datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
					return True
			return None  # un-finished

		def submit(self, target, command, threads, queue, pe, log_dir):
			'''
			Submit job.
			'''
			if '/' in target:  # path as name (target)
				sge_name = target  # name for SGE, qsub -N
				sge_name = sge_name[:-1] if sge_name[-1] == '/' else sge_name  # in case of /
				sge_name = sge_name.split('/')[-1]  # use basename as name (target)
			else:
				sge_name = target  # name for SGE, qsub -N
			if sge_name[0].isdigit():  # sge NOT allow -N start with digital
				sge_name = 'Job_{}'.format(sge_name)
			stdout_log_dir = stderr_log_dir = os.path.join(os.getcwd(), log_dir)
	
			# qsub
			sge_par = '-v PATH -cwd -pe {} {} -q {}'.format(pe, threads, queue) 
			qsub_command = 'qsub {} -N "{}" -o :"{}" -e :"{}" <<E0F\n{}\nE0F'\
					.format(sge_par,
					sge_name,
					stdout_log_dir,
					stderr_log_dir,
					command)
			#print(qsub_command)
			p = sp.Popen(qsub_command, shell=True, stdout = sp.PIPE, stderr = sp.PIPE)
			# job id
			stdout, stderr = p.communicate()
			stdout, stderr = stdout.decode("utf-8"), stderr.decode("utf-8")
			if stderr != '':  # qusb error
				sys.exit('SGE qsub error:\n{}'.format(stderr))
			job_id = stdout.split()[2]  # id is str
			# init
			self._sge_name = sge_name
			self._target = target
			self._record_time = datetime.datetime.now()  # the submit time
			self._id = job_id  # the sge given id
			self._status = 't'  # the sge job status
			print('Job submit\tID: {}\tName: {}\tTime: {}\tQueue: {}\tCPU: {}'
					.format(self._id,
						self._sge_name,
						self._record_time.strftime('%Y-%m-%d %H:%M:%S'),
						queue,
						threads))

		def kill(self, reason='error'):
			'''
			kill this job.
			'''
			p = sp.Popen('qdel {}'.format(self._id),
					shell=True,
					stdout = sp.PIPE,
					stderr = sp.PIPE)
			print('Job {}\tID: {}\tName: {}\tTime: {}'
					.format(reason, 
						self._id,
						self._sge_name, 
						datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
	
	##### High level Parallel_jobs API #####
	def __init__(self, n_jobs, threads, queue='all.q', pe='smp', log_dir='log_SGE'):
		self._jobs_array = [None for n in range(n_jobs)]  # jobs array for parallel jobs
		self._threads = threads
		self._queue = queue
		self._pe = pe
		self._log_dir = log_dir

	def __repr__(self):
		return ','.join([ '{}'.format(x) for x in self._jobs_array])

	def submit_all(self, dependence_satisfied_rules):
		'''
		dependence unsatisfied jobs array
		'''
		for idx in range(len(self._jobs_array)):
			if self._jobs_array[idx] is None and len(dependence_satisfied_rules) > 0:
				name, command, threads = dependence_satisfied_rules.pop()
				#print(name, command, threads)
				self._jobs_array[idx] = self._Job()  # init
				self._jobs_array[idx].submit(name,
						command,
						max(self._threads, threads),
						self._queue,
						self._pe,
						self._log_dir)

	def update_all(self):
		'''
		Update all jobs status.
		'''
		time_now = datetime.datetime.now()
		status_dt = self._qstat()  # id: state
		#print(status_dt)
		for idx,job in enumerate(self._jobs_array):  # _Job object
			if job is None:  # empty
				continue
			job_id = job.get_id()
			job_status = status_dt.get(job_id, None)  # None for no qstat jobs
			if job_status is not None:  # valid ongoing/waiting state
				job.set_status(job_status, time_now)
			else:  # qacct check finished status
				exit_status = self._qacct_exit_status(job_id)
				job.set_status(exit_status, time_now)

	def check_error(self):
		'''
		Kill Eqw, dr jobs and error finished jobs.
		Return True if error happend.
		'''
		err_typ = False  # if job Eqw and need kill
		for idx,job in enumerate(self._jobs_array):
			if job is None:
				continue
			status = job.get_status()
			if status == 'Eqw' or status == 'dr':  # ongoing/waiting error
				job.kill(status)  # kill this job
				self._jobs_array[idx] = None  # empty the job
				err_typ = status
			if job.is_finished() is False:  # stopped with error
				#self._jobs_array[idx] = None  # empty the job
				err_typ = 'exit_error'
		return err_typ

	def clean_finished(self, finished_jobs):
		'''
		Clean finished jobs.
		'''
		ongoing_jobs = set()
		for idx,job in enumerate(self._jobs_array):
			if job is None:
				continue
			status = job.get_status()  # t/qw/r/dr/None/0
			#print(job)
			if isinstance(status, int):  # successful finished / exit with error
				finished_jobs.add(job.get_target())  # target is same as makefile context
				self._jobs_array[idx] = None
			else:  # None: without info, digital>0: error
				ongoing_jobs.add(self._jobs_array[idx].get_target())  # target is same as makefile context
		return finished_jobs, ongoing_jobs

	def deduce_disappeared(self):
		'''
		Deduce disappeared jobs. e.g. User qdel jobs in qw status or qacct can't
		access the accounting file.
		Return True if timeout.
		'''
		time_now = datetime.datetime.now()
		job_err = False
		for idx,job in enumerate(self._jobs_array):  # _Job object
			if job is None:  # not empty
				continue
			if job.is_timeout(time_now):
				job_err = True
		return job_err

	def kill_all(self):
		'''
		Kill all jobs.
		'''
		for job in self._jobs_array:
			if job is not None:
				job.kill('auto-kill')

	def is_full(self):
		'''
		All items in jobs_array as assgin jobs.
		'''
		for job in self._jobs_array:
			if job is None:  # empty
				return False
		return True

	def is_empty(self):
		'''
		All items in jobs_array are None.
		'''
		for job in self._jobs_array:
			if job is not None:  # with job
				return False
		return True

	##### Basic func implement using Linux command. #####
	def _qstat(self,):
		'''
		Return status of all jobs in self.jobs_array
		'''
		result = {}  # id: state
		p = sp.Popen("qstat | awk \'{print $1, $5}\'",
				shell=True,
				stdout = sp.PIPE,
				stderr = sp.PIPE)
		stdout, stderr = p.communicate()
		stdout = stdout.decode("utf-8")

		for s in stdout.split('\n'):
			info = s.split()
			if len(info) < 2 or not info[0].isdigit():  # skip header
				continue
			job_id, state = info
			result.setdefault(job_id, state)
		return result
	
	def _qacct_exit_status(self, job_id):
		'''
		Finished job status
		qacct -j job_id
		'''
		p = sp.Popen('qacct -j {} | grep exit_status'.format(job_id),
				shell=True,
				stdout = sp.PIPE,
				stderr = sp.PIPE)
		stdout, stderr = p.communicate()
		stdout = stdout.decode("utf-8")
		if stdout == '':
			return None
		exit_status = int(stdout.rstrip().split()[1])  # first is 'exit_status', sec is the number
		return exit_status  # exit_status > 0, error

class Makefile(object):
	'''
	Analysis simple makefile (without varibles).
	Key word 'all:' for final processing.
	'''
	##### Nested rule (_Rule) object. #####
	class _Rule(object):
		def __init__(self, depend, command, threads=1):
			self._depend = depend
			self._command = command
			self._threads = threads

		def get_info(self):
			return self._depend, self._command, self._threads

		def __repr__(self):
			return '{} {} {}'.format(self._depend, self._command, self._threads)

	##### Makefile API #####
	def __init__(self, make_file):
		'''
		read and analysis makefile.
		'''
		self._rules = {}  # dict of _Rule object, key is target
		# read and analysis Makefile
		buff_line = []
		with open(make_file, 'r') as f:
			for line in f:
				if line.replace(' ','').replace('\t','') == '\n' or\
					line.replace(' ','').replace('\t','')[0] == '#':
						continue
				if line[0] != '\t' and len(buff_line) > 0: # analysis makefile
					self._buff2rule(buff_line)
					buff_line = []
				buff_line.append(line)
			self._buff2rule(buff_line)  # for last line

	def _buff2rule(self, buff_line):
		'''
		buffer line array to target(target): dependence commands rule.
		'''
		if len(buff_line) == 0:
			return True
		info = buff_line[0].rstrip().split('#')  # Easter Egg: #-@
		if len(info) > 1 :  # comment in target line, and check the Easter Egg
			threads = buff_line[0].rstrip().split('#-@')[1].strip()  # get threads
			threads = int(threads) if threads.isdigit() else 1  # avoid not INT
		else:
			threads = 1  # min thread is 1
		info = info[0].split(':')
		target, depend_str = info[0], info[1]
		target, depend_ar = target.replace(' ', ''), depend_str.split()
		if target == 'all' or target == 'ALL':  # continue
			return True
		# in case of mulit-line command, no comment is allowed in command
		command_str = 'true ; ' +  ' ; '.join([l.strip() for l in buff_line[1:]])
		if self._file_dir_exit(target):  # already finished
			print('Job already finished\tName: {0}'.format(target))
			return True
		# union bash and make varible. for $, make: $$, qsub:\$, sh: $
		command_str = command_str.replace('$$', '$').replace('$', '\$')  # makefile variable to bash variable
		self._rules.setdefault(target, self._Rule(depend_ar, command_str, threads))
		return True

	def _file_dir_exit(self, f_d):
		'''
		Retrun if file or dir exits.
		'''
		cwd = os.getcwd()  # current dir
		if not os.path.isfile(f_d) and\
				not os.path.isdir(f_d):  # not in abs-path
			if not os.path.isfile('%s/%s' % (cwd, f_d)) and\
					not os.path.isdir('%s/%s' % (cwd, f_d)):  # not in current dir
						return False
		return True

	def get_rules(self, finished_jobs, ongoing_jobs):
		'''
		Return an array of rules which already saitisfy the dependence.
		Each item is a tuple of (target, command, threads).
		'''
		result = []
		target_ar = list(self._rules.keys())
		for target in target_ar:
			depend_ar, command, threads = self._rules[target].get_info()
			if target in finished_jobs:  # already finished
				del self._rules[target]
				continue
			if target in ongoing_jobs:  # is ongoing
				continue
			# check dependence
			dependence_satisfied = True
			for d in depend_ar:
				# not in finished job target (target) and not exits
				if d not in finished_jobs and\
						self._file_dir_exit(d) is False:
					dependence_satisfied = False
			if dependence_satisfied:  # all dependence satisfied
				result.append( (target, command, threads) )
		return result

	def get_remaining_rules(self, finished_jobs):
		'''
		Return rules which un-saitisfy the dependence.
		'''
		result = []
		for target, rule in self._rules.items():
			if target in finished_jobs:
				continue
			result.append(target)
		return result

def usage():
	'''
	Print program usage information.
	'''
	result = ''
	result += '\nProgram: {} (Parallel multi-threads jobs qsub)\n'.format(__file__)
	result += 'Version: {}\n'.format(__version__)
	result += 'Contact: {}\n'.format(__author__)
	result += '\nUsage:\n'
	result += '\tqsub_jobs_threads <\033[95m-j\033[0m #jobs> <\033[95m-f\033[0m makefile>\n'
	result += '\tor\n'
	result += '\tqsub_jobs_threads <#jobs> <#threads> <makefile> [Queue]\n'
	result += '\nOptions:\n'
	result += '\t\033[95m-j\033[0m:\tINT\tNumber of parallel jobs. (default 1)\n'
	result += '\t\033[95m-f\033[0m:\tSTR\tPath of makefile.\n'
	result += '\t-t:\tINT\tNumber of threads(CPUs) using in every job. (default 1)\n'
	result += '\t-q:\tSTR\tCluster queue name. all.q(default)/high.q/mem.q\n'
	result += '\t-k:\t   \tSkip error jobs, do not auto-Kill rest jobs.\n'
	result += '\t-h:\t   \tHelp information.\n'
	result += '\n\033[95mEaster Egg:\033[0m\n'
	result += '\tIn the makefile, a rule consists of three parts, <target>, <dependencies>\n'
	result += '\tand <commands>. You can specify the number of threads(INT) using in a\n'
	result += '\tparticular rule, by adding "\033[95m#-@\033[0m INT" in the same line following the\n'
	result += '\t<dependencies>. Also, please do \033[95mNOT\033[0m add any comment (#...) in the same\n'
	result += '\tline of the <commands>.\n\n'
	result += '\t##### e.g. \033[95m20\033[0m threads for SOAP alignment #####\n'
	result += '\tsoap_align: depend.fq \033[95m#-@ 20\033[0m\n'
	result += '\t\tsoap -p \033[95m20\033[0m ...other options...\n'
	return result

if __name__ == "__main__":
	# get paraters
	n_jobs, threads, make_file, queue, auto_kill = 1, 1, None, 'all.q', True  # default
	try:
		opts, args = getopt.getopt(sys.argv[1:], "hkj:t:f:q:")
	except getopt.GetoptError:
		sys.exit(usage())
	for opt, arg in opts:
		if opt == '-h':
			sys.exit(usage())
		elif opt == '-k':
			auto_kill = False
		elif opt == '-j':
			n_jobs = int(arg)
		elif opt == '-t':
			threads = int(arg)
		elif opt == '-f':
			make_file = arg
		elif opt == '-q':
			queue = arg
		else:
			sys.exit(usage())

	# old style paramters
	if 3 <= len(args) <= 4 and len(opts) == 0:  # old style paraters #jobs #threads makefile (queue)
		n_jobs, threads, make_file = int(args[0]), int(args[1]), args[2]
		queue = args[3] if len(args) == 4 else queue
	elif len(args) > 0 or make_file is None:  # untraced paramters
		sys.exit(usage())

	# makefile
	if not os.path.isfile(make_file):
		sys.exit('\nNo such file: {}\n{}'.format(make_file, usage()))

	# output log dir
	if not os.path.exists(LOG_DIR):
		os.makedirs(LOG_DIR)

	# init job array
	mk = Makefile(make_file)  # make file
	jobs = Parallel_jobs(n_jobs, threads, queue, pe=PE, log_dir=LOG_DIR)
	finished_jobs = set()  # store finished job name (target)

	# loop of SGE job submit
	while True:
		# update all jobs status
		jobs.update_all()

		# if Eqw, dr, or exit status error, kill all jobs and exit the moniter program
		err_typ = jobs.check_error()
		if err_typ is not False:  # Eqw/dr/error
			if not (err_typ == 'exit_error' and\
					auto_kill==False):  # exit error, but not auto-kill rest
				jobs.kill_all() # kill rest of jobs
				print('Moniter program Stopped\tTime: {}\tMakefile: {}'\
						.format(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), make_file))
				break

		# clean finished jobs and log ongoing jobs
		finished_jobs, ongoing_jobs =\
				jobs.clean_finished(finished_jobs)
		#print(finished_jobs)

		# check if qw qdel or lost job (cannt access accounting file)
		if jobs.deduce_disappeared() is not False:
			jobs.kill_all() # kill rest of jobs
			print('Moniter program Stopped\tTime: {}\tMakefile: {}'\
					.format(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), make_file))
			break

		# submit new jobs
		if not jobs.is_full():
			dependence_satisfied_rules = mk.get_rules(finished_jobs, ongoing_jobs)
			jobs.submit_all(dependence_satisfied_rules)

		# check if all jobs finished	
		if jobs.is_empty():
			dependence_unsatisfied_rules = mk.get_remaining_rules(finished_jobs)
			if len(dependence_unsatisfied_rules) == 0:
				print('Jobs are all finished\tTime: {}\tMakefile: {}'.\
						format(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), make_file))
			else:
				print('Jobs stopped with dependence unsatisfied jobs\tTime: {}\tMakefile: {}\t{}'.\
						format(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
							make_file, ','.join(dependence_unsatisfied_rules),))
			break

		# time interval
		sleep(5)
