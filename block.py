import datetime
import hashlib
import random
import json


class Block:
    def __init__(self, index, prev_hash, round, node, arrive_time='', b_hash=None, tx=''):
        self.index = index
        self.prev_hash = prev_hash
        self.tx = tx
        self.round = round
        self.node = node
        self.mroot = self.calcMerkleRoot()
        self.arrive_time = arrive_time
        if b_hash:
            self.hash = b_hash
        else: # mostly genesis
            self.hash = self.calcBlockhash()

    def calcMerkleRoot(self):
        return hashlib.sha256(self.tx.encode('utf-8')).hexdigest()

    def calcBlockhash(self):
        # Check concatenate order
        h = str(self.prev_hash) + str(self.round) + str(self.node)
        return hashlib.sha256(h.encode('utf-8')).hexdigest()

    def rawblockInfo(self):
        return {'index': str(self.index) , 'round': str(self.round) , 'prev_hash': self.prev_hash , 'hash': self.hash, 'node': self.node, 'merkle_root': self.mroot, 'tx': self.tx, 'arrive_time': self.arrive_time}
    
    def blockInfo(self):
        return json.dumps(self.rawblockInfo(), indent=4)   