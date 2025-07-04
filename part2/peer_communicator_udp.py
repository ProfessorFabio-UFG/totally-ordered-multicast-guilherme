from socket import socket, AF_INET, SOCK_DGRAM, SOCK_STREAM
from constants import PEER_UDP_PORT, PEER_TCP_PORT, GROUPMNGR_ADDR, GROUPMNGR_TCP_PORT, SERVER_ADDR, SERVER_PORT, N
import threading
import random
import time
import pickle
import os
import heapq
from requests import get

# Quantidade de mensagens a serem enviadas
number_of_messages = 100

# Counter to make sure we have received handshakes from all other processes
handshake_count = 0

# Evento para indicar que todos os handshakes foram recebidos
handshake_complete_event = threading.Event()
handshake_ack_complete_event = threading.Event()

# Relógio de Lamport
lamport_clock = 0

# Lista de mensagens recebidas
log_list = []

# Fila de mensagens recebidas antes de serem entregues
message_queue = []

# Dicionário para armazenar as confirmações de mensagem recebidas de cada peer
# Chave: (timestamp, sender_id), quem mandou a mensagem e quando ela foi enviada
# Valor: Conjunto de peers que receberam a mensagem
acks_received = {}

# Controle de envio de mensagens enviadas aguardando acks
pending_messages = {}
# Chave: (timestamp, message_number), quem mandou a mensagem e quando ela foi enviada
# Valor: (message_data, peers_pending_ack), a mensagem (para reenvio posterior caso necessário) e a lista de peers que ainda não enviaram o ack
message_timeout = 5.0 # tempo máximo de espera para o ack de uma mensagem

# Mapeamento entre IDs dos peers e seus IPs
peer_id_to_ip = {}  # {0: '52.10.54.6', 1: '52.12.78.132', 2: '54.92.143.133'}
ip_to_peer_id = {}  # {'52.10.54.6': 0, '52.12.78.132': 1, '54.92.143.133': 2}

# Flag para indicar que todas as threads devem parar
stop_threads_flag = False

# Armazena a lista de peers
PEERS = []

# Dicionário para armazenar as confirmações de handshake recebidas de cada peer
# Chave: IP do peer, quem mandou o handshake e quando ele foi enviado
# Valor: True se o handshake foi confirmado, False caso contrário
handshake_confirmations = {}

# Locks para sincronização
message_queue_lock = threading.Lock()
acks_lock = threading.Lock()
pending_messages_lock = threading.Lock()
lamport_clock_lock = threading.Lock()
handshake_confirmations_lock = threading.Lock()

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

	my_ip = get_public_ip()
	if my_ip in PEERS:
		PEERS.remove(my_ip)

	print('Got list of peers: ', PEERS)
	clientSock.close()
	return PEERS

def wait_all_my_message_acks_received(number_of_messages, myself):
	"""
	Aguarda todos os ACKs relacionados a mensagens deste peer.
	"""
	while True:
		if not pending_messages:
			print("All messages received")
			return
		
		print(f"Still waiting for acks of messages.... Pending messages:")
		for key, message_info in pending_messages.items():
			print(f"Message {key[1]} from {key[0]}")
			print(f"\tAcks received: {message_info['peers_pending_ack']}")
			print(f"\tSent time: {message_info['sent_time']}")
			print(f"\tPeers pending ack: {message_info['peers_pending_ack']}")
			print(f"\tMessage pack: {message_info['message_pack']}")
		time.sleep(5)

def flush_queue_until_empty():
	"""
	Entrega todas as mensagens restantes na fila.
	"""
	# Exibindo a fila de mensagens
	print("Mensagens que sobraram na fila:")
	for message in message_queue:
		print(f"Message in queue: {message}")
		print(f"\tAcks received: {acks_received.get(message[0], set())}")

	while message_queue:
		top_key, top_message = message_queue[0]
		if len(acks_received.get(top_key, set())) >= N:
			heapq.heappop(message_queue)
			log_list.append(top_message)
			print(f"Delivered (late) {top_message}")
		else:
			time.sleep(0.05)

def resend_messages_thread():
	"""
	Verifica se há mensagens pendentes de ack e as reenvia caso necessário.
	"""
	global stop_threads_flag

	while not stop_threads_flag:
		print("Resend thread: checking for messages to resend...")
		current_time = time.time()
		messages_to_resend = []

		# Verificando mensagens que passaram do tempo de espera para o ack
		for key, message_info in list(pending_messages.items()):
			if current_time - message_info['sent_time'] > message_timeout:
				messages_to_resend.append((key, message_info))

		# Reenviando as mensagens que passaram do tempo de espera para o ack
		for key, message_info in messages_to_resend:
			timestamp, message_number = key
			peers_to_resend = list(message_info['peers_pending_ack'])

			print(f"Resending message {message_number} to {peers_to_resend}")

			for peer in peers_to_resend:
				send_socket.sendto(message_info['message_pack'], (peer, PEER_UDP_PORT))

			message_info['sent_time'] = current_time

		time.sleep(1)
	stop_threads_flag = False

