#!/usr/bin/env python

# Prerequisites:
#   Python 3 (https://www.python.org/downloads/)
#   Python for Windows (http://sourceforge.net/projects/pywin32/)
#   Paramiko (https://github.com/paramiko/paramiko)

# Usage:
#   $ ssh-keygen -N '' -f ssh_host_rsa_key
#   > python pyrexec.py

import sys
import os.path
import time
import socket
import logging
import paramiko
import win32con
import win32api
import win32gui
import win32gui_struct
import win32clipboard
from win32com.shell import shell, shellcon
from io import StringIO
from subprocess import Popen, PIPE, STDOUT, DEVNULL
from threading import Thread
from paramiko.py3compat import decodebytes


def msgbox(text, caption='Error'):
    win32gui.MessageBox(None, text, caption,
                        (win32con.MB_OK | win32con.MB_ERROR))
    return

def getpath(csidl):
    return shell.SHGetSpecialFolderPath(None, csidl, 0)

frozen = getattr(sys, 'frozen', False)
if frozen:
    APPDATA = os.path.join(getpath(shellcon.CSIDL_APPDATA), 'PyRexecd')
    DATADIR = os.path.dirname(sys.executable)
    error = msgbox
else:
    APPDATA = '.'
    DATADIR = os.path.dirname(__file__)
    error = print


