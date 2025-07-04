# Parte 1 do trabalho de Sistemas Distribuídos

## Handshakes

Para garantir que todos os peers estejam prontos antes do envio de mensagens:

1. Cada peer envia N-1 handshakes e espera receber N-1 acks:
```
send_handshakes_with_confirmation(PEERS)
```

2. Cada peer também recebe N-1 handshakes e envia N-1 acks em resposta:

```
if msg[0] == 'READY':
    # Envia HANDSHAKE_ACK
```

3. O recebimento de handshakes e envio de acks continua até que todos estejam sincronizados:

```
handshake_complete_event.wait()
handshake_ack_complete_event.wait()
```

## Envio de mensagens

Cada peer envia suas mensagens de forma ordenada:

1. Incremento no relógio de Lamport:

```python
lamport_clock += 1
```

2. Construção da mensagem:

```python
msg = (myself, message_number, lamport_clock)
```

3. Adição da mensagem à fila:

```python
heapq.heappush(message_queue, ((lamport_clock, myself), msg))
```

4. Registro das pendências de ACKs:

```python
key = (current_lamport_clock, message_number)
pending_messages[key] = {
	'message_data': msg,
	'message_pack': message_pack,
	'peers_pending_ack': set(PEERS.copy()),
	'sent_time': time.time(),
}
```

5. Envio da mensagem para os N-1 peers:

```python
for adress_to_send in PEERS:
	send_socket.sendto(message_pack, (adress_to_send, PEER_UDP_PORT))
```

## Reenvio de mensagens

Para garantir a confiabilidade:

1. Verificação periódica da lista de mensagens aguardando ACKs:

```python
for key, message_info in list(pending_messages.items()):
    if current_time - message_info['sent_time'] > message_timeout:
        # Reenviar
```

2. Reenvio da mensagem a quem não confirmou:

```python
send_socket.sendto(message_info['message_pack'], (peer, PEER_UDP_PORT))
```

3. Espera de 1 segundo antes da nova checagem:

```python
time.sleep(1)
```

## Recebimento de mensagens

### 1. Handshakes recebidos são respondidos com ACKs:

```python
self.send_sock.sendto(ack_message_pack, (sender_address[0], PEER_UDP_PORT))
```

### 2. Ao receber mensagem:

Atualiza Lamport:

```python
lamport_clock = max(lamport_clock, received_timestamp) + 1
```
Adiciona à fila:

```python
heapq.heappush(message_queue, ((received_timestamp, sender_id), msg))
```

Marca o recebimento da mensagem com ACKs:

```python
acks_received[key].add(myself)
acks_received[key].add(sender_id)
```

Envia ACK:

```python
self.send_sock.sendto(ack_pack, (peer, PEER_UDP_PORT))
```

### 3. Ao receber ACK

- Atualiza pendências e verifica entrega:

```python
acks_received[key].add(ack_sender)
```

Cada ACK recebido é registrado no conjunto de confirmações da mensagem correspondente.

- Verifica se já pode entregar mensagens:

Após registrar o ACK, o sistema verifica se a mensagem no topo da fila já recebeu todos os ACKs necessários e entrega todas as mensagens possíveis:

```python
while message_queue:
    (top_key, top_message) = message_queue[0]
    if len(acks_received.get(top_key, set())) >= N:
        heapq.heappop(message_queue)
        log_list.append(top_message)
        print(f"Delivered message {top_message[1]} from process {top_message[0]} with timestamp {top_message[2]}")
    else:
        break  # A próxima mensagem ainda não tem todos os ACKs
```

### 4. Ao receber N-1 mensagens de encerramento:

Para o recebimento e realiza o envio dos logs ao servidor de comparação.


## Sobre threads

- O envio de handshakes, o recebimento de handshakes e o reenvio de mensagens são feitos em threads separadas, rodando em paralelo.

- O envio e recebimento de mensagens também acontecem em threads distintas.

- Devido ao compartilhamento de variáveis (ex.: message_queue, acks_received), foi implementado controle de acesso via locks:
	```python
	with lamport_clock_lock, message_queue_lock, acks_lock:
		# operação protegida
	```