def send_handshakes_with_confirmation(PEERS, max_retries=5, timeout_per_retry=2.0):
	"""
	Envia handshakes para todos os peers e aguarda confirmações de handshake.
	"""
	global handshake_confirmations

	# Inicializar tracking de confirmações
	with handshake_confirmations_lock:
		handshake_confirmations = {peer: False for peer in PEERS}

	for retry in range(max_retries):
		# Identificar peers que ainda não confirmaram
		peers_to_send = []
		with handshake_confirmations_lock:
			peers_to_send = [peer for peer, confirmed in handshake_confirmations.items() if not confirmed]
		
		if not peers_to_send:
			print("All handshakes confirmed!")
			handshake_ack_complete_event.set()
			return True
		
		print(f"\nRetry {retry + 1}/{max_retries}: Sending handshakes to {len(peers_to_send)} peers")
		
		# Enviar handshakes para peers não confirmados
		for peer_addr in peers_to_send:
			print(f'Sending handshake to {peer_addr}')
			msg = ('READY', myself)
			message_pack = pickle.dumps(msg)
			send_socket.sendto(message_pack, (peer_addr, PEER_UDP_PORT))
		
		# Aguardar confirmações por um tempo
		time.sleep(timeout_per_retry)

		# Verificar status
		with handshake_confirmations_lock:
			confirmed_count = sum(1 for confirmed in handshake_confirmations.values() if confirmed)
			print(f"Confirmed: {confirmed_count}/{len(PEERS)}")

	# Verificar resultado final
	with handshake_confirmations_lock:
		missing = [peer for peer, confirmed in handshake_confirmations.items() if not confirmed]
		if missing:
			print(f"WARNING: Failed to get handshake confirmation from: {missing}")
			return False

	handshake_ack_complete_event.set()

	return True

