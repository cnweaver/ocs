import ocs

import txaio
txaio.use_twisted()

from twisted.internet import reactor, task, threads
from twisted.internet.defer import inlineCallbacks, Deferred, DeferredList, FirstError

from autobahn.wamp.types import ComponentConfig
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner

import time


def init_ocs_agent(address=None):
    cfg = ocs.get_ocs_config()
    server, realm = cfg.get('default', 'wamp_server'), cfg.get('default', 'wamp_realm')
    #txaio.start_logging(level='debug')
    agent = OCSAgent(ComponentConfig(realm, {}), address=address)
    runner = ApplicationRunner(server, realm)
    return agent, runner


class OCSAgent(ApplicationSession):

    def __init__(self, config, address=None):
        ApplicationSession.__init__(self, config)
        self.tasks = {}       # by op_name
        self.processes = {}   # by op_name
        self.sessions = {}    # by op_name, single OpSession.
        self.next_session_id = 0
        self.session_archive = {} # by op_name, lists of OpSession.
        self.agent_address = address
        
    def onConnect(self):
        self.log.info('transport connected')
        self.join(self.config.realm)

    def onChallenge(self, challenge):
        self.log.info('authentication challenge received')

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info('session joined: {}'.format(details))
        # Get an address somehow...
        if self.agent_address is None:
            self.agent_address = 'observatory.random'
        # Register our processes...
        # Register the device interface functions.
        yield self.register(self.my_device_handler, self.agent_address + '.ops')
        yield self.register(self.my_management_handler, self.agent_address)

    def onLeave(self, details):
        self.log.info('session left: {}'.format(details))
        self.disconnect()

    def onDisconnect(self):
        self.log.info('transport disconnected')
        # this is to clean up stuff. it is not our business to
        # possibly reconnect the underlying connection
        self._countdown -= 1
        if self._countdown <= 0:
            try:
                reactor.stop()
            except ReactorNotRunning:
                pass

    @inlineCallbacks
    def my_device_handler(self, action, op_name, params=None, timeout=None):
        if action == 'start':
            d = yield self.start(op_name, params=params)
        if action == 'stop':
            d = yield self.stop(op_name, params=params)
        if action == 'wait':
            d = yield self.wait(op_name, timeout=timeout)
        if action == 'status':
            d = yield self.status(op_name)
        print('Returning to caller', d)
        return d  #or returnValue(d), if python<3.3

    def my_management_handler(self, q, **kwargs):
        if q == 'get_tasks':
            result = []
            for k in sorted(self.tasks.keys()):
                session = self.sessions.get(k)
                if session is None:
                    session = {'op_name': k, 'status': 'no_history'}
                else:
                    session = session.encoded()
                result.append((k, session))
            return result
        if q == 'get_processes':
            result = []
            for k in sorted(self.processes.keys()):
                session = self.sessions.get(k)
                if session is None:
                    session = {'op_name': k, 'status': 'no_history'}
                else:
                    session = session.encoded()
                result.append((k, session))
            return result

    def publish_status(self, message, session):
        self.publish(self.agent_address + '.feed', session.encoded())


    """Instances of this class are used to connect blocking operation
    managers to the IOCS system.

    Multiple operations are grouped within a single server so that
    resources can be properly managed.
    """

    def register_task(self, name, func):
        self.tasks[name] = AgentTask(func)
        self.sessions[name] = None

    def register_process(self, name, start_func, stop_func):
        self.processes[name] = AgentProcess(start_func, stop_func)
        self.sessions[name] = None

    def handle_task_return_val(self, *args, **kw):
        (ok, message), session = args
        session.add_message(message)
        session.set_status('done')

    def start(self, op_name, params=None):
        print('start called for %s' % op_name)
        is_task = op_name in self.tasks
        is_proc = op_name in self.processes
        if is_task or is_proc:
            # Confirm it is currently idle.
            session = self.sessions.get(op_name)
            if session is not None:
                if session.status == 'done':
                    # Move to history...
                    #...
                    # Clear from active.
                    self.sessions[op_name] = None
                else:
                    return (ocs.ERROR, 'Operation "%s" already in progress.' % op_name,
                            session.encoded())
            # Mark as started.
            session = OpSession(self.next_session_id, op_name, app=self)
            self.next_session_id += 1
            self.sessions[op_name] = session
            # Schedule to run.
            if is_task:
                session.d = threads.deferToThread(
                    self.tasks[op_name].launcher, session, params)
                session.d.addCallback(self.handle_task_return_val, session)
                return (ocs.OK, 'Started task "%s".' % op_name,
                        session.encoded())
            else:
                proc = self.processes[op_name]
                session.d = threads.deferToThread(proc.launcher, session, params)
                session.d.addCallback(self.handle_task_return_val, session)
                return (ocs.OK, 'Started process "%s".' % op_name,
                        session.encoded())
        else:
            return (ocs.ERROR, 'No task or process called "%s"' % op_name, {})

    @inlineCallbacks
    def wait(self, op_name, timeout=None):
        if op_name in self.tasks or op_name in self.processes:
            session = self.sessions[op_name]
            if session is None:
                return (ocs.OK, 'Idle.', {})
            ready = True
            if timeout == 0:
                ready = bool(session.d.called)
            elif timeout is None:
                results = yield session.d
            else:
                # Make a timeout...
                td = Deferred()
                reactor.callLater(1., td.callback, None)
                dl = DeferredList([session.d, td], fireOnOneCallback=True,
                                  fireOnOneErrback=True, consumeErrors=True)
                try:
                    results = yield dl
                except FirstError as e:
                    assert e.index == 0  # i.e. session.d raised an error.
                    td.cancel()
                    e.subFailure.raiseException()
                else:
                    if td.called:
                        ready = False
            if ready:
                return (ocs.OK, 'Operation "%s" just exited.' % op_name, session.encoded())
            else:
                return (ocs.TIMEOUT, 'Operation "%s" still running; wait timed out.' % op_name,
                        session.encoded())
        else:
            return (ocs.ERROR, 'Unknown operation "%s".' % op_name, {})

    @inlineCallbacks
    def stop(self, op_name, params=None):
        if op_name in self.tasks:
            yield (ocs.ERROR, 'No implementation for "%s" because it is a task.' % op_name,
                    {})
        elif op_name in self.processes:
            session = self.sessions.get(op_name)
            proc = self.processes[op_name]
            d2 = threads.deferToThread(proc.stopper, params)
            yield (ocs.OK, 'Requested stop on process "%s".' % op_name, session.encoded())
        else:
            yield (ocs.ERROR, 'No process called "%s".' % op_name, {})

    @inlineCallbacks
    def abort(self, op_name, params=None):
        yield {'ok': False, 'error': 'No implementation for operation "%s"' % op_name}

    @inlineCallbacks
    def status(self, op_name, params=None):
        if op_name in self.tasks or op_name in self.processes:
            session = self.sessions.get(op_name)
            if session is None:
                yield (ocs.OK, 'No session active.', {})
            else:
                yield (ocs.OK, 'Session active.', session.encoded())
        else:
            yield (ocs.ERROR, 'No implementation for operation "%s"' % op_name, {})

