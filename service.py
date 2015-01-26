'''
nom -- Network Object Mirroring
service -- Service

Implements the actual mirroring service.

This service necessarily runs in another thread, listening to and servicing
requests indefinitely; its existence permits the main thread to continue
doing whatever it wants to do while allowing other clients to access (and
mutate) these objects from other threads. Code written this way should be
thread safe, as it is entirely possible that a network request can mutate
a value unexpectedly.

If the main thread has no other task to do, it is safe to just .join() the
service, and the main thread will wait forever (until the process is killed,
or the program is terminated through other means, such as exit()). Assuming
no other server threads are running, this provides a safe interface to
code which may not be thread-safe.
'''

import threading
import Queue
import socket
import select
import traceback

import serialize
import packet
import proxy

class NOMError(Exception):
    pass

class LoggedSocket(object):
	def __init__(self, sock):
		self.sock=sock
	def recvfrom(self, sz):
		data, src=self.sock.recvfrom(sz)
		print src, '->', repr(packet.Packet.FromStr(data))
		return data, src
	def sendto(self, data, addr):
		print addr, '<-', repr(packet.Packet.FromStr(data))
		self.sock.sendto(data, addr)
	def __getattr__(self, attr):
		return getattr(self.sock, attr)

class Deferred(object):
	TIMEOUT=None
	CONDITION=threading.Condition()
	WAITING=set()
	@classmethod
	def SetTimeout(cls, tmout):
		cls.TIMEOUT=tmout
	def __init__(self, filt=None, onwait=None):
		self.filt=filt
		self.onwait=onwait
		self.queue=Queue.Queue()
	def Wait(self):
		with self.CONDITION:
			self.Go()
			while True:
				self.CONDITION.wait(self.TIMEOUT)
				catch, res = self.Process()
				if catch:
					return res
			
	def Go(self):
		with self.CONDITION:
			self.WAITING.add(self)
			if self.onwait:
				self.onwait()
	def Process(self):
		while not self.queue.empty():
			obj=self.queue.get()
			if self.filt and self.filt(obj):
				self.WAITING.discard(self)
				return (True, obj)
		return (False, None)
	def Accept(self, obj):
		self.queue.put(obj)
	@classmethod
	def Wake(cls):
		with cls.CONDITION:
			cls.CONDITION.notify_all()
	@classmethod
	def SendAll(cls, ev):
		for inst in cls.WAITING:
			inst.Accept(ev)
		cls.Wake()
		
class DeferredResult(Deferred):
	def __init__(self, srv, xid, onwait=None):
		Deferred.__init__(self, lambda obj, self=self: obj.xid == self.xid, onwait)
		self.srv=srv
		self.xid=xid
		self.result=None
		self.ready=False
	def GetResult(self):
		if not self.ready:
			raise RuntimeError('Value not available yet')
		if self.result.Has('error'):
			raise pkt.result.error
		else:
			return self.result.result
	def Wait(self):
		if not self.ready:
			#print id(self), 'Waiting on transaction', self.xid
			self.result=Deferred.Wait(self)
			#print id(self), 'Transaction complete:', self.xid
			try:
				del self.srv.outstanding[self.xid]
			except KeyError:
				pass
			self.ready=True
		return self.GetResult()
	def Accept(self, obj):
		if self.filt(obj):
			#print id(self), 'Accepted object'
			self.result=obj
			self.ready=True
		Deferred.Accept(self, obj)
		
class ObjectTranslator(object):
	__tag__=255
	def __init__(self, srv):
		self.srv=srv
	def Serialize(self, obj, fout):
		self.srv.omap[id(obj)]=obj
		serialize.LongSerializer.Serialize(id(obj), fout)
		serialize.SequenceSerializer.Serialize(self.srv.addr, fout)
	def Deserialize(self, fin):
		oid=serialize.LongSerializer.Deserialize(fin)
		addr=tuple(serialize.SequenceSerializer.Deserialize(fin))
		if addr==self.srv.addr:
			try:
				return self.srv.omap[oid]
			except KeyError:
				raise ValueError('Bad OID in serialized data')
		else:
			return proxy.Proxy(RemoteReference(self.srv, self.srv.GetClient(addr), oid))
		
