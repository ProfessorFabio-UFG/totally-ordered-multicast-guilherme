from socket import *
from constMP import *
import threading
import random
import time
import pickle
from requests import get
from lamport_clock import LamportClock, Message, MessageQueue

# Counter to make sure we have received handshakes from all other processes
handShakeCount = 0

PEERS = []

# Relógio de Lamport e fila de mensagens para entrega ordenada
lamport_clock = LamportClock()
message_queue = None  # Will be initialized after we know N

# Message types
MSG_DATA = "DATA"
MSG_ACK = "ACK"

# UDP sockets to send and receive data messages:
# Create send socket
sendSocket = socket(AF_INET, SOCK_DGRAM)
#Create and bind receive socket
recvSocket = socket(AF_INET, SOCK_DGRAM)
recvSocket.bind(('0.0.0.0', PEER_UDP_PORT))

# TCP socket to receive start signal from the comparison server:
serverSock = socket(AF_INET, SOCK_STREAM)
serverSock.bind(('0.0.0.0', PEER_TCP_PORT))
serverSock.listen(1)


def get_public_ip():
  """
  Obtém o endereço IP público do processo.
  """
  ipAddr = get('https://api.ipify.org').content.decode('utf8')
  print('My public IP address is: {}'.format(ipAddr))
  return ipAddr

def registerWithGroupManager():
  """
  Registra este processo com o grupo de gerenciamento.
  O grupo de gerenciamento é responsável por manter o registro de todos os processos
  e fornecer informações sobre os outros processos.
  """
  # Conectando ao grupo de gerenciamento
  clientSock = socket(AF_INET, SOCK_STREAM)
  print ('Connecting to group manager: ', (GROUPMNGR_ADDR,GROUPMNGR_TCP_PORT))
  clientSock.connect((GROUPMNGR_ADDR,GROUPMNGR_TCP_PORT))

  # Se registrando com o grupo de gerenciamento
  ipAddr = get_public_ip()
  req = {"op":"register", "ipaddr":ipAddr, "port":PEER_UDP_PORT}
  msg = pickle.dumps(req)
  print ('Registering with group manager: ', req)
  clientSock.send(msg)
  clientSock.close()

def getListOfPeers():
  """
  Obtém a lista de processos participantes.
  O grupo de gerenciamento é responsável por manter o registro de todos os processos
  e fornecer informações sobre os outros processos.
  """
  clientSock = socket(AF_INET, SOCK_STREAM)
  print ('Connecting to group manager: ', (GROUPMNGR_ADDR,GROUPMNGR_TCP_PORT))
  clientSock.connect((GROUPMNGR_ADDR,GROUPMNGR_TCP_PORT))
  req = {"op":"list"}
  msg = pickle.dumps(req)
  print ('Getting list of peers from group manager: ', req)
  clientSock.send(msg)
  msg = clientSock.recv(2048)
  PEERS = pickle.loads(msg)
  print ('Got list of peers: ', PEERS)
  clientSock.close()
  return PEERS

class MsgHandler(threading.Thread):
  """
  Thread para receber as mensagens dos outros processos.
  Responsável por receber as mensagens dos outros processos e armazená-las em uma lista.
  E também por enviar as mensagens para o servidor de comparação.
  """
  def __init__(self, sock):
    threading.Thread.__init__(self)
    self.sock = sock
    self.logList = []

  def run(self):
    print('Handler is ready. Waiting for the handshakes...')
    
    global handShakeCount
    global message_queue
    
    # Wait until handshakes are received from all other processes
    while handShakeCount < N:
      msgPack = self.sock.recv(1024)
      msg = pickle.loads(msgPack)
      if msg[0] == 'READY':
        handShakeCount = handShakeCount + 1
        print('--- Handshake received: ', msg[1])

    print('Secondary Thread: Received all handshakes. Entering the loop to receive messages.')

    # Initialize message queue now that we know N
    message_queue = MessageQueue(N)

    stopCount=0 
    while True:                
      msgPack = self.sock.recv(1024)   # receive data from client
      msg = pickle.loads(msgPack)
      if msg[0] == -1:   # count the 'stop' messages from the other processes
        stopCount = stopCount + 1
        if stopCount == N:
          break  # stop loop when all other processes have finished
      else:
        msg_type = msg[0]
        if msg_type == MSG_DATA:
          # Handle data message
          sender_id, msg_content, timestamp = msg[1:]
          lamport_clock.update(timestamp)
          
          # Create Message object and add to queue
          message = Message(sender_id, msg_content, timestamp)
          message_queue.add_message(message)
          
          # Send acknowledgment to all peers (including ourselves)
          ack_msg = (MSG_ACK, sender_id, msg_content, timestamp, myself)
          ack_pack = pickle.dumps(ack_msg)
          
          # Send to all peers
          for addrToSend in PEERS:
            sendSocket.sendto(ack_pack, (addrToSend, PEER_UDP_PORT))
          
          # Also acknowledge to ourselves
          message_queue.add_acknowledgment(timestamp, sender_id, msg_content, myself)
            
        elif msg_type == MSG_ACK:
          # Handle acknowledgment
          sender_id, msg_content, timestamp, from_process = msg[1:]
          message_queue.add_acknowledgment(timestamp, sender_id, msg_content, from_process)
        
        # Process deliverable messages
        deliverable = message_queue.get_deliverable_messages()
        for msg in deliverable:
          print(f'Delivered message {msg.msg_content} from process {msg.sender_id} with timestamp {msg.timestamp}')
          self.logList.append((msg.sender_id, msg.msg_content, msg.timestamp))
        
    # Write log file with ordered messages
    logFile = open('logfile'+str(myself)+'.log', 'w')
    logFile.writelines(str(self.logList))
    logFile.close()
    
    # Send the list of messages to the server for comparison
    print('Sending the list of messages to the server for comparison...')
    clientSock = socket(AF_INET, SOCK_STREAM)
    clientSock.connect((SERVER_ADDR, SERVER_PORT))
    msgPack = pickle.dumps(self.logList)
    clientSock.send(msgPack)
    clientSock.close()
    
    # Reset the handshake counter
    handShakeCount = 0

    exit(0)

