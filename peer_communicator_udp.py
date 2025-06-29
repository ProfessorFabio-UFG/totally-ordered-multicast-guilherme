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
        

        log_list = []

        # Esperando até que todos os peers tenham enviado o handshake
        # para garantir que todos os peers estão sincronizados antes de começar a troca de mensagens
        while handshake_count < N:
            msgPack = self.sock.recv(1024)
            msg = pickle.loads(msgPack)
            
            if msg[0] == 'READY': # Recebendo handshake
				# TODO: enviar confirmação de handshake e aguardar confirmação
                handshake_count = handshake_count + 1
                print('--- Handshake received: ', msg[1])
                
				# Utilizar para verificar se todos os peers enviaram o handshake
				# handShakes[msg[1]] = 1

        print('Secondary Thread: Received all handshakes. Entering the loop to receive messages.')

		# Recebendo as mensagens dos outros peers até que
        # todos eles mandem uma mensagem de parada (-1, -1)
        stop_count = 0
        while True:
            msgPack = self.sock.recv(1024)  # receive data from client
            msg = pickle.loads(msgPack)
            
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
        msgPack = pickle.dumps(log_list)
        clientSock.send(msgPack)
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
    msgPack = conn.recv(1024)
    msg = pickle.loads(msgPack)
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

		# Wait for other processes to be ready
		# TODO: fix bug that causes a failure when not all processes are started within this time
		# (fully started processes start sending data messages, which the others try to interpret as control messages)
		time.sleep(5)

		# Criando o handler de recebimento de mensagens,
        # que é iniciado em uma thread separada para não bloquear a execução do programa
		msgHandler = MessageHandler(receive_socket)
		msgHandler.start()
		print('Handler started')

		PEERS = get_list_of_peers()

        # Enviando handshakes para todos os peers
        # TODO:
		# - Os handshakes devem ser enviados até que seja recebida uma confirmação de cada um dos peers
        # - Deve ser enviada uma confirmação de cada handshake recebido
		for adress_to_send in PEERS:
			print('Sending handshake to ', adress_to_send)
			msg = ('READY', myself)
			msgPack = pickle.dumps(msg)
			send_socket.sendto(msgPack, (adress_to_send, PEER_UDP_PORT))
			# data = receive_socket.recvfrom(128) # Handshake confirmations have not yet been implemented
		
		print('Main Thread: Sent all handshakes. handshake_count=', str(handshake_count))

		# Aguardando a quantidade de handshakes recebidos ser igual ao número de peers.
        # Eles são recebidos na thread do MessageHandler.
		while handshake_count < N:
			pass  # TODO: find a better way to wait for the handshakes

		# Enviando todas as mensagens que ele deve para os outros peers
		for message_number in range(0, number_of_messages):
			# Esperando um tempo aleatório entre a mensagem anterior e a próxima
			time.sleep(random.randrange(10, 100) / 1000)
                  
			# Enviando a mensagem para todos os peers
			msg = (myself, message_number)
			msgPack = pickle.dumps(msg)
			for adress_to_send in PEERS:
				send_socket.sendto(msgPack, (adress_to_send, PEER_UDP_PORT))
				print('Sent message ' + str(message_number))

		# Sinalizando para todos os peers que ele não tem mais mensagens para enviar
		for adress_to_send in PEERS:
			msg = (-1, -1)
			msgPack = pickle.dumps(msg)
			send_socket.sendto(msgPack, (adress_to_send, PEER_UDP_PORT))
