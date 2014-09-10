Network Object Mirroring
========================

Network Object Mirroring (or NOM) is a Python library that provides
*transparent networking* for Python objects. It has no dependencies
other than the Python standard libraries and an operating system/environment
that supports networking; just clone it and go!

Basic Usage
-----------

The library is intentionally very easy to use; you can view the local
files `test.py` and `testcli.py` to see a trivial setup. In general,
the usage pattern is as follows.

Both the server and the client are *peers*, which mean they initialize
themselves in much the same way:
	
	import nom.service    #Or just import service
	
	srv=nom.service.Service((HOST, PORT))
	srv.start()
	
`Service` objects are `threading.Thread` objects, so you need to `.start()`
them to do anything useful.

At this point, the server simply needs to register objects to make available:
	
	srv.Register(my_object, 'Object')
	srv.Register(sys, 'LocalSys')
	
Then connect the client to the server:
	
	cli=srv.Connect((SERVER_HOST, SERVER_PORT))
	
You can then query the server for the objects it serves (more specifically,
the names it serves), and ask it for local references:
	
	cli.List() # == ['Object', 'LocalSys']
	my_object = cli.Resolve('Object')
	
That's it! You can start using `my_object` from either interpreter, and NOM
will translate all the required calls into network traffic. Attributes,
indexing, length, string, representation, and calling are all presently
supported, and more can easily (and will) be added.

Advanced Usage
--------------

NOM can support callbacks and multiple client usage scenarios; for example,
in the setup above, the client can easily assign a local function to the
server as such:
	
	my_object.some_callback = lambda foo: sys.stdout.write(repr(foo)+'\n')
	
The `my_object.some_callback` callable can be called from the server, or
from *any* other connected client, and the parameter with which it is called
will be printed out on the stdout stream *of the terminal that assigned it*.
This is an important note: while NOM does its best to make the Python
environment transparent, it has no ability to integrate local resources
like memory or files transparently. However, it is relatively trivial to
expose the required Python machinery to the network to provide remote access,
but this comes with caveats--in particular, locally stored files will always
remain locally stored, and each client that needs such a resource will need
to find a way to locate that resource.

This brings another important topic: security. NOM provides an `Authenticator`
object interface that may be used by any Service; this object screens all
requests for client synchronization, as well as all object accesses (read,
write, and delete). This central interface should, in theory, make it easy
for other frameworks to integrate their own security policies into the
objects themselves, while still providing a comprehensive point-of-entry
for all remote access. Care should be exercised with any service exposed
to an untrusted network; as Python's rexec module admits, Python's own
introspection facilities are quite powerful, and it is possible to gain
access to powerful objects like `sys` or `open` in interesting ways.

An `Authenticator` may be supplied as the second argument to a `Service`,
or it may be set later as the `.auth` attribute. The default `Authenticator`
accepts all clients, and denies access only to attributes starting with
an underscore.

Network Protocol
----------------

NOM uses UDP as a transport protocol, making use of transactions and
multiple threads to guarantee concurrency. The actual object protocol
is a fairly efficient binary protocol defined in `serialize.py`, with
an additional encoder that allows NOM to encode arbitrary object
references that aren't otherwise references. While serialize has
comprehensive support for most built-in Python types, including
numerics, strings (including unicode), sequences, and maps, it
**cannot** handle circular data structures composed from these
sequences and maps.

Integrating `pickle` support would not be difficult, and may be done
eventually if support for these structures is needed. Otherwise, an
easy way to support circular structures is to wrap them in thin
classes that will be pushed over the network as references instead of
entire objects.