def waitToStart():
  """
  Aguarda o sinal de início do servidor de comparação que envia a quantidade de mensagens a ser trocadas.
  """
  (conn, addr) = serverSock.accept()
  msgPack = conn.recv(1024)
  msg = pickle.loads(msgPack)
  myself = msg[0]
  nMsgs = msg[1]
  conn.send(pickle.dumps('Peer process '+str(myself)+' started.'))
  conn.close()
  return (myself,nMsgs)

# From here, code is executed when program starts:

# Registrando este processo com o grupo de gerenciamento
registerWithGroupManager()

while 1:
  print('Waiting for signal to start...')
  (myself, nMsgs) = waitToStart() # Aguarda o sinal de início do servidor de comparação
  
  print('I am up, and my ID is: ', str(myself))
  print('I will send ', str(nMsgs), ' messages.')

  if nMsgs == 0:
    print('Terminating.')
    exit(0)

  # Wait for other processes to be ready
  # To Do: fix bug that causes a failure when not all processes are started within this time
  # (fully started processes start sending data messages, which the others try to interpret as control messages) 
  time.sleep(5)

  # Create receiving message handler
  msgHandler = MsgHandler(recvSocket)
  msgHandler.start()
  print('Handler started')

  PEERS = getListOfPeers()
  
  # Send handshakes
  # To do: Must continue sending until it gets a reply from each process
  #        Send confirmation of reply
  for addrToSend in PEERS:
    print('Sending handshake to ', addrToSend)
    msg = ('READY', myself)
    msgPack = pickle.dumps(msg)
    sendSocket.sendto(msgPack, (addrToSend,PEER_UDP_PORT))
    #data = recvSocket.recvfrom(128) # Handshadke confirmations have not yet been implemented

  print('Main Thread: Sent all handshakes. handShakeCount=', str(handShakeCount))

  while (handShakeCount < N):
    pass  # find a better way to wait for the handshakes

  # Send a sequence of data messages to all other processes 
  for msgNumber in range(0, nMsgs):
    # Wait some random time between successive messages
    time.sleep(random.randrange(10,100)/1000)
    
    # Increment Lamport clock before sending
    timestamp = lamport_clock.increment()
    
    # Create message with Lamport timestamp and send to all peers
    msg = (MSG_DATA, myself, msgNumber, timestamp)
    msgPack = pickle.dumps(msg)
    
    # Send to all peers
    for addrToSend in PEERS:
      sendSocket.sendto(msgPack, (addrToSend,PEER_UDP_PORT))
      print(f'Sent message {msgNumber} with timestamp {timestamp}')
    
    # Also deliver to ourselves
    message = Message(myself, msgNumber, timestamp)
    message_queue.add_message(message)
    message_queue.add_acknowledgment(timestamp, myself, msgNumber, myself)

  # Tell all processes that I have no more messages to send
  for addrToSend in PEERS:
    msg = (-1,-1)
    msgPack = pickle.dumps(msg)
    sendSocket.sendto(msgPack, (addrToSend,PEER_UDP_PORT))
