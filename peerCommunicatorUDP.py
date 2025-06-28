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

PEERS = {}

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
  peer_addresses = pickle.loads(msg)
  print ('Got list of peers: ', peer_addresses)
  clientSock.close()
  
  # Create a mapping between peer IDs and their addresses
  # The ID is determined by the order in the list
  peer_map = {}
  for idx, addr in enumerate(peer_addresses):
    peer_map[idx] = addr
  
  return peer_map

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
    self.handshake_confirmations = set()  # Set to track which peers have confirmed our handshake
    self.all_handshakes_received = threading.Event()  # Event to signal when all handshakes are received
    self.received_handshakes = set()  # Set to track unique handshakes

  def run(self):
    print('Handler is ready. Waiting for the handshakes...')
    
    global handShakeCount
    global message_queue
    
    # Wait until handshakes are received from all other processes
    while handShakeCount < N:
      msgPack = self.sock.recv(1024)
      msg = pickle.loads(msgPack)
      if msg[0] == 'READY':
        peer_id = msg[1]
        if peer_id not in self.received_handshakes:  # Only process if not received before
          self.received_handshakes.add(peer_id)
          handShakeCount = handShakeCount + 1
          print('--- Handshake received from peer:', peer_id)
          
          # Send confirmation back
          confirm_msg = ('READY_CONFIRM', myself)
          confirm_pack = pickle.dumps(confirm_msg)
          if peer_id in PEERS:
            sendSocket.sendto(confirm_pack, (PEERS[peer_id], PEER_UDP_PORT))
            print(f'--- Sent confirmation to peer {peer_id}')
          else:
            print(f'Warning: Peer {peer_id} not found in peer map')
          
          if handShakeCount == N:
            self.all_handshakes_received.set()
            
      elif msg[0] == 'READY_CONFIRM':
        confirming_peer = msg[1]
        if confirming_peer not in self.handshake_confirmations:
          self.handshake_confirmations.add(confirming_peer)
          print('--- Handshake confirmation received from peer:', confirming_peer)

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
          # Format: (MSG_DATA, sender_id, msg_content, timestamp)
          _, sender_id, msg_content, timestamp = msg
          print(f'Received data message {msg_content} from {sender_id} with timestamp {timestamp}')
          
          lamport_clock.update(timestamp)
          
          # Create Message object and add to queue
          message = Message(sender_id, msg_content, timestamp)
          message_queue.add_message(message)
          
          # Send acknowledgment to all peers (including ourselves)
          ack_msg = (MSG_ACK, sender_id, msg_content, timestamp, myself)
          ack_pack = pickle.dumps(ack_msg)
          
          # Send to all peers
          for peer_id, addr in PEERS.items():
            sendSocket.sendto(ack_pack, (addr, PEER_UDP_PORT))
          
          # Also acknowledge to ourselves
          message_queue.add_acknowledgment(timestamp, sender_id, msg_content, myself)
            
        elif msg_type == MSG_ACK:
          # Handle acknowledgment
          # Format: (MSG_ACK, sender_id, msg_content, timestamp, from_process)
          _, sender_id, msg_content, timestamp, from_process = msg
          print(f'Received ACK from {from_process} for message {msg_content} from {sender_id}')
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
    print(f'Log size: {len(self.logList)}')
    print(f'Log contents: {self.logList}')
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

def waitForHandshakes():
  """
  Envia handshakes para todos os peers e aguarda confirmação de todos eles.
  Só retorna quando todos os handshakes forem confirmados e recebidos.
  """
  # Send handshakes to all peers
  for peer_id, addr in PEERS.items():
    if peer_id != myself:  # Don't send to ourselves
      print('Sending handshake to peer', peer_id)
      msg = ('READY', myself)
      msgPack = pickle.dumps(msg)
      # Send each handshake 3 times to increase reliability
      for _ in range(3):
        sendSocket.sendto(msgPack, (addr, PEER_UDP_PORT))
        time.sleep(0.1)  # Small delay between retries

  print('Main Thread: Sent all handshakes, waiting for confirmations...')

  # Wait until we get confirmations from all peers with timeout
  timeout = 30  # 30 seconds timeout
  start_time = time.time()
  
  while len(msgHandler.handshake_confirmations) < N - 1:  # N-1 because we don't need confirmation from ourselves
    if time.time() - start_time > timeout:
      print('Warning: Timeout waiting for handshake confirmations')
      print(f'Received confirmations from: {msgHandler.handshake_confirmations}')
      print(f'Missing confirmations from peers: {set(range(N)) - {myself} - msgHandler.handshake_confirmations}')
      break
    time.sleep(0.1)  # Small sleep to prevent busy waiting
    
  print('Main Thread: All handshakes confirmed or timeout reached.')
  
  # Wait for all handshakes to be received with timeout
  if not msgHandler.all_handshakes_received.wait(timeout):
    print('Warning: Timeout waiting for all handshakes to be received')
    print(f'Received handshakes from: {msgHandler.received_handshakes}')
    print(f'Missing handshakes from peers: {set(range(N)) - msgHandler.received_handshakes}')
  
  print('Main Thread: Ready to start sending messages.')

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

  # Get the list of peers BEFORE starting the handler
  PEERS = getListOfPeers()

  # Create receiving message handler
  msgHandler = MsgHandler(recvSocket)
  msgHandler.start()
  print('Handler started')
  
  # Wait for all processes to be ready using the handshake mechanism
  waitForHandshakes()

  # Initialize message queue now that we know N
  message_queue = MessageQueue(N)

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
    for peer_id, addr in PEERS.items():
      sendSocket.sendto(msgPack, (addr, PEER_UDP_PORT))
      print(f'Sent message {msgNumber} with timestamp {timestamp}')
    
    # Also deliver to ourselves
    message = Message(myself, msgNumber, timestamp)
    message_queue.add_message(message)
    message_queue.add_acknowledgment(timestamp, myself, msgNumber, myself)

  # Tell all processes that I have no more messages to send
  for peer_id, addr in PEERS.items():
    msg = (-1,-1)
    msgPack = pickle.dumps(msg)
    sendSocket.sendto(msgPack, (addr, PEER_UDP_PORT))
