from dataclasses import dataclass
from typing import Any, List, Dict
import heapq

@dataclass
class Message:
    """
    Representa uma mensagem no sistema com timestamp de Lamport.
    """
    sender_id: int
    msg_content: Any
    timestamp: int
    
    def __lt__(self, other):
        """
        Este método define o resultado da comparação entre duas mensagens.
        A ordem é definida pelo timestamp e, em caso de empate, pelo ID do processo.
        """
        if self.timestamp != other.timestamp:
            return self.timestamp < other.timestamp
        return self.sender_id < other.sender_id

class LamportClock:
    """
    Implementação do relógio de Lamport para sincronização de mensagens.
    """
    def __init__(self):
        self.time = 0
    
    def get_time(self) -> int:
        return self.time
    
    def increment(self) -> int:
        self.time += 1
        return self.time
    
    def update(self, received_time: int) -> int:
        """
        Atualiza o relógio local com o timestamp recebido mais 1.
        """
        self.time = max(self.time, received_time) + 1
        return self.time

class MessageQueue:
    """
    Implementação de uma fila de mensagens com prioridade.

    Ela serve para garantir que as mensagens sejam entregues na ordem correta,
    mesmo que as mensagens cheguem fora de ordem. Então ela funciona como um 
    buffer de mensagens.
    """
    def __init__(self):
        self.queue = []
        self.delivered = set()
    
    def add_message(self, message: Message):
        """
        Adiciona uma mensagem à fila de mensagens.
        Se a mensagem já foi entregue, ela não é adicionada à fila.
        """
        msg_id = (message.timestamp, message.sender_id, message.msg_content)
        if msg_id not in self.delivered:
            heapq.heappush(self.queue, message)
    
    def get_deliverable_messages(self) -> List[Message]:
        """
        Obtém todas as mensagens que estão prontas para serem entregues.
        """
        deliverable = []
        while self.queue:
            message = self.queue[0]
            
            # Marca a mensagem como entregue e retorna ela
            msg_id = (message.timestamp, message.sender_id, message.msg_content)
            self.delivered.add(msg_id)
            deliverable.append(heapq.heappop(self.queue))
            
        return deliverable 