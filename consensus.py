import block
import random
import hashlib
import threading
import blockchain
import sqldb
import time
import math

MSG_LASTBLOCK = 'getlastblock'
MSG_BLOCK = 'block'
MSG_BLOCKS = 'getblocks'
MSG_HELLO = 'hello'
MSG_PEERS = 'peers'


TIMEOUT = 2 # Time in seconds
THRESHOLD = 2 # Threshold that the blockchain can grown and accept one previous block with the best round.
DIFFICULTY = 2

def handleMessages(bc, messages):
    cmd = messages[0] if isinstance(messages, list) else str(messages)
    cmd = cmd.lower()
    if cmd == MSG_LASTBLOCK:
        return bc.getLastBlock()
    elif cmd == MSG_HELLO:
        return MSG_HELLO
    elif cmd == MSG_BLOCKS:
        return sqldb.blocksQuery(messages)
    elif cmd == MSG_BLOCK:
        return sqldb.blockQuery(messages)
    else:
        return None


class Consensus:

    def __init__(self):
        self.type = "PoS"
        self.target = 2**(256 - DIFFICULTY) - 1
    
    def POS(self, lastBlock, round, node, stake, skip):
        """ Find nonce for PoW returning block information """
        # chr simplifies merkle root and add randomness
        tx = chr(random.randint(1,100))
        
        c_header = str(lastBlock.hash) + str(round) + str(node) # candidate header
        if skip.is_set():
            return False, False

        hash_result = hashlib.sha256(str(c_header)).hexdigest()

        print(format(int(hash_result, 16),"0256b"))
        print(format(self.target,"0256b"))

        if int(hash_result,16) < stake * self.target:
            print("OK")
            return hash_result, tx
        
        return False, tx

    def generateNewblock(self, lastBlock, node, stake, skip=False):
        """ Loop for PoS in case of solve challenge, returning new Block object """
        r = 0
        while True and not skip.is_set():
            r = r + 1
            round = lastBlock.round + r
            new_hash, tx = self.POS(lastBlock, round, node, stake, skip)
            
            print('new block' if new_hash else 'try again!')
            
            if new_hash:
                return block.Block(lastBlock.index + 1, lastBlock.hash, round, node, new_hash, tx)
            
            time.sleep(TIMEOUT)

        return None      
        
    def rawConsensusInfo(self):
        return {'difficulty': DIFFICULTY, 'type': self.type}
