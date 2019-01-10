import block
import random
import hashlib
import datetime
import threading
import blockchain
import sqldb

MSG_LASTBLOCK = 'getlastblock'
MSG_BLOCK = 'block'
MSG_BLOCKS = 'getblocks'
MSG_HELLO = 'hello'
MSG_PEERS = 'peers'

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

def validateBlockHeader(b):
    # check block header
    if b.hash == b.calcBlockhash():
        return True
    return False

def validateBlock(block, lastBlock):
	# check block chaining
	if block.prev_hash == lastBlock.hash:
		return True
	return False

def validateChain(bc, l):
    lastBlock = bc.getLastBlock()
    print lastBlock.blockInfo()
    for b in l:
        b = sqldb.dbtoBlock(b)
        if not validateBlockHeader(b): # invalid
            return b, True
        if validateBlock(b, lastBlock):
            lastBlock = b
            bc.addBlocktoBlockchain(b)
            sqldb.writeBlock(b)
            sqldb.writeChain(b)
        else: # fork
            return b, False
    return None, False

def selectChain():
    pass

class Consensus:

    def __init__(self, difficulty):
        self.difficulty = difficulty
        self.type = "PoS"
        self.MAX_NONCE = 2 ** 32
        self.target = 2 ** (4 * self.difficulty) - 1
    
    def POS(self, lastBlock, round, node, skip):
        """ Find nonce for PoW returning block information """
        # chr simplifies merkle root and add randomness
        tx = chr(random.randint(1,100))
        mroot = hashlib.sha256(tx).hexdigest()
        c_header = str(lastBlock.hash) + mroot + round # candidate header
        if skip.is_set():
            return False, False, False, False
        hash_result = hashlib.sha256(str(c_header)+str(round)).hexdigest()
        
        if hash_result:
            return hash_result, tx
        
        return False,round, tx

    def generateNewblock(self, lastBlock, skip=False):
        """ Loop for PoS in case of solve challenge, returning new Block object """
        while True:
            new_hash, tx = self.POS(lastBlock, round, node, skip)

            if new_hash:
                return block.Block(lastBlock.index + 1, lastBlock.hash, round, node, new_hash, tx)
        
    def rawConsensusInfo(self):
        return {'difficulty': self.difficulty, 'type': self.type}