##  SysTrayApp
##
class SysTrayApp(object):

    WM_NOTIFY = None
    WNDCLASS = None
    CLASS_ATOM = None
    _instance = None

    @classmethod
    def initialize(klass):
        WM_RESTART = win32gui.RegisterWindowMessage('TaskbarCreated')
        klass.WM_NOTIFY = win32con.WM_USER+1
        klass.WNDCLASS = win32gui.WNDCLASS()
        klass.WNDCLASS.hInstance = win32gui.GetModuleHandle(None)
        klass.WNDCLASS.lpszClassName = 'Py_'+klass.__name__
        klass.WNDCLASS.style = win32con.CS_VREDRAW | win32con.CS_HREDRAW;
        klass.WNDCLASS.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
        klass.WNDCLASS.hIcon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        klass.WNDCLASS.hbrBackground = win32con.COLOR_WINDOW
        klass.WNDCLASS.lpfnWndProc = {
            WM_RESTART: klass._restart,
            klass.WM_NOTIFY: klass._notify,
            win32con.WM_CLOSE: klass._close,
            win32con.WM_DESTROY: klass._destroy,
            win32con.WM_COMMAND: klass._command,
            }
        klass.CLASS_ATOM = win32gui.RegisterClass(klass.WNDCLASS)
        klass._instance = {}
        return

    @classmethod
    def _create(klass, hwnd, instance):
        klass._instance[hwnd] = instance
        win32gui.Shell_NotifyIcon(
            win32gui.NIM_ADD,
            (hwnd, 0,
             (win32gui.NIF_ICON | win32gui.NIF_MESSAGE),
             klass.WM_NOTIFY, klass.WNDCLASS.hIcon))
        instance.open()
        return

    @classmethod
    def _restart(klass, hwnd, msg, wparam, lparam):
        win32gui.Shell_NotifyIcon(
            win32gui.NIM_ADD,
            (hwnd, 0,
             (win32gui.NIF_ICON | win32gui.NIF_MESSAGE),
             klass.WM_NOTIFY, klass.WNDCLASS.hIcon))
        self = klass._instance[hwnd]
        self.open()
        return
        
    @classmethod
    def _notify(klass, hwnd, msg, wparam, lparam):
        self = klass._instance[hwnd]
        if lparam == win32con.WM_LBUTTONDBLCLK:
            menu = self.get_popup()
            wid = win32gui.GetMenuDefaultItem(menu, 0, 0)
            win32gui.PostMessage(hwnd, win32con.WM_COMMAND, wid, 0)
        elif lparam == win32con.WM_RBUTTONUP:
            menu = self.get_popup()
            pos = win32gui.GetCursorPos()
            win32gui.SetForegroundWindow(hwnd)
            win32gui.TrackPopupMenu(
                menu, win32con.TPM_LEFTALIGN,
                pos[0], pos[1], 0, hwnd, None)
            win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
        elif lparam == win32con.WM_LBUTTONUP:
            pass
        return True

    @classmethod
    def _close(klass, hwnd, msg, wparam, lparam):
        win32gui.DestroyWindow(hwnd)
        return

    @classmethod
    def _destroy(klass, hwnd, msg, wparam, lparam):
        del klass._instance[hwnd]
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (hwnd, 0))
        win32gui.PostQuitMessage(0)
        return

    @classmethod
    def _command(klass, hwnd, msg, wparam, lparam):
        wid = win32gui.LOWORD(wparam)
        self = klass._instance[hwnd]
        self.choose(wid)
        return

    def __init__(self, name):
        self.logger = logging.getLogger(name)
        self.hwnd = win32gui.CreateWindow(
            self.CLASS_ATOM, name,
            (win32con.WS_OVERLAPPED | win32con.WS_SYSMENU),
            0, 0, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT, 0, 0,
            self.WNDCLASS.hInstance, None)
        self._create(self.hwnd, self)
        self.logger.info('create: name=%r' % name)
        return

    def open(self):
        self.logger.info('open')
        win32gui.UpdateWindow(self.hwnd)
        return

    def run(self):
        self.logger.info('run')
        win32gui.PumpMessages()
        return

    def idle(self):
        return not win32gui.PumpWaitingMessages()

    def close(self):
        self.logger.info('close')
        win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
        return

    def set_icon(self, icon):
        self.logger.info('set_icon: %r' % icon)
        win32gui.Shell_NotifyIcon(
            win32gui.NIM_MODIFY,
            (self.hwnd, 0, win32gui.NIF_ICON,
             0, icon))
        return

    def set_text(self, text):
        self.logger.info('set_text: %r' % text)
        win32gui.Shell_NotifyIcon(
            win32gui.NIM_MODIFY,
            (self.hwnd, 0, win32gui.NIF_TIP,
             0, 0, text))
        return
        
    def show_balloon(self, title, text, timeout=1):
        self.logger.info('show_balloon: %r, %r' % (title, text))
        win32gui.Shell_NotifyIcon(
            win32gui.NIM_MODIFY,
            (self.hwnd, 0, win32gui.NIF_INFO,
             0, 0, '', text, timeout, title, win32gui.NIIF_INFO))
        return

    IDI_QUIT = 100
    
    def get_popup(self):
        menu = win32gui.CreatePopupMenu()
        (item, _) = win32gui_struct.PackMENUITEMINFO(text=u'Quit', wID=self.IDI_QUIT)
        win32gui.InsertMenuItem(menu, 0, 1, item)
        win32gui.SetMenuDefaultItem(menu, 0, self.IDI_QUIT)
        (item, _) = win32gui_struct.PackMENUITEMINFO(text=u'Test', wID=123)
        win32gui.InsertMenuItem(menu, 0, 1, item)
        return menu

    def choose(self, wid):
        self.logger.info('choose: wid=%r' % wid)
        if wid == self.IDI_QUIT:
            self.close()
        return


