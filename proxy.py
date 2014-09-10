'''
nom -- Network Object Mirroring
proxy -- Proxies

Proxies are very simple objects that convert special Python object calls
(like __getattr__, __setattr__, __call__, etc.) to a strictly defined
interface (GetAttr, SetAttr, Call, etc.), and back again as needed.

In doing so, this allows an arbitrary set of intermediate transformations
of these calls between a proxy and reverse proxy, including the NOM-
fundamental transformation of mapping these to object calls.
'''

class Proxy(object):
	def __init__(self, obj):
		self._obj=obj
	def __getattr__(self, attr):
		if attr=='_obj':
			print 'Warning: Failed to find obj in proxy; this will probably fail.'
			self._obj=None
			return self._obj
		return self._obj.GetAttr(attr)
	def __setattr__(self, attr, val):
		if attr=='_obj':
			object.__setattr__(self, attr, val)
		else:
			self._obj.SetAttr(attr, val)
	def __delattr__(self, attr):
		self._obj.DelAttr(attr)
	def __getitem__(self, item):
		return self._obj.GetItem(item)
	def __setitem__(self, item, val):
		self._obj.SetItem(item, val)
	def __delitem__(self, item):
		self._obj.DelItem(item)
	def __len__(self):
		return self._obj.Len()
	def __repr__(self):
		return self._obj.Repr()
	def __str__(self):
		return self._obj.Str()
	def __call__(self, *args, **kwargs):
		return self._obj.Call(*args, **kwargs)
	
class ReverseProxy(object):
	def __init__(self, obj):
		self._obj=obj
	def GetAttr(self, attr):
		return getattr(self._obj, attr)
	def SetAttr(self, attr, val):
		setattr(self._obj, attr, val)
	def DelAttr(self, attr):
		delattr(self._obj, attr)
	def GetItem(self, item):
		return self._obj[item]
	def SetItem(self, item, val):
		self._obj[item]=val
	def DelItem(self, item):
		del self._obj[item]
	def Len(self):
		return len(self._obj)
	def Repr(self):
		return repr(self._obj)
	def Str(self):
		return str(self._obj)
	def Call(self, *args, **kwargs):
		return self._obj(*args, **kwargs)