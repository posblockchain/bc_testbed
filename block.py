import datetime
import hashlib
import random
import json


class Block:
    def __init__(self, index, prev_hash, round, node, b_hash=None, tx=''):
        self.index = index
        self.prev_hash = prev_hash
        self.tx = tx
        self.round = round
        self.node = node
        self.mroot = self.calcMerkleRoot()
        if b_hash:
            self.hash = b_hash
        else: # mostly genesis
            self.hash = self.calcBlockhash()

    def calcMerkleRoot(self):
        return hashlib.sha256(self.tx).hexdigest()

    def calcBlockhash(self):
        # Check concatenate order
        h = self.prev_hash + self.mroot + str(self.round) + self.node
        return hashlib.sha256(h.encode('utf-8')).hexdigest()

    def rawblockInfo(self):
        return {'index': str(self.index) , 'round': str(self.round) , 'prev_hash': self.prev_hash , 'hash': self.hash, 'node': self.node, 'merkle_root': self.mroot, 'tx': self.tx}
    
    def blockInfo(self):
        return json.dumps(self.rawblockInfo(), indent=4)   