##  PyRexecTrayApp
##
class PyRexecTrayApp(SysTrayApp):

    @classmethod
    def initialize(klass, basedir='icons'):
        SysTrayApp.initialize()
        klass.ICON_IDLE = win32gui.LoadImage(
            0, os.path.join(basedir, 'PyRexec.ico'),
            win32con.IMAGE_ICON,
            win32con.LR_DEFAULTSIZE, win32con.LR_DEFAULTSIZE,
            win32con.LR_LOADFROMFILE)
        klass.ICON_BUSY = win32gui.LoadImage(
            0, os.path.join(basedir, 'PyRexecConnected.ico'),
            win32con.IMAGE_ICON,
            win32con.LR_DEFAULTSIZE, win32con.LR_DEFAULTSIZE,
            win32con.LR_LOADFROMFILE)
        return

    def __init__(self, name='PyRexec'):
        SysTrayApp.__init__(self, name)
        return

    def set_busy(self, busy):
        if busy:
            self.set_icon(self.ICON_BUSY)
        else:
            self.set_icon(self.ICON_IDLE)
        return

    def get_popup(self):
        menu = win32gui.CreatePopupMenu()
        (item, _) = win32gui_struct.PackMENUITEMINFO(text=u'Quit', wID=self.IDI_QUIT)
        win32gui.InsertMenuItem(menu, 0, 1, item)
        win32gui.SetMenuDefaultItem(menu, 0, self.IDI_QUIT)
        return menu

    def choose(self, wid):
        if wid == self.IDI_QUIT:
            self.close()
        return


##  PyRexecServer
##
class PyRexecServer(paramiko.ServerInterface):
    
    def __init__(self, username, pubkeys):
        self.username = username
        self.pubkeys = pubkeys
        self.command = None
        self.ready = False
        return

    def get_allowed_auths(self, username):
        if username == self.username:
            return 'publickey'
        return ''
    
    def check_auth_publickey(self, username, key):
        logging.debug('check_auth_publickey: %r' % username)
        if username == self.username:
            for k in self.pubkeys:
                if k == key: return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED
    
    def check_channel_request(self, kind, chanid):
        logging.debug('check_channel_request: %r' % kind)
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
    
    def check_channel_shell_request(self, channel):
        logging.debug('check_channel_shell_request')
        self.ready = True
        return True

    def check_channel_exec_request(self, channel, command):
        logging.debug('check_channel_exec_request: %r' % command)
        try:
            self.command = command.decode('utf-8')
            self.ready = True
        except UnicodeError:
            return False
        return True


