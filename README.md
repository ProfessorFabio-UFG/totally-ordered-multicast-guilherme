# MPComm
Very simple demo of multicast communication without coordination.
A set of peer processes is established and each process multicasts a sequence of messages to all other processes at random intervals. Messages are stamped with the ID of the sending process and a local sequence number defined by the sending process. This is a simple attempt to demonstrate the problem of message ordering (or, in this version, the lack of it).

The peer processes run the PeerCommunicatorUDP.py program, which has two separate threads, one for sending and the other for receiving messages. A basic handshaking protocol is used to synchronize the processes before they actually start multicasting the sequence of messages. Also, a fixed timer is set to allow plenty of time to start all processes on the participating machines. At the end, each process sends the sequence received messages to a server, which compares the sequences of messages received by all the processes to determine the number of messages received out of order (actually, the number of rounds in which at least one process received a different message form the others).

In order to actually see the problem, it is necessary to run the peer processes on different networks (e.g., run some of the processes in one region of the cloud, whereas the others are run on another region).

## Arquivos

### `comparison_server.py`

Este script é responsável por:
1. Receber do usuário a quantidade de mensagens que cada peer deve enviar
2. Obter a lista de peers
3. Iniciar os peers (enviando o número do peer a ele mesmo e a quantidade de mensagens que ele deve enviar)
4. Aguardar os logs de mensagens dos peers
5. Comparar os logs de mensagens dos peers e determinar se as mensagens estão ordenadas

### `group_manager.py`

Este script é responsável por:
1. Receber o registro de um peer
2. Enviar a lista de peers para o processo que solicitou

### `peer_communicator_udp.py`

Este script é responsável por:
1. Controlar a dinâmica de um peer.
2. Enviar e receber handshakes para sincronizar os peers.
3. Enviar e receber mensagens para os outros peers.
4. Sinalizar para todos os peers que ele não tem mais mensagens para enviar.

# Fluxo de execução

## 1. Handshake

- `send_handshakes_with_confirmation`
	- Envia handshakes (READY) para todos os peers.
	- Aguarda confirmações (HANDSHAKE_ACK) de todos os N-1 peers.
	- Reenvia handshakes automaticamente se não houver confirmação no tempo esperado.

- `MessageHandler`
	- Recebe handshakes dos peers (READY) e responde com HANDSHAKE_ACK.
	- Continua escutando handshakes tardios e enviando confirmações.

- Objetivo:
	- ✅ Receber N-1 handshakes.
	- ✅ Confirmar N-1 handshakes enviados.

## 2. Envio de mensagens

- Cada mensagem contém: (id do processo, número da mensagem, timestamp de Lamport).
- O relógio de Lamport é incrementado antes do envio.
- A mensagem é adicionada à fila local para ordenação (message_queue).
- A mensagem é enviada a todos os peers.
- A mensagem é registrada como pendente até receber ACK de todos.

## 3. Thread de Reenvio

- `resend_messages_thread`
	- Monitora mensagens pendentes.
	- Se uma mensagem não recebeu todos os ACKs no tempo limite, reenvia para os peers pendentes.

## 4. Recepção de mensagens

- `MessageHandler`
    - Recebe mensagens de outros peers.
    - Atualiza o relógio de Lamport: lamport_clock = max(local_clock, received_timestamp) + 1.
    - Adiciona a mensagem à fila (message_queue).
    - Marca o recebimento no acks_received.
    - Envia ACK para todos os peers.
    - Tenta entregar mensagens se todas as confirmações estiverem presentes.
- Recepção de ACKs
    - Atualiza acks_received.
    - Verifica se a mensagem pode ser entregue.
    - Atualiza pending_messages (remove peers pendentes se confirmado).

## 5. Encerramento
	- Cada processo envia (-1, -1) indicando que não tem mais mensagens.
	- O `MessageHandler` espera receber N-1 encerramentos.
	- Os logs de mensagens entregues são enviados ao servidor.