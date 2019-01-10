import datetime
import hashlib
import random
import json


class block:
    def __init__(self, index, prev_hash, b_hash=None, tx=''):
        self.index = index
        self.prev_hash = prev_hash
        self.tx = tx
        self.mroot = self.calcMerkleRoot()
        if b_hash:
            self.hash = b_hash
        else: # mostly genesis
            self.hash = self.calcBlockhash()

    def calcMerkleRoot(self):
        return hashlib.sha256(self.tx).hexdigest()

    def calcBlockhash(self):
        pass

    def rawblockInfo(self):
        pass
    
    def blockInfo(self):
        return json.dumps(self.rawblockInfo(), indent=4)

class powBlock(block):
    def __init__(self, index, prev_hash, nonce, b_hash=None, timestamp=str(datetime.datetime.now()), tx=''):
        super().__init__(index, prev_hash, b_hash=None, tx='')
        self.timestamp = timestamp
        self.nonce = nonce

    def calcBlockhash(self):
        # Check concatenate order
        h = self.prev_hash + self.mroot + str(self.timestamp) + str(self.nonce)
        return hashlib.sha256(h.encode('utf-8')).hexdigest()

    def rawblockInfo(self):
        return {'index': str(super().index) , 'timestamp': str(self.timestamp) , 'prev_hash': self.prev_hash , 'hash': self.hash, 'nonce': str(self.nonce), 'merkle_root': self.mroot, 'tx': self.tx}
    

class posBlock(block):
    def __init__(self, index, prev_hash,round, node, b_hash=None, tx=''):
        super().__init__(index, prev_hash, b_hash=None, tx='')
        self.round = round
        self.node = node

    def calcBlockhash(self):
        # Check concatenate order
        h = self.prev_hash + self.mroot + str(self.round) + self.node
        return hashlib.sha256(h.encode('utf-8')).hexdigest()

    def rawblockInfo(self):
        return {'index': str(self.index) , 'round': str(self.round) , 'prev_hash': self.prev_hash , 'hash': self.hash, 'node': self.node, 'merkle_root': self.mroot, 'tx': self.tx}