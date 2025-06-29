from socket import socket, AF_INET, SOCK_STREAM
import pickle
from constants import SERVER_PORT, GROUPMNGR_ADDR, GROUPMNGR_TCP_PORT, PEER_TCP_PORT, N
import time
import sys

server_sock = socket(AF_INET, SOCK_STREAM)
server_sock.bind(('0.0.0.0', SERVER_PORT))
server_sock.listen(N)

def main_loop():
	"""
	Loop principal do servidor de comparação.
	Responsável por receber a quantidade de mensagens que cada peer deve enviar,
	obter a lista de peers e iniciá-los.
	"""
	cont = 1
	while True:
		number_of_messages = prompt_user()
		if number_of_messages == 0:
			break
		client_sock = socket(AF_INET, SOCK_STREAM)
		client_sock.connect((GROUPMNGR_ADDR, GROUPMNGR_TCP_PORT))

		# Enviando uma requisição para o grupo manager para obter a lista de peers
		req = {"op": "list"}
		msg = pickle.dumps(req)
		client_sock.send(msg)

		# Recebendo a lista de peers do grupo manager
		msg = client_sock.recv(2048)
		client_sock.close()

		# Exibindo a lista de peers
		peerList = pickle.loads(msg)
		print("List of Peers: ", peerList)

		# Iniciando os peers
		start_peers(peerList, number_of_messages)

		# Aguardando os logs de mensagens dos peers
		print('Now, wait for the message logs from the communicating peers...')
		wait_for_logs_and_compare(number_of_messages)
	server_sock.close()

def prompt_user():
	number_of_messages = int(input('Enter the number of messages for each peer to send (0 to terminate)=> '))
	return number_of_messages

def start_peers(peerList, number_of_messages):
	peer_number = 0
	
	# Iniciando cada peer
	for peer in peerList:
		client_sock = socket(AF_INET, SOCK_STREAM)
		client_sock.connect((peer, PEER_TCP_PORT))
		
		# Enviando ao peer o seu número e a quantidade de mensagens que ele deve enviar
		msg = (peer_number, number_of_messages)
		msgPack = pickle.dumps(msg)
		client_sock.send(msgPack)

		# Recebendo uma confirmação de que o peer iniciou
		msgPack = client_sock.recv(512)
		print(pickle.loads(msgPack))
		client_sock.close()
		peer_number = peer_number + 1

def wait_for_logs_and_compare(N_MSGS):
	# Loop to wait for the message logs for comparison:
	number_of_peers = 0
	messages = [] # each msg is a list of tuples (with the original messages received by the peer processes)

	# Recebe os logs de mensagens dos peers, é sempre esperado que sejam N logs (6)
	while number_of_peers < N:
		# Recebendo o log de mensagens do peer
		(conn, addr) = server_sock.accept()
		msgPack = conn.recv(32768)
		print('Received log from peer')
		conn.close()

		# Adicionando o log de mensagens ao array de logs
		messages.append(pickle.loads(msgPack))
		number_of_peers = number_of_peers + 1

	unordered_messages = 0

	# Verificando se as mensagens estão ordenadas
	for j in range(0, N_MSGS-1):
		first_message = messages[0][j]
		for i in range(1, N-1):
			if first_message != messages[i][j]:
				unordered_messages = unordered_messages + 1
				break
	
	print ('Found ' + str(unordered_messages) + ' unordered message rounds')

if __name__ == "__main__":
	main_loop()
