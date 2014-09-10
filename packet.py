'''
packet -- Packet

Uses the general serializer interface to create network packets.
These packets MUST be read on boundaries, and never across them;
a transport like UDP, or TCP with length prefixes, should work
for these purposes.
'''

import serialize


class Packet(object):
	def __init__(self, cmd, **kwargs):
		self.cmd=cmd
		self.attrs=kwargs
	@classmethod
	def FromStr(cls, s):
		return cls(ord(s[0]), **serialize.Deserialize(s[1:]))
	@classmethod
	def Make(cls, obj):
		if isinstance(obj, cls):
			return obj
		return cls.FromStr(obj) #XXX Eww.
	def __getattr__(self, attr):
		if attr=='cmd':
			#logger.warning('Failed to find "cmd" on a Packet; assuming default')
			self.cmd=CMD.KEEPALIVE
			return self.cmd
		if attr=='attrs':
			#logger.warning('Failed to find "attrs" on a Packet; assuming default')
			self.attrs={}
			return self.attrs
		return self.attrs[attr]
	def __setattr__(self, attr, val):
		if attr in ('cmd', 'attrs'):
			object.__setattr__(self, attr, val)
		else:
			self.attrs[attr]=val
	def __delattr__(self, attr):
		del self.attrs[attr]
	def __str__(self):
		return chr(self.cmd)+serialize.Serialize(self.attrs)
	def __repr__(self):
		#return '<Packet cmd=%d %r>'%(self.cmd, self.attrs)
		return '<Packet cmd=%d %r>'%(self.cmd, self.attrs.keys())
	def Has(self, *attrs):
		for attr in attrs:
			if attr not in self.attrs:
				return False
		return True