class AgentTask:
    def __init__(self, launcher):
        self.launcher = launcher

class AgentProcess:
    def __init__(self, launcher, stopper):
        self.launcher = launcher
        self.stopper = stopper
    
class OpSession:
    def __init__(self, session_id, op_name, status='starting', log_status=True, app=None):
        self.messages = []  # entries are time-ordered (timestamp, text).
        self.session_id = session_id
        self.op_name = op_name
        self.start_time = time.time()
        self.end_time = None
        self.app = app
        # This has to be the last call since it depends on init...
        self.set_status(status, log_status=log_status, timestamp=self.start_time)

    def encoded(self):
        return {'session_id': self.session_id,
                'op_name': self.op_name,
                'status': self.status,
                'start_time': self.start_time,
                'end_time': self.end_time,
                'messages': self.messages}

    def set_status(self, status, timestamp=None, log_status=True):
        assert status in ['starting', 'running', 'stopping', 'done']
        self.status = status
        if timestamp is None:
            timestamp = time.time()
        if status == 'done':
            self.end_time = timestamp
        if log_status:
            self.add_message('Status is now "%s".' % status, timestamp=timestamp)

    def add_message(self, message, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        self.messages.append((timestamp, message))
        self.app.publish_status('Message', self)

    # Callable from task / process threads.

    def post_status(self, status):
        reactor.callFromThread(self.set_status, status)
        
    def post_message(self, message):
        reactor.callFromThread(self.add_message, message)
