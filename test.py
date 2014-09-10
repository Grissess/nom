import service
srv=service.Service(('', 12074))

class X(object):
	def a(self):
		return 1
	def b(self):
		return self
	def c(self):
		return self.d()
	
x=X()
srv.Register(x, 'X')

srv.start()