class MessageHandler(threading.Thread):
	"""
	Handler de recebimento de handshakes e mensagens.
	"""
	def __init__(self, sock, send_sock):
		threading.Thread.__init__(self)
		self.sock = sock
		self.send_sock = send_sock

	def run(self):
		print('Handler is ready. Waiting for the handshakes...')
		global handshake_count
		global log_list
		global handshake_confirmations

		# Lista de mensagens recebidas
		log_list = []

		# received_handshakes = {peer: False for peer in PEERS}

		# Recebendo handshakes e enviando confirmações de handshake.
		# Espera-se até que N handshakes sejam recebidos.
		while handshake_count < N-1:
			message_pack, sender_address = self.sock.recvfrom(1024)
			msg = pickle.loads(message_pack)
			
			if msg[0] == 'READY': # Recebendo handshake
				handshake_count = handshake_count + 1
				print('--- Handshake received: ', msg[1])

				# Construindo o mapeamento entre IDs dos peers e seus IPs
				peer_id_to_ip[msg[1]] = sender_address[0]
				ip_to_peer_id[sender_address[0]] = msg[1]

				# Enviando confirmação de handshake
				print(f"Sending handshake confirmation to {sender_address} with socket {PEER_UDP_PORT}")
				ack_message = ('HANDSHAKE_ACK', myself)
				ack_message_pack = pickle.dumps(ack_message)
				self.send_sock.sendto(ack_message_pack, (sender_address[0], PEER_UDP_PORT))
				
				# Utilizar para verificar se todos os peers enviaram o handshake
				# handShakes[msg[1]] = 1

		handshake_complete_event.set()

		print('Secondary Thread: Received all handshakes. Entering the loop to receive messages.')

		global lamport_clock

		# Recebendo as mensagens dos outros peers até que
		# todos eles mandem uma mensagem de parada (-1, -1)
		stop_count = 0
		while True:
			message_pack, sender_address = self.sock.recvfrom(1024)  # receive data from client
			msg = pickle.loads(message_pack)
			
			# Se for uma mensagem de parada, isto é, o peer não tem mais mensagens para enviar,
			# incrementa o contador de paradas até N
			if msg[0] == -2:
				# Sinalização de que o sistema pode parar quando possível
				for adress_to_send in PEERS:
					msg = (-1, -1, lamport_clock)
					message_pack = pickle.dumps(msg)
					send_socket.sendto(message_pack, (adress_to_send, PEER_UDP_PORT))
					print(f"Sent message {-1} with timestamp {lamport_clock} to {adress_to_send}")
			elif msg[0] == -1:
				stop_count = stop_count + 1
				if stop_count >= N-2: # -2 porque o peer que manda -2, não manda -1
					# flush_queue_until_empty() # entrega todas as mensagens restantes na fila
					print("Todos os peers sinalizaram encerramento. Saindo do loop de recebimento de mensagens.")
					break  # parando quando todos os peers sinalizarem encerramento
			elif msg[0] == 'HANDSHAKE_ACK':
				# Registrando a confirmação de handshake
				with handshake_confirmations_lock:
					handshake_confirmations[sender_address[0]] = True
					print(f"Received handshake confirmation from {msg[1]}")
			elif msg[0] == "READY":
				# Recebendo handshake e enviando confirmação de handshake
				# handshake_count = handshake_count + 1 # não é necessário continuar contando os handshakes
				print(f"Received handshake from {msg[1]}")
				# Enviando confirmação de handshake
				print(f"Sending handshake confirmation to {msg[1]} with socket {PEER_UDP_PORT}")
				ack_message = ('HANDSHAKE_ACK', myself)
				ack_message_pack = pickle.dumps(ack_message)
				self.send_sock.sendto(ack_message_pack, (sender_address[0], PEER_UDP_PORT))
			elif isinstance(msg, tuple) and msg[0] == "ACK": # recebendo confirmação de recebimento de mensagem
				_, ack_sender, ack_timestamp, ack_message_sender_id = msg
				key = (ack_timestamp, ack_message_sender_id)

				print(f"Received ACK from {ack_sender} for message from {ack_message_sender_id} with timestamp {ack_timestamp}")

				with message_queue_lock, acks_lock:
					# Registrando a confirmação de recebimento da mensagem pelo peer que enviou o ack
					if key not in acks_received:
						acks_received[key] = set()
					acks_received[key].add(ack_sender)

					# Tentando entregar as mensagens da fila
					while message_queue:
						(top_key, top_message) = message_queue[0]
						if len(acks_received.get(top_key, set())) >= N: # se todos os peers receberam a mensagem do topo da fila
							# Entregando a mensagem
							heapq.heappop(message_queue)
							log_list.append(top_message)
							print(f"Delivered message {top_message[1]} from process {top_message[0]} with timestamp {top_message[2]}")
						else:
							break # a próxima mensagem não tem todos os acks ainda

				# Removendo o peer da lista de pendentes se for uma mensagem deste peer
				if ack_message_sender_id == myself:
					ack_sender_ip = peer_id_to_ip[ack_sender]

					messages_to_remove = []

					# Procurando a mensagem correspondente na lista de acks pendentes
					for pending_key, pending_info in pending_messages.items():
						pending_timestamp, pending_message_number = pending_key

						if pending_timestamp == ack_timestamp: # se é a mensagem que está sendo confirmada
							if ack_sender_ip in pending_info['peers_pending_ack']: # se estava pendente mesmo
								pending_info['peers_pending_ack'].remove(ack_sender_ip)
								print(f"Removed the peer {ack_sender} ({ack_sender_ip}) from pending messages for message {pending_message_number}")
							
							if not pending_info['peers_pending_ack']: # se não há mais peers pendentes, removendo a mensagem da lista de pendentes
								messages_to_remove.append(pending_key)	
								print(f"All acks received for message {pending_key[1]}")

					# Removendo as mensagens da lista de pendentes
					for key_to_remove in messages_to_remove:
						del pending_messages[key_to_remove]
			else:
				if isinstance(msg, tuple) and len(msg) == 3: # garantindo que é uma mensagem normal e não de controle
					sender_id, message_number, received_timestamp = msg

					print(f"Received message {message_number} from process {sender_id} with timestamp {received_timestamp}")

					# Incrementando o relógio de Lamport com base na mensagem recebida
					with message_queue_lock, acks_lock, lamport_clock_lock:
						lamport_clock = max(lamport_clock, received_timestamp) + 1

						# Enfileirando a mensagem recebida
						heapq.heappush(message_queue, ((received_timestamp, sender_id), msg))

						# Marcando ACKs de recebimento da mensagem
						key = (received_timestamp, sender_id)
						if key not in acks_received:
							acks_received[key] = set()
						acks_received[key].add(myself)
						acks_received[key].add(sender_id) # o próprio peer que enviou a mensagem também confirma a mensagem recebida

						# Já que recebemos uma nova mensagem, verificamos se há mensagens na fila para serem entregues
						# Tentando entregar as mensagens da fila
						while message_queue:
							(top_key, top_message) = message_queue[0]
							if len(acks_received.get(top_key, set())) >= N: # se todos os peers receberam a mensagem do topo da fila
								# Entregando a mensagem
								heapq.heappop(message_queue)
								log_list.append(top_message)
								print(f"Delivered message {top_message[1]} from process {top_message[0]} with timestamp {top_message[2]}")
							else:
								break # a próxima mensagem não tem todos os acks ainda

					# Enviando confirmação de recebimento da mensagem para todos os peers
					ack = ("ACK", myself, received_timestamp, sender_id)
					ack_pack = pickle.dumps(ack)
					for peer in PEERS:
						self.send_sock.sendto(ack_pack, (peer, PEER_UDP_PORT))
						print(f"Sent ACK to {peer} for message {message_number} from {sender_id} with timestamp {received_timestamp}")

					# Se for uma mensagem para este peer, respondemos com uma mensagem para um novo peer aleatório
					if int(message_number[-1]) == myself:
						# Se chegamos ao limite de mensagens, sinalizamos que o sistema pode para quando possível (-2)
						if len(message_number) >= number_of_messages:
							msg = (-2, -1, lamport_clock)
						else:
							peer_id_to_send = random.randint(0, N-1)
							while peer_id_to_send == myself:
								peer_id_to_send = random.randint(0, N-1)
							message_number = message_number + str(peer_id_to_send)

							msg = (myself, message_number, lamport_clock)

						message_pack = pickle.dumps(msg)

						heapq.heappush(message_queue, ((lamport_clock, myself), msg))

						key = (lamport_clock, myself)
						if key not in acks_received:
							acks_received[key] = set()
						acks_received[key].add(myself) # Nós mesmos "confirmamos" a nossa própria mensagem

						# Registrando a mensagem como pendente de ack para todos os peers
						with pending_messages_lock:
							key = (lamport_clock, message_number)
							pending_messages[key] = {
								'message_data': msg,
								'message_pack': message_pack,
								'peers_pending_ack': set(PEERS.copy()),
								'sent_time': time.time(),
							}

						# Enviando a mensagem para todos os peers
						for adress_to_send in PEERS:
							send_socket.sendto(message_pack, (adress_to_send, PEER_UDP_PORT))
							print(f'Sent message {msg} with timestamp {lamport_clock} to {adress_to_send}')

		# Aguarda todos os ACKs das mensagens deste peer
		wait_all_my_message_acks_received(number_of_messages, myself)

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
	global number_of_messages

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