class RemoteReference(object):
	def __init__(self, srv, cli, oid):
		self.srv=srv
		self.cli=cli
		self.oid=oid
		self.blocking=True
		self.pushdata={}
	def GetAttr(self, attr):
		if attr in self.pushdata:
			return self.pushdata[attr]
		if self.blocking:
			return self.srv.GetAttr(self.cli, self.oid, attr).Wait()
		return self.srv.GetAttr(self.cli, self.oid, attr)
	def SetAttr(self, attr, val):
		if self.blocking:
			self.srv.SetAttr(self.cli, self.oid, attr, val).Wait()
		else:
			self.srv.SetAttr(self.cli, self.oid, attr, val)
	def DelAttr(self, attr):
		if self.blocking:
			self.srv.DelAttr(self.cli, self.oid, attr).Wait()
		else:
			self.srv.DelAttr(self.cli, self.oid, attr)
	def GetItem(self, item):
		if self.blocking:
			return self.srv.GetItem(self.cli, self.oid, item).Wait()
		return self.srv.GetItem(self.cli, self.oid, item)
	def SetItem(self, item, val):
		if self.blocking:
			self.srv.SetItem(self.cli, self.oid, item, val).Wait()
		else:
			self.srv.SetItem(self.cli, self.oid, item, val)
	def DelItem(self, item):
		if self.blocking:
			self.srv.Delitem(self.cli, self.oid, item).Wait()
		else:
			self.srv.Delitem(self.cli, self.oid, item)
	def Len(self):
		if self.blocking:
			return self.srv.Len(self.cli, self.oid).Wait()
		return self.srv.Len(self.cli, self.oid)
	def Repr(self):
		if self.blocking:
			return self.srv.Repr(self.cli, self.oid).Wait()
		return self.srv.Repr(self.cli, self.oid)
	def Str(self):
		if self.blocking:
			return self.srv.Str(self.cli, self.oid).Wait()
		return self.srv.Str(self.cli, self.oid)
	def Call(self, *args, **kwargs):
		if self.blocking:
			return self.srv.Call(self.cli, self.oid, *args, **kwargs).Wait()
		return self.srv.Call(self.cli, self.oid, *args, **kwargs)
		
class CMD:
	SYNC=0
	DESYNC=1
	PULL=2
	RESOLVE=3
	LIST=4
	PUSH=5
CMD.NAMES=dict(zip(CMD.__dict__.values(), CMD.__dict__.keys()))
	
class Client(object):
	def __init__(self, addr, srv=None):
		self.addr=addr
		self.srv=srv
		#Authorizers may add more attributes here
	def List(self):
		return self.srv.List(self)
	def Resolve(self, name):
		return self.srv.Resolve(self, name)
		
class Authorizor(object):
	def CanClientSync(self, client):
		return True
	def CanClientAccess(self, client, obj, pkt):
		if pkt.Has('attr'):
			return not pkt.attr.startswith('_')
		return True
		