##  PyRexecSession
##
class PyRexecSession:

    def __init__(self, app, name, chan, homedir, cmdexe, server, timeout=10):
        self.logger = logging.getLogger(name)
        self.app = app
        self.name = name
        self.homedir = homedir
        self.cmdexe = cmdexe
        self.server = server
        self.bufsize = 512
        self._timeout = time.time()+timeout
        self._chan = chan
        self._tasks = None
        self._events = []
        return

    def __repr__(self):
        return ('<%s: %s>' % (self.__class__.__name__, self.name))

    def _add_task(self, task):
        self._tasks.append(task)
        task.start()
        return

    def _add_event(self, ev):
        self._events.append(ev)
        return

    def get_name(self):
        return self.name

    def get_event(self):
        if not self._events: return None
        return self._events.pop(0)
    
    def idle(self):
        if self._tasks is None:
            if self.server.ready:
                self.open()
            elif self._timeout < time.time():
                self._add_event('timeout')
        elif self._tasks:
            for task in self._tasks:
                if not task.isAlive():
                    self._add_event('closing')
                    break
        else:
            self._add_event('closing')
        return
    
    def open(self):
        self.logger.info('open: %r' % self._chan)
        self._chan.settimeout(0.05)
        self._add_event('open')
        self._tasks = []
        self._proc = None
        self.start_tasks(self._chan, self.server.command)
        return
    
    def close(self, status=0):
        self.logger.info('close: %r, status=%r' % (self._chan, status))
        self._tasks = []
        if self._proc is None:
            status = 0
        else:
            self._proc.terminate()
            status = self._proc.wait()
        self._chan.send_exit_status(status)
        self._chan.close()
        self._add_event('closed')
        return

    def start_tasks(self, chan, command):
        self.logger.info('start: command: %r' % command)
        try:
            if command is not None and command.startswith('@'):
                args = self.cmdexe+['/C', command[1:]]
                Popen(
                    args, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL,
                    cwd=self.homedir)
            elif command == 'clipget':
                win32clipboard.OpenClipboard(self.app.hwnd)
                text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
                self.logger.debug('text=%r' % text)
                chan.send(text.encode('utf-8'))
            elif command == 'clipset':
                self._add_task(self.ClipSetter(self, chan))
            else:
                if command is None:
                    args = self.cmdexe
                else:
                    args = self.cmdexe+['/C', command]
                self._proc = Popen(
                    args, stdin=PIPE, stdout=PIPE, stderr=STDOUT,
                    cwd=self.homedir, creationflags=win32con.CREATE_NO_WINDOW)
                self._add_task(self.ChanForwarder(self, chan, self._proc.stdin))
                self._add_task(self.PipeForwarder(self, self._proc.stdout, chan))
        except OSError as e:
            self.logger.error('cannot start: %r' % e)
        return

    class ChanForwarder(Thread):
        def __init__(self, session, chan, pipe):
            Thread.__init__(self)
            self.session = session
            self.chan = chan
            self.pipe = pipe
            return
        def run(self):
            while 1:
                try:
                    data = self.chan.recv(self.session.bufsize)
                    if not data: break
                    self.pipe.write(data)
                    self.pipe.flush()
                except socket.timeout:
                    continue
                except (IOError, socket.error) as e:
                    self.session.logger.error('chan error: %r' % e)
                    break
            self.session.logger.debug('chan end')
            self.pipe.close()
            return
        
    class PipeForwarder(Thread):
        def __init__(self, session, pipe, chan):
            Thread.__init__(self)
            self.session = session
            self.pipe = pipe
            self.chan = chan
            return
        def run(self):
            while 1:
                try:
                    data = self.pipe.read(1)
                    if not data: break
                    self.chan.send(data)
                except socket.timeout:
                    continue
                except (IOError, socket.error) as e:
                    self.session.logger.error('pipe error: %r' % e)
                    break
            self.session.logger.debug('pipe end')
            self.pipe.close()
            return

    class ClipSetter(Thread):
        def __init__(self, session, chan):
            Thread.__init__(self)
            self.session = session
            self.chan = chan
            self._data = b''
            return
        def run(self):
            while 1:
                try:
                    data = self.chan.recv(self.session.bufsize)
                    if not data: break
                    self._data += data
                except socket.timeout:
                    continue
                except (IOError, socket.error) as e:
                    self.session.logger.error('chan error: %r' % e)
                    break
            self.session.logger.debug('clip data=%r' % self._data)
            try:
                text = self._data.decode('utf-8')
                win32clipboard.OpenClipboard(self.session.app.hwnd)
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text)
                win32clipboard.CloseClipboard()
            except UnicodeError:
                pass
            return
        
# get_host_key
def get_host_key(path):
    if path.endswith('rsa_key'):
        f = paramiko.RSAKey
    elif path.endswith('dsa_key'):
        f = paramiko.DSSKey
    elif path.endswith('ecdsa_key'):
        f = paramiko.ECDSAKay
    else:
        raise ValueError(path)
    return f(filename=path)

# get_authorized_keys
def get_authorized_keys(path):
    keys = []
    with open(path) as fp:
        for line in fp:
            (t,_,data) = line.partition(' ')
            if t == 'ssh-rsa':
                f = paramiko.RSAKey
            elif t == 'ssh-dss':
                f = paramiko.DSSKey
            elif t.startswith('ecdsa-'):
                f = paramiko.ECDSAKey
            else:
                continue
            data = decodebytes(data.encode('utf-8'))
            keys.append(f(data=data))
    return keys

