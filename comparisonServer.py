from socket import *
import pickle
from constMP import *
import time
import sys

serverSock = socket(AF_INET, SOCK_STREAM)
serverSock.bind(('0.0.0.0', SERVER_PORT))
serverSock.listen(6)

def mainLoop():
	"""
	Loop principal do servidor de comparação.
	Responsável por receber as mensagens de registro de processos e manter o registro.
	"""
	cont = 1
	while 1:
		nMsgs = promptUser() # Solicita ao usuário o número de mensagens para cada processo enviar
		if nMsgs == 0:
			break

		clientSock = socket(AF_INET, SOCK_STREAM) # Cria um socket para o cliente
		clientSock.connect((GROUPMNGR_ADDR,GROUPMNGR_TCP_PORT)) # Conecta ao servidor de gerenciamento de grupo
		req = {"op":"list"} # Cria uma mensagem de solicitação de lista de processos
		
		# Solicitando a lista de processos ao servidor de gerenciamento de grupo
		msg = pickle.dumps(req)
		clientSock.send(msg)
		msg = clientSock.recv(2048)
		clientSock.close()
		peerList = pickle.loads(msg)
		print("List of Peers: ", peerList)
		
		# 
		startPeers(peerList, nMsgs)
		print('Now, wait for the message logs from the communicating peers...')
		waitForLogsAndCompare(nMsgs)
	serverSock.close()

def promptUser():
	"""
	Função para solicitar ao usuário o número de mensagens para cada processo enviar.
	"""
	nMsgs = int(input('Enter the number of messages for each peer to send (0 to terminate)=> '))
	return nMsgs

def startPeers(peerList,nMsgs):
	"""
	Função para iniciar a execução de cada processo.
	Responsável por conectar a cada processo e enviar o sinal de 'initiate'.
	"""
	peerNumber = 0
	for peer in peerList:
		clientSock = socket(AF_INET, SOCK_STREAM)
		clientSock.connect((peer, PEER_TCP_PORT))
		
		# Enviando o sinal de 'initiate' para o processo,
		# que é o número do processo e o número de mensagens a ser enviado
		msg = (peerNumber, nMsgs)
		msgPack = pickle.dumps(msg)
		clientSock.send(msgPack)

		msgPack = clientSock.recv(512) # Recebe a resposta do processo
		print(pickle.loads(msgPack)) # Imprime a resposta
		clientSock.close() # Fecha a conexão com o processo
		peerNumber = peerNumber + 1

def waitForLogsAndCompare(N_MSGS):
	"""
	Loop para aguardar as mensagens de log para comparação.
	"""
	numPeers = 0
	msgs = [] # Cada mensagem é uma lista de tuplas (com as mensagens originais recebidas pelos processos)

	# Recebendo as mensagens de log dos processos
	# até que o número de processos seja igual ao número de processos participantes
	while numPeers < N:
		(conn, addr) = serverSock.accept()
		msgPack = conn.recv(32768)
		print ('Received log from peer')
		conn.close()
		msgs.append(pickle.loads(msgPack))
		numPeers = numPeers + 1

	unordered = 0 # Contador de mensagens fora de ordem

	# Comparando as listas de mensagens
	# Com os timestamps de Lamport, as mensagens devem estar na mesma ordem em todos os processos
	for j in range(0, N_MSGS-1):
		firstMsg = msgs[0][j]  # (sender_id, msg_content, timestamp)
		for i in range(1, N-1):
			if firstMsg != msgs[i][j]:
				print(f"Ordering mismatch at position {j}:")
				print(f"Process 0 received: {firstMsg}")
				print(f"Process {i} received: {msgs[i][j]}")
				unordered = unordered + 1
				break
	
	if unordered == 0:
		print("All messages were delivered in total order across all processes!")
	else:
		print(f'Found {unordered} unordered message rounds')


# Initiate server:
mainLoop()
