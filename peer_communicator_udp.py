from socket import socket, AF_INET, SOCK_DGRAM, SOCK_STREAM
from constants import PEER_UDP_PORT, PEER_TCP_PORT, GROUPMNGR_ADDR, GROUPMNGR_TCP_PORT, SERVER_ADDR, SERVER_PORT, N
import threading
import random
import time
import pickle
from requests import get

# handShakes = [] # not used; only if we need to check whose handshake is missing

# Counter to make sure we have received handshakes from all other processes
handshake_count = 0

handshake_complete_event = threading.Event()

# Armazena a lista de peers
PEERS = []

# Socket UDP para enviar e receber mensagens
send_socket = socket(AF_INET, SOCK_DGRAM)
receive_socket = socket(AF_INET, SOCK_DGRAM)
receive_socket.bind(('0.0.0.0', PEER_UDP_PORT))

# Socket TCP para receber o sinal de início do servidor de comparação:
serverSock = socket(AF_INET, SOCK_STREAM)
serverSock.bind(('0.0.0.0', PEER_TCP_PORT))
serverSock.listen(1)

def get_public_ip():
    """
    Retorna o endereço IP público do peer.
    """
    ip_adress = get('https://api.ipify.org').content.decode('utf8')
    print('My public IP address is: {}'.format(ip_adress))
    return ip_adress


def register_with_group_manager():
    """
    Registra o peer com o gerente de grupo.
    """
    client_sock = socket(AF_INET, SOCK_STREAM)
    print('Connecting to group manager: ', (GROUPMNGR_ADDR, GROUPMNGR_TCP_PORT))
    client_sock.connect((GROUPMNGR_ADDR, GROUPMNGR_TCP_PORT))
    ipAddr = get_public_ip()
    req = {"op": "register", "ipaddr": ipAddr, "port": PEER_UDP_PORT}
    msg = pickle.dumps(req)
    print('Registering with group manager: ', req)
    client_sock.send(msg)
    client_sock.close()


def get_list_of_peers():
    """
    Obtém a lista de peers do gerente de grupo.
    """
    clientSock = socket(AF_INET, SOCK_STREAM)
    print('Connecting to group manager: ', (GROUPMNGR_ADDR, GROUPMNGR_TCP_PORT))
    clientSock.connect((GROUPMNGR_ADDR, GROUPMNGR_TCP_PORT))
    req = {"op": "list"}
    msg = pickle.dumps(req)
    print('Getting list of peers from group manager: ', req)
    clientSock.send(msg)
    msg = clientSock.recv(2048)
    PEERS = pickle.loads(msg)
    print('Got list of peers: ', PEERS)
    clientSock.close()
    return PEERS


class MessageHandler(threading.Thread):
	"""
	Handler de recebimento de handshakes e mensagens.
	"""
	def __init__(self, sock):
		threading.Thread.__init__(self)
		self.sock = sock

	def run(self):
		print('Handler is ready. Waiting for the handshakes...')
		global handshake_count

		# Lista de mensagens recebidas
		log_list = []

		# received_handshakes = {peer: False for peer in PEERS}

		# Recebendo handshakes e enviando confirmações de handshake.
		# Espera-se até que N handshakes sejam recebidos.
		# TODO: verificar se o handshake é recebido de todos os peers e não apenas N
		while handshake_count < N:
			message_pack, sender_address = self.sock.recvfrom(1024)
			msg = pickle.loads(message_pack)
			
			if msg[0] == 'READY': # Recebendo handshake
				handshake_count = handshake_count + 1
				print('--- Handshake received: ', msg[1])

				# Enviando confirmação de handshake
				ack_message = ('HANDSHAKE_ACK', myself)
				ack_message_pack = pickle.dumps(ack_message)
				self.sock.sendto(ack_message_pack, sender_address)
				
				# Utilizar para verificar se todos os peers enviaram o handshake
				# handShakes[msg[1]] = 1

		handshake_complete_event.set()

		print('Secondary Thread: Received all handshakes. Entering the loop to receive messages.')

		# Recebendo as mensagens dos outros peers até que
		# todos eles mandem uma mensagem de parada (-1, -1)
		stop_count = 0
		while True:
			message_pack = self.sock.recv(1024)  # receive data from client
			msg = pickle.loads(message_pack)
			
			# Se for uma mensagem de parada, isto é, o peer não tem mais mensagens para enviar,
			# incrementa o contador de paradas até N
			if msg[0] == -1:
				stop_count = stop_count + 1
				if stop_count == N:
					break  # parando quando todos os peers sinalizarem encerramento
			else:
				# Guardando a mensagem recebida
				print('Message ' + str(msg[1]) + ' from process ' + str(msg[0]))
				log_list.append(msg)

		# Salvando a lista de mensagens recebidas por este peer em um arquivo de log
		logfile = open('logfile' + str(myself) + '.log', 'w')
		logfile.writelines(str(log_list))
		logfile.close()

		# Enviando a lista log de mensagens recebidas por este peer para o servidor de comparação
		print('Sending the list of messages to the server for comparison...')
		clientSock = socket(AF_INET, SOCK_STREAM)
		clientSock.connect((SERVER_ADDR, SERVER_PORT))
		message_pack = pickle.dumps(log_list)
		clientSock.send(message_pack)
		clientSock.close()

		# Resetando o contador de handshake para uma próxima rodada de envio de mensagens
		handshake_count = 0

		# Encerrando a thread de recebimento de mensagens
		exit(0)


