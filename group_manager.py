from socket import socket, AF_INET, SOCK_STREAM
import pickle
from constants import GROUPMNGR_TCP_PORT, N

port = GROUPMNGR_TCP_PORT
membership = []

def server_loop():
    server_sock = socket(AF_INET, SOCK_STREAM)
    server_sock.bind(('0.0.0.0', port))
    server_sock.listen(N) # N é o máximo de conexões simultâneas permitidas

    print(f"Group manager started on port {port}")

    while True:
        # Aguarda a conexão de um processo
        (conn, addr) = server_sock.accept()
        msgPack = conn.recv(2048)
        req = pickle.loads(msgPack)

		# Se a operação for de registro, adiciona o peer à lista de membros
        if req["op"] == "register":
            membership.append((req["ipaddr"], req["port"]))
            print('Registered peer: ', req)

		# Se a operação for de listagem, envia a lista de peers para o processo que solicitou
        elif req["op"] == "list":
            list_peers = []
            for m in membership:
                list_peers.append(m[0])
            print('List of peers sent to server: ', list_peers)
            conn.send(pickle.dumps(list_peers))

        else:
            pass  # fix (send back an answer in case of unknown op)

        conn.close()

if __name__ == "__main__":
	server_loop()
