import block
import random
import hashlib
import threading
import blockchain
import sqldb
import time

MSG_LASTBLOCK = 'getlastblock'
MSG_BLOCK = 'block'
MSG_BLOCKS = 'getblocks'
MSG_HELLO = 'hello'
MSG_PEERS = 'peers'


TIMEOUT = 5 # Time in seconds
THRESHOLD = 2 # Threshold that the blockchain can grown and accept one previous block with the best round.

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
	# check if the block has a valid threshold
			
def blockPosition(block, bc):
	#check if the block has a valid threshold
	chainPos, bcPos = validatePositionBlock(block, bc)		
	if(chainPos):
		return True, bcPos
	else:
		return False, bc
	
def validatePositionBlock(block, bc):	
    i = 0
    while i < THRESHOLD:
    	if(len(bc)> 1):
    		bc.pop()
		chainBlock = bc.getLastblock()
    		if(block.prev_hash == chainBlock.prev_hash and chainBlock.round > block.round):
	     		return True, bc
        i = i + 1

    return False, False
			
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

    def __init__(self, difficulty=128):
        self.difficulty = difficulty
        self.type = "PoS"
        self.target = 2 ** (256 - self.difficulty)
        self.first_timeout = True
    
    def POS(self, lastBlock, round, node, stake, skip):
        """ Find nonce for PoW returning block information """
        # chr simplifies merkle root and add randomness
        tx = chr(random.randint(1,100))
        
        c_header = str(lastBlock.hash) + str(round) + str(node) # candidate header
        if skip.is_set():
            return False, False

        hash_result = hashlib.sha256(str(c_header)).hexdigest()

        print int(hash_result, 16)
        print self.target

        if int(hash_result, 16) < stake * self.target:
            return hash_result, tx
        
        return False, tx

    def generateNewblock(self, lastBlock, round, node, stake, skip=False):
        """ Loop for PoS in case of solve challenge, returning new Block object """
        r = 0
        self.first_timeout = True
        while True:
            r = r + 1
            round = lastBlock.round + r
            new_hash, tx = self.POS(lastBlock, round, node, stake, skip)
            print new_hash

            if self.first_timeout:
                self.first_timeout = False
                time.sleep(TIMEOUT)
            
            if new_hash:
                self.first_timeout = True
                return block.Block(lastBlock.index + 1, lastBlock.hash, round, node, new_hash, tx)
            

            #time.sleep(TIMEOUT)
                
        
    def rawConsensusInfo(self):
        return {'difficulty': self.difficulty, 'type': self.type}
