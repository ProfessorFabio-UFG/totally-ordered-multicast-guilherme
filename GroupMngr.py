from socket import socket, AF_INET, SOCK_STREAM
import pickle
from constMP import GROUPMNGR_TCP_PORT

port = GROUPMNGR_TCP_PORT
membership = []

def serverLoop():
  """
  Loop principal do servidor de gerenciamento de grupo.
  Responsável por receber as mensagens de registro de processos e manter o registro.
  """
  serverSock = socket(AF_INET, SOCK_STREAM) # Cria um socket para o servidor
  serverSock.bind(('0.0.0.0', port)) # Associa o socket ao endereço e porta
  serverSock.listen(6) # Aguarda até 6 conexões
  while(1):
    # Aguarda a conexão de um processo
    (conn, addr) = serverSock.accept()
    msgPack = conn.recv(2048) # Recebe a mensagem do processo de até 2048 bytes
    req = pickle.loads(msgPack) # Deserializa a mensagem

    # Se a operação for de registro, adiciona o processo à lista de membros
    if req["op"] == "register":
      membership.append((req["ipaddr"],req["port"]))
      print ('Registered peer: ', req)
      
    # Se a operação for de listagem, envia a lista de membros para o processo
    # que solicitou
    elif req["op"] == "list":
      list = []
      for m in membership:
        list.append(m[0])
      print ('List of peers sent to server: ', list)
      conn.send(pickle.dumps(list))
    else:
      pass # fix (send back an answer in case of unknown op

  conn.close()

serverLoop()