# run_server
def run_server(app, hostkeys, username, pubkeys, homedir, cmdexe,
               addr='127.0.0.1', port=2200):
    logging.info('Listening: %s:%s...' % (addr, port))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        reuseaddr = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, reuseaddr | 1)
    except socket.error:
        pass
    sock.bind((addr, port))
    sock.listen(5)
    sock.settimeout(0.05)
    def update_text(n):
        s = u'Listening: %s:%r...' % (addr, port)
        if n:
            s += u'\n(Clients: %d)' % n
        app.set_text(s)
        return
    update_text(0)
    app.set_busy(False)
    sessions = []
    while app.idle():
        for session in sessions[:]:
            session.idle()
            ev = session.get_event()
            if ev == 'open':
                update_text(len(sessions))
                app.show_balloon(u'Connected', session.get_name())
                app.set_busy(True)
            elif ev == 'closing':
                session.close()
                sessions.remove(session)
                update_text(len(sessions))
                app.show_balloon(u'Disconnected', session.get_name())
                if not sessions:
                    app.set_busy(False)
            elif ev == 'timeout':
                sessions.remove(session)
        try:
            (conn, peer) = sock.accept()
        except socket.timeout:
            continue
        conn.settimeout(0.05)
        logging.info('Connected: addr=%r, port=%r' % peer)
        t = paramiko.Transport(conn)
        t.load_server_moduli()
        #t.set_subsystem_handler('sftp', paramiko.SFTPServer)
        for k in hostkeys:
            t.add_server_key(k)
        name = 'Session-%s-%s' % peer
        server = PyRexecServer(username, pubkeys)
        try:
            t.start_server(server=server)
            chan = t.accept(10)
            if chan is not None:
                session = PyRexecSession(app, name, chan, homedir, cmdexe, server)
                sessions.append(session)
            else:
                logging.error('Timeout')
                t.close()
        except (EOFError, OSError) as e:
            logging.error('Error: %r' % e)
            t.close()
    while sessions:
        session = sessions.pop()
        session.close()
    return

# main
def main(argv):
    import getopt
    def usage():
        error('Usage: %s [-d] [-l logfile] [-L addr] [-p port]'
              ' [-u username] [-a authkeys] [-h homedir] [-c cmdexe]' % argv[0])
        return 100
    try:
        (opts, args) = getopt.getopt(argv[1:], 'dl:L:p:u:a:h:c:')
    except getopt.GetoptError:
        return usage()
    loglevel = logging.INFO
    logfile = None
    if frozen:
        logfile = os.path.join(APPDATA, 'pyrexecd.log')
    port = 2200
    addr = '0.0.0.0'
    username = win32api.GetUserName()
    homedir = getpath(shellcon.CSIDL_PROFILE)
    authkeys = []
    cmdexe = ['cmd','/Q']
    for (k, v) in opts:
        if k == '-d': loglevel = logging.DEBUG
        elif k == '-l': logfile = v
        elif k == '-L': addr = v
        elif k == '-p': port = int(v)
        elif k == '-u': username = v
        elif k == '-a': authkeys.append(v)
        elif k == '-h': homedir = v
        elif k == '-c': cmdexe = v
    if not authkeys:
        authkeys = [os.path.join(APPDATA, 'authorized_keys')]
    if not args:
        args = [os.path.join(APPDATA, 'ssh_host_rsa_key'),
                os.path.join(APPDATA, 'ssh_host_dsa_key')]
    pubkeys = []
    for path in authkeys:
        if os.path.isfile(path):
            pubkeys.extend(get_authorized_keys(path))
    hostkeys = []
    for path in args:
        if os.path.isfile(path):
            hostkeys.append(get_host_key(path))
    if not hostkeys:
        error('No hostkey is found!')
        return 111
    logging.basicConfig(level=loglevel, filename=logfile, filemode='a')
    logging.info('Hostkeys: %d' % len(hostkeys))
    logging.info('Username: %r (pubkeys:%d)' % (username, len(pubkeys)))
    logging.info('Homedir: %r' % homedir)
    logging.info('Cmd.exe: %r' % cmdexe)
    PyRexecTrayApp.initialize(basedir=os.path.join(DATADIR, 'icons'))
    app = PyRexecTrayApp()
    run_server(app, hostkeys, username, pubkeys, homedir, cmdexe,
               addr=addr, port=port)
    return
if __name__ == '__main__': sys.exit(main(sys.argv))