def wait_to_start():
    """
    Aguarda o sinal de início do servidor de comparação.
    Retorna o ID deste peer e o número de mensagens que ele deve enviar.
    """
    # Recebendo o sinal de início do servidor de comparação
    (conn, addr) = serverSock.accept()
    message_pack = conn.recv(1024)
    msg = pickle.loads(message_pack)
    myself = msg[0]
    number_of_messages = msg[1]

    # Enviando uma confirmação de que o peer iniciou
    conn.send(pickle.dumps('Peer process ' + str(myself) + ' started.'))
    conn.close()

    return (myself, number_of_messages)


if __name__ == '__main__':
    # Registrando o peer com o gerente de grupo
	register_with_group_manager()
      
	while True:
		# Aguardando o sinal de início do servidor de comparação
		print('Waiting for signal to start...')
		(myself, number_of_messages) = wait_to_start()
		print('I am up, and my ID is: ', str(myself))

		# Se o número de mensagens for 0, encerra o programa
		if number_of_messages == 0:
			print('Terminating.')
			exit(0)

		# TODO: Verificar se é necessário mais alguma alteração para garantir que todos
		# os peers estão prontos para receber mensagens
		#	Wait for other processes to be ready
		#	TODO: fix bug that causes a failure when not all processes are started within this time
		#	(fully started processes start sending data messages, which the others try to interpret as control messages)
		#	time.sleep(5)

		# Criando o handler de recebimento de handshakes e mensagens,
		# que é iniciado em uma thread separada para não bloquear a execução do programa
		msgHandler = MessageHandler(receive_socket)
		msgHandler.start()
		print('Handler started')

		# Recebendo a lista de peers
		PEERS = get_list_of_peers()

		# Dicionário para armazenar as confirmações de handshake recebidas de cada peer
		handshake_confirmations = {peer: False for peer in PEERS}

		# Enviando handshakes para todos os peers e esperando as confirmações de cada um
		for adress_to_send in PEERS:
			print('Sending handshake to ', adress_to_send)
			msg = ('READY', myself)
			message_pack = pickle.dumps(msg)
			send_socket.sendto(message_pack, (adress_to_send, PEER_UDP_PORT))

			# Esperando a confirmação de handshake do peer destinatário atual
            # TODO: Verificar a necessidade de reenviar o handshake caso a confirmação demore demais
			try:
				print("Waiting for handshake confirmation from ", adress_to_send)
				send_socket.settimeout(2.0)
						
				while True:
                    # Fica aguardando por 2 segundos para receber a confirmação de handshake
                    # de forma interminente
					response_pack = send_socket.recvfrom(1024)
					response = pickle.loads(response_pack)

					if response[0] == 'HANDSHAKE_ACK' and response[1] == adress_to_send:
						print('Handshake confirmed from ', response[1])
						handshake_confirmations[response[1]] = True
						break
			except socket.timeout:
				print('Timeout waiting for handshake confirmation from ', adress_to_send)
				break
                
		print('Main Thread: Sent all handshakes. handshake_count=', str(handshake_count))

		# Aguardando a quantidade de handshakes recebidos ser igual ao número de peers.
		# Eles são recebidos na thread do MessageHandler.
		# while handshake_count < N:
		# 	pass  # TODO: find a better way to wait for the handshakes
		handshake_complete_event.wait()

		# Enviando todas as mensagens que ele deve para os outros peers
		for message_number in range(0, number_of_messages):
			# Esperando um tempo aleatório entre a mensagem anterior e a próxima
			time.sleep(random.randrange(10, 100) / 1000)
					
			# Enviando a mensagem para todos os peers
			msg = (myself, message_number)
			message_pack = pickle.dumps(msg)
			for adress_to_send in PEERS:
				send_socket.sendto(message_pack, (adress_to_send, PEER_UDP_PORT))
				print('Sent message ' + str(message_number))

		# Sinalizando para todos os peers que ele não tem mais mensagens para enviar
		for adress_to_send in PEERS:
			msg = (-1, -1)
			message_pack = pickle.dumps(msg)
			send_socket.sendto(message_pack, (adress_to_send, PEER_UDP_PORT))