def stop_all_threads():
    """
    Para todas as threads antes de resetar variáveis.
    """
    # Sinalizar para threads pararem
    global stop_threads_flag
    stop_threads_flag = True
    
    # Aguardar um tempo para threads terminarem
    time.sleep(2)

def reset_global_variables():
	"""
	Reseta as variáveis globais para uma próxima rodada de envio de mensagens.
	"""
	print("Stopping all threads...")
	stop_all_threads()

	global lamport_clock, message_queue, acks_received, pending_messages
	global peer_id_to_ip, ip_to_peer_id, handshake_count, log_list
	global handshake_confirmations

	print("Resetting global state for new execution...")

	lamport_clock = 0
	message_queue = []
	acks_received = {}
	pending_messages = {}
	peer_id_to_ip = {}
	ip_to_peer_id = {}
	handshake_count = 0
	log_list = []
	handshake_confirmations = {}

	# Resetar o evento de handshake
	handshake_complete_event.clear()


if __name__ == '__main__':
    # Registrando o peer com o gerente de grupo
	register_with_group_manager()
    
	while True:
		# Aguardando o sinal de início do servidor de comparação
		print('Waiting for signal to start...')
		(myself, number_of_messages) = wait_to_start()
		os.system('clear')
		print('I am up, and my ID is: ', str(myself))

		# Resetando as variáveis globais para uma próxima rodada de envio de mensagens
		reset_global_variables()

		# Se o número de mensagens for 0, encerra o programa
		if number_of_messages == 0:
			print('Terminating.')
			exit(0)

		# Criando o handler de recebimento de handshakes e mensagens,
		# que é iniciado em uma thread separada para não bloquear a execução do programa
		msgHandler = MessageHandler(receive_socket, send_socket)
		msgHandler.start()
		print('Handler started')

		# Thread de reenvio de mensagens
		resend_thread = threading.Thread(target=resend_messages_thread, daemon=True)
		resend_thread.start()
		print('Resend thread started')

		# Recebendo a lista de peers
		PEERS = get_list_of_peers()

		print("Iniciando handshake com a espera de confirmações")
		handshake_success = send_handshakes_with_confirmation(PEERS)
		if not handshake_success:
			print("Handshake com confirmações de handshake falhou. Saindo do programa.")
			exit(1)

		handshake_ack_complete_event.wait() # esperando a confirmação de handshake de todos os peers
		handshake_complete_event.wait() # esperando o handshake de todos os peers
		
                
		print('Main Thread: Sent all handshakes. handshake_count=', str(handshake_count))

		# Enviando a mensagem inicial
		if myself == 0:
			lamport_clock = 1
			message_number = "0"

			# Escolhendo um peer aleatório para enviar a mensagem inicial
			peer_id_to_send = random.randint(0, N-1)
			while peer_id_to_send == myself:
				peer_id_to_send = random.randint(0, N-1)
			message_number = "0" + str(peer_id_to_send)
			peer_ip_to_send = peer_id_to_ip[peer_id_to_send]

			msg = (myself, message_number, lamport_clock)
			message_pack = pickle.dumps(msg)

			# Adicionando a própria mensagem à fila para ordenação total
			heapq.heappush(message_queue, ((lamport_clock, myself), msg))

			key = (lamport_clock, myself)
			if key not in acks_received:
				acks_received[key] = set()
			acks_received[key].add(myself) # Nós mesmos "confirmamos" a nossa própria mensagem

			# Enviando a mensagem para o peer escolhido
			# send_socket.sendto(message_pack, (peer_ip_to_send, PEER_UDP_PORT))
			# print(f'Sent message {0} with timestamp {lamport_clock} to {peer_ip_to_send}')

			# Registrando a mensagem como pendente de ack para todos os peers
			with pending_messages_lock:
				key = (lamport_clock, message_number)
				pending_messages[key] = {
					'message_data': msg,
					'message_pack': message_pack,
					'peers_pending_ack': set(PEERS.copy()),
					'sent_time': time.time(),
				}

			# Enviando a mensagem para todos os peers
			for adress_to_send in PEERS:
				send_socket.sendto(message_pack, (adress_to_send, PEER_UDP_PORT))
				print(f'Sent message {msg} with timestamp {lamport_clock} to {adress_to_send}')

		# # Enviando todas as mensagens que ele deve para os outros peers
		# for message_number in range(0, number_of_messages):
		# 	# Esperando um tempo aleatório entre a mensagem anterior e a próxima
		# 	time.sleep(random.randrange(10, 100) / 1000)

		# 	# Incrementando o relógio de Lamport
		# 	with lamport_clock_lock, message_queue_lock, acks_lock:
		# 		lamport_clock += 1
		# 		current_lamport_clock = lamport_clock
					
		# 		# Criando a mensagem
		# 		msg = (myself, message_number, current_lamport_clock)
		# 		message_pack = pickle.dumps(msg)

		# 		# Adicionando a própria mensagem à fila para ordenação total
		# 		heapq.heappush(message_queue, ((current_lamport_clock, myself), msg))

		# 		key = (current_lamport_clock, myself)
		# 		if key not in acks_received:
		# 			acks_received[key] = set()
		# 		acks_received[key].add(myself) # Nós mesmos "confirmamos" a nossa própria mensagem
	
		# 	# Registrando a mensagem como pendente de ack para todos os peers
		# 	with pending_messages_lock:
		# 		key = (current_lamport_clock, message_number)
		# 		pending_messages[key] = {
		# 			'message_data': msg,
		# 			'message_pack': message_pack,
		# 			'peers_pending_ack': set(PEERS.copy()),
		# 			'sent_time': time.time(),
		# 		}

		# 	# Enviando a mensagem para todos os peers
		# 	for adress_to_send in PEERS:
		# 		send_socket.sendto(message_pack, (adress_to_send, PEER_UDP_PORT))
		# 		print(f'Sent message {message_number} with timestamp {lamport_clock}')

		# Sinalizando para todos os peers que ele não tem mais mensagens para enviar
		# for adress_to_send in PEERS:
		# 	msg = (-1, -1, lamport_clock)
		# 	message_pack = pickle.dumps(msg)
		# 	send_socket.sendto(message_pack, (adress_to_send, PEER_UDP_PORT))

		print("Waiting for MessageHandler to finish...")
		msgHandler.join(timeout=10)  # Aguarda até 10 segundos

		if msgHandler.is_alive():
			print("WARNING: MessageHandler still running!")

		print("MessageHandler finished. Ready for next iteration.")