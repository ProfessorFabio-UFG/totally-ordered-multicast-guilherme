from dataclasses import dataclass
from typing import Any, List, Dict, Set
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
    def __init__(self, num_processes: int):
        self.queue = []
        self.delivered = set()

        # Dicionário que armazena os acknowledgments para cada mensagem
        # Chave: (timestamp, sender_id, msg_content)
        # Valor: conjunto de IDs de processos que reconheceram a mensagem
        self.acknowledgments: Dict[tuple, Set[int]] = {}

        self.num_processes = num_processes
    
    def add_message(self, message: Message):
        """
        Adiciona uma mensagem à fila de mensagens.
        Se a mensagem já foi entregue, ela não é adicionada à fila.
        """
        msg_id = (message.timestamp, message.sender_id, message.msg_content)
        if msg_id not in self.delivered:
            heapq.heappush(self.queue, message)
            if msg_id not in self.acknowledgments:
                self.acknowledgments[msg_id] = set()
    
    def add_acknowledgment(self, timestamp: int, sender_id: int, msg_content: Any, from_process: int):
        """
        Adiciona um acknowledgment para uma mensagem específica.
        """
        msg_id = (timestamp, sender_id, msg_content)
        if msg_id in self.acknowledgments:
            self.acknowledgments[msg_id].add(from_process)
    
    def get_deliverable_messages(self) -> List[Message]:
        """
        Obtém todas as mensagens que estão prontas para serem entregues.
        Uma mensagem é entregável apenas se:
        1. Está na cabeça da fila (menor timestamp)
        2. Foi reconhecida por todos os processos (incluindo o próprio processo)
        """
        deliverable = []
        while self.queue:
            message = self.queue[0]  # Peek at head of queue
            msg_id = (message.timestamp, message.sender_id, message.msg_content)
            
            # Verifica se a mensagem foi reconhecida por todos os processos
            # Precisamos de num_processes acknowledgments (incluindo o próprio processo)
            if msg_id in self.acknowledgments and len(self.acknowledgments[msg_id]) >= self.num_processes:
                # Remove a mensagem da fila e marca como entregue
                heapq.heappop(self.queue)
                self.delivered.add(msg_id)
                del self.acknowledgments[msg_id]
                deliverable.append(message)
            else:
                break  # Se a primeira mensagem não pode ser entregue, as outras também não podem
            
        return deliverable 