import service
srv=service.Service(('', 12075))
srv.start()
cli=srv.Connect(('127.0.0.1', 12074))
rx=srv.Resolve(cli, 'X')