class Service(threading.Thread):
	BUFSIZE=65536
	XID=0
	@classmethod
	def NewXID(cls):
		cls.XID=(cls.XID+1)&0xffffffff
		return cls.XID-1
	def __init__(self, addr=('', 12074), auth=None):
		threading.Thread.__init__(self)
		self.daemon=True
		#self.sock=LoggedSocket(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
		self.sock=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.sock.bind(addr)
		self.addr=self.sock.getsockname()
		self.auth=auth or Authorizor()
		self.omap={} #id -> object tracked
		self.pubmap={} #public object name -> id
		self.outstanding={} #xid -> Deferred
		self.clients={} #addr -> Client
		serialize.SetSerializer(object, ObjectTranslator(self))
	def Connect(self, addr):
		#print 'Connecting to', addr
		if addr not in self.clients:
			cli=self.GetClient(addr)
			#print '(new client)'
			self.SendPacket(cli, _cmd=CMD.SYNC).Wait()
			return cli
		return self.clients[addr]
	def Disconnect(self, addr):
		cli=self.GetClient(addr)
		self.SendPacket(cli, _cmd=CMD.DESYNC)
	def Register(self, obj, name):
		self.omap[id(obj)]=obj
		self.pubmap[name]=id(obj)
	def Unregister(self, name):
		try:
			del self.pubmap[name]
		except KeyError:
			pass
	def Resolve(self, cli, name):
		return self.SendPacket(cli, _cmd=CMD.RESOLVE, name=name).Wait()
	def List(self, cli):
		return self.SendPacket(cli, _cmd=CMD.LIST).Wait()
	def GetClient(self, addr):
		try:
			return self.clients[addr]
		except KeyError:
			cli=Client(addr, self)
			self.clients[addr]=cli
			return cli
	def SendPacket(self, cli, **kwargs):
		xid=self.NewXID()
		if '_cmd' in kwargs:
			cmd=kwargs['_cmd']
			del kwargs['_cmd']
		else:
			cmd=CMD.PULL
		act=DeferredResult(self, xid, lambda self=self, xid=xid, cmd=cmd, kwargs=kwargs, cli=cli: self.sock.sendto(str(packet.Packet(cmd, xid=xid, **kwargs)), cli.addr))
		self.outstanding[xid]=act
		return act
	def GetAttr(self, cli, oid, attr):
		return self.SendPacket(cli, op='GetAttr', oid=oid, attr=attr)
	def SetAttr(self, cli, oid, attr, val):
		return self.SendPacket(cli, op='SetAttr', oid=oid, attr=attr, val=val)
	def DelAttr(self, cli, oid, attr):
		return self.SendPacket(cli, op='DelAttr', oid=oid, attr=attr)
	def GetItem(self, cli, oid, item):
		return self.SendPacket(cli, op='GetItem', oid=oid, item=item)
	def SetItem(self, cli, oid, item, val):
		return self.SendPacket(cli, op='SetItem', oid=oid, item=item, val=val)
	def DelItem(self, cli, oid, item):
		return self.SendPacket(cli, op='DelItem', oid=oid, item=item)
	def Len(self, cli, oid):
		return self.SendPacket(cli, op='Len', oid=oid)
	def Repr(self, cli, oid):
		return self.SendPacket(cli, op='Repr', oid=oid)
	def Str(self, cli, oid):
		return self.SendPacket(cli, op='Str', oid=oid)
	def Call(self, cli, oid, *args, **kwargs):
		return self.SendPacket(cli, op='Call', oid=oid, args=args, kwargs=kwargs)
	def run(self):
		while True:
			data, src=self.sock.recvfrom(self.BUFSIZE)
			cli=self.GetClient(src)
			try:
				pkt=packet.Packet.FromStr(data)
			except Exception:
				print 'Exception encountered parsing packet:'
				traceback.print_exc()
				print 'Continuing...'
				continue
			if pkt.Has('result') or pkt.Has('error'):
				Deferred.SendAll(pkt)
			else:
				getattr(self, 'cmd_'+CMD.NAMES[pkt.cmd], self.cmd_Unknown)(pkt, cli)
	def cmd_SYNC(self, pkt, cli):
		if self.auth.CanClientSync(cli):
			self.sock.sendto(str(packet.Packet(CMD.SYNC, xid=pkt.xid, result=True)), cli.addr)
		else:
			self.sock.sendto(str(packet.Packet(CMD.SYNC, xid=pkt.xid, result=False)), cli.addr)
			del self.clients[cli.addr]
	def cmd_DESYNC(self, pkt, cli):
		del self.clients[cli.addr]
	def cmd_PULL(self, pkt, cli):
		threading.Thread(target=self.cmd_PULL_inner, args=(pkt, cli)).start()
	def cmd_PULL_inner(self, pkt, cli):
		try:
			obj=self.omap[pkt.oid]
			if not self.auth.CanClientAccess(cli, obj, pkt):
				raise RuntimeError('Access denied')
			pkt.result=getattr(self, 'pull_'+pkt.op, self.pull_Unknown)(proxy.ReverseProxy(obj), pkt, cli)
			self.sock.sendto(str(pkt), cli.addr)
		except Exception, e:
			pkt.error=e
			self.sock.sendto(str(pkt), cli.addr)
	def cmd_RESOLVE(self, pkt, cli):
		if pkt.name in self.pubmap:
			pkt.result=self.omap[self.pubmap[pkt.name]]
		else:
			pkt.error=NameError('No such name')
		self.sock.sendto(str(pkt), cli.addr)
	def cmd_LIST(self, pkt, cli):
		pkt.result=self.pubmap.keys()
		self.sock.sendto(str(pkt), cli.addr)
	def cmd_Unknown(self, pkt, cli):
		print 'Warning: Bad packet command:', repr(pkt)
		pkt.error=NameError('Unknown command')
		self.sock.sendto(str(pkt), cli.addr)
	def pull_GetAttr(self, obj, pkt, cli):
		return obj.GetAttr(pkt.attr)
	def pull_SetAttr(self, obj, pkt, cli):
		obj.SetAttr(pkt.attr, pkt.val)
	def pull_DelAttr(self, obj, pkt, cli):
		obj.DelAttr(pkt.attr)
	def pull_GetItem(self, obj, pkt, cli):
		return obj.GetItem(pkt.item)
	def pull_SetItem(self, obj, pkt, cli):
		obj.SetItem(pkt.item, pkt.val)
	def pull_DelItem(self, obj, pkt, cli):
		obj.DelItem(pkt.item)
	def pull_Len(self, obj, pkt, cli):
		return obj.Len()
	def pull_Repr(self, obj, pkt, cli):
		return obj.Repr()
	def pull_Str(self, obj, pkt, cli):
		return obj.Str()
	def pull_Call(self, obj, pkt, cli):
		return obj.Call(*pkt.args, **pkt.kwargs)
	def pull_Unknown(self, obj, pkt, cli):
		print 'Warning: Bad packet pull:', repr(pkt)
		pkt.error=NameError('Unknown pull')