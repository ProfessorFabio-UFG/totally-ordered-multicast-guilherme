[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/TyBiAFsA)
# Totally Ordered Multicast with Lamport Clocks

This project demonstrates a totally ordered multicast communication system using Lamport's logical clocks. The system ensures that all processes deliver messages in the same order, preventing message ordering inconsistencies in distributed systems.

## Overview

A set of peer processes is established where each process multicasts a sequence of messages to all other processes at random intervals. Messages are stamped with:
- The ID of the sending process
- A local sequence number
- A Lamport timestamp

The system uses a basic handshaking protocol to synchronize processes before they start multicasting messages. At the end, each process sends its sequence of received messages to a server, which verifies that all processes delivered messages in the same order.

## Lamport Logical Clocks

Lamport logical clocks are a mechanism for ordering events in a distributed system. They work as follows:

1. Each process maintains a local counter (clock)
2. When a process performs an internal event, it increments its counter
3. When a process sends a message:
   - It increments its counter
   - It timestamps the message with the counter value
4. When a process receives a message with timestamp `t`:
   - It updates its counter to be greater than both its current counter and `t`
   - Specifically: `counter = max(local_counter, t) + 1`

This creates a "happens-before" relationship between events and ensures a partial ordering of messages across the system.

## Implementation Details

The implementation consists of several key components:

1. **Lamport Clock (`lamport_clock.py`)**:
   - Maintains the logical clock for each process
   - Provides methods to increment and update the clock based on message timestamps

2. **Message Queue**:
   - Buffers received messages
   - Delivers messages in order of their Lamport timestamps
   - Uses process IDs to break ties when timestamps are equal

3. **Peer Communication (`PeerCommunicatorUDP.py`)**:
   - Handles message sending and receiving
   - Maintains the Lamport clock
   - Orders message delivery using the message queue

4. **Comparison Server (`comparisonServer.py`)**:
   - Verifies that all processes delivered messages in the same order
   - Reports any ordering violations

## Running the Application

To demonstrate the total ordering of messages:

1. Start the Group Manager:
   ```bash
   python GroupMngr.py
   ```

2. Start the Comparison Server:
   ```bash
   python comparisonServer.py
   ```

3. Start multiple peer processes on different machines:
   ```bash
   python PeerCommunicatorUDP.py
   ```

The system will demonstrate that all processes deliver messages in the same total order, thanks to Lamport's logical clocks.

## Message Ordering Guarantee

The implementation ensures that if two processes deliver the same set of messages, they will deliver them in the same order. This is achieved by:

1. Using Lamport timestamps to create a partial ordering of messages
2. Breaking ties using process IDs when timestamps are equal
3. Buffering messages in a priority queue until they can be delivered in order

This guarantees that all processes will observe the same sequence of message deliveries, which is crucial for maintaining consistency in distributed applications.

## Network Requirements

For optimal demonstration of the ordering properties, it's recommended to run the peer processes on different networks (e.g., different regions of a cloud provider). This helps demonstrate how the system maintains message ordering even in the presence of variable network delays and out-of-order message delivery at the network level.
